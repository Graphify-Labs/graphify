"""Unit tests for the :mod:`networkx.algorithms.centrality.reaching` module."""

import pytest

import networkx as nx


class TestGlobalReachingCentrality:
    """Unit tests for the global reaching centrality function."""

    def test_non_positive_weights(self):
        with pytest.raises(nx.NetworkXError):
            G = nx.DiGraph()
            nx.global_reaching_centrality(G, weight="weight")

    def test_negatively_weighted(self):
        with pytest.raises(nx.NetworkXError):
            G = nx.Graph()
            G.add_weighted_edges_from([(0, 1, -2), (1, 2, +1)])
            nx.global_reaching_centrality(G, weight="weight")

    def test_directed_star(self):
        G = nx.DiGraph()
        G.add_weighted_edges_from([(1, 2, 0.5), (1, 3, 0.5)])
        grc = nx.global_reaching_centrality
        assert grc(G, normalized=False, weight="weight") == 0.5
        assert grc(G) == 1

    def test_undirected_unweighted_star(self):
        G = nx.star_graph(2)
        grc = nx.global_reaching_centrality
        assert grc(G, normalized=False, weight=None) == 0.25

    def test_undirected_weighted_star(self):
        G = nx.Graph()
        G.add_weighted_edges_from([(1, 2, 1), (1, 3, 2)])
        grc = nx.global_reaching_centrality
        assert grc(G, normalized=False, weight="weight") == 0.375

    def test_cycle_directed_unweighted(self):
        G = nx.DiGraph()
        G.add_edge(1, 2)
        G.add_edge(2, 1)
        assert nx.global_reaching_centrality(G, weight=None) == 0

    def test_cycle_undirected_unweighted(self):
        G = nx.Graph()
        G.add_edge(1, 2)
        assert nx.global_reaching_centrality(G, weight=None) == 0

    def test_cycle_directed_weighted(self):
        G = nx.DiGraph()
        G.add_weighted_edges_from([(1, 2, 1), (2, 1, 1)])
        assert nx.global_reaching_centrality(G) == 0

    def test_cycle_undirected_weighted(self):
        G = nx.Graph()
        G.add_edge(1, 2, weight=1)
        grc = nx.global_reaching_centrality
        assert grc(G, normalized=False) == 0

    def test_directed_weighted(self):
        G = nx.DiGraph()
        G.add_edge("A", "B", weight=5)
        G.add_edge("B", "C", weight=1)
        G.add_edge("B", "D", weight=0.25)
        G.add_edge("D", "E", weight=1)

        denom = len(G) - 1
        A_local = sum([5, 3, 2.625, 2.0833333333333]) / denom
        B_local = sum([1, 0.25, 0.625]) / denom
        C_local = 0
        D_local = sum([1]) / denom
        E_local = 0

        local_reach_ctrs = [A_local, C_local, B_local, D_local, E_local]
        max_local = max(local_reach_ctrs)
        expected = sum(max_local - lrc for lrc in local_reach_ctrs) / denom
        grc = nx.global_reaching_centrality
        actual = grc(G, normalized=False, weight="weight")
        assert expected == pytest.approx(actual, abs=1e-7)

    def test_single_node_with_cycle(self):
        G = nx.DiGraph([(1, 1)])
        with pytest.raises(nx.NetworkXError, match="local_reaching_centrality"):
            nx.global_reaching_centrality(G)

    def test_single_node_with_weighted_cycle(self):
        G = nx.DiGraph()
        G.add_weighted_edges_from([(1, 1, 2)])
        with pytest.raises(nx.NetworkXError, match="local_reaching_centrality"):
            nx.global_reaching_centrality(G, weight="weight")


class TestLocalReachingCentrality:
    """Unit tests for the local reaching centrality function."""

    def test_non_positive_weights(self):
        with pytest.raises(nx.NetworkXError):
            G = nx.DiGraph()
            G.add_weighted_edges_from([(0, 1, 0)])
            nx.local_reaching_centrality(G, 0, weight="weight")

    def test_negatively_weighted(self):
        with pytest.raises(nx.NetworkXError):
            G = nx.Graph()
            G.add_weighted_edges_from([(0, 1, -2), (1, 2, +1)])
            nx.local_reaching_centrality(G, 0, weight="weight")

    def test_undirected_unweighted_star(self):
        G = nx.star_graph(2)
        grc = nx.local_reaching_centrality
        assert grc(G, 1, weight=None, normalized=False) == 0.75

    def test_undirected_weighted_star(self):
        G = nx.Graph()
        G.add_weighted_edges_from([(1, 2, 1), (1, 3, 2)])
        centrality = nx.local_reaching_centrality(
            G, 1, normalized=False, weight="weight"
        )
        assert centrality == 1.5

    def test_undirected_weighted_normalized(self):
        G = nx.Graph()
        G.add_weighted_edges_from([(1, 2, 1), (1, 3, 2)])
        centrality = nx.local_reaching_centrality(
            G, 1, normalized=True, weight="weight"
        )
        assert centrality == 1.0

    def test_single_node_with_cycle(self):
        G = nx.DiGraph([(1, 1)])
        with pytest.raises(nx.NetworkXError, match="local_reaching_centrality"):
            nx.local_reaching_centrality(G, 1)

    def test_single_node_with_weighted_cycle(self):
        G = nx.DiGraph()
        G.add_weighted_edges_from([(1, 1, 2)])
        with pytest.raises(nx.NetworkXError, match="local_reaching_centrality"):
            nx.local_reaching_centrality(G, 1, weight="weight")
