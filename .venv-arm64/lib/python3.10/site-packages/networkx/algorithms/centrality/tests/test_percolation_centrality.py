import pytest

import networkx as nx


def example1a_G():
    G = nx.Graph()
    G.add_node(1, percolation=0.1)
    G.add_node(2, percolation=0.2)
    G.add_node(3, percolation=0.2)
    G.add_node(4, percolation=0.2)
    G.add_node(5, percolation=0.3)
    G.add_node(6, percolation=0.2)
    G.add_node(7, percolation=0.5)
    G.add_node(8, percolation=0.5)
    G.add_edges_from([(1, 4), (2, 4), (3, 4), (4, 5), (5, 6), (6, 7), (6, 8)])
    return G


def example1b_G():
    G = nx.Graph()
    G.add_node(1, percolation=0.3)
    G.add_node(2, percolation=0.5)
    G.add_node(3, percolation=0.5)
    G.add_node(4, percolation=0.2)
    G.add_node(5, percolation=0.3)
    G.add_node(6, percolation=0.2)
    G.add_node(7, percolation=0.1)
    G.add_node(8, percolation=0.1)
    G.add_edges_from([(1, 4), (2, 4), (3, 4), (4, 5), (5, 6), (6, 7), (6, 8)])
    return G


def test_percolation_example1a():
    """percolation centrality: example 1a"""
    G = example1a_G()
    p = nx.percolation_centrality(G)
    p_answer = {4: 0.625, 6: 0.667}
    for n, k in p_answer.items():
        assert p[n] == pytest.approx(k, abs=1e-3)


def test_percolation_example1b():
    """percolation centrality: example 1a"""
    G = example1b_G()
    p = nx.percolation_centrality(G)
    p_answer = {4: 0.825, 6: 0.4}
    for n, k in p_answer.items():
        assert p[n] == pytest.approx(k, abs=1e-3)


def test_converge_to_betweenness():
    """percolation centrality: should converge to betweenness
    centrality when all nodes are percolated the same"""
    # taken from betweenness test test_florentine_families_graph
    G = nx.florentine_families_graph()
    b_answer = {
        "Acciaiuoli": 0.000,
        "Albizzi": 0.212,
        "Barbadori": 0.093,
        "Bischeri": 0.104,
        "Castellani": 0.055,
        "Ginori": 0.000,
        "Guadagni": 0.255,
        "Lamberteschi": 0.000,
        "Medici": 0.522,
        "Pazzi": 0.000,
        "Peruzzi": 0.022,
        "Ridolfi": 0.114,
        "Salviati": 0.143,
        "Strozzi": 0.103,
        "Tornabuoni": 0.092,
    }

    # If no initial state is provided, state for
    # every node defaults to 1
    p_answer = nx.percolation_centrality(G)
    assert p_answer == pytest.approx(b_answer, abs=1e-3)

    p_states = {k: 0.3 for k, v in b_answer.items()}
    p_answer = nx.percolation_centrality(G, states=p_states)
    assert p_answer == pytest.approx(b_answer, abs=1e-3)


def test_default_percolation():
    G = nx.erdos_renyi_graph(42, 0.42, seed=42)
    assert nx.percolation_centrality(G) == pytest.approx(nx.betweenness_centrality(G))
