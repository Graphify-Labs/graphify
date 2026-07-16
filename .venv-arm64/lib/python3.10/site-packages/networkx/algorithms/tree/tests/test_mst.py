"""Unit tests for the :mod:`networkx.algorithms.tree.mst` module."""

import pytest

import networkx as nx
from networkx.utils import edges_equal, nodes_equal


def test_unknown_algorithm():
    with pytest.raises(ValueError):
        nx.minimum_spanning_tree(nx.Graph(), algorithm="random")
    with pytest.raises(
        ValueError, match="random is not a valid choice for an algorithm."
    ):
        nx.maximum_spanning_edges(nx.Graph(), algorithm="random")


class MinimumSpanningTreeTestBase:
    """Base class for test classes for minimum spanning tree algorithms.
    This class contains some common tests that will be inherited by
    subclasses. Each subclass must have a class attribute
    :data:`algorithm` that is a string representing the algorithm to
    run, as described under the ``algorithm`` keyword argument for the
    :func:`networkx.minimum_spanning_edges` function.  Subclasses can
    then implement any algorithm-specific tests.
    """

    def setup_method(self, method):
        """Creates an example graph and stores the expected minimum and
        maximum spanning tree edges.
        """
        # This stores the class attribute `algorithm` in an instance attribute.
        self.algo = self.algorithm
        # This example graph comes from Wikipedia:
        # https://en.wikipedia.org/wiki/Kruskal's_algorithm
        edges = [
            (0, 1, 7),
            (0, 3, 5),
            (1, 2, 8),
            (1, 3, 9),
            (1, 4, 7),
            (2, 4, 5),
            (3, 4, 15),
            (3, 5, 6),
            (4, 5, 8),
            (4, 6, 9),
            (5, 6, 11),
        ]
        self.G = nx.Graph()
        self.G.add_weighted_edges_from(edges)
        self.minimum_spanning_edgelist = [
            (0, 1, {"weight": 7}),
            (0, 3, {"weight": 5}),
            (1, 4, {"weight": 7}),
            (2, 4, {"weight": 5}),
            (3, 5, {"weight": 6}),
            (4, 6, {"weight": 9}),
        ]
        self.maximum_spanning_edgelist = [
            (0, 1, {"weight": 7}),
            (1, 2, {"weight": 8}),
            (1, 3, {"weight": 9}),
            (3, 4, {"weight": 15}),
            (4, 6, {"weight": 9}),
            (5, 6, {"weight": 11}),
        ]

    def test_minimum_edges(self):
        edges = nx.minimum_spanning_edges(self.G, algorithm=self.algo)
        # Edges from the spanning edges functions don't come in sorted
        # orientation, so we need to sort each edge individually.
        actual = sorted((min(u, v), max(u, v), d) for u, v, d in edges)
        assert edges_equal(actual, self.minimum_spanning_edgelist)

    def test_maximum_edges(self):
        edges = nx.maximum_spanning_edges(self.G, algorithm=self.algo)
        # Edges from the spanning edges functions don't come in sorted
        # orientation, so we need to sort each edge individually.
        actual = sorted((min(u, v), max(u, v), d) for u, v, d in edges)
        assert edges_equal(actual, self.maximum_spanning_edgelist)

    def test_without_data(self):
        edges = nx.minimum_spanning_edges(self.G, algorithm=self.algo, data=False)
        # Edges from the spanning edges functions don't come in sorted
        # orientation, so we need to sort each edge individually.
        actual = sorted((min(u, v), max(u, v)) for u, v in edges)
        expected = [(u, v) for u, v, d in self.minimum_spanning_edgelist]
        assert edges_equal(actual, expected)

    def test_nan_weights(self):
        # Edge weights NaN never appear in the spanning tree. see #2164
        G = self.G
        G.add_edge(0, 12, weight=float("nan"))
        edges = nx.minimum_spanning_edges(
            G, algorithm=self.algo, data=False, ignore_nan=True
        )
        actual = sorted((min(u, v), max(u, v)) for u, v in edges)
        expected = [(u, v) for u, v, d in self.minimum_spanning_edgelist]
        assert edges_equal(actual, expected)
        # Now test for raising exception
        edges = nx.minimum_spanning_edges(
            G, algorithm=self.algo, data=False, ignore_nan=False
        )
        with pytest.raises(ValueError):
            list(edges)
        # test default for ignore_nan as False
        edges = nx.minimum_spanning_edges(G, algorithm=self.algo, data=False)
        with pytest.raises(ValueError):
            list(edges)

    def test_nan_weights_MultiGraph(self):
        G = nx.MultiGraph()
        G.add_edge(0, 12, weight=float("nan"))
        edges = nx.minimum_spanning_edges(
            G, algorithm="prim", data=False, ignore_nan=False
        )
        with pytest.raises(ValueError):
            list(edges)
        # test default for ignore_nan as False
        edges = nx.minimum_spanning_edges(G, algorithm="prim", data=False)
        with pytest.raises(ValueError):
            list(edges)

    def test_nan_weights_order(self):
        # now try again with a nan edge at the beginning of G.nodes
        edges = [
            (0, 1, 7),
            (0, 3, 5),
            (1, 2, 8),
            (1, 3, 9),
            (1, 4, 7),
            (2, 4, 5),
            (3, 4, 15),
            (3, 5, 6),
            (4, 5, 8),
            (4, 6, 9),
            (5, 6, 11),
        ]
        G = nx.Graph()
        G.add_weighted_edges_from([(u + 1, v + 1, wt) for u, v, wt in edges])
        G.add_edge(0, 7, weight=float("nan"))
        edges = nx.minimum_spanning_edges(
            G, algorithm=self.algo, data=False, ignore_nan=True
        )
        actual = sorted((min(u, v), max(u, v)) for u, v in edges)
        shift = [(u + 1, v + 1) for u, v, d in self.minimum_spanning_edgelist]
        assert edges_equal(actual, shift)

    def test_isolated_node(self):
        # now try again with an isolated node
        edges = [
            (0, 1, 7),
            (0, 3, 5),
            (1, 2, 8),
            (1, 3, 9),
            (1, 4, 7),
            (2, 4, 5),
            (3, 4, 15),
            (3, 5, 6),
            (4, 5, 8),
            (4, 6, 9),
            (5, 6, 11),
        ]
        G = nx.Graph()
        G.add_weighted_edges_from([(u + 1, v + 1, wt) for u, v, wt in edges])
        G.add_node(0)
        edges = nx.minimum_spanning_edges(
            G, algorithm=self.algo, data=False, ignore_nan=True
        )
        actual = sorted((min(u, v), max(u, v)) for u, v in edges)
        shift = [(u + 1, v + 1) for u, v, d in self.minimum_spanning_edgelist]
        assert edges_equal(actual, shift)

    def test_minimum_tree(self):
        T = nx.minimum_spanning_tree(self.G, algorithm=self.algo)
        actual = sorted(T.edges(data=True))
        assert edges_equal(actual, self.minimum_spanning_edgelist)

    def test_maximum_tree(self):
        T = nx.maximum_spanning_tree(self.G, algorithm=self.algo)
        actual = sorted(T.edges(data=True))
        assert edges_equal(actual, self.maximum_spanning_edgelist)

    def test_disconnected(self):
        G = nx.Graph([(0, 1, {"weight": 1}), (2, 3, {"weight": 2})])
        T = nx.minimum_spanning_tree(G, algorithm=self.algo)
        assert nodes_equal(list(T), list(range(4)))
        assert edges_equal(list(T.edges()), [(0, 1), (2, 3)])

    def test_empty_graph(self):
        G = nx.empty_graph(3)
        T = nx.minimum_spanning_tree(G, algorithm=self.algo)
        assert nodes_equal(sorted(T), list(range(3)))
        assert T.number_of_edges() == 0

    def test_attributes(self):
        G = nx.Graph()
        G.add_edge(1, 2, weight=1, color="red", distance=7)
        G.add_edge(2, 3, weight=1, color="green", distance=2)
        G.add_edge(1, 3, weight=10, color="blue", distance=1)
        G.graph["foo"] = "bar"
        T = nx.minimum_spanning_tree(G, algorithm=self.algo)
        assert T.graph == G.graph
        assert nodes_equal(T, G)
        for u, v in T.edges():
            assert T.adj[u][v] == G.adj[u][v]

    def test_weight_attribute(self):
        G = nx.Graph()
        G.add_edge(0, 1, weight=1, distance=7)
        G.add_edge(0, 2, weight=30, distance=1)
        G.add_edge(1, 2, weight=1, distance=1)
        G.add_node(3)
        T = nx.minimum_spanning_tree(G, algorithm=self.algo, weight="distance")
        assert nodes_equal(sorted(T), list(range(4)))
        assert edges_equal(sorted(T.edges()), [(0, 2), (1, 2)])
        T = nx.maximum_spanning_tree(G, algorithm=self.algo, weight="distance")
        assert nodes_equal(sorted(T), list(range(4)))
        assert edges_equal(sorted(T.edges()), [(0, 1), (0, 2)])


