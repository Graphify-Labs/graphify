from __future__ import annotations

from pathlib import Path

from graphify.build import build_from_json
from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _label(result: dict, nid: str) -> str:
    for n in result["nodes"]:
        if n["id"] == nid:
            return n.get("label", "")
    return f"<{nid}>"


def _edge_labels(result: dict, relations=("calls", "references")) -> set[tuple[str, str, str]]:
    """Return {(source_label, relation, target_label)} for the given relations."""
    out: set[tuple[str, str, str]] = set()
    for e in result["edges"]:
        if e.get("relation") in relations:
            out.add((_label(result, e["source"]), e["relation"], _label(result, e["target"])))
    return out


def _issue_fixture(base: Path) -> list[Path]:
    """The three cross-file patterns from #1356, plus a constructor-in-initializer."""
    f1 = _write(base / "Models/SessionViewModel.swift",
                "class SessionViewModel {\n    func update() {}\n}\n")
    f2 = _write(base / "Services/NetworkService.swift",
                "class NetworkService {\n    func fetch() {}\n}\n")
    f3 = _write(base / "Core/SessionType.swift",
                "enum SessionType {\n    static func staticMethod() {}\n}\n")
    f4 = _write(base / "Core/Singleton.swift",
                "class Singleton {\n    static let shared = Singleton()\n    func method() {}\n}\n")
    f5 = _write(base / "Views/HomeView.swift", (
        "class HomeView {\n"
        "    let vm = SessionViewModel()\n"
        "    var svc: NetworkService\n\n"
        "    func go() {\n"
        "        vm.update()\n"
        "        SessionType.staticMethod()\n"
        "        Singleton.shared.method()\n"
        "        self.svc.fetch()\n"
        "    }\n"
        "}\n"
    ))
    return [f1, f2, f3, f4, f5]


def test_swift_cross_file_member_calls_resolve(tmp_path: Path):
    # #1356: cross-file member calls (recv.method()), static/singleton calls, and
    # a constructor-in-initializer must resolve to the receiver's real definition.
    files = _issue_fixture(tmp_path / "src")
    result = extract(files, cache_root=tmp_path / "cache")

    edges = _edge_labels(result)
    # Stage 1: constructor in a property initializer.
    assert ("HomeView", "calls", "SessionViewModel") in edges
    # Stage 2: receiver typed via the file's local type table.
    assert (".go()", "calls", ".update()") in edges        # vm.update()
    assert (".go()", "calls", ".fetch()") in edges         # self.svc.fetch()
    # Stage 2: upper-cased receiver is itself a type.
    assert (".go()", "calls", ".staticMethod()") in edges  # SessionType.staticMethod()
    assert (".go()", "calls", ".method()") in edges        # Singleton.shared.method()


def test_swift_cross_file_member_calls_have_correct_confidence_and_resolve(tmp_path: Path):
    # Instance calls typed via local inference (vm.update(), self.svc.fetch()) are
    # INFERRED; type-qualified static calls (SessionType.staticMethod(),
    # Singleton.shared.method()) name the receiver type explicitly in source, so
    # they are EXTRACTED, matching the Python qualified-class-method pass (#1533).
    # All must land on real definition nodes so build_from_json keeps them.
    files = _issue_fixture(tmp_path / "src")
    result = extract(files, cache_root=tmp_path / "cache")

    node_ids = {n["id"] for n in result["nodes"]}
    src_by_id = {n["id"]: n.get("source_file") for n in result["nodes"]}

    inferred_targets = {".update()", ".fetch()"}
    extracted_targets = {".staticMethod()", ".method()"}
    seen_inferred: set[str] = set()
    seen_extracted: set[str] = set()
    for e in result["edges"]:
        tgt_label = _label(result, e["target"])
        if e.get("relation") != "calls":
            continue
        if tgt_label in inferred_targets:
            assert e["confidence"] == "INFERRED" and e["confidence_score"] == 0.85
            assert e["target"] in node_ids and src_by_id.get(e["target"])
            seen_inferred.add(tgt_label)
        elif tgt_label in extracted_targets:
            assert e["confidence"] == "EXTRACTED" and e["confidence_score"] == 1.0
            assert e["target"] in node_ids and src_by_id.get(e["target"])
            seen_extracted.add(tgt_label)
    assert seen_inferred == inferred_targets
    assert seen_extracted == extracted_targets

    # Edges survive graph construction (no dangling targets pruned).
    g = build_from_json(result)
    surviving = sum(
        1 for _, _, d in g.edges(data=True)
        if d.get("relation") == "calls" and d.get("confidence") in ("INFERRED", "EXTRACTED")
    )
    assert surviving >= 5


def test_swift_ambiguous_type_does_not_over_connect(tmp_path: Path):
    # #543/#1219 guard: when the receiver's type name is defined in 2+ files the
    # resolution must bail rather than fan a member call out to every candidate.
    base = tmp_path / "src"
    for sub in ("a", "b", "c"):
        _write(base / sub / "Widget.swift", "class Widget {\n    func update() {}\n}\n")
    _write(base / "Caller.swift", (
        "class Caller {\n"
        "    var w: Widget\n"
        "    func run() {\n"
        "        w.update()\n"
        "        unknown.update()\n"
        "    }\n"
        "}\n"
    ))
    files = sorted(base.rglob("*.swift"))
    result = extract(files, cache_root=tmp_path / "cache")

    inferred_calls = [
        e for e in result["edges"]
        if e.get("relation") == "calls" and e.get("confidence") == "INFERRED"
    ]
    # Ambiguous `Widget` (3 defs) -> no member-call edge; unknown receiver -> none.
    assert inferred_calls == []


def test_swift_unknown_receiver_emits_no_edge(tmp_path: Path):
    # A lowercase receiver absent from the file's type table is never guessed.
    base = tmp_path / "src"
    _write(base / "Helper.swift", "class Helper {\n    func help() {}\n}\n")
    _write(base / "Caller.swift", (
        "class Caller {\n"
        "    func run() {\n"
        "        mystery.help()\n"
        "    }\n"
        "}\n"
    ))
    files = sorted(base.rglob("*.swift"))
    result = extract(files, cache_root=tmp_path / "cache")

    edges = _edge_labels(result, relations=("calls",))
    assert (".run()", "calls", ".help()") not in edges


