"""Neutral C# source facts used to exercise downstream relationship consumers."""
from __future__ import annotations

import json

import networkx as nx

from graphify.extract import extract


def source_graph(root, *, directed=True, local_name="Local"):
    """Keep real producer metadata while bypassing the assembly bug under test."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / "Data.cs"
    path.write_text(f"class Holder{{void Use(){{void {local_name}(){{}} {local_name}();}}}}")
    result = extract([path], root=root, cache_root=root, parallel=False)
    graph = nx.MultiDiGraph() if directed else nx.MultiGraph()
    for node in result["nodes"]:
        graph.add_node(node["id"], **{key: value for key, value in node.items() if key != "id"})
    for edge in result["edges"]:
        attrs = {key: value for key, value in edge.items() if key not in {"source", "target"}}
        graph.add_edge(edge["source"], edge["target"], **attrs,
                       _src=edge["source"], _tgt=edge["target"])
    local = next(identity for identity, node in graph.nodes(data=True)
                 if node.get("metadata", {}).get("csharp_local_function"))
    caller = next(source for source, target, attrs in graph.edges(data=True)
                  if target == local and attrs.get("context") == "csharp_local_function")
    return graph, caller, local


def write_graph(graph, path):
    """Serialize the complete accepted test input without a consumer projection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(nx.node_link_data(graph, edges="links")))
    return path


def logical_relations(graph, source, target):
    """Compare source relationships independently of physical edge keys/order."""
    return {attrs.get("relation") for left, right, attrs in graph.edges(data=True)
            if attrs.get("_src", left) == source and attrs.get("_tgt", right) == target}
