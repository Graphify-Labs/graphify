import os

import pytest

import networkx as nx
from networkx.utils import edges_equal


def test_union_attributes():
    g = nx.Graph()
    g.add_node(0, x=4)
    g.add_node(1, x=5)
    g.add_edge(0, 1, size=5)
    g.graph["name"] = "g"

    h = g.copy()
    h.graph["name"] = "h"
    h.graph["attr"] = "attr"
    h.nodes[0]["x"] = 7

    gh = nx.union(g, h, rename=("g", "h"))
    assert set(gh.nodes()) == {"h0", "h1", "g0", "g1"}
    for n in gh:
        graph, node = n
        assert gh.nodes[n] == eval(graph).nodes[int(node)]

    assert gh.graph["attr"] == "attr"
    assert gh.graph["name"] == "h"  # h graph attributes take precedent


def test_intersection():
    G = nx.Graph()
    H = nx.Graph()
    G.add_nodes_from([1, 2, 3, 4])
    G.add_edge(1, 2)
    G.add_edge(2, 3)
    H.add_nodes_from([1, 2, 3, 4])
    H.add_edge(2, 3)
    H.add_edge(3, 4)
    I = nx.intersection(G, H)
    assert set(I.nodes()) == {1, 2, 3, 4}
    assert sorted(I.edges()) == [(2, 3)]


def test_intersection_node_sets_different():
    G = nx.Graph()
    H = nx.Graph()
    G.add_nodes_from([1, 2, 3, 4, 7])
    G.add_edge(1, 2)
    G.add_edge(2, 3)
    H.add_nodes_from([1, 2, 3, 4, 5, 6])
    H.add_edge(2, 3)
    H.add_edge(3, 4)
    H.add_edge(5, 6)
    I = nx.intersection(G, H)
    assert set(I.nodes()) == {1, 2, 3, 4}
    assert sorted(I.edges()) == [(2, 3)]


def test_intersection_attributes():
    g = nx.Graph()
    g.add_node(0, x=4)
    g.add_node(1, x=5)
    g.add_edge(0, 1, size=5)
    g.graph["name"] = "g"

    h = g.copy()
    h.graph["name"] = "h"
    h.graph["attr"] = "attr"
    h.nodes[0]["x"] = 7
    gh = nx.intersection(g, h)

    assert set(gh.nodes()) == set(g.nodes())
    assert set(gh.nodes()) == set(h.nodes())
    assert sorted(gh.edges()) == sorted(g.edges())


def test_intersection_attributes_node_sets_different():
    g = nx.Graph()
    g.add_node(0, x=4)
    g.add_node(1, x=5)
    g.add_node(2, x=3)
    g.add_edge(0, 1, size=5)
    g.graph["name"] = "g"

    h = g.copy()
    h.graph["name"] = "h"
    h.graph["attr"] = "attr"
    h.nodes[0]["x"] = 7
    h.remove_node(2)

    gh = nx.intersection(g, h)
    assert set(gh.nodes()) == set(h.nodes())
    assert sorted(gh.edges()) == sorted(g.edges())


def test_intersection_multigraph_attributes():
    g = nx.MultiGraph()
    g.add_edge(0, 1, key=0)
    g.add_edge(0, 1, key=1)
    g.add_edge(0, 1, key=2)
    h = nx.MultiGraph()
    h.add_edge(0, 1, key=0)
    h.add_edge(0, 1, key=3)
    gh = nx.intersection(g, h)
    assert set(gh.nodes()) == set(g.nodes())
    assert set(gh.nodes()) == set(h.nodes())
    assert sorted(gh.edges()) == [(0, 1)]
    assert sorted(gh.edges(keys=True)) == [(0, 1, 0)]


def test_intersection_multigraph_attributes_node_set_different():
    g = nx.MultiGraph()
    g.add_edge(0, 1, key=0)
    g.add_edge(0, 1, key=1)
    g.add_edge(0, 1, key=2)
    g.add_edge(0, 2, key=2)
    g.add_edge(0, 2, key=1)
    h = nx.MultiGraph()
    h.add_edge(0, 1, key=0)
    h.add_edge(0, 1, key=3)
    gh = nx.intersection(g, h)
    assert set(gh.nodes()) == set(h.nodes())
    assert sorted(gh.edges()) == [(0, 1)]
    assert sorted(gh.edges(keys=True)) == [(0, 1, 0)]


