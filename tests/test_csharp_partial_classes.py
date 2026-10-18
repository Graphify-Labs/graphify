"""C# partial classes split across files (#2332).

`partial class Foo` declared in two files minted TWO class nodes (the node id
carries the per-file stem), so the type's members split across the halves and
every receiver-typed lookup on `Foo` bailed as ambiguous — cross-half calls
never resolved. `_merge_csharp_partial_class_nodes` collapses the halves onto
one canonical node, keyed by (assembly, namespace, type path); same-named types
in other namespaces, non-partial declarations, and nested types under a
different enclosing chain are left alone (#4363). The assembly key is the nearest ancestor dir holding a `*.csproj`/
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


def _methods_of(r, nid):
    label_of = {n["id"]: n["label"] for n in r["nodes"]}
    return {label_of[e["target"]] for e in r["edges"]
            if e["relation"] == "method" and e["source"] == nid}


_NESTED_HALVES = {
    "A.cs": (
        "namespace App {\n"
        "    public partial class Outer {\n"
        "        public partial class Inner { public void FromA() { FromB(); } }\n"
        "    }\n"
        "}\n"
    ),
    "B.cs": (
        "namespace App {\n"
        "    public partial class Outer {\n"
        "        public partial class Inner { public virtual void FromB() {} }\n"
        "    }\n"
        "}\n"
    ),
    # Same member names on an unrelated type, so a name-only fallback cannot
    # stand in for the merge.
    "Decoy.cs": (
        "namespace App {\n"
        "    public class Decoy { public void FromA() {} public virtual void FromB() {} }\n"
        "}\n"
    ),
}


def test_nested_partial_halves_merge_under_the_same_outer(tmp_path):
    """A nested partial type split across files is one type, like a top-level
    one: its halves collapse onto one node that owns both halves' members."""
    calls, r = _extract(tmp_path, _NESTED_HALVES)
    outers = _nodes_labeled(r, "Outer")
    inners = _nodes_labeled(r, "Inner")
    assert len(outers) == 1, "top-level partial halves still merge"
    assert len(inners) == 1, f"nested partial halves must merge: {inners}"
    assert _methods_of(r, inners[0]["id"]) == {".FromA()", ".FromB()"}
    # Still contained by the outer type, not by a file.
    assert any(e["relation"] == "contains" and e["source"] == outers[0]["id"]
               and e["target"] == inners[0]["id"] for e in r["edges"])


def test_nested_partial_cross_half_unqualified_call_resolves(tmp_path):
    calls, r = _extract(tmp_path, _NESTED_HALVES)
    assert (_find(r, ".FromA()", "inner"), _find(r, ".FromB()", "inner")) in calls


def test_cross_half_unqualified_call_beats_a_same_named_method_elsewhere(tmp_path):
    """The in-file own-class binding (#4252) cannot see the other half of a
    partial type; a same-named method on another type must not make the
    cross-half call ambiguous."""
    calls, r = _extract(tmp_path, {
        **_HALVES,
        "Decoy.cs": "namespace App { public class Decoy { public void Alpha() {} } }\n",
    })
    alpha = _find(r, ".Alpha()", "foo")
    beta = _find(r, ".Beta()", "foo")
    assert (beta, alpha) in calls
    assert (beta, _find(r, ".Alpha()", "decoy")) not in calls


def test_nested_partial_base_call_resolves_into_the_other_half(tmp_path):
    """`base.M()` on a nested partial base whose M is declared in the half
    that is not the merge's canonical node."""
    calls, r = _extract(tmp_path, {
        **_NESTED_HALVES,
        "Derived.cs": (
            "using static App.Outer;\n"
            "namespace App {\n"
            "    public class Derived : Inner {\n"
            "        public override void FromB() { base.FromB(); }\n"
            "    }\n"
            "}\n"
        ),
    })
    derived_from_b = _find(r, ".FromB()", "derived")
    inner_from_b = _find(r, ".FromB()", "inner")
    assert (derived_from_b, inner_from_b) in calls


def test_receiver_typed_calls_resolve_into_both_nested_halves(tmp_path):
    calls, r = _extract(tmp_path, {
        **_NESTED_HALVES,
        "Caller.cs": (
            "namespace App {\n"
            "    public class Caller {\n"
            "        public void Run(Outer.Inner i) { i.FromA(); i.FromB(); }\n"
            "    }\n"
            "}\n"
        ),
    })
    run = _find(r, ".Run()", "caller")
    assert (run, _find(r, ".FromA()", "inner")) in calls
    assert (run, _find(r, ".FromB()", "inner")) in calls


