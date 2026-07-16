"""Unit tests for the :mod:`networkx.algorithms.minors.contraction` module."""

import pytest

import networkx as nx
from networkx.utils import arbitrary_element, edges_equal, nodes_equal


def test_quotient_graph_complete_multipartite():
    """Tests that the quotient graph of the complete *n*-partite graph
    under the "same neighbors" node relation is the complete graph on *n*
    nodes.

    """
    G = nx.complete_multipartite_graph(2, 3, 4)
    # Two nodes are equivalent if they are not adjacent but have the same
    # neighbor set.

    def same_neighbors(u, v):
        return u not in G[v] and v not in G[u] and G[u] == G[v]

    expected = nx.complete_graph(3)
    actual = nx.quotient_graph(G, same_neighbors)
    # It won't take too long to run a graph isomorphism algorithm on such
    # small graphs.
    assert nx.is_isomorphic(expected, actual)


def test_quotient_graph_complete_bipartite():
    """Tests that the quotient graph of the complete bipartite graph under
    the "same neighbors" node relation is `K_2`.

    """
    G = nx.complete_bipartite_graph(2, 3)
    # Two nodes are equivalent if they are not adjacent but have the same
    # neighbor set.

    def same_neighbors(u, v):
        return u not in G[v] and v not in G[u] and G[u] == G[v]

    expected = nx.complete_graph(2)
    actual = nx.quotient_graph(G, same_neighbors)
    # It won't take too long to run a graph isomorphism algorithm on such
    # small graphs.
    assert nx.is_isomorphic(expected, actual)


def test_quotient_graph_edge_relation():
    """Tests for specifying an alternate edge relation for the quotient
    graph.

    """
    G = nx.path_graph(5)

    def identity(u, v):
        return u == v

    def same_parity(b, c):
        return arbitrary_element(b) % 2 == arbitrary_element(c) % 2

    actual = nx.quotient_graph(G, identity, same_parity)
    expected = nx.Graph()
    expected.add_edges_from([(0, 2), (0, 4), (2, 4)])
    expected.add_edge(1, 3)
    assert nx.is_isomorphic(actual, expected)


def test_condensation_as_quotient():
    """This tests that the condensation of a graph can be viewed as the
    quotient graph under the "in the same connected component" equivalence
    relation.

    """
    # This example graph comes from the file `test_strongly_connected.py`.
    G = nx.DiGraph()
    G.add_edges_from(
        [
            (1, 2),
            (2, 3),
            (2, 11),
            (2, 12),
            (3, 4),
            (4, 3),
            (4, 5),
            (5, 6),
            (6, 5),
            (6, 7),
            (7, 8),
            (7, 9),
            (7, 10),
            (8, 9),
            (9, 7),
            (10, 6),
            (11, 2),
            (11, 4),
            (11, 6),
            (12, 6),
            (12, 11),
        ]
    )
    scc = list(nx.strongly_connected_components(G))
    C = nx.condensation(G, scc)
    component_of = C.graph["mapping"]
    # Two nodes are equivalent if they are in the same connected component.

    def same_component(u, v):
        return component_of[u] == component_of[v]

    Q = nx.quotient_graph(G, same_component)
    assert nx.is_isomorphic(C, Q)


def test_path():
    G = nx.path_graph(6)
    partition = [{0, 1}, {2, 3}, {4, 5}]
    M = nx.quotient_graph(G, partition, relabel=True)
    assert nodes_equal(M, [0, 1, 2])
    assert edges_equal(M.edges(), [(0, 1), (1, 2)])
    for n in M:
        assert M.nodes[n]["nedges"] == 1
        assert M.nodes[n]["nnodes"] == 2
        assert M.nodes[n]["density"] == 1


def test_path__partition_provided_as_dict_of_lists():
    G = nx.path_graph(6)
    partition = {0: [0, 1], 2: [2, 3], 4: [4, 5]}
    M = nx.quotient_graph(G, partition, relabel=True)
    assert nodes_equal(M, [0, 1, 2])
    assert edges_equal(M.edges(), [(0, 1), (1, 2)])
    for n in M:
        assert M.nodes[n]["nedges"] == 1
        assert M.nodes[n]["nnodes"] == 2
        assert M.nodes[n]["density"] == 1


