import pytest

import networkx as nx
from networkx.generators import directed

# Unit tests for the :func:`~networkx.weisfeiler_lehman_graph_hash` function


def test_empty_graph_hash():
    """
    empty graphs should give hashes regardless of other params
    """
    G1 = nx.empty_graph()
    G2 = nx.empty_graph()

    h1 = nx.weisfeiler_lehman_graph_hash(G1)
    h2 = nx.weisfeiler_lehman_graph_hash(G2)
    h3 = nx.weisfeiler_lehman_graph_hash(G2, edge_attr="edge_attr1")
    h4 = nx.weisfeiler_lehman_graph_hash(G2, node_attr="node_attr1")
    h5 = nx.weisfeiler_lehman_graph_hash(
        G2, edge_attr="edge_attr1", node_attr="node_attr1"
    )
    h6 = nx.weisfeiler_lehman_graph_hash(G2, iterations=10)

    assert h1 == h2
    assert h1 == h3
    assert h1 == h4
    assert h1 == h5
    assert h1 == h6


def test_directed():
    """
    A directed graph with no bi-directional edges should yield different a graph hash
    to the same graph taken as undirected if there are no hash collisions.
    """
    r = 10
    for i in range(r):
        G_directed = nx.gn_graph(10 + r, seed=100 + i)
        G_undirected = nx.to_undirected(G_directed)

        h_directed = nx.weisfeiler_lehman_graph_hash(G_directed)
        h_undirected = nx.weisfeiler_lehman_graph_hash(G_undirected)

        assert h_directed != h_undirected


def test_reversed():
    """
    A directed graph with no bi-directional edges should yield different a graph hash
    to the same graph taken with edge directions reversed if there are no hash collisions.
    Here we test a cycle graph which is the minimal counterexample
    """
    G = nx.cycle_graph(5, create_using=nx.DiGraph)
    nx.set_node_attributes(G, {n: str(n) for n in G.nodes()}, name="label")

    G_reversed = G.reverse()

    h = nx.weisfeiler_lehman_graph_hash(G, node_attr="label")
    h_reversed = nx.weisfeiler_lehman_graph_hash(G_reversed, node_attr="label")

    assert h != h_reversed


def test_isomorphic():
    """
    graph hashes should be invariant to node-relabeling (when the output is reindexed
    by the same mapping)
    """
    n, r = 100, 10
    p = 1.0 / r
    for i in range(1, r + 1):
        G1 = nx.erdos_renyi_graph(n, p * i, seed=200 + i)
        G2 = nx.relabel_nodes(G1, {u: -1 * u for u in G1.nodes()})

        g1_hash = nx.weisfeiler_lehman_graph_hash(G1)
        g2_hash = nx.weisfeiler_lehman_graph_hash(G2)

        assert g1_hash == g2_hash


def test_isomorphic_edge_attr():
    """
    Isomorphic graphs with differing edge attributes should yield different graph
    hashes if the 'edge_attr' argument is supplied and populated in the graph,
    and there are no hash collisions.
    The output should still be invariant to node-relabeling
    """
    n, r = 100, 10
    p = 1.0 / r
    for i in range(1, r + 1):
        G1 = nx.erdos_renyi_graph(n, p * i, seed=300 + i)

        for a, b in G1.edges:
            G1[a][b]["edge_attr1"] = f"{a}-{b}-1"
            G1[a][b]["edge_attr2"] = f"{a}-{b}-2"

        g1_hash_with_edge_attr1 = nx.weisfeiler_lehman_graph_hash(
            G1, edge_attr="edge_attr1"
        )
        g1_hash_with_edge_attr2 = nx.weisfeiler_lehman_graph_hash(
            G1, edge_attr="edge_attr2"
        )
        g1_hash_no_edge_attr = nx.weisfeiler_lehman_graph_hash(G1, edge_attr=None)

        assert g1_hash_with_edge_attr1 != g1_hash_no_edge_attr
        assert g1_hash_with_edge_attr2 != g1_hash_no_edge_attr
        assert g1_hash_with_edge_attr1 != g1_hash_with_edge_attr2

        G2 = nx.relabel_nodes(G1, {u: -1 * u for u in G1.nodes()})

        g2_hash_with_edge_attr1 = nx.weisfeiler_lehman_graph_hash(
            G2, edge_attr="edge_attr1"
        )
        g2_hash_with_edge_attr2 = nx.weisfeiler_lehman_graph_hash(
            G2, edge_attr="edge_attr2"
        )

        assert g1_hash_with_edge_attr1 == g2_hash_with_edge_attr1
        assert g1_hash_with_edge_attr2 == g2_hash_with_edge_attr2


