"""INC-QML-60: an upstream no-change gate retains Qt acceptance ownership."""
from __future__ import annotations

from pathlib import Path

import pytest

import graphify.detect as detection
import graphify.extract as extraction
import graphify.qt_analysis_state as qt_state
import graphify.watch as watch


def _project(root: Path) -> Path:
    """Public mixed input has real QML/module facts and unrelated Python code."""
    root.mkdir()
    (root / "CMakeLists.txt").write_text(
        "qt_add_qml_module(app URI Public.Tools QML_FILES Main.qml)\n", encoding="utf-8"
    )
    (root / "Main.qml").write_text("Item { property int count: 1 }\n", encoding="utf-8")
    (root / "keep.py").write_text("def retained():\n    return 1\n", encoding="utf-8")
    (root / "imports").mkdir()
    return root


def _spy_extract(monkeypatch):
    """Count the real extractor entry point without substituting its facts."""
    calls = []
    original = extraction.extract

    def counted(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(extraction, "extract", counted)
    return calls


def _rebuild(root, raw):
    return watch._rebuild_code(root, no_cluster=raw, acquire_lock=False)


@pytest.mark.parametrize("raw", [False, True])
@pytest.mark.parametrize("mutation", ["missing-state", "import-roots"])
def test_req_qml011_ac04_qml012_ac02_fast_gate_requires_current_qt_acceptance(
        tmp_path, monkeypatch, capsys, raw, mutation):
    """Unchanged corpus hashes cannot authorize missing or changed Qt context."""
    root = _project(tmp_path / "project")
    monkeypatch.setenv("GRAPHIFY_QML_IMPORT_ROOTS", '["."]')
    assert _rebuild(root, raw)
    out = root / "graphify-out"
    stamp, accepted = out / watch._BUILD_STATE_NAME, out / qt_state.QT_STATE_FILE
    before = accepted.read_bytes()
    assert stamp.is_file()
    calls = _spy_extract(monkeypatch)
    capsys.readouterr()
    assert _rebuild(root, raw)
    assert "No relevant changes" in capsys.readouterr().out and not calls

    # Neither mutation edits a detected source or upstream skip-key input.
    # Qt analysis owns this independent acceptance decision before that gate.
    if mutation == "missing-state":
        accepted.unlink()
    else:
        monkeypatch.setenv("GRAPHIFY_QML_IMPORT_ROOTS", '["imports"]')
    assert _rebuild(root, raw)
    assert calls, "Qt context refresh was skipped merely because corpus bytes matched"
    assert accepted.is_file()
    if mutation == "import-roots":
        assert accepted.read_bytes() != before
    else:
        assert accepted.read_bytes() == before
    calls.clear()
    capsys.readouterr()
    assert _rebuild(root, raw)
    assert "No relevant changes" in capsys.readouterr().out and not calls


@pytest.mark.parametrize("raw", [False, True])
def test_req_qml012_ac02_qml011_ac04_failed_qt_cohort_cannot_advance_skip_stamp(
        tmp_path, monkeypatch, capsys, raw):
    """Actual staged Qt write failure retains accepted bytes, then recovers."""
    root = _project(tmp_path / "project")
    monkeypatch.setenv("GRAPHIFY_QML_IMPORT_ROOTS", '["."]')
    assert _rebuild(root, raw)
    out = root / "graphify-out"
    products = ("graph.json", ".graphify_root", "manifest.json", qt_state.QT_STATE_FILE,
                watch._BUILD_STATE_NAME)
    before = {name: (out / name).read_bytes() for name in products}
    (root / "Main.qml").write_text(
        "Item { property int count: 1; property int added: 2 }\n", encoding="utf-8"
    )
    original = qt_state.save_qt_fingerprint

    def reject(*args, **kwargs):
        raise OSError("injected Qt state staging failure")

    monkeypatch.setattr(qt_state, "save_qt_fingerprint", reject)
    assert not _rebuild(root, raw)
    assert "GRAPH_PUBLICATION_FAILED" in capsys.readouterr().out
    assert {name: (out / name).read_bytes() for name in products} == before

    monkeypatch.setattr(qt_state, "save_qt_fingerprint", original)
    assert _rebuild(root, raw)
    assert (out / "graph.json").read_bytes() != before["graph.json"]
    assert not list(out.glob(".gfy-publish-*"))
    calls = _spy_extract(monkeypatch)
    capsys.readouterr()
    assert _rebuild(root, raw)
    assert "No relevant changes" in capsys.readouterr().out and not calls


@pytest.mark.parametrize("name", ["settings.yaml", "settings.yml", "Main.qml", "Types.qmltypes",
                                  "project.cmake", "project.pro", "project.pri", "resources.qrc",
                                  "qmldir", "CMakeLists.txt"])
def test_req_qml002_ac01_qml014_ac03_yaml_and_qt_metadata_share_source_admission(name):
    """Incoming YAML AST classification retains every established Qt suffix/name."""
    assert detection.classify_file(Path(name)) == "code"
