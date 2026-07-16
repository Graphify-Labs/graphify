import pytest

import networkx as nx
from networkx.utils import edges_equal


def test_tensor_product_raises():
    with pytest.raises(nx.NetworkXError):
        P = nx.tensor_product(nx.DiGraph(), nx.Graph())


def test_tensor_product_null():
    null = nx.null_graph()
    empty10 = nx.empty_graph(10)
    K3 = nx.complete_graph(3)
    K10 = nx.complete_graph(10)
    P3 = nx.path_graph(3)
    P10 = nx.path_graph(10)
    # null graph
    G = nx.tensor_product(null, null)
    assert nx.is_isomorphic(G, null)
    # null_graph X anything = null_graph and v.v.
    G = nx.tensor_product(null, empty10)
    assert nx.is_isomorphic(G, null)
    G = nx.tensor_product(null, K3)
    assert nx.is_isomorphic(G, null)
    G = nx.tensor_product(null, K10)
    assert nx.is_isomorphic(G, null)
    G = nx.tensor_product(null, P3)
    assert nx.is_isomorphic(G, null)
    G = nx.tensor_product(null, P10)
    assert nx.is_isomorphic(G, null)
    G = nx.tensor_product(empty10, null)
    assert nx.is_isomorphic(G, null)
    G = nx.tensor_product(K3, null)
    assert nx.is_isomorphic(G, null)
    G = nx.tensor_product(K10, null)
    assert nx.is_isomorphic(G, null)
    G = nx.tensor_product(P3, null)
    assert nx.is_isomorphic(G, null)
    G = nx.tensor_product(P10, null)
    assert nx.is_isomorphic(G, null)


def test_tensor_product_size():
    P5 = nx.path_graph(5)
    K3 = nx.complete_graph(3)
    K5 = nx.complete_graph(5)

    G = nx.tensor_product(P5, K3)
    assert nx.number_of_nodes(G) == 5 * 3
    G = nx.tensor_product(K3, K5)
    assert nx.number_of_nodes(G) == 3 * 5


def test_tensor_product_combinations():
    # basic smoke test, more realistic tests would be useful
    P5 = nx.path_graph(5)
    K3 = nx.complete_graph(3)
    G = nx.tensor_product(P5, K3)
    assert nx.number_of_nodes(G) == 5 * 3
    G = nx.tensor_product(P5, nx.MultiGraph(K3))
    assert nx.number_of_nodes(G) == 5 * 3
    G = nx.tensor_product(nx.MultiGraph(P5), K3)
    assert nx.number_of_nodes(G) == 5 * 3
    G = nx.tensor_product(nx.MultiGraph(P5), nx.MultiGraph(K3))
    assert nx.number_of_nodes(G) == 5 * 3

    G = nx.tensor_product(nx.DiGraph(P5), nx.DiGraph(K3))
    assert nx.number_of_nodes(G) == 5 * 3


def test_tensor_product_classic_result():
    K2 = nx.complete_graph(2)
    G = nx.petersen_graph()
    G = nx.tensor_product(G, K2)
    assert nx.is_isomorphic(G, nx.desargues_graph())

    G = nx.cycle_graph(5)
    G = nx.tensor_product(G, K2)
    assert nx.is_isomorphic(G, nx.cycle_graph(10))

    G = nx.tetrahedral_graph()
    G = nx.tensor_product(G, K2)
    assert nx.is_isomorphic(G, nx.cubical_graph())


def test_tensor_product_random():
    G = nx.erdos_renyi_graph(10, 2 / 10.0)
    H = nx.erdos_renyi_graph(10, 2 / 10.0)
    GH = nx.tensor_product(G, H)

    for u_G, u_H in GH.nodes():
        for v_G, v_H in GH.nodes():
            if H.has_edge(u_H, v_H) and G.has_edge(u_G, v_G):
                assert GH.has_edge((u_G, u_H), (v_G, v_H))
            else:
                assert not GH.has_edge((u_G, u_H), (v_G, v_H))


def test_cartesian_product_multigraph():
    G = nx.MultiGraph()
    G.add_edge(1, 2, key=0)
    G.add_edge(1, 2, key=1)
    H = nx.MultiGraph()
    H.add_edge(3, 4, key=0)
    H.add_edge(3, 4, key=1)
    GH = nx.cartesian_product(G, H)
    assert set(GH) == {(1, 3), (2, 3), (2, 4), (1, 4)}
    assert {(frozenset([u, v]), k) for u, v, k in GH.edges(keys=True)} == {
        (frozenset([u, v]), k)
        for u, v, k in [
            ((1, 3), (2, 3), 0),
            ((1, 3), (2, 3), 1),
            ((1, 3), (1, 4), 0),
            ((1, 3), (1, 4), 1),
            ((2, 3), (2, 4), 0),
            ((2, 3), (2, 4), 1),
            ((2, 4), (1, 4), 0),
            ((2, 4), (1, 4), 1),
        ]
    }


