import pytest

import networkx as nx
from networkx.algorithms import bipartite
from networkx.utils import edges_equal, nodes_equal


class TestBipartiteProject:
    def test_path_projected_graph(self):
        G = nx.path_graph(4)
        P = bipartite.projected_graph(G, [1, 3])
        assert nodes_equal(list(P), [1, 3])
        assert edges_equal(list(P.edges()), [(1, 3)])
        P = bipartite.projected_graph(G, [0, 2])
        assert nodes_equal(list(P), [0, 2])
        assert edges_equal(list(P.edges()), [(0, 2)])
        G = nx.MultiGraph([(0, 1)])
        with pytest.raises(nx.NetworkXError, match="not defined for multigraphs"):
            bipartite.projected_graph(G, [0])

    def test_path_projected_properties_graph(self):
        G = nx.path_graph(4)
        G.add_node(1, name="one")
        G.add_node(2, name="two")
        P = bipartite.projected_graph(G, [1, 3])
        assert nodes_equal(list(P), [1, 3])
        assert edges_equal(list(P.edges()), [(1, 3)])
        assert P.nodes[1]["name"] == G.nodes[1]["name"]
        P = bipartite.projected_graph(G, [0, 2])
        assert nodes_equal(list(P), [0, 2])
        assert edges_equal(list(P.edges()), [(0, 2)])
        assert P.nodes[2]["name"] == G.nodes[2]["name"]

    def test_path_collaboration_projected_graph(self):
        G = nx.path_graph(4)
        P = bipartite.collaboration_weighted_projected_graph(G, [1, 3])
        assert nodes_equal(list(P), [1, 3])
        assert edges_equal(list(P.edges()), [(1, 3)])
        P[1][3]["weight"] = 1
        P = bipartite.collaboration_weighted_projected_graph(G, [0, 2])
        assert nodes_equal(list(P), [0, 2])
        assert edges_equal(list(P.edges()), [(0, 2)])
        P[0][2]["weight"] = 1

    def test_directed_path_collaboration_projected_graph(self):
        G = nx.DiGraph()
        nx.add_path(G, range(4))
        P = bipartite.collaboration_weighted_projected_graph(G, [1, 3])
        assert nodes_equal(list(P), [1, 3])
        assert edges_equal(list(P.edges()), [(1, 3)])
        P[1][3]["weight"] = 1
        P = bipartite.collaboration_weighted_projected_graph(G, [0, 2])
        assert nodes_equal(list(P), [0, 2])
        assert edges_equal(list(P.edges()), [(0, 2)])
        P[0][2]["weight"] = 1

    def test_path_weighted_projected_graph(self):
        G = nx.path_graph(4)

        with pytest.raises(nx.NetworkXAlgorithmError):
            bipartite.weighted_projected_graph(G, [1, 2, 3, 3])

        P = bipartite.weighted_projected_graph(G, [1, 3])
        assert nodes_equal(list(P), [1, 3])
        assert edges_equal(list(P.edges()), [(1, 3)])
        P[1][3]["weight"] = 1
        P = bipartite.weighted_projected_graph(G, [0, 2])
        assert nodes_equal(list(P), [0, 2])
        assert edges_equal(list(P.edges()), [(0, 2)])
        P[0][2]["weight"] = 1

    def test_digraph_weighted_projection(self):
        G = nx.DiGraph([(0, 1), (1, 2), (2, 3), (3, 4)])
        P = bipartite.overlap_weighted_projected_graph(G, [1, 3])
        assert nx.get_edge_attributes(P, "weight") == {(1, 3): 1.0}
        assert len(P) == 2

    def test_path_weighted_projected_directed_graph(self):
        G = nx.DiGraph()
        nx.add_path(G, range(4))
        P = bipartite.weighted_projected_graph(G, [1, 3])
        assert nodes_equal(list(P), [1, 3])
        assert edges_equal(list(P.edges()), [(1, 3)])
        P[1][3]["weight"] = 1
        P = bipartite.weighted_projected_graph(G, [0, 2])
        assert nodes_equal(list(P), [0, 2])
        assert edges_equal(list(P.edges()), [(0, 2)])
        P[0][2]["weight"] = 1

    def test_star_projected_graph(self):
        G = nx.star_graph(3)
        P = bipartite.projected_graph(G, [1, 2, 3])
        assert nodes_equal(list(P), [1, 2, 3])
        assert edges_equal(list(P.edges()), [(1, 2), (1, 3), (2, 3)])
        P = bipartite.weighted_projected_graph(G, [1, 2, 3])
        assert nodes_equal(list(P), [1, 2, 3])
        assert edges_equal(list(P.edges()), [(1, 2), (1, 3), (2, 3)])

        P = bipartite.projected_graph(G, [0])
        assert nodes_equal(list(P), [0])
        assert edges_equal(list(P.edges()), [])

    def test_project_multigraph(self):
        G = nx.Graph()
        G.add_edge("a", 1)
        G.add_edge("b", 1)
        G.add_edge("a", 2)
        G.add_edge("b", 2)
        P = bipartite.projected_graph(G, "ab")
        assert edges_equal(list(P.edges()), [("a", "b")])
        P = bipartite.weighted_projected_graph(G, "ab")
        assert edges_equal(list(P.edges()), [("a", "b")])
        P = bipartite.projected_graph(G, "ab", multigraph=True)
        assert edges_equal(list(P.edges()), [("a", "b"), ("a", "b")])

    def test_project_collaboration(self):
        G = nx.Graph()
        G.add_edge("a", 1)
        G.add_edge("b", 1)
        G.add_edge("b", 2)
        G.add_edge("c", 2)
        G.add_edge("c", 3)
        G.add_edge("c", 4)
        G.add_edge("b", 4)
        P = bipartite.collaboration_weighted_projected_graph(G, "abc")
        assert P["a"]["b"]["weight"] == 1
        assert P["b"]["c"]["weight"] == 2

    def test_directed_projection(self):
        G = nx.DiGraph()
        G.add_edge("A", 1)
        G.add_edge(1, "B")
        G.add_edge("A", 2)
        G.add_edge("B", 2)
        P = bipartite.projected_graph(G, "AB")
        assert edges_equal(list(P.edges()), [("A", "B")])
        P = bipartite.weighted_projected_graph(G, "AB")
        assert edges_equal(list(P.edges()), [("A", "B")])
        assert P["A"]["B"]["weight"] == 1

        P = bipartite.projected_graph(G, "AB", multigraph=True)
        assert edges_equal(list(P.edges()), [("A", "B")])

        G = nx.DiGraph()
        G.add_edge("A", 1)
        G.add_edge(1, "B")
        G.add_edge("A", 2)
        G.add_edge(2, "B")
        P = bipartite.projected_graph(G, "AB")
        assert edges_equal(list(P.edges()), [("A", "B")])
        P = bipartite.weighted_projected_graph(G, "AB")
        assert edges_equal(list(P.edges()), [("A", "B")])
        assert P["A"]["B"]["weight"] == 2

        P = bipartite.projected_graph(G, "AB", multigraph=True)
        assert edges_equal(list(P.edges()), [("A", "B"), ("A", "B")])


