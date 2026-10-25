"""Swift cross-file type resolution, Phase 2: qualified names and lexical lookup.

See docs/swift-cross-file-type-resolution-rfc.md ("Test plan", Phase 2). The style
follows tests/test_swift_cross_file_calls.py: write the files into ``tmp_path`` and call
``extract(files, cache_root=..., root=..., parallel=False)``.

Several nodes share a label such as ``State`` or ``Inner``, so a label assertion passes
on a wrong binding. Every test therefore names the *target node*: its label, its
``source_file`` and the label of its parent ``contains`` edge. The target is found by
those properties, not by a hard-coded id, so the Phase 2 tests hold both before and
after the nested-type id change of Phase 3. The Phase 3 tests at the end of the file
(and the rewritten duplicate-nested-names test) assert the new ids and need Phase 3.

``_swift_scope`` and ``_swift_lookup`` are run-local edge attributes that ``extract()``
pops at the end, so nothing here asserts them. The outcome of the lookup is read from
the edge target: a repointed edge reaches the declaration, a declined edge stays on a
sourceless stub.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphify.extract import _make_id, extract, extract_swift
from graphify.extractors.engine import _underscore_salted_nid


# ── helpers ───────────────────────────────────────────────────────────────────

def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _extract(files: list[Path], tmp_path: Path) -> dict:
    return extract(files, cache_root=tmp_path / "cache", root=tmp_path / "src", parallel=False)


def _sf(node: dict) -> str:
    return str(node.get("source_file") or "").replace("\\", "/")


def _by_id(result: dict) -> dict[str, dict]:
    return {n["id"]: n for n in result["nodes"]}


def _is_stub(result: dict, nid: str) -> bool:
    """A sourceless node: what an unresolved type reference leaves behind."""
    node = _by_id(result).get(nid)
    return node is not None and not _sf(node)


def _parent_labels(result: dict, nid: str) -> set[str]:
    """Labels of the nodes that hold ``nid`` through a ``contains`` edge."""
    by_id = _by_id(result)
    return {
        by_id[e["source"]].get("label", "")
        for e in result["edges"]
        if e.get("relation") == "contains" and e.get("target") == nid and e["source"] in by_id
    }


def _node(result: dict, label: str, suffix: str, parent: str | None = None) -> str:
    """The id of the one sourced node ``label`` from ``suffix``, optionally under ``parent``."""
    found = [
        n["id"] for n in result["nodes"]
        if n.get("label") == label and _sf(n).endswith(suffix)
        and (parent is None or parent in _parent_labels(result, n["id"]))
    ]
    assert len(found) == 1, (
        f"expected one {label!r} in {suffix} (parent={parent!r}), got {found}"
    )
    return found[0]


def _targets(result: dict, source: str, relations=("references",)) -> set[str]:
    return {
        e["target"] for e in result["edges"]
        if e.get("source") == source and e.get("relation") in relations
    }


def _assert_declaration(result: dict, nid: str, label: str, suffix: str, parent: str) -> None:
    node = _by_id(result)[nid]
    assert node.get("label") == label
    assert _sf(node).endswith(suffix), f"{nid} comes from {_sf(node)!r}, not {suffix}"
    assert parent in _parent_labels(result, nid), (
        f"{nid} is held by {_parent_labels(result, nid)}, not by {parent!r}"
    )


def _method_of(result: dict, owner: str, label: str) -> str:
    """The id of the method ``label`` that ``owner`` holds through a ``method`` edge."""
    by_id = _by_id(result)
    found = [
        e["target"] for e in result["edges"]
        if e.get("relation") == "method" and e.get("source") == owner
        and by_id.get(e["target"], {}).get("label") == label
    ]
    assert len(found) == 1, f"expected one {label!r} method of {owner}, got {found}"
    return found[0]


# ── fixtures ──────────────────────────────────────────────────────────────────

def _layout_files(base: Path) -> list[Path]:
    return [
        _write(base / "App/Models/Layout.swift", (
            "import Foundation\n\n"
            "struct Layout: Equatable {\n"
            "    var panes: [Pane]\n"
            "    struct Pane: Equatable { var id: Int }\n"
            "}\n"
        )),
        _write(base / "App/Reducer/Editor.swift", (
            "import Foundation\n\n"
            "struct Editor {\n"
            "    struct State {\n"
            "        var layout: Layout\n"
            "        var focused: Layout.Pane?\n"
            "    }\n"
            "}\n"
        )),
    ]


def _two_reducers(base: Path) -> list[Path]:
    """Two features that both declare a nested ``State``."""
    return [
        _write(base / "Features/Editor.swift",
               "struct Editor {\n    struct State { var n: Int }\n}\n"),
        _write(base / "Features/OtherFeature.swift",
               "struct OtherFeature {\n    struct State { var m: Int }\n}\n"),
    ]


# ── regressions ───────────────────────────────────────────────────────────────

def test_qualified_nested_reference_resolves_to_nested_type(tmp_path: Path):
    # `var focused: Layout.Pane?` was reduced to its head and bound to Layout.
    files = _layout_files(tmp_path / "src")
    result = _extract(files, tmp_path)

    pane = _node(result, "Pane", "Layout.swift", parent="Layout")
    _assert_declaration(result, pane, "Pane", "Layout.swift", "Layout")
    state = _node(result, "State", "Editor.swift", parent="Editor")
    layout = _node(result, "Layout", "Layout.swift")

    targets = _targets(result, state)
    assert pane in targets, "State.focused must reach the nested Pane declaration"
    assert layout in targets, "State.layout still reaches Layout"
    assert not [t for t in targets if _by_id(result)[t].get("label") == "Layout.Pane"], (
        "the repointed qualified reference must not leave its stub behind"
    )


def test_bare_nested_name_resolves_lexically_in_extension(tmp_path: Path):
    # Inside `extension Editor`, a bare `State` means Editor.State and
    # not the State of another reducer.
    base = tmp_path / "src"
    files = _two_reducers(base) + [
        _write(base / "Features/Editor+Ext.swift",
               "extension Editor {\n    func f(_ s: State) {}\n}\n"),
    ]
    result = _extract(files, tmp_path)

    own = _node(result, "State", "Editor.swift", parent="Editor")
    other = _node(result, "State", "OtherFeature.swift", parent="OtherFeature")
    _assert_declaration(result, own, "State", "Editor.swift", "Editor")
    f = _node(result, ".f()", "Editor+Ext.swift")

    targets = _targets(result, f)
    assert own in targets
    assert other not in targets


def test_bare_name_not_visible_lexically_stays_on_stub(tmp_path: Path):
    # The only `Config` is `Outer.Config`; a bare `Config` outside `Outer` never means it.
    base = tmp_path / "src"
    files = [
        _write(base / "Outer.swift", "enum Outer {\n    struct Config { var a: Int }\n}\n"),
        _write(base / "User.swift", "struct User {\n    var config: Config\n}\n"),
    ]
    result = _extract(files, tmp_path)

    nested = _node(result, "Config", "Outer.swift", parent="Outer")
    user = _node(result, "User", "User.swift")
    targets = _targets(result, user)
    assert nested not in targets, "a bare Config must not bind to Outer.Config"
    stubs = [t for t in targets if _by_id(result)[t].get("label") == "Config"]
    assert stubs and all(_is_stub(result, t) for t in stubs), "the reference stays on its stub"


def test_extension_of_nested_type_merges(tmp_path: Path):
    # `extension Editor.State` merges into the nested declaration.
    base = tmp_path / "src"
    files = _two_reducers(base) + [
        _write(base / "Features/State+Ext.swift",
               "extension Editor.State {\n    func reset() {}\n}\n"),
    ]
    result = _extract(files, tmp_path)

    own = _node(result, "State", "Editor.swift", parent="Editor")
    other = _node(result, "State", "OtherFeature.swift", parent="OtherFeature")
    reset = _node(result, ".reset()", "State+Ext.swift")

    methods = {
        e["source"] for e in result["edges"]
        if e.get("relation") == "method" and e.get("target") == reset
    }
    assert methods == {own}, f"reset() must attach to Editor.State only, got {methods}"
    assert other not in methods
    leftovers = [
        n["id"] for n in result["nodes"]
        if n.get("label") in ("State", "Editor.State") and _sf(n).endswith("State+Ext.swift")
    ]
    assert not leftovers, f"the extension must not survive as its own node: {leftovers}"


def test_qualified_conformance_and_generic_args_resolve(tmp_path: Path):
    # A qualified protocol, a qualified base class and a qualified generic argument
    # reach the nested declarations, with the relation the base kind dictates:
    # a struct conforms (`implements`), the first base of a class is `inherits`.
    base = tmp_path / "src"
    files = _layout_files(base) + [
        _write(base / "Outer.swift", (
            "enum Outer {\n    protocol Proto {}\n    class Base { func hello() {} }\n}\n"
        )),
        _write(base / "Conf.swift", "struct Conf: Outer.Proto {}\n"),
        _write(base / "Child.swift", "class Child: Outer.Base {}\n"),
        _write(base / "Holder.swift",
               "struct Holder {\n    var x: [String: Layout.Pane]\n}\n"),
    ]
    result = _extract(files, tmp_path)

    proto = _node(result, "Proto", "Outer.swift", parent="Outer")
    _assert_declaration(result, proto, "Proto", "Outer.swift", "Outer")
    outer_base = _node(result, "Base", "Outer.swift", parent="Outer")
    _assert_declaration(result, outer_base, "Base", "Outer.swift", "Outer")
    pane = _node(result, "Pane", "Layout.swift", parent="Layout")

    assert proto in _targets(result, _node(result, "Conf", "Conf.swift"), ("implements",))
    assert outer_base in _targets(result, _node(result, "Child", "Child.swift"), ("inherits",))
    assert pane in _targets(result, _node(result, "Holder", "Holder.swift"))


def test_type_table_records_full_path(tmp_path: Path):
    # The per-file extractor result keeps the written dotted path and the scope of the
    # property, so the corpus pass can resolve `focused.xxx()` against the right type.
    path = _write(tmp_path / "src/Editor.swift", (
        "struct Editor {\n"
        "    var plain: Layout\n"
        "    struct State {\n"
        "        var focused: Layout.Pane?\n"
        "    }\n"
        "}\n"
    ))
    result = extract_swift(path)

    table = result["swift_type_table"]["table"]
    scopes = result["swift_type_table"]["scopes"]
    assert table["focused"] == "Layout.Pane"
    assert scopes["focused"] == "Editor.State"
    assert table["plain"] == "Layout"
    assert scopes["plain"] == "Editor"


def test_member_call_through_nested_type_annotation(tmp_path: Path):
    # `x: Outer.Inner` + `x.go()` binds to Inner.go().
    base = tmp_path / "src"
    files = [
        _write(base / "Outer.swift", "enum Outer {\n    class Inner {\n        func go() {}\n    }\n}\n"),
        _write(base / "User.swift", (
            "class User {\n"
            "    var x: Outer.Inner\n"
            "    func run() {\n"
            "        x.go()\n"
            "    }\n"
            "}\n"
        )),
    ]
    result = _extract(files, tmp_path)

    inner = _node(result, "Inner", "Outer.swift", parent="Outer")
    go = _node(result, ".go()", "Outer.swift")
    run = _node(result, ".run()", "User.swift")
    assert any(
        e.get("relation") == "method" and e.get("source") == inner and e.get("target") == go
        for e in result["edges"]
    ), "go() is a method of Outer.Inner"
    assert go in _targets(result, run, ("calls",))


def test_qualified_identity_survives_incremental_update(tmp_path: Path, monkeypatch):
    # Change only a consumer of `Outer.Inner`. The declaration arrives as resolution
    # context, so the identity (`_swift_qualified`) has to ride through the context-node
    # marker tuples. A second `Inner` under `Other` rules out a label-only fallback.
    from graphify.watch import _rebuild_code

    # GRAPHIFY_OUT is read once at import and copied into several modules by name, so
    # patch the copies (as tests/test_hook_guard.py does), not just the environment.
    monkeypatch.delenv("GRAPHIFY_OUT", raising=False)
    for target in (
        "graphify.paths.GRAPHIFY_OUT", "graphify.watch._GRAPHIFY_OUT",
        "graphify.cache._GRAPHIFY_OUT", "graphify.cli._GRAPHIFY_OUT",
        "graphify.security.GRAPHIFY_OUT", "graphify.detect.GRAPHIFY_OUT",
    ):
        monkeypatch.setattr(target, "graphify-out")
    for target in (
        "graphify.paths.GRAPHIFY_OUT_NAME", "graphify.security.GRAPHIFY_OUT_NAME",
        "graphify.detect.GRAPHIFY_OUT_NAME",
    ):
        monkeypatch.setattr(target, "graphify-out")

    corpus = tmp_path / "corpus"
    _write(corpus / "Outer.swift", "enum Outer {\n    struct Inner { var a: Int }\n}\n")
    _write(corpus / "Other.swift", "enum Other {\n    struct Inner { var b: Int }\n}\n")
    consumer = _write(corpus / "Consumer.swift", "struct Consumer {\n    var i: Outer.Inner\n}\n")
    graph_path = corpus / "graphify-out" / "graph.json"

    def graph() -> dict:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        return {"nodes": data["nodes"], "edges": data["links"]}

    def reached(result: dict) -> set[str]:
        return _targets(result, _node(result, "Consumer", "Consumer.swift"))

    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    full = graph()
    inner = _node(full, "Inner", "Outer.swift", parent="Outer")
    other = _node(full, "Inner", "Other.swift", parent="Other")
    assert inner in reached(full)
    assert other not in reached(full)

    consumer.write_text(
        "struct Consumer {\n    var i: Outer.Inner\n    func again() {}\n}\n", encoding="utf-8",
    )
    assert _rebuild_code(corpus, changed_paths=[consumer], no_cluster=True,
                         acquire_lock=False) is True
    incremental = graph()
    assert _node(incremental, "Inner", "Outer.swift", parent="Outer") == inner
    assert inner in reached(incremental), "the changed consumer still reaches Outer.Inner"
    assert other not in reached(incremental)


def test_type_declarations_resolve_with_absolute_paths(tmp_path: Path, monkeypatch):
    # The same fixture, extracted with absolute and with relative paths, and with
    # colliding path slugs (`Cfg/Helpers.swift`, `Cfg_Helpers.swift` both slug to
    # `cfg_helpers`), reaches the same target ids.
    root = tmp_path.resolve()
    src = root / "src"
    _write(src / "Cfg/Helpers.swift", "enum A {\n    struct Inner { var a: Int }\n}\n")
    _write(src / "Cfg_Helpers.swift", "enum B {\n    struct Inner { var b: Int }\n}\n")
    _write(src / "UseA.swift", "struct UseA {\n    var a: A.Inner\n}\n")
    _write(src / "UseB.swift", "struct UseB {\n    var b: B.Inner\n}\n")
    names = ["Cfg/Helpers.swift", "Cfg_Helpers.swift", "UseA.swift", "UseB.swift"]

    def check(result: dict) -> tuple[str, str]:
        inner_a = _node(result, "Inner", "Cfg/Helpers.swift", parent="A")
        inner_b = _node(result, "Inner", "Cfg_Helpers.swift", parent="B")
        assert inner_a != inner_b
        use_a = _targets(result, _node(result, "UseA", "UseA.swift"))
        use_b = _targets(result, _node(result, "UseB", "UseB.swift"))
        assert inner_a in use_a and inner_b not in use_a, f"A.Inner must reach A's Inner: {use_a}"
        assert inner_b in use_b and inner_a not in use_b, f"B.Inner must reach B's Inner: {use_b}"
        return inner_a, inner_b

    absolute = extract([src / n for n in names], cache_root=root / "cache-abs",
                       root=src, parallel=False)
    abs_ids = check(absolute)

    monkeypatch.chdir(src)
    relative = extract([Path(n) for n in names], cache_root=root / "cache-rel",
                       root=src, parallel=False)
    assert check(relative) == abs_ids


def test_member_call_through_nested_parameter_type(tmp_path: Path):
    # Inside `A`, a bare `State` parameter means A.State, so `x.go()` binds to the
    # `go()` that `extension A.State` adds, not to B.State's.
    base = tmp_path / "src"
    a_file = _write(base / "A.swift", (
        "struct A {\n"
        "    struct State { var n: Int }\n"
        "    func f(_ x: State) {\n"
        "        x.go()\n"
        "    }\n"
        "}\n"
    ))
    files = [
        a_file,
        _write(base / "B.swift", (
            "struct B {\n    struct State { var m: Int\n        func go() {} }\n}\n"
        )),
        _write(base / "AState+Ext.swift", "extension A.State {\n    func go() {}\n}\n"),
    ]
    table = extract_swift(a_file)["swift_type_table"]
    assert table["table"]["x"] == "State"
    assert table["scopes"]["x"] == "A"

    result = _extract(files, tmp_path)
    a_state = _node(result, "State", "A.swift", parent="A")
    b_state = _node(result, "State", "B.swift", parent="B")
    a_go = _node(result, ".go()", "AState+Ext.swift")
    b_go = _node(result, ".go()", "B.swift")
    assert any(e.get("relation") == "method" and e.get("source") == a_state
               and e.get("target") == a_go for e in result["edges"]), (
        "go() from the extension is a method of A.State"
    )
    assert b_state != a_state
    called = _targets(result, _node(result, ".f()", "A.swift"), ("calls",))
    assert a_go in called
    assert b_go not in called


def test_nested_base_class_resolves_lexically_in_extension(tmp_path: Path):
    # In `extension Outer`, the base `Base` means Outer.Base, not the top-level Base.
    base = tmp_path / "src"
    files = [
        _write(base / "Outer.swift", "enum Outer {\n    class Base {}\n}\n"),
        _write(base / "Base.swift", "class Base {}\n"),
        _write(base / "Outer+Ext.swift", "extension Outer {\n    class Derived: Base {}\n}\n"),
    ]
    result = _extract(files, tmp_path)

    outer_base = _node(result, "Base", "Outer.swift", parent="Outer")
    _assert_declaration(result, outer_base, "Base", "Outer.swift", "Outer")
    top_base = _node(result, "Base", "Base.swift")
    derived = _node(result, "Derived", "Outer+Ext.swift")
    bases = _targets(result, derived, ("inherits",))
    assert outer_base in bases
    assert top_base not in bases


def test_extension_of_external_type_does_not_merge_into_nested_namesake(tmp_path: Path):
    # The only `Config` is `Outer.Config`. `extension Config` elsewhere extends some
    # outside type: it stays its own node and its methods do not join Outer.Config.
    base = tmp_path / "src"
    files = [
        _write(base / "Outer.swift", "enum Outer {\n    struct Config { var a: Int }\n}\n"),
        _write(base / "Config+Ext.swift", "extension Config {\n    func extra() {}\n}\n"),
    ]
    result = _extract(files, tmp_path)

    nested = _node(result, "Config", "Outer.swift", parent="Outer")
    ext = _node(result, "Config", "Config+Ext.swift")
    extra = _node(result, ".extra()", "Config+Ext.swift")
    assert ext != nested
    owners = {e["source"] for e in result["edges"]
              if e.get("relation") == "method" and e.get("target") == extra}
    assert nested not in owners, "extra() must not become a method of Outer.Config"
    assert ext in owners, "extra() stays a method of the extension node"


# ── controls ──────────────────────────────────────────────────────────────────

def test_ambiguous_bare_name_stays_on_stub(tmp_path: Path):
    # Two top-level `Config` in different files: no edge, the stub is kept.
    base = tmp_path / "src"
    files = [
        _write(base / "One/Config.swift", "struct Config { var a: Int }\n"),
        _write(base / "Two/Config.swift", "struct Config { var b: Int }\n"),
        _write(base / "User.swift", "struct User {\n    var config: Config\n}\n"),
    ]
    result = _extract(files, tmp_path)

    one = _node(result, "Config", "One/Config.swift")
    two = _node(result, "Config", "Two/Config.swift")
    targets = _targets(result, _node(result, "User", "User.swift"))
    assert one not in targets and two not in targets
    stubs = [t for t in targets if _by_id(result)[t].get("label") == "Config"]
    assert stubs and all(_is_stub(result, t) for t in stubs)


def test_member_call_dotted_type_does_not_bind_concatenated_label(tmp_path: Path):
    # `x: Outer.Inner` must not bind to a type labelled `OuterInner` (the key function
    # strips non-alphanumerics, so the dotted name would match it by accident).
    base = tmp_path / "src"
    files = [
        _write(base / "Outer.swift", "enum Outer {\n    class Inner {\n        func go() {}\n    }\n}\n"),
        _write(base / "OuterInner.swift", "class OuterInner {\n    func go() {}\n}\n"),
        _write(base / "User.swift", (
            "class User {\n"
            "    var x: Outer.Inner\n"
            "    func run() {\n"
            "        x.go()\n"
            "    }\n"
            "}\n"
        )),
    ]
    result = _extract(files, tmp_path)

    wrong = _node(result, ".go()", "OuterInner.swift")
    assert wrong not in {
        e["target"] for e in result["edges"] if e.get("relation") == "calls"
    }, "x.go() must not bind to OuterInner.go()"


def test_same_file_duplicate_nested_names_stay_ambiguous(tmp_path: Path):
    # Phase 3 rewrite of the Phase 2 control (the name is kept for traceability to the
    # RFC test plan). `A.State` and `B.State` declared in one file, referenced from
    # other files. Before Phase 3 both folded into one node holding two qualified paths
    # and nothing could bind to it. With distinct nested ids each reference reaches its
    # own State, and never the other one.
    base = tmp_path / "src"
    files = [
        _write(base / "Features.swift", (
            "struct A {\n    struct State { var a: Int }\n}\n"
            "struct B {\n    struct State { var b: Int }\n}\n"
        )),
        _write(base / "ConsumerA.swift", "struct ConsumerA {\n    var s: A.State\n}\n"),
        _write(base / "ConsumerB.swift", "struct ConsumerB {\n    var s: B.State\n}\n"),
    ]
    result = _extract(files, tmp_path)

    a_state = _node(result, "State", "Features.swift", parent="A")
    b_state = _node(result, "State", "Features.swift", parent="B")
    assert a_state != b_state
    _assert_declaration(result, a_state, "State", "Features.swift", "A")
    _assert_declaration(result, b_state, "State", "Features.swift", "B")

    to_a = _targets(result, _node(result, "ConsumerA", "ConsumerA.swift"))
    to_b = _targets(result, _node(result, "ConsumerB", "ConsumerB.swift"))
    assert a_state in to_a and b_state not in to_a
    assert b_state in to_b and a_state not in to_b
    for targets in (to_a, to_b):
        assert not [t for t in targets if _is_stub(result, t)
                    and _by_id(result)[t].get("label") in ("A.State", "B.State")], (
            "the repointed qualified reference must not leave its stub behind"
        )


def test_no_cross_language_binding(tmp_path: Path):
    # A TypeScript `class Store` in the corpus is never the target of a bare Swift
    # reference: the reference stays on its sourceless stub.
    base = tmp_path / "src"
    files = [
        _write(base / "web/Store.ts", "export class Store {\n  save() { return 1; }\n}\n"),
        _write(base / "ios/User.swift", "struct User {\n    var bare: Store\n}\n"),
    ]
    result = _extract(files, tmp_path)

    ts_store = _node(result, "Store", "Store.ts")
    for e in result["edges"]:
        if str(e.get("source_file") or "").endswith(".swift"):
            assert e.get("target") != ts_store, f"Swift edge {e.get('relation')} bound to the TS Store"
    targets = _targets(result, _node(result, "User", "User.swift"))
    assert ts_store not in targets
    stubs = [t for t in targets if _by_id(result)[t].get("label") == "Store"]
    assert stubs and all(_is_stub(result, t) for t in stubs), "the reference stays on its stub"


def test_qualified_swift_reference_ignores_foreign_namesake(tmp_path: Path):
    # With a TS `class Store` and a Swift `Outer.Store`, `Outer.Store` reaches the Swift
    # nested declaration and never the TypeScript class.
    base = tmp_path / "src"
    files = [
        _write(base / "web/Store.ts", "export class Store {\n  save() { return 1; }\n}\n"),
        _write(base / "ios/Outer.swift", "enum Outer {\n    struct Store { var a: Int }\n}\n"),
        _write(base / "ios/User.swift", "struct User {\n    var qualified: Outer.Store\n}\n"),
    ]
    result = _extract(files, tmp_path)

    ts_store = _node(result, "Store", "Store.ts")
    swift_store = _node(result, "Store", "Outer.swift", parent="Outer")
    targets = _targets(result, _node(result, "User", "User.swift"))
    assert swift_store in targets
    assert ts_store not in targets


def test_swift_reference_to_non_swift_type_keeps_generic_rewire(tmp_path: Path):
    # A Swift reference to an Objective-C class is "external" for the Swift pass and
    # keeps today's generic rewire onto the ObjC declaration.
    base = tmp_path / "src"
    files = [
        _write(base / "Legacy/Legacy.h", "@interface LegacyThing : NSObject\n- (void)ping;\n@end\n"),
        _write(base / "Legacy/Legacy.m",
               '#import "Legacy.h"\n@implementation LegacyThing\n- (void)ping {}\n@end\n'),
        _write(base / "App/Holder.swift", "final class Holder {\n    var thing: LegacyThing?\n}\n"),
    ]
    result = _extract(files, tmp_path)

    # The ObjC declaration: a sourced LegacyThing held by its own file node.
    declarations = {
        n["id"] for n in result["nodes"]
        if n.get("label") == "LegacyThing" and _sf(n).endswith((".h", ".m"))
        and _parent_labels(result, n["id"]) & {"Legacy.h", "Legacy.m"}
    }
    assert declarations, "the ObjC class must be declared and held by its file"
    targets = _targets(result, _node(result, "Holder", "Holder.swift"))
    assert targets & declarations, f"the Swift reference must reach the ObjC declaration: {targets}"
    assert not any(_is_stub(result, t) and _by_id(result)[t].get("label") == "LegacyThing"
                   for t in targets), "no stub is left for the resolved reference"


@pytest.mark.parametrize("name", ["Layout.Pane", "Outer.Inner"])
def test_dotted_external_name_keeps_its_full_label_on_stub(tmp_path: Path, name: str):
    # Nothing in the corpus declares the type: the stub keeps the written dotted label
    # (RFC open question 4), so a later declaration can still be told apart.
    base = tmp_path / "src"
    files = [
        _write(base / "User.swift", f"struct User {{\n    var x: {name}\n}}\n"),
    ]
    result = _extract(files, tmp_path)

    targets = _targets(result, _node(result, "User", "User.swift"))
    labels = {_by_id(result)[t].get("label") for t in targets}
    assert name in labels, f"expected a stub labelled {name!r}, got {labels}"
    assert all(_is_stub(result, t) for t in targets if _by_id(result)[t].get("label") == name)


# ── Phase 3: nested type identity ─────────────────────────────────────────────

def test_same_file_nested_types_get_distinct_ids(tmp_path: Path):
    # Two nested types with one name in one file. A nested id is
    # `_make_id(parent_class_nid, name)`, so the two never share a node. Nothing
    # collides here (no member slugs to `state`), so the ids are not salted.
    base = tmp_path / "src"
    files = [
        _write(base / "Features.swift", (
            "struct A {\n    struct State { var a: Int }\n}\n"
            "struct B {\n    struct State { var b: Int }\n}\n"
        )),
    ]
    result = _extract(files, tmp_path)

    a_nid = _node(result, "A", "Features.swift")
    b_nid = _node(result, "B", "Features.swift")
    states = {n["id"] for n in result["nodes"]
              if n.get("label") == "State" and _sf(n).endswith("Features.swift")}
    assert states == {_make_id(a_nid, "State"), _make_id(b_nid, "State")}, (
        "each nested State has its own id, built from its parent's id"
    )
    _assert_declaration(result, _make_id(a_nid, "State"), "State", "Features.swift", "A")
    _assert_declaration(result, _make_id(b_nid, "State"), "State", "Features.swift", "B")
    assert _parent_labels(result, _make_id(a_nid, "State")) == {"A"}
    assert _parent_labels(result, _make_id(b_nid, "State")) == {"B"}


def test_nested_type_and_same_slug_method_both_kept(tmp_path: Path):
    # RFC r1 F10: `struct State` and `func state()` of one parent slug to one id
    # (ids are caseless) and `add_node` would drop the second node. The collision
    # pre-scan salts both ids, so both survive with their edges, and a reference from
    # another file still reaches the nested type.
    base = tmp_path / "src"
    files = [
        _write(base / "Outer.swift", (
            "struct Outer {\n"
            "    struct State { var n: Int }\n"
            "    func state() {}\n"
            "}\n"
        )),
        _write(base / "Consumer.swift", "struct Consumer {\n    var s: Outer.State\n}\n"),
    ]
    result = _extract(files, tmp_path)

    outer = _node(result, "Outer", "Outer.swift")
    plain = _make_id(outer, "State")
    assert plain == _make_id(outer, "state"), "the type and the method slug to one id"
    groups = {plain: {"State", "state"}}
    state_nid = _underscore_salted_nid(plain, "State", groups)
    method_nid = _underscore_salted_nid(plain, "state", groups)
    assert state_nid != method_nid

    state = _node(result, "State", "Outer.swift", parent="Outer")
    method = _method_of(result, outer, ".state()")
    assert state == state_nid
    assert method == method_nid
    _assert_declaration(result, state, "State", "Outer.swift", "Outer")
    assert _sf(_by_id(result)[method]).endswith("Outer.swift")
    assert state in _targets(result, _node(result, "Consumer", "Consumer.swift")), (
        "the reference from another file reaches the nested type, not the method"
    )
    assert method not in _targets(result, _node(result, "Consumer", "Consumer.swift"))


def test_bare_in_body_reference_binds_own_nested_type(tmp_path: Path):
    # Two features in one file, each with its own nested `State`. A bare `State` in a
    # method signature misses the same-file shortcut once the ids are distinct and
    # resolves through the lexical lookup to the State of its own enclosing type.
    base = tmp_path / "src"
    files = [
        _write(base / "Features.swift", (
            "struct A {\n"
            "    struct State { var a: Int }\n"
            "    func f(_ s: State) {}\n"
            "}\n"
            "struct B {\n"
            "    struct State { var b: Int }\n"
            "    func f(_ s: State) {}\n"
            "}\n"
        )),
    ]
    result = _extract(files, tmp_path)

    a_nid = _node(result, "A", "Features.swift")
    b_nid = _node(result, "B", "Features.swift")
    a_state = _node(result, "State", "Features.swift", parent="A")
    b_state = _node(result, "State", "Features.swift", parent="B")
    assert a_state == _make_id(a_nid, "State")
    assert b_state == _make_id(b_nid, "State")
    _assert_declaration(result, a_state, "State", "Features.swift", "A")
    _assert_declaration(result, b_state, "State", "Features.swift", "B")

    a_f = _method_of(result, a_nid, ".f()")
    b_f = _method_of(result, b_nid, ".f()")
    a_targets = _targets(result, a_f)
    b_targets = _targets(result, b_f)
    assert a_state in a_targets and b_state not in a_targets
    assert b_state in b_targets and a_state not in b_targets
    for targets in (a_targets, b_targets):
        assert not [t for t in targets if _is_stub(result, t)
                    and _by_id(result)[t].get("label") == "State"], (
            "a bare in-body reference must not stay on a sourceless stub"
        )


def test_local_var_same_name_in_two_types_scope_is_none(tmp_path: Path):
    # Fail-closed rule: the flat per-file table keeps one record per name. When two writes
    # of `x` agree on the type but disagree on the scope (the enclosing type of each
    # function), the extractor stores `scopes["x"] = None` and keeps the table value, so
    # the corpus pass binds nothing instead of a wrong `State`.
    path = _write(tmp_path / "src/Features.swift", (
        "struct A {\n"
        "    struct State {}\n"
        "    func f() { let x = State() }\n"
        "}\n"
        "struct B {\n"
        "    struct State {}\n"
        "    func g() { let x = State() }\n"
        "}\n"
    ))
    result = extract_swift(path)

    assert result["swift_type_table"]["scopes"]["x"] is None
    assert result["swift_type_table"]["table"]["x"] == "State"


def test_property_same_name_in_two_types_scope_is_none(tmp_path: Path):
    # Fail-closed rule, property flavour: `var x: State` in two sibling types.
    path = _write(tmp_path / "src/Features.swift", (
        "struct A {\n"
        "    struct State {}\n"
        "    var x: State\n"
        "}\n"
        "struct B {\n"
        "    struct State {}\n"
        "    var x: State\n"
        "}\n"
    ))
    result = extract_swift(path)

    assert result["swift_type_table"]["scopes"]["x"] is None
    assert result["swift_type_table"]["table"]["x"] == "State"


def test_shadowed_local_with_different_type_scope_is_none(tmp_path: Path):
    # Fail-closed rule, same body: an outer `let x` and a shadowing `let x` in a nested
    # block disagree on the type. The flat table keeps one record for `x`, so its
    # scope must be None (the corpus pass then binds nothing), and the table value
    # stays the one the walk keeps today.
    path = _write(tmp_path / "src/Features.swift", (
        "struct State {}\n"
        "struct Other {}\n"
        "struct A {\n"
        "    func f() {\n"
        "        let x = State()\n"
        "        if true {\n"
        "            let x = Other()\n"
        "        }\n"
        "    }\n"
        "}\n"
    ))
    result = extract_swift(path)

    assert result["swift_type_table"]["scopes"]["x"] is None
    # The walk pops the later sibling first, so the nested `Other()` binding is kept.
    assert result["swift_type_table"]["table"]["x"] == "Other"


# ── Phase 3 review fixes ─────────────────────────────────────────────────────

def _labelled(result: dict, label: str, suffix: str) -> list[str]:
    return [n["id"] for n in result["nodes"]
            if n.get("label") == label and _sf(n).endswith(suffix)]


def test_nested_type_beside_private_computed_property_and_case_both_kept(tmp_path: Path):
    # r1 F1: an enum case and a computed property keep their plain id, so a nested
    # type of the same slug is salted even when it is the only public name.
    base = tmp_path / "src"
    files = [
        _write(base / "Outer.swift", (
            "struct Outer {\n"
            "    struct State { var n: Int }\n"
            "    var _state: Int { 0 }\n"
            "}\n"
        )),
        _write(base / "Status.swift", (
            "enum Status {\n"
            "    struct Delegate { var n: Int }\n"
            "    case _delegate\n"
            "}\n"
        )),
    ]
    result = _extract(files, tmp_path)

    outer = _node(result, "Outer", "Outer.swift")
    state = _node(result, "State", "Outer.swift", parent="Outer")
    prop = _method_of(result, outer, "._state")
    assert state != prop
    status = _node(result, "Status", "Status.swift")
    delegate = _node(result, "Delegate", "Status.swift", parent="Status")
    cases = [e["target"] for e in result["edges"]
             if e.get("relation") == "case_of" and e.get("source") == status]
    assert _labelled(result, "_delegate", "Status.swift") == cases
    assert delegate not in cases


def test_nested_type_and_same_slug_method_in_same_file_extension_both_kept(tmp_path: Path):
    # r1 F2: the collision scan covers every same-file body of the parent, so a
    # method declared in `extension Outer` does not swallow the nested `State`.
    base = tmp_path / "src"
    files = [
        _write(base / "Outer.swift", (
            "struct Outer {\n"
            "    struct State { var n: Int }\n"
            "}\n"
            "extension Outer {\n"
            "    func state() {}\n"
            "}\n"
        )),
    ]
    result = _extract(files, tmp_path)

    outer = _node(result, "Outer", "Outer.swift")
    state = _node(result, "State", "Outer.swift", parent="Outer")
    method = _method_of(result, outer, ".state()")
    assert state != method
    assert _sf(_by_id(result)[method]).endswith("Outer.swift")


def test_nested_type_and_method_of_the_same_name_both_kept(tmp_path: Path):
    # r1 F3: `struct State` and `func State()` share the exact name, so a salt by
    # name alone cannot tell them apart; the type salts a kind-tagged name.
    base = tmp_path / "src"
    files = [
        _write(base / "Outer.swift", (
            "struct Outer {\n"
            "    struct State { var n: Int }\n"
            "    func State() {}\n"
            "}\n"
        )),
    ]
    result = _extract(files, tmp_path)

    outer = _node(result, "Outer", "Outer.swift")
    state = _node(result, "State", "Outer.swift", parent="Outer")
    method = _method_of(result, outer, ".State()")
    assert state != method


def test_same_file_extension_of_salted_nested_type_keeps_its_owner(tmp_path: Path):
    # r1 F5: `State` keeps the plain id and `_State` is salted. A same-file
    # `extension Outer._State` takes `_State`'s real id, so `extra()` belongs to
    # `_State` and `State` gains no second qualified path.
    base = tmp_path / "src"
    files = [
        _write(base / "Outer.swift", (
            "struct Outer {\n"
            "    struct State { var n: Int }\n"
            "    struct _State { var m: Int }\n"
            "}\n"
            "extension Outer._State {\n"
            "    func extra() {}\n"
            "}\n"
        )),
    ]
    result = _extract(files, tmp_path)

    state = _node(result, "State", "Outer.swift", parent="Outer")
    private_state = _node(result, "_State", "Outer.swift", parent="Outer")
    assert state != private_state
    _method_of(result, private_state, ".extra()")
    assert not [e for e in result["edges"]
                if e.get("relation") == "method" and e.get("source") == state]
    assert _by_id(result)[state].get("_swift_qualified", ["Outer.State"]) == ["Outer.State"]


def test_dotted_reference_reaches_nested_type_not_same_slug_enum_case(tmp_path: Path):
    # `Action.Delegate` slugs to the id of `case delegate` (ids are caseless), and the
    # case keeps the plain id while the nested type is salted. The reference must
    # reach the type, not the case.
    base = tmp_path / "src"
    path = base / "Action.swift"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "enum Action {\n    case delegate\n    enum Delegate {}\n}\n"
        "struct Use {\n    var value: Action.Delegate\n}\n",
        encoding="utf-8",
    )
    result = extract([path], cache_root=tmp_path / "cache", root=base, parallel=False)

    by_id = {n["id"]: n for n in result["nodes"]}
    use_ids = {nid for nid, n in by_id.items() if n.get("label") == "Use"}
    targets = {
        by_id[e["target"]].get("label") for e in result["edges"]
        if e.get("relation") == "references" and e["source"] in use_ids
    }
    assert targets == {"Delegate"}, targets


@pytest.mark.parametrize("top_level_first", [False, True])
def test_dotted_reference_uses_lexical_scope_over_same_named_top_level(
    tmp_path: Path, top_level_first: bool,
):
    # Inside `Outer`, `Model.Item` means `Outer.Model.Item`, which hides the
    # top-level `Model.Item`, whichever of the two is declared first in the file.
    outer = (
        "struct Outer {\n    struct Model {\n        struct Item {}\n    }\n"
        "    var item: Model.Item\n}\n"
    )
    top = "struct Model {\n    struct Item {}\n}\n"
    base = tmp_path / "src"
    path = base / "Types.swift"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(top + outer if top_level_first else outer + top, encoding="utf-8")
    result = extract([path], cache_root=tmp_path / "cache", root=base, parallel=False)

    by_id = {n["id"]: n for n in result["nodes"]}
    outer_ids = {nid for nid, n in by_id.items() if n.get("label") == "Outer"}
    targets = [
        by_id[e["target"]] for e in result["edges"]
        if e.get("relation") == "references" and e["source"] in outer_ids
        and by_id.get(e["target"], {}).get("label") in ("Item", "Model.Item")
    ]
    assert len(targets) == 1, targets
    assert targets[0].get("_swift_qualified") == ["Outer.Model.Item"], targets[0]
