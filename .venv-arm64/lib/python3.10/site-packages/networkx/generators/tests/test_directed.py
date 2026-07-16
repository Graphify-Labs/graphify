"""Generators - Directed Graphs
----------------------------
"""

import pytest

import networkx as nx
from networkx.classes import Graph, MultiDiGraph
from networkx.generators.directed import (
    gn_graph,
    gnc_graph,
    gnr_graph,
    random_k_out_graph,
    random_uniform_k_out_graph,
    scale_free_graph,
)


class TestGeneratorsDirected:
    def test_smoke_test_random_graphs(self):
        gn_graph(100)
        gnr_graph(100, 0.5)
        gnc_graph(100)
        scale_free_graph(100)

        gn_graph(100, seed=42)
        gnr_graph(100, 0.5, seed=42)
        gnc_graph(100, seed=42)
        scale_free_graph(100, seed=42)

    def test_create_using_keyword_arguments(self):
        pytest.raises(nx.NetworkXError, gn_graph, 100, create_using=Graph())
        pytest.raises(nx.NetworkXError, gnr_graph, 100, 0.5, create_using=Graph())
        pytest.raises(nx.NetworkXError, gnc_graph, 100, create_using=Graph())
        G = gn_graph(100, seed=1)
        MG = gn_graph(100, create_using=MultiDiGraph(), seed=1)
        assert sorted(G.edges()) == sorted(MG.edges())
        G = gnr_graph(100, 0.5, seed=1)
        MG = gnr_graph(100, 0.5, create_using=MultiDiGraph(), seed=1)
        assert sorted(G.edges()) == sorted(MG.edges())
        G = gnc_graph(100, seed=1)
        MG = gnc_graph(100, create_using=MultiDiGraph(), seed=1)
        assert sorted(G.edges()) == sorted(MG.edges())

        G = scale_free_graph(
            100,
            alpha=0.3,
            beta=0.4,
            gamma=0.3,
            delta_in=0.3,
            delta_out=0.1,
            initial_graph=nx.cycle_graph(4, create_using=MultiDiGraph),
            seed=1,
        )
        pytest.raises(ValueError, scale_free_graph, 100, 0.5, 0.4, 0.3)
        pytest.raises(ValueError, scale_free_graph, 100, alpha=-0.3)
        pytest.raises(ValueError, scale_free_graph, 100, beta=-0.3)
        pytest.raises(ValueError, scale_free_graph, 100, gamma=-0.3)

    def test_parameters(self):
        G = nx.DiGraph()
        G.add_node(0)

        def kernel(x):
            return x

        assert nx.is_isomorphic(gn_graph(1), G)
        assert nx.is_isomorphic(gn_graph(1, kernel=kernel), G)
        assert nx.is_isomorphic(gnc_graph(1), G)
        assert nx.is_isomorphic(gnr_graph(1, 0.5), G)


def test_scale_free_graph_negative_delta():
    with pytest.raises(ValueError, match="delta_in must be >= 0."):
        scale_free_graph(10, delta_in=-1)
    with pytest.raises(ValueError, match="delta_out must be >= 0."):
        scale_free_graph(10, delta_out=-1)


def test_non_numeric_ordering():
    G = MultiDiGraph([("a", "b"), ("b", "c"), ("c", "a")])
    s = scale_free_graph(3, initial_graph=G)
    assert len(s) == 3
    assert len(s.edges) == 3


@pytest.mark.parametrize("ig", (nx.Graph(), nx.DiGraph([(0, 1)])))
def test_scale_free_graph_initial_graph_kwarg(ig):
    with pytest.raises(nx.NetworkXError):
        scale_free_graph(100, initial_graph=ig)


class TestRandomKOutGraph:
    """Unit tests for the
    :func:`~networkx.generators.directed.random_k_out_graph` function.

    """

    def test_regularity(self):
        """Tests that the generated graph is `k`-out-regular."""
        n = 10
        k = 3
        alpha = 1
        G = random_k_out_graph(n, k, alpha)
        assert all(d == k for v, d in G.out_degree())
        G = random_k_out_graph(n, k, alpha, seed=42)
        assert all(d == k for v, d in G.out_degree())

    def test_no_self_loops(self):
        """Tests for forbidding self-loops."""
        n = 10
        k = 3
        alpha = 1
        G = random_k_out_graph(n, k, alpha, self_loops=False)
        assert nx.number_of_selfloops(G) == 0

    def test_negative_alpha(self):
        with pytest.raises(ValueError, match="alpha must be positive"):
            random_k_out_graph(10, 3, -1)


class TestUniformRandomKOutGraph:
    """Unit tests for the
    :func:`~networkx.generators.directed.random_uniform_k_out_graph`
    function.

    """

    def test_regularity(self):
        """Tests that the generated graph is `k`-out-regular."""
        n = 10
        k = 3
        G = random_uniform_k_out_graph(n, k)
        assert all(d == k for v, d in G.out_degree())
        G = random_uniform_k_out_graph(n, k, seed=42)
        assert all(d == k for v, d in G.out_degree())

    def test_no_self_loops(self):
        """Tests for forbidding self-loops."""
        n = 10
        k = 3
        G = random_uniform_k_out_graph(n, k, self_loops=False)
        assert nx.number_of_selfloops(G) == 0
        assert all(d == k for v, d in G.out_degree())

    def test_with_replacement(self):
        n = 10
        k = 3
        G = random_uniform_k_out_graph(n, k, with_replacement=True)
        assert G.is_multigraph()
        assert all(d == k for v, d in G.out_degree())
        n = 10
        k = 9
        G = random_uniform_k_out_graph(n, k, with_replacement=False, self_loops=False)
        assert nx.number_of_selfloops(G) == 0
        assert all(d == k for v, d in G.out_degree())

    def test_without_replacement(self):
        n = 10
        k = 3
        G = random_uniform_k_out_graph(n, k, with_replacement=False)
        assert not G.is_multigraph()
        assert all(d == k for v, d in G.out_degree())
