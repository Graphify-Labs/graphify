"""Unit tests for the :mod:`networkx.generators.duplication` module."""

import pytest

import networkx as nx


class TestDuplicationDivergenceGraph:
    """Unit tests for the
    :func:`networkx.generators.duplication.duplication_divergence_graph`
    function.

    """

    def test_final_size(self):
        G = nx.duplication_divergence_graph(3, p=1)
        assert len(G) == 3
        G = nx.duplication_divergence_graph(3, p=1, seed=42)
        assert len(G) == 3

    def test_probability_too_large(self):
        with pytest.raises(nx.NetworkXError):
            nx.duplication_divergence_graph(3, p=2)

    def test_probability_too_small(self):
        with pytest.raises(nx.NetworkXError):
            nx.duplication_divergence_graph(3, p=-1)

    def test_non_extreme_probability_value(self):
        G = nx.duplication_divergence_graph(6, p=0.3, seed=42)
        assert len(G) == 6
        assert list(G.degree()) == [(0, 2), (1, 3), (2, 2), (3, 3), (4, 1), (5, 1)]

    def test_minimum_desired_nodes(self):
        with pytest.raises(
            nx.NetworkXError, match=".*n must be greater than or equal to 2"
        ):
            nx.duplication_divergence_graph(1, p=1)

    def test_create_using(self):
        class DummyGraph(nx.Graph):
            pass

        class DummyDiGraph(nx.DiGraph):
            pass

        G = nx.duplication_divergence_graph(6, 0.3, seed=42, create_using=DummyGraph)
        assert isinstance(G, DummyGraph)
        with pytest.raises(nx.NetworkXError, match="create_using must not be directed"):
            nx.duplication_divergence_graph(6, 0.3, seed=42, create_using=DummyDiGraph)


class TestPartialDuplicationGraph:
    """Unit tests for the
    :func:`networkx.generators.duplication.partial_duplication_graph`
    function.

    """

    def test_final_size(self):
        N = 10
        n = 5
        p = 0.5
        q = 0.5
        G = nx.partial_duplication_graph(N, n, p, q)
        assert len(G) == N
        G = nx.partial_duplication_graph(N, n, p, q, seed=42)
        assert len(G) == N

    def test_initial_clique_size(self):
        N = 10
        n = 10
        p = 0.5
        q = 0.5
        G = nx.partial_duplication_graph(N, n, p, q)
        assert len(G) == n

    def test_invalid_initial_size(self):
        with pytest.raises(nx.NetworkXError):
            N = 5
            n = 10
            p = 0.5
            q = 0.5
            G = nx.partial_duplication_graph(N, n, p, q)

    def test_invalid_probabilities(self):
        N = 1
        n = 1
        for p, q in [(0.5, 2), (0.5, -1), (2, 0.5), (-1, 0.5)]:
            args = (N, n, p, q)
            pytest.raises(nx.NetworkXError, nx.partial_duplication_graph, *args)

    def test_create_using(self):
        class DummyGraph(nx.Graph):
            pass

        class DummyDiGraph(nx.DiGraph):
            pass

        G = nx.partial_duplication_graph(10, 5, 0.5, 0.5, create_using=DummyGraph)
        assert isinstance(G, DummyGraph)
        with pytest.raises(nx.NetworkXError, match="create_using must not be directed"):
            nx.partial_duplication_graph(10, 5, 0.5, 0.5, create_using=DummyDiGraph)
