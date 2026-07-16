"""Unit tests for the :mod:`networkx.algorithms.walks` module."""

import pytest

import networkx as nx

pytest.importorskip("numpy")
pytest.importorskip("scipy")


def test_directed():
    G = nx.DiGraph([(0, 1), (1, 2), (2, 0)])
    num_walks = nx.number_of_walks(G, 3)
    expected = {0: {0: 1, 1: 0, 2: 0}, 1: {0: 0, 1: 1, 2: 0}, 2: {0: 0, 1: 0, 2: 1}}
    assert num_walks == expected


def test_undirected():
    G = nx.cycle_graph(3)
    num_walks = nx.number_of_walks(G, 3)
    expected = {0: {0: 2, 1: 3, 2: 3}, 1: {0: 3, 1: 2, 2: 3}, 2: {0: 3, 1: 3, 2: 2}}
    assert num_walks == expected


def test_non_integer_nodes():
    G = nx.DiGraph([("A", "B"), ("B", "C"), ("C", "A")])
    num_walks = nx.number_of_walks(G, 2)
    expected = {
        "A": {"A": 0, "B": 0, "C": 1},
        "B": {"A": 1, "B": 0, "C": 0},
        "C": {"A": 0, "B": 1, "C": 0},
    }
    assert num_walks == expected


def test_zero_length():
    G = nx.cycle_graph(3)
    num_walks = nx.number_of_walks(G, 0)
    expected = {0: {0: 1, 1: 0, 2: 0}, 1: {0: 0, 1: 1, 2: 0}, 2: {0: 0, 1: 0, 2: 1}}
    assert num_walks == expected


def test_negative_length_exception():
    G = nx.cycle_graph(3)
    with pytest.raises(ValueError):
        nx.number_of_walks(G, -1)


def test_hidden_weight_attr():
    G = nx.cycle_graph(3)
    G.add_edge(1, 2, weight=5)
    num_walks = nx.number_of_walks(G, 3)
    expected = {0: {0: 2, 1: 3, 2: 3}, 1: {0: 3, 1: 2, 2: 3}, 2: {0: 3, 1: 3, 2: 2}}
    assert num_walks == expected
