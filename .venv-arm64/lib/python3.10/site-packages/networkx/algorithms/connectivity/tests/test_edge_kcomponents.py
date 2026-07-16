import itertools as it

import pytest

import networkx as nx
from networkx.algorithms.connectivity import EdgeComponentAuxGraph, bridge_components
from networkx.algorithms.connectivity.edge_kcomponents import general_k_edge_subgraphs
from networkx.utils import pairwise

# ----------------
# Helper functions
# ----------------


def fset(list_of_sets):
    """allows == to be used for list of sets"""
    return set(map(frozenset, list_of_sets))


def _assert_subgraph_edge_connectivity(G, ccs_subgraph, k):
    """
    tests properties of k-edge-connected subgraphs

    the actual edge connectivity should be no less than k unless the cc is a
    single node.
    """
    for cc in ccs_subgraph:
        C = G.subgraph(cc)
        if len(cc) > 1:
            connectivity = nx.edge_connectivity(C)
            assert connectivity >= k


def _memo_connectivity(G, u, v, memo):
    edge = (u, v)
    if edge in memo:
        return memo[edge]
    if not G.is_directed():
        redge = (v, u)
        if redge in memo:
            return memo[redge]
    memo[edge] = nx.edge_connectivity(G, *edge)
    return memo[edge]


def _all_pairs_connectivity(G, cc, k, memo):
    # Brute force check
    for u, v in it.combinations(cc, 2):
        # Use a memoization dict to save on computation
        connectivity = _memo_connectivity(G, u, v, memo)
        if G.is_directed():
            connectivity = min(connectivity, _memo_connectivity(G, v, u, memo))
        assert connectivity >= k


def _assert_local_cc_edge_connectivity(G, ccs_local, k, memo):
    """
    tests properties of k-edge-connected components

    the local edge connectivity between each pair of nodes in the original
    graph should be no less than k unless the cc is a single node.
    """
    for cc in ccs_local:
        if len(cc) > 1:
            # Strategy for testing a bit faster: If the subgraph has high edge
            # connectivity then it must have local connectivity
            C = G.subgraph(cc)
            connectivity = nx.edge_connectivity(C)
            if connectivity < k:
                # Otherwise do the brute force (with memoization) check
                _all_pairs_connectivity(G, cc, k, memo)


# Helper function
def _check_edge_connectivity(G):
    """
    Helper - generates all k-edge-components using the aux graph.  Checks the
    both local and subgraph edge connectivity of each cc. Also checks that
    alternate methods of computing the k-edge-ccs generate the same result.
    """
    # Construct the auxiliary graph that can be used to make each k-cc or k-sub
    aux_graph = EdgeComponentAuxGraph.construct(G)

    # memoize the local connectivity in this graph
    memo = {}

    for k in it.count(1):
        # Test "local" k-edge-components and k-edge-subgraphs
        ccs_local = fset(aux_graph.k_edge_components(k))
        ccs_subgraph = fset(aux_graph.k_edge_subgraphs(k))

        # Check connectivity properties that should be guaranteed by the
        # algorithms.
        _assert_local_cc_edge_connectivity(G, ccs_local, k, memo)
        _assert_subgraph_edge_connectivity(G, ccs_subgraph, k)

        if k == 1 or k == 2 and not G.is_directed():
            assert (
                ccs_local == ccs_subgraph
            ), "Subgraphs and components should be the same when k == 1 or (k == 2 and not G.directed())"

        if G.is_directed():
            # Test special case methods are the same as the aux graph
            if k == 1:
                alt_sccs = fset(nx.strongly_connected_components(G))
                assert alt_sccs == ccs_local, "k=1 failed alt"
                assert alt_sccs == ccs_subgraph, "k=1 failed alt"
        else:
            # Test special case methods are the same as the aux graph
            if k == 1:
                alt_ccs = fset(nx.connected_components(G))
                assert alt_ccs == ccs_local, "k=1 failed alt"
                assert alt_ccs == ccs_subgraph, "k=1 failed alt"
            elif k == 2:
                alt_bridge_ccs = fset(bridge_components(G))
                assert alt_bridge_ccs == ccs_local, "k=2 failed alt"
                assert alt_bridge_ccs == ccs_subgraph, "k=2 failed alt"
            # if new methods for k == 3 or k == 4 are implemented add them here

        # Check the general subgraph method works by itself
        alt_subgraph_ccs = fset(
            [set(C.nodes()) for C in general_k_edge_subgraphs(G, k=k)]
        )
        assert alt_subgraph_ccs == ccs_subgraph, "alt subgraph method failed"

        # Stop once k is larger than all special case methods
        # and we cannot break down ccs any further.
        if k > 2 and all(len(cc) == 1 for cc in ccs_local):
            break


