"""Unit tests for the :mod:`networkx.algorithms.bipartite.redundancy` module."""

import pytest

from networkx import NetworkXError, cycle_graph
from networkx.algorithms.bipartite import complete_bipartite_graph, node_redundancy


def test_no_redundant_nodes():
    G = complete_bipartite_graph(2, 2)

    # when nodes is None
    rc = node_redundancy(G)
    assert all(redundancy == 1 for redundancy in rc.values())

    # when set of nodes is specified
    rc = node_redundancy(G, (2, 3))
    assert rc == {2: 1.0, 3: 1.0}


def test_redundant_nodes():
    G = cycle_graph(6)
    edge = {0, 3}
    G.add_edge(*edge)
    redundancy = node_redundancy(G)
    for v in edge:
        assert redundancy[v] == 2 / 3
    for v in set(G) - edge:
        assert redundancy[v] == 1


def test_not_enough_neighbors():
    with pytest.raises(NetworkXError):
        G = complete_bipartite_graph(1, 2)
        node_redundancy(G)
