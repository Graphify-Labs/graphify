"""C# member-level interface dispatch (#3003).

`_report.Build()` on an injected `IReport` resolves to `IReport.Build()`, which
is what the call site names. The implementing `Report.Build()` is a separate
node with nothing joining the two, so a directed walk stops at the interface
and every chain through an injected dependency is cut there.

`resolve_csharp_interface_dispatch` links the interface's method to the
implementing method when the interface has exactly one implementer and that
implementer owns exactly one method of the same name. Ambiguity at either step
leaves the pair alone, the same single-owner guard the Pascal and Ruby
resolvers use.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=Path(tempfile.mkdtemp()))
    finally:
        os.chdir(old)
    dispatch = {(e["source"], e["target"]) for e in r["edges"]
                if e["relation"] == "dispatches_to"}
    return dispatch, r


def _find(r, label, id_contains):
    return next(n["id"] for n in r["nodes"]
                if n["label"] == label and id_contains in n["id"])


def _reachable(r, start: str) -> set[str]:
    adjacency: dict[str, list[str]] = {}
    for e in r["edges"]:
        adjacency.setdefault(e["source"], []).append(e["target"])
    seen = {start}
    queue = [start]
    while queue:
        for nxt in adjacency.get(queue.pop(0), []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


_INJECTED = {
    "IReport.cs": "public interface IReport { void Build(); }\n",
    "Report.cs": (
        "public class Report : IReport {\n"
        "    public void Build() { Format(); }\n"
        "    public void Format() { }\n"
        "}\n"
    ),
    "Runner.cs": (
        "public class Runner {\n"
        "    private readonly IReport _report;\n"
        "    public Runner(IReport report) { _report = report; }\n"
        "    public void Go() { _report.Build(); }\n"
        "}\n"
    ),
}


def test_single_implementer_links_the_interface_method(tmp_path):
    dispatch, r = _extract(tmp_path, _INJECTED)
    assert (_find(r, ".Build()", "ireport"), _find(r, ".Build()", "report_report")) in dispatch


def test_chain_through_an_injected_dependency_becomes_reachable(tmp_path):
    dispatch, r = _extract(tmp_path, _INJECTED)
    assert dispatch
    # Go -> IReport.Build -> Report.Build -> Format
    assert _find(r, ".Format()", "report") in _reachable(r, _find(r, ".Go()", "runner"))


def test_the_call_to_the_interface_method_is_kept(tmp_path):
    # Additive: the call site really does name the interface.
    _, r = _extract(tmp_path, _INJECTED)
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    assert (_find(r, ".Go()", "runner"), _find(r, ".Build()", "ireport")) in calls


def test_two_implementers_produce_no_edge(tmp_path):
    dispatch, _ = _extract(tmp_path, {"S.cs": (
        "public interface IR { void M(); }\n"
        "public class A : IR { public void M() { } }\n"
        "public class B : IR { public void M() { } }\n"
    )})
    assert not dispatch


def test_no_matching_member_produces_no_edge(tmp_path):
    dispatch, _ = _extract(tmp_path, {"S.cs": (
        "public interface IR { void Build(); }\n"
        "public class A : IR { public void Other() { } }\n"
    )})
    assert not dispatch


def test_overloads_collapsed_into_one_node_still_link(tmp_path):
    # The extractor mints one node per method name, so two overloads share it.
    # The guard counts distinct nodes, not `method` edge multiplicity, so this
    # is one candidate rather than a tie. Same reasoning as the dedup comment in
    # resolve_pascal_inherited_calls.
    dispatch, r = _extract(tmp_path, {"S.cs": (
        "public interface IR { void M(); }\n"
        "public class A : IR { public void M() { } public void M(int x) { } }\n"
    )})
    assert (_find(r, ".M()", "ir"), _find(r, ".M()", "s_a")) in dispatch


def test_abstract_base_class_is_out_of_scope(tmp_path):
    # `class Impl : Base` is an `inherits` edge, and a base method may well be
    # the real target, so walking inheritance is a different bet from dispatch.
    dispatch, _ = _extract(tmp_path, {"S.cs": (
        "public abstract class Base { public abstract void M(); }\n"
        "public class Impl : Base { public override void M() { } }\n"
    )})
    assert not dispatch


def test_interface_hierarchy_is_not_walked_transitively(tmp_path):
    # Known limit: IBase's only implementer is IChild, which declares nothing,
    # so IBase.M never reaches Impl.M. Walking the chain is follow-up work.
    dispatch, _ = _extract(tmp_path, {"S.cs": (
        "public interface IBase { void M(); }\n"
        "public interface IChild : IBase { }\n"
        "public class Impl : IChild { public void M() { } }\n"
    )})
    assert not dispatch


def test_java_interface_and_implementation_are_untouched(tmp_path):
    # The resolver is registered for .cs; a Java corpus must not gain the edge.
    dispatch, _ = _extract(tmp_path, {
        "IReport.java": "public interface IReport { void build(); }\n",
        "Report.java": "public class Report implements IReport { public void build() { } }\n",
    })
    assert not dispatch