def test_missing_edge_attr():
    """
    If the 'edge_attr' argument is supplied but is missing from an edge in the graph,
    we should raise a KeyError
    """
    G = nx.Graph()
    G.add_edges_from([(1, 2, {"edge_attr1": "a"}), (1, 3, {})])
    pytest.raises(KeyError, nx.weisfeiler_lehman_graph_hash, G, edge_attr="edge_attr1")


def test_isomorphic_node_attr():
    """
    Isomorphic graphs with differing node attributes should yield different graph
    hashes if the 'node_attr' argument is supplied and populated in the graph, and
    there are no hash collisions.
    The output should still be invariant to node-relabeling
    """
    n, r = 100, 10
    p = 1.0 / r
    for i in range(1, r + 1):
        G1 = nx.erdos_renyi_graph(n, p * i, seed=400 + i)

        for u in G1.nodes():
            G1.nodes[u]["node_attr1"] = f"{u}-1"
            G1.nodes[u]["node_attr2"] = f"{u}-2"

        g1_hash_with_node_attr1 = nx.weisfeiler_lehman_graph_hash(
            G1, node_attr="node_attr1"
        )
        g1_hash_with_node_attr2 = nx.weisfeiler_lehman_graph_hash(
            G1, node_attr="node_attr2"
        )
        g1_hash_no_node_attr = nx.weisfeiler_lehman_graph_hash(G1, node_attr=None)

        assert g1_hash_with_node_attr1 != g1_hash_no_node_attr
        assert g1_hash_with_node_attr2 != g1_hash_no_node_attr
        assert g1_hash_with_node_attr1 != g1_hash_with_node_attr2

        G2 = nx.relabel_nodes(G1, {u: -1 * u for u in G1.nodes()})

        g2_hash_with_node_attr1 = nx.weisfeiler_lehman_graph_hash(
            G2, node_attr="node_attr1"
        )
        g2_hash_with_node_attr2 = nx.weisfeiler_lehman_graph_hash(
            G2, node_attr="node_attr2"
        )

        assert g1_hash_with_node_attr1 == g2_hash_with_node_attr1
        assert g1_hash_with_node_attr2 == g2_hash_with_node_attr2


def test_missing_node_attr():
    """
    If the 'node_attr' argument is supplied but is missing from a node in the graph,
    we should raise a KeyError
    """
    G = nx.Graph()
    G.add_nodes_from([(1, {"node_attr1": "a"}), (2, {})])
    G.add_edges_from([(1, 2), (2, 3), (3, 1), (1, 4)])
    pytest.raises(KeyError, nx.weisfeiler_lehman_graph_hash, G, node_attr="node_attr1")


