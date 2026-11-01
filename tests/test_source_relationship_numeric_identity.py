"""INC131: numeric identity repair preserves only previously accepted direction."""
from __future__ import annotations

from copy import deepcopy
import errno

import pytest

from graphify.build import build, build_from_json
from graphify.export import to_json
from graphify.paths import load_node_link_graph
from graphify.source_relationships import FIELD, is_source_graph, validate_source_transport
from tests.qt_publication_faults import publication_fault
from tests.source_relationship_projection_helpers import arcs, readback, state
from tests.test_source_relationship_legacy_metadata import typed


def numeric_input(root, number, carrier, *, directed=False, native=True, reverse=False):
    """A real C# producer activates storage; its numeric concept peer is ordinary data."""
    if native:
        data = typed(root, directed)
        target = next(node["id"] for node in data["nodes"]
                      if "csharp_local_function" in node.get("metadata", {}))
    else:
        target = "target"
        data = {"nodes": [{"id": target, "label": "Target", "type": "function",
                           "source_file": "keep.py", "source_location": "L1"}],
                "edges": [], "directed": directed}
    data.pop("multigraph", None)
    data["nodes"].append({"id": number, "label": "Legacy", "file_type": "concept",
                          "source_file": "legacy.md", "source_location": "L1"})
    pair = (target, number) if reverse else (number, target)
    peer = {"source": number, "target": target, "relation": "mentions", "confidence": "EXTRACTED",
            "source_file": "legacy.md", "source_location": "L1", "_src": pair[0], "_tgt": pair[1],
            "from": number, "to": target, "custom": {"values": ["kept", {"literal": 7}]}}
    data["edges"].append(peer)
    if carrier != "raw":
        data["graph"] = {FIELD: {"contract_version": 1}}
    if carrier == "persisted":
        data["multigraph"] = True
    return data, peer, target


def consume(data, boundary, root, directed=False):
    """Use the actual direct and combined ownership boundaries, without policy fakes."""
    if boundary == "direct":
        return build_from_json(data, root=root, directed=directed, dedup=False)
    return build([data], root=root, directed=directed, dedup=False)


@pytest.mark.parametrize("number", [7, 7.25], ids=["int", "float"])
@pytest.mark.parametrize("carrier", ["raw", "marker", "persisted"])
@pytest.mark.parametrize("boundary", ["direct", "combined"])
@pytest.mark.parametrize("directed,reverse", [(False, False), (False, True), (True, False)],
                         ids=["undirected-forward", "undirected-reverse", "directed-forward"])
def test_req_qml010_ac02_valid_numeric_direction_survives_original_view_and_path(
        tmp_path, number, carrier, boundary, directed, reverse):
    """An accepted exact pair follows canonical IDs through repeated real publication."""
    data, peer, target = numeric_input(tmp_path, number, carrier, directed=directed, reverse=reverse)
    validate_source_transport(data)
    held = data["edges"]
    original_custom = deepcopy(peer["custom"])
    expected = (target, str(number)) if reverse else (str(number), target)
    output = tmp_path / "numeric.json"
    for _ in range(2):
        graph = consume(data, boundary, tmp_path, directed)
        assert is_source_graph(graph) and graph.is_directed() is directed
        assert str(number) in graph and number not in graph
        assert data["edges"] is held and any(edge is peer for edge in held)
        assert (peer["_src"], peer["_tgt"]) == expected
        assert (peer["from"], peer["to"]) == (peer["source"], peer["target"])
        assert peer["custom"] == original_custom and arcs(graph, "mentions") == {expected}
        assert to_json(graph, {}, str(output), force=True, original_links=held)
        restored, _ = readback(output)
        assert is_source_graph(restored) and arcs(restored, "mentions") == {expected}


@pytest.mark.parametrize("number", [7, 7.25], ids=["int", "float"])
@pytest.mark.parametrize("carrier", ["raw", "marker"], ids=["ordinary", "explicit-source"])
@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
def test_req_qml010_ac02_numeric_ordinary_and_explicit_storage_keep_their_profiles(
        tmp_path, number, carrier, directed):
    """Numeric compatibility is shared; selecting source storage grants no native authority."""
    data, peer, target = numeric_input(tmp_path, number, carrier, directed=directed, native=False)
    graph = consume(data, "direct", tmp_path, directed)
    assert is_source_graph(graph) is (carrier != "raw")
    assert (peer["_src"], peer["_tgt"]) == (str(number), target)
    output = tmp_path / "ordinary.json"
    assert to_json(graph, {}, str(output), original_links=data["edges"])
    assert arcs(load_node_link_graph(output), "mentions") == {(str(number), target)}


def damage_pair(peer, damage, target):
    """Keep malformed marker types/absence distinct from accepted numeric conversion."""
    if damage == "source-only":
        peer.pop("_tgt")
    elif damage == "target-only":
        peer.pop("_src")
    elif damage == "foreign":
        peer["_src"] = "foreign"
    elif damage == "bool-type":
        peer["_src"] = True
    else:
        peer.update(_src=target, _tgt=1)


