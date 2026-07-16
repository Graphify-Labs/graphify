import pytest

import networkx as nx


def test_richclub():
    G = nx.Graph([(0, 1), (0, 2), (1, 2), (1, 3), (1, 4), (4, 5)])
    rc = nx.richclub.rich_club_coefficient(G, normalized=False)
    assert rc == {0: 12.0 / 30, 1: 8.0 / 12}

    # test single value
    rc0 = nx.richclub.rich_club_coefficient(G, normalized=False)[0]
    assert rc0 == 12.0 / 30.0


def test_richclub_seed():
    G = nx.Graph([(0, 1), (0, 2), (1, 2), (1, 3), (1, 4), (4, 5)])
    rcNorm = nx.richclub.rich_club_coefficient(G, Q=2, seed=1)
    assert rcNorm == {0: 1.0, 1: 1.0}


def test_richclub_normalized():
    G = nx.Graph([(0, 1), (0, 2), (1, 2), (1, 3), (1, 4), (4, 5)])
    rcNorm = nx.richclub.rich_club_coefficient(G, Q=2, seed=42)
    assert rcNorm == {0: 1.0, 1: 1.0}


def test_richclub2():
    T = nx.balanced_tree(2, 10)
    rc = nx.richclub.rich_club_coefficient(T, normalized=False)
    assert rc == {
        0: 4092 / (2047 * 2046.0),
        1: (2044.0 / (1023 * 1022)),
        2: (2040.0 / (1022 * 1021)),
    }


def test_richclub3():
    # tests edgecase
    G = nx.karate_club_graph()
    rc = nx.rich_club_coefficient(G, normalized=False)
    assert rc == {
        0: 156.0 / 1122,
        1: 154.0 / 1056,
        2: 110.0 / 462,
        3: 78.0 / 240,
        4: 44.0 / 90,
        5: 22.0 / 42,
        6: 10.0 / 20,
        7: 10.0 / 20,
        8: 10.0 / 20,
        9: 6.0 / 12,
        10: 2.0 / 6,
        11: 2.0 / 6,
        12: 0.0,
        13: 0.0,
        14: 0.0,
        15: 0.0,
    }


def test_richclub4():
    G = nx.Graph()
    G.add_edges_from(
        [(0, 1), (0, 2), (0, 3), (0, 4), (4, 5), (5, 9), (6, 9), (7, 9), (8, 9)]
    )
    rc = nx.rich_club_coefficient(G, normalized=False)
    assert rc == {0: 18 / 90.0, 1: 6 / 12.0, 2: 0.0, 3: 0.0}


def test_richclub_exception():
    with pytest.raises(nx.NetworkXNotImplemented):
        G = nx.DiGraph()
        nx.rich_club_coefficient(G)


def test_rich_club_exception2():
    with pytest.raises(nx.NetworkXNotImplemented):
        G = nx.MultiGraph()
        nx.rich_club_coefficient(G)


def test_rich_club_selfloop():
    G = nx.Graph()  # or DiGraph, MultiGraph, MultiDiGraph, etc
    G.add_edge(1, 1)  # self loop
    G.add_edge(1, 2)
    with pytest.raises(
        Exception,
        match="rich_club_coefficient is not implemented for " "graphs with self loops.",
    ):
        nx.rich_club_coefficient(G)


def test_rich_club_leq_3_nodes_unnormalized():
    # edgeless graphs upto 3 nodes
    G = nx.Graph()
    rc = nx.rich_club_coefficient(G, normalized=False)
    assert rc == {}

    for i in range(3):
        G.add_node(i)
        rc = nx.rich_club_coefficient(G, normalized=False)
        assert rc == {}

    # 2 nodes, single edge
    G = nx.Graph()
    G.add_edge(0, 1)
    rc = nx.rich_club_coefficient(G, normalized=False)
    assert rc == {0: 1}

    # 3 nodes, single edge
    G = nx.Graph()
    G.add_nodes_from([0, 1, 2])
    G.add_edge(0, 1)
    rc = nx.rich_club_coefficient(G, normalized=False)
    assert rc == {0: 1}

    # 3 nodes, 2 edges
    G.add_edge(1, 2)
    rc = nx.rich_club_coefficient(G, normalized=False)
    assert rc == {0: 2 / 3}

    # 3 nodes, 3 edges
    G.add_edge(0, 2)
    rc = nx.rich_club_coefficient(G, normalized=False)
    assert rc == {0: 1, 1: 1}


def test_rich_club_leq_3_nodes_normalized():
    G = nx.Graph()
    with pytest.raises(
        nx.exception.NetworkXError,
        match="Graph has fewer than four nodes",
    ):
        rc = nx.rich_club_coefficient(G, normalized=True)

    for i in range(3):
        G.add_node(i)
        with pytest.raises(
            nx.exception.NetworkXError,
            match="Graph has fewer than four nodes",
        ):
            rc = nx.rich_club_coefficient(G, normalized=True)


# def test_richclub2_normalized():
#    T = nx.balanced_tree(2,10)
#    rcNorm = nx.richclub.rich_club_coefficient(T,Q=2)
#    assert_true(rcNorm[0] ==1.0 and rcNorm[1] < 0.9 and rcNorm[2] < 0.9)