class TestBoruvka(MinimumSpanningTreeTestBase):
    """Unit tests for computing a minimum (or maximum) spanning tree
    using Borůvka's algorithm.
    """

    algorithm = "boruvka"

    def test_unicode_name(self):
        """Tests that using a Unicode string can correctly indicate
        Borůvka's algorithm.
        """
        edges = nx.minimum_spanning_edges(self.G, algorithm="borůvka")
        # Edges from the spanning edges functions don't come in sorted
        # orientation, so we need to sort each edge individually.
        actual = sorted((min(u, v), max(u, v), d) for u, v, d in edges)
        assert edges_equal(actual, self.minimum_spanning_edgelist)


class MultigraphMSTTestBase(MinimumSpanningTreeTestBase):
    # Abstract class

    def test_multigraph_keys_min(self):
        """Tests that the minimum spanning edges of a multigraph
        preserves edge keys.
        """
        G = nx.MultiGraph()
        G.add_edge(0, 1, key="a", weight=2)
        G.add_edge(0, 1, key="b", weight=1)
        min_edges = nx.minimum_spanning_edges
        mst_edges = min_edges(G, algorithm=self.algo, data=False)
        assert edges_equal([(0, 1, "b")], list(mst_edges))

    def test_multigraph_keys_max(self):
        """Tests that the maximum spanning edges of a multigraph
        preserves edge keys.
        """
        G = nx.MultiGraph()
        G.add_edge(0, 1, key="a", weight=2)
        G.add_edge(0, 1, key="b", weight=1)
        max_edges = nx.maximum_spanning_edges
        mst_edges = max_edges(G, algorithm=self.algo, data=False)
        assert edges_equal([(0, 1, "a")], list(mst_edges))


