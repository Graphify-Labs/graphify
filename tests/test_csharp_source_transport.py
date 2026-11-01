"""INC-QML-89 rejects corrupt typed transport before graph-library coercion."""
from __future__ import annotations

import json

import pytest

from graphify.export import to_json
from graphify.build import build_from_json
from graphify.paths import load_node_link_graph
from tests.test_csharp_source_topology import graph


@pytest.mark.parametrize("entry", ["load", "build"])
@pytest.mark.parametrize("damage", ["directed_string", "multigraph_string", "missing_target",
    "list_endpoint", "null_edge", "list_edge", "list_relation", "dict_relation", "empty_relation",
    "links_mapping", "coercing_ids", "duplicate_ids", "missing_node", "nodes_mapping", "nodes_null", "conflicting_aliases"])
def test_req_qml022_ac06_corrupt_source_transport_is_controlled_and_retains_publication(tmp_path, damage, entry):
    """Exact-profile input rejects malformed shapes/types before NetworkX can repair them."""
    path = tmp_path / "graph.json"
    assert to_json(graph(), {}, str(path), force=True)
    before = path.read_bytes()
    data = json.loads(before)
    edge = data["links"][0]
    if damage.endswith("_string"):
        data[damage.removesuffix("_string")] = "false"
    elif damage == "missing_target":
        del edge["target"]
    elif damage == "list_endpoint":
        edge["source"] = []
    elif damage in {"null_edge", "list_edge"}:
        data["links"][0] = None if damage == "null_edge" else []
    elif damage.endswith("_relation"):
        edge["relation"] = {"list_relation": [], "dict_relation": {}, "empty_relation": ""}[damage]
    elif damage == "links_mapping":
        data["links"] = {}
    elif damage == "coercing_ids":
        data["nodes"].extend([{"id": 1}, {"id": True}])
    elif damage == "duplicate_ids":
        data["nodes"].append(dict(data["nodes"][0]))
    elif damage == "missing_node":
        edge["source"] = "not-declared"
    elif damage == "conflicting_aliases":
        data["edges"] = []
    else:
        data["nodes"] = None if damage == "nodes_null" else {}
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID"):
        load_node_link_graph(data) if entry == "load" else build_from_json(data)
    assert path.read_bytes() == before


@pytest.mark.parametrize("entry", ["load", "build"])
def test_req_qml022_ac06_accepted_reverse_markers_survive_adoption_and_rebuild(tmp_path, entry):
    """Canonicalized undirected transport preserves accepted logical direction at both APIs."""
    path = tmp_path / "graph.json"
    assert to_json(graph(), {}, str(path), force=True)
    data = json.loads(path.read_text())
    expected = {(edge["source"], edge["target"], edge["relation"]) for edge in data["links"]}
    for edge in data["links"]:
        source, target = edge["source"], edge["target"]
        edge.update(source=target, target=source, _src=source, _tgt=target)
    data["edges"] = [dict(edge) for edge in data["links"]]
    accepted = load_node_link_graph(data) if entry == "load" else build_from_json(data)
    assert {(edge["_src"], edge["_tgt"], edge["relation"]) for _, _, edge in accepted.edges(data=True)} == expected
