"""Unit tests for the :mod:`networkx.generators.lattice` module."""

from itertools import product

import pytest

import networkx as nx
from networkx.utils import edges_equal


class TestGrid2DGraph:
    """Unit tests for :func:`networkx.generators.lattice.grid_2d_graph`"""

    def test_number_of_vertices(self):
        m, n = 5, 6
        G = nx.grid_2d_graph(m, n)
        assert len(G) == m * n

    def test_degree_distribution(self):
        m, n = 5, 6
        G = nx.grid_2d_graph(m, n)
        expected_histogram = [0, 0, 4, 2 * (m + n) - 8, (m - 2) * (n - 2)]
        assert nx.degree_histogram(G) == expected_histogram

    def test_directed(self):
        m, n = 5, 6
        G = nx.grid_2d_graph(m, n)
        H = nx.grid_2d_graph(m, n, create_using=nx.DiGraph())
        assert H.succ == G.adj
        assert H.pred == G.adj

    def test_multigraph(self):
        m, n = 5, 6
        G = nx.grid_2d_graph(m, n)
        H = nx.grid_2d_graph(m, n, create_using=nx.MultiGraph())
        assert list(H.edges()) == list(G.edges())

    def test_periodic(self):
        G = nx.grid_2d_graph(0, 0, periodic=True)
        assert dict(G.degree()) == {}

        for m, n, H in [
            (2, 2, nx.cycle_graph(4)),
            (1, 7, nx.cycle_graph(7)),
            (7, 1, nx.cycle_graph(7)),
            (2, 5, nx.circular_ladder_graph(5)),
            (5, 2, nx.circular_ladder_graph(5)),
            (2, 4, nx.cubical_graph()),
            (4, 2, nx.cubical_graph()),
        ]:
            G = nx.grid_2d_graph(m, n, periodic=True)
            assert nx.could_be_isomorphic(G, H)

    def test_periodic_iterable(self):
        m, n = 3, 7
        for a, b in product([0, 1], [0, 1]):
            G = nx.grid_2d_graph(m, n, periodic=(a, b))
            assert G.number_of_nodes() == m * n
            assert G.number_of_edges() == (m + a - 1) * n + (n + b - 1) * m

    def test_periodic_directed(self):
        G = nx.grid_2d_graph(4, 2, periodic=True)
        H = nx.grid_2d_graph(4, 2, periodic=True, create_using=nx.DiGraph())
        assert H.succ == G.adj
        assert H.pred == G.adj

    def test_periodic_multigraph(self):
        G = nx.grid_2d_graph(4, 2, periodic=True)
        H = nx.grid_2d_graph(4, 2, periodic=True, create_using=nx.MultiGraph())
        assert list(G.edges()) == list(H.edges())

    def test_exceptions(self):
        pytest.raises(nx.NetworkXError, nx.grid_2d_graph, -3, 2)
        pytest.raises(nx.NetworkXError, nx.grid_2d_graph, 3, -2)
        pytest.raises(TypeError, nx.grid_2d_graph, 3.3, 2)
        pytest.raises(TypeError, nx.grid_2d_graph, 3, 2.2)

    def test_node_input(self):
        G = nx.grid_2d_graph(4, 2, periodic=True)
        H = nx.grid_2d_graph(range(4), range(2), periodic=True)
        assert nx.is_isomorphic(H, G)
        H = nx.grid_2d_graph("abcd", "ef", periodic=True)
        assert nx.is_isomorphic(H, G)
        G = nx.grid_2d_graph(5, 6)
        H = nx.grid_2d_graph(range(5), range(6))
        assert edges_equal(H, G)


class TestGridGraph:
    """Unit tests for :func:`networkx.generators.lattice.grid_graph`"""

    def test_grid_graph(self):
        """grid_graph([n,m]) is a connected simple graph with the
        following properties:
        number_of_nodes = n*m
        degree_histogram = [0,0,4,2*(n+m)-8,(n-2)*(m-2)]
        """
        for n, m in [(3, 5), (5, 3), (4, 5), (5, 4)]:
            dim = [n, m]
            g = nx.grid_graph(dim)
            assert len(g) == n * m
            assert nx.degree_histogram(g) == [
                0,
                0,
                4,
                2 * (n + m) - 8,
                (n - 2) * (m - 2),
            ]

        for n, m in [(1, 5), (5, 1)]:
            dim = [n, m]
            g = nx.grid_graph(dim)
            assert len(g) == n * m
            assert nx.is_isomorphic(g, nx.path_graph(5))

    #        mg = nx.grid_graph([n,m], create_using=MultiGraph())
    #        assert_equal(mg.edges(), g.edges())

    def test_node_input(self):
        G = nx.grid_graph([range(7, 9), range(3, 6)])
        assert len(G) == 2 * 3
        assert nx.is_isomorphic(G, nx.grid_graph([2, 3]))

    def test_periodic_iterable(self):
        m, n, k = 3, 7, 5
        for a, b, c in product([0, 1], [0, 1], [0, 1]):
            G = nx.grid_graph([m, n, k], periodic=(a, b, c))
            num_e = (m + a - 1) * n * k + (n + b - 1) * m * k + (k + c - 1) * m * n
            assert G.number_of_nodes() == m * n * k
            assert G.number_of_edges() == num_e


