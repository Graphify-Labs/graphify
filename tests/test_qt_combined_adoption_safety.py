"""REQ-QML-018-AC06: combined installed profile retains products at real failure boundaries."""
from __future__ import annotations

import builtins
import os
import stat

import pytest

from graphify.cache import cache_dir
from tests.qt_combined_adoption_fixture import corpus
from tests.test_qt_combined_adoption import accepted, clean
from tests.test_qt_final_incremental_parity import normalized, run
from tests.test_qt_product_publication import reject, snapshot


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("failure", ["missing_optional_parser", "malformed_qml", "unsafe_import_root"])
def test_req_qml018_ac06_combined_rejection_retains_cache_products_and_retries(tmp_path, monkeypatch, capsys, operation, failure):
    """Actual parser import/syntax or configured-root rejection cannot accept a new graph."""
    app = corpus(tmp_path, "qmake")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    monkeypatch.setenv("GRAPHIFY_QML_IMPORT_ROOTS", '["app/imports"]')
    initial = run(tmp_path, monkeypatch, operation)
    accepted(initial)
    before = snapshot(tmp_path / "graphify-out")
    cache = {path: path.read_bytes() for path in cache_dir(tmp_path).rglob("*") if path.is_file()}
    assert cache
    qml = app / "Main.qml"
    original = qml.read_bytes()
    qml.write_bytes(original + (b"Item {\n" if failure == "malformed_qml" else b"\n// changed\n"))
    with monkeypatch.context() as broken:
        if failure == "missing_optional_parser":
            original_import = builtins.__import__
            def absent(name, *args, **kwargs):
                if name == "tree_sitter_language_pack":
                    raise ModuleNotFoundError("unavailable optional parser")
                return original_import(name, *args, **kwargs)
            broken.setattr(builtins, "__import__", absent)
        elif failure == "unsafe_import_root":
            broken.setenv("GRAPHIFY_QML_IMPORT_ROOTS", '["../outside"]')
        reject(tmp_path, broken, operation, qml)
    assert snapshot(tmp_path / "graphify-out") == before
    assert all(path.exists() and path.read_bytes() == value for path, value in cache.items())
    output = capsys.readouterr().out
    assert ("QML_GRAPH_PRESERVED" if failure != "unsafe_import_root" else "QT_CONFIG") in output
    qml.write_bytes(original)
    recovered = run(tmp_path, monkeypatch, operation, [qml])
    accepted(recovered)
    assert normalized(recovered) == normalized(initial)
    assert normalized(recovered) == normalized(clean(tmp_path, tmp_path / ".retry-cache"))
    completed = snapshot(tmp_path / "graphify-out")
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(recovered)
    assert snapshot(tmp_path / "graphify-out") == completed


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only destination")
@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml018_ac06_combined_readonly_destination_preserves_then_retries(tmp_path, monkeypatch, operation):
    """A real persisted graph failure occurs after successful combined source analysis."""
    app = corpus(tmp_path, "cmake")
    monkeypatch.chdir(app)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    monkeypatch.setenv("GRAPHIFY_QML_IMPORT_ROOTS", '["imports"]')
    initial = run(app, monkeypatch, operation)
    accepted(initial)
    before = snapshot(app / "graphify-out")
    qml = app / "Main.qml"
    qml.write_bytes(qml.read_bytes().replace(b"handleReady", b"received"))
    target = app / "graphify-out/graph.json"
    target.chmod(stat.S_IREAD)
    try:
        reject(app, monkeypatch, operation, qml)
        assert snapshot(app / "graphify-out") == before
    finally:
        target.chmod(stat.S_IWRITE)
    recovered = run(app, monkeypatch, operation, [qml])
    accepted(recovered)
    assert normalized(recovered) != normalized(initial)
    assert normalized(recovered) == normalized(clean(app, app / ".retry-cache"))
    after = snapshot(app / "graphify-out")
    assert normalized(run(app, monkeypatch, operation, [])) == normalized(recovered)
    assert snapshot(app / "graphify-out") == after
