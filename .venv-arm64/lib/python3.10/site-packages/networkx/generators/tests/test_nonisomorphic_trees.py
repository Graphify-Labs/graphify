"""
Unit tests for WROM algorithm generator in generators/nonisomorphic_trees.py
"""

import pytest

import networkx as nx
from networkx.utils import edges_equal


class TestGeneratorNonIsomorphicTrees:
    def test_tree_structure(self):
        # test for tree structure for nx.nonisomorphic_trees()
        def f(x):
            return list(nx.nonisomorphic_trees(x))

        for i in f(6):
            assert nx.is_tree(i)
        for i in f(8):
            assert nx.is_tree(i)

    def test_nonisomorphism(self):
        # test for nonisomorphism of trees for nx.nonisomorphic_trees()
        def f(x):
            return list(nx.nonisomorphic_trees(x))

        trees = f(6)
        for i in range(len(trees)):
            for j in range(i + 1, len(trees)):
                assert not nx.is_isomorphic(trees[i], trees[j])
        trees = f(8)
        for i in range(len(trees)):
            for j in range(i + 1, len(trees)):
                assert not nx.is_isomorphic(trees[i], trees[j])

    def test_number_of_nonisomorphic_trees(self):
        # http://oeis.org/A000055
        assert nx.number_of_nonisomorphic_trees(2) == 1
        assert nx.number_of_nonisomorphic_trees(3) == 1
        assert nx.number_of_nonisomorphic_trees(4) == 2
        assert nx.number_of_nonisomorphic_trees(5) == 3
        assert nx.number_of_nonisomorphic_trees(6) == 6
        assert nx.number_of_nonisomorphic_trees(7) == 11
        assert nx.number_of_nonisomorphic_trees(8) == 23

    def test_nonisomorphic_trees(self):
        def f(x):
            return list(nx.nonisomorphic_trees(x))

        assert edges_equal(f(3)[0].edges(), [(0, 1), (0, 2)])
        assert edges_equal(f(4)[0].edges(), [(0, 1), (0, 3), (1, 2)])
        assert edges_equal(f(4)[1].edges(), [(0, 1), (0, 2), (0, 3)])

    def test_nonisomorphic_trees_matrix(self):
        trees_2 = [[[0, 1], [1, 0]]]
        with pytest.deprecated_call():
            assert list(nx.nonisomorphic_trees(2, create="matrix")) == trees_2

        trees_3 = [[[0, 1, 1], [1, 0, 0], [1, 0, 0]]]
        with pytest.deprecated_call():
            assert list(nx.nonisomorphic_trees(3, create="matrix")) == trees_3

        trees_4 = [
            [[0, 1, 0, 1], [1, 0, 1, 0], [0, 1, 0, 0], [1, 0, 0, 0]],
            [[0, 1, 1, 1], [1, 0, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0]],
        ]
        with pytest.deprecated_call():
            assert list(nx.nonisomorphic_trees(4, create="matrix")) == trees_4
