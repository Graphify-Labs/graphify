"""INC-QML-64: enum source edits obey real cache/publication recovery boundaries."""
from __future__ import annotations

import pytest

from graphify.build import build_from_json
from graphify.extract import collect_files, extract
from graphify.extractors.qml_facts import qml_metadata
from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.watch import _rebuild_code
from tests.test_qt_cmake_mutation_updates import compare_clean, normalized, published


def _project(root):
    """Independent consumer and provider make unchanged-source invalidation visible."""
    provider = root / "State.qml"
    provider.write_bytes(b"QtObject { enum Mode { Ready = 4, Waiting } }\n")
    (root / "Main.qml").write_bytes(b"QtObject { property int chosen: State.Mode.Ready }\n")
    return provider


def _value_read(graph):
    return [(nid, qml_metadata(node)) for nid, node in graph.nodes(data=True)
            if qml_metadata(node).get("kind") == "read"
            and qml_metadata(node).get("raw_name") == "State.Mode.Ready"][0]


def test_req_qml022_ac06_enum_cold_warm_incremental_removal_and_clean_parity(tmp_path):
    """Provider-only changes update values/stale endpoints while preserving stable IDs."""
    provider = _project(tmp_path)
    paths = collect_files(tmp_path, root=tmp_path)
    cold = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    warm = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert normalized(build_from_json(cold, root=tmp_path)) == normalized(build_from_json(warm, root=tmp_path))
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    graph = published(tmp_path)
    site_id, read = _value_read(graph)
    value_id = read["resolved_target_id"]
    assert qml_metadata(graph.nodes[value_id])["value"] == 4
    provider.write_bytes(provider.read_bytes().replace(b"Ready = 4", b"Ready = 8"))
    assert _rebuild_code(tmp_path, changed_paths=[provider], no_cluster=True, acquire_lock=False)
    changed = published(tmp_path)
    assert _value_read(changed)[1]["resolved_target_id"] == value_id
    assert qml_metadata(changed.nodes[value_id])["value"] == 8
    compare_clean(tmp_path)
    provider.write_bytes(b"QtObject { enum Mode { Waiting = 5 } }\n")
    assert _rebuild_code(tmp_path, changed_paths=[provider], no_cluster=True, acquire_lock=False)
    removed = published(tmp_path)
    assert value_id not in removed
    assert _value_read(removed)[1]["status"] != "resolved"
    assert not removed.has_edge(site_id, value_id)
    compare_clean(tmp_path)
    accepted = normalized(removed)
    assert _rebuild_code(tmp_path, changed_paths=[provider], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == accepted


@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_enum_rejection_retains_products_then_recovers(tmp_path, force):
    """An incomplete enum source preserves committed products; repair/repeat stay safe."""
    provider = _project(tmp_path)
    accepted_source = provider.read_bytes()
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    before = {name: (out / name).read_bytes() for name in names}
    provider.write_bytes(b"QtObject { enum Mode { Ready = ")
    for _ in range(2):
        assert not _rebuild_code(tmp_path, changed_paths=[provider], no_cluster=True,
                                 acquire_lock=False, force=force)
        assert {name: (out / name).read_bytes() for name in names} == before
    provider.write_bytes(accepted_source)
    assert _rebuild_code(tmp_path, changed_paths=[provider], no_cluster=True, acquire_lock=False)
    compare_clean(tmp_path)
    restored = (out / "graph.json").read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[provider], no_cluster=True, acquire_lock=False)
    assert (out / "graph.json").read_bytes() == restored
