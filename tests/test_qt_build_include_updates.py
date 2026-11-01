"""INC-QML-93: real metadata refresh, coherent checkpoints and durable retention."""
from __future__ import annotations

import os
import stat

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.watch import _rebuild_code
from tests.test_qt_build_include_context import CMAKE, project
from tests.test_qt_cmake_mutation_updates import compare_clean, normalized, published


def fixture(root):
    paths = project(root)
    # Source-context changes must not be confused with unrelated shrink guards.
    (root / "retained.py").write_text("\n".join(f"def retained_{i}(): return {i}" for i in range(40)), encoding="utf-8")
    return paths


def records(root):
    return {identity: qt_metadata(node) for identity, node in published(root).nodes(data=True)
            if qt_metadata(node).get("kind") in {"test_data", "test_assertion", "test_launcher"}}


def retained(root):
    out = root / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted build context report\n")
    return {name: (out / name).read_bytes() for name in ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)}


def assert_retained(root, prior):
    assert {name: (root / "graphify-out" / name).read_bytes() for name in prior} == prior


def test_req_qml022_ac06_metadata_only_root_retarget_refreshes_stable_source_facts(tmp_path):
    """Unchanged native consumers receive new root proof and match clean extraction after warm updates."""
    paths = fixture(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    before = records(tmp_path)
    assert len(before) == 3
    graph_before = normalized(published(tmp_path))
    assert _rebuild_code(tmp_path, changed_paths=[paths[2]], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == graph_before
    alternate = tmp_path / "alternate/api.h"
    alternate.parent.mkdir()
    alternate.write_bytes(b"struct Alternate{};\n")
    paths[2].write_bytes(CMAKE.replace("../src", "../alternate").encode())
    assert _rebuild_code(tmp_path, changed_paths=[paths[2], alternate], no_cluster=True, acquire_lock=False)
    after = records(tmp_path)
    assert set(after) == set(before) and after != before
    assert all(row["build_include_witnesses"][0]["header_file"] == "alternate/api.h" for row in after.values())
    compare_clean(tmp_path)
    paths[2].write_bytes(CMAKE.encode())
    assert _rebuild_code(tmp_path, changed_paths=[paths[2]], no_cluster=True, acquire_lock=False)
    assert records(tmp_path) == before
    compare_clean(tmp_path)


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("mutation", ["interface", "unknown_target"])
def test_req_qml022_ac06_removed_root_retains_prior_products_then_recovers(tmp_path, force, mutation):
    """Unsupported metadata cannot publish partial macro facts even after repeated force requests."""
    paths = fixture(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    prior = retained(tmp_path)
    changed = (CMAKE.replace("PRIVATE", "INTERFACE") if mutation == "interface" else
               CMAKE + "target_include_directories(${WHICH} PRIVATE ../other)\n")
    paths[2].write_bytes(changed.encode())
    for _ in range(2):
        assert not _rebuild_code(tmp_path, changed_paths=[paths[2]], no_cluster=True, acquire_lock=False, force=force)
        assert_retained(tmp_path, prior)
    paths[2].write_bytes(CMAKE.encode())
    assert _rebuild_code(tmp_path, changed_paths=[paths[2]], no_cluster=True, acquire_lock=False)
    assert len(records(tmp_path)) == 3
    compare_clean(tmp_path)
    saved = (tmp_path / "graphify-out/graph.json").read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[paths[2]], no_cluster=True, acquire_lock=False)
    assert (tmp_path / "graphify-out/graph.json").read_bytes() == saved


@pytest.mark.parametrize("mutation", ["metadata", "local_shadow", "other_root_shadow"])
def test_req_qml022_ac06_actual_context_dependency_mutation_after_collection_rejects_and_recovers(tmp_path, monkeypatch, mutation):
    """Actual filesystem changes after exposure are caught before scratch adoption, with exact products retained."""
    import graphify.extractors.qt_cpp_exposure as exposure
    import graphify.qt_qml_pipeline as pipeline
    paths = fixture(tmp_path)
    if mutation == "other_root_shadow":
        paths[2].write_bytes(CMAKE.replace("../src", "../src ../other").encode())
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    prior, diagnostics, overlays = retained(tmp_path), [], []
    original, original_resolve = exposure.enrich_qt_cpp, pipeline.resolve_qt_qml
    created = tmp_path / ("other/api.h" if mutation == "other_root_shadow" else "tests/api.h")

    def collect_then_change(*args, **kwargs):
        answer = original(*args, **kwargs)
        if mutation == "metadata":
            paths[2].write_bytes(paths[2].read_bytes() + b"# concurrent metadata edit\n")
        else:
            created.parent.mkdir(parents=True, exist_ok=True)
            created.write_bytes(b"struct NewShadow{};\n")
        return answer

    def observe(paths, per_file, *args, **kwargs):
        answer = original_resolve(paths, per_file, *args, **kwargs)
        diagnostics.extend(item for result in per_file for item in result.get("diagnostics", []))
        overlays.extend(node for node in args[0] if qt_metadata(node))
        return answer

    with monkeypatch.context() as guard:
        guard.setattr(exposure, "enrich_qt_cpp", collect_then_change)
        guard.setattr(pipeline, "resolve_qt_qml", observe)
        assert not _rebuild_code(tmp_path, changed_paths=[paths[2]], no_cluster=True, acquire_lock=False)
    assert_retained(tmp_path, prior)
    assert not overlays
    assert any(item["code"] == "QT_CPP_CONTEXT" and item["owner"] == "cpp_test_context" for item in diagnostics)
    if mutation != "metadata":
        created.unlink()
    assert _rebuild_code(tmp_path, changed_paths=[paths[2]], no_cluster=True, acquire_lock=False)
    compare_clean(tmp_path)


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only replacement boundary")
def test_req_qml022_ac06_valid_build_context_write_failure_retains_and_retries(tmp_path):
    """An actual durable replacement failure cannot publish new proof ahead of graph/cache ownership."""
    paths = fixture(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    prior = retained(tmp_path)
    paths[2].write_bytes(b"# valid changed metadata\n" + CMAKE.encode())
    graph = tmp_path / "graphify-out/graph.json"
    mode = graph.stat().st_mode
    os.chmod(graph, stat.S_IREAD)
    try:
        for _ in range(2):
            assert not _rebuild_code(tmp_path, changed_paths=[paths[2]], no_cluster=True, acquire_lock=False)
            assert_retained(tmp_path, prior)
        assert not list(graph.parent.glob(".gfy-*.tmp"))
    finally:
        os.chmod(graph, mode)
    assert _rebuild_code(tmp_path, changed_paths=[paths[2]], no_cluster=True, acquire_lock=False)
    compare_clean(tmp_path)
