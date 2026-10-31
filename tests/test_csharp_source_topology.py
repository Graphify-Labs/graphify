"""INC-QML-89 source relationships and derived topology are separate views."""
from __future__ import annotations

import json

import pytest

from graphify.analyze import graph_diff, surprising_connections
from graphify.build import add_source_relationship, build_from_json
from graphify.cluster import cohesion_score
from graphify.cross_repo_calls import CROSS_REPO_CALL_MARKER, _drop_previous_output
from graphify.export import to_json
from graphify.paths import load_node_link_graph
from graphify.source_relationships import FIELD, is_source_graph, make_source_graph


def graph():
    result = make_source_graph(graph_metadata={FIELD: {"contract_version": 1}})
    assert is_source_graph(result)
    result.add_nodes_from([("first", {"label": "First"}), ("second", {"label": "Second"})])
    for source, target, relation in [("first", "second", "contains"), ("first", "second", "calls"), ("second", "first", "calls")]:
        add_source_relationship(result, source, target, {"relation": relation, "confidence": "EXTRACTED"})
    return result


def test_req_qml022_ac06_source_relationship_metrics_use_explicit_topology():
    """Parallel mechanisms don't inflate pair cohesion or crash topology centrality."""
    source = graph()
    assert cohesion_score(source, list(source)) == 1.0
    result = surprising_connections(source, {}, top_n=5)
    assert len(result) == 1 and result[0]["note"].startswith("Bridges graph structure")
    assert source.number_of_edges() == 3


def test_req_qml022_ac06_diff_distinguishes_opposite_source_arcs():
    """Deleting just the reverse call reports that one logical relationship."""
    old, new = graph(), graph()
    key = next(key for _, _, key, data in new.edges(keys=True, data=True) if data["_src"] == "second")
    new.remove_edge("first", "second", key)
    result = graph_diff(old, new)
    assert result["new_edges"] == []
    assert [(edge["source"], edge["target"], edge["relation"]) for edge in result["removed_edges"]] == [("second", "first", "calls")]


def test_req_qml022_ac06_keyed_stale_cleanup_preserves_parallel_source_relationships():
    """Cross-repository cleanup removes its tagged relationship, never a peer."""
    source = graph()
    next(data for _, _, data in source.edges(data=True) if data["_src"] == "first" and data["relation"] == "calls")[CROSS_REPO_CALL_MARKER] = True
    _drop_previous_output(source)
    assert {(d["_src"], d["_tgt"], d["relation"]) for _, _, d in source.edges(data=True)} == {
        ("first", "second", "contains"), ("second", "first", "calls")}


@pytest.mark.parametrize("damage", ["marker", "direction", "simple"])
def test_req_qml022_ac06_corrupt_persisted_profile_rejects_adoption_and_preserves_file(tmp_path, damage):
    """Corruption cannot be repaired into source authority during load or publication."""
    path = tmp_path / "graph.json"
    assert to_json(graph(), {}, str(path), force=True)
    before = path.read_bytes()
    data = json.loads(before)
    if damage == "marker":
        data["graph"][FIELD]["contract_version"] = True
    elif damage == "simple":
        data["multigraph"] = False
    else:
        data["links"][0]["_src"] = "foreign"
    with pytest.raises(ValueError):
        load_node_link_graph(data)
    assert path.read_bytes() == before


def test_req_qml022_ac06_rebuild_saved_profile_without_typed_nodes_retains_arcs(tmp_path):
    """A storage marker isn't callability; it keeps already accepted nonlocal arcs distinct."""
    path = tmp_path / "graph.json"
    assert to_json(graph(), {}, str(path), force=True)
    rebuilt = build_from_json(json.loads(path.read_text()))
    assert rebuilt.number_of_edges() == 3 and rebuilt.is_multigraph()