def test_difference():
    G = nx.Graph()
    H = nx.Graph()
    G.add_nodes_from([1, 2, 3, 4])
    G.add_edge(1, 2)
    G.add_edge(2, 3)
    H.add_nodes_from([1, 2, 3, 4])
    H.add_edge(2, 3)
    H.add_edge(3, 4)
    D = nx.difference(G, H)
    assert set(D.nodes()) == {1, 2, 3, 4}
    assert sorted(D.edges()) == [(1, 2)]
    D = nx.difference(H, G)
    assert set(D.nodes()) == {1, 2, 3, 4}
    assert sorted(D.edges()) == [(3, 4)]
    D = nx.symmetric_difference(G, H)
    assert set(D.nodes()) == {1, 2, 3, 4}
    assert sorted(D.edges()) == [(1, 2), (3, 4)]


def test_difference2():
    G = nx.Graph()
    H = nx.Graph()
    G.add_nodes_from([1, 2, 3, 4])
    H.add_nodes_from([1, 2, 3, 4])
    G.add_edge(1, 2)
    H.add_edge(1, 2)
    G.add_edge(2, 3)
    D = nx.difference(G, H)
    assert set(D.nodes()) == {1, 2, 3, 4}
    assert sorted(D.edges()) == [(2, 3)]
    D = nx.difference(H, G)
    assert set(D.nodes()) == {1, 2, 3, 4}
    assert sorted(D.edges()) == []
    H.add_edge(3, 4)
    D = nx.difference(H, G)
    assert set(D.nodes()) == {1, 2, 3, 4}
    assert sorted(D.edges()) == [(3, 4)]


def test_difference_attributes():
    g = nx.Graph()
    g.add_node(0, x=4)
    g.add_node(1, x=5)
    g.add_edge(0, 1, size=5)
    g.graph["name"] = "g"

    h = g.copy()
    h.graph["name"] = "h"
    h.graph["attr"] = "attr"
    h.nodes[0]["x"] = 7

    gh = nx.difference(g, h)
    assert set(gh.nodes()) == set(g.nodes())
    assert set(gh.nodes()) == set(h.nodes())
    assert sorted(gh.edges()) == []
    # node and graph data should not be copied over
    assert gh.nodes.data() != g.nodes.data()
    assert gh.graph != g.graph


def test_difference_multigraph_attributes():
    g = nx.MultiGraph()
    g.add_edge(0, 1, key=0)
    g.add_edge(0, 1, key=1)
    g.add_edge(0, 1, key=2)
    h = nx.MultiGraph()
    h.add_edge(0, 1, key=0)
    h.add_edge(0, 1, key=3)
    gh = nx.difference(g, h)
    assert set(gh.nodes()) == set(g.nodes())
    assert set(gh.nodes()) == set(h.nodes())
    assert sorted(gh.edges()) == [(0, 1), (0, 1)]
    assert sorted(gh.edges(keys=True)) == [(0, 1, 1), (0, 1, 2)]


def test_difference_raise():
    G = nx.path_graph(4)
    H = nx.path_graph(3)
    pytest.raises(nx.NetworkXError, nx.difference, G, H)
    pytest.raises(nx.NetworkXError, nx.symmetric_difference, G, H)


def test_symmetric_difference_multigraph():
    g = nx.MultiGraph()
    g.add_edge(0, 1, key=0)
    g.add_edge(0, 1, key=1)
    g.add_edge(0, 1, key=2)
    h = nx.MultiGraph()
    h.add_edge(0, 1, key=0)
    h.add_edge(0, 1, key=3)
    gh = nx.symmetric_difference(g, h)
    assert set(gh.nodes()) == set(g.nodes())
    assert set(gh.nodes()) == set(h.nodes())
    assert sorted(gh.edges()) == 3 * [(0, 1)]
    assert sorted(sorted(e) for e in gh.edges(keys=True)) == [
        [0, 1, 1],
        [0, 1, 2],
        [0, 1, 3],
    ]


