import networkx as nx


def test_unionfind():
    # Fixed by: 2cddd5958689bdecdcd89b91ac9aaf6ce0e4f6b8
    # Previously (in 2.x), the UnionFind class could handle mixed types.
    # But in Python 3.x, this causes a TypeError such as:
    #   TypeError: unorderable types: str() > int()
    #
    # Now we just make sure that no exception is raised.
    x = nx.utils.UnionFind()
    x.union(0, "a")


def test_subtree_union():
    # See https://github.com/networkx/networkx/pull/3224
    # (35db1b551ee65780794a357794f521d8768d5049).
    # Test if subtree unions hare handled correctly by to_sets().
    uf = nx.utils.UnionFind()
    uf.union(1, 2)
    uf.union(3, 4)
    uf.union(4, 5)
    uf.union(1, 5)
    assert list(uf.to_sets()) == [{1, 2, 3, 4, 5}]


def test_unionfind_weights():
    # Tests if weights are computed correctly with unions of many elements
    uf = nx.utils.UnionFind()
    uf.union(1, 4, 7)
    uf.union(2, 5, 8)
    uf.union(3, 6, 9)
    uf.union(1, 2, 3, 4, 5, 6, 7, 8, 9)
    assert uf.weights[uf[1]] == 9


def test_unbalanced_merge_weights():
    # Tests if the largest set's root is used as the new root when merging
    uf = nx.utils.UnionFind()
    uf.union(1, 2, 3)
    uf.union(4, 5, 6, 7, 8, 9)
    assert uf.weights[uf[1]] == 3
    assert uf.weights[uf[4]] == 6
    largest_root = uf[4]
    uf.union(1, 4)
    assert uf[1] == largest_root
    assert uf.weights[largest_root] == 9


def test_empty_union():
    # Tests if a null-union does nothing.
    uf = nx.utils.UnionFind((0, 1))
    uf.union()
    assert uf[0] == 0
    assert uf[1] == 1
