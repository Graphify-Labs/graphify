"""INC-QML-59: generic intentional-empty sources coexist with accepted Qt state."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

import graphify.__main__ as mainmod
import graphify.detect as detectmod
import graphify.extract as extractmod
from graphify.qt_analysis_state import inspect_qt_analysis


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


def _decline_sql(monkeypatch):
    """Isolate the unrelated SQL parser while exercising real Qt publication."""
    calls = []

    def decline(path):
        calls.append(path)
        return {"nodes": [], "edges": [], "skipped": True}

    monkeypatch.setitem(extractmod._DISPATCH, ".sql", decline)
    return calls


@pytest.mark.parametrize("raw", [False, True])
def test_req_qml011_ac04_declined_sources_preserve_accepted_qt_context(
    monkeypatch, tmp_path, capsys, raw
):
    """Both publication paths retain the upstream marker and real Qt context."""
    root = _corpus(tmp_path / "app")
    calls = _decline_sql(monkeypatch)
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
    # Acceptance setup must not depend on an optional SQL wheel: only that
    # independent input declines; Qt parsing and the manifest write remain real.
    _decline_sql(monkeypatch)
    _run(monkeypatch, root, True)
    output = root / "graphify-out"
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    sql = next(value for key, value in manifest.items() if key.endswith("schema.sql"))
    assert sql["ast_empty"] is True and sql["ast_hash"]
    state = output / ".qt_analysis.json"
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
    recovered = state.read_bytes()
    products = {name: (output / name).read_bytes() for name in (
        "graph.json", "manifest.json", ".graphify_root", ".qt_analysis.json"
    )}
    _run(monkeypatch, root, True)
    assert state.read_bytes() == recovered
    assert {name: (output / name).read_bytes() for name in products} == products


@pytest.mark.parametrize("raw", [False, True])
def test_req_qml012_ac02_missing_unrelated_parser_preserves_accepted_qt_context(
    monkeypatch, tmp_path, capsys, raw
):
    """A real optional-parser rejection cannot authorize changed Qt context."""
    root = _corpus(tmp_path / "app")
    real_sql = extractmod._DISPATCH[".sql"]
    _decline_sql(monkeypatch)
    _run(monkeypatch, root, raw)
    output = root / "graphify-out"
    state = output / ".qt_analysis.json"
    accepted = state.read_bytes()

    # Leave the intentional-empty cache behind, then invalidate the SQL bytes
    # and restore its actual parser. The import sentinel exercises production's
    # missing-module diagnostic without installing or removing any dependency.
    (root / "schema.sql").write_text("-- changed SQL input\n", encoding="utf-8")
    (root / "Main.qml").write_text("Item { property int count: 2 }\n", encoding="utf-8")
    (root / ".graphifyignore").write_text("*.never\n", encoding="utf-8")
    candidate = inspect_qt_analysis(root, output, [
        root / name for name in ("CMakeLists.txt", "Main.qml", "schema.sql")
    ])
    assert candidate.changed and candidate.fingerprint != json.loads(accepted)["fingerprint"]
    monkeypatch.setitem(extractmod._DISPATCH, ".sql", real_sql)
    monkeypatch.setitem(sys.modules, "tree_sitter_sql", None)
    _run(monkeypatch, root, raw)
    assert "tree_sitter_sql not installed" in capsys.readouterr().err
    assert state.read_bytes() == accepted
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    sql = next(value for key, value in manifest.items() if key.endswith("schema.sql"))
    assert not sql["ast_hash"] and not sql.get("ast_empty")

    # A deliberate decline is accepted only after a new successful publication;
    # repeating it must not manufacture another Qt acceptance transition.
    _decline_sql(monkeypatch)
    _run(monkeypatch, root, raw)
    recovered = state.read_bytes()
    assert recovered != accepted
    assert json.loads(recovered)["fingerprint"] == candidate.fingerprint
    _run(monkeypatch, root, raw)
    assert state.read_bytes() == recovered
