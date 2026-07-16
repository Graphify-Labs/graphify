import pytest

import networkx as nx


def test_selfloops_raises():
    G = nx.ladder_graph(3)
    G.add_edge(0, 0)
    with pytest.raises(nx.NetworkXError, match=".*not bipartite"):
        nx.bipartite.maximal_extendability(G)


def test_disconnected_raises():
    G = nx.ladder_graph(3)
    G.add_node("a")
    with pytest.raises(nx.NetworkXError, match=".*not connected"):
        nx.bipartite.maximal_extendability(G)


def test_not_bipartite_raises():
    G = nx.complete_graph(5)
    with pytest.raises(nx.NetworkXError, match=".*not bipartite"):
        nx.bipartite.maximal_extendability(G)


def test_no_perfect_matching_raises():
    G = nx.Graph([(0, 1), (0, 2)])
    with pytest.raises(nx.NetworkXError, match=".*not contain a perfect matching"):
        nx.bipartite.maximal_extendability(G)


def test_residual_graph_not_strongly_connected_raises():
    G = nx.Graph([(1, 2), (2, 3), (3, 4)])
    with pytest.raises(
        nx.NetworkXError, match="The residual graph of G is not strongly connected"
    ):
        nx.bipartite.maximal_extendability(G)


def test_ladder_graph_is_1():
    G = nx.ladder_graph(3)
    assert nx.bipartite.maximal_extendability(G) == 1


def test_cubical_graph_is_2():
    G = nx.cubical_graph()
    assert nx.bipartite.maximal_extendability(G) == 2


def test_k_is_3():
    G = nx.Graph(
        [
            (1, 6),
            (1, 7),
            (1, 8),
            (1, 9),
            (2, 6),
            (2, 7),
            (2, 8),
            (2, 10),
            (3, 6),
            (3, 8),
            (3, 9),
            (3, 10),
            (4, 7),
            (4, 8),
            (4, 9),
            (4, 10),
            (5, 6),
            (5, 7),
            (5, 9),
            (5, 10),
        ]
    )
    assert nx.bipartite.maximal_extendability(G) == 3


def test_k_is_4():
    G = nx.Graph(
        [
            (8, 1),
            (8, 2),
            (8, 3),
            (8, 4),
            (8, 5),
            (9, 1),
            (9, 2),
            (9, 3),
            (9, 4),
            (9, 7),
            (10, 1),
            (10, 2),
            (10, 3),
            (10, 4),
            (10, 6),
            (11, 1),
            (11, 2),
            (11, 5),
            (11, 6),
            (11, 7),
            (12, 1),
            (12, 3),
            (12, 5),
            (12, 6),
            (12, 7),
            (13, 2),
            (13, 4),
            (13, 5),
            (13, 6),
            (13, 7),
            (14, 3),
            (14, 4),
            (14, 5),
            (14, 6),
            (14, 7),
        ]
    )
    assert nx.bipartite.maximal_extendability(G) == 4


def test_k_is_5():
    G = nx.Graph(
        [
            (8, 1),
            (8, 2),
            (8, 3),
            (8, 4),
            (8, 5),
            (8, 6),
            (9, 1),
            (9, 2),
            (9, 3),
            (9, 4),
            (9, 5),
            (9, 7),
            (10, 1),
            (10, 2),
            (10, 3),
            (10, 4),
            (10, 6),
            (10, 7),
            (11, 1),
            (11, 2),
            (11, 3),
            (11, 5),
            (11, 6),
            (11, 7),
            (12, 1),
            (12, 2),
            (12, 4),
            (12, 5),
            (12, 6),
            (12, 7),
            (13, 1),
            (13, 3),
            (13, 4),
            (13, 5),
            (13, 6),
            (13, 7),
            (14, 2),
            (14, 3),
            (14, 4),
            (14, 5),
            (14, 6),
            (14, 7),
        ]
    )
    assert nx.bipartite.maximal_extendability(G) == 5


def test_k_is_6():
    G = nx.Graph(
        [
            (9, 1),
            (9, 2),
            (9, 3),
            (9, 4),
            (9, 5),
            (9, 6),
            (9, 7),
            (10, 1),
            (10, 2),
            (10, 3),
            (10, 4),
            (10, 5),
            (10, 6),
            (10, 8),
            (11, 1),
            (11, 2),
            (11, 3),
            (11, 4),
            (11, 5),
            (11, 7),
            (11, 8),
            (12, 1),
            (12, 2),
            (12, 3),
            (12, 4),
            (12, 6),
            (12, 7),
            (12, 8),
            (13, 1),
            (13, 2),
            (13, 3),
            (13, 5),
            (13, 6),
            (13, 7),
            (13, 8),
            (14, 1),
            (14, 2),
            (14, 4),
            (14, 5),
            (14, 6),
            (14, 7),
            (14, 8),
            (15, 1),
            (15, 3),
            (15, 4),
            (15, 5),
            (15, 6),
            (15, 7),
            (15, 8),
            (16, 2),
            (16, 3),
            (16, 4),
            (16, 5),
            (16, 6),
            (16, 7),
            (16, 8),
        ]
    )
    assert nx.bipartite.maximal_extendability(G) == 6


def test_k_is_7():
    G = nx.Graph(
        [
            (1, 11),
            (1, 12),
            (1, 13),
            (1, 14),
            (1, 15),
            (1, 16),
            (1, 17),
            (1, 18),
            (2, 11),
            (2, 12),
            (2, 13),
            (2, 14),
            (2, 15),
            (2, 16),
            (2, 17),
            (2, 19),
            (3, 11),
            (3, 12),
            (3, 13),
            (3, 14),
            (3, 15),
            (3, 16),
            (3, 17),
            (3, 20),
            (4, 11),
            (4, 12),
            (4, 13),
            (4, 14),
            (4, 15),
            (4, 16),
            (4, 17),
            (4, 18),
            (4, 19),
            (4, 20),
            (5, 11),
            (5, 12),
            (5, 13),
            (5, 14),
            (5, 15),
            (5, 16),
            (5, 17),
            (5, 18),
            (5, 19),
            (5, 20),
            (6, 11),
            (6, 12),
            (6, 13),
            (6, 14),
            (6, 15),
            (6, 16),
            (6, 17),
            (6, 18),
            (6, 19),
            (6, 20),
            (7, 11),
            (7, 12),
            (7, 13),
            (7, 14),
            (7, 15),
            (7, 16),
            (7, 17),
            (7, 18),
            (7, 19),
            (7, 20),
            (8, 11),
            (8, 12),
            (8, 13),
            (8, 14),
            (8, 15),
            (8, 16),
            (8, 17),
            (8, 18),
            (8, 19),
            (8, 20),
            (9, 11),
            (9, 12),
            (9, 13),
            (9, 14),
            (9, 15),
            (9, 16),
            (9, 17),
            (9, 18),
            (9, 19),
            (9, 20),
            (10, 11),
            (10, 12),
            (10, 13),
            (10, 14),
            (10, 15),
            (10, 16),
            (10, 17),
            (10, 18),
            (10, 19),
            (10, 20),
        ]
    )
    assert nx.bipartite.maximal_extendability(G) == 7
