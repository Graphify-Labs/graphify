"""INC129: accepted link adoption preserves ordinary legacy field absence."""
from __future__ import annotations

from copy import deepcopy

import networkx as nx
import pytest

from graphify.build import build, build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.paths import load_node_link_graph
from graphify.source_relationships import FIELD, is_source_graph
from tests.source_relationship_projection_helpers import arcs, readback, storage


def ordinary(value=None, directed=False):
    """Match the unchanged installed legacy100 fixture without invoking its environment."""
    return {"nodes": [{"id": name, "label": name.title(), "type": "function", "file_type": "code",
                       "source_file": "keep.py", "source_location": f"L{line}", "_origin": "ast"}
                      for name, line in (("one", 1), ("two", 2))],
            "edges": [{"source": "one", "target": "two", "relation": "calls", "confidence": "EXTRACTED",
                       "source_file": "keep.py", "source_location": "L3"}],
            "graph": deepcopy(value), "directed": directed, "multigraph": False}


def consume(data, boundary, root, directed=False):
    if boundary == "direct":
        return build_from_json(data, root=root, directed=directed)
    if boundary == "combined":
        return build([data], root=root, directed=directed, dedup=False)
    return load_node_link_graph(data)


def typed(root):
    """Actual C# source facts, rather than a fabricated activation marker, own this profile."""
    path = root / "Data.cs"
    path.write_bytes(b"class Store{void Use(){void Local(){}Local();}}")
    result = extract([path], root=root, cache_root=root, parallel=False)
    assert not result.get("failed_sources") and not result.get("error")
    assert any(node.get("metadata", {}).get("csharp_local_function") for node in result["nodes"])
    return result, path


@pytest.mark.parametrize("value", [None, False, 0, [], ""], ids=["null", "false", "zero", "empty-list", "empty-text"])
@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
@pytest.mark.parametrize("boundary", ["direct", "combined", "reload"], ids=["direct", "combined", "reload"])
def test_req_qml022_ac06_legacy100_falsy_graph_keeps_input_exact(tmp_path, value, directed, boundary):
    """The historical conjunction fails only at input equality; ordinary graph shape remains valid."""
    data = ordinary(value, directed)
    before = deepcopy(data)
    held, record = data["edges"], data["edges"][0]
    graph = consume(data, boundary, tmp_path, directed)
    assert type(graph) is (nx.DiGraph if directed else nx.Graph)
    assert len(graph) == 2 and graph.number_of_edges() == 1 and FIELD not in graph.graph
    assert data["edges"] is held and held[0] is record
    assert data == before


@pytest.mark.parametrize("value", [False, 0, [], ""], ids=["false", "zero", "empty-list", "empty-text"])
@pytest.mark.parametrize("boundary", ["direct", "combined", "reload"], ids=["direct", "combined", "reload"])
def test_req_qml022_ac06_legacy100_typed_falsy_graph_rejects_without_mutation(tmp_path, value, boundary):
    """A genuine activating producer cannot treat an invalid falsy graph carrier as absence."""
    produced, path = typed(tmp_path)
    original = deepcopy(produced)
    data = deepcopy(produced)
    data["graph"] = value
    before = deepcopy(data)
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID"):
        consume(data, boundary, tmp_path)
    assert data == before and produced == original
    assert extract([path], root=tmp_path, cache_root=tmp_path, parallel=False) == original


@pytest.mark.parametrize("carrier", ["missing", "null"], ids=["missing", "null"])
@pytest.mark.parametrize("boundary", ["direct", "combined", "reload"], ids=["direct", "combined", "reload"])
def test_req_qml022_ac06_legacy100_typed_absence_still_adopts(tmp_path, carrier, boundary):
    """Optional storage activation still follows unchanged real source-only producer facts."""
    produced, path = typed(tmp_path)
    original = deepcopy(produced)
    data = deepcopy(produced)
    data.update(directed=False, multigraph=True)
    if carrier == "null":
        data["graph"] = None
    graph = consume(data, boundary, tmp_path)
    assert is_source_graph(graph)
    assert {edge["relation"] for _, _, edge in graph.edges(data=True)} >= {"calls", "contains"}
    assert produced == original
    assert extract([path], root=tmp_path, cache_root=tmp_path, parallel=False) == original


@pytest.mark.parametrize("boundary", ["direct", "combined"], ids=["direct", "combined"])
@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
def test_req_qml010_ac02_legacy_source_field_absence_is_not_backfilled_in_input(tmp_path, boundary, directed):
    """Graph provenance may be derived from nodes without inserting it into an unpromised caller record."""
    data = ordinary(directed=directed)
    data["edges"][0].pop("source_file")
    before = deepcopy(data)
    graph = consume(data, boundary, tmp_path, directed)
    edge, = [edge for _, _, edge in graph.edges(data=True)]
    assert edge["source_file"] == "keep.py"
    assert data == before
    output = tmp_path / "absent.json"
    assert to_json(graph, {}, str(output), original_links=data["edges"])
    _, payload = readback(output)
    assert "source_file" not in payload["links"][0]


