import pytest

import networkx as nx
from networkx.algorithms.community import (
    greedy_modularity_communities,
    naive_greedy_modularity_communities,
)


@pytest.mark.parametrize(
    "func", (greedy_modularity_communities, naive_greedy_modularity_communities)
)
def test_modularity_communities(func):
    G = nx.karate_club_graph()
    john_a = frozenset(
        [8, 14, 15, 18, 20, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33]
    )
    mr_hi = frozenset([0, 4, 5, 6, 10, 11, 16, 19])
    overlap = frozenset([1, 2, 3, 7, 9, 12, 13, 17, 21])
    expected = {john_a, overlap, mr_hi}
    assert set(func(G, weight=None)) == expected


@pytest.mark.parametrize(
    "func", (greedy_modularity_communities, naive_greedy_modularity_communities)
)
def test_modularity_communities_categorical_labels(func):
    # Using other than 0-starting contiguous integers as node-labels.
    G = nx.Graph(
        [
            ("a", "b"),
            ("a", "c"),
            ("b", "c"),
            ("b", "d"),  # inter-community edge
            ("d", "e"),
            ("d", "f"),
            ("d", "g"),
            ("f", "g"),
            ("d", "e"),
            ("f", "e"),
        ]
    )
    expected = {frozenset({"f", "g", "e", "d"}), frozenset({"a", "b", "c"})}
    assert set(func(G)) == expected


def test_greedy_modularity_communities_components():
    # Test for gh-5530
    G = nx.Graph([(0, 1), (2, 3), (4, 5), (5, 6)])
    # usual case with 3 components
    assert greedy_modularity_communities(G) == [{4, 5, 6}, {0, 1}, {2, 3}]
    # best_n can make the algorithm continue even when modularity goes down
    assert greedy_modularity_communities(G, best_n=3) == [{4, 5, 6}, {0, 1}, {2, 3}]
    assert greedy_modularity_communities(G, best_n=2) == [{0, 1, 4, 5, 6}, {2, 3}]
    assert greedy_modularity_communities(G, best_n=1) == [{0, 1, 2, 3, 4, 5, 6}]


def test_greedy_modularity_communities_relabeled():
    # Test for gh-4966
    G = nx.balanced_tree(2, 2)
    mapping = {0: "a", 1: "b", 2: "c", 3: "d", 4: "e", 5: "f", 6: "g", 7: "h"}
    G = nx.relabel_nodes(G, mapping)
    expected = [frozenset({"e", "d", "a", "b"}), frozenset({"c", "f", "g"})]
    assert greedy_modularity_communities(G) == expected


def test_greedy_modularity_communities_directed():
    G = nx.DiGraph(
        [
            ("a", "b"),
            ("a", "c"),
            ("b", "c"),
            ("b", "d"),  # inter-community edge
            ("d", "e"),
            ("d", "f"),
            ("d", "g"),
            ("f", "g"),
            ("d", "e"),
            ("f", "e"),
        ]
    )
    expected = [frozenset({"f", "g", "e", "d"}), frozenset({"a", "b", "c"})]
    assert greedy_modularity_communities(G) == expected

    # with loops
    G = nx.DiGraph()
    G.add_edges_from(
        [(1, 1), (1, 2), (1, 3), (2, 3), (1, 4), (4, 4), (5, 5), (4, 5), (4, 6), (5, 6)]
    )
    expected = [frozenset({1, 2, 3}), frozenset({4, 5, 6})]
    assert greedy_modularity_communities(G) == expected


@pytest.mark.parametrize(
    "func", (greedy_modularity_communities, naive_greedy_modularity_communities)
)
def test_modularity_communities_weighted(func):
    G = nx.balanced_tree(2, 3)
    for a, b in G.edges:
        if ((a == 1) or (a == 2)) and (b != 0):
            G[a][b]["weight"] = 10.0
        else:
            G[a][b]["weight"] = 1.0

    expected = [{0, 1, 3, 4, 7, 8, 9, 10}, {2, 5, 6, 11, 12, 13, 14}]

    assert func(G, weight="weight") == expected
    assert func(G, weight="weight", resolution=0.9) == expected
    assert func(G, weight="weight", resolution=0.3) == expected
    assert func(G, weight="weight", resolution=1.1) != expected


