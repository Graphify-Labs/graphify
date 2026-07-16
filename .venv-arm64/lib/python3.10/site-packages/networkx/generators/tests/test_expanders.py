"""Unit tests for the :mod:`networkx.generators.expanders` module."""

import pytest

import networkx as nx


@pytest.mark.parametrize("n", (2, 3, 5, 6, 10))
def test_margulis_gabber_galil_graph_properties(n):
    g = nx.margulis_gabber_galil_graph(n)
    assert g.number_of_nodes() == n * n
    for node in g:
        assert g.degree(node) == 8
        assert len(node) == 2
        for i in node:
            assert int(i) == i
            assert 0 <= i < n


@pytest.mark.parametrize("n", (2, 3, 5, 6, 10))
def test_margulis_gabber_galil_graph_eigvals(n):
    np = pytest.importorskip("numpy")
    sp = pytest.importorskip("scipy")

    g = nx.margulis_gabber_galil_graph(n)
    # Eigenvalues are already sorted using the scipy eigvalsh,
    # but the implementation in numpy does not guarantee order.
    w = sorted(sp.linalg.eigvalsh(nx.adjacency_matrix(g).toarray()))
    assert w[-2] < 5 * np.sqrt(2)


@pytest.mark.parametrize("p", (3, 5, 7, 11))  # Primes
def test_chordal_cycle_graph(p):
    """Test for the :func:`networkx.chordal_cycle_graph` function."""
    G = nx.chordal_cycle_graph(p)
    assert len(G) == p
    # TODO The second largest eigenvalue should be smaller than a constant,
    # independent of the number of nodes in the graph:
    #
    #     eigs = sorted(sp.linalg.eigvalsh(nx.adjacency_matrix(G).toarray()))
    #     assert_less(eigs[-2], ...)
    #


@pytest.mark.parametrize("p", (3, 5, 7, 11, 13))  # Primes
def test_paley_graph(p):
    """Test for the :func:`networkx.paley_graph` function."""
    G = nx.paley_graph(p)
    # G has p nodes
    assert len(G) == p
    # G is (p-1)/2-regular
    in_degrees = {G.in_degree(node) for node in G.nodes}
    out_degrees = {G.out_degree(node) for node in G.nodes}
    assert len(in_degrees) == 1 and in_degrees.pop() == (p - 1) // 2
    assert len(out_degrees) == 1 and out_degrees.pop() == (p - 1) // 2

    # If p = 1 mod 4, -1 is a square mod 4 and therefore the
    # edge in the Paley graph are symmetric.
    if p % 4 == 1:
        for u, v in G.edges:
            assert (v, u) in G.edges


@pytest.mark.parametrize("d, n", [(2, 7), (4, 10), (4, 16)])
def test_maybe_regular_expander(d, n):
    pytest.importorskip("numpy")
    G = nx.maybe_regular_expander(n, d)

    assert len(G) == n, "Should have n nodes"
    assert len(G.edges) == n * d / 2, "Should have n*d/2 edges"
    assert nx.is_k_regular(G, d), "Should be d-regular"


@pytest.mark.parametrize("n", (3, 5, 6, 10))
def test_is_regular_expander(n):
    pytest.importorskip("numpy")
    pytest.importorskip("scipy")
    G = nx.complete_graph(n)

    assert nx.is_regular_expander(G) == True, "Should be a regular expander"


@pytest.mark.parametrize("d, n", [(2, 7), (4, 10), (4, 16)])
def test_random_regular_expander(d, n):
    pytest.importorskip("numpy")
    pytest.importorskip("scipy")
    G = nx.random_regular_expander_graph(n, d)

    assert len(G) == n, "Should have n nodes"
    assert len(G.edges) == n * d / 2, "Should have n*d/2 edges"
    assert nx.is_k_regular(G, d), "Should be d-regular"
    assert nx.is_regular_expander(G) == True, "Should be a regular expander"


def test_random_regular_expander_explicit_construction():
    pytest.importorskip("numpy")
    pytest.importorskip("scipy")
    G = nx.random_regular_expander_graph(d=4, n=5)

    assert len(G) == 5 and len(G.edges) == 10, "Should be a complete graph"


@pytest.mark.parametrize("graph_type", (nx.Graph, nx.DiGraph, nx.MultiDiGraph))
def test_margulis_gabber_galil_graph_badinput(graph_type):
    with pytest.raises(
        nx.NetworkXError, match="`create_using` must be an undirected multigraph"
    ):
        nx.margulis_gabber_galil_graph(3, create_using=graph_type)


@pytest.mark.parametrize("graph_type", (nx.Graph, nx.DiGraph, nx.MultiDiGraph))
def test_chordal_cycle_graph_badinput(graph_type):
    with pytest.raises(
        nx.NetworkXError, match="`create_using` must be an undirected multigraph"
    ):
        nx.chordal_cycle_graph(3, create_using=graph_type)


def test_paley_graph_badinput():
    with pytest.raises(
        nx.NetworkXError, match="`create_using` cannot be a multigraph."
    ):
        nx.paley_graph(3, create_using=nx.MultiGraph)


def test_maybe_regular_expander_badinput():
    pytest.importorskip("numpy")
    pytest.importorskip("scipy")

    with pytest.raises(nx.NetworkXError, match="n must be a positive integer"):
        nx.maybe_regular_expander(n=-1, d=2)

    with pytest.raises(nx.NetworkXError, match="d must be greater than or equal to 2"):
        nx.maybe_regular_expander(n=10, d=0)

    with pytest.raises(nx.NetworkXError, match="Need n-1>= d to have room"):
        nx.maybe_regular_expander(n=5, d=6)


def test_is_regular_expander_badinput():
    pytest.importorskip("numpy")
    pytest.importorskip("scipy")

    with pytest.raises(nx.NetworkXError, match="epsilon must be non negative"):
        nx.is_regular_expander(nx.Graph(), epsilon=-1)


def test_random_regular_expander_badinput():
    pytest.importorskip("numpy")
    pytest.importorskip("scipy")

    with pytest.raises(nx.NetworkXError, match="n must be a positive integer"):
        nx.random_regular_expander_graph(n=-1, d=2)

    with pytest.raises(nx.NetworkXError, match="d must be greater than or equal to 2"):
        nx.random_regular_expander_graph(n=10, d=0)

    with pytest.raises(nx.NetworkXError, match="Need n-1>= d to have room"):
        nx.random_regular_expander_graph(n=5, d=6)

    with pytest.raises(nx.NetworkXError, match="epsilon must be non negative"):
        nx.random_regular_expander_graph(n=4, d=2, epsilon=-1)