@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
def test_req_qml010_ac02_present_numeric_repairs_and_unknown_fields_survive(tmp_path, directed):
    """Actual supplied numeric fields normalize; unrelated attributes and absent fields keep their authority."""
    data = ordinary(directed=directed)
    held, record = data["edges"], data["edges"][0]
    record.update(weight="0.5", confidence_score="0.37", custom={"values": [1, {"literal": "kept"}]})
    expected = deepcopy(record)
    expected.update(weight=0.5, confidence_score=0.37)
    graph = consume(data, "direct", tmp_path, directed)
    assert data["edges"] is held and held[0] is record and record == expected
    edge, = [edge for _, _, edge in graph.edges(data=True)]
    assert edge["weight"] == 0.5 and edge["confidence_score"] == 0.37
    assert edge["custom"] == expected["custom"]


@pytest.mark.parametrize("directed,reverse", [(False, False), (False, True), (True, False)],
                         ids=["undirected-forward", "undirected-reverse", "directed-forward"])
def test_req_qml010_ac02_explicit_valid_legacy_direction_stays_explicit(tmp_path, directed, reverse):
    """Accepted explicit orientation remains the supported raw export view, without field synthesis."""
    data = ordinary(directed=directed)
    pair = ("two", "one") if reverse else ("one", "two")
    data["edges"][0].update(_src=pair[0], _tgt=pair[1])
    before = deepcopy(data)
    graph = consume(data, "direct", tmp_path, directed)
    assert data == before
    output = tmp_path / "explicit.json"
    assert to_json(graph, {}, str(output), original_links=data["edges"])
    assert arcs(readback(output)[0], "calls") == {pair}


@pytest.mark.parametrize("damage", ["source-only", "target-only", "foreign"], ids=["source-only", "target-only", "foreign"])
@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
@pytest.mark.parametrize("force", [False, True], ids=["guarded", "forced"])
def test_req_qml010_ac03_invalid_legacy_direction_is_not_repaired_for_publication(tmp_path, damage, directed, force):
    """A previously rejected raw marker remains rejected and cannot overwrite the accepted disk view."""
    data = ordinary(directed=directed)
    edge = data["edges"][0]
    if damage == "source-only":
        edge["_src"] = "one"
    elif damage == "target-only":
        edge["_tgt"] = "two"
    else:
        edge.update(_src="foreign", _tgt="two")
    before = deepcopy(data)
    graph = consume(data, "direct", tmp_path, directed)
    assert data == before
    output = tmp_path / "retained.json"
    assert to_json(graph, {}, str(output))
    accepted = output.read_bytes()
    assert to_json(graph, {}, str(output), force=force, original_links=data["edges"]) is False
    assert output.read_bytes() == accepted and data == before


@pytest.mark.parametrize("profile", [False, True], ids=["legacy", "source"])
@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
def test_req_qml010_ac02_required_remap_and_rejected_peer_still_adopt(tmp_path, profile, directed):
    """Preserving ordinary absence cannot restore a rejected call or strand a needed canonical endpoint."""
    data = ordinary(directed=directed)
    data["edges"][0]["target"] = "TWO"
    data["nodes"].append({"id": "format", "label": "format", "type": "field", "source_file": "config.json"})
    data["edges"].append({"source": "one", "target": "format", "relation": "calls",
                          "confidence": "INFERRED", "source_file": "keep.py"})
    if profile:
        data.pop("multigraph")
        storage(data, True)
    held, record = data["edges"], data["edges"][0]
    graph = consume(data, "direct", tmp_path, directed)
    assert data["edges"] is held and held[0] is record and len(held) == 1
    assert record["target"] == "two" and arcs(graph, "calls") == {("one", "two")}
    output = tmp_path / "required.json"
    assert to_json(graph, {}, str(output), original_links=held)
    assert arcs(readback(output)[0], "calls") == {("one", "two")}


@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
def test_req_qml010_ac02_source_profile_keeps_canonical_derived_fields(tmp_path, directed):
    """The legacy absence correction must not strip the promised source-profile caller frame."""
    data = ordinary(directed=directed)
    data.pop("multigraph")
    data["edges"][0].pop("source_file")
    storage(data, True)
    graph = consume(data, "direct", tmp_path, directed)
    edge = data["edges"][0]
    assert is_source_graph(graph)
    assert edge["source_file"] == "keep.py" and (edge["_src"], edge["_tgt"]) == ("one", "two")
    output = tmp_path / "canonical.json"
    assert to_json(graph, {}, str(output), original_links=data["edges"])
    assert arcs(readback(output)[0], "calls") == {("one", "two")}