# ----------------
# Misc tests
# ----------------


def test_zero_k_exception():
    G = nx.Graph()
    # functions that return generators error immediately
    pytest.raises(ValueError, nx.k_edge_components, G, k=0)
    pytest.raises(ValueError, nx.k_edge_subgraphs, G, k=0)

    # actual generators only error when you get the first item
    aux_graph = EdgeComponentAuxGraph.construct(G)
    pytest.raises(ValueError, list, aux_graph.k_edge_components(k=0))
    pytest.raises(ValueError, list, aux_graph.k_edge_subgraphs(k=0))

    pytest.raises(ValueError, list, general_k_edge_subgraphs(G, k=0))


def test_empty_input():
    G = nx.Graph()
    assert [] == list(nx.k_edge_components(G, k=5))
    assert [] == list(nx.k_edge_subgraphs(G, k=5))

    G = nx.DiGraph()
    assert [] == list(nx.k_edge_components(G, k=5))
    assert [] == list(nx.k_edge_subgraphs(G, k=5))


def test_not_implemented():
    G = nx.MultiGraph()
    pytest.raises(nx.NetworkXNotImplemented, EdgeComponentAuxGraph.construct, G)
    pytest.raises(nx.NetworkXNotImplemented, nx.k_edge_components, G, k=2)
    pytest.raises(nx.NetworkXNotImplemented, nx.k_edge_subgraphs, G, k=2)
    with pytest.raises(nx.NetworkXNotImplemented):
        next(bridge_components(G))
    with pytest.raises(nx.NetworkXNotImplemented):
        next(bridge_components(nx.DiGraph()))


def test_general_k_edge_subgraph_quick_return():
    # tests quick return optimization
    G = nx.Graph()
    G.add_node(0)
    subgraphs = list(general_k_edge_subgraphs(G, k=1))
    assert len(subgraphs) == 1
    for subgraph in subgraphs:
        assert subgraph.number_of_nodes() == 1

    G.add_node(1)
    subgraphs = list(general_k_edge_subgraphs(G, k=1))
    assert len(subgraphs) == 2
    for subgraph in subgraphs:
        assert subgraph.number_of_nodes() == 1


# ----------------
# Undirected tests
# ----------------


def test_random_gnp():
    # seeds = [1550709854, 1309423156, 4208992358, 2785630813, 1915069929]
    seeds = [12, 13]

    for seed in seeds:
        G = nx.gnp_random_graph(20, 0.2, seed=seed)
        _check_edge_connectivity(G)


def test_configuration():
    # seeds = [2718183590, 2470619828, 1694705158, 3001036531, 2401251497]
    seeds = [14, 15]
    for seed in seeds:
        deg_seq = nx.random_powerlaw_tree_sequence(20, seed=seed, tries=5000)
        G = nx.Graph(nx.configuration_model(deg_seq, seed=seed))
        G.remove_edges_from(nx.selfloop_edges(G))
        _check_edge_connectivity(G)


def test_shell():
    # seeds = [2057382236, 3331169846, 1840105863, 476020778, 2247498425]
    seeds = [20]
    for seed in seeds:
        constructor = [(12, 70, 0.8), (15, 40, 0.6)]
        G = nx.random_shell_graph(constructor, seed=seed)
        _check_edge_connectivity(G)


def test_karate():
    G = nx.karate_club_graph()
    _check_edge_connectivity(G)


def test_tarjan_bridge():
    # graph from tarjan paper
    # RE Tarjan - "A note on finding the bridges of a graph"
    # Information Processing Letters, 1974 - Elsevier
    # doi:10.1016/0020-0190(74)90003-9.
    # define 2-connected components and bridges
    ccs = [
        (1, 2, 4, 3, 1, 4),
        (5, 6, 7, 5),
        (8, 9, 10, 8),
        (17, 18, 16, 15, 17),
        (11, 12, 14, 13, 11, 14),
    ]
    bridges = [(4, 8), (3, 5), (3, 17)]
    G = nx.Graph(it.chain(*(pairwise(path) for path in ccs + bridges)))
    _check_edge_connectivity(G)


def test_bridge_cc():
    # define 2-connected components and bridges
    cc2 = [(1, 2, 4, 3, 1, 4), (8, 9, 10, 8), (11, 12, 13, 11)]
    bridges = [(4, 8), (3, 5), (20, 21), (22, 23, 24)]
    G = nx.Graph(it.chain(*(pairwise(path) for path in cc2 + bridges)))
    bridge_ccs = fset(bridge_components(G))
    target_ccs = fset(
        [{1, 2, 3, 4}, {5}, {8, 9, 10}, {11, 12, 13}, {20}, {21}, {22}, {23}, {24}]
    )
    assert bridge_ccs == target_ccs
    _check_edge_connectivity(G)


