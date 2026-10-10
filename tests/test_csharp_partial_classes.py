"""C# partial classes split across files (#2332).

`partial class Foo` declared in two files minted TWO class nodes (the node id
carries the per-file stem), so the type's members split across the halves and
every receiver-typed lookup on `Foo` bailed as ambiguous — cross-half calls
never resolved. `_merge_csharp_partial_class_nodes` collapses the halves onto
one canonical node, keyed by (assembly, namespace, label); same-named types in
other namespaces, non-partial declarations, and nested partial types are left
alone. The assembly key is the nearest ancestor dir holding a `*.csproj`/
`*.fsproj`/`*.vbproj` (#2411: `partial` never fuses across assemblies), with
"" — halves under no project at all, which still merge — as the sentinel.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.extract import _merge_csharp_partial_class_nodes, extract


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


_TWO_ASSEMBLIES = {
    "src/AsmOne/AsmOne.csproj": "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n",
    "src/AsmOne/Widget.cs": (
        "namespace Shared {\n"
        "    public partial class Widget {\n"
        "        public void OnlyInAssemblyOne() {}\n"
        "    }\n"
        "}\n"
    ),
    "src/AsmOne/Widget.Part2.cs": (
        "namespace Shared {\n"
        "    public partial class Widget {\n"
        "        public void AlsoInAssemblyOne() {}\n"
        "    }\n"
        "}\n"
    ),
    "src/AsmTwo/AsmTwo.csproj": "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n",
    "src/AsmTwo/Widget.cs": (
        "namespace Shared {\n"
        "    public partial class Widget {\n"
        "        public void OnlyInAssemblyTwo() {}\n"
        "    }\n"
        "}\n"
    ),
}


def _widget_methods_by_assembly(r):
    """Map each Widget class node -> set of member-method labels hanging off it."""
    widgets = _nodes_labeled(r, "Widget")
    label_of = {n["id"]: n["label"] for n in r["nodes"]}
    return widgets, {
        w["id"]: {
            label_of[e["target"]] for e in r["edges"]
            if e["relation"] == "method" and e["source"] == w["id"]
        }
        for w in widgets
    }


def test_same_namespace_partials_in_different_assemblies_not_merged(tmp_path):
    """#2411: same fully-qualified name under TWO .csproj projects is two
    genuinely distinct types — never one node with phantom cross-assembly edges."""
    calls, r = _extract(tmp_path, _TWO_ASSEMBLIES)
    widgets, methods = _widget_methods_by_assembly(r)
    assert len(widgets) == 2, \
        f"partials in different assemblies must stay distinct: {widgets}"
    asm_one = next(w["id"] for w in widgets if "asmone" in w["id"].lower())
    asm_two = next(w["id"] for w in widgets if "asmtwo" in w["id"].lower())
    assert methods[asm_one] == {".OnlyInAssemblyOne()", ".AlsoInAssemblyOne()"}, \
        f"AsmOne's Widget owns exactly its own two members: {methods[asm_one]}"
    assert methods[asm_two] == {".OnlyInAssemblyTwo()"}, \
        f"AsmTwo's Widget owns exactly its own member: {methods[asm_two]}"
    phantom = [
        e for e in r["edges"]
        if e["relation"] in ("contains", "method")
        and e["target"] == asm_one and "asmtwo" in str(e["source"]).lower()
    ]
    assert not phantom, f"no AsmTwo-derived edge may reach AsmOne's Widget: {phantom}"


def test_partial_halves_within_one_csproj_still_merge(tmp_path):
    """Adding a .csproj must not break the #2332 merge within one project."""
    calls, r = _extract(tmp_path, {
        "src/AsmOne/AsmOne.csproj": "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n",
        "src/AsmOne/Widget.cs": (
            "namespace Shared {\n"
            "    public partial class Widget {\n"
            "        public void Alpha() {}\n"
            "    }\n"
            "}\n"
        ),
        "src/AsmOne/Widget.Part2.cs": (
            "namespace Shared {\n"
            "    public partial class Widget {\n"
            "        public void Beta() { Alpha(); }\n"
            "    }\n"
            "}\n"
        ),
    })
    widgets, methods = _widget_methods_by_assembly(r)
    assert len(widgets) == 1, \
        f"same-project halves must still collapse to ONE node: {widgets}"
    assert methods[widgets[0]["id"]] == {".Alpha()", ".Beta()"}, \
        f"canonical Widget must own members from BOTH halves: {methods}"
    alpha = _find(r, ".Alpha()", "widget")
    beta = _find(r, ".Beta()", "widget")
    assert (beta, alpha) in calls, "cross-half in-class call must still resolve"