class TestKruskal(MultigraphMSTTestBase):
    """Unit tests for computing a minimum (or maximum) spanning tree
    using Kruskal's algorithm.
    """

    algorithm = "kruskal"

    def test_key_data_bool(self):
        """Tests that the keys and data values are included in
        MST edges based on whether keys and data parameters are
        true or false"""
        G = nx.MultiGraph()
        G.add_edge(1, 2, key=1, weight=2)
        G.add_edge(1, 2, key=2, weight=3)
        G.add_edge(3, 2, key=1, weight=2)
        G.add_edge(3, 1, key=1, weight=4)

        # keys are included and data is not included
        mst_edges = nx.minimum_spanning_edges(
            G, algorithm=self.algo, keys=True, data=False
        )
        assert edges_equal([(1, 2, 1), (2, 3, 1)], list(mst_edges))

        # keys are not included and data is included
        mst_edges = nx.minimum_spanning_edges(
            G, algorithm=self.algo, keys=False, data=True
        )
        assert edges_equal(
            [(1, 2, {"weight": 2}), (2, 3, {"weight": 2})], list(mst_edges)
        )

        # both keys and data are not included
        mst_edges = nx.minimum_spanning_edges(
            G, algorithm=self.algo, keys=False, data=False
        )
        assert edges_equal([(1, 2), (2, 3)], list(mst_edges))

        # both keys and data are included
        mst_edges = nx.minimum_spanning_edges(
            G, algorithm=self.algo, keys=True, data=True
        )
        assert edges_equal(
            [(1, 2, 1, {"weight": 2}), (2, 3, 1, {"weight": 2})], list(mst_edges)
        )


