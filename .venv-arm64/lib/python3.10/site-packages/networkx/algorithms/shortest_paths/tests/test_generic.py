import pytest

import networkx as nx


def validate_grid_path(r, c, s, t, p):
    assert isinstance(p, list)
    assert p[0] == s
    assert p[-1] == t
    s = ((s - 1) // c, (s - 1) % c)
    t = ((t - 1) // c, (t - 1) % c)
    assert len(p) == abs(t[0] - s[0]) + abs(t[1] - s[1]) + 1
    p = [((u - 1) // c, (u - 1) % c) for u in p]
    for u in p:
        assert 0 <= u[0] < r
        assert 0 <= u[1] < c
    for u, v in zip(p[:-1], p[1:]):
        assert (abs(v[0] - u[0]), abs(v[1] - u[1])) in [(0, 1), (1, 0)]


class TestGenericPath:
    @classmethod
    def setup_class(cls):
        from networkx import convert_node_labels_to_integers as cnlti

        cls.grid = cnlti(nx.grid_2d_graph(4, 4), first_label=1, ordering="sorted")
        cls.cycle = nx.cycle_graph(7)
        cls.directed_cycle = nx.cycle_graph(7, create_using=nx.DiGraph())
        cls.neg_weights = nx.DiGraph()
        cls.neg_weights.add_edge(0, 1, weight=1)
        cls.neg_weights.add_edge(0, 2, weight=3)
        cls.neg_weights.add_edge(1, 3, weight=1)
        cls.neg_weights.add_edge(2, 3, weight=-2)

    def test_shortest_path(self):
        assert nx.shortest_path(self.cycle, 0, 3) == [0, 1, 2, 3]
        assert nx.shortest_path(self.cycle, 0, 4) == [0, 6, 5, 4]
        validate_grid_path(4, 4, 1, 12, nx.shortest_path(self.grid, 1, 12))
        assert nx.shortest_path(self.directed_cycle, 0, 3) == [0, 1, 2, 3]
        # now with weights
        assert nx.shortest_path(self.cycle, 0, 3, weight="weight") == [0, 1, 2, 3]
        assert nx.shortest_path(self.cycle, 0, 4, weight="weight") == [0, 6, 5, 4]
        validate_grid_path(
            4, 4, 1, 12, nx.shortest_path(self.grid, 1, 12, weight="weight")
        )
        assert nx.shortest_path(self.directed_cycle, 0, 3, weight="weight") == [
            0,
            1,
            2,
            3,
        ]
        # weights and method specified
        assert nx.shortest_path(
            self.directed_cycle, 0, 3, weight="weight", method="dijkstra"
        ) == [0, 1, 2, 3]
        assert nx.shortest_path(
            self.directed_cycle, 0, 3, weight="weight", method="bellman-ford"
        ) == [0, 1, 2, 3]
        # when Dijkstra's will probably (depending on precise implementation)
        # incorrectly return [0, 1, 3] instead
        assert nx.shortest_path(
            self.neg_weights, 0, 3, weight="weight", method="bellman-ford"
        ) == [0, 2, 3]
        # confirm bad method rejection
        pytest.raises(ValueError, nx.shortest_path, self.cycle, method="SPAM")
        # confirm absent source rejection
        pytest.raises(nx.NodeNotFound, nx.shortest_path, self.cycle, 8)

    def test_shortest_path_target(self):
        answer = {0: [0, 1], 1: [1], 2: [2, 1]}
        sp = nx.shortest_path(nx.path_graph(3), target=1)
        assert sp == answer
        # with weights
        sp = nx.shortest_path(nx.path_graph(3), target=1, weight="weight")
        assert sp == answer
        # weights and method specified
        sp = nx.shortest_path(
            nx.path_graph(3), target=1, weight="weight", method="dijkstra"
        )
        assert sp == answer
        sp = nx.shortest_path(
            nx.path_graph(3), target=1, weight="weight", method="bellman-ford"
        )
        assert sp == answer

    def test_shortest_path_length(self):
        assert nx.shortest_path_length(self.cycle, 0, 3) == 3
        assert nx.shortest_path_length(self.grid, 1, 12) == 5
        assert nx.shortest_path_length(self.directed_cycle, 0, 4) == 4
        # now with weights
        assert nx.shortest_path_length(self.cycle, 0, 3, weight="weight") == 3
        assert nx.shortest_path_length(self.grid, 1, 12, weight="weight") == 5
        assert nx.shortest_path_length(self.directed_cycle, 0, 4, weight="weight") == 4
        # weights and method specified
        assert (
            nx.shortest_path_length(
                self.cycle, 0, 3, weight="weight", method="dijkstra"
            )
            == 3
        )
        assert (
            nx.shortest_path_length(
                self.cycle, 0, 3, weight="weight", method="bellman-ford"
            )
            == 3
        )
        # confirm bad method rejection
        pytest.raises(ValueError, nx.shortest_path_length, self.cycle, method="SPAM")
        # confirm absent source rejection
        pytest.raises(nx.NodeNotFound, nx.shortest_path_length, self.cycle, 8)

    def test_shortest_path_length_target(self):
        answer = {0: 1, 1: 0, 2: 1}
        sp = dict(nx.shortest_path_length(nx.path_graph(3), target=1))
        assert sp == answer
        # with weights
        sp = nx.shortest_path_length(nx.path_graph(3), target=1, weight="weight")
        assert sp == answer
        # weights and method specified
        sp = nx.shortest_path_length(
            nx.path_graph(3), target=1, weight="weight", method="dijkstra"
        )
        assert sp == answer
        sp = nx.shortest_path_length(
            nx.path_graph(3), target=1, weight="weight", method="bellman-ford"
        )
        assert sp == answer

    def test_single_source_shortest_path(self):
        p = nx.shortest_path(self.cycle, 0)
        assert p[3] == [0, 1, 2, 3]
        assert p == nx.single_source_shortest_path(self.cycle, 0)
        p = nx.shortest_path(self.grid, 1)
        validate_grid_path(4, 4, 1, 12, p[12])
        # now with weights
        p = nx.shortest_path(self.cycle, 0, weight="weight")
        assert p[3] == [0, 1, 2, 3]
        assert p == nx.single_source_dijkstra_path(self.cycle, 0)
        p = nx.shortest_path(self.grid, 1, weight="weight")
        validate_grid_path(4, 4, 1, 12, p[12])
        # weights and method specified
        p = nx.shortest_path(self.cycle, 0, method="dijkstra", weight="weight")
        assert p[3] == [0, 1, 2, 3]
        assert p == nx.single_source_shortest_path(self.cycle, 0)
        p = nx.shortest_path(self.cycle, 0, method="bellman-ford", weight="weight")
        assert p[3] == [0, 1, 2, 3]
        assert p == nx.single_source_shortest_path(self.cycle, 0)

    def test_single_source_shortest_path_length(self):
        ans = dict(nx.shortest_path_length(self.cycle, 0))
        assert ans == {0: 0, 1: 1, 2: 2, 3: 3, 4: 3, 5: 2, 6: 1}
        assert ans == dict(nx.single_source_shortest_path_length(self.cycle, 0))
        ans = dict(nx.shortest_path_length(self.grid, 1))
        assert ans[16] == 6
        # now with weights
        ans = dict(nx.shortest_path_length(self.cycle, 0, weight="weight"))
        assert ans == {0: 0, 1: 1, 2: 2, 3: 3, 4: 3, 5: 2, 6: 1}
        assert ans == dict(nx.single_source_dijkstra_path_length(self.cycle, 0))
        ans = dict(nx.shortest_path_length(self.grid, 1, weight="weight"))
        assert ans[16] == 6
        # weights and method specified
        ans = dict(
            nx.shortest_path_length(self.cycle, 0, weight="weight", method="dijkstra")
        )
        assert ans == {0: 0, 1: 1, 2: 2, 3: 3, 4: 3, 5: 2, 6: 1}
        assert ans == dict(nx.single_source_dijkstra_path_length(self.cycle, 0))
        ans = dict(
            nx.shortest_path_length(
                self.cycle, 0, weight="weight", method="bellman-ford"
            )
        )
        assert ans == {0: 0, 1: 1, 2: 2, 3: 3, 4: 3, 5: 2, 6: 1}
        assert ans == dict(nx.single_source_bellman_ford_path_length(self.cycle, 0))

    def test_single_source_all_shortest_paths(self):
        cycle_ans = {0: [[0]], 1: [[0, 1]], 2: [[0, 1, 2], [0, 3, 2]], 3: [[0, 3]]}
        ans = dict(nx.single_source_all_shortest_paths(nx.cycle_graph(4), 0))
        assert sorted(ans[2]) == cycle_ans[2]
        ans = dict(nx.single_source_all_shortest_paths(self.grid, 1))
        grid_ans = [
            [1, 2, 3, 7, 11],
            [1, 2, 6, 7, 11],
            [1, 2, 6, 10, 11],
            [1, 5, 6, 7, 11],
            [1, 5, 6, 10, 11],
            [1, 5, 9, 10, 11],
        ]
        assert sorted(ans[11]) == grid_ans
        ans = dict(
            nx.single_source_all_shortest_paths(nx.cycle_graph(4), 0, weight="weight")
        )
        assert sorted(ans[2]) == cycle_ans[2]
        ans = dict(
            nx.single_source_all_shortest_paths(
                nx.cycle_graph(4), 0, method="bellman-ford", weight="weight"
            )
        )
        assert sorted(ans[2]) == cycle_ans[2]
        ans = dict(nx.single_source_all_shortest_paths(self.grid, 1, weight="weight"))
        assert sorted(ans[11]) == grid_ans
        ans = dict(
            nx.single_source_all_shortest_paths(
                self.grid, 1, method="bellman-ford", weight="weight"
            )
        )
        assert sorted(ans[11]) == grid_ans
        G = nx.cycle_graph(4)
        G.add_node(4)
        ans = dict(nx.single_source_all_shortest_paths(G, 0))
        assert sorted(ans[2]) == [[0, 1, 2], [0, 3, 2]]
        ans = dict(nx.single_source_all_shortest_paths(G, 4))
        assert sorted(ans[4]) == [[4]]

    def test_all_pairs_shortest_path(self):
        # shortest_path w/o source and target will return a generator instead of
        # a dict beginning in version 3.5. Only the first call needs changed here.
        p = nx.shortest_path(self.cycle)
        assert p[0][3] == [0, 1, 2, 3]
        assert p == dict(nx.all_pairs_shortest_path(self.cycle))
        p = dict(nx.shortest_path(self.grid))
        validate_grid_path(4, 4, 1, 12, p[1][12])
        # now with weights
        p = dict(nx.shortest_path(self.cycle, weight="weight"))
        assert p[0][3] == [0, 1, 2, 3]
        assert p == dict(nx.all_pairs_dijkstra_path(self.cycle))
        p = dict(nx.shortest_path(self.grid, weight="weight"))
        validate_grid_path(4, 4, 1, 12, p[1][12])
        # weights and method specified
        p = dict(nx.shortest_path(self.cycle, weight="weight", method="dijkstra"))
        assert p[0][3] == [0, 1, 2, 3]
        assert p == dict(nx.all_pairs_dijkstra_path(self.cycle))
        p = dict(nx.shortest_path(self.cycle, weight="weight", method="bellman-ford"))
        assert p[0][3] == [0, 1, 2, 3]
        assert p == dict(nx.all_pairs_bellman_ford_path(self.cycle))

    def test_all_pairs_shortest_path_length(self):
        ans = dict(nx.shortest_path_length(self.cycle))
        assert ans[0] == {0: 0, 1: 1, 2: 2, 3: 3, 4: 3, 5: 2, 6: 1}
        assert ans == dict(nx.all_pairs_shortest_path_length(self.cycle))
        ans = dict(nx.shortest_path_length(self.grid))
        assert ans[1][16] == 6
        # now with weights
        ans = dict(nx.shortest_path_length(self.cycle, weight="weight"))
        assert ans[0] == {0: 0, 1: 1, 2: 2, 3: 3, 4: 3, 5: 2, 6: 1}
        assert ans == dict(nx.all_pairs_dijkstra_path_length(self.cycle))
        ans = dict(nx.shortest_path_length(self.grid, weight="weight"))
        assert ans[1][16] == 6
        # weights and method specified
        ans = dict(
            nx.shortest_path_length(self.cycle, weight="weight", method="dijkstra")
        )
        assert ans[0] == {0: 0, 1: 1, 2: 2, 3: 3, 4: 3, 5: 2, 6: 1}
        assert ans == dict(nx.all_pairs_dijkstra_path_length(self.cycle))
        ans = dict(
            nx.shortest_path_length(self.cycle, weight="weight", method="bellman-ford")
        )
        assert ans[0] == {0: 0, 1: 1, 2: 2, 3: 3, 4: 3, 5: 2, 6: 1}
        assert ans == dict(nx.all_pairs_bellman_ford_path_length(self.cycle))

    def test_all_pairs_all_shortest_paths(self):
        ans = dict(nx.all_pairs_all_shortest_paths(nx.cycle_graph(4)))
        assert sorted(ans[1][3]) == [[1, 0, 3], [1, 2, 3]]
        ans = dict(nx.all_pairs_all_shortest_paths(nx.cycle_graph(4)), weight="weight")
        assert sorted(ans[1][3]) == [[1, 0, 3], [1, 2, 3]]
        ans = dict(
            nx.all_pairs_all_shortest_paths(nx.cycle_graph(4)),
            method="bellman-ford",
            weight="weight",
        )
        assert sorted(ans[1][3]) == [[1, 0, 3], [1, 2, 3]]
        G = nx.cycle_graph(4)
        G.add_node(4)
        ans = dict(nx.all_pairs_all_shortest_paths(G))
        assert sorted(ans[4][4]) == [[4]]

    def test_has_path(self):
        G = nx.Graph()
        nx.add_path(G, range(3))
        nx.add_path(G, range(3, 5))
        assert nx.has_path(G, 0, 2)
        assert not nx.has_path(G, 0, 4)

    def test_has_path_singleton(self):
        G = nx.empty_graph(1)
        assert nx.has_path(G, 0, 0)

    def test_all_shortest_paths(self):
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2, 3])
        nx.add_path(G, [0, 10, 20, 3])
        assert [[0, 1, 2, 3], [0, 10, 20, 3]] == sorted(nx.all_shortest_paths(G, 0, 3))
        # with weights
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2, 3])
        nx.add_path(G, [0, 10, 20, 3])
        assert [[0, 1, 2, 3], [0, 10, 20, 3]] == sorted(
            nx.all_shortest_paths(G, 0, 3, weight="weight")
        )
        # weights and method specified
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2, 3])
        nx.add_path(G, [0, 10, 20, 3])
        assert [[0, 1, 2, 3], [0, 10, 20, 3]] == sorted(
            nx.all_shortest_paths(G, 0, 3, weight="weight", method="dijkstra")
        )
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2, 3])
        nx.add_path(G, [0, 10, 20, 3])
        assert [[0, 1, 2, 3], [0, 10, 20, 3]] == sorted(
            nx.all_shortest_paths(G, 0, 3, weight="weight", method="bellman-ford")
        )

    def test_all_shortest_paths_raise(self):
        with pytest.raises(nx.NetworkXNoPath):
            G = nx.path_graph(4)
            G.add_node(4)
            list(nx.all_shortest_paths(G, 0, 4))

    def test_bad_method(self):
        with pytest.raises(ValueError):
            G = nx.path_graph(2)
            list(nx.all_shortest_paths(G, 0, 1, weight="weight", method="SPAM"))

    def test_single_source_all_shortest_paths_bad_method(self):
        with pytest.raises(ValueError):
            G = nx.path_graph(2)
            dict(
                nx.single_source_all_shortest_paths(
                    G, 0, weight="weight", method="SPAM"
                )
            )

    def test_all_shortest_paths_zero_weight_edge(self):
        g = nx.Graph()
        nx.add_path(g, [0, 1, 3])
        nx.add_path(g, [0, 1, 2, 3])
        g.edges[1, 2]["weight"] = 0
        paths30d = list(
            nx.all_shortest_paths(g, 3, 0, weight="weight", method="dijkstra")
        )
        paths03d = list(
            nx.all_shortest_paths(g, 0, 3, weight="weight", method="dijkstra")
        )
        paths30b = list(
            nx.all_shortest_paths(g, 3, 0, weight="weight", method="bellman-ford")
        )
        paths03b = list(
            nx.all_shortest_paths(g, 0, 3, weight="weight", method="bellman-ford")
        )
        assert sorted(paths03d) == sorted(p[::-1] for p in paths30d)
        assert sorted(paths03d) == sorted(p[::-1] for p in paths30b)
        assert sorted(paths03b) == sorted(p[::-1] for p in paths30b)