def test_isomorphic_edge_attr_and_node_attr():
    """
    Isomorphic graphs with differing node attributes should yield different graph
    hashes if the 'node_attr' and 'edge_attr' argument is supplied and populated in
    the graph, and there are no hash collisions.
    The output should still be invariant to node-relabeling
    """
    n, r = 100, 10
    p = 1.0 / r
    for i in range(1, r + 1):
        G1 = nx.erdos_renyi_graph(n, p * i, seed=500 + i)

        for u in G1.nodes():
            G1.nodes[u]["node_attr1"] = f"{u}-1"
            G1.nodes[u]["node_attr2"] = f"{u}-2"

        for a, b in G1.edges:
            G1[a][b]["edge_attr1"] = f"{a}-{b}-1"
            G1[a][b]["edge_attr2"] = f"{a}-{b}-2"

        g1_hash_edge1_node1 = nx.weisfeiler_lehman_graph_hash(
            G1, edge_attr="edge_attr1", node_attr="node_attr1"
        )
        g1_hash_edge2_node2 = nx.weisfeiler_lehman_graph_hash(
            G1, edge_attr="edge_attr2", node_attr="node_attr2"
        )
        g1_hash_edge1_node2 = nx.weisfeiler_lehman_graph_hash(
            G1, edge_attr="edge_attr1", node_attr="node_attr2"
        )
        g1_hash_no_attr = nx.weisfeiler_lehman_graph_hash(G1)

        assert g1_hash_edge1_node1 != g1_hash_no_attr
        assert g1_hash_edge2_node2 != g1_hash_no_attr
        assert g1_hash_edge1_node1 != g1_hash_edge2_node2
        assert g1_hash_edge1_node2 != g1_hash_edge2_node2
        assert g1_hash_edge1_node2 != g1_hash_edge1_node1

        G2 = nx.relabel_nodes(G1, {u: -1 * u for u in G1.nodes()})

        g2_hash_edge1_node1 = nx.weisfeiler_lehman_graph_hash(
            G2, edge_attr="edge_attr1", node_attr="node_attr1"
        )
        g2_hash_edge2_node2 = nx.weisfeiler_lehman_graph_hash(
            G2, edge_attr="edge_attr2", node_attr="node_attr2"
        )

        assert g1_hash_edge1_node1 == g2_hash_edge1_node1
        assert g1_hash_edge2_node2 == g2_hash_edge2_node2


def test_digest_size():
    """
    The hash string lengths should be as expected for a variety of graphs and
    digest sizes
    """
    n, r = 100, 10
    p = 1.0 / r
    for i in range(1, r + 1):
        G = nx.erdos_renyi_graph(n, p * i, seed=1000 + i)

        h16 = nx.weisfeiler_lehman_graph_hash(G)
        h32 = nx.weisfeiler_lehman_graph_hash(G, digest_size=32)

        assert h16 != h32
        assert len(h16) == 16 * 2
        assert len(h32) == 32 * 2


# Unit tests for the :func:`~networkx.weisfeiler_lehman_hash_subgraphs` function


def is_subiteration(a, b):
    """
    returns True if that each hash sequence in 'a' is a prefix for
    the corresponding sequence indexed by the same node in 'b'.
    """
    return all(b[node][: len(hashes)] == hashes for node, hashes in a.items())


def hexdigest_sizes_correct(a, digest_size):
    """
    returns True if all hex digest sizes are the expected length in a node:subgraph-hashes
    dictionary. Hex digest string length == 2 * bytes digest length since each pair of hex
    digits encodes 1 byte (https://docs.python.org/3/library/hashlib.html)
    """
    hexdigest_size = digest_size * 2
    list_digest_sizes_correct = lambda l: all(len(x) == hexdigest_size for x in l)
    return all(list_digest_sizes_correct(hashes) for hashes in a.values())


def test_empty_graph_subgraph_hash():
    """ "
    empty graphs should give empty dict subgraph hashes regardless of other params
    """
    G = nx.empty_graph()

    subgraph_hashes1 = nx.weisfeiler_lehman_subgraph_hashes(G)
    subgraph_hashes2 = nx.weisfeiler_lehman_subgraph_hashes(G, edge_attr="edge_attr")
    subgraph_hashes3 = nx.weisfeiler_lehman_subgraph_hashes(G, node_attr="edge_attr")
    subgraph_hashes4 = nx.weisfeiler_lehman_subgraph_hashes(G, iterations=2)
    subgraph_hashes5 = nx.weisfeiler_lehman_subgraph_hashes(G, digest_size=64)

    assert subgraph_hashes1 == {}
    assert subgraph_hashes2 == {}
    assert subgraph_hashes3 == {}
    assert subgraph_hashes4 == {}
    assert subgraph_hashes5 == {}


