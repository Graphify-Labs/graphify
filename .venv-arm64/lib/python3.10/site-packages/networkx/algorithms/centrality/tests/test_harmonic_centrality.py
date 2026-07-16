"""
Tests for degree centrality.
"""

import pytest

import networkx as nx
from networkx.algorithms.centrality import harmonic_centrality


class TestClosenessCentrality:
    @classmethod
    def setup_class(cls):
        cls.P3 = nx.path_graph(3)
        cls.P4 = nx.path_graph(4)
        cls.K5 = nx.complete_graph(5)

        cls.C4 = nx.cycle_graph(4)
        cls.C4_directed = nx.cycle_graph(4, create_using=nx.DiGraph)

        cls.C5 = nx.cycle_graph(5)

        cls.T = nx.balanced_tree(r=2, h=2)

        cls.Gb = nx.DiGraph()
        cls.Gb.add_edges_from([(0, 1), (0, 2), (0, 4), (2, 1), (2, 3), (4, 3)])

    def test_p3_harmonic(self):
        c = harmonic_centrality(self.P3)
        d = {0: 1.5, 1: 2, 2: 1.5}
        for n in sorted(self.P3):
            assert c[n] == pytest.approx(d[n], abs=1e-3)

    def test_p4_harmonic(self):
        c = harmonic_centrality(self.P4)
        d = {0: 1.8333333, 1: 2.5, 2: 2.5, 3: 1.8333333}
        for n in sorted(self.P4):
            assert c[n] == pytest.approx(d[n], abs=1e-3)

    def test_clique_complete(self):
        c = harmonic_centrality(self.K5)
        d = {0: 4, 1: 4, 2: 4, 3: 4, 4: 4}
        for n in sorted(self.P3):
            assert c[n] == pytest.approx(d[n], abs=1e-3)

    def test_cycle_C4(self):
        c = harmonic_centrality(self.C4)
        d = {0: 2.5, 1: 2.5, 2: 2.5, 3: 2.5}
        for n in sorted(self.C4):
            assert c[n] == pytest.approx(d[n], abs=1e-3)

    def test_cycle_C5(self):
        c = harmonic_centrality(self.C5)
        d = {0: 3, 1: 3, 2: 3, 3: 3, 4: 3, 5: 4}
        for n in sorted(self.C5):
            assert c[n] == pytest.approx(d[n], abs=1e-3)

    def test_bal_tree(self):
        c = harmonic_centrality(self.T)
        d = {0: 4.0, 1: 4.1666, 2: 4.1666, 3: 2.8333, 4: 2.8333, 5: 2.8333, 6: 2.8333}
        for n in sorted(self.T):
            assert c[n] == pytest.approx(d[n], abs=1e-3)

    def test_exampleGraph(self):
        c = harmonic_centrality(self.Gb)
        d = {0: 0, 1: 2, 2: 1, 3: 2.5, 4: 1}
        for n in sorted(self.Gb):
            assert c[n] == pytest.approx(d[n], abs=1e-3)

    def test_weighted_harmonic(self):
        XG = nx.DiGraph()
        XG.add_weighted_edges_from(
            [
                ("a", "b", 10),
                ("d", "c", 5),
                ("a", "c", 1),
                ("e", "f", 2),
                ("f", "c", 1),
                ("a", "f", 3),
            ]
        )
        c = harmonic_centrality(XG, distance="weight")
        d = {"a": 0, "b": 0.1, "c": 2.533, "d": 0, "e": 0, "f": 0.83333}
        for n in sorted(XG):
            assert c[n] == pytest.approx(d[n], abs=1e-3)

    def test_empty(self):
        G = nx.DiGraph()
        c = harmonic_centrality(G, distance="weight")
        d = {}
        assert c == d

    def test_singleton(self):
        G = nx.DiGraph()
        G.add_node(0)
        c = harmonic_centrality(G, distance="weight")
        d = {0: 0}
        assert c == d

    def test_cycle_c4_directed(self):
        c = harmonic_centrality(self.C4_directed, nbunch=[0, 1], sources=[1, 2])
        d = {0: 0.833, 1: 0.333}
        for n in [0, 1]:
            assert c[n] == pytest.approx(d[n], abs=1e-3)

    def test_cycle_c4_directed_subset(self):
        c = harmonic_centrality(self.C4_directed, nbunch=[0, 1])
        d = 1.833
        for n in [0, 1]:
            assert c[n] == pytest.approx(d, abs=1e-3)

    def test_p3_harmonic_subset(self):
        c = harmonic_centrality(self.P3, sources=[0, 1])
        d = {0: 1, 1: 1, 2: 1.5}
        for n in self.P3:
            assert c[n] == pytest.approx(d[n], abs=1e-3)

    def test_p4_harmonic_subset(self):
        c = harmonic_centrality(self.P4, nbunch=[2, 3], sources=[0, 1])
        d = {2: 1.5, 3: 0.8333333}
        for n in [2, 3]:
            assert c[n] == pytest.approx(d[n], abs=1e-3)
