"""INC120: optional typed activation rejects corrupt envelopes without legacy drift."""
from __future__ import annotations

from copy import deepcopy
from types import MappingProxyType

import networkx as nx
import pytest

from graphify.build import build_from_json
from graphify.paths import load_node_link_graph
from graphify.source_relationships import FIELD, make_source_graph, source_profile
from tests.test_source_relationship_activation_helpers import local_node, payload

MARKER = {FIELD: {"contract_version": 1}}


@pytest.mark.parametrize("carrier", [None, False, 0, 1.25, "", "text", b"", b"text",
                                     {}, {"ordinary": {}}, MappingProxyType({})])
def test_req_qml022_ac06_explicit_source_marker_rejects_invalid_collection(carrier):
    """An explicit storage promise cannot turn a malformed carrier into source absence."""
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID"):
        source_profile(carrier, deepcopy(MARKER))


@pytest.mark.parametrize("kind", ["list", "tuple", "pairs", "generator", "node_view"])
@pytest.mark.parametrize("marker", [False, True])
def test_req_qml022_ac06_supported_node_iterables_keep_activation(tmp_path, kind, marker):
    """Accepted direct producer/view inputs scan completely without consuming twice."""
    node = local_node(payload(tmp_path))
    nodes = [{"id": "ordinary"}, node, {"id": "last"}]
    before, seen = deepcopy(nodes), []
    if kind == "tuple":
        carrier = tuple(nodes)
    elif kind == "pairs":
        carrier = [(item["id"], item) for item in nodes]
    elif kind == "node_view":
        graph = nx.Graph()
        graph.add_nodes_from((item["id"], item) for item in nodes)
        carrier = graph.nodes(data=True)
    elif kind == "generator":
        def records():
            for item in nodes:
                seen.append(item["id"])
                yield item
        carrier = records()
    else:
        carrier = nodes
    assert source_profile(carrier, deepcopy(MARKER) if marker else None) is True
    assert nodes == before
    if kind == "generator":
        assert seen == [item["id"] for item in nodes]


@pytest.mark.parametrize("damage", ["none", "list", "text", "number", "empty_pair",
                                   "short_pair", "null_attributes", "list_attributes", "long_pair"])
@pytest.mark.parametrize("position", ["before", "after"])
@pytest.mark.parametrize("marker", [False, True])
def test_req_qml022_ac06_typed_fact_cannot_mask_invalid_node_records(tmp_path, damage, position, marker):
    """An admitted peer activates strict records; tuple envelope errors stay controlled."""
    node = local_node(payload(tmp_path))
    malformed = {"none": None, "list": [], "text": "text", "number": 7,
                 "empty_pair": (), "short_pair": ("only",), "null_attributes": ("id", None),
                 "list_attributes": ("id", []), "long_pair": ("id", {}, "extra")}[damage]
    nodes = [malformed, node] if position == "before" else [node, malformed]
    before = deepcopy(nodes)
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID"):
        source_profile(nodes, deepcopy(MARKER) if marker else None)
    assert nodes == before


def test_req_qml022_ac06_invalid_pair_cannot_hide_its_actual_attribute_promise(tmp_path):
    """A bad pair still exposes its existing attribute slot; no recursive mapping search."""
    node = local_node(payload(tmp_path))
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID"):
        source_profile([(node["id"], node, "unexpected")])


@pytest.mark.parametrize("kind", ["list", "tuple", "pairs", "generator", "node_view"])
@pytest.mark.parametrize("position", ["before", "after"])
def test_req_qml022_ac06_all_local_promises_validate_after_activation(tmp_path, kind, position):
    """A valid first promise never hides a later malformed actual producer record."""
    valid = local_node(payload(tmp_path))
    invalid = deepcopy(valid)
    invalid["metadata"]["csharp_local_function"]["contract_version"] = True
    nodes = [invalid, valid] if position == "before" else [valid, invalid]
    if kind == "tuple":
        carrier = tuple(nodes)
    elif kind == "pairs":
        carrier = [(str(index), node) for index, node in enumerate(nodes)]
    elif kind == "node_view":
        graph = nx.Graph()
        graph.add_nodes_from((str(index), node) for index, node in enumerate(nodes))
        carrier = graph.nodes(data=True)
    else:
        carrier = (node for node in nodes) if kind == "generator" else nodes
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID"):
        source_profile(carrier)


@pytest.mark.parametrize("nodes", [[], (), "", {}, [None, [], "text", 7, ("id", {}), {"id": "ordinary"}]])
@pytest.mark.parametrize("metadata", [None, {}, [], "", False, 0])
def test_req_qml022_ac06_unpromised_legacy_activation_absence_is_unchanged(nodes, metadata):
    """Optional typed strictness cannot impose new rules on successful legacy absence."""
    assert source_profile(deepcopy(nodes), deepcopy(metadata)) is False


@pytest.mark.parametrize("nodes", ["", {}, [], ()])
def test_req_qml022_ac06_actual_legacy_builder_empty_carriers_stay_accepted(nodes):
    """The preimplementation accepted empty-carrier matrix keeps its simple graph."""
    graph = build_from_json({"nodes": deepcopy(nodes), "edges": []})
    assert not graph and graph.number_of_edges() == 0 and not graph.is_multigraph()


@pytest.mark.parametrize("boundary", ["build", "load"])
def test_req_qml022_ac06_actual_legacy_ordinary_list_keeps_existing_projection(boundary):
    """The loader's legacy multigraph default and builder's simple default remain distinct."""
    data = {"nodes": [{"id": "ordinary", "label": "Ordinary", "type": "code"}], "edges": []}
    graph = build_from_json(data) if boundary == "build" else load_node_link_graph(data)
    assert set(graph) == {"ordinary"} and graph.number_of_edges() == 0
    assert graph.is_multigraph() is (boundary == "load")


def test_req_qml022_ac06_marker_only_default_source_graph_stays_supported():
    """No source fact is fabricated when the persisted storage marker alone selects arcs."""
    graph = make_source_graph(graph_metadata=deepcopy(MARKER))
    assert graph.is_multigraph() and not graph and graph.graph == MARKER


@pytest.mark.parametrize("nodes", [None, False, 0])
def test_req_qml022_ac06_unpromised_noniterable_keeps_existing_legacy_failure(nodes):
    """The precharacterized failed legacy carrier does not acquire typed diagnostics."""
    with pytest.raises(TypeError):
        source_profile(nodes)