def test_union_and_compose():
    K3 = nx.complete_graph(3)
    P3 = nx.path_graph(3)

    G1 = nx.DiGraph()
    G1.add_edge("A", "B")
    G1.add_edge("A", "C")
    G1.add_edge("A", "D")
    G2 = nx.DiGraph()
    G2.add_edge("1", "2")
    G2.add_edge("1", "3")
    G2.add_edge("1", "4")

    G = nx.union(G1, G2)
    H = nx.compose(G1, G2)
    assert edges_equal(G.edges(), H.edges())
    assert not G.has_edge("A", 1)
    pytest.raises(nx.NetworkXError, nx.union, K3, P3)
    H1 = nx.union(H, G1, rename=("H", "G1"))
    assert sorted(H1.nodes()) == [
        "G1A",
        "G1B",
        "G1C",
        "G1D",
        "H1",
        "H2",
        "H3",
        "H4",
        "HA",
        "HB",
        "HC",
        "HD",
    ]

    H2 = nx.union(H, G2, rename=("H", ""))
    assert sorted(H2.nodes()) == [
        "1",
        "2",
        "3",
        "4",
        "H1",
        "H2",
        "H3",
        "H4",
        "HA",
        "HB",
        "HC",
        "HD",
    ]

    assert not H1.has_edge("NB", "NA")

    G = nx.compose(G, G)
    assert edges_equal(G.edges(), H.edges())

    G2 = nx.union(G2, G2, rename=("", "copy"))
    assert sorted(G2.nodes()) == [
        "1",
        "2",
        "3",
        "4",
        "copy1",
        "copy2",
        "copy3",
        "copy4",
    ]

    assert sorted(G2.neighbors("copy4")) == []
    assert sorted(G2.neighbors("copy1")) == ["copy2", "copy3", "copy4"]
    assert len(G) == 8
    assert nx.number_of_edges(G) == 6

    E = nx.disjoint_union(G, G)
    assert len(E) == 16
    assert nx.number_of_edges(E) == 12

    E = nx.disjoint_union(G1, G2)
    assert sorted(E.nodes()) == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]

    G = nx.Graph()
    H = nx.Graph()
    G.add_nodes_from([(1, {"a1": 1})])
    H.add_nodes_from([(1, {"b1": 1})])
    R = nx.compose(G, H)
    assert R.nodes == {1: {"a1": 1, "b1": 1}}


def test_union_multigraph():
    G = nx.MultiGraph()
    G.add_edge(1, 2, key=0)
    G.add_edge(1, 2, key=1)
    H = nx.MultiGraph()
    H.add_edge(3, 4, key=0)
    H.add_edge(3, 4, key=1)
    GH = nx.union(G, H)
    assert set(GH) == set(G) | set(H)
    assert set(GH.edges(keys=True)) == set(G.edges(keys=True)) | set(H.edges(keys=True))


def test_disjoint_union_multigraph():
    G = nx.MultiGraph()
    G.add_edge(0, 1, key=0)
    G.add_edge(0, 1, key=1)
    H = nx.MultiGraph()
    H.add_edge(2, 3, key=0)
    H.add_edge(2, 3, key=1)
    GH = nx.disjoint_union(G, H)
    assert set(GH) == set(G) | set(H)
    assert set(GH.edges(keys=True)) == set(G.edges(keys=True)) | set(H.edges(keys=True))


def test_compose_multigraph():
    G = nx.MultiGraph()
    G.add_edge(1, 2, key=0)
    G.add_edge(1, 2, key=1)
    H = nx.MultiGraph()
    H.add_edge(3, 4, key=0)
    H.add_edge(3, 4, key=1)
    GH = nx.compose(G, H)
    assert set(GH) == set(G) | set(H)
    assert set(GH.edges(keys=True)) == set(G.edges(keys=True)) | set(H.edges(keys=True))
    H.add_edge(1, 2, key=2)
    GH = nx.compose(G, H)
    assert set(GH) == set(G) | set(H)
    assert set(GH.edges(keys=True)) == set(G.edges(keys=True)) | set(H.edges(keys=True))