def test_deferred_singleton_local_var_resolves(tmp_path):
    """#1604: `let x = Type.shared` cached into a local var, then `x.method()` on a
    later line, must resolve to Type's method. This static-member (navigation) init
    was previously untyped, so the singleton-into-local idiom produced zero edges.
    The constructor form `let x = Type()` is exercised alongside it."""
    base = tmp_path / "src"
    _write(base / "NetworkManager.swift",
           "class NetworkManager {\n    static let shared = NetworkManager()\n"
           "    func fetchData() { }\n    func isLoading() -> Bool { return false }\n}\n")
    _write(base / "ViewController.swift",
           "class ViewControllerA {\n    func loadIfNeeded() {\n"
           "        let manager = NetworkManager.shared\n"
           "        if manager.isLoading() { return }\n"
           "        manager.fetchData()\n    }\n"
           "    func makeFresh() {\n        let m = NetworkManager()\n        m.fetchData()\n    }\n}\n")
    result = extract(sorted(base.glob("*.swift")), cache_root=tmp_path / "cache", parallel=False)
    calls = {(s, t) for s, r, t in _edge_labels(result, ("calls",))}
    # deferred singleton local var -> both later member calls resolve (method
    # labels carry a leading dot, e.g. ".loadIfNeeded()")
    assert any("loadIfNeeded" in s and "fetchData" in t for s, t in calls)
    assert any("loadIfNeeded" in s and "isLoading" in t for s, t in calls)
    # constructor-into-local still resolves
    assert any("makeFresh" in s and "fetchData" in t for s, t in calls)


def _extension_fixture(base: Path) -> list[Path]:
    """A singleton, a caller, and a cross-file `extension` of that singleton."""
    return [
        _write(base / "Core/Singleton.swift",
               "class Singleton {\n    static let shared = Singleton()\n"
               "    static func sm() {}\n    func method() {}\n}\n"),
        _write(base / "Views/HomeView.swift",
               "class HomeView {\n    func go() {\n        Singleton.sm()\n"
               "        Singleton.shared.method()\n        Singleton.shared.extra()\n    }\n}\n"),
        _write(base / "Core/Singleton+Ext.swift",
               "extension Singleton {\n    func extra() {}\n}\n"),
    ]


def test_cross_file_extension_does_not_erase_static_calls(tmp_path: Path):
    # #2538: swift_extensions[].nid is recorded pre-remap, so with absolute input
    # paths the extension merge matched nothing and Singleton kept two definition
    # nodes; the single-definition guard in _resolve_swift_member_calls then
    # dropped every call edge into it. One `extension Singleton {}` in its own
    # file was enough to zero the type's call graph, defeating #1533.
    files = _extension_fixture(tmp_path / "src")
    # root= is what the CLI passes; it triggers the id remap that made the
    # recorded extension nid stale. Without it the merge silently works.
    result = extract(files, cache_root=tmp_path / "cache", root=tmp_path / "src", parallel=False)

    defs = [n for n in result["nodes"] if n.get("label") == "Singleton"]
    assert len(defs) == 1, f"extension must merge into the canonical type, got {[n['id'] for n in defs]}"
    edges = _edge_labels(result)
    assert (".go()", "calls", ".sm()") in edges         # Singleton.sm()
    assert (".go()", "calls", ".method()") in edges     # Singleton.shared.method()
    assert (".go()", "calls", ".extra()") in edges      # extension method via .shared
    # Type-qualified static/singleton calls name the receiver in source: EXTRACTED.
    extracted = {
        (_label(result, e["source"]), _label(result, e["target"]))
        for e in result["edges"]
        if e.get("relation") == "calls" and e.get("confidence") == "EXTRACTED"
    }
    for tgt in (".sm()", ".method()", ".extra()"):
        assert (".go()", tgt) in extracted


def test_type_annotation_stub_does_not_block_extension_merge(tmp_path: Path):
    # A bare `var s: Singleton?` mints a sourceless shadow node labelled
    # Singleton; counting it as a merge candidate made the label look ambiguous.
    files = _extension_fixture(tmp_path / "src")
    files.append(_write(tmp_path / "src/Views/Holder.swift",
                        "class Holder {\n    var s: Singleton?\n}\n"))
    result = extract(files, cache_root=tmp_path / "cache", root=tmp_path / "src", parallel=False)

    assert (".go()", "calls", ".method()") in _edge_labels(result)


def test_same_file_extension_still_merges(tmp_path: Path):
    # Type, extension, and caller in ONE file: the pre-#2538 behaviour must hold —
    # a single Widget node and resolved calls into both halves.
    f = _write(tmp_path / "src/All.swift", (
        "class Widget {\n    static func sm() {}\n}\n\n"
        "extension Widget {\n    func extra() {}\n}\n\n"
        "class User {\n    let w = Widget()\n    func go() {\n"
        "        Widget.sm()\n        w.extra()\n    }\n}\n"
    ))
    result = extract([f], cache_root=tmp_path / "cache", root=tmp_path / "src", parallel=False)

    defs = [n for n in result["nodes"] if n.get("label") == "Widget"]
    assert len(defs) == 1, f"same-file extension must fold, got {[n['id'] for n in defs]}"
    edges = _edge_labels(result)
    assert (".go()", "calls", ".sm()") in edges
    assert (".go()", "calls", ".extra()") in edges


