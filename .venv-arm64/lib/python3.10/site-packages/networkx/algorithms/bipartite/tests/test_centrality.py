import pytest

import networkx as nx
from networkx.algorithms import bipartite


class TestBipartiteCentrality:
    @classmethod
    def setup_class(cls):
        cls.P4 = nx.path_graph(4)
        cls.K3 = nx.complete_bipartite_graph(3, 3)
        cls.C4 = nx.cycle_graph(4)
        cls.davis = nx.davis_southern_women_graph()
        cls.top_nodes = [
            n for n, d in cls.davis.nodes(data=True) if d["bipartite"] == 0
        ]

    def test_degree_centrality(self):
        d = bipartite.degree_centrality(self.P4, [1, 3])
        answer = {0: 0.5, 1: 1.0, 2: 1.0, 3: 0.5}
        assert d == answer
        d = bipartite.degree_centrality(self.K3, [0, 1, 2])
        answer = {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0}
        assert d == answer
        d = bipartite.degree_centrality(self.C4, [0, 2])
        answer = {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0}
        assert d == answer

    def test_betweenness_centrality(self):
        c = bipartite.betweenness_centrality(self.P4, [1, 3])
        answer = {0: 0.0, 1: 1.0, 2: 1.0, 3: 0.0}
        assert c == answer
        c = bipartite.betweenness_centrality(self.K3, [0, 1, 2])
        answer = {0: 0.125, 1: 0.125, 2: 0.125, 3: 0.125, 4: 0.125, 5: 0.125}
        assert c == answer
        c = bipartite.betweenness_centrality(self.C4, [0, 2])
        answer = {0: 0.25, 1: 0.25, 2: 0.25, 3: 0.25}
        assert c == answer

    def test_closeness_centrality(self):
        c = bipartite.closeness_centrality(self.P4, [1, 3])
        answer = {0: 2.0 / 3, 1: 1.0, 2: 1.0, 3: 2.0 / 3}
        assert c == answer
        c = bipartite.closeness_centrality(self.K3, [0, 1, 2])
        answer = {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0}
        assert c == answer
        c = bipartite.closeness_centrality(self.C4, [0, 2])
        answer = {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0}
        assert c == answer
        G = nx.Graph()
        G.add_node(0)
        G.add_node(1)
        c = bipartite.closeness_centrality(G, [0])
        assert c == {0: 0.0, 1: 0.0}
        c = bipartite.closeness_centrality(G, [1])
        assert c == {0: 0.0, 1: 0.0}

    def test_bipartite_closeness_centrality_unconnected(self):
        G = nx.complete_bipartite_graph(3, 3)
        G.add_edge(6, 7)
        c = bipartite.closeness_centrality(G, [0, 2, 4, 6], normalized=False)
        answer = {
            0: 10.0 / 7,
            2: 10.0 / 7,
            4: 10.0 / 7,
            6: 10.0,
            1: 10.0 / 7,
            3: 10.0 / 7,
            5: 10.0 / 7,
            7: 10.0,
        }
        assert c == answer

    def test_davis_degree_centrality(self):
        G = self.davis
        deg = bipartite.degree_centrality(G, self.top_nodes)
        answer = {
            "E8": 0.78,
            "E9": 0.67,
            "E7": 0.56,
            "Nora Fayette": 0.57,
            "Evelyn Jefferson": 0.57,
            "Theresa Anderson": 0.57,
            "E6": 0.44,
            "Sylvia Avondale": 0.50,
            "Laura Mandeville": 0.50,
            "Brenda Rogers": 0.50,
            "Katherina Rogers": 0.43,
            "E5": 0.44,
            "Helen Lloyd": 0.36,
            "E3": 0.33,
            "Ruth DeSand": 0.29,
            "Verne Sanderson": 0.29,
            "E12": 0.33,
            "Myra Liddel": 0.29,
            "E11": 0.22,
            "Eleanor Nye": 0.29,
            "Frances Anderson": 0.29,
            "Pearl Oglethorpe": 0.21,
            "E4": 0.22,
            "Charlotte McDowd": 0.29,
            "E10": 0.28,
            "Olivia Carleton": 0.14,
            "Flora Price": 0.14,
            "E2": 0.17,
            "E1": 0.17,
            "Dorothy Murchison": 0.14,
            "E13": 0.17,
            "E14": 0.17,
        }
        for node, value in answer.items():
            assert value == pytest.approx(deg[node], abs=1e-2)

    def test_davis_betweenness_centrality(self):
        G = self.davis
        bet = bipartite.betweenness_centrality(G, self.top_nodes)
        answer = {
            "E8": 0.24,
            "E9": 0.23,
            "E7": 0.13,
            "Nora Fayette": 0.11,
            "Evelyn Jefferson": 0.10,
            "Theresa Anderson": 0.09,
            "E6": 0.07,
            "Sylvia Avondale": 0.07,
            "Laura Mandeville": 0.05,
            "Brenda Rogers": 0.05,
            "Katherina Rogers": 0.05,
            "E5": 0.04,
            "Helen Lloyd": 0.04,
            "E3": 0.02,
            "Ruth DeSand": 0.02,
            "Verne Sanderson": 0.02,
            "E12": 0.02,
            "Myra Liddel": 0.02,
            "E11": 0.02,
            "Eleanor Nye": 0.01,
            "Frances Anderson": 0.01,
            "Pearl Oglethorpe": 0.01,
            "E4": 0.01,
            "Charlotte McDowd": 0.01,
            "E10": 0.01,
            "Olivia Carleton": 0.01,
            "Flora Price": 0.01,
            "E2": 0.00,
            "E1": 0.00,
            "Dorothy Murchison": 0.00,
            "E13": 0.00,
            "E14": 0.00,
        }
        for node, value in answer.items():
            assert value == pytest.approx(bet[node], abs=1e-2)

    def test_davis_closeness_centrality(self):
        G = self.davis
        clos = bipartite.closeness_centrality(G, self.top_nodes)
        answer = {
            "E8": 0.85,
            "E9": 0.79,
            "E7": 0.73,
            "Nora Fayette": 0.80,
            "Evelyn Jefferson": 0.80,
            "Theresa Anderson": 0.80,
            "E6": 0.69,
            "Sylvia Avondale": 0.77,
            "Laura Mandeville": 0.73,
            "Brenda Rogers": 0.73,
            "Katherina Rogers": 0.73,
            "E5": 0.59,
            "Helen Lloyd": 0.73,
            "E3": 0.56,
            "Ruth DeSand": 0.71,
            "Verne Sanderson": 0.71,
            "E12": 0.56,
            "Myra Liddel": 0.69,
            "E11": 0.54,
            "Eleanor Nye": 0.67,
            "Frances Anderson": 0.67,
            "Pearl Oglethorpe": 0.67,
            "E4": 0.54,
            "Charlotte McDowd": 0.60,
            "E10": 0.55,
            "Olivia Carleton": 0.59,
            "Flora Price": 0.59,
            "E2": 0.52,
            "E1": 0.52,
            "Dorothy Murchison": 0.65,
            "E13": 0.52,
            "E14": 0.52,
        }
        for node, value in answer.items():
            assert value == pytest.approx(clos[node], abs=1e-2)
