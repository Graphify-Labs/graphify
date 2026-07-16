import pytest

np = pytest.importorskip("numpy")
sp = pytest.importorskip("scipy")
sparse = pytest.importorskip("scipy.sparse")


import networkx as nx
from networkx.algorithms import bipartite
from networkx.utils import edges_equal


class TestBiadjacencyMatrix:
    def test_biadjacency_matrix_weight(self):
        G = nx.path_graph(5)
        G.add_edge(0, 1, weight=2, other=4)
        X = [1, 3]
        Y = [0, 2, 4]
        M = bipartite.biadjacency_matrix(G, X, weight="weight")
        assert M[0, 0] == 2
        M = bipartite.biadjacency_matrix(G, X, weight="other")
        assert M[0, 0] == 4

    def test_biadjacency_matrix(self):
        tops = [2, 5, 10]
        bots = [5, 10, 15]
        for i in range(len(tops)):
            G = bipartite.random_graph(tops[i], bots[i], 0.2)
            top = [n for n, d in G.nodes(data=True) if d["bipartite"] == 0]
            M = bipartite.biadjacency_matrix(G, top)
            assert M.shape[0] == tops[i]
            assert M.shape[1] == bots[i]

    def test_biadjacency_matrix_order(self):
        G = nx.path_graph(5)
        G.add_edge(0, 1, weight=2)
        X = [3, 1]
        Y = [4, 2, 0]
        M = bipartite.biadjacency_matrix(G, X, Y, weight="weight")
        assert M[1, 2] == 2

    def test_biadjacency_matrix_empty_graph(self):
        G = nx.empty_graph(2)
        M = nx.bipartite.biadjacency_matrix(G, [0])
        assert np.array_equal(M.toarray(), np.array([[0]]))

    def test_null_graph(self):
        with pytest.raises(nx.NetworkXError):
            bipartite.biadjacency_matrix(nx.Graph(), [])

    def test_empty_graph(self):
        with pytest.raises(nx.NetworkXError):
            bipartite.biadjacency_matrix(nx.Graph([(1, 0)]), [])

    def test_duplicate_row(self):
        with pytest.raises(nx.NetworkXError):
            bipartite.biadjacency_matrix(nx.Graph([(1, 0)]), [1, 1])

    def test_duplicate_col(self):
        with pytest.raises(nx.NetworkXError):
            bipartite.biadjacency_matrix(nx.Graph([(1, 0)]), [0], [1, 1])

    def test_format_keyword(self):
        with pytest.raises(nx.NetworkXError):
            bipartite.biadjacency_matrix(nx.Graph([(1, 0)]), [0], format="foo")

    def test_from_biadjacency_roundtrip(self):
        B1 = nx.path_graph(5)
        M = bipartite.biadjacency_matrix(B1, [0, 2, 4])
        B2 = bipartite.from_biadjacency_matrix(M)
        assert nx.is_isomorphic(B1, B2)

    def test_from_biadjacency_weight(self):
        M = sparse.csc_matrix([[1, 2], [0, 3]])
        B = bipartite.from_biadjacency_matrix(M)
        assert edges_equal(B.edges(), [(0, 2), (0, 3), (1, 3)])
        B = bipartite.from_biadjacency_matrix(M, edge_attribute="weight")
        e = [(0, 2, {"weight": 1}), (0, 3, {"weight": 2}), (1, 3, {"weight": 3})]
        assert edges_equal(B.edges(data=True), e)

    def test_from_biadjacency_multigraph(self):
        M = sparse.csc_matrix([[1, 2], [0, 3]])
        B = bipartite.from_biadjacency_matrix(M, create_using=nx.MultiGraph())
        assert edges_equal(B.edges(), [(0, 2), (0, 3), (0, 3), (1, 3), (1, 3), (1, 3)])
