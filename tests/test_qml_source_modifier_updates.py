"""INC-QML-66: modified declarations retain actual update/persistence safety."""
from __future__ import annotations

import pytest

from graphify.extractors.qml_facts import qml_metadata
from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.watch import _rebuild_code
from tests.test_qt_cmake_mutation_updates import compare_clean, normalized, published


def _project(root):
    """An unchanged derived file must observe source-provider edits through cache."""
    path = root / "Base.qml"
    path.write_bytes(b"QtObject { virtual property int amount: 1 }\n")
    (root / "Main.qml").write_bytes(b"Base { property int shown: amount }\n")
    return path


def test_req_qml022_ac06_source_modifier_updates_match_clean_and_remove_stale_endpoints(tmp_path):
    """Modifier-only changes retain identities; removed source declarations lose edges."""
    path = _project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    graph = published(tmp_path)
    before = normalized(graph)
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == before
    node_id = [nid for nid, node in graph.nodes(data=True)
               if qml_metadata(node).get("kind") == "property" and node.get("source_file") == "Base.qml"][0]
    path.write_bytes(path.read_bytes().replace(b"virtual", b"final"))
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    graph = published(tmp_path)
    assert qml_metadata(graph.nodes[node_id])["modifiers"] == ["final"]
    compare_clean(tmp_path)
    path.write_bytes(path.read_bytes().replace(b"amount", b"size"))
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    graph = published(tmp_path)
    assert node_id not in graph
    reads = [qml_metadata(node) for _, node in graph.nodes(data=True) if qml_metadata(node).get("kind") == "read"]
    assert reads and all(md["status"] != "resolved" for md in reads)
    compare_clean(tmp_path)


@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_invalid_modifier_combination_retains_products_then_recovers(tmp_path, force):
    """Rejected compatibility inputs preserve committed products, then repair repeats."""
    path = _project(tmp_path)
    source = path.read_bytes()
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted modifier report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    path.write_bytes(source.replace(b"virtual property", b"virtual final property"))
    for _ in range(2):
        assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True,
                                 acquire_lock=False, force=force)
        assert {name: (out / name).read_bytes() for name in names} == prior
    path.write_bytes(source)
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    compare_clean(tmp_path)
    accepted = (out / "graph.json").read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert (out / "graph.json").read_bytes() == accepted