def test_directed_subgraph_hash():
    """
    A directed graph with no bi-directional edges should yield different subgraph hashes
    to the same graph taken as undirected, if all hashes don't collide.
    """
    r = 10
    for i in range(r):
        G_directed = nx.gn_graph(10 + r, seed=100 + i)
        G_undirected = nx.to_undirected(G_directed)

        directed_subgraph_hashes = nx.weisfeiler_lehman_subgraph_hashes(G_directed)
        undirected_subgraph_hashes = nx.weisfeiler_lehman_subgraph_hashes(G_undirected)

        assert directed_subgraph_hashes != undirected_subgraph_hashes


def test_reversed_subgraph_hash():
    """
    A directed graph with no bi-directional edges should yield different subgraph hashes
    to the same graph taken with edge directions reversed if there are no hash collisions.
    Here we test a cycle graph which is the minimal counterexample
    """
    G = nx.cycle_graph(5, create_using=nx.DiGraph)
    nx.set_node_attributes(G, {n: str(n) for n in G.nodes()}, name="label")

    G_reversed = G.reverse()

    h = nx.weisfeiler_lehman_subgraph_hashes(G, node_attr="label")
    h_reversed = nx.weisfeiler_lehman_subgraph_hashes(G_reversed, node_attr="label")

    assert h != h_reversed


def test_isomorphic_subgraph_hash():
    """
    the subgraph hashes should be invariant to node-relabeling when the output is reindexed
    by the same mapping and all hashes don't collide.
    """
    n, r = 100, 10
    p = 1.0 / r
    for i in range(1, r + 1):
        G1 = nx.erdos_renyi_graph(n, p * i, seed=200 + i)
        G2 = nx.relabel_nodes(G1, {u: -1 * u for u in G1.nodes()})

        g1_subgraph_hashes = nx.weisfeiler_lehman_subgraph_hashes(G1)
        g2_subgraph_hashes = nx.weisfeiler_lehman_subgraph_hashes(G2)

        assert g1_subgraph_hashes == {-1 * k: v for k, v in g2_subgraph_hashes.items()}


def test_isomorphic_edge_attr_subgraph_hash():
    """
    Isomorphic graphs with differing edge attributes should yield different subgraph
    hashes if the 'edge_attr' argument is supplied and populated in the graph, and
    all hashes don't collide.
    The output should still be invariant to node-relabeling
    """
    n, r = 100, 10
    p = 1.0 / r
    for i in range(1, r + 1):
        G1 = nx.erdos_renyi_graph(n, p * i, seed=300 + i)

        for a, b in G1.edges:
            G1[a][b]["edge_attr1"] = f"{a}-{b}-1"
            G1[a][b]["edge_attr2"] = f"{a}-{b}-2"

        g1_hash_with_edge_attr1 = nx.weisfeiler_lehman_subgraph_hashes(
            G1, edge_attr="edge_attr1"
        )
        g1_hash_with_edge_attr2 = nx.weisfeiler_lehman_subgraph_hashes(
            G1, edge_attr="edge_attr2"
        )
        g1_hash_no_edge_attr = nx.weisfeiler_lehman_subgraph_hashes(G1, edge_attr=None)

        assert g1_hash_with_edge_attr1 != g1_hash_no_edge_attr
        assert g1_hash_with_edge_attr2 != g1_hash_no_edge_attr
        assert g1_hash_with_edge_attr1 != g1_hash_with_edge_attr2

        G2 = nx.relabel_nodes(G1, {u: -1 * u for u in G1.nodes()})

        g2_hash_with_edge_attr1 = nx.weisfeiler_lehman_subgraph_hashes(
            G2, edge_attr="edge_attr1"
        )
        g2_hash_with_edge_attr2 = nx.weisfeiler_lehman_subgraph_hashes(
            G2, edge_attr="edge_attr2"
        )

        assert g1_hash_with_edge_attr1 == {
            -1 * k: v for k, v in g2_hash_with_edge_attr1.items()
        }
        assert g1_hash_with_edge_attr2 == {
            -1 * k: v for k, v in g2_hash_with_edge_attr2.items()
        }


