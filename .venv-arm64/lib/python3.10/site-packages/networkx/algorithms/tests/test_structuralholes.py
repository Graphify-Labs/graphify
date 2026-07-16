"""Unit tests for the :mod:`networkx.algorithms.structuralholes` module."""

import math

import pytest

import networkx as nx
from networkx.classes.tests import dispatch_interface


class TestStructuralHoles:
    """Unit tests for computing measures of structural holes.

    The expected values for these functions were originally computed using the
    proprietary software `UCINET`_ and the free software `IGraph`_ , and then
    computed by hand to make sure that the results are correct.

    .. _UCINET: https://sites.google.com/site/ucinetsoftware/home
    .. _IGraph: http://igraph.org/

    """

    def setup_method(self):
        self.D = nx.DiGraph()
        self.D.add_edges_from([(0, 1), (0, 2), (1, 0), (2, 1)])
        self.D_weights = {(0, 1): 2, (0, 2): 2, (1, 0): 1, (2, 1): 1}
        # Example from http://www.analytictech.com/connections/v20(1)/holes.htm
        self.G = nx.Graph()
        self.G.add_edges_from(
            [
                ("A", "B"),
                ("A", "F"),
                ("A", "G"),
                ("A", "E"),
                ("E", "G"),
                ("F", "G"),
                ("B", "G"),
                ("B", "D"),
                ("D", "G"),
                ("G", "C"),
            ]
        )
        self.G_weights = {
            ("A", "B"): 2,
            ("A", "F"): 3,
            ("A", "G"): 5,
            ("A", "E"): 2,
            ("E", "G"): 8,
            ("F", "G"): 3,
            ("B", "G"): 4,
            ("B", "D"): 1,
            ("D", "G"): 3,
            ("G", "C"): 10,
        }

    def test_constraint_directed(self):
        constraint = nx.constraint(self.D)
        assert constraint[0] == pytest.approx(1.003, abs=1e-3)
        assert constraint[1] == pytest.approx(1.003, abs=1e-3)
        assert constraint[2] == pytest.approx(1.389, abs=1e-3)

    def test_effective_size_directed(self):
        effective_size = nx.effective_size(self.D)
        assert effective_size[0] == pytest.approx(1.167, abs=1e-3)
        assert effective_size[1] == pytest.approx(1.167, abs=1e-3)
        assert effective_size[2] == pytest.approx(1, abs=1e-3)

    def test_constraint_weighted_directed(self):
        D = self.D.copy()
        nx.set_edge_attributes(D, self.D_weights, "weight")
        constraint = nx.constraint(D, weight="weight")
        assert constraint[0] == pytest.approx(0.840, abs=1e-3)
        assert constraint[1] == pytest.approx(1.143, abs=1e-3)
        assert constraint[2] == pytest.approx(1.378, abs=1e-3)

    def test_effective_size_weighted_directed(self):
        D = self.D.copy()
        nx.set_edge_attributes(D, self.D_weights, "weight")
        effective_size = nx.effective_size(D, weight="weight")
        assert effective_size[0] == pytest.approx(1.567, abs=1e-3)
        assert effective_size[1] == pytest.approx(1.083, abs=1e-3)
        assert effective_size[2] == pytest.approx(1, abs=1e-3)

    def test_constraint_undirected(self):
        constraint = nx.constraint(self.G)
        assert constraint["G"] == pytest.approx(0.400, abs=1e-3)
        assert constraint["A"] == pytest.approx(0.595, abs=1e-3)
        assert constraint["C"] == pytest.approx(1, abs=1e-3)

    def test_effective_size_undirected_borgatti(self):
        effective_size = nx.effective_size(self.G)
        assert effective_size["G"] == pytest.approx(4.67, abs=1e-2)
        assert effective_size["A"] == pytest.approx(2.50, abs=1e-2)
        assert effective_size["C"] == pytest.approx(1, abs=1e-2)

    def test_effective_size_undirected(self):
        G = self.G.copy()
        nx.set_edge_attributes(G, 1, "weight")
        effective_size = nx.effective_size(G, weight="weight")
        assert effective_size["G"] == pytest.approx(4.67, abs=1e-2)
        assert effective_size["A"] == pytest.approx(2.50, abs=1e-2)
        assert effective_size["C"] == pytest.approx(1, abs=1e-2)

    def test_constraint_weighted_undirected(self):
        G = self.G.copy()
        nx.set_edge_attributes(G, self.G_weights, "weight")
        constraint = nx.constraint(G, weight="weight")
        assert constraint["G"] == pytest.approx(0.299, abs=1e-3)
        assert constraint["A"] == pytest.approx(0.795, abs=1e-3)
        assert constraint["C"] == pytest.approx(1, abs=1e-3)

    def test_effective_size_weighted_undirected(self):
        G = self.G.copy()
        nx.set_edge_attributes(G, self.G_weights, "weight")
        effective_size = nx.effective_size(G, weight="weight")
        assert effective_size["G"] == pytest.approx(5.47, abs=1e-2)
        assert effective_size["A"] == pytest.approx(2.47, abs=1e-2)
        assert effective_size["C"] == pytest.approx(1, abs=1e-2)

    def test_constraint_isolated(self):
        G = self.G.copy()
        G.add_node(1)
        constraint = nx.constraint(G)
        assert math.isnan(constraint[1])

    def test_effective_size_isolated(self):
        G = self.G.copy()
        G.add_node(1)
        nx.set_edge_attributes(G, self.G_weights, "weight")
        effective_size = nx.effective_size(G, weight="weight")
        assert math.isnan(effective_size[1])

    def test_effective_size_borgatti_isolated(self):
        G = self.G.copy()
        G.add_node(1)
        effective_size = nx.effective_size(G)
        assert math.isnan(effective_size[1])