def test_modularity_communities_floating_point():
    # check for floating point error when used as key in the mapped_queue dict.
    # Test for gh-4992 and gh-5000
    G = nx.Graph()
    G.add_weighted_edges_from(
        [(0, 1, 12), (1, 4, 71), (2, 3, 15), (2, 4, 10), (3, 6, 13)]
    )
    expected = [{0, 1, 4}, {2, 3, 6}]
    assert greedy_modularity_communities(G, weight="weight") == expected
    assert (
        greedy_modularity_communities(G, weight="weight", resolution=0.99) == expected
    )


def test_modularity_communities_directed_weighted():
    G = nx.DiGraph()
    G.add_weighted_edges_from(
        [
            (1, 2, 5),
            (1, 3, 3),
            (2, 3, 6),
            (2, 6, 1),
            (1, 4, 1),
            (4, 5, 3),
            (4, 6, 7),
            (5, 6, 2),
            (5, 7, 5),
            (5, 8, 4),
            (6, 8, 3),
        ]
    )
    expected = [frozenset({4, 5, 6, 7, 8}), frozenset({1, 2, 3})]
    assert greedy_modularity_communities(G, weight="weight") == expected

    # A large weight of the edge (2, 6) causes 6 to change group, even if it shares
    # only one connection with the new group and 3 with the old one.
    G[2][6]["weight"] = 20
    expected = [frozenset({1, 2, 3, 6}), frozenset({4, 5, 7, 8})]
    assert greedy_modularity_communities(G, weight="weight") == expected


def test_greedy_modularity_communities_multigraph():
    G = nx.MultiGraph()
    G.add_edges_from(
        [
            (1, 2),
            (1, 2),
            (1, 3),
            (2, 3),
            (1, 4),
            (2, 4),
            (4, 5),
            (5, 6),
            (5, 7),
            (5, 7),
            (6, 7),
            (7, 8),
            (5, 8),
        ]
    )
    expected = [frozenset({1, 2, 3, 4}), frozenset({5, 6, 7, 8})]
    assert greedy_modularity_communities(G) == expected

    # Converting (4, 5) into a multi-edge causes node 4 to change group.
    G.add_edge(4, 5)
    expected = [frozenset({4, 5, 6, 7, 8}), frozenset({1, 2, 3})]
    assert greedy_modularity_communities(G) == expected


def test_greedy_modularity_communities_multigraph_weighted():
    G = nx.MultiGraph()
    G.add_weighted_edges_from(
        [
            (1, 2, 5),
            (1, 2, 3),
            (1, 3, 6),
            (1, 3, 6),
            (2, 3, 4),
            (1, 4, 1),
            (1, 4, 1),
            (2, 4, 3),
            (2, 4, 3),
            (4, 5, 1),
            (5, 6, 3),
            (5, 6, 7),
            (5, 6, 4),
            (5, 7, 9),
            (5, 7, 9),
            (6, 7, 8),
            (7, 8, 2),
            (7, 8, 2),
            (5, 8, 6),
            (5, 8, 6),
        ]
    )
    expected = [frozenset({1, 2, 3, 4}), frozenset({5, 6, 7, 8})]
    assert greedy_modularity_communities(G, weight="weight") == expected

    # Adding multi-edge (4, 5, 16) causes node 4 to change group.
    G.add_edge(4, 5, weight=16)
    expected = [frozenset({4, 5, 6, 7, 8}), frozenset({1, 2, 3})]
    assert greedy_modularity_communities(G, weight="weight") == expected

    # Increasing the weight of edge (1, 4) causes node 4 to return to the former group.
    G[1][4][1]["weight"] = 3
    expected = [frozenset({1, 2, 3, 4}), frozenset({5, 6, 7, 8})]
    assert greedy_modularity_communities(G, weight="weight") == expected