def test_missing_edge_attr_subgraph_hash():
    """
    If the 'edge_attr' argument is supplied but is missing from an edge in the graph,
    we should raise a KeyError
    """
    G = nx.Graph()
    G.add_edges_from([(1, 2, {"edge_attr1": "a"}), (1, 3, {})])
    pytest.raises(
        KeyError, nx.weisfeiler_lehman_subgraph_hashes, G, edge_attr="edge_attr1"
    )


def test_isomorphic_node_attr_subgraph_hash():
    """
    Isomorphic graphs with differing node attributes should yield different subgraph
    hashes if the 'node_attr' argument is supplied and populated in the graph, and
    all hashes don't collide.
    The output should still be invariant to node-relabeling
    """
    n, r = 100, 10
    p = 1.0 / r
    for i in range(1, r + 1):
        G1 = nx.erdos_renyi_graph(n, p * i, seed=400 + i)

        for u in G1.nodes():
            G1.nodes[u]["node_attr1"] = f"{u}-1"
            G1.nodes[u]["node_attr2"] = f"{u}-2"

        g1_hash_with_node_attr1 = nx.weisfeiler_lehman_subgraph_hashes(
            G1, node_attr="node_attr1"
        )
        g1_hash_with_node_attr2 = nx.weisfeiler_lehman_subgraph_hashes(
            G1, node_attr="node_attr2"
        )
        g1_hash_no_node_attr = nx.weisfeiler_lehman_subgraph_hashes(G1, node_attr=None)

        assert g1_hash_with_node_attr1 != g1_hash_no_node_attr
        assert g1_hash_with_node_attr2 != g1_hash_no_node_attr
        assert g1_hash_with_node_attr1 != g1_hash_with_node_attr2

        G2 = nx.relabel_nodes(G1, {u: -1 * u for u in G1.nodes()})

        g2_hash_with_node_attr1 = nx.weisfeiler_lehman_subgraph_hashes(
            G2, node_attr="node_attr1"
        )
        g2_hash_with_node_attr2 = nx.weisfeiler_lehman_subgraph_hashes(
            G2, node_attr="node_attr2"
        )

        assert g1_hash_with_node_attr1 == {
            -1 * k: v for k, v in g2_hash_with_node_attr1.items()
        }
        assert g1_hash_with_node_attr2 == {
            -1 * k: v for k, v in g2_hash_with_node_attr2.items()
        }


def test_missing_node_attr_subgraph_hash():
    """
    If the 'node_attr' argument is supplied but is missing from a node in the graph,
    we should raise a KeyError
    """
    G = nx.Graph()
    G.add_nodes_from([(1, {"node_attr1": "a"}), (2, {})])
    G.add_edges_from([(1, 2), (2, 3), (3, 1), (1, 4)])
    pytest.raises(
        KeyError, nx.weisfeiler_lehman_subgraph_hashes, G, node_attr="node_attr1"
    )