class TestPrim(MultigraphMSTTestBase):
    """Unit tests for computing a minimum (or maximum) spanning tree
    using Prim's algorithm.
    """

    algorithm = "prim"

    def test_prim_mst_edges_simple_graph(self):
        H = nx.Graph()
        H.add_edge(1, 2, key=2, weight=3)
        H.add_edge(3, 2, key=1, weight=2)
        H.add_edge(3, 1, key=1, weight=4)

        mst_edges = nx.minimum_spanning_edges(H, algorithm=self.algo, ignore_nan=True)
        assert edges_equal(
            [(1, 2, {"key": 2, "weight": 3}), (2, 3, {"key": 1, "weight": 2})],
            list(mst_edges),
        )

    def test_ignore_nan(self):
        """Tests that the edges with NaN weights are ignored or
        raise an Error based on ignore_nan is true or false"""
        H = nx.MultiGraph()
        H.add_edge(1, 2, key=1, weight=float("nan"))
        H.add_edge(1, 2, key=2, weight=3)
        H.add_edge(3, 2, key=1, weight=2)
        H.add_edge(3, 1, key=1, weight=4)

        # NaN weight edges are ignored when ignore_nan=True
        mst_edges = nx.minimum_spanning_edges(H, algorithm=self.algo, ignore_nan=True)
        assert edges_equal(
            [(1, 2, 2, {"weight": 3}), (2, 3, 1, {"weight": 2})], list(mst_edges)
        )

        # NaN weight edges raise Error when ignore_nan=False
        with pytest.raises(ValueError):
            list(nx.minimum_spanning_edges(H, algorithm=self.algo, ignore_nan=False))

    def test_multigraph_keys_tree(self):
        G = nx.MultiGraph()
        G.add_edge(0, 1, key="a", weight=2)
        G.add_edge(0, 1, key="b", weight=1)
        T = nx.minimum_spanning_tree(G, algorithm=self.algo)
        assert edges_equal([(0, 1, 1)], list(T.edges(data="weight")))

    def test_multigraph_keys_tree_max(self):
        G = nx.MultiGraph()
        G.add_edge(0, 1, key="a", weight=2)
        G.add_edge(0, 1, key="b", weight=1)
        T = nx.maximum_spanning_tree(G, algorithm=self.algo)
        assert edges_equal([(0, 1, 2)], list(T.edges(data="weight")))


class TestSpanningTreeIterator:
    """
    Tests the spanning tree iterator on the example graph in the 2005 Sörensen
    and Janssens paper An Algorithm to Generate all Spanning Trees of a Graph in
    Order of Increasing Cost
    """

    def setup_method(self):
        # Original Graph
        edges = [(0, 1, 5), (1, 2, 4), (1, 4, 6), (2, 3, 5), (2, 4, 7), (3, 4, 3)]
        self.G = nx.Graph()
        self.G.add_weighted_edges_from(edges)
        # List of lists of spanning trees in increasing order
        self.spanning_trees = [
            # 1, MST, cost = 17
            [
                (0, 1, {"weight": 5}),
                (1, 2, {"weight": 4}),
                (2, 3, {"weight": 5}),
                (3, 4, {"weight": 3}),
            ],
            # 2, cost = 18
            [
                (0, 1, {"weight": 5}),
                (1, 2, {"weight": 4}),
                (1, 4, {"weight": 6}),
                (3, 4, {"weight": 3}),
            ],
            # 3, cost = 19
            [
                (0, 1, {"weight": 5}),
                (1, 4, {"weight": 6}),
                (2, 3, {"weight": 5}),
                (3, 4, {"weight": 3}),
            ],
            # 4, cost = 19
            [
                (0, 1, {"weight": 5}),
                (1, 2, {"weight": 4}),
                (2, 4, {"weight": 7}),
                (3, 4, {"weight": 3}),
            ],
            # 5, cost = 20
            [
                (0, 1, {"weight": 5}),
                (1, 2, {"weight": 4}),
                (1, 4, {"weight": 6}),
                (2, 3, {"weight": 5}),
            ],
            # 6, cost = 21
            [
                (0, 1, {"weight": 5}),
                (1, 4, {"weight": 6}),
                (2, 4, {"weight": 7}),
                (3, 4, {"weight": 3}),
            ],
            # 7, cost = 21
            [
                (0, 1, {"weight": 5}),
                (1, 2, {"weight": 4}),
                (2, 3, {"weight": 5}),
                (2, 4, {"weight": 7}),
            ],
            # 8, cost = 23
            [
                (0, 1, {"weight": 5}),
                (1, 4, {"weight": 6}),
                (2, 3, {"weight": 5}),
                (2, 4, {"weight": 7}),
            ],
        ]

    def test_minimum_spanning_tree_iterator(self):
        """
        Tests that the spanning trees are correctly returned in increasing order
        """
        tree_index = 0
        for tree in nx.SpanningTreeIterator(self.G):
            actual = sorted(tree.edges(data=True))
            assert edges_equal(actual, self.spanning_trees[tree_index])
            tree_index += 1

    def test_maximum_spanning_tree_iterator(self):
        """
        Tests that the spanning trees are correctly returned in decreasing order
        """
        tree_index = 7
        for tree in nx.SpanningTreeIterator(self.G, minimum=False):
            actual = sorted(tree.edges(data=True))
            assert edges_equal(actual, self.spanning_trees[tree_index])
            tree_index -= 1


