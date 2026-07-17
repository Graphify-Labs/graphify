#!/usr/bin/env python3
"""Isolated behavioral parity checks; NetworkX is benchmark-only."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

import networkx

from graphify.helix.model import EdgeData, GraphBuildData, NodeData
from graphify.helix.native import native_backend_info
from graphify.helix.persistence import HelixEmbeddedStore
from graphify.helix.state import new_state


def load_native(build: GraphBuildData, root: Path):
    with HelixEmbeddedStore(root / "graph.helix") as store:
        store.save_generation(build, new_state())
    with HelixEmbeddedStore(root / "graph.helix", read_only=True) as store:
        return store.load().graph


def close_scores(left: dict, right: dict, tolerance: float = 1e-9) -> bool:
    return left.keys() == right.keys() and all(
        abs(left[key] - right[key]) <= tolerance for key in left
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="graphify-parity-") as temporary:
        root = Path(temporary)
        nodes = [NodeData("a"), NodeData(2), NodeData(b"c")]
        edges = [
            EdgeData("a", 2, {"relation": "calls", "weight": 1.0}),
            EdgeData(2, b"c", {"relation": "calls", "weight": 1.0}),
        ]
        native = load_native(GraphBuildData(kind="digraph", nodes=nodes, edges=edges), root)
        reference = networkx.DiGraph()
        reference.add_edge("a", 2, weight=1.0)
        reference.add_edge(2, b"c", weight=1.0)

        from helixdb import TraversalOptions

        checks = {
            "directed_path": native.shortest_path("a", b"c", direction="out").node_ids
            == tuple(networkx.shortest_path(reference, "a", b"c")),
            "bfs": {visit.node_id for visit in native.traverse(TraversalOptions(
                seeds=("a",), max_depth=10, strategy="breadth_first", direction="out"
            )).visits} == set(networkx.bfs_tree(reference, "a")),
            "dfs": {visit.node_id for visit in native.traverse(TraversalOptions(
                seeds=("a",), max_depth=10, strategy="depth_first", direction="out"
            )).visits} == set(networkx.dfs_tree(reference, "a")),
        }
        native_node_scores = {row.node_id: row.score for row in native.betweenness_centrality()}
        checks["node_betweenness"] = close_scores(
            native_node_scores, networkx.betweenness_centrality(reference)
        )
        native_edge_scores = {
            (row.source, row.target): row.score
            for row in native.edge_betweenness_centrality()
        }
        checks["edge_betweenness"] = close_scores(
            native_edge_scores, networkx.edge_betweenness_centrality(reference)
        )

        community_nodes = [NodeData(name) for name in "abcdef"]
        community_edges = [
            EdgeData(u, v, {"relation": "related", "weight": 1.0})
            for group in ("abc", "def")
            for index, u in enumerate(group)
            for v in group[index + 1 :]
        ]
        communities = load_native(
            GraphBuildData(nodes=community_nodes, edges=community_edges), root / "communities"
        )
        native_partition = {frozenset(row.node_ids) for row in communities.louvain_communities().communities}
        nx_community = networkx.Graph()
        nx_community.add_edges_from((edge.source, edge.target) for edge in community_edges)
        nx_partition = {
            frozenset(group)
            for group in networkx.community.louvain_communities(nx_community, seed=42)
        }
        checks["louvain"] = native_partition == nx_partition
        checks["layout"] = len(communities.spring_layout()) == 6
        checks["transformations"] = (
            communities.induced_subgraph(["a", "b"]).edge_count == 1
            and communities.relabel({"a": ("renamed", "a")}).contains_node(("renamed", "a"))
            and communities.to_directed().directed
        )

        report = {
            "helix_revision": native_backend_info().embedded_version,
            "networkx_version": networkx.__version__,
            "checks": checks,
            "all_passed": all(checks.values()),
        }
        print(json.dumps(report, indent=2))
        if not report["all_passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