def test_cartesian_product_raises():
    with pytest.raises(nx.NetworkXError):
        P = nx.cartesian_product(nx.DiGraph(), nx.Graph())


def test_cartesian_product_null():
    null = nx.null_graph()
    empty10 = nx.empty_graph(10)
    K3 = nx.complete_graph(3)
    K10 = nx.complete_graph(10)
    P3 = nx.path_graph(3)
    P10 = nx.path_graph(10)
    # null graph
    G = nx.cartesian_product(null, null)
    assert nx.is_isomorphic(G, null)
    # null_graph X anything = null_graph and v.v.
    G = nx.cartesian_product(null, empty10)
    assert nx.is_isomorphic(G, null)
    G = nx.cartesian_product(null, K3)
    assert nx.is_isomorphic(G, null)
    G = nx.cartesian_product(null, K10)
    assert nx.is_isomorphic(G, null)
    G = nx.cartesian_product(null, P3)
    assert nx.is_isomorphic(G, null)
    G = nx.cartesian_product(null, P10)
    assert nx.is_isomorphic(G, null)
    G = nx.cartesian_product(empty10, null)
    assert nx.is_isomorphic(G, null)
    G = nx.cartesian_product(K3, null)
    assert nx.is_isomorphic(G, null)
    G = nx.cartesian_product(K10, null)
    assert nx.is_isomorphic(G, null)
    G = nx.cartesian_product(P3, null)
    assert nx.is_isomorphic(G, null)
    G = nx.cartesian_product(P10, null)
    assert nx.is_isomorphic(G, null)


def test_cartesian_product_size():
    # order(GXH)=order(G)*order(H)
    K5 = nx.complete_graph(5)
    P5 = nx.path_graph(5)
    K3 = nx.complete_graph(3)
    G = nx.cartesian_product(P5, K3)
    assert nx.number_of_nodes(G) == 5 * 3
    assert nx.number_of_edges(G) == nx.number_of_edges(P5) * nx.number_of_nodes(
        K3
    ) + nx.number_of_edges(K3) * nx.number_of_nodes(P5)
    G = nx.cartesian_product(K3, K5)
    assert nx.number_of_nodes(G) == 3 * 5
    assert nx.number_of_edges(G) == nx.number_of_edges(K5) * nx.number_of_nodes(
        K3
    ) + nx.number_of_edges(K3) * nx.number_of_nodes(K5)


def test_cartesian_product_classic():
    # test some classic product graphs
    P2 = nx.path_graph(2)
    P3 = nx.path_graph(3)
    # cube = 2-path X 2-path
    G = nx.cartesian_product(P2, P2)
    G = nx.cartesian_product(P2, G)
    assert nx.is_isomorphic(G, nx.cubical_graph())

    # 3x3 grid
    G = nx.cartesian_product(P3, P3)
    assert nx.is_isomorphic(G, nx.grid_2d_graph(3, 3))


def test_cartesian_product_random():
    G = nx.erdos_renyi_graph(10, 2 / 10.0)
    H = nx.erdos_renyi_graph(10, 2 / 10.0)
    GH = nx.cartesian_product(G, H)

    for u_G, u_H in GH.nodes():
        for v_G, v_H in GH.nodes():
            if (u_G == v_G and H.has_edge(u_H, v_H)) or (
                u_H == v_H and G.has_edge(u_G, v_G)
            ):
                assert GH.has_edge((u_G, u_H), (v_G, v_H))
            else:
                assert not GH.has_edge((u_G, u_H), (v_G, v_H))


def test_lexicographic_product_raises():
    with pytest.raises(nx.NetworkXError):
        P = nx.lexicographic_product(nx.DiGraph(), nx.Graph())


def test_lexicographic_product_null():
    null = nx.null_graph()
    empty10 = nx.empty_graph(10)
    K3 = nx.complete_graph(3)
    K10 = nx.complete_graph(10)
    P3 = nx.path_graph(3)
    P10 = nx.path_graph(10)
    # null graph
    G = nx.lexicographic_product(null, null)
    assert nx.is_isomorphic(G, null)
    # null_graph X anything = null_graph and v.v.
    G = nx.lexicographic_product(null, empty10)
    assert nx.is_isomorphic(G, null)
    G = nx.lexicographic_product(null, K3)
    assert nx.is_isomorphic(G, null)
    G = nx.lexicographic_product(null, K10)
    assert nx.is_isomorphic(G, null)
    G = nx.lexicographic_product(null, P3)
    assert nx.is_isomorphic(G, null)
    G = nx.lexicographic_product(null, P10)
    assert nx.is_isomorphic(G, null)
    G = nx.lexicographic_product(empty10, null)
    assert nx.is_isomorphic(G, null)
    G = nx.lexicographic_product(K3, null)
    assert nx.is_isomorphic(G, null)
    G = nx.lexicographic_product(K10, null)
    assert nx.is_isomorphic(G, null)
    G = nx.lexicographic_product(P3, null)
    assert nx.is_isomorphic(G, null)
    G = nx.lexicographic_product(P10, null)
    assert nx.is_isomorphic(G, null)


