import pytest

import networkx as nx


class TestImmediateDominators:
    def test_exceptions(self):
        G = nx.Graph()
        G.add_node(0)
        pytest.raises(nx.NetworkXNotImplemented, nx.immediate_dominators, G, 0)
        G = nx.MultiGraph(G)
        pytest.raises(nx.NetworkXNotImplemented, nx.immediate_dominators, G, 0)
        G = nx.DiGraph([[0, 0]])
        pytest.raises(nx.NetworkXError, nx.immediate_dominators, G, 1)

    def test_singleton(self):
        G = nx.DiGraph()
        G.add_node(0)
        assert nx.immediate_dominators(G, 0) == {0: 0}
        G.add_edge(0, 0)
        assert nx.immediate_dominators(G, 0) == {0: 0}

    def test_path(self):
        n = 5
        G = nx.path_graph(n, create_using=nx.DiGraph())
        assert nx.immediate_dominators(G, 0) == {i: max(i - 1, 0) for i in range(n)}

    def test_cycle(self):
        n = 5
        G = nx.cycle_graph(n, create_using=nx.DiGraph())
        assert nx.immediate_dominators(G, 0) == {i: max(i - 1, 0) for i in range(n)}

    def test_unreachable(self):
        n = 5
        assert n > 1
        G = nx.path_graph(n, create_using=nx.DiGraph())
        assert nx.immediate_dominators(G, n // 2) == {
            i: max(i - 1, n // 2) for i in range(n // 2, n)
        }

    def test_irreducible1(self):
        """
        Graph taken from figure 2 of "A simple, fast dominance algorithm." (2006).
        https://hdl.handle.net/1911/96345
        """
        edges = [(1, 2), (2, 1), (3, 2), (4, 1), (5, 3), (5, 4)]
        G = nx.DiGraph(edges)
        assert nx.immediate_dominators(G, 5) == {i: 5 for i in range(1, 6)}

    def test_irreducible2(self):
        """
        Graph taken from figure 4 of "A simple, fast dominance algorithm." (2006).
        https://hdl.handle.net/1911/96345
        """

        edges = [(1, 2), (2, 1), (2, 3), (3, 2), (4, 2), (4, 3), (5, 1), (6, 4), (6, 5)]
        G = nx.DiGraph(edges)
        result = nx.immediate_dominators(G, 6)
        assert result == {i: 6 for i in range(1, 7)}

    def test_domrel_png(self):
        # Graph taken from https://commons.wikipedia.org/wiki/File:Domrel.png
        edges = [(1, 2), (2, 3), (2, 4), (2, 6), (3, 5), (4, 5), (5, 2)]
        G = nx.DiGraph(edges)
        result = nx.immediate_dominators(G, 1)
        assert result == {1: 1, 2: 1, 3: 2, 4: 2, 5: 2, 6: 2}
        # Test postdominance.
        result = nx.immediate_dominators(G.reverse(copy=False), 6)
        assert result == {1: 2, 2: 6, 3: 5, 4: 5, 5: 2, 6: 6}

    def test_boost_example(self):
        # Graph taken from Figure 1 of
        # http://www.boost.org/doc/libs/1_56_0/libs/graph/doc/lengauer_tarjan_dominator.htm
        edges = [(0, 1), (1, 2), (1, 3), (2, 7), (3, 4), (4, 5), (4, 6), (5, 7), (6, 4)]
        G = nx.DiGraph(edges)
        result = nx.immediate_dominators(G, 0)
        assert result == {0: 0, 1: 0, 2: 1, 3: 1, 4: 3, 5: 4, 6: 4, 7: 1}
        # Test postdominance.
        result = nx.immediate_dominators(G.reverse(copy=False), 7)
        assert result == {0: 1, 1: 7, 2: 7, 3: 4, 4: 5, 5: 7, 6: 4, 7: 7}


class TestDominanceFrontiers:
    def test_exceptions(self):
        G = nx.Graph()
        G.add_node(0)
        pytest.raises(nx.NetworkXNotImplemented, nx.dominance_frontiers, G, 0)
        G = nx.MultiGraph(G)
        pytest.raises(nx.NetworkXNotImplemented, nx.dominance_frontiers, G, 0)
        G = nx.DiGraph([[0, 0]])
        pytest.raises(nx.NetworkXError, nx.dominance_frontiers, G, 1)

    def test_singleton(self):
        G = nx.DiGraph()
        G.add_node(0)
        assert nx.dominance_frontiers(G, 0) == {0: set()}
        G.add_edge(0, 0)
        assert nx.dominance_frontiers(G, 0) == {0: set()}

    def test_path(self):
        n = 5
        G = nx.path_graph(n, create_using=nx.DiGraph())
        assert nx.dominance_frontiers(G, 0) == {i: set() for i in range(n)}

    def test_cycle(self):
        n = 5
        G = nx.cycle_graph(n, create_using=nx.DiGraph())
        assert nx.dominance_frontiers(G, 0) == {i: set() for i in range(n)}

    def test_unreachable(self):
        n = 5
        assert n > 1
        G = nx.path_graph(n, create_using=nx.DiGraph())
        assert nx.dominance_frontiers(G, n // 2) == {i: set() for i in range(n // 2, n)}

    def test_irreducible1(self):
        """
        Graph taken from figure 2 of "A simple, fast dominance algorithm." (2006).
        https://hdl.handle.net/1911/96345
        """
        edges = [(1, 2), (2, 1), (3, 2), (4, 1), (5, 3), (5, 4)]
        G = nx.DiGraph(edges)
        assert dict(nx.dominance_frontiers(G, 5).items()) == {
            1: {2},
            2: {1},
            3: {2},
            4: {1},
            5: set(),
        }

    def test_irreducible2(self):
        """
        Graph taken from figure 4 of "A simple, fast dominance algorithm." (2006).
        https://hdl.handle.net/1911/96345
        """
        edges = [(1, 2), (2, 1), (2, 3), (3, 2), (4, 2), (4, 3), (5, 1), (6, 4), (6, 5)]
        G = nx.DiGraph(edges)
        assert nx.dominance_frontiers(G, 6) == {
            1: {2},
            2: {1, 3},
            3: {2},
            4: {2, 3},
            5: {1},
            6: set(),
        }

    def test_domrel_png(self):
        # Graph taken from https://commons.wikipedia.org/wiki/File:Domrel.png
        edges = [(1, 2), (2, 3), (2, 4), (2, 6), (3, 5), (4, 5), (5, 2)]
        G = nx.DiGraph(edges)
        assert nx.dominance_frontiers(G, 1) == {
            1: set(),
            2: {2},
            3: {5},
            4: {5},
            5: {2},
            6: set(),
        }
        # Test postdominance.
        result = nx.dominance_frontiers(G.reverse(copy=False), 6)
        assert result == {1: set(), 2: {2}, 3: {2}, 4: {2}, 5: {2}, 6: set()}

    def test_boost_example(self):
        # Graph taken from Figure 1 of
        # http://www.boost.org/doc/libs/1_56_0/libs/graph/doc/lengauer_tarjan_dominator.htm
        edges = [(0, 1), (1, 2), (1, 3), (2, 7), (3, 4), (4, 5), (4, 6), (5, 7), (6, 4)]
        G = nx.DiGraph(edges)
        assert nx.dominance_frontiers(G, 0) == {
            0: set(),
            1: set(),
            2: {7},
            3: {7},
            4: {4, 7},
            5: {7},
            6: {4},
            7: set(),
        }
        # Test postdominance.
        result = nx.dominance_frontiers(G.reverse(copy=False), 7)
        expected = {
            0: set(),
            1: set(),
            2: {1},
            3: {1},
            4: {1, 4},
            5: {1},
            6: {4},
            7: set(),
        }
        assert result == expected

    def test_discard_issue(self):
        # https://github.com/networkx/networkx/issues/2071
        g = nx.DiGraph()
        g.add_edges_from(
            [
                ("b0", "b1"),
                ("b1", "b2"),
                ("b2", "b3"),
                ("b3", "b1"),
                ("b1", "b5"),
                ("b5", "b6"),
                ("b5", "b8"),
                ("b6", "b7"),
                ("b8", "b7"),
                ("b7", "b3"),
                ("b3", "b4"),
            ]
        )
        df = nx.dominance_frontiers(g, "b0")
        assert df == {
            "b4": set(),
            "b5": {"b3"},
            "b6": {"b7"},
            "b7": {"b3"},
            "b0": set(),
            "b1": {"b1"},
            "b2": {"b3"},
            "b3": {"b1"},
            "b8": {"b7"},
        }

    def test_loop(self):
        g = nx.DiGraph()
        g.add_edges_from([("a", "b"), ("b", "c"), ("b", "a")])
        df = nx.dominance_frontiers(g, "a")
        assert df == {"a": set(), "b": set(), "c": set()}

    def test_missing_immediate_doms(self):
        # see https://github.com/networkx/networkx/issues/2070
        g = nx.DiGraph()
        edges = [
            ("entry_1", "b1"),
            ("b1", "b2"),
            ("b2", "b3"),
            ("b3", "exit"),
            ("entry_2", "b3"),
        ]

        # entry_1
        #   |
        #   b1
        #   |
        #   b2  entry_2
        #    |  /
        #    b3
        #    |
        #   exit

        g.add_edges_from(edges)
        # formerly raised KeyError on entry_2 when parsing b3
        # because entry_2 does not have immediate doms (no path)
        nx.dominance_frontiers(g, "entry_1")

    def test_loops_larger(self):
        # from
        # http://ecee.colorado.edu/~waite/Darmstadt/motion.html
        g = nx.DiGraph()
        edges = [
            ("entry", "exit"),
            ("entry", "1"),
            ("1", "2"),
            ("2", "3"),
            ("3", "4"),
            ("4", "5"),
            ("5", "6"),
            ("6", "exit"),
            ("6", "2"),
            ("5", "3"),
            ("4", "4"),
        ]

        g.add_edges_from(edges)
        df = nx.dominance_frontiers(g, "entry")
        answer = {
            "entry": set(),
            "1": {"exit"},
            "2": {"exit", "2"},
            "3": {"exit", "3", "2"},
            "4": {"exit", "4", "3", "2"},
            "5": {"exit", "3", "2"},
            "6": {"exit", "2"},
            "exit": set(),
        }
        for n in df:
            assert set(df[n]) == set(answer[n])