def test_extension_does_not_merge_into_same_named_foreign_type(tmp_path: Path):
    # The merge matches on label alone, so `extension Store` must not absorb a
    # TypeScript `class Store` in a polyglot repo — that fabricates a Swift call
    # into a TS method and makes the TS class own a Swift one.
    files = [
        _write(tmp_path / "src/web/Store.ts", "export class Store {\n  save() { return 1; }\n}\n"),
        _write(tmp_path / "src/ios/StoreExt.swift", "extension Store {\n    func reset() { }\n}\n"),
        _write(tmp_path / "src/ios/VM.swift",
               "final class VM {\n    let store: Store = Store()\n    func f() {\n        store.save()\n    }\n}\n"),
    ]
    result = extract(files, cache_root=tmp_path / "cache", root=tmp_path / "src", parallel=False)

    ts_store = next(n["id"] for n in result["nodes"]
                    if n.get("label") == "Store" and str(n.get("source_file", "")).endswith(".ts"))
    swift_nids = {n["id"] for n in result["nodes"]
                  if str(n.get("source_file", "")).endswith(".swift")}
    for e in result["edges"]:
        src_file = str(e.get("source_file", ""))
        if src_file.endswith(".swift"):
            assert e.get("target") != ts_store, f"Swift edge {e.get('relation')} bound to the TS Store"
        if e.get("source") == ts_store:
            assert e.get("target") not in swift_nids, "the TS Store came to own a Swift node"


# ── #2561: attribute-argument and factory-returned receiver types ─────────────

def test_environment_attribute_typed_receiver_resolves(tmp_path: Path):
    # @Environment(Store.self) names the property's type only inside the
    # attribute argument (modifiers > attribute), which the direct-children
    # scan never reached — store.reset() produced no edge at all.
    base = tmp_path / "src"
    _write(base / "Store.swift", "class Store {\n    func reset() {}\n}\n")
    _write(base / "HomeView.swift", (
        "struct HomeView {\n"
        "    @Environment(Store.self) var store\n"
        "    func go() {\n"
        "        store.reset()\n"
        "    }\n"
        "}\n"
    ))
    result = extract(sorted(base.glob("*.swift")), cache_root=tmp_path / "cache",
                     parallel=False)
    edge = next((e for e in result["edges"] if e.get("relation") == "calls"
                 and _label(result, e["target"]) == ".reset()"), None)
    assert edge is not None, "store.reset() must resolve to Store.reset"
    assert _label(result, edge["source"]) == ".go()"
    assert edge["confidence"] == "INFERRED" and edge["confidence_score"] == 0.85


def test_environment_keypath_and_dotted_forms_are_skipped(tmp_path: Path):
    # @Environment(\.dismiss) (keypath head) and @Environment(MyModule.Store.self)
    # (nested-navigation head) are undeterminable: skipping is a missed edge,
    # typing them would be a WRONG edge (e.g. into a fabricated MyModule node).
    base = tmp_path / "src"
    _write(base / "Store.swift", "class Store {\n    func reset() {}\n}\n")
    _write(base / "SheetView.swift", (
        "struct SheetView {\n"
        "    @Environment(\\.dismiss) var dismiss\n"
        "    @Environment(MyModule.Store.self) var other\n"
        "    func close() {\n"
        "        other.reset()\n"
        "    }\n"
        "}\n"
    ))
    result = extract(sorted(base.glob("*.swift")), cache_root=tmp_path / "cache",
                     parallel=False)
    assert (".close()", "calls", ".reset()") not in _edge_labels(result, ("calls",))
    for e in result["edges"]:
        assert _label(result, e["source"]) != "MyModule"
        assert _label(result, e["target"]) != "MyModule"


def test_stateobject_annotated_receiver_still_resolves(tmp_path: Path):
    # Regression pin: an explicitly-annotated wrapped property (@StateObject
    # var vm: ViewModel) resolved before #2561 and must keep resolving — the
    # attribute helper is a LAST resort behind the annotation.
    base = tmp_path / "src"
    _write(base / "ViewModel.swift", "class ViewModel {\n    func load() {}\n}\n")
    _write(base / "RootView.swift", (
        "struct RootView {\n"
        "    @StateObject var vm: ViewModel\n"
        "    func go() {\n"
        "        vm.load()\n"
        "    }\n"
        "}\n"
    ))
    result = extract(sorted(base.glob("*.swift")), cache_root=tmp_path / "cache",
                     parallel=False)
    assert (".go()", "calls", ".load()") in _edge_labels(result, ("calls",))


def test_factory_returned_receiver_resolves(tmp_path: Path):
    # `let widget = ServiceFactory.make()` (make -> Widget): the receiver types
    # as make's plain return type, for both a stored property and a local.
    base = tmp_path / "src"
    files = [
        _write(base / "Widget.swift", "class Widget {\n    func go() {}\n}\n"),
        _write(base / "ServiceFactory.swift",
               "class ServiceFactory {\n    static func make() -> Widget {\n"
               "        return Widget()\n    }\n}\n"),
        _write(base / "Consumer.swift", (
            "struct Consumer {\n"
            "    let widget = ServiceFactory.make()\n"
            "    func run() {\n"
            "        widget.go()\n"
            "    }\n"
            "    func local() {\n"
            "        let w = ServiceFactory.make()\n"
            "        w.go()\n"
            "    }\n"
            "}\n"
        )),
    ]
    result = extract(files, cache_root=tmp_path / "cache", parallel=False)
    calls = _edge_labels(result, ("calls",))
    assert (".run()", "calls", ".go()") in calls      # stored-property receiver
    assert (".local()", "calls", ".go()") in calls    # method-local receiver
    for e in result["edges"]:
        if e.get("relation") == "calls" and _label(result, e["target"]) == ".go()":
            assert e["confidence"] == "INFERRED" and e["confidence_score"] == 0.85