def test_lexicographic_product_size():
    K5 = nx.complete_graph(5)
    P5 = nx.path_graph(5)
    K3 = nx.complete_graph(3)
    G = nx.lexicographic_product(P5, K3)
    assert nx.number_of_nodes(G) == 5 * 3
    G = nx.lexicographic_product(K3, K5)
    assert nx.number_of_nodes(G) == 3 * 5


def test_lexicographic_product_combinations():
    P5 = nx.path_graph(5)
    K3 = nx.complete_graph(3)
    G = nx.lexicographic_product(P5, K3)
    assert nx.number_of_nodes(G) == 5 * 3
    G = nx.lexicographic_product(nx.MultiGraph(P5), K3)
    assert nx.number_of_nodes(G) == 5 * 3
    G = nx.lexicographic_product(P5, nx.MultiGraph(K3))
    assert nx.number_of_nodes(G) == 5 * 3
    G = nx.lexicographic_product(nx.MultiGraph(P5), nx.MultiGraph(K3))
    assert nx.number_of_nodes(G) == 5 * 3

    # No classic easily found classic results for lexicographic product


def test_lexicographic_product_random():
    G = nx.erdos_renyi_graph(10, 2 / 10.0)
    H = nx.erdos_renyi_graph(10, 2 / 10.0)
    GH = nx.lexicographic_product(G, H)

    for u_G, u_H in GH.nodes():
        for v_G, v_H in GH.nodes():
            if G.has_edge(u_G, v_G) or (u_G == v_G and H.has_edge(u_H, v_H)):
                assert GH.has_edge((u_G, u_H), (v_G, v_H))
            else:
                assert not GH.has_edge((u_G, u_H), (v_G, v_H))


def test_strong_product_raises():
    with pytest.raises(nx.NetworkXError):
        P = nx.strong_product(nx.DiGraph(), nx.Graph())


def test_strong_product_null():
    null = nx.null_graph()
    empty10 = nx.empty_graph(10)
    K3 = nx.complete_graph(3)
    K10 = nx.complete_graph(10)
    P3 = nx.path_graph(3)
    P10 = nx.path_graph(10)
    # null graph
    G = nx.strong_product(null, null)
    assert nx.is_isomorphic(G, null)
    # null_graph X anything = null_graph and v.v.
    G = nx.strong_product(null, empty10)
    assert nx.is_isomorphic(G, null)
    G = nx.strong_product(null, K3)
    assert nx.is_isomorphic(G, null)
    G = nx.strong_product(null, K10)
    assert nx.is_isomorphic(G, null)
    G = nx.strong_product(null, P3)
    assert nx.is_isomorphic(G, null)
    G = nx.strong_product(null, P10)
    assert nx.is_isomorphic(G, null)
    G = nx.strong_product(empty10, null)
    assert nx.is_isomorphic(G, null)
    G = nx.strong_product(K3, null)
    assert nx.is_isomorphic(G, null)
    G = nx.strong_product(K10, null)
    assert nx.is_isomorphic(G, null)
    G = nx.strong_product(P3, null)
    assert nx.is_isomorphic(G, null)
    G = nx.strong_product(P10, null)
    assert nx.is_isomorphic(G, null)


def test_strong_product_size():
    K5 = nx.complete_graph(5)
    P5 = nx.path_graph(5)
    K3 = nx.complete_graph(3)
    G = nx.strong_product(P5, K3)
    assert nx.number_of_nodes(G) == 5 * 3
    G = nx.strong_product(K3, K5)
    assert nx.number_of_nodes(G) == 3 * 5


def test_strong_product_combinations():
    P5 = nx.path_graph(5)
    K3 = nx.complete_graph(3)
    G = nx.strong_product(P5, K3)
    assert nx.number_of_nodes(G) == 5 * 3
    G = nx.strong_product(nx.MultiGraph(P5), K3)
    assert nx.number_of_nodes(G) == 5 * 3
    G = nx.strong_product(P5, nx.MultiGraph(K3))
    assert nx.number_of_nodes(G) == 5 * 3
    G = nx.strong_product(nx.MultiGraph(P5), nx.MultiGraph(K3))
    assert nx.number_of_nodes(G) == 5 * 3

    # No classic easily found classic results for strong product