class TestSpanningTreeMultiGraphIterator:
    """
    Uses the same graph as the above class but with an added edge of twice the weight.
    """

    def setup_method(self):
        # New graph
        edges = [
            (0, 1, 5),
            (0, 1, 10),
            (1, 2, 4),
            (1, 2, 8),
            (1, 4, 6),
            (1, 4, 12),
            (2, 3, 5),
            (2, 3, 10),
            (2, 4, 7),
            (2, 4, 14),
            (3, 4, 3),
            (3, 4, 6),
        ]
        self.G = nx.MultiGraph()
        self.G.add_weighted_edges_from(edges)

        # There are 128 trees. I'd rather not list all 128 here, and computing them
        # on such a small graph actually doesn't take that long.
        from itertools import combinations

        self.spanning_trees = []
        for e in combinations(self.G.edges, 4):
            tree = self.G.edge_subgraph(e)
            if nx.is_tree(tree):
                self.spanning_trees.append(sorted(tree.edges(keys=True, data=True)))

    def test_minimum_spanning_tree_iterator_multigraph(self):
        """
        Tests that the spanning trees are correctly returned in increasing order
        """
        tree_index = 0
        last_weight = 0
        for tree in nx.SpanningTreeIterator(self.G):
            actual = sorted(tree.edges(keys=True, data=True))
            weight = sum([e[3]["weight"] for e in actual])
            assert actual in self.spanning_trees
            assert weight >= last_weight
            tree_index += 1

    def test_maximum_spanning_tree_iterator_multigraph(self):
        """
        Tests that the spanning trees are correctly returned in decreasing order
        """
        tree_index = 127
        # Maximum weight tree is 46
        last_weight = 50
        for tree in nx.SpanningTreeIterator(self.G, minimum=False):
            actual = sorted(tree.edges(keys=True, data=True))
            weight = sum([e[3]["weight"] for e in actual])
            assert actual in self.spanning_trees
            assert weight <= last_weight
            tree_index -= 1


def test_random_spanning_tree_multiplicative_small():
    """
    Using a fixed seed, sample one tree for repeatability.
    """
    from math import exp

    pytest.importorskip("scipy")

    gamma = {
        (0, 1): -0.6383,
        (0, 2): -0.6827,
        (0, 5): 0,
        (1, 2): -1.0781,
        (1, 4): 0,
        (2, 3): 0,
        (5, 3): -0.2820,
        (5, 4): -0.3327,
        (4, 3): -0.9927,
    }

    # The undirected support of gamma
    G = nx.Graph()
    for u, v in gamma:
        G.add_edge(u, v, lambda_key=exp(gamma[(u, v)]))

    solution_edges = [(2, 3), (3, 4), (0, 5), (5, 4), (4, 1)]
    solution = nx.Graph()
    solution.add_edges_from(solution_edges)

    sampled_tree = nx.random_spanning_tree(G, "lambda_key", seed=42)

    assert nx.utils.edges_equal(solution.edges, sampled_tree.edges)


