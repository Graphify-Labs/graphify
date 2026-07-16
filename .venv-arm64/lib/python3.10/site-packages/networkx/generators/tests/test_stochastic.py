"""Unit tests for the :mod:`networkx.generators.stochastic` module."""

import pytest

import networkx as nx


class TestStochasticGraph:
    """Unit tests for the :func:`~networkx.stochastic_graph` function."""

    def test_default_weights(self):
        G = nx.DiGraph()
        G.add_edge(0, 1)
        G.add_edge(0, 2)
        S = nx.stochastic_graph(G)
        assert nx.is_isomorphic(G, S)
        assert sorted(S.edges(data=True)) == [
            (0, 1, {"weight": 0.5}),
            (0, 2, {"weight": 0.5}),
        ]

    def test_in_place(self):
        """Tests for an in-place reweighting of the edges of the graph."""
        G = nx.DiGraph()
        G.add_edge(0, 1, weight=1)
        G.add_edge(0, 2, weight=1)
        nx.stochastic_graph(G, copy=False)
        assert sorted(G.edges(data=True)) == [
            (0, 1, {"weight": 0.5}),
            (0, 2, {"weight": 0.5}),
        ]

    def test_arbitrary_weights(self):
        G = nx.DiGraph()
        G.add_edge(0, 1, weight=1)
        G.add_edge(0, 2, weight=1)
        S = nx.stochastic_graph(G)
        assert sorted(S.edges(data=True)) == [
            (0, 1, {"weight": 0.5}),
            (0, 2, {"weight": 0.5}),
        ]

    def test_multidigraph(self):
        G = nx.MultiDiGraph()
        G.add_edges_from([(0, 1), (0, 1), (0, 2), (0, 2)])
        S = nx.stochastic_graph(G)
        d = {"weight": 0.25}
        assert sorted(S.edges(data=True)) == [
            (0, 1, d),
            (0, 1, d),
            (0, 2, d),
            (0, 2, d),
        ]

    def test_zero_weights(self):
        """Smoke test: ensure ZeroDivisionError is not raised."""
        G = nx.DiGraph()
        G.add_edge(0, 1, weight=0)
        G.add_edge(0, 2, weight=0)
        S = nx.stochastic_graph(G)
        assert sorted(S.edges(data=True)) == [
            (0, 1, {"weight": 0}),
            (0, 2, {"weight": 0}),
        ]

    def test_graph_disallowed(self):
        with pytest.raises(nx.NetworkXNotImplemented):
            nx.stochastic_graph(nx.Graph())

    def test_multigraph_disallowed(self):
        with pytest.raises(nx.NetworkXNotImplemented):
            nx.stochastic_graph(nx.MultiGraph())