def test_undirected_aux_graph():
    # Graph similar to the one in
    # http://journals.plos.org/plosone/article?id=10.1371/journal.pone.0136264
    a, b, c, d, e, f, g, h, i = "abcdefghi"
    paths = [
        (a, d, b, f, c),
        (a, e, b),
        (a, e, b, c, g, b, a),
        (c, b),
        (f, g, f),
        (h, i),
    ]
    G = nx.Graph(it.chain(*[pairwise(path) for path in paths]))
    aux_graph = EdgeComponentAuxGraph.construct(G)

    components_1 = fset(aux_graph.k_edge_subgraphs(k=1))
    target_1 = fset([{a, b, c, d, e, f, g}, {h, i}])
    assert target_1 == components_1

    # Check that the undirected case for k=1 agrees with CCs
    alt_1 = fset(nx.k_edge_subgraphs(G, k=1))
    assert alt_1 == components_1

    components_2 = fset(aux_graph.k_edge_subgraphs(k=2))
    target_2 = fset([{a, b, c, d, e, f, g}, {h}, {i}])
    assert target_2 == components_2

    # Check that the undirected case for k=2 agrees with bridge components
    alt_2 = fset(nx.k_edge_subgraphs(G, k=2))
    assert alt_2 == components_2

    components_3 = fset(aux_graph.k_edge_subgraphs(k=3))
    target_3 = fset([{a}, {b, c, f, g}, {d}, {e}, {h}, {i}])
    assert target_3 == components_3

    components_4 = fset(aux_graph.k_edge_subgraphs(k=4))
    target_4 = fset([{a}, {b}, {c}, {d}, {e}, {f}, {g}, {h}, {i}])
    assert target_4 == components_4

    _check_edge_connectivity(G)


def test_local_subgraph_difference():
    paths = [
        (11, 12, 13, 14, 11, 13, 14, 12),  # first 4-clique
        (21, 22, 23, 24, 21, 23, 24, 22),  # second 4-clique
        # paths connecting each node of the 4 cliques
        (11, 101, 21),
        (12, 102, 22),
        (13, 103, 23),
        (14, 104, 24),
    ]
    G = nx.Graph(it.chain(*[pairwise(path) for path in paths]))
    aux_graph = EdgeComponentAuxGraph.construct(G)

    # Each clique is returned separately in k-edge-subgraphs
    subgraph_ccs = fset(aux_graph.k_edge_subgraphs(3))
    subgraph_target = fset(
        [{101}, {102}, {103}, {104}, {21, 22, 23, 24}, {11, 12, 13, 14}]
    )
    assert subgraph_ccs == subgraph_target

    # But in k-edge-ccs they are returned together
    # because they are locally 3-edge-connected
    local_ccs = fset(aux_graph.k_edge_components(3))
    local_target = fset([{101}, {102}, {103}, {104}, {11, 12, 13, 14, 21, 22, 23, 24}])
    assert local_ccs == local_target


def test_local_subgraph_difference_directed():
    dipaths = [(1, 2, 3, 4, 1), (1, 3, 1)]
    G = nx.DiGraph(it.chain(*[pairwise(path) for path in dipaths]))

    assert fset(nx.k_edge_components(G, k=1)) == fset(nx.k_edge_subgraphs(G, k=1))

    # Unlike undirected graphs, when k=2, for directed graphs there is a case
    # where the k-edge-ccs are not the same as the k-edge-subgraphs.
    # (in directed graphs ccs and subgraphs are the same when k=2)
    assert fset(nx.k_edge_components(G, k=2)) != fset(nx.k_edge_subgraphs(G, k=2))

    assert fset(nx.k_edge_components(G, k=3)) == fset(nx.k_edge_subgraphs(G, k=3))

    _check_edge_connectivity(G)


def test_triangles():
    paths = [
        (11, 12, 13, 11),  # first 3-clique
        (21, 22, 23, 21),  # second 3-clique
        (11, 21),  # connected by an edge
    ]
    G = nx.Graph(it.chain(*[pairwise(path) for path in paths]))

    # subgraph and ccs are the same in all cases here
    assert fset(nx.k_edge_components(G, k=1)) == fset(nx.k_edge_subgraphs(G, k=1))

    assert fset(nx.k_edge_components(G, k=2)) == fset(nx.k_edge_subgraphs(G, k=2))

    assert fset(nx.k_edge_components(G, k=3)) == fset(nx.k_edge_subgraphs(G, k=3))

    _check_edge_connectivity(G)