def test_assembly_probe_without_scanned_csproj(tmp_path):
    """The .csproj files exist on disk but are NOT in the scanned paths — the
    assembly key comes from the ancestor-dir walk, not the paths seed."""
    for name, body in _TWO_ASSEMBLIES.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    cs_only = {n: b for n, b in _TWO_ASSEMBLIES.items() if n.endswith(".cs")}
    calls, r = _extract(tmp_path, cs_only)
    widgets = _nodes_labeled(r, "Widget")
    assert len(widgets) == 2, \
        f"on-disk (unscanned) project files must still split assemblies: {widgets}"


# ---------------------------------------------------------------------------
# The merge rewrites every edge in the corpus, not only C# ones. It must drop
# only the self-loops it creates itself (two distinct halves collapsing into
# one node) and leave every edge it does not remap exactly as it was — the
# same rules as the Swift extension merge (#2538) and deduplicate_entities
# (#3809). Before this, one partial class anywhere in a repo erased every
# recursive call, in every language.
# ---------------------------------------------------------------------------

def _self_calls(r):
    """Names (without the `()` suffix some extractors add) of functions with a
    recursive `calls` self-loop."""
    label = {n["id"]: n["label"] for n in r["nodes"]}
    return {label[e["source"]].removesuffix("()") for e in r["edges"]
            if e["relation"] == "calls" and e["source"] == e["target"]}


def test_partial_class_keeps_recursive_calls_in_other_languages(tmp_path):
    calls, r = _extract(tmp_path, {
        **_HALVES,
        "tree.py": "def walk(node):\n    for child in node.children:\n        walk(child)\n",
        "tree.ts": "export function visit(n: any): void {\n  for (const c of n.children) visit(c);\n}\n",
    })
    assert len(_nodes_labeled(r, "Foo")) == 1, "the partial halves still merge"
    assert {"walk", "visit"} <= _self_calls(r), \
        f"recursive calls outside C# must survive the partial merge, got {_self_calls(r)}"


def test_partial_class_keeps_recursive_call_inside_a_half(tmp_path):
    calls, r = _extract(tmp_path, {
        "FooPartA.cs": (
            "namespace App {\n"
            "    public partial class Foo {\n"
            "        public int Depth(int n) { return n <= 0 ? 0 : 1 + Depth(n - 1); }\n"
            "    }\n"
            "}\n"
        ),
        "FooPartB.cs": _HALVES["FooPartB.cs"],
    })
    assert ".Depth" in _self_calls(r), \
        f"a recursive method inside a partial half must keep its self-call, got {_self_calls(r)}"


def _merge(tmp_path, nodes, edges):
    _merge_csharp_partial_class_nodes([], nodes, edges, [], tmp_path)
    return {(e["source"], e["target"], e["relation"], e.get("confidence")) for e in edges}


def _partial_half(nid, source_file):
    return {"id": nid, "label": "Foo", "source_file": source_file, "file_type": "code",
            "metadata": {"is_partial": True, "namespace": "App"}}


def test_merge_drops_only_the_self_loops_it_creates(tmp_path):
    nodes = [
        _partial_half("a_app_foo", "A.cs"),  # sorts first: the canonical half
        _partial_half("b_app_foo", "B.cs"),
        {"id": "tree_walk", "label": "walk()", "source_file": "tree.py", "file_type": "code"},
    ]
    edges = [
        # pre-existing self-loop on a node the merge never touches
        {"source": "tree_walk", "target": "tree_walk", "relation": "calls"},
        # pre-existing self-loop on the merged-away half: rewired, not dropped
        {"source": "b_app_foo", "target": "b_app_foo", "relation": "references"},
        # two distinct halves collapse into one node: a merge artifact
        {"source": "b_app_foo", "target": "a_app_foo", "relation": "references",
         "source_file": "B.cs", "source_location": "L3"},
    ]
    got = _merge(tmp_path, nodes, edges)
    assert ("tree_walk", "tree_walk", "calls", None) in got
    assert ("a_app_foo", "a_app_foo", "references", None) in got
    assert len(got) == 2, f"only the collapsed b->a edge may be dropped, got {got}"


def test_merge_does_not_dedup_edges_it_never_rewrote(tmp_path):
    nodes = [_partial_half("a_app_foo", "A.cs"), _partial_half("b_app_foo", "B.cs")]
    # Two parallel edges at one call site that differ only in confidence —
    # unrelated to the merge, so both must come out unchanged.
    edges = [
        {"source": "x", "target": "y", "relation": "calls", "confidence": "EXTRACTED",
         "source_file": "x.py", "source_location": "L1"},
        {"source": "x", "target": "y", "relation": "calls", "confidence": "INFERRED",
         "source_file": "x.py", "source_location": "L1"},
    ]
    got = _merge(tmp_path, nodes, edges)
    assert got == {("x", "y", "calls", "EXTRACTED"), ("x", "y", "calls", "INFERRED")}
