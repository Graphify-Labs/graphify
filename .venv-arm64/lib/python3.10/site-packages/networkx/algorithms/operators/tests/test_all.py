import pytest

import networkx as nx
from networkx.utils import edges_equal


def test_union_all_attributes():
    g = nx.Graph()
    g.add_node(0, x=4)
    g.add_node(1, x=5)
    g.add_edge(0, 1, size=5)
    g.graph["name"] = "g"

    h = g.copy()
    h.graph["name"] = "h"
    h.graph["attr"] = "attr"
    h.nodes[0]["x"] = 7

    j = g.copy()
    j.graph["name"] = "j"
    j.graph["attr"] = "attr"
    j.nodes[0]["x"] = 7

    ghj = nx.union_all([g, h, j], rename=("g", "h", "j"))
    assert set(ghj.nodes()) == {"h0", "h1", "g0", "g1", "j0", "j1"}
    for n in ghj:
        graph, node = n
        assert ghj.nodes[n] == eval(graph).nodes[int(node)]

    assert ghj.graph["attr"] == "attr"
    assert ghj.graph["name"] == "j"  # j graph attributes take precedent


def test_intersection_all():
    G = nx.Graph()
    H = nx.Graph()
    R = nx.Graph(awesome=True)
    G.add_nodes_from([1, 2, 3, 4])
    G.add_edge(1, 2)
    G.add_edge(2, 3)
    H.add_nodes_from([1, 2, 3, 4])
    H.add_edge(2, 3)
    H.add_edge(3, 4)
    R.add_nodes_from([1, 2, 3, 4])
    R.add_edge(2, 3)
    R.add_edge(4, 1)
    I = nx.intersection_all([G, H, R])
    assert set(I.nodes()) == {1, 2, 3, 4}
    assert sorted(I.edges()) == [(2, 3)]
    assert I.graph == {}


def test_intersection_all_different_node_sets():
    G = nx.Graph()
    H = nx.Graph()
    R = nx.Graph()
    G.add_nodes_from([1, 2, 3, 4, 6, 7])
    G.add_edge(1, 2)
    G.add_edge(2, 3)
    G.add_edge(6, 7)
    H.add_nodes_from([1, 2, 3, 4])
    H.add_edge(2, 3)
    H.add_edge(3, 4)
    R.add_nodes_from([1, 2, 3, 4, 8, 9])
    R.add_edge(2, 3)
    R.add_edge(4, 1)
    R.add_edge(8, 9)
    I = nx.intersection_all([G, H, R])
    assert set(I.nodes()) == {1, 2, 3, 4}
    assert sorted(I.edges()) == [(2, 3)]


def test_intersection_all_attributes():
    g = nx.Graph()
    g.add_node(0, x=4)
    g.add_node(1, x=5)
    g.add_edge(0, 1, size=5)
    g.graph["name"] = "g"

    h = g.copy()
    h.graph["name"] = "h"
    h.graph["attr"] = "attr"
    h.nodes[0]["x"] = 7

    gh = nx.intersection_all([g, h])
    assert set(gh.nodes()) == set(g.nodes())
    assert set(gh.nodes()) == set(h.nodes())
    assert sorted(gh.edges()) == sorted(g.edges())


def test_intersection_all_attributes_different_node_sets():
    g = nx.Graph()
    g.add_node(0, x=4)
    g.add_node(1, x=5)
    g.add_edge(0, 1, size=5)
    g.graph["name"] = "g"

    h = g.copy()
    g.add_node(2)
    h.graph["name"] = "h"
    h.graph["attr"] = "attr"
    h.nodes[0]["x"] = 7

    gh = nx.intersection_all([g, h])
    assert set(gh.nodes()) == set(h.nodes())
    assert sorted(gh.edges()) == sorted(g.edges())


def test_intersection_all_multigraph_attributes():
    g = nx.MultiGraph()
    g.add_edge(0, 1, key=0)
    g.add_edge(0, 1, key=1)
    g.add_edge(0, 1, key=2)
    h = nx.MultiGraph()
    h.add_edge(0, 1, key=0)
    h.add_edge(0, 1, key=3)
    gh = nx.intersection_all([g, h])
    assert set(gh.nodes()) == set(g.nodes())
    assert set(gh.nodes()) == set(h.nodes())
    assert sorted(gh.edges()) == [(0, 1)]
    assert sorted(gh.edges(keys=True)) == [(0, 1, 0)]


def test_intersection_all_multigraph_attributes_different_node_sets():
    g = nx.MultiGraph()
    g.add_edge(0, 1, key=0)
    g.add_edge(0, 1, key=1)
    g.add_edge(0, 1, key=2)
    g.add_edge(1, 2, key=1)
    g.add_edge(1, 2, key=2)
    h = nx.MultiGraph()
    h.add_edge(0, 1, key=0)
    h.add_edge(0, 1, key=2)
    h.add_edge(0, 1, key=3)
    gh = nx.intersection_all([g, h])
    assert set(gh.nodes()) == set(h.nodes())
    assert sorted(gh.edges()) == [(0, 1), (0, 1)]
    assert sorted(gh.edges(keys=True)) == [(0, 1, 0), (0, 1, 2)]