@pytest.mark.slow
def test_random_spanning_tree_multiplicative_large():
    """
    Sample many trees from the distribution created in the last test
    """
    from math import exp
    from random import Random

    pytest.importorskip("numpy")
    stats = pytest.importorskip("scipy.stats")

    gamma = {
        (0, 1): -0.6383,
        (0, 2): -0.6827,
        (0, 5): 0,
        (1, 2): -1.0781,
        (1, 4): 0,
        (2, 3): 0,
        (5, 3): -0.2820,
        (5, 4): -0.3327,
        (4, 3): -0.9927,
    }

    # The undirected support of gamma
    G = nx.Graph()
    for u, v in gamma:
        G.add_edge(u, v, lambda_key=exp(gamma[(u, v)]))

    # Find the multiplicative weight for each tree.
    total_weight = 0
    tree_expected = {}
    for t in nx.SpanningTreeIterator(G):
        # Find the multiplicative weight of the spanning tree
        weight = 1
        for u, v, d in t.edges(data="lambda_key"):
            weight *= d
        tree_expected[t] = weight
        total_weight += weight

    # Assert that every tree has an entry in the expected distribution
    assert len(tree_expected) == 75

    # Set the sample size and then calculate the expected number of times we
    # expect to see each tree. This test uses a near minimum sample size where
    # the most unlikely tree has an expected frequency of 5.15.
    # (Minimum required is 5)
    #
    # Here we also initialize the tree_actual dict so that we know the keys
    # match between the two. We will later take advantage of the fact that since
    # python 3.7 dict order is guaranteed so the expected and actual data will
    # have the same order.
    sample_size = 1200
    tree_actual = {}
    for t in tree_expected:
        tree_expected[t] = (tree_expected[t] / total_weight) * sample_size
        tree_actual[t] = 0

    # Sample the spanning trees
    #
    # Assert that they are actually trees and record which of the 75 trees we
    # have sampled.
    #
    # For repeatability, we want to take advantage of the decorators in NetworkX
    # to randomly sample the same sample each time. However, if we pass in a
    # constant seed to sample_spanning_tree we will get the same tree each time.
    # Instead, we can create our own random number generator with a fixed seed
    # and pass those into sample_spanning_tree.
    rng = Random(37)
    for _ in range(sample_size):
        sampled_tree = nx.random_spanning_tree(G, "lambda_key", seed=rng)
        assert nx.is_tree(sampled_tree)

        for t in tree_expected:
            if nx.utils.edges_equal(t.edges, sampled_tree.edges):
                tree_actual[t] += 1
                break

    # Conduct a Chi squared test to see if the actual distribution matches the
    # expected one at an alpha = 0.05 significance level.
    #
    # H_0: The distribution of trees in tree_actual matches the normalized product
    # of the edge weights in the tree.
    #
    # H_a: The distribution of trees in tree_actual follows some other
    # distribution of spanning trees.
    _, p = stats.chisquare(list(tree_actual.values()), list(tree_expected.values()))

    # Assert that p is greater than the significance level so that we do not
    # reject the null hypothesis
    assert not p < 0.05


def test_random_spanning_tree_additive_small():
    """
    Sample a single spanning tree from the additive method.
    """
    pytest.importorskip("scipy")

    edges = {
        (0, 1): 1,
        (0, 2): 1,
        (0, 5): 3,
        (1, 2): 2,
        (1, 4): 3,
        (2, 3): 3,
        (5, 3): 4,
        (5, 4): 5,
        (4, 3): 4,
    }

    # Build the graph
    G = nx.Graph()
    for u, v in edges:
        G.add_edge(u, v, weight=edges[(u, v)])

    solution_edges = [(0, 2), (1, 2), (2, 3), (3, 4), (3, 5)]
    solution = nx.Graph()
    solution.add_edges_from(solution_edges)

    sampled_tree = nx.random_spanning_tree(
        G, weight="weight", multiplicative=False, seed=37
    )

    assert nx.utils.edges_equal(solution.edges, sampled_tree.edges)


