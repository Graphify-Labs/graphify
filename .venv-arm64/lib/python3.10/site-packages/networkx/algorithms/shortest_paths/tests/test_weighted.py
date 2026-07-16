import pytest

import networkx as nx
from networkx.utils import pairwise


def validate_path(G, s, t, soln_len, path, weight="weight"):
    assert path[0] == s
    assert path[-1] == t

    if callable(weight):
        weight_f = weight
    else:
        if G.is_multigraph():

            def weight_f(u, v, d):
                return min(e.get(weight, 1) for e in d.values())

        else:

            def weight_f(u, v, d):
                return d.get(weight, 1)

    computed = sum(weight_f(u, v, G[u][v]) for u, v in pairwise(path))
    assert soln_len == computed


def validate_length_path(G, s, t, soln_len, length, path, weight="weight"):
    assert soln_len == length
    validate_path(G, s, t, length, path, weight=weight)


class WeightedTestBase:
    """Base class for test classes that test functions for computing
    shortest paths in weighted graphs.

    """

    def setup_method(self):
        """Creates some graphs for use in the unit tests."""
        cnlti = nx.convert_node_labels_to_integers
        self.grid = cnlti(nx.grid_2d_graph(4, 4), first_label=1, ordering="sorted")
        self.cycle = nx.cycle_graph(7)
        self.directed_cycle = nx.cycle_graph(7, create_using=nx.DiGraph())
        self.XG = nx.DiGraph()
        self.XG.add_weighted_edges_from(
            [
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
        )
        self.MXG = nx.MultiDiGraph(self.XG)
        self.MXG.add_edge("s", "u", weight=15)
        self.XG2 = nx.DiGraph()
        self.XG2.add_weighted_edges_from(
            [
                [1, 4, 1],
                [4, 5, 1],
                [5, 6, 1],
                [6, 3, 1],
                [1, 3, 50],
                [1, 2, 100],
                [2, 3, 100],
            ]
        )

        self.XG3 = nx.Graph()
        self.XG3.add_weighted_edges_from(
            [[0, 1, 2], [1, 2, 12], [2, 3, 1], [3, 4, 5], [4, 5, 1], [5, 0, 10]]
        )

        self.XG4 = nx.Graph()
        self.XG4.add_weighted_edges_from(
            [
                [0, 1, 2],
                [1, 2, 2],
                [2, 3, 1],
                [3, 4, 1],
                [4, 5, 1],
                [5, 6, 1],
                [6, 7, 1],
                [7, 0, 1],
            ]
        )
        self.MXG4 = nx.MultiGraph(self.XG4)
        self.MXG4.add_edge(0, 1, weight=3)
        self.G = nx.DiGraph()  # no weights
        self.G.add_edges_from(
            [
                ("s", "u"),
                ("s", "x"),
                ("u", "v"),
                ("u", "x"),
                ("v", "y"),
                ("x", "u"),
                ("x", "v"),
                ("x", "y"),
                ("y", "s"),
                ("y", "v"),
            ]
        )


class TestWeightedPath(WeightedTestBase):
    def test_dijkstra(self):
        (D, P) = nx.single_source_dijkstra(self.XG, "s")
        validate_path(self.XG, "s", "v", 9, P["v"])
        assert D["v"] == 9

        validate_path(
            self.XG, "s", "v", 9, nx.single_source_dijkstra_path(self.XG, "s")["v"]
        )
        assert dict(nx.single_source_dijkstra_path_length(self.XG, "s"))["v"] == 9

        validate_path(
            self.XG, "s", "v", 9, nx.single_source_dijkstra(self.XG, "s")[1]["v"]
        )
        validate_path(
            self.MXG, "s", "v", 9, nx.single_source_dijkstra_path(self.MXG, "s")["v"]
        )

        GG = self.XG.to_undirected()
        # make sure we get lower weight
        # to_undirected might choose either edge with weight 2 or weight 3
        GG["u"]["x"]["weight"] = 2
        (D, P) = nx.single_source_dijkstra(GG, "s")
        validate_path(GG, "s", "v", 8, P["v"])
        assert D["v"] == 8  # uses lower weight of 2 on u<->x edge
        validate_path(GG, "s", "v", 8, nx.dijkstra_path(GG, "s", "v"))
        assert nx.dijkstra_path_length(GG, "s", "v") == 8

        validate_path(self.XG2, 1, 3, 4, nx.dijkstra_path(self.XG2, 1, 3))
        validate_path(self.XG3, 0, 3, 15, nx.dijkstra_path(self.XG3, 0, 3))
        assert nx.dijkstra_path_length(self.XG3, 0, 3) == 15
        validate_path(self.XG4, 0, 2, 4, nx.dijkstra_path(self.XG4, 0, 2))
        assert nx.dijkstra_path_length(self.XG4, 0, 2) == 4
        validate_path(self.MXG4, 0, 2, 4, nx.dijkstra_path(self.MXG4, 0, 2))
        validate_path(
            self.G, "s", "v", 2, nx.single_source_dijkstra(self.G, "s", "v")[1]
        )
        validate_path(
            self.G, "s", "v", 2, nx.single_source_dijkstra(self.G, "s")[1]["v"]
        )

        validate_path(self.G, "s", "v", 2, nx.dijkstra_path(self.G, "s", "v"))
        assert nx.dijkstra_path_length(self.G, "s", "v") == 2

        # NetworkXError: node s not reachable from moon
        pytest.raises(nx.NetworkXNoPath, nx.dijkstra_path, self.G, "s", "moon")
        pytest.raises(nx.NetworkXNoPath, nx.dijkstra_path_length, self.G, "s", "moon")

        validate_path(self.cycle, 0, 3, 3, nx.dijkstra_path(self.cycle, 0, 3))
        validate_path(self.cycle, 0, 4, 3, nx.dijkstra_path(self.cycle, 0, 4))

        assert nx.single_source_dijkstra(self.cycle, 0, 0) == (0, [0])

    def test_bidirectional_dijkstra(self):
        validate_length_path(
            self.XG, "s", "v", 9, *nx.bidirectional_dijkstra(self.XG, "s", "v")
        )
        validate_length_path(
            self.G, "s", "v", 2, *nx.bidirectional_dijkstra(self.G, "s", "v")
        )
        validate_length_path(
            self.cycle, 0, 3, 3, *nx.bidirectional_dijkstra(self.cycle, 0, 3)
        )
        validate_length_path(
            self.cycle, 0, 4, 3, *nx.bidirectional_dijkstra(self.cycle, 0, 4)
        )
        validate_length_path(
            self.XG3, 0, 3, 15, *nx.bidirectional_dijkstra(self.XG3, 0, 3)
        )
        validate_length_path(
            self.XG4, 0, 2, 4, *nx.bidirectional_dijkstra(self.XG4, 0, 2)
        )

        # need more tests here
        P = nx.single_source_dijkstra_path(self.XG, "s")["v"]
        validate_path(
            self.XG,
            "s",
            "v",
            sum(self.XG[u][v]["weight"] for u, v in zip(P[:-1], P[1:])),
            nx.dijkstra_path(self.XG, "s", "v"),
        )

        # check absent source
        G = nx.path_graph(2)
        pytest.raises(nx.NodeNotFound, nx.bidirectional_dijkstra, G, 3, 0)

    def test_weight_functions(self):
        def heuristic(*z):
            return sum(val**2 for val in z)

        def getpath(pred, v, s):
            return [v] if v == s else getpath(pred, pred[v], s) + [v]

        def goldberg_radzik(g, s, t, weight="weight"):
            pred, dist = nx.goldberg_radzik(g, s, weight=weight)
            dist = dist[t]
            return dist, getpath(pred, t, s)

        def astar(g, s, t, weight="weight"):
            path = nx.astar_path(g, s, t, heuristic, weight=weight)
            dist = nx.astar_path_length(g, s, t, heuristic, weight=weight)
            return dist, path

        def vlp(G, s, t, l, F, w):
            res = F(G, s, t, weight=w)
            validate_length_path(G, s, t, l, *res, weight=w)

        G = self.cycle
        s = 6
        t = 4
        path = [6] + list(range(t + 1))

        def weight(u, v, _):
            return 1 + v**2

        length = sum(weight(u, v, None) for u, v in pairwise(path))
        vlp(G, s, t, length, nx.bidirectional_dijkstra, weight)
        vlp(G, s, t, length, nx.single_source_dijkstra, weight)
        vlp(G, s, t, length, nx.single_source_bellman_ford, weight)
        vlp(G, s, t, length, goldberg_radzik, weight)
        vlp(G, s, t, length, astar, weight)

        def weight(u, v, _):
            return 2 ** (u * v)

        length = sum(weight(u, v, None) for u, v in pairwise(path))
        vlp(G, s, t, length, nx.bidirectional_dijkstra, weight)
        vlp(G, s, t, length, nx.single_source_dijkstra, weight)
        vlp(G, s, t, length, nx.single_source_bellman_ford, weight)
        vlp(G, s, t, length, goldberg_radzik, weight)
        vlp(G, s, t, length, astar, weight)

    def test_bidirectional_dijkstra_no_path(self):
        with pytest.raises(nx.NetworkXNoPath):
            G = nx.Graph()
            nx.add_path(G, [1, 2, 3])
            nx.add_path(G, [4, 5, 6])
            path = nx.bidirectional_dijkstra(G, 1, 6)

    @pytest.mark.parametrize(
        "fn",
        (
            nx.dijkstra_path,
            nx.dijkstra_path_length,
            nx.single_source_dijkstra_path,
            nx.single_source_dijkstra_path_length,
            nx.single_source_dijkstra,
            nx.dijkstra_predecessor_and_distance,
        ),
    )
    def test_absent_source(self, fn):
        G = nx.path_graph(2)
        with pytest.raises(nx.NodeNotFound):
            fn(G, 3, 0)
        # Test when source == target, which is handled specially by some functions
        with pytest.raises(nx.NodeNotFound):
            fn(G, 3, 3)

    def test_dijkstra_predecessor1(self):
        G = nx.path_graph(4)
        assert nx.dijkstra_predecessor_and_distance(G, 0) == (
            {0: [], 1: [0], 2: [1], 3: [2]},
            {0: 0, 1: 1, 2: 2, 3: 3},
        )

    def test_dijkstra_predecessor2(self):
        # 4-cycle
        G = nx.Graph([(0, 1), (1, 2), (2, 3), (3, 0)])
        pred, dist = nx.dijkstra_predecessor_and_distance(G, (0))
        assert pred[0] == []
        assert pred[1] == [0]
        assert pred[2] in [[1, 3], [3, 1]]
        assert pred[3] == [0]
        assert dist == {0: 0, 1: 1, 2: 2, 3: 1}

    def test_dijkstra_predecessor3(self):
        XG = nx.DiGraph()
        XG.add_weighted_edges_from(
            [
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
        )
        (P, D) = nx.dijkstra_predecessor_and_distance(XG, "s")
        assert P["v"] == ["u"]
        assert D["v"] == 9
        (P, D) = nx.dijkstra_predecessor_and_distance(XG, "s", cutoff=8)
        assert "v" not in D

    def test_single_source_dijkstra_path_length(self):
        pl = nx.single_source_dijkstra_path_length
        assert dict(pl(self.MXG4, 0))[2] == 4
        spl = pl(self.MXG4, 0, cutoff=2)
        assert 2 not in spl

    def test_bidirectional_dijkstra_multigraph(self):
        G = nx.MultiGraph()
        G.add_edge("a", "b", weight=10)
        G.add_edge("a", "b", weight=100)
        dp = nx.bidirectional_dijkstra(G, "a", "b")
        assert dp == (10, ["a", "b"])

    def test_dijkstra_pred_distance_multigraph(self):
        G = nx.MultiGraph()
        G.add_edge("a", "b", key="short", foo=5, weight=100)
        G.add_edge("a", "b", key="long", bar=1, weight=110)
        p, d = nx.dijkstra_predecessor_and_distance(G, "a")
        assert p == {"a": [], "b": ["a"]}
        assert d == {"a": 0, "b": 100}

    def test_negative_edge_cycle(self):
        G = nx.cycle_graph(5, create_using=nx.DiGraph())
        assert not nx.negative_edge_cycle(G)
        G.add_edge(8, 9, weight=-7)
        G.add_edge(9, 8, weight=3)
        graph_size = len(G)
        assert nx.negative_edge_cycle(G)
        assert graph_size == len(G)
        pytest.raises(ValueError, nx.single_source_dijkstra_path_length, G, 8)
        pytest.raises(ValueError, nx.single_source_dijkstra, G, 8)
        pytest.raises(ValueError, nx.dijkstra_predecessor_and_distance, G, 8)
        G.add_edge(9, 10)
        pytest.raises(ValueError, nx.bidirectional_dijkstra, G, 8, 10)
        G = nx.MultiDiGraph()
        G.add_edge(2, 2, weight=-1)
        assert nx.negative_edge_cycle(G)

    def test_negative_edge_cycle_empty(self):
        G = nx.DiGraph()
        assert not nx.negative_edge_cycle(G)

    def test_negative_edge_cycle_custom_weight_key(self):
        d = nx.DiGraph()
        d.add_edge("a", "b", w=-2)
        d.add_edge("b", "a", w=-1)
        assert nx.negative_edge_cycle(d, weight="w")

    def test_weight_function(self):
        """Tests that a callable weight is interpreted as a weight
        function instead of an edge attribute.

        """
        # Create a triangle in which the edge from node 0 to node 2 has
        # a large weight and the other two edges have a small weight.
        G = nx.complete_graph(3)
        G.adj[0][2]["weight"] = 10
        G.adj[0][1]["weight"] = 1
        G.adj[1][2]["weight"] = 1

        # The weight function will take the multiplicative inverse of
        # the weights on the edges. This way, weights that were large
        # before now become small and vice versa.

        def weight(u, v, d):
            return 1 / d["weight"]

        # The shortest path from 0 to 2 using the actual weights on the
        # edges should be [0, 1, 2].
        distance, path = nx.single_source_dijkstra(G, 0, 2)
        assert distance == 2
        assert path == [0, 1, 2]
        # However, with the above weight function, the shortest path
        # should be [0, 2], since that has a very small weight.
        distance, path = nx.single_source_dijkstra(G, 0, 2, weight=weight)
        assert distance == 1 / 10
        assert path == [0, 2]

    def test_all_pairs_dijkstra_path(self):
        cycle = nx.cycle_graph(7)
        p = dict(nx.all_pairs_dijkstra_path(cycle))
        assert p[0][3] == [0, 1, 2, 3]

        cycle[1][2]["weight"] = 10
        p = dict(nx.all_pairs_dijkstra_path(cycle))
        assert p[0][3] == [0, 6, 5, 4, 3]

    def test_all_pairs_dijkstra_path_length(self):
        cycle = nx.cycle_graph(7)
        pl = dict(nx.all_pairs_dijkstra_path_length(cycle))
        assert pl[0] == {0: 0, 1: 1, 2: 2, 3: 3, 4: 3, 5: 2, 6: 1}

        cycle[1][2]["weight"] = 10
        pl = dict(nx.all_pairs_dijkstra_path_length(cycle))
        assert pl[0] == {0: 0, 1: 1, 2: 5, 3: 4, 4: 3, 5: 2, 6: 1}

    def test_all_pairs_dijkstra(self):
        cycle = nx.cycle_graph(7)
        out = dict(nx.all_pairs_dijkstra(cycle))
        assert out[0][0] == {0: 0, 1: 1, 2: 2, 3: 3, 4: 3, 5: 2, 6: 1}
        assert out[0][1][3] == [0, 1, 2, 3]

        cycle[1][2]["weight"] = 10
        out = dict(nx.all_pairs_dijkstra(cycle))
        assert out[0][0] == {0: 0, 1: 1, 2: 5, 3: 4, 4: 3, 5: 2, 6: 1}
        assert out[0][1][3] == [0, 6, 5, 4, 3]


class TestDijkstraPathLength:
    """Unit tests for the :func:`networkx.dijkstra_path_length`
    function.

    """

    def test_weight_function(self):
        """Tests for computing the length of the shortest path using
        Dijkstra's algorithm with a user-defined weight function.

        """
        # Create a triangle in which the edge from node 0 to node 2 has
        # a large weight and the other two edges have a small weight.
        G = nx.complete_graph(3)
        G.adj[0][2]["weight"] = 10
        G.adj[0][1]["weight"] = 1
        G.adj[1][2]["weight"] = 1

        # The weight function will take the multiplicative inverse of
        # the weights on the edges. This way, weights that were large
        # before now become small and vice versa.

        def weight(u, v, d):
            return 1 / d["weight"]

        # The shortest path from 0 to 2 using the actual weights on the
        # edges should be [0, 1, 2]. However, with the above weight
        # function, the shortest path should be [0, 2], since that has a
        # very small weight.
        length = nx.dijkstra_path_length(G, 0, 2, weight=weight)
        assert length == 1 / 10


class TestMultiSourceDijkstra:
    """Unit tests for the multi-source dialect of Dijkstra's shortest
    path algorithms.

    """

    def test_no_sources(self):
        with pytest.raises(ValueError):
            nx.multi_source_dijkstra(nx.Graph(), {})

    def test_path_no_sources(self):
        with pytest.raises(ValueError):
            nx.multi_source_dijkstra_path(nx.Graph(), {})

    def test_path_length_no_sources(self):
        with pytest.raises(ValueError):
            nx.multi_source_dijkstra_path_length(nx.Graph(), {})

    @pytest.mark.parametrize(
        "fn",
        (
            nx.multi_source_dijkstra_path,
            nx.multi_source_dijkstra_path_length,
            nx.multi_source_dijkstra,
        ),
    )
    def test_absent_source(self, fn):
        G = nx.path_graph(2)
        with pytest.raises(nx.NodeNotFound):
            fn(G, [3], 0)
        with pytest.raises(nx.NodeNotFound):
            fn(G, [3], 3)

    def test_two_sources(self):
        edges = [(0, 1, 1), (1, 2, 1), (2, 3, 10), (3, 4, 1)]
        G = nx.Graph()
        G.add_weighted_edges_from(edges)
        sources = {0, 4}
        distances, paths = nx.multi_source_dijkstra(G, sources)
        expected_distances = {0: 0, 1: 1, 2: 2, 3: 1, 4: 0}
        expected_paths = {0: [0], 1: [0, 1], 2: [0, 1, 2], 3: [4, 3], 4: [4]}
        assert distances == expected_distances
        assert paths == expected_paths

    def test_simple_paths(self):
        G = nx.path_graph(4)
        lengths = nx.multi_source_dijkstra_path_length(G, [0])
        assert lengths == {n: n for n in G}
        paths = nx.multi_source_dijkstra_path(G, [0])
        assert paths == {n: list(range(n + 1)) for n in G}


class TestBellmanFordAndGoldbergRadzik(WeightedTestBase):
    def test_single_node_graph(self):
        G = nx.DiGraph()
        G.add_node(0)
        assert nx.single_source_bellman_ford_path(G, 0) == {0: [0]}
        assert nx.single_source_bellman_ford_path_length(G, 0) == {0: 0}
        assert nx.single_source_bellman_ford(G, 0) == ({0: 0}, {0: [0]})
        assert nx.bellman_ford_predecessor_and_distance(G, 0) == ({0: []}, {0: 0})
        assert nx.goldberg_radzik(G, 0) == ({0: None}, {0: 0})

    def test_absent_source_bellman_ford(self):
        # the check is in _bellman_ford; this provides regression testing
        # against later changes to "client" Bellman-Ford functions
        G = nx.path_graph(2)
        for fn in (
            nx.bellman_ford_predecessor_and_distance,
            nx.bellman_ford_path,
            nx.bellman_ford_path_length,
            nx.single_source_bellman_ford_path,
            nx.single_source_bellman_ford_path_length,
            nx.single_source_bellman_ford,
        ):
            pytest.raises(nx.NodeNotFound, fn, G, 3, 0)
            pytest.raises(nx.NodeNotFound, fn, G, 3, 3)

    def test_absent_source_goldberg_radzik(self):
        with pytest.raises(nx.NodeNotFound):
            G = nx.path_graph(2)
            nx.goldberg_radzik(G, 3, 0)

    def test_negative_cycle_heuristic(self):
        G = nx.DiGraph()
        G.add_edge(0, 1, weight=-1)
        G.add_edge(1, 2, weight=-1)
        G.add_edge(2, 3, weight=-1)
        G.add_edge(3, 0, weight=3)
        assert not nx.negative_edge_cycle(G, heuristic=True)
        G.add_edge(2, 0, weight=1.999)
        assert nx.negative_edge_cycle(G, heuristic=True)
        G.edges[2, 0]["weight"] = 2
        assert not nx.negative_edge_cycle(G, heuristic=True)

    def test_negative_cycle_consistency(self):
        import random

        unif = random.uniform
        for random_seed in range(2):  # range(20):
            random.seed(random_seed)
            for density in [0.1, 0.9]:  # .3, .7, .9]:
                for N in [1, 10, 20]:  # range(1, 60 - int(30 * density)):
                    for max_cost in [1, 90]:  # [1, 10, 40, 90]:
                        G = nx.binomial_graph(N, density, seed=4, directed=True)
                        edges = ((u, v, unif(-1, max_cost)) for u, v in G.edges)
                        G.add_weighted_edges_from(edges)

                        no_heuristic = nx.negative_edge_cycle(G, heuristic=False)
                        with_heuristic = nx.negative_edge_cycle(G, heuristic=True)
                        assert no_heuristic == with_heuristic

    def test_negative_cycle(self):
        G = nx.cycle_graph(5, create_using=nx.DiGraph())
        G.add_edge(1, 2, weight=-7)
        for i in range(5):
            pytest.raises(
                nx.NetworkXUnbounded, nx.single_source_bellman_ford_path, G, i
            )
            pytest.raises(
                nx.NetworkXUnbounded, nx.single_source_bellman_ford_path_length, G, i
            )
            pytest.raises(nx.NetworkXUnbounded, nx.single_source_bellman_ford, G, i)
            pytest.raises(
                nx.NetworkXUnbounded, nx.bellman_ford_predecessor_and_distance, G, i
            )
            pytest.raises(nx.NetworkXUnbounded, nx.goldberg_radzik, G, i)
        G = nx.cycle_graph(5)  # undirected Graph
        G.add_edge(1, 2, weight=-3)
        for i in range(5):
            pytest.raises(
                nx.NetworkXUnbounded, nx.single_source_bellman_ford_path, G, i
            )
            pytest.raises(
                nx.NetworkXUnbounded, nx.single_source_bellman_ford_path_length, G, i
            )
            pytest.raises(nx.NetworkXUnbounded, nx.single_source_bellman_ford, G, i)
            pytest.raises(
                nx.NetworkXUnbounded, nx.bellman_ford_predecessor_and_distance, G, i
            )
            pytest.raises(nx.NetworkXUnbounded, nx.goldberg_radzik, G, i)
        G = nx.DiGraph([(1, 1, {"weight": -1})])
        pytest.raises(nx.NetworkXUnbounded, nx.single_source_bellman_ford_path, G, 1)
        pytest.raises(
            nx.NetworkXUnbounded, nx.single_source_bellman_ford_path_length, G, 1
        )
        pytest.raises(nx.NetworkXUnbounded, nx.single_source_bellman_ford, G, 1)
        pytest.raises(
            nx.NetworkXUnbounded, nx.bellman_ford_predecessor_and_distance, G, 1
        )
        pytest.raises(nx.NetworkXUnbounded, nx.goldberg_radzik, G, 1)
        G = nx.MultiDiGraph([(1, 1, {"weight": -1})])
        pytest.raises(nx.NetworkXUnbounded, nx.single_source_bellman_ford_path, G, 1)
        pytest.raises(
            nx.NetworkXUnbounded, nx.single_source_bellman_ford_path_length, G, 1
        )
        pytest.raises(nx.NetworkXUnbounded, nx.single_source_bellman_ford, G, 1)
        pytest.raises(
            nx.NetworkXUnbounded, nx.bellman_ford_predecessor_and_distance, G, 1
        )
        pytest.raises(nx.NetworkXUnbounded, nx.goldberg_radzik, G, 1)

    def test_zero_cycle(self):
        G = nx.cycle_graph(5, create_using=nx.DiGraph())
        G.add_edge(2, 3, weight=-4)
        # check that zero cycle doesn't raise
        nx.goldberg_radzik(G, 1)
        nx.bellman_ford_predecessor_and_distance(G, 1)

        G.add_edge(2, 3, weight=-4.0001)
        # check that negative cycle does raise
        pytest.raises(
            nx.NetworkXUnbounded, nx.bellman_ford_predecessor_and_distance, G, 1
        )
        pytest.raises(nx.NetworkXUnbounded, nx.goldberg_radzik, G, 1)

    def test_find_negative_cycle_longer_cycle(self):
        G = nx.cycle_graph(5, create_using=nx.DiGraph())
        nx.add_cycle(G, [3, 5, 6, 7, 8, 9])
        G.add_edge(1, 2, weight=-30)
        assert nx.find_negative_cycle(G, 1) == [0, 1, 2, 3, 4, 0]
        assert nx.find_negative_cycle(G, 7) == [2, 3, 4, 0, 1, 2]

    def test_find_negative_cycle_no_cycle(self):
        G = nx.path_graph(5, create_using=nx.DiGraph())
        pytest.raises(nx.NetworkXError, nx.find_negative_cycle, G, 3)

    def test_find_negative_cycle_single_edge(self):
        G = nx.Graph()
        G.add_edge(0, 1, weight=-1)
        assert nx.find_negative_cycle(G, 1) == [1, 0, 1]

    def test_negative_weight(self):
        G = nx.cycle_graph(5, create_using=nx.DiGraph())
        G.add_edge(1, 2, weight=-3)
        assert nx.single_source_bellman_ford_path(G, 0) == {
            0: [0],
            1: [0, 1],
            2: [0, 1, 2],
            3: [0, 1, 2, 3],
            4: [0, 1, 2, 3, 4],
        }
        assert nx.single_source_bellman_ford_path_length(G, 0) == {
            0: 0,
            1: 1,
            2: -2,
            3: -1,
            4: 0,
        }
        assert nx.single_source_bellman_ford(G, 0) == (
            {0: 0, 1: 1, 2: -2, 3: -1, 4: 0},
            {0: [0], 1: [0, 1], 2: [0, 1, 2], 3: [0, 1, 2, 3], 4: [0, 1, 2, 3, 4]},
        )
        assert nx.bellman_ford_predecessor_and_distance(G, 0) == (
            {0: [], 1: [0], 2: [1], 3: [2], 4: [3]},
            {0: 0, 1: 1, 2: -2, 3: -1, 4: 0},
        )
        assert nx.goldberg_radzik(G, 0) == (
            {0: None, 1: 0, 2: 1, 3: 2, 4: 3},
            {0: 0, 1: 1, 2: -2, 3: -1, 4: 0},
        )

    def test_not_connected(self):
        G = nx.complete_graph(6)
        G.add_edge(10, 11)
        G.add_edge(10, 12)
        assert nx.single_source_bellman_ford_path(G, 0) == {
            0: [0],
            1: [0, 1],
            2: [0, 2],
            3: [0, 3],
            4: [0, 4],
            5: [0, 5],
        }
        assert nx.single_source_bellman_ford_path_length(G, 0) == {
            0: 0,
            1: 1,
            2: 1,
            3: 1,
            4: 1,
            5: 1,
        }
        assert nx.single_source_bellman_ford(G, 0) == (
            {0: 0, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1},
            {0: [0], 1: [0, 1], 2: [0, 2], 3: [0, 3], 4: [0, 4], 5: [0, 5]},
        )
        assert nx.bellman_ford_predecessor_and_distance(G, 0) == (
            {0: [], 1: [0], 2: [0], 3: [0], 4: [0], 5: [0]},
            {0: 0, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1},
        )
        assert nx.goldberg_radzik(G, 0) == (
            {0: None, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
            {0: 0, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1},
        )

        # not connected, with a component not containing the source that
        # contains a negative cycle.
        G = nx.complete_graph(6)
        G.add_edges_from(
            [
                ("A", "B", {"load": 3}),
                ("B", "C", {"load": -10}),
                ("C", "A", {"load": 2}),
            ]
        )
        assert nx.single_source_bellman_ford_path(G, 0, weight="load") == {
            0: [0],
            1: [0, 1],
            2: [0, 2],
            3: [0, 3],
            4: [0, 4],
            5: [0, 5],
        }
        assert nx.single_source_bellman_ford_path_length(G, 0, weight="load") == {
            0: 0,
            1: 1,
            2: 1,
            3: 1,
            4: 1,
            5: 1,
        }
        assert nx.single_source_bellman_ford(G, 0, weight="load") == (
            {0: 0, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1},
            {0: [0], 1: [0, 1], 2: [0, 2], 3: [0, 3], 4: [0, 4], 5: [0, 5]},
        )
        assert nx.bellman_ford_predecessor_and_distance(G, 0, weight="load") == (
            {0: [], 1: [0], 2: [0], 3: [0], 4: [0], 5: [0]},
            {0: 0, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1},
        )
        assert nx.goldberg_radzik(G, 0, weight="load") == (
            {0: None, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
            {0: 0, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1},
        )

    def test_multigraph(self):
        assert nx.bellman_ford_path(self.MXG, "s", "v") == ["s", "x", "u", "v"]
        assert nx.bellman_ford_path_length(self.MXG, "s", "v") == 9
        assert nx.single_source_bellman_ford_path(self.MXG, "s")["v"] == [
            "s",
            "x",
            "u",
            "v",
        ]
        assert nx.single_source_bellman_ford_path_length(self.MXG, "s")["v"] == 9
        D, P = nx.single_source_bellman_ford(self.MXG, "s", target="v")
        assert D == 9
        assert P == ["s", "x", "u", "v"]
        P, D = nx.bellman_ford_predecessor_and_distance(self.MXG, "s")
        assert P["v"] == ["u"]
        assert D["v"] == 9
        P, D = nx.goldberg_radzik(self.MXG, "s")
        assert P["v"] == "u"
        assert D["v"] == 9
        assert nx.bellman_ford_path(self.MXG4, 0, 2) == [0, 1, 2]
        assert nx.bellman_ford_path_length(self.MXG4, 0, 2) == 4
        assert nx.single_source_bellman_ford_path(self.MXG4, 0)[2] == [0, 1, 2]
        assert nx.single_source_bellman_ford_path_length(self.MXG4, 0)[2] == 4
        D, P = nx.single_source_bellman_ford(self.MXG4, 0, target=2)
        assert D == 4
        assert P == [0, 1, 2]
        P, D = nx.bellman_ford_predecessor_and_distance(self.MXG4, 0)
        assert P[2] == [1]
        assert D[2] == 4
        P, D = nx.goldberg_radzik(self.MXG4, 0)
        assert P[2] == 1
        assert D[2] == 4

    def test_others(self):
        assert nx.bellman_ford_path(self.XG, "s", "v") == ["s", "x", "u", "v"]
        assert nx.bellman_ford_path_length(self.XG, "s", "v") == 9
        assert nx.single_source_bellman_ford_path(self.XG, "s")["v"] == [
            "s",
            "x",
            "u",
            "v",
        ]
        assert nx.single_source_bellman_ford_path_length(self.XG, "s")["v"] == 9
        D, P = nx.single_source_bellman_ford(self.XG, "s", target="v")
        assert D == 9
        assert P == ["s", "x", "u", "v"]
        (P, D) = nx.bellman_ford_predecessor_and_distance(self.XG, "s")
        assert P["v"] == ["u"]
        assert D["v"] == 9
        (P, D) = nx.goldberg_radzik(self.XG, "s")
        assert P["v"] == "u"
        assert D["v"] == 9

    def test_path_graph(self):
        G = nx.path_graph(4)
        assert nx.single_source_bellman_ford_path(G, 0) == {
            0: [0],
            1: [0, 1],
            2: [0, 1, 2],
            3: [0, 1, 2, 3],
        }
        assert nx.single_source_bellman_ford_path_length(G, 0) == {
            0: 0,
            1: 1,
            2: 2,
            3: 3,
        }
        assert nx.single_source_bellman_ford(G, 0) == (
            {0: 0, 1: 1, 2: 2, 3: 3},
            {0: [0], 1: [0, 1], 2: [0, 1, 2], 3: [0, 1, 2, 3]},
        )
        assert nx.bellman_ford_predecessor_and_distance(G, 0) == (
            {0: [], 1: [0], 2: [1], 3: [2]},
            {0: 0, 1: 1, 2: 2, 3: 3},
        )
        assert nx.goldberg_radzik(G, 0) == (
            {0: None, 1: 0, 2: 1, 3: 2},
            {0: 0, 1: 1, 2: 2, 3: 3},
        )
        assert nx.single_source_bellman_ford_path(G, 3) == {
            0: [3, 2, 1, 0],
            1: [3, 2, 1],
            2: [3, 2],
            3: [3],
        }
        assert nx.single_source_bellman_ford_path_length(G, 3) == {
            0: 3,
            1: 2,
            2: 1,
            3: 0,
        }
        assert nx.single_source_bellman_ford(G, 3) == (
            {0: 3, 1: 2, 2: 1, 3: 0},
            {0: [3, 2, 1, 0], 1: [3, 2, 1], 2: [3, 2], 3: [3]},
        )
        assert nx.bellman_ford_predecessor_and_distance(G, 3) == (
            {0: [1], 1: [2], 2: [3], 3: []},
            {0: 3, 1: 2, 2: 1, 3: 0},
        )
        assert nx.goldberg_radzik(G, 3) == (
            {0: 1, 1: 2, 2: 3, 3: None},
            {0: 3, 1: 2, 2: 1, 3: 0},
        )

    def test_4_cycle(self):
        # 4-cycle
        G = nx.Graph([(0, 1), (1, 2), (2, 3), (3, 0)])
        dist, path = nx.single_source_bellman_ford(G, 0)
        assert dist == {0: 0, 1: 1, 2: 2, 3: 1}
        assert path[0] == [0]
        assert path[1] == [0, 1]
        assert path[2] in [[0, 1, 2], [0, 3, 2]]
        assert path[3] == [0, 3]

        pred, dist = nx.bellman_ford_predecessor_and_distance(G, 0)
        assert pred[0] == []
        assert pred[1] == [0]
        assert pred[2] in [[1, 3], [3, 1]]
        assert pred[3] == [0]
        assert dist == {0: 0, 1: 1, 2: 2, 3: 1}

        pred, dist = nx.goldberg_radzik(G, 0)
        assert pred[0] is None
        assert pred[1] == 0
        assert pred[2] in [1, 3]
        assert pred[3] == 0
        assert dist == {0: 0, 1: 1, 2: 2, 3: 1}

    def test_negative_weight_bf_path(self):
        G = nx.DiGraph()
        G.add_nodes_from("abcd")
        G.add_edge("a", "d", weight=0)
        G.add_edge("a", "b", weight=1)
        G.add_edge("b", "c", weight=-3)
        G.add_edge("c", "d", weight=1)

        assert nx.bellman_ford_path(G, "a", "d") == ["a", "b", "c", "d"]
        assert nx.bellman_ford_path_length(G, "a", "d") == -1

    def test_zero_cycle_smoke(self):
        D = nx.DiGraph()
        D.add_weighted_edges_from([(0, 1, 1), (1, 2, 1), (2, 3, 1), (3, 1, -2)])

        nx.bellman_ford_path(D, 1, 3)
        nx.dijkstra_path(D, 1, 3)
        nx.bidirectional_dijkstra(D, 1, 3)
        # FIXME nx.goldberg_radzik(D, 1)


class TestJohnsonAlgorithm(WeightedTestBase):
    def test_single_node_graph(self):
        G = nx.DiGraph()
        G.add_node(0)
        assert nx.johnson(G) == {0: {0: [0]}}

    def test_negative_cycle(self):
        G = nx.DiGraph()
        G.add_weighted_edges_from(
            [
                ("0", "3", 3),
                ("0", "1", -5),
                ("1", "0", -5),
                ("0", "2", 2),
                ("1", "2", 4),
                ("2", "3", 1),
            ]
        )
        pytest.raises(nx.NetworkXUnbounded, nx.johnson, G)
        G = nx.Graph()
        G.add_weighted_edges_from(
            [
                ("0", "3", 3),
                ("0", "1", -5),
                ("1", "0", -5),
                ("0", "2", 2),
                ("1", "2", 4),
                ("2", "3", 1),
            ]
        )
        pytest.raises(nx.NetworkXUnbounded, nx.johnson, G)

    def test_negative_weights(self):
        G = nx.DiGraph()
        G.add_weighted_edges_from(
            [("0", "3", 3), ("0", "1", -5), ("0", "2", 2), ("1", "2", 4), ("2", "3", 1)]
        )
        paths = nx.johnson(G)
        assert paths == {
            "1": {"1": ["1"], "3": ["1", "2", "3"], "2": ["1", "2"]},
            "0": {
                "1": ["0", "1"],
                "0": ["0"],
                "3": ["0", "1", "2", "3"],
                "2": ["0", "1", "2"],
            },
            "3": {"3": ["3"]},
            "2": {"3": ["2", "3"], "2": ["2"]},
        }

    def test_unweighted_graph(self):
        G = nx.Graph()
        G.add_edges_from([(1, 0), (2, 1)])
        H = G.copy()
        nx.set_edge_attributes(H, values=1, name="weight")
        assert nx.johnson(G) == nx.johnson(H)

    def test_partially_weighted_graph_with_negative_edges(self):
        G = nx.DiGraph()
        G.add_edges_from([(0, 1), (1, 2), (2, 0), (1, 0)])
        G[1][0]["weight"] = -2
        G[0][1]["weight"] = 3
        G[1][2]["weight"] = -4

        H = G.copy()
        H[2][0]["weight"] = 1

        I = G.copy()
        I[2][0]["weight"] = 8

        assert nx.johnson(G) == nx.johnson(H)
        assert nx.johnson(G) != nx.johnson(I)

    def test_graphs(self):
        validate_path(self.XG, "s", "v", 9, nx.johnson(self.XG)["s"]["v"])
        validate_path(self.MXG, "s", "v", 9, nx.johnson(self.MXG)["s"]["v"])
        validate_path(self.XG2, 1, 3, 4, nx.johnson(self.XG2)[1][3])
        validate_path(self.XG3, 0, 3, 15, nx.johnson(self.XG3)[0][3])
        validate_path(self.XG4, 0, 2, 4, nx.johnson(self.XG4)[0][2])
        validate_path(self.MXG4, 0, 2, 4, nx.johnson(self.MXG4)[0][2])
