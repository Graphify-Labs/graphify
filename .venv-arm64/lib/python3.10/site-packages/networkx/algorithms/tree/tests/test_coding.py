"""Unit tests for the :mod:`~networkx.algorithms.tree.coding` module."""

from itertools import product

import pytest

import networkx as nx
from networkx.utils import edges_equal, nodes_equal


class TestPruferSequence:
    """Unit tests for the Prüfer sequence encoding and decoding
    functions.

    """

    def test_nontree(self):
        with pytest.raises(nx.NotATree):
            G = nx.cycle_graph(3)
            nx.to_prufer_sequence(G)

    def test_null_graph(self):
        with pytest.raises(nx.NetworkXPointlessConcept):
            nx.to_prufer_sequence(nx.null_graph())

    def test_trivial_graph(self):
        with pytest.raises(nx.NetworkXPointlessConcept):
            nx.to_prufer_sequence(nx.trivial_graph())

    def test_bad_integer_labels(self):
        with pytest.raises(KeyError):
            T = nx.Graph(nx.utils.pairwise("abc"))
            nx.to_prufer_sequence(T)

    def test_encoding(self):
        """Tests for encoding a tree as a Prüfer sequence using the
        iterative strategy.

        """
        # Example from Wikipedia.
        tree = nx.Graph([(0, 3), (1, 3), (2, 3), (3, 4), (4, 5)])
        sequence = nx.to_prufer_sequence(tree)
        assert sequence == [3, 3, 3, 4]

    def test_decoding(self):
        """Tests for decoding a tree from a Prüfer sequence."""
        # Example from Wikipedia.
        sequence = [3, 3, 3, 4]
        tree = nx.from_prufer_sequence(sequence)
        assert nodes_equal(list(tree), list(range(6)))
        edges = [(0, 3), (1, 3), (2, 3), (3, 4), (4, 5)]
        assert edges_equal(list(tree.edges()), edges)

    def test_decoding2(self):
        # Example from "An Optimal Algorithm for Prufer Codes".
        sequence = [2, 4, 0, 1, 3, 3]
        tree = nx.from_prufer_sequence(sequence)
        assert nodes_equal(list(tree), list(range(8)))
        edges = [(0, 1), (0, 4), (1, 3), (2, 4), (2, 5), (3, 6), (3, 7)]
        assert edges_equal(list(tree.edges()), edges)

    def test_inverse(self):
        """Tests that the encoding and decoding functions are inverses."""
        for T in nx.nonisomorphic_trees(4):
            T2 = nx.from_prufer_sequence(nx.to_prufer_sequence(T))
            assert nodes_equal(list(T), list(T2))
            assert edges_equal(list(T.edges()), list(T2.edges()))

        for seq in product(range(4), repeat=2):
            seq2 = nx.to_prufer_sequence(nx.from_prufer_sequence(seq))
            assert list(seq) == seq2


class TestNestedTuple:
    """Unit tests for the nested tuple encoding and decoding functions."""

    def test_nontree(self):
        with pytest.raises(nx.NotATree):
            G = nx.cycle_graph(3)
            nx.to_nested_tuple(G, 0)

    def test_unknown_root(self):
        with pytest.raises(nx.NodeNotFound):
            G = nx.path_graph(2)
            nx.to_nested_tuple(G, "bogus")

    def test_encoding(self):
        T = nx.full_rary_tree(2, 2**3 - 1)
        expected = (((), ()), ((), ()))
        actual = nx.to_nested_tuple(T, 0)
        assert nodes_equal(expected, actual)

    def test_canonical_form(self):
        T = nx.Graph()
        T.add_edges_from([(0, 1), (0, 2), (0, 3)])
        T.add_edges_from([(1, 4), (1, 5)])
        T.add_edges_from([(3, 6), (3, 7)])
        root = 0
        actual = nx.to_nested_tuple(T, root, canonical_form=True)
        expected = ((), ((), ()), ((), ()))
        assert actual == expected

    def test_decoding(self):
        balanced = (((), ()), ((), ()))
        expected = nx.full_rary_tree(2, 2**3 - 1)
        actual = nx.from_nested_tuple(balanced)
        assert nx.is_isomorphic(expected, actual)

    def test_sensible_relabeling(self):
        balanced = (((), ()), ((), ()))
        T = nx.from_nested_tuple(balanced, sensible_relabeling=True)
        edges = [(0, 1), (0, 2), (1, 3), (1, 4), (2, 5), (2, 6)]
        assert nodes_equal(list(T), list(range(2**3 - 1)))
        assert edges_equal(list(T.edges()), edges)
