import pytest

import networkx as nx


def test_modularity_increase():
    G = nx.LFR_benchmark_graph(
        250, 3, 1.5, 0.009, average_degree=5, min_community=20, seed=10
    )
    partition = [{u} for u in G.nodes()]
    mod = nx.community.modularity(G, partition)
    partition = nx.community.louvain_communities(G)

    assert nx.community.modularity(G, partition) > mod


def test_valid_partition():
    G = nx.LFR_benchmark_graph(
        250, 3, 1.5, 0.009, average_degree=5, min_community=20, seed=10
    )
    H = G.to_directed()
    partition = nx.community.louvain_communities(G)
    partition2 = nx.community.louvain_communities(H)

    assert nx.community.is_partition(G, partition)
    assert nx.community.is_partition(H, partition2)


def test_karate_club_partition():
    G = nx.karate_club_graph()
    part = [
        {0, 1, 2, 3, 7, 9, 11, 12, 13, 17, 19, 21},
        {16, 4, 5, 6, 10},
        {23, 25, 27, 28, 24, 31},
        {32, 33, 8, 14, 15, 18, 20, 22, 26, 29, 30},
    ]
    partition = nx.community.louvain_communities(G, seed=2, weight=None)

    assert part == partition


def test_partition_iterator():
    G = nx.path_graph(15)
    parts_iter = nx.community.louvain_partitions(G, seed=42)
    first_part = next(parts_iter)
    first_copy = [s.copy() for s in first_part]

    # gh-5901 reports sets changing after next partition is yielded
    assert first_copy[0] == first_part[0]
    second_part = next(parts_iter)
    assert first_copy[0] == first_part[0]


def test_undirected_selfloops():
    G = nx.karate_club_graph()
    expected_partition = nx.community.louvain_communities(G, seed=2, weight=None)
    part = [
        {0, 1, 2, 3, 7, 9, 11, 12, 13, 17, 19, 21},
        {16, 4, 5, 6, 10},
        {23, 25, 27, 28, 24, 31},
        {32, 33, 8, 14, 15, 18, 20, 22, 26, 29, 30},
    ]
    assert expected_partition == part

    G.add_weighted_edges_from([(i, i, i * 1000) for i in range(9)])
    # large self-loop weight impacts partition
    partition = nx.community.louvain_communities(G, seed=2, weight="weight")
    assert part != partition

    # small self-loop weights aren't enough to impact partition in this graph
    partition = nx.community.louvain_communities(G, seed=2, weight=None)
    assert part == partition


def test_directed_selfloops():
    G = nx.DiGraph()
    G.add_nodes_from(range(11))
    G_edges = [
        (0, 2),
        (0, 1),
        (1, 0),
        (2, 1),
        (2, 0),
        (3, 4),
        (4, 3),
        (7, 8),
        (8, 7),
        (9, 10),
        (10, 9),
    ]
    G.add_edges_from(G_edges)
    G_expected_partition = nx.community.louvain_communities(G, seed=123, weight=None)

    G.add_weighted_edges_from([(i, i, i * 1000) for i in range(3)])
    # large self-loop weight impacts partition
    G_partition = nx.community.louvain_communities(G, seed=123, weight="weight")
    assert G_partition != G_expected_partition

    # small self-loop weights aren't enough to impact partition in this graph
    G_partition = nx.community.louvain_communities(G, seed=123, weight=None)
    assert G_partition == G_expected_partition