def test_same_named_nested_partials_under_different_outers_not_merged(tmp_path):
    """Nested ids omit the enclosing type; the merge must still keep
    `OuterA.Inner` and `OuterB.Inner` apart, each owning only its own halves."""
    def _half(outer, method):
        return (
            "namespace App {\n"
            f"    public partial class {outer} {{\n"
            f"        public partial class Inner {{ public void {method}() {{}} }}\n"
            "    }\n"
            "}\n"
        )
    calls, r = _extract(tmp_path, {
        "A1.cs": _half("OuterA", "A1"), "A2.cs": _half("OuterA", "A2"),
        "B1.cs": _half("OuterB", "B1"), "B2.cs": _half("OuterB", "B2"),
    })
    inners = _nodes_labeled(r, "Inner")
    assert len(inners) == 2, f"one Inner per outer: {inners}"
    owned = sorted(sorted(_methods_of(r, n["id"])) for n in inners)
    assert owned == [[".A1()", ".A2()"], [".B1()", ".B2()"]]


def test_deeply_nested_partials_key_on_the_whole_enclosing_chain(tmp_path):
    def _half(mid, method):
        return (
            "namespace App {\n"
            "    public partial class Outer {\n"
            f"        public partial class {mid} {{\n"
            f"            public partial class Inner {{ public void {method}() {{}} }}\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
    calls, r = _extract(tmp_path, {
        "M1a.cs": _half("Mid1", "One"), "M1b.cs": _half("Mid1", "Two"),
        "M2.cs": _half("Mid2", "Three"),
    })
    inners = _nodes_labeled(r, "Inner")
    owned = sorted(sorted(_methods_of(r, n["id"])) for n in inners)
    assert owned == [[".One()", ".Two()"], [".Three()"]]


def test_generic_and_non_generic_partials_not_merged(tmp_path):
    """`Foo` and `Foo<T>` are distinct types with distinct ids (#4249); the
    merge must not fold them back together, top-level or as an outer."""
    calls, r = _extract(tmp_path, {
        "A.cs": "namespace App { public partial class Foo { public void A() {} } }\n",
        "B.cs": "namespace App { public partial class Foo<T> { public void B() {} } }\n",
        "C.cs": "namespace App { public partial class Foo { public void C() {} } }\n",
        "D.cs": (
            "namespace App { public partial class Box {"
            " public partial class Item { public void D() {} } } }\n"
        ),
        "E.cs": (
            "namespace App { public partial class Box<T> {"
            " public partial class Item { public void E() {} } } }\n"
        ),
    })
    foos = sorted(sorted(_methods_of(r, n["id"])) for n in _nodes_labeled(r, "Foo"))
    assert foos == [[".A()", ".C()"], [".B()"]]
    items = sorted(sorted(_methods_of(r, n["id"])) for n in _nodes_labeled(r, "Item"))
    assert items == [[".D()"], [".E()"]]


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


def test_base_named_by_two_halves_resolves_once(tmp_path):
    """Both halves name the base, a sibling nested type of the same holder.
    Only the half that imports the holder (`using static`) resolves it; the
    other leaves a placeholder. After the merge the type must not carry that
    placeholder next to the real base — it made the base-chain lookup for
    `base.Init()` look ambiguous and dropped the edge."""
    calls, r = _extract(tmp_path, {
        "Base.cs": (
            "namespace App {\n"
            "    public static partial class Agents {\n"
            "        public class Base { public virtual void Init() {} }\n"
            "    }\n"
            "}\n"
        ),
        "DA.cs": (
            "using static App.Agents;\n"
            "namespace App {\n"
            "    public static partial class Agents {\n"
            "        public partial class Derived : Base { public override void Init() { base.Init(); } }\n"
            "    }\n"
            "}\n"
        ),
        "DB.cs": (
            "namespace App {\n"
            "    public static partial class Agents {\n"
            "        public partial class Derived : Base { public void Other() {} }\n"
            "    }\n"
            "}\n"
        ),
        "Decoy.cs": "namespace App { public class Decoy { public virtual void Init() {} } }\n",
    })
    derived = _nodes_labeled(r, "Derived")
    assert len(derived) == 1
    by_id = {n["id"]: n for n in r["nodes"]}
    bases = [by_id[e["target"]] for e in r["edges"]
             if e["relation"] in ("inherits", "implements") and e["source"] == derived[0]["id"]]
    assert [b["label"] for b in bases] == ["Base"], bases
    assert bases[0].get("source_file"), "the one base must be the real Agents.Base"
    assert (_find(r, ".Init()", "derived"), _find(r, ".Init()", "base")) in calls


def test_schema_bump_retires_csharp_entries_cached_without_type_path(tmp_path, monkeypatch):
    """An entry from schema 8 has no `type_path`; replayed, its nested halves
    stay split and `Box` / `Box<T>` fold back into one node."""
    import graphify.cache as cache_mod
    from graphify.cache import save_cached
    from graphify.extract import extract_csharp

    files = {
        **{k: v for k, v in _NESTED_HALVES.items() if k != "Decoy.cs"},
        "Box.cs": "namespace App { public partial class Box { public void Plain() {} } }\n",
        "BoxOfT.cs": "namespace App { public partial class Box<T> { public void Typed() {} } }\n",
    }
    paths = []
    for name, body in files.items():
        p = tmp_path / name
        p.write_text(body)
        paths.append(p)
    current_schema = cache_mod._AST_CACHE_SCHEMA
    monkeypatch.setattr(cache_mod, "_EXTRACTOR_VERSION", "same-version")
    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", 8)  # last schema without type_path
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set())
    for p in paths:
        stale = extract_csharp(p)
        for node in stale["nodes"]:
            (node.get("metadata") or {}).pop("type_path", None)
        save_cached(p, stale, root=tmp_path, cache_root=tmp_path, kind="ast")

    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", current_schema)
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set())
    r = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert len(_nodes_labeled(r, "Inner")) == 1
    boxes = sorted(sorted(_methods_of(r, n["id"])) for n in _nodes_labeled(r, "Box"))
    assert boxes == [[".Plain()"], [".Typed()"]]