@pytest.mark.parametrize("carrier", ["raw", "marker", "persisted"])
@pytest.mark.parametrize("boundary", ["direct", "combined"])
@pytest.mark.parametrize("damage", ["source-only", "target-only", "foreign", "bool-type", "reverse-directed"])
def test_req_qml010_ac03_invalid_numeric_source_pair_is_not_healed(
        tmp_path, carrier, boundary, damage):
    """Malformed source transport rejects before it can replace an accepted disk graph."""
    data, peer, target = numeric_input(tmp_path, 1, carrier, directed=damage == "reverse-directed")
    clean = deepcopy(data)
    clean["edges"].remove(clean["edges"][-1])
    clean["nodes"].remove(clean["nodes"][-1])
    output = tmp_path / "accepted.json"
    accepted_graph = consume(clean, "direct", tmp_path, damage == "reverse-directed")
    assert to_json(accepted_graph, {}, str(output), force=True)
    accepted = output.read_bytes()
    damage_pair(peer, damage, target)
    before = deepcopy(data)
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID"):
        consume(data, boundary, tmp_path, damage == "reverse-directed")
    assert output.read_bytes() == accepted
    if boundary == "direct":
        assert data == before


@pytest.mark.parametrize("boundary", ["direct", "combined"])
@pytest.mark.parametrize("damage", ["source-only", "target-only", "foreign", "bool-type"])
def test_req_qml010_ac03_invalid_ordinary_numeric_pair_remains_rejected_by_export(
        tmp_path, boundary, damage):
    """Legacy normalization may repair IDs, but cannot authorize an invalid original view."""
    data, peer, target = numeric_input(tmp_path, 1, "raw", native=False)
    damage_pair(peer, damage, target)
    graph = consume(data, boundary, tmp_path)
    before = deepcopy(data)
    output = tmp_path / "ordinary-retained.json"
    assert to_json(graph, {}, str(output))
    accepted = output.read_bytes()
    for force in (False, True):
        assert to_json(graph, {}, str(output), force=force, original_links=data["edges"]) is False
        assert output.read_bytes() == accepted and data == before


@pytest.mark.parametrize("carrier", ["raw", "marker", "persisted"])
@pytest.mark.parametrize("boundary", ["direct", "combined"])
def test_req_qml010_ac02_numeric_original_view_write_failure_retains_and_recovers(
        tmp_path, monkeypatch, carrier, boundary):
    """A reached atomic replacement failure retains accepted data, then retries identically."""
    data, _, target = numeric_input(tmp_path, 7, carrier)
    graph = consume(data, boundary, tmp_path)
    output = tmp_path / "retry.json"
    assert to_json(graph, {}, str(output), force=True, original_links=data["edges"])
    accepted, before, graph_before = output.read_bytes(), deepcopy(data), state(graph)
    with publication_fault(output, "replace", monkeypatch) as fault:
        with pytest.raises(OSError) as error:
            to_json(graph, {}, str(output), force=True, original_links=data["edges"])
        assert error.value.errno == errno.EIO
    assert fault.qualified and fault.hits == 1
    assert output.read_bytes() == accepted and data == before and state(graph) == graph_before
    assert arcs(load_node_link_graph(output), "mentions") == {("7", target)}
    for _ in range(2):
        assert to_json(graph, {}, str(output), force=True, original_links=data["edges"])
        assert output.read_bytes() == accepted and data == before


@pytest.mark.parametrize("carrier", ["raw", "marker", "persisted"])
@pytest.mark.parametrize("reverse", [False, True], ids=["forward", "reverse"])
def test_req_qml010_ac02_default_dedup_numeric_pair_keeps_one_caller_frame(tmp_path, carrier, reverse):
    """The pre-dedup owner and nested direct owner share the same accepted exact pair."""
    data, peer, target = numeric_input(tmp_path, 7, carrier, reverse=reverse)
    held, custom = data["edges"], deepcopy(peer["custom"])
    expected = (target, "7") if reverse else ("7", target)
    output = tmp_path / "default-dedup.json"
    for _ in range(2):
        graph = build([data], root=tmp_path)
        assert is_source_graph(graph) and "7" in graph and 7 not in graph
        assert data["edges"] is held and any(edge is peer for edge in held)
        assert (peer["_src"], peer["_tgt"]) == expected
        assert (peer["from"], peer["to"]) == (peer["source"], peer["target"])
        assert peer["custom"] == custom and arcs(graph, "mentions") == {expected}
        assert to_json(graph, {}, str(output), force=True, original_links=held)
        assert arcs(load_node_link_graph(output), "mentions") == {expected}


@pytest.mark.parametrize("carrier", ["raw", "marker", "persisted"])
def test_req_qml010_ac03_default_dedup_cannot_heal_reverse_directed_numeric_pair(tmp_path, carrier):
    """Dedup may convert numeric IDs, but cannot turn contradictory direction into authority."""
    data, peer, target = numeric_input(tmp_path, 7, carrier, directed=True, reverse=True)
    accepted_input = deepcopy(data)
    clean_peer = accepted_input["edges"][-1]
    clean_peer.update(_src=7, _tgt=target)
    graph = build([accepted_input], root=tmp_path, directed=True)
    output = tmp_path / "default-retained.json"
    assert to_json(graph, {}, str(output), force=True, original_links=accepted_input["edges"])
    accepted = output.read_bytes()
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID"):
        build([data], root=tmp_path, directed=True)
    assert output.read_bytes() == accepted
