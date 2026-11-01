"""INC-QML-53 review corrections preserve published products and incremental parity."""
from __future__ import annotations

import pytest

from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.qml_resolution_types import qml_metadata
from graphify.watch import _rebuild_code
from tests.test_qt_cmake_mutation_updates import compare_clean, fixture, normalized, published


@pytest.mark.parametrize("mutation", [
    "set_source_files_properties(Main.qml DIRECTORY other PROPERTIES QT_RESOURCE_ALIAS Wrong.qml)\n",
    "set_source_files_properties(Main.qml TARGET_DIRECTORY other PROPERTIES QT_RESOURCE_ALIAS Wrong.qml)\n",
    "qt_add_resources(app empty PREFIX /empty FILES Main.qml DISCARD_FILE_CONTENTS)\n",
], ids=["directory_scope", "target_directory_scope", "discard_contents"])
@pytest.mark.parametrize("force", [False, True])
def test_req_qml012_ac02_review_rejection_preserves_products_and_recovery_repeats(tmp_path, mutation, force):
    """Unsupported reviewed forms retain graph, manifest, report and accepted Qt policy.

    Repair the same file without deleting persisted data; the recovered/repeated
    graph must agree with both the prior valid facts and an independent full scan.
    """
    build = fixture(tmp_path)
    original = build.read_bytes()
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    baseline = normalized(published(tmp_path))
    out = tmp_path / "graphify-out"
    (out / "report.md").write_text("Previously accepted public report\n", encoding="utf-8")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    # Place the candidate before metadata use: otherwise the older late-property
    # guard could reject it and conceal the missing scope/empty-resource guard.
    build.write_bytes(mutation.encode() + original)
    assert not _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False, force=force)
    assert {name: (out / name).read_bytes() for name in names} == prior
    build.write_bytes(original)
    assert _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == baseline
    assert _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == baseline
    compare_clean(tmp_path)


def test_req_qml011_ac02_metadata_collision_update_removes_stale_edge_and_recovers(tmp_path):
    """An alias-only change creates/removes ambiguity for unchanged QML inputs."""
    source = ("qt_add_qml_module(app URI Public.Tools RESOURCE_PREFIX /ui "
              "NO_RESOURCE_TARGET_PATH QML_FILES Main.qml)\n"
              "qt_add_resources(app extras PREFIX /ui FILES Other.qml)\n")
    build = tmp_path / "CMakeLists.txt"
    build.write_text(source, encoding="utf-8")
    (tmp_path / "Main.qml").write_text("Item { property int primary: 1 }\n", encoding="utf-8")
    (tmp_path / "Other.qml").write_text("Item { property int secondary: 2 }\n", encoding="utf-8")
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    baseline = normalized(published(tmp_path))
    assert any(edge.get("context") == "qt_resource_membership"
               for _, _, edge in published(tmp_path).edges(data=True))
    build.write_text("set_source_files_properties(Other.qml PROPERTIES QT_RESOURCE_ALIAS Main.qml)\n"
                     + source, encoding="utf-8")
    assert _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False)
    graph = published(tmp_path)
    sites = [qml_metadata(node) for _, node in graph.nodes(data=True)
             if qml_metadata(node).get("kind") == "membership_resolution"
             and qml_metadata(node).get("declaration_kind") == "resource_alias"]
    assert len(sites) == 1 and sites[0]["status"] == "ambiguous" and not sites[0]["target_id"]
    assert not any(edge.get("context") == "qt_resource_membership" for _, _, edge in graph.edges(data=True))
    compare_clean(tmp_path)
    assert _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == normalized(graph)
    build.write_text(source, encoding="utf-8")
    assert _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == baseline
    compare_clean(tmp_path)