def test_nested_types_sharing_an_id_in_one_file_are_not_merged(tmp_path):
    """`OuterA.Inner` and `OuterB.Inner` declared in one file already share
    one node id. No single type path is right for that node, so it must not
    join the halves of either `OuterA.Inner` or `OuterB.Inner` elsewhere."""
    calls, r = _extract(tmp_path, {
        "One.cs": (
            "namespace App {\n"
            "    public partial class OuterA { public partial class Inner { public void A1() {} } }\n"
            "    public partial class OuterB { public partial class Inner { public void B1() {} } }\n"
            "}\n"
        ),
        "A2.cs": (
            "namespace App { public partial class OuterA {"
            " public partial class Inner { public void A2() {} } } }\n"
        ),
        "B2.cs": (
            "namespace App { public partial class OuterB {"
            " public partial class Inner { public void B2() {} } } }\n"
        ),
    })
    owned = [_methods_of(r, n["id"]) for n in _nodes_labeled(r, "Inner")]
    assert not any({".A2()", ".B1()"} <= m or {".B2()", ".A1()"} <= m for m in owned), owned


def test_qualified_or_aliased_base_is_not_dropped_as_shadowed(tmp_path):
    """A half that names a same-named but different base (`Other.IFoo`, or an
    alias) keeps its placeholder edge; only a bare-name placeholder next to
    the real base of that name is the unresolved spelling of it."""
    def _bases(case, files):
        _, r = _extract(tmp_path / case, files)
        by_id = {n["id"]: n for n in r["nodes"]}
        return sorted((by_id[e["target"]]["label"], bool(by_id[e["target"]].get("source_file")))
                      for e in r["edges"] if e["relation"] in ("inherits", "implements"))

    common = {
        "I.cs": "namespace App { public interface IFoo { void F(); } }\n",
        "DA.cs": "namespace App { public partial class D : IFoo { public void F() {} } }\n",
    }
    qualified = _bases("qualified", {**common, "DB.cs": "namespace App { public partial class D : Other.IFoo { } }\n"})
    aliased = _bases("aliased", {**common, "DB.cs": (
        "using IFoo = Other.IFoo;\n"
        "namespace App { public partial class D : IFoo { } }\n"
    )})
    assert qualified == [("IFoo", False), ("IFoo", True)], qualified
    assert aliased == [("IFoo", False), ("IFoo", True)], aliased


def test_receiver_qualified_calls_are_not_rebound_to_the_own_type(tmp_path):
    """The own-type binding is for unqualified calls only: `base.M()`,
    `this.M()` and `Type.M()` keep their existing targets."""
    calls, r = _extract(tmp_path, {
        "Machine.cs": "namespace App { public class Machine { public virtual void Reset() {} } }\n",
        "E1.cs": (
            "namespace App { public partial class Engine : Machine {"
            " public override void Reset() {} public static void Stop() {} } }\n"
        ),
        "E2.cs": (
            "namespace App { public partial class Engine : Machine {"
            " public void Go() { base.Reset(); Valve.Stop(); } } }\n"
        ),
        "Valve.cs": "namespace App { public static class Valve { public static void Stop() {} } }\n",
    })
    go = _find(r, ".Go()", "engine")
    assert (go, _find(r, ".Reset()", "machine")) in calls
    assert (go, _find(r, ".Stop()", "valve")) in calls
    assert (go, _find(r, ".Reset()", "engine")) not in calls
    assert (go, _find(r, ".Stop()", "engine")) not in calls


