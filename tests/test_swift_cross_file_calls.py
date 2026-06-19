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


def test_swift_cross_file_member_calls_are_inferred_and_resolve_to_real_nodes(tmp_path: Path):
    # The new edges must be INFERRED (type inference, not an explicit import) and
    # land on real definition nodes so build_from_json keeps them.
    files = _issue_fixture(tmp_path / "src")
    result = extract(files, cache_root=tmp_path / "cache")

    node_ids = {n["id"] for n in result["nodes"]}
    src_by_id = {n["id"]: n.get("source_file") for n in result["nodes"]}

    member_targets = {".update()", ".fetch()", ".staticMethod()", ".method()"}
    seen_targets: set[str] = set()
    for e in result["edges"]:
        tgt_label = _label(result, e["target"])
        if e.get("relation") == "calls" and tgt_label in member_targets:
            assert e["confidence"] == "INFERRED"
            assert e["confidence_score"] == 0.8
            assert e["target"] in node_ids
            assert src_by_id.get(e["target"])  # resolved to a real, source-backed def
            seen_targets.add(tgt_label)
    assert seen_targets == member_targets

    # Edges survive graph construction (no dangling targets pruned).
    g = build_from_json(result)
    surviving = sum(
        1 for _, _, d in g.edges(data=True)
        if d.get("confidence") == "INFERRED" and d.get("relation") == "calls"
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