@pytest.mark.slow
def test_random_spanning_tree_additive_large():
    """
    Sample many spanning trees from the additive method.
    """
    from random import Random

    pytest.importorskip("numpy")
    stats = pytest.importorskip("scipy.stats")

    edges = {
        (0, 1): 1,
        (0, 2): 1,
        (0, 5): 3,
        (1, 2): 2,
        (1, 4): 3,
        (2, 3): 3,
        (5, 3): 4,
        (5, 4): 5,
        (4, 3): 4,
    }

    # Build the graph
    G = nx.Graph()
    for u, v in edges:
        G.add_edge(u, v, weight=edges[(u, v)])

    # Find the additive weight for each tree.
    total_weight = 0
    tree_expected = {}
    for t in nx.SpanningTreeIterator(G):
        # Find the multiplicative weight of the spanning tree
        weight = 0
        for u, v, d in t.edges(data="weight"):
            weight += d
        tree_expected[t] = weight
        total_weight += weight

    # Assert that every tree has an entry in the expected distribution
    assert len(tree_expected) == 75

    # Set the sample size and then calculate the expected number of times we
    # expect to see each tree. This test uses a near minimum sample size where
    # the most unlikely tree has an expected frequency of 5.07.
    # (Minimum required is 5)
    #
    # Here we also initialize the tree_actual dict so that we know the keys
    # match between the two. We will later take advantage of the fact that since
    # python 3.7 dict order is guaranteed so the expected and actual data will
    # have the same order.
    sample_size = 500
    tree_actual = {}
    for t in tree_expected:
        tree_expected[t] = (tree_expected[t] / total_weight) * sample_size
        tree_actual[t] = 0

    # Sample the spanning trees
    #
    # Assert that they are actually trees and record which of the 75 trees we
    # have sampled.
    #
    # For repeatability, we want to take advantage of the decorators in NetworkX
    # to randomly sample the same sample each time. However, if we pass in a
    # constant seed to sample_spanning_tree we will get the same tree each time.
    # Instead, we can create our own random number generator with a fixed seed
    # and pass those into sample_spanning_tree.
    rng = Random(37)
    for _ in range(sample_size):
        sampled_tree = nx.random_spanning_tree(
            G, "weight", multiplicative=False, seed=rng
        )
        assert nx.is_tree(sampled_tree)

        for t in tree_expected:
            if nx.utils.edges_equal(t.edges, sampled_tree.edges):
                tree_actual[t] += 1
                break

    # Conduct a Chi squared test to see if the actual distribution matches the
    # expected one at an alpha = 0.05 significance level.
    #
    # H_0: The distribution of trees in tree_actual matches the normalized product
    # of the edge weights in the tree.
    #
    # H_a: The distribution of trees in tree_actual follows some other
    # distribution of spanning trees.
    _, p = stats.chisquare(list(tree_actual.values()), list(tree_expected.values()))

    # Assert that p is greater than the significance level so that we do not
    # reject the null hypothesis
    assert not p < 0.05


def test_random_spanning_tree_empty_graph():
    G = nx.Graph()
    rst = nx.tree.random_spanning_tree(G)
    assert len(rst.nodes) == 0
    assert len(rst.edges) == 0


def test_random_spanning_tree_single_node_graph():
    G = nx.Graph()
    G.add_node(0)
    rst = nx.tree.random_spanning_tree(G)
    assert len(rst.nodes) == 1
    assert len(rst.edges) == 0


def test_random_spanning_tree_single_node_loop():
    G = nx.Graph()
    G.add_node(0)
    G.add_edge(0, 0)
    rst = nx.tree.random_spanning_tree(G)
    assert len(rst.nodes) == 1
    assert len(rst.edges) == 0