def test_isomorphic_edge_attr_and_node_attr_subgraph_hash():
    """
    Isomorphic graphs with differing node attributes should yield different subgraph
    hashes if the 'node_attr' and 'edge_attr' argument is supplied and populated in
    the graph, and all hashes don't collide
    The output should still be invariant to node-relabeling
    """
    n, r = 100, 10
    p = 1.0 / r
    for i in range(1, r + 1):
        G1 = nx.erdos_renyi_graph(n, p * i, seed=500 + i)

        for u in G1.nodes():
            G1.nodes[u]["node_attr1"] = f"{u}-1"
            G1.nodes[u]["node_attr2"] = f"{u}-2"

        for a, b in G1.edges:
            G1[a][b]["edge_attr1"] = f"{a}-{b}-1"
            G1[a][b]["edge_attr2"] = f"{a}-{b}-2"

        g1_hash_edge1_node1 = nx.weisfeiler_lehman_subgraph_hashes(
            G1, edge_attr="edge_attr1", node_attr="node_attr1"
        )
        g1_hash_edge2_node2 = nx.weisfeiler_lehman_subgraph_hashes(
            G1, edge_attr="edge_attr2", node_attr="node_attr2"
        )
        g1_hash_edge1_node2 = nx.weisfeiler_lehman_subgraph_hashes(
            G1, edge_attr="edge_attr1", node_attr="node_attr2"
        )
        g1_hash_no_attr = nx.weisfeiler_lehman_subgraph_hashes(G1)

        assert g1_hash_edge1_node1 != g1_hash_no_attr
        assert g1_hash_edge2_node2 != g1_hash_no_attr
        assert g1_hash_edge1_node1 != g1_hash_edge2_node2
        assert g1_hash_edge1_node2 != g1_hash_edge2_node2
        assert g1_hash_edge1_node2 != g1_hash_edge1_node1

        G2 = nx.relabel_nodes(G1, {u: -1 * u for u in G1.nodes()})

        g2_hash_edge1_node1 = nx.weisfeiler_lehman_subgraph_hashes(
            G2, edge_attr="edge_attr1", node_attr="node_attr1"
        )
        g2_hash_edge2_node2 = nx.weisfeiler_lehman_subgraph_hashes(
            G2, edge_attr="edge_attr2", node_attr="node_attr2"
        )

        assert g1_hash_edge1_node1 == {
            -1 * k: v for k, v in g2_hash_edge1_node1.items()
        }
        assert g1_hash_edge2_node2 == {
            -1 * k: v for k, v in g2_hash_edge2_node2.items()
        }


def test_iteration_depth():
    """
    All nodes should have the correct number of subgraph hashes in the output when
    using degree as initial node labels
    Subsequent iteration depths for the same graph should be additive for each node
    """
    n, r = 100, 10
    p = 1.0 / r
    for i in range(1, r + 1):
        G = nx.erdos_renyi_graph(n, p * i, seed=600 + i)

        depth3 = nx.weisfeiler_lehman_subgraph_hashes(G, iterations=3)
        depth4 = nx.weisfeiler_lehman_subgraph_hashes(G, iterations=4)
        depth5 = nx.weisfeiler_lehman_subgraph_hashes(G, iterations=5)

        assert all(len(hashes) == 3 for hashes in depth3.values())
        assert all(len(hashes) == 4 for hashes in depth4.values())
        assert all(len(hashes) == 5 for hashes in depth5.values())

        assert is_subiteration(depth3, depth4)
        assert is_subiteration(depth4, depth5)
        assert is_subiteration(depth3, depth5)


def test_iteration_depth_edge_attr():
    """
    All nodes should have the correct number of subgraph hashes in the output when
    setting initial node labels empty and using an edge attribute when aggregating
    neighborhoods.
    Subsequent iteration depths for the same graph should be additive for each node
    """
    n, r = 100, 10
    p = 1.0 / r
    for i in range(1, r + 1):
        G = nx.erdos_renyi_graph(n, p * i, seed=700 + i)

        for a, b in G.edges:
            G[a][b]["edge_attr1"] = f"{a}-{b}-1"

        depth3 = nx.weisfeiler_lehman_subgraph_hashes(
            G, edge_attr="edge_attr1", iterations=3
        )
        depth4 = nx.weisfeiler_lehman_subgraph_hashes(
            G, edge_attr="edge_attr1", iterations=4
        )
        depth5 = nx.weisfeiler_lehman_subgraph_hashes(
            G, edge_attr="edge_attr1", iterations=5
        )

        assert all(len(hashes) == 3 for hashes in depth3.values())
        assert all(len(hashes) == 4 for hashes in depth4.values())
        assert all(len(hashes) == 5 for hashes in depth5.values())

        assert is_subiteration(depth3, depth4)
        assert is_subiteration(depth4, depth5)
        assert is_subiteration(depth3, depth5)