def test_factory_receiver_resolves_through_cross_file_extension(tmp_path: Path):
    # #2538 composition: the called method lives in a cross-file `extension
    # Widget` — the extension merge runs before this resolver, so the factory
    # receiver resolves through the merged method_index.
    base = tmp_path / "src"
    files = [
        _write(base / "Widget.swift", "class Widget {\n    func spin() {}\n}\n"),
        _write(base / "Widget+Ext.swift", "extension Widget {\n    func go() {}\n}\n"),
        _write(base / "ServiceFactory.swift",
               "class ServiceFactory {\n    static func make() -> Widget {\n"
               "        return Widget()\n    }\n}\n"),
        _write(base / "Consumer.swift", (
            "struct Consumer {\n"
            "    let widget = ServiceFactory.make()\n"
            "    func run() {\n"
            "        widget.go()\n"
            "    }\n"
            "}\n"
        )),
    ]
    result = extract(files, cache_root=tmp_path / "cache", root=base, parallel=False)
    assert (".run()", "calls", ".go()") in _edge_labels(result, ("calls",))


def test_undeterminable_factory_returns_yield_no_edge(tmp_path: Path):
    # `-> some P` (opaque), `-> [Widget]` (a COLLECTION of Widget, not a
    # Widget), and an out-of-corpus `-> Ghost` are all undeterminable: the
    # receiver stays untyped and no edge reaches Widget.go.
    base = tmp_path / "src"
    files = [
        _write(base / "Widget.swift", "class Widget {\n    func go() {}\n}\n"),
        _write(base / "ServiceFactory.swift", (
            "class ServiceFactory {\n"
            "    static func makeOpaque() -> some P {\n        return Widget()\n    }\n"
            "    static func makeMany() -> [Widget] {\n        return []\n    }\n"
            "    static func makeGhost() -> Ghost {\n        return Ghost()\n    }\n"
            "}\n"
        )),
        _write(base / "Consumer.swift", (
            "struct Consumer {\n"
            "    let a = ServiceFactory.makeOpaque()\n"
            "    let b = ServiceFactory.makeMany()\n"
            "    let c = ServiceFactory.makeGhost()\n"
            "    func run() {\n"
            "        a.go()\n"
            "        b.go()\n"
            "        c.go()\n"
            "    }\n"
            "}\n"
        )),
    ]
    result = extract(files, cache_root=tmp_path / "cache", parallel=False)
    assert (".run()", "calls", ".go()") not in _edge_labels(result, ("calls",))


def test_ambiguous_factory_type_yields_no_edge(tmp_path: Path):
    # Two ServiceFactory definitions: the exactly-one-definition guard must
    # refuse to pick a factory, so the receiver stays untyped.
    base = tmp_path / "src"
    files = [
        _write(base / "Widget.swift", "class Widget {\n    func go() {}\n}\n"),
        _write(base / "a/ServiceFactory.swift",
               "class ServiceFactory {\n    static func make() -> Widget {\n"
               "        return Widget()\n    }\n}\n"),
        _write(base / "b/ServiceFactory.swift",
               "class ServiceFactory {\n    static func make() -> Widget {\n"
               "        return Widget()\n    }\n}\n"),
        _write(base / "Consumer.swift", (
            "struct Consumer {\n"
            "    let widget = ServiceFactory.make()\n"
            "    func run() {\n"
            "        widget.go()\n"
            "    }\n"
            "}\n"
        )),
    ]
    result = extract(files, cache_root=tmp_path / "cache", parallel=False)
    assert (".run()", "calls", ".go()") not in _edge_labels(result, ("calls",))


def test_extension_merge_does_not_prune_unrelated_edges(tmp_path: Path):
    # The post-merge edge rebuild dedups on a key that ignores confidence and
    # weight. It must only touch edges the merge actually rewrote, or a single
    # Swift extension silently prunes parallel edges from other languages.
    # `g` emits three references to Thing sharing one (src, tgt, relation, file,
    # line) key — legitimate parallel edges the dedup key cannot tell apart.
    py = _write(tmp_path / "src/mod.py",
                "class Thing:\n    def run(self): return 1\n\n"
                "def g(a: Thing, b: Thing) -> Thing:\n    return a\n")
    swift = [
        _write(tmp_path / "src/Foo.swift", "struct Foo {\n    func bar() {}\n}\n"),
        _write(tmp_path / "src/FooExt.swift", "extension Foo {\n    func baz() {}\n}\n"),
    ]
    with_ext = extract([py, *swift], cache_root=tmp_path / "cache-a", root=tmp_path / "src", parallel=False)
    without_ext = extract([py, swift[0]], cache_root=tmp_path / "cache-b", root=tmp_path / "src", parallel=False)

    def _py_edges(result):
        return sum(1 for e in result["edges"] if str(e.get("source_file", "")).endswith(".py"))

    assert _py_edges(with_ext) == _py_edges(without_ext), "the extension merge pruned unrelated .py edges"


# ── Phase 1 of the cross-file type resolution RFC: mark real declarations ─────
#
# A type declared in one file, extended in the same file, and extended again in
# another file used to leave two sourced nodes of one name, so the rewire kept
# every referrer on its own stub. An extension of a type nobody in the corpus
# declares acted as that type's declaration instead. The assertions below name
# the target node (id plus source_file), not only a label: several nodes share a
# label, so a label-only check passes on a wrong binding.

def _xext_nodes(result: dict, label: str, file_suffix: str | None = None) -> list[dict]:
    return [
        n for n in result["nodes"]
        if n.get("label") == label
        and (file_suffix is None or str(n.get("source_file", "")).endswith(file_suffix))
    ]


def _xext_one(result: dict, label: str, file_suffix: str) -> dict:
    found = _xext_nodes(result, label, file_suffix)
    assert len(found) == 1, f"expected one {label!r} node in {file_suffix}, got {[n['id'] for n in found]}"
    return found[0]


def _xext_incoming(result: dict, nid: str, relation: str = "references") -> set[tuple[str, str | None, str]]:
    """{(source label, edge context, source file name)} of the `relation` edges into `nid`."""
    by_id = {n["id"]: n for n in result["nodes"]}
    return {
        (by_id[e["source"]].get("label", ""), e.get("context"),
         Path(str(by_id[e["source"]].get("source_file", ""))).name)
        for e in result["edges"]
        if e.get("target") == nid and e.get("relation") == relation and e.get("source") in by_id
    }


