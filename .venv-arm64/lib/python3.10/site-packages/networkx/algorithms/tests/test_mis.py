"""
Tests for maximal (not maximum) independent sets.

"""

import random

import pytest

import networkx as nx


def test_random_seed():
    G = nx.empty_graph(5)
    assert nx.maximal_independent_set(G, seed=1) == [1, 0, 3, 2, 4]


@pytest.mark.parametrize("graph", [nx.complete_graph(5), nx.complete_graph(55)])
def test_K5(graph):
    """Maximal independent set for complete graphs"""
    assert all(nx.maximal_independent_set(graph, [n]) == [n] for n in graph)


def test_exceptions():
    """Bad input should raise exception."""
    G = nx.florentine_families_graph()
    pytest.raises(nx.NetworkXUnfeasible, nx.maximal_independent_set, G, ["Smith"])
    pytest.raises(
        nx.NetworkXUnfeasible, nx.maximal_independent_set, G, ["Salviati", "Pazzi"]
    )
    # MaximalIndependentSet is not implemented for directed graphs
    pytest.raises(nx.NetworkXNotImplemented, nx.maximal_independent_set, nx.DiGraph(G))


def test_florentine_family():
    G = nx.florentine_families_graph()
    indep = nx.maximal_independent_set(G, ["Medici", "Bischeri"])
    assert set(indep) == {
        "Medici",
        "Bischeri",
        "Castellani",
        "Pazzi",
        "Ginori",
        "Lamberteschi",
    }


def test_bipartite():
    G = nx.complete_bipartite_graph(12, 34)
    indep = nx.maximal_independent_set(G, [4, 5, 9, 10])
    assert sorted(indep) == list(range(12))


def test_random_graphs():
    """Generate 5 random graphs of different types and sizes and
    make sure that all sets are independent and maximal."""
    for i in range(0, 50, 10):
        G = nx.erdos_renyi_graph(i * 10 + 1, random.random())
        IS = nx.maximal_independent_set(G)
        assert G.subgraph(IS).number_of_edges() == 0
        nbrs_of_MIS = set.union(*(set(G.neighbors(v)) for v in IS))
        assert all(v in nbrs_of_MIS for v in set(G.nodes()).difference(IS))