class TestAverageShortestPathLength:
    def test_cycle_graph(self):
        ans = nx.average_shortest_path_length(nx.cycle_graph(7))
        assert ans == pytest.approx(2, abs=1e-7)

    def test_path_graph(self):
        ans = nx.average_shortest_path_length(nx.path_graph(5))
        assert ans == pytest.approx(2, abs=1e-7)

    def test_weighted(self):
        G = nx.Graph()
        nx.add_cycle(G, range(7), weight=2)
        ans = nx.average_shortest_path_length(G, weight="weight")
        assert ans == pytest.approx(4, abs=1e-7)
        G = nx.Graph()
        nx.add_path(G, range(5), weight=2)
        ans = nx.average_shortest_path_length(G, weight="weight")
        assert ans == pytest.approx(4, abs=1e-7)

    def test_specified_methods(self):
        G = nx.Graph()
        nx.add_cycle(G, range(7), weight=2)
        ans = nx.average_shortest_path_length(G, weight="weight", method="dijkstra")
        assert ans == pytest.approx(4, abs=1e-7)
        ans = nx.average_shortest_path_length(G, weight="weight", method="bellman-ford")
        assert ans == pytest.approx(4, abs=1e-7)
        ans = nx.average_shortest_path_length(
            G, weight="weight", method="floyd-warshall"
        )
        assert ans == pytest.approx(4, abs=1e-7)

        G = nx.Graph()
        nx.add_path(G, range(5), weight=2)
        ans = nx.average_shortest_path_length(G, weight="weight", method="dijkstra")
        assert ans == pytest.approx(4, abs=1e-7)
        ans = nx.average_shortest_path_length(G, weight="weight", method="bellman-ford")
        assert ans == pytest.approx(4, abs=1e-7)
        ans = nx.average_shortest_path_length(
            G, weight="weight", method="floyd-warshall"
        )
        assert ans == pytest.approx(4, abs=1e-7)

    def test_directed_not_strongly_connected(self):
        G = nx.DiGraph([(0, 1)])
        with pytest.raises(nx.NetworkXError, match="Graph is not strongly connected"):
            nx.average_shortest_path_length(G)

    def test_undirected_not_connected(self):
        g = nx.Graph()
        g.add_nodes_from(range(3))
        g.add_edge(0, 1)
        pytest.raises(nx.NetworkXError, nx.average_shortest_path_length, g)

    def test_trivial_graph(self):
        """Tests that the trivial graph has average path length zero,
        since there is exactly one path of length zero in the trivial
        graph.

        For more information, see issue #1960.

        """
        G = nx.trivial_graph()
        assert nx.average_shortest_path_length(G) == 0

    def test_null_graph(self):
        with pytest.raises(nx.NetworkXPointlessConcept):
            nx.average_shortest_path_length(nx.null_graph())

    def test_bad_method(self):
        with pytest.raises(ValueError):
            G = nx.path_graph(2)
            nx.average_shortest_path_length(G, weight="weight", method="SPAM")


class TestAverageShortestPathLengthNumpy:
    @classmethod
    def setup_class(cls):
        global np
        import pytest

        np = pytest.importorskip("numpy")

    def test_specified_methods_numpy(self):
        G = nx.Graph()
        nx.add_cycle(G, range(7), weight=2)
        ans = nx.average_shortest_path_length(
            G, weight="weight", method="floyd-warshall-numpy"
        )
        np.testing.assert_almost_equal(ans, 4)

        G = nx.Graph()
        nx.add_path(G, range(5), weight=2)
        ans = nx.average_shortest_path_length(
            G, weight="weight", method="floyd-warshall-numpy"
        )
        np.testing.assert_almost_equal(ans, 4)
