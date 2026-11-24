"""Tests for sampled edge betweenness centrality fallback in surprising_connections."""

from __future__ import annotations

import networkx as nx

from graphify.analyze import _cross_community_surprises, surprising_connections


def test_surprising_connections_empty_communities_small_graph():
    """On small graphs (<= 500 nodes), un-sampled exact edge betweenness is used."""
    G = nx.Graph()
    # Graph with 2 cliques connected by a single bridge edge (c1_end - c2_start)
    for i in range(5):
        G.add_node(f"c1_{i}", label=f"C1_{i}", file_type="code", source_file="lib.py")
        G.add_node(f"c2_{i}", label=f"C2_{i}", file_type="code", source_file="lib.py")
    for i in range(5):
        for j in range(i + 1, 5):
            G.add_edge(f"c1_{i}", f"c1_{j}", relation="calls", confidence="EXTRACTED")
            G.add_edge(f"c2_{i}", f"c2_{j}", relation="calls", confidence="EXTRACTED")
    bridge = ("c1_4", "c2_0")
    G.add_edge(*bridge, relation="calls", confidence="EXTRACTED")

    surprises = surprising_connections(G, communities={})
    assert len(surprises) > 0
    # The bridge edge has the highest betweenness centrality
    top = surprises[0]
    labels = {top["source"], top["target"]}
    assert labels == {"C1_4", "C2_0"}
    assert "betweenness=" in top["note"]


def test_surprising_connections_empty_communities_large_graph_sampled():
    """On large graphs (> 500 nodes), edge betweenness uses sampled k=50 for speed."""
    # Create a 600-node barbell-like graph with a single bridge edge (single source file)
    G = nx.Graph()
    for i in range(300):
        G.add_node(f"left_{i}", label=f"Left_{i}", file_type="code", source_file="bundle.py")
        G.add_node(f"right_{i}", label=f"Right_{i}", file_type="code", source_file="bundle.py")
    # Add cycle edges to ensure connectivity in each cluster
    for i in range(300):
        G.add_edge(f"left_{i}", f"left_{(i+1)%300}", relation="calls", confidence="EXTRACTED")
        G.add_edge(f"right_{i}", f"right_{(i+1)%300}", relation="calls", confidence="EXTRACTED")
    # Single bridge connecting left and right clusters
    G.add_edge("left_0", "right_0", relation="bridges", confidence="EXTRACTED")

    assert G.number_of_nodes() == 600

    # Must complete fast and return valid surprises
    surprises = surprising_connections(G, communities={}, top_n=3)
    assert len(surprises) > 0
    top = surprises[0]
    assert "source" in top and "target" in top
    assert "confidence" in top
    assert "note" in top
    assert "betweenness=" in top["note"]
    # The bridge between the two large clusters should be the top surprise
    assert {top["source"], top["target"]} == {"Left_0", "Right_0"}


def test_cross_community_surprises_direct_sampling():
    """_cross_community_surprises directly exercises k=50 sampling for N > 500."""
    G = nx.erdos_renyi_graph(600, 0.01, seed=42)
    for n in G.nodes():
        G.nodes[n]["label"] = f"N_{n}"
        G.nodes[n]["source_file"] = "all.py"
    for u, v in G.edges():
        G.edges[u, v]["relation"] = "calls"
        G.edges[u, v]["confidence"] = "EXTRACTED"

    res = _cross_community_surprises(G, communities={}, top_n=5)
    assert len(res) == 5
    for item in res:
        assert "betweenness=" in item["note"]


def test_surprising_connections_deterministic_with_sampling():
    """Sampling with seed=42 must produce deterministic results across multiple runs."""
    G = nx.erdos_renyi_graph(600, 0.01, seed=123)
    for n in G.nodes():
        G.nodes[n]["label"] = f"node_{n}"
        G.nodes[n]["file_type"] = "code"
        G.nodes[n]["source_file"] = "main.py"
    for u, v in G.edges():
        G.edges[u, v]["relation"] = "calls"
        G.edges[u, v]["confidence"] = "EXTRACTED"

    res1 = surprising_connections(G, communities={}, top_n=5)
    res2 = surprising_connections(G, communities={}, top_n=5)

    assert res1 == res2


def test_surprising_connections_empty_communities_no_edges():
    """Graph with no edges returns empty list immediately."""
    G = nx.Graph()
    G.add_node("a", label="A")
    assert surprising_connections(G, communities={}) == []


def test_surprising_connections_empty_communities_over_5000_nodes():
    """Graph with > 5000 nodes returns empty list without freezing."""
    G = nx.Graph()
    G.add_nodes_from(range(5001))
    G.add_edge(0, 1)
    assert surprising_connections(G, communities={}) == []