def test_directed_partition():
    """
    Test 2 cases that were looping infinitely
    from issues #5175 and #5704
    """
    G = nx.DiGraph()
    H = nx.DiGraph()
    G.add_nodes_from(range(10))
    H.add_nodes_from([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
    G_edges = [
        (0, 2),
        (0, 1),
        (1, 0),
        (2, 1),
        (2, 0),
        (3, 4),
        (4, 3),
        (7, 8),
        (8, 7),
        (9, 10),
        (10, 9),
    ]
    H_edges = [
        (1, 2),
        (1, 6),
        (1, 9),
        (2, 3),
        (2, 4),
        (2, 5),
        (3, 4),
        (4, 3),
        (4, 5),
        (5, 4),
        (6, 7),
        (6, 8),
        (9, 10),
        (9, 11),
        (10, 11),
        (11, 10),
    ]
    G.add_edges_from(G_edges)
    H.add_edges_from(H_edges)

    G_expected_partition = [{0, 1, 2}, {3, 4}, {5}, {6}, {8, 7}, {9, 10}]
    G_partition = nx.community.louvain_communities(G, seed=123, weight=None)

    H_expected_partition = [{2, 3, 4, 5}, {8, 1, 6, 7}, {9, 10, 11}]
    H_partition = nx.community.louvain_communities(H, seed=123, weight=None)

    assert G_partition == G_expected_partition
    assert H_partition == H_expected_partition


def test_none_weight_param():
    G = nx.karate_club_graph()
    nx.set_edge_attributes(
        G, {edge: i * i for i, edge in enumerate(G.edges)}, name="foo"
    )

    part = [
        {0, 1, 2, 3, 7, 9, 11, 12, 13, 17, 19, 21},
        {16, 4, 5, 6, 10},
        {23, 25, 27, 28, 24, 31},
        {32, 33, 8, 14, 15, 18, 20, 22, 26, 29, 30},
    ]
    partition1 = nx.community.louvain_communities(G, weight=None, seed=2)
    partition2 = nx.community.louvain_communities(G, weight="foo", seed=2)
    partition3 = nx.community.louvain_communities(G, weight="weight", seed=2)

    assert part == partition1
    assert part != partition2
    assert part != partition3
    assert partition2 != partition3


def test_quality():
    G = nx.LFR_benchmark_graph(
        250, 3, 1.5, 0.009, average_degree=5, min_community=20, seed=10
    )
    H = nx.gn_graph(200, seed=1234)
    I = nx.MultiGraph(G)
    J = nx.MultiDiGraph(H)

    partition = nx.community.louvain_communities(G)
    partition2 = nx.community.louvain_communities(H)
    partition3 = nx.community.louvain_communities(I)
    partition4 = nx.community.louvain_communities(J)

    quality = nx.community.partition_quality(G, partition)[0]
    quality2 = nx.community.partition_quality(H, partition2)[0]
    quality3 = nx.community.partition_quality(I, partition3)[0]
    quality4 = nx.community.partition_quality(J, partition4)[0]

    assert quality >= 0.65
    assert quality2 >= 0.65
    assert quality3 >= 0.65
    assert quality4 >= 0.65


def test_multigraph():
    G = nx.karate_club_graph()
    H = nx.MultiGraph(G)
    G.add_edge(0, 1, weight=10)
    H.add_edge(0, 1, weight=9)
    G.add_edge(0, 9, foo=20)
    H.add_edge(0, 9, foo=20)

    partition1 = nx.community.louvain_communities(G, seed=1234)
    partition2 = nx.community.louvain_communities(H, seed=1234)
    partition3 = nx.community.louvain_communities(H, weight="foo", seed=1234)

    assert partition1 == partition2 != partition3


def test_resolution():
    G = nx.LFR_benchmark_graph(
        250, 3, 1.5, 0.009, average_degree=5, min_community=20, seed=10
    )

    partition1 = nx.community.louvain_communities(G, resolution=0.5, seed=12)
    partition2 = nx.community.louvain_communities(G, seed=12)
    partition3 = nx.community.louvain_communities(G, resolution=2, seed=12)

    assert len(partition1) <= len(partition2) <= len(partition3)


def test_threshold():
    G = nx.LFR_benchmark_graph(
        250, 3, 1.5, 0.009, average_degree=5, min_community=20, seed=10
    )
    partition1 = nx.community.louvain_communities(G, threshold=0.3, seed=2)
    partition2 = nx.community.louvain_communities(G, seed=2)
    mod1 = nx.community.modularity(G, partition1)
    mod2 = nx.community.modularity(G, partition2)

    assert mod1 <= mod2


def test_empty_graph():
    G = nx.Graph()
    G.add_nodes_from(range(5))
    expected = [{0}, {1}, {2}, {3}, {4}]
    assert nx.community.louvain_communities(G) == expected


def test_max_level():
    G = nx.LFR_benchmark_graph(
        250, 3, 1.5, 0.009, average_degree=5, min_community=20, seed=10
    )
    parts_iter = nx.community.louvain_partitions(G, seed=42)
    for max_level, expected in enumerate(parts_iter, 1):
        partition = nx.community.louvain_communities(G, max_level=max_level, seed=42)
        assert partition == expected
    assert max_level > 1  # Ensure we are actually testing max_level
    # max_level is an upper limit; it's okay if we stop before it's hit.
    partition = nx.community.louvain_communities(G, max_level=max_level + 1, seed=42)
    assert partition == expected
    with pytest.raises(
        ValueError, match="max_level argument must be a positive integer"
    ):
        nx.community.louvain_communities(G, max_level=0)