class TestBipartiteWeightedProjection:
    @classmethod
    def setup_class(cls):
        # Tore Opsahl's example
        # http://toreopsahl.com/2009/05/01/projecting-two-mode-networks-onto-weighted-one-mode-networks/
        cls.G = nx.Graph()
        cls.G.add_edge("A", 1)
        cls.G.add_edge("A", 2)
        cls.G.add_edge("B", 1)
        cls.G.add_edge("B", 2)
        cls.G.add_edge("B", 3)
        cls.G.add_edge("B", 4)
        cls.G.add_edge("B", 5)
        cls.G.add_edge("C", 1)
        cls.G.add_edge("D", 3)
        cls.G.add_edge("E", 4)
        cls.G.add_edge("E", 5)
        cls.G.add_edge("E", 6)
        cls.G.add_edge("F", 6)
        # Graph based on figure 6 from Newman (2001)
        cls.N = nx.Graph()
        cls.N.add_edge("A", 1)
        cls.N.add_edge("A", 2)
        cls.N.add_edge("A", 3)
        cls.N.add_edge("B", 1)
        cls.N.add_edge("B", 2)
        cls.N.add_edge("B", 3)
        cls.N.add_edge("C", 1)
        cls.N.add_edge("D", 1)
        cls.N.add_edge("E", 3)

    def test_project_weighted_shared(self):
        edges = [
            ("A", "B", 2),
            ("A", "C", 1),
            ("B", "C", 1),
            ("B", "D", 1),
            ("B", "E", 2),
            ("E", "F", 1),
        ]
        Panswer = nx.Graph()
        Panswer.add_weighted_edges_from(edges)
        P = bipartite.weighted_projected_graph(self.G, "ABCDEF")
        assert edges_equal(list(P.edges()), Panswer.edges())
        for u, v in list(P.edges()):
            assert P[u][v]["weight"] == Panswer[u][v]["weight"]

        edges = [
            ("A", "B", 3),
            ("A", "E", 1),
            ("A", "C", 1),
            ("A", "D", 1),
            ("B", "E", 1),
            ("B", "C", 1),
            ("B", "D", 1),
            ("C", "D", 1),
        ]
        Panswer = nx.Graph()
        Panswer.add_weighted_edges_from(edges)
        P = bipartite.weighted_projected_graph(self.N, "ABCDE")
        assert edges_equal(list(P.edges()), Panswer.edges())
        for u, v in list(P.edges()):
            assert P[u][v]["weight"] == Panswer[u][v]["weight"]

    def test_project_weighted_newman(self):
        edges = [
            ("A", "B", 1.5),
            ("A", "C", 0.5),
            ("B", "C", 0.5),
            ("B", "D", 1),
            ("B", "E", 2),
            ("E", "F", 1),
        ]
        Panswer = nx.Graph()
        Panswer.add_weighted_edges_from(edges)
        P = bipartite.collaboration_weighted_projected_graph(self.G, "ABCDEF")
        assert edges_equal(list(P.edges()), Panswer.edges())
        for u, v in list(P.edges()):
            assert P[u][v]["weight"] == Panswer[u][v]["weight"]

        edges = [
            ("A", "B", 11 / 6.0),
            ("A", "E", 1 / 2.0),
            ("A", "C", 1 / 3.0),
            ("A", "D", 1 / 3.0),
            ("B", "E", 1 / 2.0),
            ("B", "C", 1 / 3.0),
            ("B", "D", 1 / 3.0),
            ("C", "D", 1 / 3.0),
        ]
        Panswer = nx.Graph()
        Panswer.add_weighted_edges_from(edges)
        P = bipartite.collaboration_weighted_projected_graph(self.N, "ABCDE")
        assert edges_equal(list(P.edges()), Panswer.edges())
        for u, v in list(P.edges()):
            assert P[u][v]["weight"] == Panswer[u][v]["weight"]

    def test_project_weighted_ratio(self):
        edges = [
            ("A", "B", 2 / 6.0),
            ("A", "C", 1 / 6.0),
            ("B", "C", 1 / 6.0),
            ("B", "D", 1 / 6.0),
            ("B", "E", 2 / 6.0),
            ("E", "F", 1 / 6.0),
        ]
        Panswer = nx.Graph()
        Panswer.add_weighted_edges_from(edges)
        P = bipartite.weighted_projected_graph(self.G, "ABCDEF", ratio=True)
        assert edges_equal(list(P.edges()), Panswer.edges())
        for u, v in list(P.edges()):
            assert P[u][v]["weight"] == Panswer[u][v]["weight"]

        edges = [
            ("A", "B", 3 / 3.0),
            ("A", "E", 1 / 3.0),
            ("A", "C", 1 / 3.0),
            ("A", "D", 1 / 3.0),
            ("B", "E", 1 / 3.0),
            ("B", "C", 1 / 3.0),
            ("B", "D", 1 / 3.0),
            ("C", "D", 1 / 3.0),
        ]
        Panswer = nx.Graph()
        Panswer.add_weighted_edges_from(edges)
        P = bipartite.weighted_projected_graph(self.N, "ABCDE", ratio=True)
        assert edges_equal(list(P.edges()), Panswer.edges())
        for u, v in list(P.edges()):
            assert P[u][v]["weight"] == Panswer[u][v]["weight"]

    def test_project_weighted_overlap(self):
        edges = [
            ("A", "B", 2 / 2.0),
            ("A", "C", 1 / 1.0),
            ("B", "C", 1 / 1.0),
            ("B", "D", 1 / 1.0),
            ("B", "E", 2 / 3.0),
            ("E", "F", 1 / 1.0),
        ]
        Panswer = nx.Graph()
        Panswer.add_weighted_edges_from(edges)
        P = bipartite.overlap_weighted_projected_graph(self.G, "ABCDEF", jaccard=False)
        assert edges_equal(list(P.edges()), Panswer.edges())
        for u, v in list(P.edges()):
            assert P[u][v]["weight"] == Panswer[u][v]["weight"]

        edges = [
            ("A", "B", 3 / 3.0),
            ("A", "E", 1 / 1.0),
            ("A", "C", 1 / 1.0),
            ("A", "D", 1 / 1.0),
            ("B", "E", 1 / 1.0),
            ("B", "C", 1 / 1.0),
            ("B", "D", 1 / 1.0),
            ("C", "D", 1 / 1.0),
        ]
        Panswer = nx.Graph()
        Panswer.add_weighted_edges_from(edges)
        P = bipartite.overlap_weighted_projected_graph(self.N, "ABCDE", jaccard=False)
        assert edges_equal(list(P.edges()), Panswer.edges())
        for u, v in list(P.edges()):
            assert P[u][v]["weight"] == Panswer[u][v]["weight"]

    def test_project_weighted_jaccard(self):
        edges = [
            ("A", "B", 2 / 5.0),
            ("A", "C", 1 / 2.0),
            ("B", "C", 1 / 5.0),
            ("B", "D", 1 / 5.0),
            ("B", "E", 2 / 6.0),
            ("E", "F", 1 / 3.0),
        ]
        Panswer = nx.Graph()
        Panswer.add_weighted_edges_from(edges)
        P = bipartite.overlap_weighted_projected_graph(self.G, "ABCDEF")
        assert edges_equal(list(P.edges()), Panswer.edges())
        for u, v in list(P.edges()):
            assert P[u][v]["weight"] == Panswer[u][v]["weight"]

        edges = [
            ("A", "B", 3 / 3.0),
            ("A", "E", 1 / 3.0),
            ("A", "C", 1 / 3.0),
            ("A", "D", 1 / 3.0),
            ("B", "E", 1 / 3.0),
            ("B", "C", 1 / 3.0),
            ("B", "D", 1 / 3.0),
            ("C", "D", 1 / 1.0),
        ]
        Panswer = nx.Graph()
        Panswer.add_weighted_edges_from(edges)
        P = bipartite.overlap_weighted_projected_graph(self.N, "ABCDE")
        assert edges_equal(list(P.edges()), Panswer.edges())
        for u, v in P.edges():
            assert P[u][v]["weight"] == Panswer[u][v]["weight"]

    def test_generic_weighted_projected_graph_simple(self):
        def shared(G, u, v):
            return len(set(G[u]) & set(G[v]))

        B = nx.path_graph(5)
        G = bipartite.generic_weighted_projected_graph(
            B, [0, 2, 4], weight_function=shared
        )
        assert nodes_equal(list(G), [0, 2, 4])
        assert edges_equal(
            list(G.edges(data=True)),
            [(0, 2, {"weight": 1}), (2, 4, {"weight": 1})],
        )

        G = bipartite.generic_weighted_projected_graph(B, [0, 2, 4])
        assert nodes_equal(list(G), [0, 2, 4])
        assert edges_equal(
            list(G.edges(data=True)),
            [(0, 2, {"weight": 1}), (2, 4, {"weight": 1})],
        )
        B = nx.DiGraph()
        nx.add_path(B, range(5))
        G = bipartite.generic_weighted_projected_graph(B, [0, 2, 4])
        assert nodes_equal(list(G), [0, 2, 4])
        assert edges_equal(
            list(G.edges(data=True)), [(0, 2, {"weight": 1}), (2, 4, {"weight": 1})]
        )

    def test_generic_weighted_projected_graph_custom(self):
        def jaccard(G, u, v):
            unbrs = set(G[u])
            vnbrs = set(G[v])
            return len(unbrs & vnbrs) / len(unbrs | vnbrs)

        def my_weight(G, u, v, weight="weight"):
            w = 0
            for nbr in set(G[u]) & set(G[v]):
                w += G.edges[u, nbr].get(weight, 1) + G.edges[v, nbr].get(weight, 1)
            return w

        B = nx.bipartite.complete_bipartite_graph(2, 2)
        for i, (u, v) in enumerate(B.edges()):
            B.edges[u, v]["weight"] = i + 1
        G = bipartite.generic_weighted_projected_graph(
            B, [0, 1], weight_function=jaccard
        )
        assert edges_equal(list(G.edges(data=True)), [(0, 1, {"weight": 1.0})])
        G = bipartite.generic_weighted_projected_graph(
            B, [0, 1], weight_function=my_weight
        )
        assert edges_equal(list(G.edges(data=True)), [(0, 1, {"weight": 10})])
        G = bipartite.generic_weighted_projected_graph(B, [0, 1])
        assert edges_equal(list(G.edges(data=True)), [(0, 1, {"weight": 2})])