def test_path__partition_provided_as_dict_of_tuples():
    G = nx.path_graph(6)
    partition = {0: (0, 1), 2: (2, 3), 4: (4, 5)}
    M = nx.quotient_graph(G, partition, relabel=True)
    assert nodes_equal(M, [0, 1, 2])
    assert edges_equal(M.edges(), [(0, 1), (1, 2)])
    for n in M:
        assert M.nodes[n]["nedges"] == 1
        assert M.nodes[n]["nnodes"] == 2
        assert M.nodes[n]["density"] == 1


def test_path__partition_provided_as_dict_of_sets():
    G = nx.path_graph(6)
    partition = {0: {0, 1}, 2: {2, 3}, 4: {4, 5}}
    M = nx.quotient_graph(G, partition, relabel=True)
    assert nodes_equal(M, [0, 1, 2])
    assert edges_equal(M.edges(), [(0, 1), (1, 2)])
    for n in M:
        assert M.nodes[n]["nedges"] == 1
        assert M.nodes[n]["nnodes"] == 2
        assert M.nodes[n]["density"] == 1


def test_multigraph_path():
    G = nx.MultiGraph(nx.path_graph(6))
    partition = [{0, 1}, {2, 3}, {4, 5}]
    M = nx.quotient_graph(G, partition, relabel=True)
    assert nodes_equal(M, [0, 1, 2])
    assert edges_equal(M.edges(), [(0, 1), (1, 2)])
    for n in M:
        assert M.nodes[n]["nedges"] == 1
        assert M.nodes[n]["nnodes"] == 2
        assert M.nodes[n]["density"] == 1


def test_directed_path():
    G = nx.DiGraph()
    nx.add_path(G, range(6))
    partition = [{0, 1}, {2, 3}, {4, 5}]
    M = nx.quotient_graph(G, partition, relabel=True)
    assert nodes_equal(M, [0, 1, 2])
    assert edges_equal(M.edges(), [(0, 1), (1, 2)])
    for n in M:
        assert M.nodes[n]["nedges"] == 1
        assert M.nodes[n]["nnodes"] == 2
        assert M.nodes[n]["density"] == 0.5


def test_directed_multigraph_path():
    G = nx.MultiDiGraph()
    nx.add_path(G, range(6))
    partition = [{0, 1}, {2, 3}, {4, 5}]
    M = nx.quotient_graph(G, partition, relabel=True)
    assert nodes_equal(M, [0, 1, 2])
    assert edges_equal(M.edges(), [(0, 1), (1, 2)])
    for n in M:
        assert M.nodes[n]["nedges"] == 1
        assert M.nodes[n]["nnodes"] == 2
        assert M.nodes[n]["density"] == 0.5


def test_overlapping_blocks():
    with pytest.raises(nx.NetworkXException):
        G = nx.path_graph(6)
        partition = [{0, 1, 2}, {2, 3}, {4, 5}]
        nx.quotient_graph(G, partition)


def test_weighted_path():
    G = nx.path_graph(6)
    for i in range(5):
        G[i][i + 1]["w"] = i + 1
    partition = [{0, 1}, {2, 3}, {4, 5}]
    M = nx.quotient_graph(G, partition, weight="w", relabel=True)
    assert nodes_equal(M, [0, 1, 2])
    assert edges_equal(M.edges(), [(0, 1), (1, 2)])
    assert M[0][1]["weight"] == 2
    assert M[1][2]["weight"] == 4
    for n in M:
        assert M.nodes[n]["nedges"] == 1
        assert M.nodes[n]["nnodes"] == 2
        assert M.nodes[n]["density"] == 1


def test_barbell():
    G = nx.barbell_graph(3, 0)
    partition = [{0, 1, 2}, {3, 4, 5}]
    M = nx.quotient_graph(G, partition, relabel=True)
    assert nodes_equal(M, [0, 1])
    assert edges_equal(M.edges(), [(0, 1)])
    for n in M:
        assert M.nodes[n]["nedges"] == 3
        assert M.nodes[n]["nnodes"] == 3
        assert M.nodes[n]["density"] == 1


