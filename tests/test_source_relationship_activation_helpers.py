"""Neutral real-source helpers for typed activation and durable consumer checks."""
from __future__ import annotations

from copy import deepcopy
import json

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.graph_direction import logical_endpoints
from graphify.paths import load_node_link_graph
from tests.source_observation_helpers import produce


def payload(root):
    """Use actual parser-produced promises, rather than duplicating their validator."""
    data = produce(root, local=True, mode="direct")
    assert any("csharp_local_function" in node.get("metadata", {}) for node in data["nodes"])
    return data


def local_node(data):
    return deepcopy(next(node for node in data["nodes"]
                         if "csharp_local_function" in node.get("metadata", {})))


def graph_state(graph):
    return deepcopy((graph.graph, list(graph.nodes(data=True)), list(graph.edges(data=True))))


def topology(graph):
    """Compare source mechanisms in their logical direction, independently of keys."""
    return {(logical_endpoints(left, right, attrs, directed=graph.is_directed()),
             attrs.get("relation"), attrs.get("context"))
            for left, right, attrs in graph.edges(data=True)}


def accepted(root, data, directed):
    graph = build_from_json(deepcopy(data), root=root, directed=directed)
    path = root / "accepted.json"
    assert to_json(graph, {}, str(path), force=True)
    return graph, path, path.read_bytes()


def assert_recovery(root, data, path, expected, directed):
    """Repair through real assembly/export/path reload and prove repeat bytes."""
    restored = build_from_json(deepcopy(data), root=root, directed=directed)
    assert topology(restored) == expected
    assert to_json(restored, {}, str(path), force=True)
    loaded = load_node_link_graph(path)
    assert topology(loaded) == expected
    recovered = path.read_bytes()
    assert to_json(loaded, {}, str(path), force=True)
    assert path.read_bytes() == recovered
    assert json.loads(recovered)["graph"]["graphify_source_relationships"] == {"contract_version": 1}
