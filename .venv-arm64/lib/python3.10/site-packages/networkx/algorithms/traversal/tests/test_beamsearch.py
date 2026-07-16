"""Unit tests for the beam search functions."""

import pytest

import networkx as nx


def test_narrow():
    """Tests that a narrow beam width may cause an incomplete search."""
    # In this search, we enqueue only the neighbor 3 at the first
    # step, then only the neighbor 2 at the second step. Once at
    # node 2, the search chooses node 3, since it has a higher value
    # than node 1, but node 3 has already been visited, so the
    # search terminates.
    G = nx.cycle_graph(4)
    edges = nx.bfs_beam_edges(G, source=0, value=lambda n: n, width=1)
    assert list(edges) == [(0, 3), (3, 2)]


@pytest.mark.parametrize("width", (2, None))
def test_wide(width):
    """All nodes are searched when `width` is None or >= max degree"""
    G = nx.cycle_graph(4)
    edges = nx.bfs_beam_edges(G, source=0, value=lambda n: n, width=width)
    assert list(edges) == [(0, 3), (0, 1), (3, 2)]