def _xext_has_edge(result: dict, source: str, target: str, relation: str) -> bool:
    return any(e.get("source") == source and e.get("target") == target
               and e.get("relation") == relation for e in result["edges"])


def _xext_foreign_refs(result: dict, nid: str, own_file: str) -> set[tuple[str, str | None, str]]:
    """References into `nid` that come from a file other than `own_file`."""
    return {r for r in _xext_incoming(result, nid) if r[2] != own_file}


def _xext_assert_contained(result: dict, ext_file: str, nid: str) -> None:
    """The file node of `ext_file` must have a `contains` edge to the node `nid`."""
    file_node = _xext_one(result, ext_file, ext_file)
    assert _xext_has_edge(result, file_node["id"], nid, "contains"), f"{ext_file} does not contain {nid}"


def test_declaration_with_same_file_extension_absorbs_cross_file_extension(tmp_path: Path):
    # RC1: `struct Layout` + `extension Layout` in one file share a node id and
    # the id used to be skipped as a merge candidate, so the `extension Layout` in
    # another file found no declaration and every referrer kept a per-file stub.
    base = tmp_path / "src"
    files = [
        _write(base / "App/Models/Layout.swift", (
            "import Foundation\n\n"
            "struct Layout: Equatable, Codable {\n"
            "  var panes: [Pane]\n"
            "  struct Pane: Equatable, Codable { var id: Int }\n"
            "  func encodeAll() -> Data { Data() }\n"
            "}\n\n"
            "extension Layout {\n"
            "  var isEmpty: Bool { panes.isEmpty }\n"
            "}\n"
        )),
        _write(base / "App/Logic/Migrator.swift", (
            "import Foundation\n\n"
            "extension Layout {\n"
            "  static func migrated() -> Layout { Layout(panes: []) }\n"
            "}\n\n"
            "enum Migrator {\n"
            "  static func run(_ input: Layout) -> Layout { input }\n"
            "}\n"
        )),
        _write(base / "App/Reducer/Editor.swift", (
            "import Foundation\n\n"
            "struct Editor {\n"
            "  struct State: Equatable {\n"
            "    var layout: Layout\n"
            "    var focused: Layout.Pane?\n"
            "  }\n"
            "  func reset(_ state: inout State) {\n"
            "    state.layout = Layout(panes: [])\n"
            "  }\n"
            "}\n"
        )),
        _write(base / "App/Logic/Persistence.swift", (
            "import Foundation\n\n"
            "final class LayoutStore {\n"
            "  var cached: Layout?\n"
            "  func save(_ layout: Layout) {}\n"
            "  func load() -> Layout { Layout(panes: []) }\n"
            "}\n"
        )),
    ]
    result = extract(files, cache_root=tmp_path / "cache", root=base, parallel=False)

    # One Layout node: the declaration. No extension node, no per-file stub.
    layouts = _xext_nodes(result, "Layout")
    assert len(layouts) == 1, f"expected one Layout node, got {[(n['id'], n.get('source_file')) for n in layouts]}"
    decl = layouts[0]
    assert str(decl.get("source_file", "")).endswith("Layout.swift")
    assert not decl.get("_swift_extension_only"), "a declared type must not be marked extension-only"
    nid = decl["id"]

    # The cross-file extension's method hangs on the declaration, and the extension's
    # file contains it.
    migrated = _xext_one(result, ".migrated()", "Migrator.swift")
    assert _xext_has_edge(result, nid, migrated["id"], "method")
    for file_label in ("Layout.swift", "Migrator.swift"):
        file_node = _xext_one(result, file_label, file_label)
        assert _xext_has_edge(result, file_node["id"], nid, "contains"), f"{file_label} must contain the declaration"

    # Every `references` edge from the other files lands on that node.
    refs = _xext_incoming(result, nid)
    expected = {
        (".run()", "parameter_type", "Migrator.swift"),
        (".run()", "return_type", "Migrator.swift"),
        (".migrated()", "return_type", "Migrator.swift"),
        ("State", "field", "Editor.swift"),
        ("LayoutStore", "field", "Persistence.swift"),
        (".save()", "parameter_type", "Persistence.swift"),
        (".load()", "return_type", "Persistence.swift"),
    }
    assert expected <= refs, f"references that missed the declaration: {sorted(expected - refs)}"


def test_extension_of_outside_type_does_not_absorb_references(tmp_path: Path):
    # RC2 / #4574: `extension String` is not a declaration of String. The only sourced
    # `String` node used to become the unique "real" definition, and every other file's
    # `String` stub was rewired onto the extension.
    base = tmp_path / "src"
    files = [
        _write(base / "Ext/StringExt.swift",
               "extension String {\n    func shout() -> String { self }\n}\n"),
        _write(base / "Ext/DateExt.swift",
               "private extension Date {\n    func day() -> Int { 1 }\n}\n"),
        _write(base / "Models/Name.swift", (
            "struct Name {\n"
            "    var raw: String\n"
            "    var at: Date\n"
            "    func f(_ s: String) -> Date { at }\n"
            "}\n"
        )),
    ]
    result = extract(files, cache_root=tmp_path / "cache", root=base, parallel=False)
    by_id = {n["id"]: n for n in result["nodes"]}

    for label, ext_file in (("String", "StringExt.swift"), ("Date", "DateExt.swift")):
        ext = _xext_one(result, label, ext_file)
        # The extension node stays, file-local, and no other file's reference reaches it.
        _xext_assert_contained(result, ext_file, ext["id"])
        assert _xext_foreign_refs(result, ext["id"], ext_file) == set(), (
            f"{ext_file} extension of {label} absorbed references from another file"
        )
        # Name.swift keeps its reference on a sourceless stub of the outside type.
        targets = [by_id[e["target"]] for e in result["edges"]
                   if e.get("relation") == "references"
                   and e["target"] in by_id and e["source"] in by_id
                   and by_id[e["target"]].get("label") == label
                   and Path(str(by_id[e["source"]].get("source_file", ""))).name == "Name.swift"]
        assert targets, f"Name.swift lost its reference to {label}"
        assert all(not t.get("source_file") for t in targets), (
            f"Name.swift reference to {label} reached {[(t['id'], t.get('source_file')) for t in targets]}"
        )

    # The extension's own method keeps its file-local reference to its extension node.
    string_ext = _xext_one(result, "String", "StringExt.swift")
    assert (".shout()", "return_type", "StringExt.swift") in _xext_incoming(result, string_ext["id"])


