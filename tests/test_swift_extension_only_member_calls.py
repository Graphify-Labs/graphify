"""Swift member calls must not bind a type-only edge to an extension-only node.

See docs/swift-cross-file-type-resolution-rfc.md (extension-only nodes). An
``extension Foo {}`` in a file where ``Foo`` is not declared leaves a node marked
``_swift_extension_only``: ``Foo`` is an external type (``NSEvent``) or a type declared
nowhere in the corpus. That node is not a declaration, so a cross-file member call
``Foo.x()`` / ``foo.x()`` whose method is not defined in the extension must not emit a
``references`` edge to it. A method defined in the extension is a real target, so its
``calls`` edge stays. With a real declaration of ``Foo`` in the corpus the extension
folds into it and the usual binding holds.

The style follows tests/test_swift_type_resolution.py: write the files into
``tmp_path`` and call ``extract(files, cache_root=..., root=..., parallel=False)``.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


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


def _call_edges(result: dict, relation: str) -> list[tuple[dict, dict]]:
    """(source node, target node) of every ``context == "call"`` edge of ``relation``."""
    by_id = _by_id(result)
    return [
        (by_id.get(e["source"], {}), by_id.get(e["target"], {}))
        for e in result["edges"]
        if e.get("relation") == relation and e.get("context") == "call"
    ]


def _files(base: Path, *, with_declaration: bool, helper_call: bool = False) -> list[Path]:
    """The repro: extension-only ``Manager`` and ``NSEvent``, called from ``User``."""
    calls = [
        "        Manager.shared.run()",
        "        m?.hostIfExists()",
        "        NSEvent.addMonitor()",
    ]
    if helper_call:
        calls.append("        m?.helper()")
    files = [
        _write(base / "Tests" / "Helpers.swift", "extension Manager {\n    func helper() {}\n}\n"),
        _write(
            base / "App" / "Use.swift",
            "class User {\n    var m: Manager?\n    func go() {\n"
            + "\n".join(calls)
            + "\n    }\n}\n",
        ),
        _write(base / "App" / "Panel.swift", "extension NSEvent {\n    var flags: Int { 0 }\n}\n"),
    ]
    if with_declaration:
        files.append(_write(
            base / "App" / "Manager.swift",
            "class Manager {\n    static let shared = Manager()\n    func run() {}\n}\n",
        ))
    return files


# ── tests ─────────────────────────────────────────────────────────────────────

def test_member_call_to_undefined_method_does_not_reference_extension_only_node(tmp_path: Path):
    result = _extract(_files(tmp_path / "src", with_declaration=False), tmp_path)

    by_label = {}
    for n in result["nodes"]:
        if n.get("_swift_extension_only"):
            by_label[n.get("label")] = n
    # The setup holds: both extensions stay extension-only (nothing to fold into).
    assert {"Manager", "NSEvent"} <= set(by_label), by_label

    wrong = [
        (src.get("label"), tgt.get("label"), _sf(tgt))
        for src, tgt in _call_edges(result, "references")
        if tgt.get("_swift_extension_only")
    ]
    assert wrong == []


def test_member_call_to_method_defined_in_extension_keeps_calls_edge(tmp_path: Path):
    result = _extract(
        _files(tmp_path / "src", with_declaration=False, helper_call=True), tmp_path,
    )

    calls = {
        (src.get("label"), tgt.get("label"), _sf(tgt))
        for src, tgt in _call_edges(result, "calls")
    }
    assert any(
        src == ".go()" and tgt == ".helper()" and sf.endswith("Helpers.swift")
        for src, tgt, sf in calls
    ), calls
    # The undefined methods on the same extension-only types still bind nothing.
    assert not any(
        tgt.get("_swift_extension_only") for _, tgt in _call_edges(result, "references")
    )


def test_member_call_with_real_declaration_still_binds(tmp_path: Path):
    result = _extract(_files(tmp_path / "src", with_declaration=True), tmp_path)

    calls = {
        (src.get("label"), tgt.get("label"), _sf(tgt))
        for src, tgt in _call_edges(result, "calls")
    }
    assert any(
        src == ".go()" and tgt == ".run()" and sf.endswith("Manager.swift")
        for src, tgt, sf in calls
    ), calls

    refs = [(src, tgt) for src, tgt in _call_edges(result, "references")]
    # `m?.hostIfExists()` names no method, so it references the declared type.
    manager_refs = [
        tgt for src, tgt in refs
        if src.get("label") == ".go()" and tgt.get("label") == "Manager"
    ]
    assert len(manager_refs) == 1, refs
    assert _sf(manager_refs[0]).endswith("Manager.swift")
    assert not manager_refs[0].get("_swift_extension_only")
    # `NSEvent` is still declared nowhere: its extension-only node gets no edge.
    assert not any(tgt.get("_swift_extension_only") for _, tgt in refs), refs


def test_dotted_external_type_name_does_not_bind_through_label_key(tmp_path: Path):
    # `MenuItem.ID` is declared nowhere here. The label key strips the dot,
    # so without the guard `x.run()` bound to the unrelated `MenuItemID.run`.
    base = tmp_path / "src"
    files = [
        _write(base / "App" / "ItemID.swift", "enum MenuItemID {\n    func run() {}\n}\n"),
        _write(
            base / "App" / "Use.swift",
            "class User {\n    let x: MenuItem.ID\n    func go() {\n        x.run()\n    }\n}\n",
        ),
    ]
    result = _extract(files, tmp_path)

    by_id = _by_id(result)
    item_ids = {n["id"] for n in result["nodes"] if n.get("label") == "MenuItemID"}
    assert item_ids, "setup: the namesake enum must exist"
    run_ids = {
        e["target"] for e in result["edges"]
        if e.get("relation") == "method" and e.get("source") in item_ids
    }
    assert run_ids, "setup: the namesake enum must own `run()`"
    wrong = [
        (by_id.get(e["source"], {}).get("label"), by_id.get(e["target"], {}).get("label"))
        for e in result["edges"]
        if e.get("context") == "call" and e.get("target") in item_ids | run_ids
    ]
    assert wrong == []