def test_strong_product_random():
    G = nx.erdos_renyi_graph(10, 2 / 10.0)
    H = nx.erdos_renyi_graph(10, 2 / 10.0)
    GH = nx.strong_product(G, H)

    for u_G, u_H in GH.nodes():
        for v_G, v_H in GH.nodes():
            if (
                (u_G == v_G and H.has_edge(u_H, v_H))
                or (u_H == v_H and G.has_edge(u_G, v_G))
                or (G.has_edge(u_G, v_G) and H.has_edge(u_H, v_H))
            ):
                assert GH.has_edge((u_G, u_H), (v_G, v_H))
            else:
                assert not GH.has_edge((u_G, u_H), (v_G, v_H))


def test_graph_power_raises():
    with pytest.raises(nx.NetworkXNotImplemented):
        nx.power(nx.MultiDiGraph(), 2)


def test_graph_power():
    # wikipedia example for graph power
    G = nx.cycle_graph(7)
    G.add_edge(6, 7)
    G.add_edge(7, 8)
    G.add_edge(8, 9)
    G.add_edge(9, 2)
    H = nx.power(G, 2)

    assert edges_equal(
        list(H.edges()),
        [
            (0, 1),
            (0, 2),
            (0, 5),
            (0, 6),
            (0, 7),
            (1, 9),
            (1, 2),
            (1, 3),
            (1, 6),
            (2, 3),
            (2, 4),
            (2, 8),
            (2, 9),
            (3, 4),
            (3, 5),
            (3, 9),
            (4, 5),
            (4, 6),
            (5, 6),
            (5, 7),
            (6, 7),
            (6, 8),
            (7, 8),
            (7, 9),
            (8, 9),
        ],
    )


def test_graph_power_negative():
    with pytest.raises(ValueError):
        nx.power(nx.Graph(), -1)


def test_rooted_product_raises():
    with pytest.raises(nx.NodeNotFound):
        nx.rooted_product(nx.Graph(), nx.path_graph(2), 10)


def test_rooted_product():
    G = nx.cycle_graph(5)
    H = nx.Graph()
    H.add_edges_from([("a", "b"), ("b", "c"), ("b", "d")])
    R = nx.rooted_product(G, H, "a")
    assert len(R) == len(G) * len(H)
    assert R.size() == G.size() + len(G) * H.size()


def test_corona_product():
    G = nx.cycle_graph(3)
    H = nx.path_graph(2)
    C = nx.corona_product(G, H)
    assert len(C) == (len(G) * len(H)) + len(G)
    assert C.size() == G.size() + len(G) * H.size() + len(G) * len(H)


def test_modular_product():
    G = nx.path_graph(3)
    H = nx.path_graph(4)
    M = nx.modular_product(G, H)
    assert len(M) == len(G) * len(H)

    assert edges_equal(
        list(M.edges()),
        [
            ((0, 0), (1, 1)),
            ((0, 0), (2, 2)),
            ((0, 0), (2, 3)),
            ((0, 1), (1, 0)),
            ((0, 1), (1, 2)),
            ((0, 1), (2, 3)),
            ((0, 2), (1, 1)),
            ((0, 2), (1, 3)),
            ((0, 2), (2, 0)),
            ((0, 3), (1, 2)),
            ((0, 3), (2, 0)),
            ((0, 3), (2, 1)),
            ((1, 0), (2, 1)),
            ((1, 1), (2, 0)),
            ((1, 1), (2, 2)),
            ((1, 2), (2, 1)),
            ((1, 2), (2, 3)),
            ((1, 3), (2, 2)),
        ],
    )


def test_modular_product_raises():
    G = nx.Graph([(0, 1), (1, 2), (2, 0)])
    H = nx.Graph([(0, 1), (1, 2), (2, 0)])
    DG = nx.DiGraph([(0, 1), (1, 2), (2, 0)])
    DH = nx.DiGraph([(0, 1), (1, 2), (2, 0)])
    with pytest.raises(nx.NetworkXNotImplemented):
        nx.modular_product(G, DH)
    with pytest.raises(nx.NetworkXNotImplemented):
        nx.modular_product(DG, H)
    with pytest.raises(nx.NetworkXNotImplemented):
        nx.modular_product(DG, DH)

    MG = nx.MultiGraph([(0, 1), (1, 2), (2, 0), (0, 1)])
    MH = nx.MultiGraph([(0, 1), (1, 2), (2, 0), (0, 1)])
    with pytest.raises(nx.NetworkXNotImplemented):
        nx.modular_product(G, MH)
    with pytest.raises(nx.NetworkXNotImplemented):
        nx.modular_product(MG, H)
    with pytest.raises(nx.NetworkXNotImplemented):
        nx.modular_product(MG, MH)
    with pytest.raises(nx.NetworkXNotImplemented):
        # check multigraph with no multiedges
        nx.modular_product(nx.MultiGraph(G), H)