def test_extension_only_type_extended_in_two_files_stays_unresolved(tmp_path: Path):
    # Control (passes on the base too: two extension nodes already make the label
    # ambiguous). `extension View` in two files and `var body: some View` elsewhere: View
    # is declared nowhere in the corpus. The reference must stay on its stub and neither
    # extension node may attract it.
    base = tmp_path / "src"
    files = [
        _write(base / "Ext/ViewA.swift",
               "extension View {\n    func a() -> some View { self }\n}\n"),
        _write(base / "Ext/ViewB.swift",
               "extension View {\n    func b() -> some View { self }\n}\n"),
        _write(base / "Views/Home.swift",
               "struct Home {\n    var body: some View { Text() }\n}\n"),
    ]
    result = extract(files, cache_root=tmp_path / "cache", root=base, parallel=False)
    by_id = {n["id"]: n for n in result["nodes"]}

    ext_a = _xext_one(result, "View", "ViewA.swift")
    ext_b = _xext_one(result, "View", "ViewB.swift")
    for ext, own_file in ((ext_a, "ViewA.swift"), (ext_b, "ViewB.swift")):
        _xext_assert_contained(result, own_file, ext["id"])
        assert _xext_foreign_refs(result, ext["id"], own_file) == set()

    home_targets = [by_id[e["target"]] for e in result["edges"]
                    if e.get("relation") == "references"
                    and e["target"] in by_id and e["source"] in by_id
                    and by_id[e["target"]].get("label") == "View"
                    and Path(str(by_id[e["source"]].get("source_file", ""))).name == "Home.swift"]
    assert home_targets, "Home.swift lost its reference to View"
    assert all(not t.get("source_file") for t in home_targets), (
        f"Home.swift reference to View reached {[(t['id'], t.get('source_file')) for t in home_targets]}"
    )


def test_extension_only_node_does_not_absorb_other_file_reference(tmp_path: Path):
    # `extension Foo {}` in one file, no declaration anywhere, `var w: Foo` in another
    # file. On the base the rewire binds the other file's reference to the single
    # extension node; the extension-only marker keeps it on its sourceless stub.
    base = tmp_path / "src"
    files = [
        _write(base / "FooExt.swift", "extension Foo {\n    func a() {}\n}\n"),
        _write(base / "Use.swift", "struct Use {\n    var w: Foo\n}\n"),
    ]
    result = extract(files, cache_root=tmp_path / "cache", root=base, parallel=False)
    by_id = {n["id"]: n for n in result["nodes"]}

    ext = _xext_one(result, "Foo", "FooExt.swift")
    assert ext.get("_swift_extension_only") is True, "the extension node lost its marker"
    _xext_assert_contained(result, "FooExt.swift", ext["id"])
    assert _xext_foreign_refs(result, ext["id"], "FooExt.swift") == set(), (
        "Use.swift reference reached the extension-only node"
    )
    targets = [by_id[e["target"]] for e in result["edges"]
               if e.get("relation") == "references"
               and e["target"] in by_id and e["source"] in by_id
               and by_id[e["target"]].get("label") == "Foo"
               and Path(str(by_id[e["source"]].get("source_file", ""))).name == "Use.swift"]
    assert targets, "Use.swift lost its reference to Foo"
    assert all(not t.get("source_file") for t in targets), (
        f"Use.swift reference to Foo reached {[(t['id'], t.get('source_file')) for t in targets]}"
    )


def test_extension_only_marker_survives_incremental_update(tmp_path: Path):
    """`graphify update` hands the unchanged extension file to the changed file's
    resolution only as context nodes. The extension-only marker must ride along, or
    the changed file's `String` reference binds to the extension again."""
    import json

    from graphify.watch import _GRAPHIFY_OUT, _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "StringExt.swift").write_text(
        "extension String {\n    func shout() -> String { self }\n}\n", encoding="utf-8")
    consumer = corpus / "Name.swift"
    consumer.write_text("struct Name {\n    var raw: String\n}\n", encoding="utf-8")
    graph_path = corpus / _GRAPHIFY_OUT / "graph.json"

    def graph() -> tuple[dict[str, dict], list[dict]]:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        return {n["id"]: n for n in data["nodes"]}, data["links"]

    def refs_from_consumer_onto_extension() -> list[tuple[str, str]]:
        by_id, links = graph()
        ext_ids = {nid for nid, n in by_id.items()
                   if n.get("label") == "String" and str(n.get("source_file", "")).endswith("StringExt.swift")}
        assert len(ext_ids) == 1, f"expected the extension node of String, got {sorted(ext_ids)}"
        return [
            (by_id[e["source"]].get("label", ""), e["target"])
            for e in links
            if e.get("relation") == "references" and e["target"] in ext_ids
            and e["source"] in by_id
            and str(by_id[e["source"]].get("source_file", "")).endswith("Name.swift")
        ]

    def consumer_refs_on_stub() -> int:
        """Name's field reference to String, kept on a sourceless stub."""
        by_id, links = graph()
        return sum(
            1 for e in links
            if e.get("relation") == "references" and e.get("context") == "field"
            and e["source"] in by_id and e["target"] in by_id
            and by_id[e["source"]].get("label") == "Name"
            and by_id[e["target"]].get("label") == "String"
            and not by_id[e["target"]].get("source_file")
        )

    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    assert refs_from_consumer_onto_extension() == [], "the full build bound Name to the String extension"
    assert consumer_refs_on_stub() == 1, "the full build lost Name's reference to the String stub"

    # Change only the consumer; the extension file comes back as context nodes.
    consumer.write_text("struct Name {\n    var raw: String\n    func f() {}\n}\n", encoding="utf-8")
    assert _rebuild_code(corpus, changed_paths=[consumer], no_cluster=True, acquire_lock=False) is True
    by_id, _ = graph()
    assert any(n.get("label") == ".f()" for n in by_id.values()), "the incremental update did not re-extract Name.swift"
    assert refs_from_consumer_onto_extension() == [], "the incremental update bound Name to the String extension"
    assert consumer_refs_on_stub() == 1, "the incremental update lost Name's reference to the String stub"