def test_greed_modularity_communities_multidigraph():
    G = nx.MultiDiGraph()
    G.add_edges_from(
        [
            (1, 2),
            (1, 2),
            (3, 1),
            (2, 3),
            (2, 3),
            (3, 2),
            (1, 4),
            (2, 4),
            (4, 2),
            (4, 5),
            (5, 6),
            (5, 6),
            (6, 5),
            (5, 7),
            (6, 7),
            (7, 8),
            (5, 8),
            (8, 4),
        ]
    )
    expected = [frozenset({1, 2, 3, 4}), frozenset({5, 6, 7, 8})]
    assert greedy_modularity_communities(G, weight="weight") == expected


def test_greed_modularity_communities_multidigraph_weighted():
    G = nx.MultiDiGraph()
    G.add_weighted_edges_from(
        [
            (1, 2, 5),
            (1, 2, 3),
            (3, 1, 6),
            (1, 3, 6),
            (3, 2, 4),
            (1, 4, 2),
            (1, 4, 5),
            (2, 4, 3),
            (3, 2, 8),
            (4, 2, 3),
            (4, 3, 5),
            (4, 5, 2),
            (5, 6, 3),
            (5, 6, 7),
            (6, 5, 4),
            (5, 7, 9),
            (5, 7, 9),
            (7, 6, 8),
            (7, 8, 2),
            (8, 7, 2),
            (5, 8, 6),
            (5, 8, 6),
        ]
    )
    expected = [frozenset({1, 2, 3, 4}), frozenset({5, 6, 7, 8})]
    assert greedy_modularity_communities(G, weight="weight") == expected


def test_resolution_parameter_impact():
    G = nx.barbell_graph(5, 3)

    gamma = 1
    expected = [frozenset(range(5)), frozenset(range(8, 13)), frozenset(range(5, 8))]
    assert greedy_modularity_communities(G, resolution=gamma) == expected
    assert naive_greedy_modularity_communities(G, resolution=gamma) == expected

    gamma = 2.5
    expected = [{0, 1, 2, 3}, {9, 10, 11, 12}, {5, 6, 7}, {4}, {8}]
    assert greedy_modularity_communities(G, resolution=gamma) == expected
    assert naive_greedy_modularity_communities(G, resolution=gamma) == expected

    gamma = 0.3
    expected = [frozenset(range(8)), frozenset(range(8, 13))]
    assert greedy_modularity_communities(G, resolution=gamma) == expected
    assert naive_greedy_modularity_communities(G, resolution=gamma) == expected


def test_cutoff_parameter():
    G = nx.circular_ladder_graph(4)

    # No aggregation:
    expected = [{k} for k in range(8)]
    assert greedy_modularity_communities(G, cutoff=8) == expected

    # Aggregation to half order (number of nodes)
    expected = [{k, k + 1} for k in range(0, 8, 2)]
    assert greedy_modularity_communities(G, cutoff=4) == expected

    # Default aggregation case (here, 2 communities emerge)
    expected = [frozenset(range(4)), frozenset(range(4, 8))]
    assert greedy_modularity_communities(G, cutoff=1) == expected


def test_best_n():
    G = nx.barbell_graph(5, 3)

    # Same result as without enforcing cutoff:
    best_n = 3
    expected = [frozenset(range(5)), frozenset(range(8, 13)), frozenset(range(5, 8))]
    assert greedy_modularity_communities(G, best_n=best_n) == expected

    # One additional merging step:
    best_n = 2
    expected = [frozenset(range(8)), frozenset(range(8, 13))]
    assert greedy_modularity_communities(G, best_n=best_n) == expected

    # Two additional merging steps:
    best_n = 1
    expected = [frozenset(range(13))]
    assert greedy_modularity_communities(G, best_n=best_n) == expected


def test_greedy_modularity_communities_corner_cases():
    G = nx.empty_graph()
    assert nx.community.greedy_modularity_communities(G) == []
    G.add_nodes_from(range(3))
    assert nx.community.greedy_modularity_communities(G) == [{0}, {1}, {2}]
