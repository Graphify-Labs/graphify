import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")


import networkx as nx
from networkx.algorithms.assortativity.correlation import attribute_ac

from .base_test import BaseTestAttributeMixing, BaseTestDegreeMixing


class TestDegreeMixingCorrelation(BaseTestDegreeMixing):
    def test_degree_assortativity_undirected(self):
        r = nx.degree_assortativity_coefficient(self.P4)
        np.testing.assert_almost_equal(r, -1.0 / 2, decimal=4)

    def test_degree_assortativity_node_kwargs(self):
        G = nx.Graph()
        edges = [(0, 1), (0, 3), (1, 2), (1, 3), (1, 4), (5, 9), (9, 0)]
        G.add_edges_from(edges)
        r = nx.degree_assortativity_coefficient(G, nodes=[1, 2, 4])
        np.testing.assert_almost_equal(r, -1.0, decimal=4)

    def test_degree_assortativity_directed(self):
        r = nx.degree_assortativity_coefficient(self.D)
        np.testing.assert_almost_equal(r, -0.57735, decimal=4)

    def test_degree_assortativity_directed2(self):
        """Test degree assortativity for a directed graph where the set of
        in/out degree does not equal the total degree."""
        r = nx.degree_assortativity_coefficient(self.D2)
        np.testing.assert_almost_equal(r, 0.14852, decimal=4)

    def test_degree_assortativity_multigraph(self):
        r = nx.degree_assortativity_coefficient(self.M)
        np.testing.assert_almost_equal(r, -1.0 / 7.0, decimal=4)

    def test_degree_pearson_assortativity_undirected(self):
        r = nx.degree_pearson_correlation_coefficient(self.P4)
        np.testing.assert_almost_equal(r, -1.0 / 2, decimal=4)

    def test_degree_pearson_assortativity_directed(self):
        r = nx.degree_pearson_correlation_coefficient(self.D)
        np.testing.assert_almost_equal(r, -0.57735, decimal=4)

    def test_degree_pearson_assortativity_directed2(self):
        """Test degree assortativity with Pearson for a directed graph where
        the set of in/out degree does not equal the total degree."""
        r = nx.degree_pearson_correlation_coefficient(self.D2)
        np.testing.assert_almost_equal(r, 0.14852, decimal=4)

    def test_degree_pearson_assortativity_multigraph(self):
        r = nx.degree_pearson_correlation_coefficient(self.M)
        np.testing.assert_almost_equal(r, -1.0 / 7.0, decimal=4)

    def test_degree_assortativity_weighted(self):
        r = nx.degree_assortativity_coefficient(self.W, weight="weight")
        np.testing.assert_almost_equal(r, -0.1429, decimal=4)

    def test_degree_assortativity_double_star(self):
        r = nx.degree_assortativity_coefficient(self.DS)
        np.testing.assert_almost_equal(r, -0.9339, decimal=4)


class TestAttributeMixingCorrelation(BaseTestAttributeMixing):
    def test_attribute_assortativity_undirected(self):
        r = nx.attribute_assortativity_coefficient(self.G, "fish")
        assert r == 6.0 / 22.0

    def test_attribute_assortativity_directed(self):
        r = nx.attribute_assortativity_coefficient(self.D, "fish")
        assert r == 1.0 / 3.0

    def test_attribute_assortativity_multigraph(self):
        r = nx.attribute_assortativity_coefficient(self.M, "fish")
        assert r == 1.0

    def test_attribute_assortativity_coefficient(self):
        # from "Mixing patterns in networks"
        # fmt: off
        a = np.array([[0.258, 0.016, 0.035, 0.013],
                      [0.012, 0.157, 0.058, 0.019],
                      [0.013, 0.023, 0.306, 0.035],
                      [0.005, 0.007, 0.024, 0.016]])
        # fmt: on
        r = attribute_ac(a)
        np.testing.assert_almost_equal(r, 0.623, decimal=3)

    def test_attribute_assortativity_coefficient2(self):
        # fmt: off
        a = np.array([[0.18, 0.02, 0.01, 0.03],
                      [0.02, 0.20, 0.03, 0.02],
                      [0.01, 0.03, 0.16, 0.01],
                      [0.03, 0.02, 0.01, 0.22]])
        # fmt: on
        r = attribute_ac(a)
        np.testing.assert_almost_equal(r, 0.68, decimal=2)

    def test_attribute_assortativity(self):
        a = np.array([[50, 50, 0], [50, 50, 0], [0, 0, 2]])
        r = attribute_ac(a)
        np.testing.assert_almost_equal(r, 0.029, decimal=3)

    def test_attribute_assortativity_negative(self):
        r = nx.numeric_assortativity_coefficient(self.N, "margin")
        np.testing.assert_almost_equal(r, -0.2903, decimal=4)

    def test_assortativity_node_kwargs(self):
        G = nx.Graph()
        G.add_nodes_from([0, 1], size=2)
        G.add_nodes_from([2, 3], size=3)
        G.add_edges_from([(0, 1), (2, 3)])
        r = nx.numeric_assortativity_coefficient(G, "size", nodes=[0, 3])
        np.testing.assert_almost_equal(r, 1.0, decimal=4)

    def test_attribute_assortativity_float(self):
        r = nx.numeric_assortativity_coefficient(self.F, "margin")
        np.testing.assert_almost_equal(r, -0.1429, decimal=4)

    def test_attribute_assortativity_mixed(self):
        r = nx.numeric_assortativity_coefficient(self.K, "margin")
        np.testing.assert_almost_equal(r, 0.4340, decimal=4)
