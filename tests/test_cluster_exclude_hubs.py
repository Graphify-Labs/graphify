"""cluster() under exclude_hubs_percentile keeps hub-only neighbours with their hub.

Excluded hubs are removed from the subgraph that gets partitioned, so a node
whose only neighbours are hubs is isolated there. It used to come back as a
singleton community while the hub itself was reattached by majority vote.
"""
from __future__ import annotations

import networkx as nx

from graphify.cluster import cluster


def _hub_with_private_leaves():
    """Two 4-cliques, one hub H joined to all of A and to b1, and three
    leaves that are connected to H only. Degrees: H=8, A=4, b1=4, B=3,
    leaves=1, so exclude_hubs_percentile=90 excludes exactly H."""
    G = nx.Graph()
    A = ["a1", "a2", "a3", "a4"]
    B = ["b1", "b2", "b3", "b4"]
    for group in (A, B):
        for i, u in enumerate(group):
            for v in group[i + 1:]:
                G.add_edge(u, v)
    for a in A:
        G.add_edge("H", a)
    G.add_edge("H", "b1")
    for leaf in ("l1", "l2", "l3"):
        G.add_edge("H", leaf)
    return G


def test_exclude_hubs_keeps_hub_only_neighbours_with_their_hub():
    """A node whose only neighbours are excluded hubs has degree 0 in the
    partitioned subgraph. It used to come back as a singleton community while
    the hub itself was reattached elsewhere, so every such node was cut off
    from the only node it connects to."""
    G = _hub_with_private_leaves()
    communities = cluster(G, exclude_hubs_percentile=90)
    node_to_cid = {n: cid for cid, nodes in communities.items() for n in nodes}
    assert set(node_to_cid) == set(G.nodes())
    for leaf in ("l1", "l2", "l3"):
        assert node_to_cid[leaf] == node_to_cid["H"]
    assert not [nodes for nodes in communities.values() if len(nodes) == 1]


def test_exclude_hubs_leaves_true_isolates_alone():
    G = _hub_with_private_leaves()
    G.add_node("lonely")
    communities = cluster(G, exclude_hubs_percentile=90)
    assert ["lonely"] in communities.values()


def test_exclude_hubs_without_hubs_is_unchanged():
    G = _hub_with_private_leaves()
    assert cluster(G, exclude_hubs_percentile=100) == cluster(G)


def test_exclude_hubs_hub_only_neighbour_with_self_loop_joins_its_hub():
    """A self-loop is not a real neighbour: a node whose other neighbours are
    all hubs is stranded just the same."""
    G = _hub_with_private_leaves()
    G.add_edge("l1", "l1")
    communities = cluster(G, exclude_hubs_percentile=90)
    node_to_cid = {n: cid for cid, nodes in communities.items() for n in nodes}
    assert node_to_cid["l1"] == node_to_cid["H"]


def test_exclude_hubs_self_loop_only_node_is_left_alone():
    """A node whose only edge is a self-loop has no hub to join; it keeps
    the behaviour it has without the exclusion (its own community)."""
    G = _hub_with_private_leaves()
    G.add_edge("solo", "solo")
    communities = cluster(G, exclude_hubs_percentile=90)
    assert ["solo"] in communities.values()
