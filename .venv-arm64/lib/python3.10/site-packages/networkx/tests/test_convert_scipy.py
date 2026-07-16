import pytest

np = pytest.importorskip("numpy")
sp = pytest.importorskip("scipy")

import networkx as nx
from networkx.generators.classic import barbell_graph, cycle_graph, path_graph
from networkx.utils import graphs_equal


class TestConvertScipy:
    def setup_method(self):
        self.G1 = barbell_graph(10, 3)
        self.G2 = cycle_graph(10, create_using=nx.DiGraph)

        self.G3 = self.create_weighted(nx.Graph())
        self.G4 = self.create_weighted(nx.DiGraph())

    def test_exceptions(self):
        class G:
            format = None

        pytest.raises(nx.NetworkXError, nx.to_networkx_graph, G)

    def create_weighted(self, G):
        g = cycle_graph(4)
        e = list(g.edges())
        source = [u for u, v in e]
        dest = [v for u, v in e]
        weight = [s + 10 for s in source]
        ex = zip(source, dest, weight)
        G.add_weighted_edges_from(ex)
        return G

    def identity_conversion(self, G, A, create_using):
        GG = nx.from_scipy_sparse_array(A, create_using=create_using)
        assert nx.is_isomorphic(G, GG)

        GW = nx.to_networkx_graph(A, create_using=create_using)
        assert nx.is_isomorphic(G, GW)

        GI = nx.empty_graph(0, create_using).__class__(A)
        assert nx.is_isomorphic(G, GI)

        ACSR = A.tocsr()
        GI = nx.empty_graph(0, create_using).__class__(ACSR)
        assert nx.is_isomorphic(G, GI)

        ACOO = A.tocoo()
        GI = nx.empty_graph(0, create_using).__class__(ACOO)
        assert nx.is_isomorphic(G, GI)

        ACSC = A.tocsc()
        GI = nx.empty_graph(0, create_using).__class__(ACSC)
        assert nx.is_isomorphic(G, GI)

        AD = A.todense()
        GI = nx.empty_graph(0, create_using).__class__(AD)
        assert nx.is_isomorphic(G, GI)

        AA = A.toarray()
        GI = nx.empty_graph(0, create_using).__class__(AA)
        assert nx.is_isomorphic(G, GI)

    def test_shape(self):
        "Conversion from non-square sparse array."
        A = sp.sparse.lil_array([[1, 2, 3], [4, 5, 6]])
        pytest.raises(nx.NetworkXError, nx.from_scipy_sparse_array, A)

    def test_identity_graph_matrix(self):
        "Conversion from graph to sparse matrix to graph."
        A = nx.to_scipy_sparse_array(self.G1)
        self.identity_conversion(self.G1, A, nx.Graph())

    def test_identity_digraph_matrix(self):
        "Conversion from digraph to sparse matrix to digraph."
        A = nx.to_scipy_sparse_array(self.G2)
        self.identity_conversion(self.G2, A, nx.DiGraph())

    def test_identity_weighted_graph_matrix(self):
        """Conversion from weighted graph to sparse matrix to weighted graph."""
        A = nx.to_scipy_sparse_array(self.G3)
        self.identity_conversion(self.G3, A, nx.Graph())

    def test_identity_weighted_digraph_matrix(self):
        """Conversion from weighted digraph to sparse matrix to weighted digraph."""
        A = nx.to_scipy_sparse_array(self.G4)
        self.identity_conversion(self.G4, A, nx.DiGraph())

    def test_nodelist(self):
        """Conversion from graph to sparse matrix to graph with nodelist."""
        P4 = path_graph(4)
        P3 = path_graph(3)
        nodelist = list(P3.nodes())
        A = nx.to_scipy_sparse_array(P4, nodelist=nodelist)
        GA = nx.Graph(A)
        assert nx.is_isomorphic(GA, P3)

        pytest.raises(nx.NetworkXError, nx.to_scipy_sparse_array, P3, nodelist=[])
        # Test nodelist duplicates.
        long_nl = nodelist + [0]
        pytest.raises(nx.NetworkXError, nx.to_scipy_sparse_array, P3, nodelist=long_nl)

        # Test nodelist contains non-nodes
        non_nl = [-1, 0, 1, 2]
        pytest.raises(nx.NetworkXError, nx.to_scipy_sparse_array, P3, nodelist=non_nl)

    def test_weight_keyword(self):
        WP4 = nx.Graph()
        WP4.add_edges_from((n, n + 1, {"weight": 0.5, "other": 0.3}) for n in range(3))
        P4 = path_graph(4)
        A = nx.to_scipy_sparse_array(P4)
        np.testing.assert_equal(
            A.todense(), nx.to_scipy_sparse_array(WP4, weight=None).todense()
        )
        np.testing.assert_equal(
            0.5 * A.todense(), nx.to_scipy_sparse_array(WP4).todense()
        )
        np.testing.assert_equal(
            0.3 * A.todense(), nx.to_scipy_sparse_array(WP4, weight="other").todense()
        )

    def test_format_keyword(self):
        WP4 = nx.Graph()
        WP4.add_edges_from((n, n + 1, {"weight": 0.5, "other": 0.3}) for n in range(3))
        P4 = path_graph(4)
        A = nx.to_scipy_sparse_array(P4, format="csr")
        np.testing.assert_equal(
            A.todense(), nx.to_scipy_sparse_array(WP4, weight=None).todense()
        )

        A = nx.to_scipy_sparse_array(P4, format="csc")
        np.testing.assert_equal(
            A.todense(), nx.to_scipy_sparse_array(WP4, weight=None).todense()
        )

        A = nx.to_scipy_sparse_array(P4, format="coo")
        np.testing.assert_equal(
            A.todense(), nx.to_scipy_sparse_array(WP4, weight=None).todense()
        )

        A = nx.to_scipy_sparse_array(P4, format="bsr")
        np.testing.assert_equal(
            A.todense(), nx.to_scipy_sparse_array(WP4, weight=None).todense()
        )

        A = nx.to_scipy_sparse_array(P4, format="lil")
        np.testing.assert_equal(
            A.todense(), nx.to_scipy_sparse_array(WP4, weight=None).todense()
        )

        A = nx.to_scipy_sparse_array(P4, format="dia")
        np.testing.assert_equal(
            A.todense(), nx.to_scipy_sparse_array(WP4, weight=None).todense()
        )

        A = nx.to_scipy_sparse_array(P4, format="dok")
        np.testing.assert_equal(
            A.todense(), nx.to_scipy_sparse_array(WP4, weight=None).todense()
        )

    def test_format_keyword_raise(self):
        with pytest.raises(nx.NetworkXError):
            WP4 = nx.Graph()
            WP4.add_edges_from(
                (n, n + 1, {"weight": 0.5, "other": 0.3}) for n in range(3)
            )
            P4 = path_graph(4)
            nx.to_scipy_sparse_array(P4, format="any_other")

    def test_null_raise(self):
        with pytest.raises(nx.NetworkXError):
            nx.to_scipy_sparse_array(nx.Graph())

    def test_empty(self):
        G = nx.Graph()
        G.add_node(1)
        M = nx.to_scipy_sparse_array(G)
        np.testing.assert_equal(M.toarray(), np.array([[0]]))

    def test_ordering(self):
        G = nx.DiGraph()
        G.add_edge(1, 2)
        G.add_edge(2, 3)
        G.add_edge(3, 1)
        M = nx.to_scipy_sparse_array(G, nodelist=[3, 2, 1])
        np.testing.assert_equal(
            M.toarray(), np.array([[0, 0, 1], [1, 0, 0], [0, 1, 0]])
        )

    def test_selfloop_graph(self):
        G = nx.Graph([(1, 1)])
        M = nx.to_scipy_sparse_array(G)
        np.testing.assert_equal(M.toarray(), np.array([[1]]))

        G.add_edges_from([(2, 3), (3, 4)])
        M = nx.to_scipy_sparse_array(G, nodelist=[2, 3, 4])
        np.testing.assert_equal(
            M.toarray(), np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]])
        )

    def test_selfloop_digraph(self):
        G = nx.DiGraph([(1, 1)])
        M = nx.to_scipy_sparse_array(G)
        np.testing.assert_equal(M.toarray(), np.array([[1]]))

        G.add_edges_from([(2, 3), (3, 4)])
        M = nx.to_scipy_sparse_array(G, nodelist=[2, 3, 4])
        np.testing.assert_equal(
            M.toarray(), np.array([[0, 1, 0], [0, 0, 1], [0, 0, 0]])
        )

    def test_from_scipy_sparse_array_parallel_edges(self):
        """Tests that the :func:`networkx.from_scipy_sparse_array` function
        interprets integer weights as the number of parallel edges when
        creating a multigraph.

        """
        A = sp.sparse.csr_array([[1, 1], [1, 2]])
        # First, with a simple graph, each integer entry in the adjacency
        # matrix is interpreted as the weight of a single edge in the graph.
        expected = nx.DiGraph()
        edges = [(0, 0), (0, 1), (1, 0)]
        expected.add_weighted_edges_from([(u, v, 1) for (u, v) in edges])
        expected.add_edge(1, 1, weight=2)
        actual = nx.from_scipy_sparse_array(
            A, parallel_edges=True, create_using=nx.DiGraph
        )
        assert graphs_equal(actual, expected)
        actual = nx.from_scipy_sparse_array(
            A, parallel_edges=False, create_using=nx.DiGraph
        )
        assert graphs_equal(actual, expected)
        # Now each integer entry in the adjacency matrix is interpreted as the
        # number of parallel edges in the graph if the appropriate keyword
        # argument is specified.
        edges = [(0, 0), (0, 1), (1, 0), (1, 1), (1, 1)]
        expected = nx.MultiDiGraph()
        expected.add_weighted_edges_from([(u, v, 1) for (u, v) in edges])
        actual = nx.from_scipy_sparse_array(
            A, parallel_edges=True, create_using=nx.MultiDiGraph
        )
        assert graphs_equal(actual, expected)
        expected = nx.MultiDiGraph()
        expected.add_edges_from(set(edges), weight=1)
        # The sole self-loop (edge 0) on vertex 1 should have weight 2.
        expected[1][1][0]["weight"] = 2
        actual = nx.from_scipy_sparse_array(
            A, parallel_edges=False, create_using=nx.MultiDiGraph
        )
        assert graphs_equal(actual, expected)

    def test_symmetric(self):
        """Tests that a symmetric matrix has edges added only once to an
        undirected multigraph when using
        :func:`networkx.from_scipy_sparse_array`.

        """
        A = sp.sparse.csr_array([[0, 1], [1, 0]])
        G = nx.from_scipy_sparse_array(A, create_using=nx.MultiGraph)
        expected = nx.MultiGraph()
        expected.add_edge(0, 1, weight=1)
        assert graphs_equal(G, expected)


@pytest.mark.parametrize("sparse_format", ("csr", "csc", "dok"))
def test_from_scipy_sparse_array_formats(sparse_format):
    """Test all formats supported by _generate_weighted_edges."""
    # trinode complete graph with non-uniform edge weights
    expected = nx.Graph()
    expected.add_edges_from(
        [
            (0, 1, {"weight": 3}),
            (0, 2, {"weight": 2}),
            (1, 0, {"weight": 3}),
            (1, 2, {"weight": 1}),
            (2, 0, {"weight": 2}),
            (2, 1, {"weight": 1}),
        ]
    )
    A = sp.sparse.coo_array([[0, 3, 2], [3, 0, 1], [2, 1, 0]]).asformat(sparse_format)
    assert graphs_equal(expected, nx.from_scipy_sparse_array(A))
