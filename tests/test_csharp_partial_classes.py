"""C# partial classes split across files (#2332).

`partial class Foo` declared in two files minted TWO class nodes (the node id
carries the per-file stem), so the type's members split across the halves and
every receiver-typed lookup on `Foo` bailed as ambiguous — cross-half calls
never resolved. `_merge_csharp_partial_class_nodes` collapses the halves onto
one canonical node, keyed by (namespace, label); same-named types in other
namespaces, non-partial declarations, and nested partial types are left alone.
"""
from __future__ import annotations

import os
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
        r = extract([Path(n) for n in files], cache_root=tmp_path / ".cache")
    finally:
        os.chdir(old)
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    return calls, r


def _nodes_labeled(r, label):
    return [n for n in r["nodes"] if n["label"] == label]


def _find(r, label, id_contains):
    return next(n["id"] for n in r["nodes"]
                if n["label"] == label and id_contains in n["id"])


_HALVES = {
    "FooPartA.cs": (
        "namespace App {\n"
        "    public partial class Foo {\n"
        "        public void Alpha() {}\n"
        "    }\n"
        "}\n"
    ),
    "FooPartB.cs": (
        "namespace App {\n"
        "    public partial class Foo {\n"
        "        public void Beta() { Alpha(); }\n"
        "    }\n"
        "}\n"
    ),
}


def test_partial_halves_merge_to_one_class_node(tmp_path):
    calls, r = _extract(tmp_path, _HALVES)
    foos = _nodes_labeled(r, "Foo")
    assert len(foos) == 1, f"partial halves must collapse to ONE class node, got {foos}"
    # Both halves' members hang off the canonical node.
    foo_nid = foos[0]["id"]
    methods = {e["target"] for e in r["edges"]
               if e["relation"] == "method" and e["source"] == foo_nid}
    labels = {n["label"] for n in r["nodes"] if n["id"] in methods}
    assert {".Alpha()", ".Beta()"} <= labels, \
        f"canonical Foo must own members from BOTH halves, got {labels}"


def test_cross_file_caller_resolves_into_both_halves(tmp_path):
    calls, r = _extract(tmp_path, {
        **_HALVES,
        "Caller.cs": (
            "namespace App {\n"
            "    public class Caller {\n"
            "        public void Run(Foo f) { f.Alpha(); f.Beta(); }\n"
            "    }\n"
            "}\n"
        ),
    })
    run = _find(r, ".Run()", "caller")
    alpha = _find(r, ".Alpha()", "foo")
    beta = _find(r, ".Beta()", "foo")
    assert (run, alpha) in calls, "receiver-typed call into half A must resolve"
    assert (run, beta) in calls, "receiver-typed call into half B must resolve"


def test_cross_half_unqualified_in_class_call_resolves(tmp_path):
    """Beta() in half B calls Alpha() declared in half A — an in-class
    unqualified call that spans the file boundary."""
    calls, r = _extract(tmp_path, _HALVES)
    alpha = _find(r, ".Alpha()", "foo")
    beta = _find(r, ".Beta()", "foo")
    assert (beta, alpha) in calls, "cross-half unqualified in-class call must resolve"


def test_same_name_different_namespace_not_merged(tmp_path):
    calls, r = _extract(tmp_path, {
        "A.cs": (
            "namespace Alpha { public partial class Foo { public void FromA() {} } }\n"
        ),
        "B.cs": (
            "namespace Beta { public partial class Foo { public void FromB() {} } }\n"
        ),
    })
    foos = _nodes_labeled(r, "Foo")
    assert len(foos) == 2, \
        f"same-named partials in DIFFERENT namespaces are distinct types: {foos}"


def test_non_partial_same_name_not_merged(tmp_path):
    calls, r = _extract(tmp_path, {
        "A.cs": (
            "namespace App { public partial class Foo { public void FromA() {} } }\n"
        ),
        "B.cs": (
            "namespace App { public class Foo { public void FromB() {} } }\n"
        ),
    })
    foos = _nodes_labeled(r, "Foo")
    assert len(foos) == 2, \
        f"a non-partial declaration never merges with a partial half: {foos}"


def test_nested_partial_not_merged(tmp_path):
    """Nested partial types are excluded: their ids omit the enclosing type
    name, so same-named nested pairs would falsely merge across outers."""
    calls, r = _extract(tmp_path, {
        "A.cs": (
            "namespace App {\n"
            "    public partial class Outer {\n"
            "        public partial class Inner { public void FromA() {} }\n"
            "    }\n"
            "}\n"
        ),
        "B.cs": (
            "namespace App {\n"
            "    public partial class Outer {\n"
            "        public partial class Inner { public void FromB() {} }\n"
            "    }\n"
            "}\n"
        ),
    })
    outers = _nodes_labeled(r, "Outer")
    inners = _nodes_labeled(r, "Inner")
    assert len(outers) == 1, "top-level partial halves still merge"
    assert len(inners) == 2, \
        f"nested partial types must NOT merge (id has no outer qualifier): {inners}"
