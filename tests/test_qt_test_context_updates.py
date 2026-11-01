"""INC-QML-78: admitted include context participates in real retained updates."""
from __future__ import annotations

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.watch import _rebuild_code
from tests.test_qt_cmake_mutation_updates import compare_clean, normalized, published
from tests.test_qt_test_include_context import FILES, write_project


def _data(root):
    return {identity: qt_metadata(node) for identity, node in published(root).nodes(data=True)
            if qt_metadata(node).get("kind") == "test_data"}


def test_req_qml022_ac06_forward_context_cold_warm_header_change_matches_clean(tmp_path):
    """A header-only witness change invalidates unchanged typed consumers before cache reuse."""
    write_project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    original = _data(tmp_path)
    assert len(original) == 1
    before = normalized(published(tmp_path))
    header = tmp_path / "framework.hpp"
    assert _rebuild_code(tmp_path, changed_paths=[header], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == before
    header.write_bytes(b"// UTF-8: caf\xc3\xa9 \xe9\x9b\xaa\r\n" + FILES["framework.hpp"].encode())
    assert _rebuild_code(tmp_path, changed_paths=[header], no_cluster=True, acquire_lock=False)
    assert _data(tmp_path) != original
    compare_clean(tmp_path)
    consumer = tmp_path / "checks.hpp"
    consumer.write_bytes(FILES["checks.hpp"].replace("QFETCH(int,state);", "int state;").encode())
    assert _rebuild_code(tmp_path, changed_paths=[consumer], no_cluster=True, acquire_lock=False)
    assert not _data(tmp_path)
    compare_clean(tmp_path)


@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_unavailable_header_context_retains_graph_then_recovers(tmp_path, force):
    """Removing source context cannot replace a valid graph with a missing native body."""
    write_project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    assert _data(tmp_path)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted source-context report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    header = tmp_path / "framework.hpp"
    header.write_bytes(b"// framework context removed\n")
    for _ in range(2):
        assert not _rebuild_code(tmp_path, changed_paths=[header], no_cluster=True, acquire_lock=False, force=force)
        assert {name: (out / name).read_bytes() for name in names} == prior
    header.write_bytes(FILES["framework.hpp"].encode())
    assert _rebuild_code(tmp_path, changed_paths=[header], no_cluster=True, acquire_lock=False)
    assert _data(tmp_path)
    compare_clean(tmp_path)
    accepted = (out / "graph.json").read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[header], no_cluster=True, acquire_lock=False)
    assert (out / "graph.json").read_bytes() == accepted


@pytest.mark.parametrize("stage", ["before_collectors", "after_exposure"])
def test_req_qml022_ac06_real_header_mutation_between_producers_rejects_same_snapshot(tmp_path, monkeypatch, stage):
    """A real stale witness at the final collector checkpoint rejects publication and recovers."""
    import graphify.qt_qml_pipeline as pipeline
    import graphify.extractors.qt_cpp_exposure as exposure
    write_project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted coherent snapshot\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    header, original = tmp_path / "framework.hpp", pipeline.resolve_qt_qml
    diagnostics, overlays = [], []

    def change_then_resolve(paths, per_file, *args, **kwargs):
        # This seam changes actual admitted bytes at a real producer boundary;
        # the production verifier and diagnostic path remain authoritative.
        if stage == "before_collectors":
            header.write_bytes(header.read_bytes() + b"// concurrent edit\n")
        answer = original(paths, per_file, *args, **kwargs)
        diagnostics.extend(item for result in per_file for item in result.get("diagnostics", []))
        overlays.extend(node for node in args[0] if qt_metadata(node))
        return answer

    original_exposure = exposure.enrich_qt_cpp

    def collect_then_change(*args, **kwargs):
        answer = original_exposure(*args, **kwargs)
        header.write_bytes(header.read_bytes() + b"// edit after exposure\n")
        return answer

    with monkeypatch.context() as scope:
        scope.setattr(pipeline, "resolve_qt_qml", change_then_resolve)
        if stage == "after_exposure":
            scope.setattr(exposure, "enrich_qt_cpp", collect_then_change)
        assert not _rebuild_code(tmp_path, changed_paths=[header], no_cluster=True, acquire_lock=False)
    assert {name: (out / name).read_bytes() for name in names} == prior
    assert any(item["code"] == "QT_CPP_CONTEXT" and item["owner"] == "cpp_test_context"
               and item["severity"] == "error" for item in diagnostics)
    assert not overlays
    assert _rebuild_code(tmp_path, changed_paths=[header], no_cluster=True, acquire_lock=False)
    compare_clean(tmp_path)