def test_iteration_depth_node_attr():
    """
    All nodes should have the correct number of subgraph hashes in the output when
    setting initial node labels to an attribute.
    Subsequent iteration depths for the same graph should be additive for each node
    """
    n, r = 100, 10
    p = 1.0 / r
    for i in range(1, r + 1):
        G = nx.erdos_renyi_graph(n, p * i, seed=800 + i)

        for u in G.nodes():
            G.nodes[u]["node_attr1"] = f"{u}-1"

        depth3 = nx.weisfeiler_lehman_subgraph_hashes(
            G, node_attr="node_attr1", iterations=3
        )
        depth4 = nx.weisfeiler_lehman_subgraph_hashes(
            G, node_attr="node_attr1", iterations=4
        )
        depth5 = nx.weisfeiler_lehman_subgraph_hashes(
            G, node_attr="node_attr1", iterations=5
        )

        assert all(len(hashes) == 3 for hashes in depth3.values())
        assert all(len(hashes) == 4 for hashes in depth4.values())
        assert all(len(hashes) == 5 for hashes in depth5.values())

        assert is_subiteration(depth3, depth4)
        assert is_subiteration(depth4, depth5)
        assert is_subiteration(depth3, depth5)


def test_iteration_depth_node_edge_attr():
    """
    All nodes should have the correct number of subgraph hashes in the output when
    setting initial node labels to an attribute and also using an edge attribute when
    aggregating neighborhoods.
    Subsequent iteration depths for the same graph should be additive for each node
    """
    n, r = 100, 10
    p = 1.0 / r
    for i in range(1, r + 1):
        G = nx.erdos_renyi_graph(n, p * i, seed=900 + i)

        for u in G.nodes():
            G.nodes[u]["node_attr1"] = f"{u}-1"

        for a, b in G.edges:
            G[a][b]["edge_attr1"] = f"{a}-{b}-1"

        depth3 = nx.weisfeiler_lehman_subgraph_hashes(
            G, edge_attr="edge_attr1", node_attr="node_attr1", iterations=3
        )
        depth4 = nx.weisfeiler_lehman_subgraph_hashes(
            G, edge_attr="edge_attr1", node_attr="node_attr1", iterations=4
        )
        depth5 = nx.weisfeiler_lehman_subgraph_hashes(
            G, edge_attr="edge_attr1", node_attr="node_attr1", iterations=5
        )

        assert all(len(hashes) == 3 for hashes in depth3.values())
        assert all(len(hashes) == 4 for hashes in depth4.values())
        assert all(len(hashes) == 5 for hashes in depth5.values())

        assert is_subiteration(depth3, depth4)
        assert is_subiteration(depth4, depth5)
        assert is_subiteration(depth3, depth5)


def test_digest_size_subgraph_hash():
    """
    The hash string lengths should be as expected for a variety of graphs and
    digest sizes
    """
    n, r = 100, 10
    p = 1.0 / r
    for i in range(1, r + 1):
        G = nx.erdos_renyi_graph(n, p * i, seed=1000 + i)

        digest_size16_hashes = nx.weisfeiler_lehman_subgraph_hashes(G)
        digest_size32_hashes = nx.weisfeiler_lehman_subgraph_hashes(G, digest_size=32)

        assert digest_size16_hashes != digest_size32_hashes

        assert hexdigest_sizes_correct(digest_size16_hashes, 16)
        assert hexdigest_sizes_correct(digest_size32_hashes, 32)


def test_initial_node_labels_subgraph_hash():
    """
    Including the hashed initial label prepends an extra hash to the lists
    """
    G = nx.path_graph(5)
    nx.set_node_attributes(G, {i: int(0 < i < 4) for i in G}, "label")
    # initial node labels:
    # 0--1--1--1--0

    without_initial_label = nx.weisfeiler_lehman_subgraph_hashes(G, node_attr="label")
    assert all(len(v) == 3 for v in without_initial_label.values())
    # 3 different 1 hop nhds
    assert len({v[0] for v in without_initial_label.values()}) == 3

    with_initial_label = nx.weisfeiler_lehman_subgraph_hashes(
        G, node_attr="label", include_initial_labels=True
    )
    assert all(len(v) == 4 for v in with_initial_label.values())
    # 2 different initial labels
    assert len({v[0] for v in with_initial_label.values()}) == 2

    # check hashes match otherwise
    for u in G:
        for a, b in zip(
            with_initial_label[u][1:], without_initial_label[u], strict=True
        ):
            assert a == b