def test_incremental_extension_merges_into_unchanged_declaration(tmp_path: Path):
    """Change only `extension Foo`: the declaration in the unchanged file is a read-only
    candidate, so the extension folds onto it exactly as in a full build."""
    import json

    from graphify.watch import _GRAPHIFY_OUT, _rebuild_code

    ext_v1 = "extension Foo {\n    func extra() {}\n}\n"
    ext_v2 = "extension Foo {\n    func extra() {}\n    func more() {}\n}\n"

    def write_corpus(corpus: Path, ext_text: str) -> Path:
        corpus.mkdir()
        (corpus / "Foo.swift").write_text("struct Foo {\n    func a() {}\n}\n", encoding="utf-8")
        (corpus / "Use.swift").write_text("struct Use {\n    var f: Foo\n}\n", encoding="utf-8")
        ext_file = corpus / "FooExt.swift"
        ext_file.write_text(ext_text, encoding="utf-8")
        return ext_file

    def graph(corpus: Path) -> tuple[dict[str, dict], set[tuple[str, str, str]]]:
        data = json.loads((corpus / _GRAPHIFY_OUT / "graph.json").read_text(encoding="utf-8"))
        by_id = {n["id"]: n for n in data["nodes"]}
        return by_id, {(e["source"], e["target"], e["relation"]) for e in data["links"]}

    # Reference: a full build of the final content.
    full_dir = tmp_path / "full" / "corpus"
    full_dir.parent.mkdir()
    write_corpus(full_dir, ext_v2)
    assert _rebuild_code(full_dir, no_cluster=True, acquire_lock=False) is True
    full_nodes, full_edges = graph(full_dir)

    # Full build of the old content, then an incremental update of the extension file only.
    inc_dir = tmp_path / "inc" / "corpus"
    inc_dir.parent.mkdir()
    ext_file = write_corpus(inc_dir, ext_v1)
    assert _rebuild_code(inc_dir, no_cluster=True, acquire_lock=False) is True
    ext_file.write_text(ext_v2, encoding="utf-8")
    assert _rebuild_code(inc_dir, changed_paths=[ext_file], no_cluster=True, acquire_lock=False) is True
    inc_nodes, inc_edges = graph(inc_dir)

    foos = [n for n in inc_nodes.values() if n.get("label") == "Foo"]
    assert len(foos) == 1, f"expected one Foo node, got {[(n['id'], n.get('source_file')) for n in foos]}"
    foo = foos[0]
    assert str(foo.get("source_file", "")).endswith("Foo.swift")
    methods = {inc_nodes[t]["label"] for s, t, r in inc_edges if s == foo["id"] and r == "method"}
    assert methods == {".a()", ".extra()", ".more()"}
    uses = [n for n in inc_nodes.values() if n.get("label") == "Use"]
    assert len(uses) == 1
    assert (uses[0]["id"], foo["id"], "references") in inc_edges, "Use lost its reference to the declaration"

    assert set(inc_nodes) == set(full_nodes), "the incremental node set differs from a full build"
    assert inc_edges == full_edges, "the incremental edge set differs from a full build"


def test_same_file_extension_alone_still_resolves_references(tmp_path: Path):
    # Control (the RC1 control, and the #4600 regression guard): `struct Foo` + `extension
    # Foo` in one file, nothing extends Foo elsewhere. The declared node is the only Foo,
    # so other files' references resolve to it. Marking every id that has an extension as
    # "extension-only" would put them back on stubs.
    base = tmp_path / "src"
    files = [
        _write(base / "Foo.swift", (
            "struct Foo {\n    func a() {}\n}\n\n"
            "extension Foo {\n    func b() {}\n}\n"
        )),
        _write(base / "Consumer.swift", (
            "struct Consumer {\n"
            "    var f: Foo\n"
            "    func g(_ x: Foo) -> Foo { x }\n"
            "}\n"
        )),
    ]
    result = extract(files, cache_root=tmp_path / "cache", root=base, parallel=False)

    foo = _xext_one(result, "Foo", "Foo.swift")
    assert len(_xext_nodes(result, "Foo")) == 1, "a sourceless Foo stub survived"
    assert not foo.get("_swift_extension_only")
    file_node = _xext_one(result, "Foo.swift", "Foo.swift")
    assert _xext_has_edge(result, file_node["id"], foo["id"], "contains")
    for method in (".a()", ".b()"):
        node = _xext_one(result, method, "Foo.swift")
        assert _xext_has_edge(result, foo["id"], node["id"], "method")
    expected = {
        ("Consumer", "field", "Consumer.swift"),
        (".g()", "parameter_type", "Consumer.swift"),
        (".g()", "return_type", "Consumer.swift"),
    }
    refs = _xext_incoming(result, foo["id"])
    assert expected <= refs, f"references that missed Foo: {sorted(expected - refs)}"


def test_same_file_reference_to_extension_only_node_stays_file_local(tmp_path: Path):
    # Control: `extension Foo {}` and `var v: Foo` in one file, no declaration anywhere.
    # The reference targets that file's own extension node, never a fabricated stub. (The
    # other half of the rule, that no OTHER file's reference reaches an extension-only
    # node, is covered by test_extension_only_node_does_not_absorb_other_file_reference.)
    base = tmp_path / "src"
    f = _write(base / "Holder.swift", (
        "extension Foo {\n    func a() {}\n}\n\n"
        "struct Holder {\n    var v: Foo\n}\n"
    ))
    result = extract([f], cache_root=tmp_path / "cache", root=base, parallel=False)

    foo = _xext_one(result, "Foo", "Holder.swift")
    assert len(_xext_nodes(result, "Foo")) == 1, "a Foo stub appeared next to the file's own node"
    _xext_assert_contained(result, "Holder.swift", foo["id"])
    assert ("Holder", "field", "Holder.swift") in _xext_incoming(result, foo["id"])