def _methods_owned_by(r, nid):
    targets = {e["target"] for e in r["edges"] if e["relation"] == "method" and e["source"] == nid}
    return {n["label"] for n in r["nodes"] if n["id"] in targets}


def test_partial_half_with_a_path_colliding_id_keeps_its_members(tmp_path):
    """`Cfg/Helpers.cs` and `Cfg_Helpers.cs` mint the same file stem, so the
    halves declared there share one id and get salted apart by path. The merge
    used to run first: it rewired the third half's `method` edges onto that
    shared id, the salting then keyed them by the third half's own file, missed,
    and left them dangling, so `Gamma()` had no owner and the two colliding
    halves stayed two `Cfg` nodes."""
    _, r = _extract(tmp_path, {
        "Lib.csproj": "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n",
        "Cfg/Helpers.cs": "namespace App { public partial class Cfg { public void Alpha() {} } }\n",
        "Cfg_Helpers.cs": "namespace App { public partial class Cfg { public void Beta() {} } }\n",
        "generated/Cfg.cs": (
            "namespace App { public partial class Cfg {"
            " public void Gamma() { Alpha(); Beta(); } } }\n"
        ),
    })
    cfgs = _nodes_labeled(r, "Cfg")
    assert len(cfgs) == 1, cfgs
    assert _methods_owned_by(r, cfgs[0]["id"]) == {".Alpha()", ".Beta()", ".Gamma()"}


def test_partial_half_colliding_with_an_underscore_sibling_keeps_its_members(tmp_path):
    """`Spec.cs` and `_Spec.cs` collide the same way (the leading underscore is
    dropped from the stem). The merged `Spec` must own the generated half's
    methods, and the unrelated `_Spec` must stay a separate type deriving from it."""
    _, r = _extract(tmp_path, {
        "Spec.cs": "namespace App { public partial class Spec { public int Size; } }\n",
        "_Spec.cs": "namespace App { public class _Spec : Spec { public void Extra() { Move(); } } }\n",
        "generated/Spec.cs": (
            "namespace App { public partial class Spec {"
            " public void Move() {} public void Copy() {} } }\n"
        ),
    })
    specs = _nodes_labeled(r, "Spec")
    assert len(specs) == 1, specs
    spec = specs[0]["id"]
    assert _methods_owned_by(r, spec) == {".Move()", ".Copy()"}
    sub = _nodes_labeled(r, "_Spec")
    assert len(sub) == 1 and sub[0]["id"] != spec, sub
    assert (sub[0]["id"], spec) in {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "inherits"}


def test_outer_partial_halves_in_path_colliding_files_merge(tmp_path):
    """The colliding files both declare `partial class Tools`: identical ids
    from two files. Salted apart first, the halves now merge by type path
    instead of staying two `Tools` nodes (and losing the third half)."""
    _, r = _extract(tmp_path, {
        "Spec.cs": "namespace App { public static partial class Tools { public static void A() {} } }\n",
        "_Spec.cs": "namespace App { public static partial class Tools { public static void B() {} } }\n",
        "generated/Spec.cs": "namespace App { public static partial class Tools { public static void C() {} } }\n",
    })
    tools = _nodes_labeled(r, "Tools")
    assert len(tools) == 1, tools
    assert _methods_owned_by(r, tools[0]["id"]) == {".A()", ".B()", ".C()"}


def test_merge_does_not_delete_an_unrelated_node_sharing_a_half_id(tmp_path):
    """A half's id can collide with an unrelated node in another file: here the
    method `Helpers.App.Cfg()` in `Cfg.cs` mints the same id as the half of
    `App.Cfg` in `Cfg/Helpers.cs`. The merge removes merged-away halves by id,
    so before ids were salted apart it also deleted that method, and the
    method's `calls` edge was rewired onto the type."""
    calls, r = _extract(tmp_path, {
        "A/Cfg.cs": "namespace App { public partial class Cfg { public void Alpha() {} } }\n",
        "Cfg/Helpers.cs": "namespace App { public partial class Cfg { public void Beta() {} } }\n",
        "Cfg.cs": (
            "namespace Helpers { public class App {"
            " public void Cfg() { Other(); } public void Other() {} } }\n"
        ),
    })
    method = _nodes_labeled(r, ".Cfg()")
    assert len(method) == 1 and method[0]["source_file"] == "Cfg.cs", method
    assert (method[0]["id"], _find(r, ".Other()", "")) in calls
    cfgs = _nodes_labeled(r, "Cfg")
    assert len(cfgs) == 1 and _methods_owned_by(r, cfgs[0]["id"]) == {".Alpha()", ".Beta()"}, cfgs
