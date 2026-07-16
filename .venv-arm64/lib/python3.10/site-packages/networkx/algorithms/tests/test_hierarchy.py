import pytest

import networkx as nx


def test_hierarchy_undirected():
    G = nx.cycle_graph(5)
    pytest.raises(nx.NetworkXError, nx.flow_hierarchy, G)


def test_hierarchy_cycle():
    G = nx.cycle_graph(5, create_using=nx.DiGraph())
    assert nx.flow_hierarchy(G) == 0.0


def test_hierarchy_tree():
    G = nx.full_rary_tree(2, 16, create_using=nx.DiGraph())
    assert nx.flow_hierarchy(G) == 1.0


def test_hierarchy_1():
    G = nx.DiGraph()
    G.add_edges_from([(0, 1), (1, 2), (2, 3), (3, 1), (3, 4), (0, 4)])
    assert nx.flow_hierarchy(G) == 0.5


def test_hierarchy_weight():
    G = nx.DiGraph()
    G.add_edges_from(
        [
            (0, 1, {"weight": 0.3}),
            (1, 2, {"weight": 0.1}),
            (2, 3, {"weight": 0.1}),
            (3, 1, {"weight": 0.1}),
            (3, 4, {"weight": 0.3}),
            (0, 4, {"weight": 0.3}),
        ]
    )
    assert nx.flow_hierarchy(G, weight="weight") == 0.75


@pytest.mark.parametrize("n", (0, 1, 3))
def test_hierarchy_empty_graph(n):
    G = nx.empty_graph(n, create_using=nx.DiGraph)
    with pytest.raises(nx.NetworkXError, match=".*not applicable to empty graphs"):
        nx.flow_hierarchy(G)
