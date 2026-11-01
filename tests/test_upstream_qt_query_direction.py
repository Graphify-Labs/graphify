"""INC-QML-54: upstream override/parallel queries retain Qt direction authority."""
from __future__ import annotations

import copy

import networkx as nx
import pytest

from graphify.affected import affected_nodes
from graphify.extractors.qml_facts import qml_metadata
from graphify.qml_resolution_types import fact_edge, fact_node


OWNER_EDGES = (("derived", "derived_method"), ("derived", "base"), ("base", "base_method"))


def override_graph():
    """A generic override has both a plain caller and a source-owned QML use."""
    graph = nx.DiGraph()
    for identity, label in (("derived", "Derived"), ("base", "Base"),
                            ("derived_method", "apply"), ("base_method", "apply"),
                            ("caller", "caller")):
        graph.add_node(identity, label=label, source_file="adapter.py")
    for pair, relation in zip(OWNER_EDGES, ("method", "inherits", "method")):
        graph.add_edge(*pair, relation=relation, _src=pair[0], _tgt=pair[1])
    graph.add_edge("caller", "base_method", relation="calls", _src="caller", _tgt="base_method")
    component = fact_node("Main.qml", "component", "root", "Panel", 1)
    site = fact_node("Main.qml", "read", "site", "apply", 2)
    assert qml_metadata(site)["contract_version"] == 1
    for node in (component, site):
        graph.add_node(node["id"], **node)
    ownership = fact_edge(component["id"], site["id"], "contains", site, "qml_source_owner")
    graph.add_edge(component["id"], site["id"], **ownership)
    graph.add_edge(site["id"], "base_method", relation="references", _src=site["id"], _tgt="base_method")
    return graph, component["id"], site["id"]


def test_req_qml013_ac02_override_keeps_generic_callers_and_qml_source_owners():
    """An accepted stepping stone preserves mechanism filters and source ownership."""
    graph, component, site = override_graph()
    original = copy.deepcopy(graph)
    hits = {hit.node_id for hit in affected_nodes(graph, "derived_method", depth=2)}
    assert {"caller", component, site} <= hits
    assert "base_method" not in hits
    calls = {hit.node_id for hit in affected_nodes(graph, "derived_method", relations=["calls"], depth=2)}
    assert "caller" in calls and not {component, site} & calls
    assert nx.utils.graphs_equal(graph, original)


@pytest.mark.parametrize("pair", OWNER_EDGES)
@pytest.mark.parametrize("corruption", ["partial", "foreign", "reversed"])
def test_req_qml010_ac04_override_cannot_bypass_owner_edge_direction(pair, corruption):
    """Each new owner/supertype/member hop must reject invalid transport evidence."""
    graph, component, site = override_graph()
    edge = graph.edges[pair]
    if corruption == "partial":
        del edge["_tgt"]
    elif corruption == "foreign":
        edge["_src"] = "outside_identity"
    else:
        edge["_src"], edge["_tgt"] = pair[1], pair[0]
    hits = {hit.node_id for hit in affected_nodes(graph, "derived_method", depth=2)}
    assert not {"caller", component, site} & hits


def test_req_qml013_ac04_parallel_consumer_orders_all_original_relationships(tmp_path):
    """MCP loading retains parallel mechanisms; source-fact rendering is stable."""
    import json

    from graphify.serve import _read_graph, _subgraph_to_text

    nodes = [{"id": "owner", "label": "Owner", "source_file": "Main.qml"},
             {"id": "target", "label": "Target", "source_file": "backend.h"}]
    links = [{"source": "owner", "target": "target", "_src": "owner", "_tgt": "target",
              "relation": relation, "confidence": "EXTRACTED", "context": context,
              "source_file": "Main.qml", "source_location": location}
             for relation, context, location in (("references", "qml_binding_read", "L8"),
                                                  ("contains", "qml_source_owner", "L3"))]
    rendered = []
    for index, ordered in enumerate((links, list(reversed(links)))):
        path = tmp_path / f"parallel-{index}.json"
        path.write_text(json.dumps({"nodes": nodes, "links": ordered,
                                    "directed": True, "multigraph": False}), encoding="utf-8")
        graph = _read_graph(str(path))
        assert graph.is_multigraph() and graph.number_of_edges() == 2
        text = _subgraph_to_text(graph, {"owner", "target"}, [("owner", "target")])
        assert text.count("EDGE Owner --") == 2
        assert "--references [EXTRACTED context=qml_binding_read]--> Target at=Main.qml:L8" in text
        assert "--contains [EXTRACTED context=qml_source_owner]--> Target at=Main.qml:L3" in text
        rendered.append(text)
    assert rendered[0] == rendered[1]
