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
            assert e["confidence"] == "INFERRED" and e["confidence_score"] == 0.8
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
    assert edge["confidence"] == "INFERRED" and edge["confidence_score"] == 0.8


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
            assert e["confidence"] == "INFERRED" and e["confidence_score"] == 0.8


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
