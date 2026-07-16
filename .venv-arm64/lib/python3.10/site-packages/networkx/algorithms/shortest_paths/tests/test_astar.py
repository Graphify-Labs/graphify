import pytest

import networkx as nx
from networkx.utils import pairwise


class TestAStar:
    @classmethod
    def setup_class(cls):
        edges = [
            ("s", "u", 10),
            ("s", "x", 5),
            ("u", "v", 1),
            ("u", "x", 2),
            ("v", "y", 1),
            ("x", "u", 3),
            ("x", "v", 5),
            ("x", "y", 2),
            ("y", "s", 7),
            ("y", "v", 6),
        ]
        cls.XG = nx.DiGraph()
        cls.XG.add_weighted_edges_from(edges)

    def test_multiple_optimal_paths(self):
        """Tests that A* algorithm finds any of multiple optimal paths"""
        heuristic_values = {"a": 1.35, "b": 1.18, "c": 0.67, "d": 0}

        def h(u, v):
            return heuristic_values[u]

        graph = nx.Graph()
        points = ["a", "b", "c", "d"]
        edges = [("a", "b", 0.18), ("a", "c", 0.68), ("b", "c", 0.50), ("c", "d", 0.67)]

        graph.add_nodes_from(points)
        graph.add_weighted_edges_from(edges)

        path1 = ["a", "c", "d"]
        path2 = ["a", "b", "c", "d"]
        assert nx.astar_path(graph, "a", "d", h) in (path1, path2)

    def test_astar_directed(self):
        assert nx.astar_path(self.XG, "s", "v") == ["s", "x", "u", "v"]
        assert nx.astar_path_length(self.XG, "s", "v") == 9

    def test_astar_directed_weight_function(self):
        w1 = lambda u, v, d: d["weight"]
        assert nx.astar_path(self.XG, "x", "u", weight=w1) == ["x", "u"]
        assert nx.astar_path_length(self.XG, "x", "u", weight=w1) == 3
        assert nx.astar_path(self.XG, "s", "v", weight=w1) == ["s", "x", "u", "v"]
        assert nx.astar_path_length(self.XG, "s", "v", weight=w1) == 9

        w2 = lambda u, v, d: None if (u, v) == ("x", "u") else d["weight"]
        assert nx.astar_path(self.XG, "x", "u", weight=w2) == ["x", "y", "s", "u"]
        assert nx.astar_path_length(self.XG, "x", "u", weight=w2) == 19
        assert nx.astar_path(self.XG, "s", "v", weight=w2) == ["s", "x", "v"]
        assert nx.astar_path_length(self.XG, "s", "v", weight=w2) == 10

        w3 = lambda u, v, d: d["weight"] + 10
        assert nx.astar_path(self.XG, "x", "u", weight=w3) == ["x", "u"]
        assert nx.astar_path_length(self.XG, "x", "u", weight=w3) == 13
        assert nx.astar_path(self.XG, "s", "v", weight=w3) == ["s", "x", "v"]
        assert nx.astar_path_length(self.XG, "s", "v", weight=w3) == 30

    def test_astar_multigraph(self):
        G = nx.MultiDiGraph(self.XG)
        G.add_weighted_edges_from((u, v, 1000) for (u, v) in list(G.edges()))
        assert nx.astar_path(G, "s", "v") == ["s", "x", "u", "v"]
        assert nx.astar_path_length(G, "s", "v") == 9

    def test_astar_undirected(self):
        GG = self.XG.to_undirected()
        # make sure we get lower weight
        # to_undirected might choose either edge with weight 2 or weight 3
        GG["u"]["x"]["weight"] = 2
        GG["y"]["v"]["weight"] = 2
        assert nx.astar_path(GG, "s", "v") == ["s", "x", "u", "v"]
        assert nx.astar_path_length(GG, "s", "v") == 8

    def test_astar_directed2(self):
        XG2 = nx.DiGraph()
        edges = [
            (1, 4, 1),
            (4, 5, 1),
            (5, 6, 1),
            (6, 3, 1),
            (1, 3, 50),
            (1, 2, 100),
            (2, 3, 100),
        ]
        XG2.add_weighted_edges_from(edges)
        assert nx.astar_path(XG2, 1, 3) == [1, 4, 5, 6, 3]

    def test_astar_undirected2(self):
        XG3 = nx.Graph()
        edges = [(0, 1, 2), (1, 2, 12), (2, 3, 1), (3, 4, 5), (4, 5, 1), (5, 0, 10)]
        XG3.add_weighted_edges_from(edges)
        assert nx.astar_path(XG3, 0, 3) == [0, 1, 2, 3]
        assert nx.astar_path_length(XG3, 0, 3) == 15

    def test_astar_undirected3(self):
        XG4 = nx.Graph()
        edges = [
            (0, 1, 2),
            (1, 2, 2),
            (2, 3, 1),
            (3, 4, 1),
            (4, 5, 1),
            (5, 6, 1),
            (6, 7, 1),
            (7, 0, 1),
        ]
        XG4.add_weighted_edges_from(edges)
        assert nx.astar_path(XG4, 0, 2) == [0, 1, 2]
        assert nx.astar_path_length(XG4, 0, 2) == 4

    """ Tests that A* finds correct path when multiple paths exist
        and the best one is not expanded first (GH issue #3464)
    """

    def test_astar_directed3(self):
        heuristic_values = {"n5": 36, "n2": 4, "n1": 0, "n0": 0}

        def h(u, v):
            return heuristic_values[u]

        edges = [("n5", "n1", 11), ("n5", "n2", 9), ("n2", "n1", 1), ("n1", "n0", 32)]
        graph = nx.DiGraph()
        graph.add_weighted_edges_from(edges)
        answer = ["n5", "n2", "n1", "n0"]
        assert nx.astar_path(graph, "n5", "n0", h) == answer

    """ Tests that parent is not wrongly overridden when a node
        is re-explored multiple times.
    """

    def test_astar_directed4(self):
        edges = [
            ("a", "b", 1),
            ("a", "c", 1),
            ("b", "d", 2),
            ("c", "d", 1),
            ("d", "e", 1),
        ]
        graph = nx.DiGraph()
        graph.add_weighted_edges_from(edges)
        assert nx.astar_path(graph, "a", "e") == ["a", "c", "d", "e"]

    # >>> MXG4=NX.MultiGraph(XG4)
    # >>> MXG4.add_edge(0,1,3)
    # >>> NX.dijkstra_path(MXG4,0,2)
    # [0, 1, 2]

    def test_astar_w1(self):
        G = nx.DiGraph()
        G.add_edges_from(
            [
                ("s", "u"),
                ("s", "x"),
                ("u", "v"),
                ("u", "x"),
                ("v", "y"),
                ("x", "u"),
                ("x", "w"),
                ("w", "v"),
                ("x", "y"),
                ("y", "s"),
                ("y", "v"),
            ]
        )
        assert nx.astar_path(G, "s", "v") == ["s", "u", "v"]
        assert nx.astar_path_length(G, "s", "v") == 2

    def test_astar_nopath(self):
        with pytest.raises(nx.NodeNotFound):
            nx.astar_path(self.XG, "s", "moon")

    def test_astar_cutoff(self):
        with pytest.raises(nx.NetworkXNoPath):
            # optimal path_length in XG is 9
            nx.astar_path(self.XG, "s", "v", cutoff=8.0)
        with pytest.raises(nx.NetworkXNoPath):
            nx.astar_path_length(self.XG, "s", "v", cutoff=8.0)

    def test_astar_admissible_heuristic_with_cutoff(self):
        heuristic_values = {"s": 36, "y": 4, "x": 0, "u": 0, "v": 0}

        def h(u, v):
            return heuristic_values[u]

        assert nx.astar_path_length(self.XG, "s", "v") == 9
        assert nx.astar_path_length(self.XG, "s", "v", heuristic=h) == 9
        assert nx.astar_path_length(self.XG, "s", "v", heuristic=h, cutoff=12) == 9
        assert nx.astar_path_length(self.XG, "s", "v", heuristic=h, cutoff=9) == 9
        with pytest.raises(nx.NetworkXNoPath):
            nx.astar_path_length(self.XG, "s", "v", heuristic=h, cutoff=8)

    def test_astar_inadmissible_heuristic_with_cutoff(self):
        heuristic_values = {"s": 36, "y": 14, "x": 10, "u": 10, "v": 0}

        def h(u, v):
            return heuristic_values[u]

        # optimal path_length in XG is 9. This heuristic gives over-estimate.
        assert nx.astar_path_length(self.XG, "s", "v", heuristic=h) == 10
        assert nx.astar_path_length(self.XG, "s", "v", heuristic=h, cutoff=15) == 10
        with pytest.raises(nx.NetworkXNoPath):
            nx.astar_path_length(self.XG, "s", "v", heuristic=h, cutoff=9)
        with pytest.raises(nx.NetworkXNoPath):
            nx.astar_path_length(self.XG, "s", "v", heuristic=h, cutoff=12)

    def test_astar_cutoff2(self):
        assert nx.astar_path(self.XG, "s", "v", cutoff=10.0) == ["s", "x", "u", "v"]
        assert nx.astar_path_length(self.XG, "s", "v") == 9

    def test_cycle(self):
        C = nx.cycle_graph(7)
        assert nx.astar_path(C, 0, 3) == [0, 1, 2, 3]
        assert nx.dijkstra_path(C, 0, 4) == [0, 6, 5, 4]

    def test_unorderable_nodes(self):
        """Tests that A* accommodates nodes that are not orderable.

        For more information, see issue #554.

        """
        # Create the cycle graph on four nodes, with nodes represented
        # as (unorderable) Python objects.
        nodes = [object() for n in range(4)]
        G = nx.Graph()
        G.add_edges_from(pairwise(nodes, cyclic=True))
        path = nx.astar_path(G, nodes[0], nodes[2])
        assert len(path) == 3

    def test_astar_NetworkXNoPath(self):
        """Tests that exception is raised when there exists no
        path between source and target"""
        G = nx.gnp_random_graph(10, 0.2, seed=10)
        with pytest.raises(nx.NetworkXNoPath):
            nx.astar_path(G, 4, 9)

    def test_astar_NodeNotFound(self):
        """Tests that exception is raised when either
        source or target is not in graph"""
        G = nx.gnp_random_graph(10, 0.2, seed=10)
        with pytest.raises(nx.NodeNotFound):
            nx.astar_path_length(G, 11, 9)