class TestHypercubeGraph:
    """Unit tests for :func:`networkx.generators.lattice.hypercube_graph`"""

    def test_special_cases(self):
        for n, H in [
            (0, nx.null_graph()),
            (1, nx.path_graph(2)),
            (2, nx.cycle_graph(4)),
            (3, nx.cubical_graph()),
        ]:
            G = nx.hypercube_graph(n)
            assert nx.could_be_isomorphic(G, H)

    def test_degree_distribution(self):
        for n in range(1, 10):
            G = nx.hypercube_graph(n)
            expected_histogram = [0] * n + [2**n]
            assert nx.degree_histogram(G) == expected_histogram


class TestTriangularLatticeGraph:
    "Tests for :func:`networkx.generators.lattice.triangular_lattice_graph`"

    def test_lattice_points(self):
        """Tests that the graph is really a triangular lattice."""
        for m, n in [(2, 3), (2, 2), (2, 1), (3, 3), (3, 2), (3, 4)]:
            G = nx.triangular_lattice_graph(m, n)
            N = (n + 1) // 2
            assert len(G) == (m + 1) * (1 + N) - (n % 2) * ((m + 1) // 2)
        for i, j in G.nodes():
            nbrs = G[(i, j)]
            if i < N:
                assert (i + 1, j) in nbrs
            if j < m:
                assert (i, j + 1) in nbrs
            if j < m and (i > 0 or j % 2) and (i < N or (j + 1) % 2):
                assert (i + 1, j + 1) in nbrs or (i - 1, j + 1) in nbrs

    def test_directed(self):
        """Tests for creating a directed triangular lattice."""
        G = nx.triangular_lattice_graph(3, 4, create_using=nx.Graph())
        H = nx.triangular_lattice_graph(3, 4, create_using=nx.DiGraph())
        assert H.is_directed()
        for u, v in H.edges():
            assert v[1] >= u[1]
            if v[1] == u[1]:
                assert v[0] > u[0]

    def test_multigraph(self):
        """Tests for creating a triangular lattice multigraph."""
        G = nx.triangular_lattice_graph(3, 4, create_using=nx.Graph())
        H = nx.triangular_lattice_graph(3, 4, create_using=nx.MultiGraph())
        assert list(H.edges()) == list(G.edges())

    def test_periodic(self):
        G = nx.triangular_lattice_graph(4, 6, periodic=True)
        assert len(G) == 12
        assert G.size() == 36
        # all degrees are 6
        assert len([n for n, d in G.degree() if d != 6]) == 0
        G = nx.triangular_lattice_graph(5, 7, periodic=True)
        TLG = nx.triangular_lattice_graph
        pytest.raises(nx.NetworkXError, TLG, 2, 4, periodic=True)
        pytest.raises(nx.NetworkXError, TLG, 4, 4, periodic=True)
        pytest.raises(nx.NetworkXError, TLG, 2, 6, periodic=True)


class TestHexagonalLatticeGraph:
    "Tests for :func:`networkx.generators.lattice.hexagonal_lattice_graph`"

    def test_lattice_points(self):
        """Tests that the graph is really a hexagonal lattice."""
        for m, n in [(4, 5), (4, 4), (4, 3), (3, 2), (3, 3), (3, 5)]:
            G = nx.hexagonal_lattice_graph(m, n)
            assert len(G) == 2 * (m + 1) * (n + 1) - 2
        C_6 = nx.cycle_graph(6)
        hexagons = [
            [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)],
            [(0, 2), (0, 3), (0, 4), (1, 2), (1, 3), (1, 4)],
            [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)],
            [(2, 0), (2, 1), (2, 2), (3, 0), (3, 1), (3, 2)],
            [(2, 2), (2, 3), (2, 4), (3, 2), (3, 3), (3, 4)],
        ]
        for hexagon in hexagons:
            assert nx.is_isomorphic(G.subgraph(hexagon), C_6)

    def test_directed(self):
        """Tests for creating a directed hexagonal lattice."""
        G = nx.hexagonal_lattice_graph(3, 5, create_using=nx.Graph())
        H = nx.hexagonal_lattice_graph(3, 5, create_using=nx.DiGraph())
        assert H.is_directed()
        pos = nx.get_node_attributes(H, "pos")
        for u, v in H.edges():
            assert pos[v][1] >= pos[u][1]
            if pos[v][1] == pos[u][1]:
                assert pos[v][0] > pos[u][0]

    def test_multigraph(self):
        """Tests for creating a hexagonal lattice multigraph."""
        G = nx.hexagonal_lattice_graph(3, 5, create_using=nx.Graph())
        H = nx.hexagonal_lattice_graph(3, 5, create_using=nx.MultiGraph())
        assert list(H.edges()) == list(G.edges())

    def test_periodic(self):
        G = nx.hexagonal_lattice_graph(4, 6, periodic=True)
        assert len(G) == 48
        assert G.size() == 72
        # all degrees are 3
        assert len([n for n, d in G.degree() if d != 3]) == 0
        G = nx.hexagonal_lattice_graph(5, 8, periodic=True)
        HLG = nx.hexagonal_lattice_graph
        pytest.raises(nx.NetworkXError, HLG, 2, 7, periodic=True)
        pytest.raises(nx.NetworkXError, HLG, 1, 4, periodic=True)
        pytest.raises(nx.NetworkXError, HLG, 2, 1, periodic=True)
