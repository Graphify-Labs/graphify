"""
ego graph
---------
"""

import networkx as nx
from networkx.utils import edges_equal, nodes_equal


class TestGeneratorEgo:
    def test_ego(self):
        G = nx.star_graph(3)
        H = nx.ego_graph(G, 0)
        assert nx.is_isomorphic(G, H)
        G.add_edge(1, 11)
        G.add_edge(2, 22)
        G.add_edge(3, 33)
        H = nx.ego_graph(G, 0)
        assert nx.is_isomorphic(nx.star_graph(3), H)
        G = nx.path_graph(3)
        H = nx.ego_graph(G, 0)
        assert edges_equal(H.edges(), [(0, 1)])
        H = nx.ego_graph(G, 0, undirected=True)
        assert edges_equal(H.edges(), [(0, 1)])
        H = nx.ego_graph(G, 0, center=False)
        assert edges_equal(H.edges(), [])

    def test_ego_distance(self):
        G = nx.Graph()
        G.add_edge(0, 1, weight=2, distance=1)
        G.add_edge(1, 2, weight=2, distance=2)
        G.add_edge(2, 3, weight=2, distance=1)
        assert nodes_equal(nx.ego_graph(G, 0, radius=3).nodes(), [0, 1, 2, 3])
        eg = nx.ego_graph(G, 0, radius=3, distance="weight")
        assert nodes_equal(eg.nodes(), [0, 1])
        eg = nx.ego_graph(G, 0, radius=3, distance="weight", undirected=True)
        assert nodes_equal(eg.nodes(), [0, 1])
        eg = nx.ego_graph(G, 0, radius=3, distance="distance")
        assert nodes_equal(eg.nodes(), [0, 1, 2])
