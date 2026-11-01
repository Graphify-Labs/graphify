"""INC-QML-100: legacy empty metadata is absence, never typed storage authority."""
from __future__ import annotations

import copy

import networkx as nx
import pytest

from graphify.build import build, build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.paths import load_node_link_graph
from graphify.source_relationships import FIELD, is_source_graph


def legacy(metadata, directed):
    """Complete accepted legacy fields avoid unrelated default-filling mutations."""
    return {"nodes": [{"id": name, "label": name.title(), "type": "function", "file_type": "code",
                       "source_file": "keep.py", "source_location": f"L{line}", "_origin": "ast"}
                      for name, line in (("one", 1), ("two", 2))],
            "edges": [{"source": "one", "target": "two", "relation": "calls", "confidence": "EXTRACTED",
                       "source_file": "keep.py", "source_location": "L3"}],
            "graph": metadata, "directed": directed, "multigraph": False}


def typed(root, directed=False):
    """Real source producers supply two separately owned local-function promises."""
    path = root / "Data.cs"
    path.write_bytes(b"class Holder{void Use(){void First(){}First();void Second(){}Second();}}")
    result = extract([path], root=root, cache_root=root, parallel=False)
    assert not result.get("failed_sources")
    return {"nodes": result["nodes"], "edges": result["edges"], "directed": directed, "multigraph": True}


def adopt(data, boundary, root, directed=False):
    """Exercise each public owner instead of repeating the selection algorithm."""
    if boundary == "direct":
        return build_from_json(data, directed=directed, root=root)
    if boundary == "combined":
        return build([data], directed=directed, root=root, dedup=False)
    return load_node_link_graph(data)


@pytest.mark.parametrize("metadata", [None, False, 0, [], ""], ids=["null", "false", "zero", "list", "string"])
@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("boundary", ["direct", "combined", "reload"])
def test_req_qml022_ac06_nonempty_legacy_empty_carrier_preserves_graph_facts_and_input(tmp_path, boundary, directed, metadata):
    """All old falsy carriers retain nonempty Graph/DiGraph storage and source evidence."""
    data = legacy(metadata, directed)
    before = copy.deepcopy(data)
    graph = adopt(data, boundary, tmp_path, directed)
    assert type(graph) is (nx.DiGraph if directed else nx.Graph)
    assert FIELD not in graph.graph and data == before
    assert set(graph) == {"one", "two"} and graph.number_of_edges() == 1
    edge = graph.get_edge_data("one", "two")
    assert edge and (edge["relation"], edge["confidence"], edge["source_file"], edge["source_location"]) == (
        "calls", "EXTRACTED", "keep.py", "L3")


@pytest.mark.parametrize("metadata", [False, 0, [], ""], ids=["false", "zero", "list", "string"])
@pytest.mark.parametrize("boundary", ["direct", "combined", "reload"])
def test_req_qml022_ac06_typed_source_cannot_hide_invalid_carrier_as_legacy_absence(tmp_path, boundary, metadata):
    """A real typed producer promise keeps the stronger metadata carrier contract."""
    data = typed(tmp_path)
    data["graph"] = metadata
    before = copy.deepcopy(data)
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID"):
        adopt(data, boundary, tmp_path)
    assert data == before


@pytest.mark.parametrize("carrier", ["missing", "null"])
@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("boundary", ["direct", "combined", "reload"])
def test_req_qml022_ac06_missing_or_null_typed_metadata_still_selects_source_storage(tmp_path, boundary, directed, carrier):
    """The legacy allowance does not remove raw typed producer autoactivation."""
    data = typed(tmp_path, directed)
    if carrier == "null":
        data["graph"] = None
    before = copy.deepcopy(data)
    graph = adopt(data, boundary, tmp_path, directed)
    assert is_source_graph(graph) and graph.is_directed() is directed and data == before
    locals_ = {identity for identity, node in graph.nodes(data=True) if "csharp_local_function" in node.get("metadata", {})}
    assert len(locals_) == 2
    for identity in locals_:
        assert {edge["relation"] for _, _, edge in graph.edges(data=True) if edge["_tgt"] == identity} == {"contains", "calls"}


@pytest.mark.parametrize("boundary", ["direct", "combined", "reload"])
@pytest.mark.parametrize("damage", ["role", "span"])
def test_req_qml022_ac06_valid_typed_peer_cannot_mask_later_malformed_promise(tmp_path, boundary, damage):
    """Every actual typed fact is validated even after its first peer activates storage."""
    data = typed(tmp_path)
    first, second = [node for node in data["nodes"] if "csharp_local_function" in node.get("metadata", {})]
    assert first["metadata"]["csharp_local_function"]["role"] == "definition"
    fact = second["metadata"]["csharp_local_function"]
    if damage == "role":
        fact["role"] = []
    else:
        fact["span"]["start_byte"] = True
    before = copy.deepcopy(data)
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID"):
        adopt(data, boundary, tmp_path)
    assert data == before


@pytest.mark.parametrize("metadata", [True, 1, ["unsupported"], "unsupported"])
@pytest.mark.parametrize("boundary", ["direct", "combined", "reload"])
def test_req_qml022_ac06_nonempty_invalid_carrier_remains_controlled_rejection(tmp_path, boundary, metadata):
    """Falsy absence does not broaden the existing nonempty carrier rejection."""
    data = legacy(metadata, False)
    before = copy.deepcopy(data)
    with pytest.raises(ValueError, match="_INVALID"):
        adopt(data, boundary, tmp_path)
    assert data == before


@pytest.mark.parametrize("marker", [None, False, [], {}, {"contract_version": True}, {"contract_version": 1, "extra": 0}])
@pytest.mark.parametrize("boundary", ["direct", "combined", "reload"])
def test_req_qml022_ac06_invalid_reserved_profile_remains_rejected(tmp_path, boundary, marker):
    """An explicit reserved dictionary promise cannot be repaired as legacy absence."""
    data = legacy({FIELD: marker}, False)
    before = copy.deepcopy(data)
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID"):
        adopt(data, boundary, tmp_path)
    assert data == before


@pytest.mark.parametrize("boundary", ["direct", "combined", "reload"])
def test_req_qml022_ac06_rejected_typed_carrier_retains_json_then_recovers_and_repeats(tmp_path, boundary):
    """A failed public adoption cannot reach the real writer or replace its accepted graph."""
    original = typed(tmp_path)
    output = tmp_path / "graph.json"
    assert to_json(adopt(copy.deepcopy(original), boundary, tmp_path), {}, str(output), force=True)
    accepted = output.read_bytes()
    bad = copy.deepcopy(original)
    bad["graph"] = False
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID"):
        adopt(bad, boundary, tmp_path)
    assert output.read_bytes() == accepted
    for _ in range(2):
        graph = adopt(copy.deepcopy(original), boundary, tmp_path)
        assert to_json(graph, {}, str(output), force=True)
        assert output.read_bytes() == accepted
