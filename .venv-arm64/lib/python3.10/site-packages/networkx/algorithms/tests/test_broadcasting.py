"""Unit tests for the broadcasting module."""

import math

import networkx as nx


def test_example_tree_broadcast():
    """
    Test the BROADCAST algorithm on the example in the paper titled: "Information Dissemination in Trees"
    """
    edge_list = [
        (0, 1),
        (1, 2),
        (2, 7),
        (3, 4),
        (5, 4),
        (4, 7),
        (6, 7),
        (7, 9),
        (8, 9),
        (9, 13),
        (13, 14),
        (14, 15),
        (14, 16),
        (14, 17),
        (13, 11),
        (11, 10),
        (11, 12),
        (13, 18),
        (18, 19),
        (18, 20),
    ]
    G = nx.Graph(edge_list)
    b_T, b_C = nx.tree_broadcast_center(G)
    assert b_T == 6
    assert b_C == {13, 9}
    # test broadcast time from specific vertex
    assert nx.tree_broadcast_time(G, 17) == 8
    assert nx.tree_broadcast_time(G, 3) == 9
    # test broadcast time of entire tree
    assert nx.tree_broadcast_time(G) == 10


def test_path_broadcast():
    for i in range(2, 12):
        G = nx.path_graph(i)
        b_T, b_C = nx.tree_broadcast_center(G)
        assert b_T == math.ceil(i / 2)
        assert b_C == {
            math.ceil(i / 2),
            math.floor(i / 2),
            math.ceil(i / 2 - 1),
            math.floor(i / 2 - 1),
        }
        assert nx.tree_broadcast_time(G) == i - 1


def test_empty_graph_broadcast():
    H = nx.empty_graph(1)
    b_T, b_C = nx.tree_broadcast_center(H)
    assert b_T == 0
    assert b_C == {0}
    assert nx.tree_broadcast_time(H) == 0


def test_star_broadcast():
    for i in range(4, 12):
        G = nx.star_graph(i)
        b_T, b_C = nx.tree_broadcast_center(G)
        assert b_T == i
        assert b_C == set(G.nodes())
        assert nx.tree_broadcast_time(G) == b_T


def test_binomial_tree_broadcast():
    for i in range(2, 8):
        G = nx.binomial_tree(i)
        b_T, b_C = nx.tree_broadcast_center(G)
        assert b_T == i
        assert b_C == {0, 2 ** (i - 1)}
        assert nx.tree_broadcast_time(G) == 2 * i - 1