def test_full_join_graph():
    # Simple Graphs
    G = nx.Graph()
    G.add_node(0)
    G.add_edge(1, 2)
    H = nx.Graph()
    H.add_edge(3, 4)

    U = nx.full_join(G, H)
    assert set(U) == set(G) | set(H)
    assert len(U) == len(G) + len(H)
    assert len(U.edges()) == len(G.edges()) + len(H.edges()) + len(G) * len(H)

    # Rename
    U = nx.full_join(G, H, rename=("g", "h"))
    assert set(U) == {"g0", "g1", "g2", "h3", "h4"}
    assert len(U) == len(G) + len(H)
    assert len(U.edges()) == len(G.edges()) + len(H.edges()) + len(G) * len(H)

    # Rename graphs with string-like nodes
    G = nx.Graph()
    G.add_node("a")
    G.add_edge("b", "c")
    H = nx.Graph()
    H.add_edge("d", "e")

    U = nx.full_join(G, H, rename=("g", "h"))
    assert set(U) == {"ga", "gb", "gc", "hd", "he"}
    assert len(U) == len(G) + len(H)
    assert len(U.edges()) == len(G.edges()) + len(H.edges()) + len(G) * len(H)

    # DiGraphs
    G = nx.DiGraph()
    G.add_node(0)
    G.add_edge(1, 2)
    H = nx.DiGraph()
    H.add_edge(3, 4)

    U = nx.full_join(G, H)
    assert set(U) == set(G) | set(H)
    assert len(U) == len(G) + len(H)
    assert len(U.edges()) == len(G.edges()) + len(H.edges()) + len(G) * len(H) * 2

    # DiGraphs Rename
    U = nx.full_join(G, H, rename=("g", "h"))
    assert set(U) == {"g0", "g1", "g2", "h3", "h4"}
    assert len(U) == len(G) + len(H)
    assert len(U.edges()) == len(G.edges()) + len(H.edges()) + len(G) * len(H) * 2


def test_full_join_multigraph():
    # MultiGraphs
    G = nx.MultiGraph()
    G.add_node(0)
    G.add_edge(1, 2)
    H = nx.MultiGraph()
    H.add_edge(3, 4)

    U = nx.full_join(G, H)
    assert set(U) == set(G) | set(H)
    assert len(U) == len(G) + len(H)
    assert len(U.edges()) == len(G.edges()) + len(H.edges()) + len(G) * len(H)

    # MultiGraphs rename
    U = nx.full_join(G, H, rename=("g", "h"))
    assert set(U) == {"g0", "g1", "g2", "h3", "h4"}
    assert len(U) == len(G) + len(H)
    assert len(U.edges()) == len(G.edges()) + len(H.edges()) + len(G) * len(H)

    # MultiDiGraphs
    G = nx.MultiDiGraph()
    G.add_node(0)
    G.add_edge(1, 2)
    H = nx.MultiDiGraph()
    H.add_edge(3, 4)

    U = nx.full_join(G, H)
    assert set(U) == set(G) | set(H)
    assert len(U) == len(G) + len(H)
    assert len(U.edges()) == len(G.edges()) + len(H.edges()) + len(G) * len(H) * 2

    # MultiDiGraphs rename
    U = nx.full_join(G, H, rename=("g", "h"))
    assert set(U) == {"g0", "g1", "g2", "h3", "h4"}
    assert len(U) == len(G) + len(H)
    assert len(U.edges()) == len(G.edges()) + len(H.edges()) + len(G) * len(H) * 2


def test_mixed_type_union():
    G = nx.Graph()
    H = nx.MultiGraph()
    pytest.raises(nx.NetworkXError, nx.union, G, H)
    pytest.raises(nx.NetworkXError, nx.disjoint_union, G, H)
    pytest.raises(nx.NetworkXError, nx.intersection, G, H)
    pytest.raises(nx.NetworkXError, nx.difference, G, H)
    pytest.raises(nx.NetworkXError, nx.symmetric_difference, G, H)
    pytest.raises(nx.NetworkXError, nx.compose, G, H)