def test_intersection_all_digraph():
    g = nx.DiGraph()
    g.add_edges_from([(1, 2), (2, 3)])
    h = nx.DiGraph()
    h.add_edges_from([(2, 1), (2, 3)])
    gh = nx.intersection_all([g, h])
    assert sorted(gh.edges()) == [(2, 3)]


def test_union_all_and_compose_all():
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

    G = nx.union_all([G1, G2])
    H = nx.compose_all([G1, G2])
    assert edges_equal(G.edges(), H.edges())
    assert not G.has_edge("A", "1")
    pytest.raises(nx.NetworkXError, nx.union, K3, P3)
    H1 = nx.union_all([H, G1], rename=("H", "G1"))
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

    H2 = nx.union_all([H, G2], rename=("H", ""))
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

    G = nx.compose_all([G, G])
    assert edges_equal(G.edges(), H.edges())

    G2 = nx.union_all([G2, G2], rename=("", "copy"))
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

    E = nx.disjoint_union_all([G, G])
    assert len(E) == 16
    assert nx.number_of_edges(E) == 12

    E = nx.disjoint_union_all([G1, G2])
    assert sorted(E.nodes()) == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]

    G1 = nx.DiGraph()
    G1.add_edge("A", "B")
    G2 = nx.DiGraph()
    G2.add_edge(1, 2)
    G3 = nx.DiGraph()
    G3.add_edge(11, 22)
    G4 = nx.union_all([G1, G2, G3], rename=("G1", "G2", "G3"))
    assert sorted(G4.nodes()) == ["G1A", "G1B", "G21", "G22", "G311", "G322"]


def test_union_all_multigraph():
    G = nx.MultiGraph()
    G.add_edge(1, 2, key=0)
    G.add_edge(1, 2, key=1)
    H = nx.MultiGraph()
    H.add_edge(3, 4, key=0)
    H.add_edge(3, 4, key=1)
    GH = nx.union_all([G, H])
    assert set(GH) == set(G) | set(H)
    assert set(GH.edges(keys=True)) == set(G.edges(keys=True)) | set(H.edges(keys=True))


def test_input_output():
    l = [nx.Graph([(1, 2)]), nx.Graph([(3, 4)], awesome=True)]
    U = nx.disjoint_union_all(l)
    assert len(l) == 2
    assert U.graph["awesome"]
    C = nx.compose_all(l)
    assert len(l) == 2
    l = [nx.Graph([(1, 2)]), nx.Graph([(1, 2)])]
    R = nx.intersection_all(l)
    assert len(l) == 2


def test_mixed_type_union():
    with pytest.raises(nx.NetworkXError):
        G = nx.Graph()
        H = nx.MultiGraph()
        I = nx.Graph()
        U = nx.union_all([G, H, I])
    with pytest.raises(nx.NetworkXError):
        X = nx.Graph()
        Y = nx.DiGraph()
        XY = nx.union_all([X, Y])


def test_mixed_type_disjoint_union():
    with pytest.raises(nx.NetworkXError):
        G = nx.Graph()
        H = nx.MultiGraph()
        I = nx.Graph()
        U = nx.disjoint_union_all([G, H, I])
    with pytest.raises(nx.NetworkXError):
        X = nx.Graph()
        Y = nx.DiGraph()
        XY = nx.disjoint_union_all([X, Y])


def test_mixed_type_intersection():
    with pytest.raises(nx.NetworkXError):
        G = nx.Graph()
        H = nx.MultiGraph()
        I = nx.Graph()
        U = nx.intersection_all([G, H, I])
    with pytest.raises(nx.NetworkXError):
        X = nx.Graph()
        Y = nx.DiGraph()
        XY = nx.intersection_all([X, Y])


def test_mixed_type_compose():
    with pytest.raises(nx.NetworkXError):
        G = nx.Graph()
        H = nx.MultiGraph()
        I = nx.Graph()
        U = nx.compose_all([G, H, I])
    with pytest.raises(nx.NetworkXError):
        X = nx.Graph()
        Y = nx.DiGraph()
        XY = nx.compose_all([X, Y])


def test_empty_union():
    with pytest.raises(ValueError):
        nx.union_all([])


def test_empty_disjoint_union():
    with pytest.raises(ValueError):
        nx.disjoint_union_all([])


def test_empty_compose_all():
    with pytest.raises(ValueError):
        nx.compose_all([])


def test_empty_intersection_all():
    with pytest.raises(ValueError):
        nx.intersection_all([])
