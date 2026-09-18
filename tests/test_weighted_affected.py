from __future__ import annotations

import networkx as nx

from graphify.affected import (
    affected_proof_path,
    weighted_affected_details,
    weighted_affected_nodes,
)


def test_weighted_affected_orders_by_relation_cost() -> None:
    graph = nx.DiGraph()
    graph.add_edge("fast_consumer", "core", relation="calls")
    graph.add_edge("slow_importer", "core", relation="imports")
    graph.add_edge("downstream", "slow_importer", relation="calls")

    hits = weighted_affected_nodes(
        graph,
        "core",
        relations=("calls", "imports"),
        relation_weights={"calls": 0.2, "imports": 2.0},
    )

    assert [h.node_id for h in hits[:2]] == ["fast_consumer", "slow_importer"]
    assert hits[0].cost < hits[1].cost
    assert hits[0].path == ("fast_consumer", "core")


def test_weighted_affected_applies_hub_penalty_and_pruning() -> None:
    graph = nx.DiGraph()
    graph.add_edge("hub", "core", relation="calls")
    for i in range(5):
        graph.add_edge(f"spoke_{i}", "hub", relation="calls")

    details = weighted_affected_details(
        graph,
        "core",
        hub_degree=3,
        hub_penalty=5.0,
    )

    assert [h.node_id for h in details.hits] == ["hub"]
    assert details.hits[0].cost == 6.0
    assert details.metrics["hub_skips"] == 1


def test_weighted_affected_exports_proof_path_to_target() -> None:
    graph = nx.DiGraph()
    graph.add_edge("controller", "service", relation="calls")
    graph.add_edge("service", "core", relation="calls")
    graph.add_edge("unrelated", "other", relation="calls")

    path = affected_proof_path(graph, "core", "controller")

    assert path == ("controller", "service", "core")
