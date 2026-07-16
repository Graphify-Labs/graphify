from itertools import chain

import pytest

import networkx as nx


def _check_partition(G, cut_value, partition, weight):
    assert isinstance(partition, tuple)
    assert len(partition) == 2
    assert isinstance(partition[0], list)
    assert isinstance(partition[1], list)
    assert len(partition[0]) > 0
    assert len(partition[1]) > 0
    assert sum(map(len, partition)) == len(G)
    assert set(chain.from_iterable(partition)) == set(G)
    partition = tuple(map(set, partition))
    w = 0
    for u, v, e in G.edges(data=True):
        if (u in partition[0]) == (v in partition[1]):
            w += e.get(weight, 1)
    assert w == cut_value


def _test_stoer_wagner(G, answer, weight="weight"):
    cut_value, partition = nx.stoer_wagner(G, weight, heap=nx.utils.PairingHeap)
    assert cut_value == answer
    _check_partition(G, cut_value, partition, weight)
    cut_value, partition = nx.stoer_wagner(G, weight, heap=nx.utils.BinaryHeap)
    assert cut_value == answer
    _check_partition(G, cut_value, partition, weight)


def test_graph1():
    G = nx.Graph()
    G.add_edge("x", "a", weight=3)
    G.add_edge("x", "b", weight=1)
    G.add_edge("a", "c", weight=3)
    G.add_edge("b", "c", weight=5)
    G.add_edge("b", "d", weight=4)
    G.add_edge("d", "e", weight=2)
    G.add_edge("c", "y", weight=2)
    G.add_edge("e", "y", weight=3)
    _test_stoer_wagner(G, 4)


def test_graph2():
    G = nx.Graph()
    G.add_edge("x", "a")
    G.add_edge("x", "b")
    G.add_edge("a", "c")
    G.add_edge("b", "c")
    G.add_edge("b", "d")
    G.add_edge("d", "e")
    G.add_edge("c", "y")
    G.add_edge("e", "y")
    _test_stoer_wagner(G, 2)


def test_graph3():
    # Source:
    # Stoer, M. and Wagner, F. (1997). "A simple min-cut algorithm". Journal of
    # the ACM 44 (4), 585-591.
    G = nx.Graph()
    G.add_edge(1, 2, weight=2)
    G.add_edge(1, 5, weight=3)
    G.add_edge(2, 3, weight=3)
    G.add_edge(2, 5, weight=2)
    G.add_edge(2, 6, weight=2)
    G.add_edge(3, 4, weight=4)
    G.add_edge(3, 7, weight=2)
    G.add_edge(4, 7, weight=2)
    G.add_edge(4, 8, weight=2)
    G.add_edge(5, 6, weight=3)
    G.add_edge(6, 7, weight=1)
    G.add_edge(7, 8, weight=3)
    _test_stoer_wagner(G, 4)


def test_weight_name():
    G = nx.Graph()
    G.add_edge(1, 2, weight=1, cost=8)
    G.add_edge(1, 3, cost=2)
    G.add_edge(2, 3, cost=4)
    _test_stoer_wagner(G, 6, weight="cost")


def test_exceptions():
    G = nx.Graph()
    pytest.raises(nx.NetworkXError, nx.stoer_wagner, G)
    G.add_node(1)
    pytest.raises(nx.NetworkXError, nx.stoer_wagner, G)
    G.add_node(2)
    pytest.raises(nx.NetworkXError, nx.stoer_wagner, G)
    G.add_edge(1, 2, weight=-2)
    pytest.raises(nx.NetworkXError, nx.stoer_wagner, G)
    G = nx.DiGraph()
    pytest.raises(nx.NetworkXNotImplemented, nx.stoer_wagner, G)
    G = nx.MultiGraph()
    pytest.raises(nx.NetworkXNotImplemented, nx.stoer_wagner, G)
    G = nx.MultiDiGraph()
    pytest.raises(nx.NetworkXNotImplemented, nx.stoer_wagner, G)
