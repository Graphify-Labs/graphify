import pytest

np = pytest.importorskip("numpy")

import networkx as nx


def test_attr_matrix():
    G = nx.Graph()
    G.add_edge(0, 1, thickness=1, weight=3)
    G.add_edge(0, 1, thickness=1, weight=3)
    G.add_edge(0, 2, thickness=2)
    G.add_edge(1, 2, thickness=3)

    def node_attr(u):
        return G.nodes[u].get("size", 0.5) * 3

    def edge_attr(u, v):
        return G[u][v].get("thickness", 0.5)

    M = nx.attr_matrix(G, edge_attr=edge_attr, node_attr=node_attr)
    np.testing.assert_equal(M[0], np.array([[6.0]]))
    assert M[1] == [1.5]


def test_attr_matrix_directed():
    G = nx.DiGraph()
    G.add_edge(0, 1, thickness=1, weight=3)
    G.add_edge(0, 1, thickness=1, weight=3)
    G.add_edge(0, 2, thickness=2)
    G.add_edge(1, 2, thickness=3)
    M = nx.attr_matrix(G, rc_order=[0, 1, 2])
    # fmt: off
    data = np.array(
        [[0., 1., 1.],
         [0., 0., 1.],
         [0., 0., 0.]]
    )
    # fmt: on
    np.testing.assert_equal(M, np.array(data))


def test_attr_matrix_multigraph():
    G = nx.MultiGraph()
    G.add_edge(0, 1, thickness=1, weight=3)
    G.add_edge(0, 1, thickness=1, weight=3)
    G.add_edge(0, 1, thickness=1, weight=3)
    G.add_edge(0, 2, thickness=2)
    G.add_edge(1, 2, thickness=3)
    M = nx.attr_matrix(G, rc_order=[0, 1, 2])
    # fmt: off
    data = np.array(
        [[0., 3., 1.],
         [3., 0., 1.],
         [1., 1., 0.]]
    )
    # fmt: on
    np.testing.assert_equal(M, np.array(data))
    M = nx.attr_matrix(G, edge_attr="weight", rc_order=[0, 1, 2])
    # fmt: off
    data = np.array(
        [[0., 9., 1.],
         [9., 0., 1.],
         [1., 1., 0.]]
    )
    # fmt: on
    np.testing.assert_equal(M, np.array(data))
    M = nx.attr_matrix(G, edge_attr="thickness", rc_order=[0, 1, 2])
    # fmt: off
    data = np.array(
        [[0., 3., 2.],
         [3., 0., 3.],
         [2., 3., 0.]]
    )
    # fmt: on
    np.testing.assert_equal(M, np.array(data))


def test_attr_sparse_matrix():
    pytest.importorskip("scipy")
    G = nx.Graph()
    G.add_edge(0, 1, thickness=1, weight=3)
    G.add_edge(0, 2, thickness=2)
    G.add_edge(1, 2, thickness=3)
    M = nx.attr_sparse_matrix(G)
    mtx = M[0]
    data = np.ones((3, 3), float)
    np.fill_diagonal(data, 0)
    np.testing.assert_equal(mtx.todense(), np.array(data))
    assert M[1] == [0, 1, 2]


def test_attr_sparse_matrix_directed():
    pytest.importorskip("scipy")
    G = nx.DiGraph()
    G.add_edge(0, 1, thickness=1, weight=3)
    G.add_edge(0, 1, thickness=1, weight=3)
    G.add_edge(0, 2, thickness=2)
    G.add_edge(1, 2, thickness=3)
    M = nx.attr_sparse_matrix(G, rc_order=[0, 1, 2])
    # fmt: off
    data = np.array(
        [[0., 1., 1.],
         [0., 0., 1.],
         [0., 0., 0.]]
    )
    # fmt: on
    np.testing.assert_equal(M.todense(), np.array(data))
