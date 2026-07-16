"""Unit tests for the :mod:`networkx.algorithms.approximation.distance_measures` module."""

import pytest

import networkx as nx
from networkx.algorithms.approximation import diameter


class TestDiameter:
    """Unit tests for the approximate diameter function
    :func:`~networkx.algorithms.approximation.distance_measures.diameter`.
    """

    def test_null_graph(self):
        """Test empty graph."""
        G = nx.null_graph()
        with pytest.raises(
            nx.NetworkXError, match="Expected non-empty NetworkX graph!"
        ):
            diameter(G)

    def test_undirected_non_connected(self):
        """Test an undirected disconnected graph."""
        graph = nx.path_graph(10)
        graph.remove_edge(3, 4)
        with pytest.raises(nx.NetworkXError, match="Graph not connected."):
            diameter(graph)

    def test_directed_non_strongly_connected(self):
        """Test a directed non strongly connected graph."""
        graph = nx.path_graph(10, create_using=nx.DiGraph())
        with pytest.raises(nx.NetworkXError, match="DiGraph not strongly connected."):
            diameter(graph)

    def test_complete_undirected_graph(self):
        """Test a complete undirected graph."""
        graph = nx.complete_graph(10)
        assert diameter(graph) == 1

    def test_complete_directed_graph(self):
        """Test a complete directed graph."""
        graph = nx.complete_graph(10, create_using=nx.DiGraph())
        assert diameter(graph) == 1

    def test_undirected_path_graph(self):
        """Test an undirected path graph with 10 nodes."""
        graph = nx.path_graph(10)
        assert diameter(graph) == 9

    def test_directed_path_graph(self):
        """Test a directed path graph with 10 nodes."""
        graph = nx.path_graph(10).to_directed()
        assert diameter(graph) == 9

    def test_single_node(self):
        """Test a graph which contains just a node."""
        graph = nx.Graph()
        graph.add_node(1)
        assert diameter(graph) == 0
