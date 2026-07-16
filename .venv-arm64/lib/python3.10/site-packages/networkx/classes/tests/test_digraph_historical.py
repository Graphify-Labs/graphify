"""Original NetworkX graph tests"""

import pytest

import networkx
import networkx as nx

from .historical_tests import HistoricalTests


class TestDiGraphHistorical(HistoricalTests):
    @classmethod
    def setup_class(cls):
        HistoricalTests.setup_class()
        cls.G = nx.DiGraph

    def test_in_degree(self):
        G = self.G()
        G.add_nodes_from("GJK")
        G.add_edges_from([("A", "B"), ("A", "C"), ("B", "D"), ("B", "C"), ("C", "D")])

        assert sorted(d for n, d in G.in_degree()) == [0, 0, 0, 0, 1, 2, 2]
        assert dict(G.in_degree()) == {
            "A": 0,
            "C": 2,
            "B": 1,
            "D": 2,
            "G": 0,
            "K": 0,
            "J": 0,
        }

    def test_out_degree(self):
        G = self.G()
        G.add_nodes_from("GJK")
        G.add_edges_from([("A", "B"), ("A", "C"), ("B", "D"), ("B", "C"), ("C", "D")])
        assert sorted(v for k, v in G.in_degree()) == [0, 0, 0, 0, 1, 2, 2]
        assert dict(G.out_degree()) == {
            "A": 2,
            "C": 1,
            "B": 2,
            "D": 0,
            "G": 0,
            "K": 0,
            "J": 0,
        }

    def test_degree_digraph(self):
        H = nx.DiGraph()
        H.add_edges_from([(1, 24), (1, 2)])
        assert sorted(d for n, d in H.in_degree([1, 24])) == [0, 1]
        assert sorted(d for n, d in H.out_degree([1, 24])) == [0, 2]
        assert sorted(d for n, d in H.degree([1, 24])) == [1, 2]

    def test_neighbors(self):
        G = self.G()
        G.add_nodes_from("GJK")
        G.add_edges_from([("A", "B"), ("A", "C"), ("B", "D"), ("B", "C"), ("C", "D")])

        assert sorted(G.neighbors("C")) == ["D"]
        assert sorted(G["C"]) == ["D"]
        assert sorted(G.neighbors("A")) == ["B", "C"]
        pytest.raises(nx.NetworkXError, G.neighbors, "j")
        pytest.raises(nx.NetworkXError, G.neighbors, "j")

    def test_successors(self):
        G = self.G()
        G.add_nodes_from("GJK")
        G.add_edges_from([("A", "B"), ("A", "C"), ("B", "D"), ("B", "C"), ("C", "D")])
        assert sorted(G.successors("A")) == ["B", "C"]
        assert sorted(G.successors("A")) == ["B", "C"]
        assert sorted(G.successors("G")) == []
        assert sorted(G.successors("D")) == []
        assert sorted(G.successors("G")) == []
        pytest.raises(nx.NetworkXError, G.successors, "j")
        pytest.raises(nx.NetworkXError, G.successors, "j")

    def test_predecessors(self):
        G = self.G()
        G.add_nodes_from("GJK")
        G.add_edges_from([("A", "B"), ("A", "C"), ("B", "D"), ("B", "C"), ("C", "D")])
        assert sorted(G.predecessors("C")) == ["A", "B"]
        assert sorted(G.predecessors("C")) == ["A", "B"]
        assert sorted(G.predecessors("G")) == []
        assert sorted(G.predecessors("A")) == []
        assert sorted(G.predecessors("G")) == []
        assert sorted(G.predecessors("A")) == []
        assert sorted(G.successors("D")) == []

        pytest.raises(nx.NetworkXError, G.predecessors, "j")
        pytest.raises(nx.NetworkXError, G.predecessors, "j")

    def test_reverse(self):
        G = nx.complete_graph(10)
        H = G.to_directed()
        HR = H.reverse()
        assert nx.is_isomorphic(H, HR)
        assert sorted(H.edges()) == sorted(HR.edges())

    def test_reverse2(self):
        H = nx.DiGraph()
        foo = [H.add_edge(u, u + 1) for u in range(5)]
        HR = H.reverse()
        for u in range(5):
            assert HR.has_edge(u + 1, u)

    def test_reverse3(self):
        H = nx.DiGraph()
        H.add_nodes_from([1, 2, 3, 4])
        HR = H.reverse()
        assert sorted(HR.nodes()) == [1, 2, 3, 4]
