"""Unit tests for the :mod:`networkx.algorithms.tournament` module."""

from itertools import combinations

import pytest

from networkx import DiGraph
from networkx.algorithms.tournament import (
    hamiltonian_path,
    index_satisfying,
    is_reachable,
    is_strongly_connected,
    is_tournament,
    random_tournament,
    score_sequence,
    tournament_matrix,
)


def test_condition_not_satisfied():
    condition = lambda x: x > 0
    iter_in = [0]
    assert index_satisfying(iter_in, condition) == 1


def test_empty_iterable():
    condition = lambda x: x > 0
    with pytest.raises(ValueError):
        index_satisfying([], condition)


def test_is_tournament():
    G = DiGraph()
    G.add_edges_from([(0, 1), (1, 2), (2, 3), (3, 0), (1, 3), (0, 2)])
    assert is_tournament(G)


def test_self_loops():
    """A tournament must have no self-loops."""
    G = DiGraph()
    G.add_edges_from([(0, 1), (1, 2), (2, 3), (3, 0), (1, 3), (0, 2)])
    G.add_edge(0, 0)
    assert not is_tournament(G)


def test_missing_edges():
    """A tournament must not have any pair of nodes without at least
    one edge joining the pair.

    """
    G = DiGraph()
    G.add_edges_from([(0, 1), (1, 2), (2, 3), (3, 0), (1, 3)])
    assert not is_tournament(G)


def test_bidirectional_edges():
    """A tournament must not have any pair of nodes with greater
    than one edge joining the pair.

    """
    G = DiGraph()
    G.add_edges_from([(0, 1), (1, 2), (2, 3), (3, 0), (1, 3), (0, 2)])
    G.add_edge(1, 0)
    assert not is_tournament(G)


def test_graph_is_tournament():
    for _ in range(10):
        G = random_tournament(5)
        assert is_tournament(G)


def test_graph_is_tournament_seed():
    for _ in range(10):
        G = random_tournament(5, seed=1)
        assert is_tournament(G)


def test_graph_is_tournament_one_node():
    G = random_tournament(1)
    assert is_tournament(G)


def test_graph_is_tournament_zero_node():
    G = random_tournament(0)
    assert is_tournament(G)


def test_hamiltonian_empty_graph():
    path = hamiltonian_path(DiGraph())
    assert len(path) == 0


def test_path_is_hamiltonian():
    G = DiGraph()
    G.add_edges_from([(0, 1), (1, 2), (2, 3), (3, 0), (1, 3), (0, 2)])
    path = hamiltonian_path(G)
    assert len(path) == 4
    assert all(v in G[u] for u, v in zip(path, path[1:]))


def test_hamiltonian_cycle():
    """Tests that :func:`networkx.tournament.hamiltonian_path`
    returns a Hamiltonian cycle when provided a strongly connected
    tournament.

    """
    G = DiGraph()
    G.add_edges_from([(0, 1), (1, 2), (2, 3), (3, 0), (1, 3), (0, 2)])
    path = hamiltonian_path(G)
    assert len(path) == 4
    assert all(v in G[u] for u, v in zip(path, path[1:]))
    assert path[0] in G[path[-1]]


def test_score_sequence_edge():
    G = DiGraph([(0, 1)])
    assert score_sequence(G) == [0, 1]


def test_score_sequence_triangle():
    G = DiGraph([(0, 1), (1, 2), (2, 0)])
    assert score_sequence(G) == [1, 1, 1]


def test_tournament_matrix():
    np = pytest.importorskip("numpy")
    pytest.importorskip("scipy")
    npt = np.testing
    G = DiGraph([(0, 1)])
    m = tournament_matrix(G)
    npt.assert_array_equal(m.todense(), np.array([[0, 1], [-1, 0]]))


def test_reachable_pair():
    """Tests for a reachable pair of nodes."""
    G = DiGraph([(0, 1), (1, 2), (2, 0)])
    assert is_reachable(G, 0, 2)


def test_same_node_is_reachable():
    """Tests that a node is always reachable from it."""
    # G is an arbitrary tournament on ten nodes.
    G = DiGraph(sorted(p) for p in combinations(range(10), 2))
    assert all(is_reachable(G, v, v) for v in G)


def test_unreachable_pair():
    """Tests for an unreachable pair of nodes."""
    G = DiGraph([(0, 1), (0, 2), (1, 2)])
    assert not is_reachable(G, 1, 0)


def test_is_strongly_connected():
    """Tests for a strongly connected tournament."""
    G = DiGraph([(0, 1), (1, 2), (2, 0)])
    assert is_strongly_connected(G)


def test_not_strongly_connected():
    """Tests for a tournament that is not strongly connected."""
    G = DiGraph([(0, 1), (0, 2), (1, 2)])
    assert not is_strongly_connected(G)
