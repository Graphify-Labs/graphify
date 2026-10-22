"""INC-QML-59: generic intentional-empty sources coexist with accepted Qt state."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import graphify.__main__ as mainmod
import graphify.detect as detectmod
import graphify.extract as extractmod


def _corpus(root: Path) -> Path:
    """Public mixed corpus has a real Qt module plus one declined SQL input."""
    root.mkdir()
    (root / "CMakeLists.txt").write_text(
        "qt_add_qml_module(app URI Example QML_FILES Main.qml)\n", encoding="utf-8"
    )
    (root / "Main.qml").write_text("Item { property int count: 1 }\n", encoding="utf-8")
    (root / "schema.sql").write_text("-- intentionally declined fixture\n", encoding="utf-8")
    return root


def _run(monkeypatch, root: Path, raw: bool) -> None:
    """Exercise the actual CLI pipeline while isolating installer side effects."""
    argv = ["graphify", "extract", str(root), "--code-only", "--max-workers", "1"]
    if raw:
        argv.append("--no-cluster")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0)


@pytest.mark.parametrize("raw", [False, True])
def test_req_qml011_ac04_declined_sources_preserve_accepted_qt_context(
    monkeypatch, tmp_path, capsys, raw
):
    """Both publication paths retain the upstream marker and real Qt context."""
    root = _corpus(tmp_path / "app")
    calls = []

    def decline(path):
        # Only the independent SQL extraction boundary is controlled; Qt parsing,
        # cache, manifest publication, graph assembly and repeats remain real.
        calls.append(path)
        return {"nodes": [], "edges": [], "skipped": True}

    monkeypatch.setitem(extractmod._DISPATCH, ".sql", decline)
    _run(monkeypatch, root, raw)
    output = root / "graphify-out"
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    sql = next(value for key, value in manifest.items() if key.endswith("schema.sql"))
    assert sql["ast_empty"] is True and sql["ast_hash"]
    state = output / ".qt_analysis.json"
    accepted = state.read_bytes()
    graph = json.loads((output / "graph.json").read_text(encoding="utf-8"))
    assert any(node.get("source_file") == "Main.qml" for node in graph["nodes"])

    capsys.readouterr()
    for _ in range(2):
        _run(monkeypatch, root, raw)
        assert state.read_bytes() == accepted
    assert len(calls) == 1


def test_req_qml012_ac02_manifest_failure_does_not_advance_accepted_qt_context(
    monkeypatch, tmp_path, capsys
):
    """An actual manifest persistence rejection prevents the later Qt commit."""
    root = _corpus(tmp_path / "app")
    _run(monkeypatch, root, True)
    state = root / "graphify-out" / ".qt_analysis.json"
    accepted = state.read_bytes()
    (root / "Main.qml").write_text("Item { property int count: 2 }\n", encoding="utf-8")
    # Qt state owns configuration rather than per-source hashes. A harmless
    # new ignore pattern changes its fingerprint without excluding any input.
    (root / ".graphifyignore").write_text("*.never\n", encoding="utf-8")
    original = detectmod.save_manifest

    def reject(*args, **kwargs):
        raise OSError("injected manifest persistence rejection")

    monkeypatch.setattr(detectmod, "save_manifest", reject)
    _run(monkeypatch, root, True)
    assert "injected manifest persistence rejection" in capsys.readouterr().err
    assert state.read_bytes() == accepted

    monkeypatch.setattr(detectmod, "save_manifest", original)
    _run(monkeypatch, root, True)
    assert state.read_bytes() != accepted