def test_barbell_plus():
    G = nx.barbell_graph(3, 0)
    # Add an extra edge joining the bells.
    G.add_edge(0, 5)
    partition = [{0, 1, 2}, {3, 4, 5}]
    M = nx.quotient_graph(G, partition, relabel=True)
    assert nodes_equal(M, [0, 1])
    assert edges_equal(M.edges(), [(0, 1)])
    assert M[0][1]["weight"] == 2
    for n in M:
        assert M.nodes[n]["nedges"] == 3
        assert M.nodes[n]["nnodes"] == 3
        assert M.nodes[n]["density"] == 1


def test_blockmodel():
    G = nx.path_graph(6)
    partition = [[0, 1], [2, 3], [4, 5]]
    M = nx.quotient_graph(G, partition, relabel=True)
    assert nodes_equal(M.nodes(), [0, 1, 2])
    assert edges_equal(M.edges(), [(0, 1), (1, 2)])
    for n in M.nodes():
        assert M.nodes[n]["nedges"] == 1
        assert M.nodes[n]["nnodes"] == 2
        assert M.nodes[n]["density"] == 1.0


def test_multigraph_blockmodel():
    G = nx.MultiGraph(nx.path_graph(6))
    partition = [[0, 1], [2, 3], [4, 5]]
    M = nx.quotient_graph(G, partition, create_using=nx.MultiGraph(), relabel=True)
    assert nodes_equal(M.nodes(), [0, 1, 2])
    assert edges_equal(M.edges(), [(0, 1), (1, 2)])
    for n in M.nodes():
        assert M.nodes[n]["nedges"] == 1
        assert M.nodes[n]["nnodes"] == 2
        assert M.nodes[n]["density"] == 1.0


def test_quotient_graph_incomplete_partition():
    G = nx.path_graph(6)
    partition = []
    H = nx.quotient_graph(G, partition, relabel=True)
    assert nodes_equal(H.nodes(), [])
    assert edges_equal(H.edges(), [])

    partition = [[0, 1], [2, 3], [5]]
    H = nx.quotient_graph(G, partition, relabel=True)
    assert nodes_equal(H.nodes(), [0, 1, 2])
    assert edges_equal(H.edges(), [(0, 1)])


def test_undirected_node_contraction():
    """Tests for node contraction in an undirected graph."""
    G = nx.cycle_graph(4)
    actual = nx.contracted_nodes(G, 0, 1)
    expected = nx.cycle_graph(3)
    expected.add_edge(0, 0)
    assert nx.is_isomorphic(actual, expected)


def test_directed_node_contraction():
    """Tests for node contraction in a directed graph."""
    G = nx.DiGraph(nx.cycle_graph(4))
    actual = nx.contracted_nodes(G, 0, 1)
    expected = nx.DiGraph(nx.cycle_graph(3))
    expected.add_edge(0, 0)
    expected.add_edge(0, 0)
    assert nx.is_isomorphic(actual, expected)


def test_undirected_node_contraction_no_copy():
    """Tests for node contraction in an undirected graph
    by making changes in place."""
    G = nx.cycle_graph(4)
    actual = nx.contracted_nodes(G, 0, 1, copy=False)
    expected = nx.cycle_graph(3)
    expected.add_edge(0, 0)
    assert nx.is_isomorphic(actual, G)
    assert nx.is_isomorphic(actual, expected)


def test_directed_node_contraction_no_copy():
    """Tests for node contraction in a directed graph
    by making changes in place."""
    G = nx.DiGraph(nx.cycle_graph(4))
    actual = nx.contracted_nodes(G, 0, 1, copy=False)
    expected = nx.DiGraph(nx.cycle_graph(3))
    expected.add_edge(0, 0)
    expected.add_edge(0, 0)
    assert nx.is_isomorphic(actual, G)
    assert nx.is_isomorphic(actual, expected)


def test_create_multigraph():
    """Tests that using a MultiGraph creates multiple edges."""
    G = nx.path_graph(3, create_using=nx.MultiGraph())
    G.add_edge(0, 1)
    G.add_edge(0, 0)
    G.add_edge(0, 2)
    actual = nx.contracted_nodes(G, 0, 2)
    expected = nx.MultiGraph()
    expected.add_edge(0, 1)
    expected.add_edge(0, 1)
    expected.add_edge(0, 1)
    expected.add_edge(0, 0)
    expected.add_edge(0, 0)
    assert edges_equal(actual.edges, expected.edges)