def test_four_clique():
    paths = [
        (11, 12, 13, 14, 11, 13, 14, 12),  # first 4-clique
        (21, 22, 23, 24, 21, 23, 24, 22),  # second 4-clique
        # paths connecting the 4 cliques such that they are
        # 3-connected in G, but not in the subgraph.
        # Case where the nodes bridging them do not have degree less than 3.
        (100, 13),
        (12, 100, 22),
        (13, 200, 23),
        (14, 300, 24),
    ]
    G = nx.Graph(it.chain(*[pairwise(path) for path in paths]))

    # The subgraphs and ccs are different for k=3
    local_ccs = fset(nx.k_edge_components(G, k=3))
    subgraphs = fset(nx.k_edge_subgraphs(G, k=3))
    assert local_ccs != subgraphs

    # The cliques ares in the same cc
    clique1 = frozenset(paths[0])
    clique2 = frozenset(paths[1])
    assert clique1.union(clique2).union({100}) in local_ccs

    # but different subgraphs
    assert clique1 in subgraphs
    assert clique2 in subgraphs

    assert G.degree(100) == 3

    _check_edge_connectivity(G)


def test_five_clique():
    # Make a graph that can be disconnected less than 4 edges, but no node has
    # degree less than 4.
    G = nx.disjoint_union(nx.complete_graph(5), nx.complete_graph(5))
    paths = [
        # add aux-connections
        (1, 100, 6),
        (2, 100, 7),
        (3, 200, 8),
        (4, 200, 100),
    ]
    G.add_edges_from(it.chain(*[pairwise(path) for path in paths]))
    assert min(dict(nx.degree(G)).values()) == 4

    # For k=3 they are the same
    assert fset(nx.k_edge_components(G, k=3)) == fset(nx.k_edge_subgraphs(G, k=3))

    # For k=4 they are the different
    # the aux nodes are in the same CC as clique 1 but no the same subgraph
    assert fset(nx.k_edge_components(G, k=4)) != fset(nx.k_edge_subgraphs(G, k=4))

    # For k=5 they are not the same
    assert fset(nx.k_edge_components(G, k=5)) != fset(nx.k_edge_subgraphs(G, k=5))

    # For k=6 they are the same
    assert fset(nx.k_edge_components(G, k=6)) == fset(nx.k_edge_subgraphs(G, k=6))
    _check_edge_connectivity(G)


# ----------------
# Undirected tests
# ----------------


def test_directed_aux_graph():
    # Graph similar to the one in
    # http://journals.plos.org/plosone/article?id=10.1371/journal.pone.0136264
    a, b, c, d, e, f, g, h, i = "abcdefghi"
    dipaths = [
        (a, d, b, f, c),
        (a, e, b),
        (a, e, b, c, g, b, a),
        (c, b),
        (f, g, f),
        (h, i),
    ]
    G = nx.DiGraph(it.chain(*[pairwise(path) for path in dipaths]))
    aux_graph = EdgeComponentAuxGraph.construct(G)

    components_1 = fset(aux_graph.k_edge_subgraphs(k=1))
    target_1 = fset([{a, b, c, d, e, f, g}, {h}, {i}])
    assert target_1 == components_1

    # Check that the directed case for k=1 agrees with SCCs
    alt_1 = fset(nx.strongly_connected_components(G))
    assert alt_1 == components_1

    components_2 = fset(aux_graph.k_edge_subgraphs(k=2))
    target_2 = fset([{i}, {e}, {d}, {b, c, f, g}, {h}, {a}])
    assert target_2 == components_2

    components_3 = fset(aux_graph.k_edge_subgraphs(k=3))
    target_3 = fset([{a}, {b}, {c}, {d}, {e}, {f}, {g}, {h}, {i}])
    assert target_3 == components_3


def test_random_gnp_directed():
    # seeds = [3894723670, 500186844, 267231174, 2181982262, 1116750056]
    seeds = [21]
    for seed in seeds:
        G = nx.gnp_random_graph(20, 0.2, directed=True, seed=seed)
        _check_edge_connectivity(G)


def test_configuration_directed():
    # seeds = [671221681, 2403749451, 124433910, 672335939, 1193127215]
    seeds = [67]
    for seed in seeds:
        deg_seq = nx.random_powerlaw_tree_sequence(20, seed=seed, tries=5000)
        G = nx.DiGraph(nx.configuration_model(deg_seq, seed=seed))
        G.remove_edges_from(nx.selfloop_edges(G))
        _check_edge_connectivity(G)


def test_shell_directed():
    # seeds = [3134027055, 4079264063, 1350769518, 1405643020, 530038094]
    seeds = [31]
    for seed in seeds:
        constructor = [(12, 70, 0.8), (15, 40, 0.6)]
        G = nx.random_shell_graph(constructor, seed=seed).to_directed()
        _check_edge_connectivity(G)


def test_karate_directed():
    G = nx.karate_club_graph().to_directed()
    _check_edge_connectivity(G)