# Phase 4 (RC4): a bare `Foo(...)` in a Swift file binds to the one type the
# caller's lexical scope sees, as an INFERRED constructor call.


def _constructor_calls(result: dict, caller_label: str) -> list[dict]:
    """The `calls` edges out of the node labelled ``caller_label``."""
    callers = {n["id"] for n in result["nodes"] if n.get("label") == caller_label}
    return [
        e for e in result["edges"]
        if e.get("relation") == "calls" and e["source"] in callers
    ]


def test_cross_file_constructor_call_emits_inferred_call(tmp_path: Path):
    # `.reset()` names Layout only in the constructor call, not as a type,
    # so the (caller, target) pair dedup cannot hide the edge behind a
    # `references` edge. The caller's file names Layout as a field type
    # without defining it, which made the call a `via_stub` call that the
    # import-evidence gate dropped before.
    base = tmp_path / "src"
    files = [
        _write(base / "Models/Layout.swift",
               "struct Layout {\n    let panes: [Int]\n}\n"),
        _write(base / "Reducer/Editor.swift", (
            "struct Editor {\n"
            "    struct State {\n"
            "        var layout: Layout\n"
            "    }\n"
            "    func reset(_ state: inout State) {\n"
            "        state.layout = Layout(panes: [])\n"
            "    }\n"
            "}\n"
        )),
    ]
    result = extract(files, cache_root=tmp_path / "cache", root=base, parallel=False)

    decl_ids = {
        n["id"] for n in result["nodes"]
        if n.get("label") == "Layout"
        and str(n.get("source_file", "")).endswith("Models/Layout.swift")
    }
    assert len(decl_ids) == 1
    calls = [e for e in _constructor_calls(result, ".reset()") if e["target"] in decl_ids]
    assert len(calls) == 1
    edge = calls[0]
    assert edge["context"] == "constructor"
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.85


def test_constructor_call_not_visible_lexically_stays_unresolved(tmp_path: Path):
    # The only Config is the nested Outer.Config; a bare `Config()` in an
    # unrelated type cannot see it, so no edge lands on it by name.
    base = tmp_path / "src"
    files = [
        _write(base / "Models/Outer.swift",
               "struct Outer {\n    struct Config {}\n}\n"),
        _write(base / "Views/User.swift", (
            "struct User {\n"
            "    func make() {\n"
            "        let c = Config()\n"
            "    }\n"
            "}\n"
        )),
    ]
    result = extract(files, cache_root=tmp_path / "cache", root=base, parallel=False)

    config_ids = {n["id"] for n in result["nodes"] if n.get("label") == "Config"}
    assert config_ids
    assert [e for e in _constructor_calls(result, ".make()") if e["target"] in config_ids] == []


def test_ambiguous_constructor_callee_stays_unresolved(tmp_path: Path):
    # Two top-level Config types: `Config()` sees both, so it binds to neither.
    base = tmp_path / "src"
    files = [
        _write(base / "a/Config.swift", "struct Config {}\n"),
        _write(base / "b/Config.swift", "struct Config {}\n"),
        _write(base / "Views/User.swift", (
            "struct User {\n"
            "    func make() {\n"
            "        let c = Config()\n"
            "    }\n"
            "}\n"
        )),
    ]
    result = extract(files, cache_root=tmp_path / "cache", root=base, parallel=False)

    config_ids = {n["id"] for n in result["nodes"] if n.get("label") == "Config"}
    assert len(config_ids) >= 2
    assert [e for e in _constructor_calls(result, ".make()") if e["target"] in config_ids] == []


def test_constructor_call_in_extension_of_objc_class_binds(tmp_path: Path):
    # A Swift extension of an Objective-C class folds onto the ObjC node, which
    # carries no Swift qualified path. Its calls are looked up at file scope and
    # still bind `Item()`, as before the Swift type index.
    base = tmp_path / "src"
    files = [
        _write(base / "Widget.h",
               "#import <Foundation/Foundation.h>\n@interface Widget : NSObject\n- (void)ping;\n@end\n"),
        _write(base / "Types.swift", "struct Item {}\n"),
        _write(base / "Extras.swift",
               "extension Widget {\n    func run() {\n        Item()\n    }\n}\n"),
    ]
    result = extract(files, cache_root=tmp_path / "cache", root=base, parallel=False)

    item_ids = {
        n["id"] for n in result["nodes"]
        if n.get("label") == "Item" and str(n.get("source_file", "")).endswith("Types.swift")
    }
    assert len(item_ids) == 1
    calls = [e for e in _constructor_calls(result, ".run()") if e["target"] in item_ids]
    assert len(calls) == 1, f"expected one call to Item, got {_constructor_calls(result, '.run()')}"


def test_constructor_call_does_not_bind_extension_only_node(tmp_path: Path):
    # `External` is declared outside the corpus; `extension External` only adds
    # members. `External()` must not bind to that extension node.
    base = tmp_path / "src"
    files = [
        _write(base / "Ext.swift", "extension External {\n    func helper() {}\n}\n"),
        _write(base / "Use.swift", "func run() {\n    External()\n}\n"),
    ]
    result = extract(files, cache_root=tmp_path / "cache", root=base, parallel=False)

    ext_ids = {
        n["id"] for n in result["nodes"]
        if n.get("label") == "External" and str(n.get("source_file", "")).endswith("Ext.swift")
    }
    assert ext_ids
    assert [e for e in _constructor_calls(result, "run()") if e["target"] in ext_ids] == []