def test_multigraph_keys():
    """Tests that multiedge keys are reset in new graph."""
    G = nx.path_graph(3, create_using=nx.MultiGraph())
    G.add_edge(0, 1, 5)
    G.add_edge(0, 0, 0)
    G.add_edge(0, 2, 5)
    actual = nx.contracted_nodes(G, 0, 2)
    expected = nx.MultiGraph()
    expected.add_edge(0, 1, 0)
    expected.add_edge(0, 1, 5)
    expected.add_edge(0, 1, 2)  # keyed as 2 b/c 2 edges already in G
    expected.add_edge(0, 0, 0)
    expected.add_edge(0, 0, 1)  # this comes from (0, 2, 5)
    assert edges_equal(actual.edges, expected.edges)


def test_node_attributes():
    """Tests that node contraction preserves node attributes."""
    G = nx.cycle_graph(4)
    # Add some data to the two nodes being contracted.
    G.nodes[0]["foo"] = "bar"
    G.nodes[1]["baz"] = "xyzzy"
    actual = nx.contracted_nodes(G, 0, 1)
    # We expect that contracting the nodes 0 and 1 in C_4 yields K_3, but
    # with nodes labeled 0, 2, and 3, and with a -loop on 0.
    expected = nx.complete_graph(3)
    expected = nx.relabel_nodes(expected, {1: 2, 2: 3})
    expected.add_edge(0, 0)
    cdict = {1: {"baz": "xyzzy"}}
    expected.nodes[0].update({"foo": "bar", "contraction": cdict})
    assert nx.is_isomorphic(actual, expected)
    assert actual.nodes == expected.nodes


def test_edge_attributes():
    """Tests that node contraction preserves edge attributes."""
    # Shape: src1 --> dest <-- src2
    G = nx.DiGraph([("src1", "dest"), ("src2", "dest")])
    G["src1"]["dest"]["value"] = "src1-->dest"
    G["src2"]["dest"]["value"] = "src2-->dest"
    H = nx.MultiDiGraph(G)

    G = nx.contracted_nodes(G, "src1", "src2")  # New Shape: src1 --> dest
    assert G.edges[("src1", "dest")]["value"] == "src1-->dest"
    assert (
        G.edges[("src1", "dest")]["contraction"][("src2", "dest")]["value"]
        == "src2-->dest"
    )

    H = nx.contracted_nodes(H, "src1", "src2")  # New Shape: src1 -(x2)-> dest
    assert len(H.edges(("src1", "dest"))) == 2


def test_without_self_loops():
    """Tests for node contraction without preserving -loops."""
    G = nx.cycle_graph(4)
    actual = nx.contracted_nodes(G, 0, 1, self_loops=False)
    expected = nx.complete_graph(3)
    assert nx.is_isomorphic(actual, expected)


def test_contract_loop_graph():
    """Tests for node contraction when nodes have loops."""
    G = nx.cycle_graph(4)
    G.add_edge(0, 0)
    actual = nx.contracted_nodes(G, 0, 1)
    expected = nx.complete_graph([0, 2, 3])
    expected.add_edge(0, 0)
    expected.add_edge(0, 0)
    assert edges_equal(actual.edges, expected.edges)
    actual = nx.contracted_nodes(G, 1, 0)
    expected = nx.complete_graph([1, 2, 3])
    expected.add_edge(1, 1)
    expected.add_edge(1, 1)
    assert edges_equal(actual.edges, expected.edges)


def test_undirected_edge_contraction():
    """Tests for edge contraction in an undirected graph."""
    G = nx.cycle_graph(4)
    actual = nx.contracted_edge(G, (0, 1))
    expected = nx.complete_graph(3)
    expected.add_edge(0, 0)
    assert nx.is_isomorphic(actual, expected)


def test_multigraph_edge_contraction():
    """Tests for edge contraction in a multigraph"""
    G = nx.cycle_graph(4)
    actual = nx.contracted_edge(G, (0, 1, 0))
    expected = nx.complete_graph(3)
    expected.add_edge(0, 0)
    assert nx.is_isomorphic(actual, expected)


def test_nonexistent_edge():
    """Tests that attempting to contract a nonexistent edge raises an
    exception.

    """
    with pytest.raises(ValueError):
        G = nx.cycle_graph(4)
        nx.contracted_edge(G, (0, 2))
