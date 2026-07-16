"""
Tests for second order centrality.
"""

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

import networkx as nx


def test_empty():
    with pytest.raises(nx.NetworkXException):
        G = nx.empty_graph()
        nx.second_order_centrality(G)


def test_non_connected():
    with pytest.raises(nx.NetworkXException):
        G = nx.Graph()
        G.add_node(0)
        G.add_node(1)
        nx.second_order_centrality(G)


def test_non_negative_edge_weights():
    with pytest.raises(nx.NetworkXException):
        G = nx.path_graph(2)
        G.add_edge(0, 1, weight=-1)
        nx.second_order_centrality(G)


def test_weight_attribute():
    G = nx.Graph()
    G.add_weighted_edges_from([(0, 1, 1.0), (1, 2, 3.5)], weight="w")
    expected = {0: 3.431, 1: 3.082, 2: 5.612}
    b = nx.second_order_centrality(G, weight="w")

    for n in sorted(G):
        assert b[n] == pytest.approx(expected[n], abs=1e-2)


def test_one_node_graph():
    """Second order centrality: single node"""
    G = nx.Graph()
    G.add_node(0)
    G.add_edge(0, 0)
    assert nx.second_order_centrality(G)[0] == 0


def test_P3():
    """Second order centrality: line graph, as defined in paper"""
    G = nx.path_graph(3)
    b_answer = {0: 3.741, 1: 1.414, 2: 3.741}

    b = nx.second_order_centrality(G)

    for n in sorted(G):
        assert b[n] == pytest.approx(b_answer[n], abs=1e-2)


def test_K3():
    """Second order centrality: complete graph, as defined in paper"""
    G = nx.complete_graph(3)
    b_answer = {0: 1.414, 1: 1.414, 2: 1.414}

    b = nx.second_order_centrality(G)

    for n in sorted(G):
        assert b[n] == pytest.approx(b_answer[n], abs=1e-2)


def test_ring_graph():
    """Second order centrality: ring graph, as defined in paper"""
    G = nx.cycle_graph(5)
    b_answer = {0: 4.472, 1: 4.472, 2: 4.472, 3: 4.472, 4: 4.472}

    b = nx.second_order_centrality(G)

    for n in sorted(G):
        assert b[n] == pytest.approx(b_answer[n], abs=1e-2)