class TestNumberSpanningTrees:
    @classmethod
    def setup_class(cls):
        global np
        np = pytest.importorskip("numpy")
        sp = pytest.importorskip("scipy")

    def test_nst_disconnected(self):
        G = nx.empty_graph(2)
        assert np.isclose(nx.number_of_spanning_trees(G), 0)

    def test_nst_no_nodes(self):
        G = nx.Graph()
        with pytest.raises(nx.NetworkXPointlessConcept):
            nx.number_of_spanning_trees(G)

    def test_nst_weight(self):
        G = nx.Graph()
        G.add_edge(1, 2, weight=1)
        G.add_edge(1, 3, weight=1)
        G.add_edge(2, 3, weight=2)
        # weights are ignored
        assert np.isclose(nx.number_of_spanning_trees(G), 3)
        # including weight
        assert np.isclose(nx.number_of_spanning_trees(G, weight="weight"), 5)

    def test_nst_negative_weight(self):
        G = nx.Graph()
        G.add_edge(1, 2, weight=1)
        G.add_edge(1, 3, weight=-1)
        G.add_edge(2, 3, weight=-2)
        # weights are ignored
        assert np.isclose(nx.number_of_spanning_trees(G), 3)
        # including weight
        assert np.isclose(nx.number_of_spanning_trees(G, weight="weight"), -1)

    def test_nst_selfloop(self):
        # self-loops are ignored
        G = nx.complete_graph(3)
        G.add_edge(1, 1)
        assert np.isclose(nx.number_of_spanning_trees(G), 3)

    def test_nst_multigraph(self):
        G = nx.MultiGraph()
        G.add_edge(1, 2)
        G.add_edge(1, 2)
        G.add_edge(1, 3)
        G.add_edge(2, 3)
        assert np.isclose(nx.number_of_spanning_trees(G), 5)

    def test_nst_complete_graph(self):
        # this is known as Cayley's formula
        N = 5
        G = nx.complete_graph(N)
        assert np.isclose(nx.number_of_spanning_trees(G), N ** (N - 2))

    def test_nst_path_graph(self):
        G = nx.path_graph(5)
        assert np.isclose(nx.number_of_spanning_trees(G), 1)

    def test_nst_cycle_graph(self):
        G = nx.cycle_graph(5)
        assert np.isclose(nx.number_of_spanning_trees(G), 5)

    def test_nst_directed_noroot(self):
        G = nx.empty_graph(3, create_using=nx.MultiDiGraph)
        with pytest.raises(nx.NetworkXError):
            nx.number_of_spanning_trees(G)

    def test_nst_directed_root_not_exist(self):
        G = nx.empty_graph(3, create_using=nx.MultiDiGraph)
        with pytest.raises(nx.NetworkXError):
            nx.number_of_spanning_trees(G, root=42)

    def test_nst_directed_not_weak_connected(self):
        G = nx.DiGraph()
        G.add_edge(1, 2)
        G.add_edge(3, 4)
        assert np.isclose(nx.number_of_spanning_trees(G, root=1), 0)

    def test_nst_directed_cycle_graph(self):
        G = nx.DiGraph()
        G = nx.cycle_graph(7, G)
        assert np.isclose(nx.number_of_spanning_trees(G, root=0), 1)

    def test_nst_directed_complete_graph(self):
        G = nx.DiGraph()
        G = nx.complete_graph(7, G)
        assert np.isclose(nx.number_of_spanning_trees(G, root=0), 7**5)

    def test_nst_directed_multi(self):
        G = nx.MultiDiGraph()
        G = nx.cycle_graph(3, G)
        G.add_edge(1, 2)
        assert np.isclose(nx.number_of_spanning_trees(G, root=0), 2)

    def test_nst_directed_selfloop(self):
        G = nx.MultiDiGraph()
        G = nx.cycle_graph(3, G)
        G.add_edge(1, 1)
        assert np.isclose(nx.number_of_spanning_trees(G, root=0), 1)

    def test_nst_directed_weak_connected(self):
        G = nx.MultiDiGraph()
        G = nx.cycle_graph(3, G)
        G.remove_edge(1, 2)
        assert np.isclose(nx.number_of_spanning_trees(G, root=0), 0)

    def test_nst_directed_weighted(self):
        # from root=1:
        # arborescence 1: 1->2, 1->3, weight=2*1
        # arborescence 2: 1->2, 2->3, weight=2*3
        G = nx.DiGraph()
        G.add_edge(1, 2, weight=2)
        G.add_edge(1, 3, weight=1)
        G.add_edge(2, 3, weight=3)
        Nst = nx.number_of_spanning_trees(G, root=1, weight="weight")
        assert np.isclose(Nst, 8)
        Nst = nx.number_of_spanning_trees(G, root=2, weight="weight")
        assert np.isclose(Nst, 0)
        Nst = nx.number_of_spanning_trees(G, root=3, weight="weight")
        assert np.isclose(Nst, 0)
