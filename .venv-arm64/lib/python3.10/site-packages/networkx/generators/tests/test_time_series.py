"""Unit tests for the :mod:`networkx.generators.time_series` module."""

import itertools

import networkx as nx


def test_visibility_graph__empty_series__empty_graph():
    null_graph = nx.visibility_graph([])  # move along nothing to see here
    assert nx.is_empty(null_graph)


def test_visibility_graph__single_value_ts__single_node_graph():
    node_graph = nx.visibility_graph([10])  # So Lonely
    assert node_graph.number_of_nodes() == 1
    assert node_graph.number_of_edges() == 0


def test_visibility_graph__two_values_ts__single_edge_graph():
    edge_graph = nx.visibility_graph([10, 20])  # Two of Us
    assert list(edge_graph.edges) == [(0, 1)]


def test_visibility_graph__convex_series__complete_graph():
    series = [i**2 for i in range(10)]  # no obstructions
    expected_series_length = len(series)

    actual_graph = nx.visibility_graph(series)

    assert actual_graph.number_of_nodes() == expected_series_length
    assert actual_graph.number_of_edges() == 45
    assert nx.is_isomorphic(actual_graph, nx.complete_graph(expected_series_length))


def test_visibility_graph__concave_series__path_graph():
    series = [-(i**2) for i in range(10)]  # Slip Slidin' Away
    expected_node_count = len(series)

    actual_graph = nx.visibility_graph(series)

    assert actual_graph.number_of_nodes() == expected_node_count
    assert actual_graph.number_of_edges() == expected_node_count - 1
    assert nx.is_isomorphic(actual_graph, nx.path_graph(expected_node_count))


def test_visibility_graph__flat_series__path_graph():
    series = [0] * 10  # living in 1D flatland
    expected_node_count = len(series)

    actual_graph = nx.visibility_graph(series)

    assert actual_graph.number_of_nodes() == expected_node_count
    assert actual_graph.number_of_edges() == expected_node_count - 1
    assert nx.is_isomorphic(actual_graph, nx.path_graph(expected_node_count))


def test_visibility_graph_cyclic_series():
    series = list(itertools.islice(itertools.cycle((2, 1, 3)), 17))  # It's so bumpy!
    expected_node_count = len(series)

    actual_graph = nx.visibility_graph(series)

    assert actual_graph.number_of_nodes() == expected_node_count
    assert actual_graph.number_of_edges() == 25
