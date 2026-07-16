import random

import pytest

import networkx as nx
from networkx import convert_node_labels_to_integers as cnlti
from networkx.algorithms.simple_paths import (
    _bidirectional_dijkstra,
    _bidirectional_shortest_path,
)
from networkx.utils import arbitrary_element, pairwise


class TestIsSimplePath:
    """Unit tests for the
    :func:`networkx.algorithms.simple_paths.is_simple_path` function.

    """

    def test_empty_list(self):
        """Tests that the empty list is not a valid path, since there
        should be a one-to-one correspondence between paths as lists of
        nodes and paths as lists of edges.

        """
        G = nx.trivial_graph()
        assert not nx.is_simple_path(G, [])

    def test_trivial_path(self):
        """Tests that the trivial path, a path of length one, is
        considered a simple path in a graph.

        """
        G = nx.trivial_graph()
        assert nx.is_simple_path(G, [0])

    def test_trivial_nonpath(self):
        """Tests that a list whose sole element is an object not in the
        graph is not considered a simple path.

        """
        G = nx.trivial_graph()
        assert not nx.is_simple_path(G, ["not a node"])

    def test_simple_path(self):
        G = nx.path_graph(2)
        assert nx.is_simple_path(G, [0, 1])

    def test_non_simple_path(self):
        G = nx.path_graph(2)
        assert not nx.is_simple_path(G, [0, 1, 0])

    def test_cycle(self):
        G = nx.cycle_graph(3)
        assert not nx.is_simple_path(G, [0, 1, 2, 0])

    def test_missing_node(self):
        G = nx.path_graph(2)
        assert not nx.is_simple_path(G, [0, 2])

    def test_missing_starting_node(self):
        G = nx.path_graph(2)
        assert not nx.is_simple_path(G, [2, 0])

    def test_directed_path(self):
        G = nx.DiGraph([(0, 1), (1, 2)])
        assert nx.is_simple_path(G, [0, 1, 2])

    def test_directed_non_path(self):
        G = nx.DiGraph([(0, 1), (1, 2)])
        assert not nx.is_simple_path(G, [2, 1, 0])

    def test_directed_cycle(self):
        G = nx.DiGraph([(0, 1), (1, 2), (2, 0)])
        assert not nx.is_simple_path(G, [0, 1, 2, 0])

    def test_multigraph(self):
        G = nx.MultiGraph([(0, 1), (0, 1)])
        assert nx.is_simple_path(G, [0, 1])

    def test_multidigraph(self):
        G = nx.MultiDiGraph([(0, 1), (0, 1), (1, 0), (1, 0)])
        assert nx.is_simple_path(G, [0, 1])


# Tests for all_simple_paths
def test_all_simple_paths():
    G = nx.path_graph(4)
    paths = nx.all_simple_paths(G, 0, 3)
    assert {tuple(p) for p in paths} == {(0, 1, 2, 3)}


def test_all_simple_paths_with_two_targets_emits_two_paths():
    G = nx.path_graph(4)
    G.add_edge(2, 4)
    paths = nx.all_simple_paths(G, 0, [3, 4])
    assert {tuple(p) for p in paths} == {(0, 1, 2, 3), (0, 1, 2, 4)}


def test_digraph_all_simple_paths_with_two_targets_emits_two_paths():
    G = nx.path_graph(4, create_using=nx.DiGraph())
    G.add_edge(2, 4)
    paths = nx.all_simple_paths(G, 0, [3, 4])
    assert {tuple(p) for p in paths} == {(0, 1, 2, 3), (0, 1, 2, 4)}


def test_all_simple_paths_with_two_targets_cutoff():
    G = nx.path_graph(4)
    G.add_edge(2, 4)
    paths = nx.all_simple_paths(G, 0, [3, 4], cutoff=3)
    assert {tuple(p) for p in paths} == {(0, 1, 2, 3), (0, 1, 2, 4)}


def test_digraph_all_simple_paths_with_two_targets_cutoff():
    G = nx.path_graph(4, create_using=nx.DiGraph())
    G.add_edge(2, 4)
    paths = nx.all_simple_paths(G, 0, [3, 4], cutoff=3)
    assert {tuple(p) for p in paths} == {(0, 1, 2, 3), (0, 1, 2, 4)}


def test_all_simple_paths_with_two_targets_in_line_emits_two_paths():
    G = nx.path_graph(4)
    paths = nx.all_simple_paths(G, 0, [2, 3])
    assert {tuple(p) for p in paths} == {(0, 1, 2), (0, 1, 2, 3)}


def test_all_simple_paths_ignores_cycle():
    G = nx.cycle_graph(3, create_using=nx.DiGraph())
    G.add_edge(1, 3)
    paths = nx.all_simple_paths(G, 0, 3)
    assert {tuple(p) for p in paths} == {(0, 1, 3)}


def test_all_simple_paths_with_two_targets_inside_cycle_emits_two_paths():
    G = nx.cycle_graph(3, create_using=nx.DiGraph())
    G.add_edge(1, 3)
    paths = nx.all_simple_paths(G, 0, [2, 3])
    assert {tuple(p) for p in paths} == {(0, 1, 2), (0, 1, 3)}


def test_all_simple_paths_source_target():
    G = nx.path_graph(4)
    assert list(nx.all_simple_paths(G, 1, 1)) == [[1]]


def test_all_simple_paths_cutoff():
    G = nx.complete_graph(4)
    paths = nx.all_simple_paths(G, 0, 1, cutoff=1)
    assert {tuple(p) for p in paths} == {(0, 1)}
    paths = nx.all_simple_paths(G, 0, 1, cutoff=2)
    assert {tuple(p) for p in paths} == {(0, 1), (0, 2, 1), (0, 3, 1)}


def test_all_simple_paths_on_non_trivial_graph():
    """you may need to draw this graph to make sure it is reasonable"""
    G = nx.path_graph(5, create_using=nx.DiGraph())
    G.add_edges_from([(0, 5), (1, 5), (1, 3), (5, 4), (4, 2), (4, 3)])
    paths = nx.all_simple_paths(G, 1, [2, 3])
    assert {tuple(p) for p in paths} == {
        (1, 2),
        (1, 3, 4, 2),
        (1, 5, 4, 2),
        (1, 3),
        (1, 2, 3),
        (1, 5, 4, 3),
        (1, 5, 4, 2, 3),
    }
    paths = nx.all_simple_paths(G, 1, [2, 3], cutoff=3)
    assert {tuple(p) for p in paths} == {
        (1, 2),
        (1, 3, 4, 2),
        (1, 5, 4, 2),
        (1, 3),
        (1, 2, 3),
        (1, 5, 4, 3),
    }
    paths = nx.all_simple_paths(G, 1, [2, 3], cutoff=2)
    assert {tuple(p) for p in paths} == {(1, 2), (1, 3), (1, 2, 3)}


def test_all_simple_paths_multigraph():
    G = nx.MultiGraph([(1, 2), (1, 2)])
    assert list(nx.all_simple_paths(G, 1, 1)) == [[1]]
    nx.add_path(G, [3, 1, 10, 2])
    paths = list(nx.all_simple_paths(G, 1, 2))
    assert len(paths) == 3
    assert {tuple(p) for p in paths} == {(1, 2), (1, 2), (1, 10, 2)}


def test_all_simple_paths_multigraph_with_cutoff():
    G = nx.MultiGraph([(1, 2), (1, 2), (1, 10), (10, 2)])
    paths = list(nx.all_simple_paths(G, 1, 2, cutoff=1))
    assert len(paths) == 2
    assert {tuple(p) for p in paths} == {(1, 2), (1, 2)}

    # See GitHub issue #6732.
    G = nx.MultiGraph([(0, 1), (0, 2)])
    assert list(nx.all_simple_paths(G, 0, {1, 2}, cutoff=1)) == [[0, 1], [0, 2]]


def test_all_simple_paths_directed():
    G = nx.DiGraph()
    nx.add_path(G, [1, 2, 3])
    nx.add_path(G, [3, 2, 1])
    paths = nx.all_simple_paths(G, 1, 3)
    assert {tuple(p) for p in paths} == {(1, 2, 3)}


def test_all_simple_paths_empty():
    G = nx.path_graph(4)
    paths = nx.all_simple_paths(G, 0, 3, cutoff=2)
    assert list(paths) == []


def test_all_simple_paths_corner_cases():
    assert list(nx.all_simple_paths(nx.empty_graph(2), 0, 0)) == [[0]]
    assert list(nx.all_simple_paths(nx.empty_graph(2), 0, 1)) == []
    assert list(nx.all_simple_paths(nx.path_graph(9), 0, 8, 0)) == []


def test_all_simple_paths_source_in_targets():
    # See GitHub issue #6690.
    G = nx.path_graph(3)
    assert list(nx.all_simple_paths(G, 0, {0, 1, 2})) == [[0], [0, 1], [0, 1, 2]]


def hamiltonian_path(G, source):
    source = arbitrary_element(G)
    neighbors = set(G[source]) - {source}
    n = len(G)
    for target in neighbors:
        for path in nx.all_simple_paths(G, source, target):
            if len(path) == n:
                yield path


def test_hamiltonian_path():
    from itertools import permutations

    G = nx.complete_graph(4)
    paths = [list(p) for p in hamiltonian_path(G, 0)]
    exact = [[0] + list(p) for p in permutations([1, 2, 3], 3)]
    assert sorted(paths) == sorted(exact)


def test_cutoff_zero():
    G = nx.complete_graph(4)
    paths = nx.all_simple_paths(G, 0, 3, cutoff=0)
    assert [list(p) for p in paths] == []
    paths = nx.all_simple_paths(nx.MultiGraph(G), 0, 3, cutoff=0)
    assert [list(p) for p in paths] == []


def test_source_missing():
    with pytest.raises(nx.NodeNotFound):
        G = nx.Graph()
        nx.add_path(G, [1, 2, 3])
        list(nx.all_simple_paths(nx.MultiGraph(G), 0, 3))


def test_target_missing():
    with pytest.raises(nx.NodeNotFound):
        G = nx.Graph()
        nx.add_path(G, [1, 2, 3])
        list(nx.all_simple_paths(nx.MultiGraph(G), 1, 4))


# Tests for all_simple_edge_paths
def test_all_simple_edge_paths():
    G = nx.path_graph(4)
    paths = nx.all_simple_edge_paths(G, 0, 3)
    assert {tuple(p) for p in paths} == {((0, 1), (1, 2), (2, 3))}


def test_all_simple_edge_paths_empty_path():
    G = nx.empty_graph(1)
    assert list(nx.all_simple_edge_paths(G, 0, 0)) == [[]]


def test_all_simple_edge_paths_with_two_targets_emits_two_paths():
    G = nx.path_graph(4)
    G.add_edge(2, 4)
    paths = nx.all_simple_edge_paths(G, 0, [3, 4])
    assert {tuple(p) for p in paths} == {
        ((0, 1), (1, 2), (2, 3)),
        ((0, 1), (1, 2), (2, 4)),
    }


def test_digraph_all_simple_edge_paths_with_two_targets_emits_two_paths():
    G = nx.path_graph(4, create_using=nx.DiGraph())
    G.add_edge(2, 4)
    paths = nx.all_simple_edge_paths(G, 0, [3, 4])
    assert {tuple(p) for p in paths} == {
        ((0, 1), (1, 2), (2, 3)),
        ((0, 1), (1, 2), (2, 4)),
    }


def test_all_simple_edge_paths_with_two_targets_cutoff():
    G = nx.path_graph(4)
    G.add_edge(2, 4)
    paths = nx.all_simple_edge_paths(G, 0, [3, 4], cutoff=3)
    assert {tuple(p) for p in paths} == {
        ((0, 1), (1, 2), (2, 3)),
        ((0, 1), (1, 2), (2, 4)),
    }


def test_digraph_all_simple_edge_paths_with_two_targets_cutoff():
    G = nx.path_graph(4, create_using=nx.DiGraph())
    G.add_edge(2, 4)
    paths = nx.all_simple_edge_paths(G, 0, [3, 4], cutoff=3)
    assert {tuple(p) for p in paths} == {
        ((0, 1), (1, 2), (2, 3)),
        ((0, 1), (1, 2), (2, 4)),
    }


def test_all_simple_edge_paths_with_two_targets_in_line_emits_two_paths():
    G = nx.path_graph(4)
    paths = nx.all_simple_edge_paths(G, 0, [2, 3])
    assert {tuple(p) for p in paths} == {((0, 1), (1, 2)), ((0, 1), (1, 2), (2, 3))}


def test_all_simple_edge_paths_ignores_cycle():
    G = nx.cycle_graph(3, create_using=nx.DiGraph())
    G.add_edge(1, 3)
    paths = nx.all_simple_edge_paths(G, 0, 3)
    assert {tuple(p) for p in paths} == {((0, 1), (1, 3))}


def test_all_simple_edge_paths_with_two_targets_inside_cycle_emits_two_paths():
    G = nx.cycle_graph(3, create_using=nx.DiGraph())
    G.add_edge(1, 3)
    paths = nx.all_simple_edge_paths(G, 0, [2, 3])
    assert {tuple(p) for p in paths} == {((0, 1), (1, 2)), ((0, 1), (1, 3))}


def test_all_simple_edge_paths_source_target():
    G = nx.path_graph(4)
    paths = nx.all_simple_edge_paths(G, 1, 1)
    assert list(paths) == [[]]


def test_all_simple_edge_paths_cutoff():
    G = nx.complete_graph(4)
    paths = nx.all_simple_edge_paths(G, 0, 1, cutoff=1)
    assert {tuple(p) for p in paths} == {((0, 1),)}
    paths = nx.all_simple_edge_paths(G, 0, 1, cutoff=2)
    assert {tuple(p) for p in paths} == {((0, 1),), ((0, 2), (2, 1)), ((0, 3), (3, 1))}


def test_all_simple_edge_paths_on_non_trivial_graph():
    """you may need to draw this graph to make sure it is reasonable"""
    G = nx.path_graph(5, create_using=nx.DiGraph())
    G.add_edges_from([(0, 5), (1, 5), (1, 3), (5, 4), (4, 2), (4, 3)])
    paths = nx.all_simple_edge_paths(G, 1, [2, 3])
    assert {tuple(p) for p in paths} == {
        ((1, 2),),
        ((1, 3), (3, 4), (4, 2)),
        ((1, 5), (5, 4), (4, 2)),
        ((1, 3),),
        ((1, 2), (2, 3)),
        ((1, 5), (5, 4), (4, 3)),
        ((1, 5), (5, 4), (4, 2), (2, 3)),
    }
    paths = nx.all_simple_edge_paths(G, 1, [2, 3], cutoff=3)
    assert {tuple(p) for p in paths} == {
        ((1, 2),),
        ((1, 3), (3, 4), (4, 2)),
        ((1, 5), (5, 4), (4, 2)),
        ((1, 3),),
        ((1, 2), (2, 3)),
        ((1, 5), (5, 4), (4, 3)),
    }
    paths = nx.all_simple_edge_paths(G, 1, [2, 3], cutoff=2)
    assert {tuple(p) for p in paths} == {((1, 2),), ((1, 3),), ((1, 2), (2, 3))}


def test_all_simple_edge_paths_multigraph():
    G = nx.MultiGraph([(1, 2), (1, 2)])
    paths = nx.all_simple_edge_paths(G, 1, 1)
    assert list(paths) == [[]]
    nx.add_path(G, [3, 1, 10, 2])
    paths = list(nx.all_simple_edge_paths(G, 1, 2))
    assert len(paths) == 3
    assert {tuple(p) for p in paths} == {
        ((1, 2, 0),),
        ((1, 2, 1),),
        ((1, 10, 0), (10, 2, 0)),
    }


def test_all_simple_edge_paths_multigraph_with_cutoff():
    G = nx.MultiGraph([(1, 2), (1, 2), (1, 10), (10, 2)])
    paths = list(nx.all_simple_edge_paths(G, 1, 2, cutoff=1))
    assert len(paths) == 2
    assert {tuple(p) for p in paths} == {((1, 2, 0),), ((1, 2, 1),)}


def test_all_simple_edge_paths_directed():
    G = nx.DiGraph()
    nx.add_path(G, [1, 2, 3])
    nx.add_path(G, [3, 2, 1])
    paths = nx.all_simple_edge_paths(G, 1, 3)
    assert {tuple(p) for p in paths} == {((1, 2), (2, 3))}


def test_all_simple_edge_paths_empty():
    G = nx.path_graph(4)
    paths = nx.all_simple_edge_paths(G, 0, 3, cutoff=2)
    assert list(paths) == []


def test_all_simple_edge_paths_corner_cases():
    assert list(nx.all_simple_edge_paths(nx.empty_graph(2), 0, 0)) == [[]]
    assert list(nx.all_simple_edge_paths(nx.empty_graph(2), 0, 1)) == []
    assert list(nx.all_simple_edge_paths(nx.path_graph(9), 0, 8, 0)) == []


def test_all_simple_edge_paths_ignores_self_loop():
    G = nx.Graph([(0, 0), (0, 1), (1, 1), (1, 2)])
    assert list(nx.all_simple_edge_paths(G, 0, 2)) == [[(0, 1), (1, 2)]]


def hamiltonian_edge_path(G, source):
    source = arbitrary_element(G)
    neighbors = set(G[source]) - {source}
    n = len(G)
    for target in neighbors:
        for path in nx.all_simple_edge_paths(G, source, target):
            if len(path) == n - 1:
                yield path


def test_hamiltonian__edge_path():
    from itertools import permutations

    G = nx.complete_graph(4)
    paths = hamiltonian_edge_path(G, 0)
    exact = [list(pairwise([0] + list(p))) for p in permutations([1, 2, 3], 3)]
    assert sorted(exact) == sorted(paths)


def test_edge_cutoff_zero():
    G = nx.complete_graph(4)
    paths = nx.all_simple_edge_paths(G, 0, 3, cutoff=0)
    assert [list(p) for p in paths] == []
    paths = nx.all_simple_edge_paths(nx.MultiGraph(G), 0, 3, cutoff=0)
    assert [list(p) for p in paths] == []


def test_edge_source_missing():
    with pytest.raises(nx.NodeNotFound):
        G = nx.Graph()
        nx.add_path(G, [1, 2, 3])
        list(nx.all_simple_edge_paths(nx.MultiGraph(G), 0, 3))


def test_edge_target_missing():
    with pytest.raises(nx.NodeNotFound):
        G = nx.Graph()
        nx.add_path(G, [1, 2, 3])
        list(nx.all_simple_edge_paths(nx.MultiGraph(G), 1, 4))


# Tests for shortest_simple_paths
def test_shortest_simple_paths():
    G = cnlti(nx.grid_2d_graph(4, 4), first_label=1, ordering="sorted")
    paths = nx.shortest_simple_paths(G, 1, 12)
    assert next(paths) == [1, 2, 3, 4, 8, 12]
    assert next(paths) == [1, 5, 6, 7, 8, 12]
    assert [len(path) for path in nx.shortest_simple_paths(G, 1, 12)] == sorted(
        len(path) for path in nx.all_simple_paths(G, 1, 12)
    )


def test_shortest_simple_paths_singleton_path():
    G = nx.empty_graph(3)
    assert list(nx.shortest_simple_paths(G, 0, 0)) == [[0]]


def test_shortest_simple_paths_directed():
    G = nx.cycle_graph(7, create_using=nx.DiGraph())
    paths = nx.shortest_simple_paths(G, 0, 3)
    assert list(paths) == [[0, 1, 2, 3]]


def test_shortest_simple_paths_directed_with_weight_function():
    def cost(u, v, x):
        return 1

    G = cnlti(nx.grid_2d_graph(4, 4), first_label=1, ordering="sorted")
    paths = nx.shortest_simple_paths(G, 1, 12)
    assert next(paths) == [1, 2, 3, 4, 8, 12]
    assert next(paths) == [1, 5, 6, 7, 8, 12]
    assert [
        len(path) for path in nx.shortest_simple_paths(G, 1, 12, weight=cost)
    ] == sorted(len(path) for path in nx.all_simple_paths(G, 1, 12))


def test_shortest_simple_paths_with_weight_function():
    def cost(u, v, x):
        return 1

    G = nx.cycle_graph(7, create_using=nx.DiGraph())
    paths = nx.shortest_simple_paths(G, 0, 3, weight=cost)
    assert list(paths) == [[0, 1, 2, 3]]


def test_shortest_simple_paths_with_none_weight_function():
    def cost(u, v, x):
        delta = abs(u - v)
        # ignore interior edges
        return 1 if (delta == 1 or delta == 4) else None

    G = nx.complete_graph(5)
    paths = nx.shortest_simple_paths(G, 0, 2, weight=cost)
    assert list(paths) == [[0, 1, 2], [0, 4, 3, 2]]


def test_Greg_Bernstein():
    g1 = nx.Graph()
    g1.add_nodes_from(["N0", "N1", "N2", "N3", "N4"])
    g1.add_edge("N4", "N1", weight=10.0, capacity=50, name="L5")
    g1.add_edge("N4", "N0", weight=7.0, capacity=40, name="L4")
    g1.add_edge("N0", "N1", weight=10.0, capacity=45, name="L1")
    g1.add_edge("N3", "N0", weight=10.0, capacity=50, name="L0")
    g1.add_edge("N2", "N3", weight=12.0, capacity=30, name="L2")
    g1.add_edge("N1", "N2", weight=15.0, capacity=42, name="L3")
    solution = [["N1", "N0", "N3"], ["N1", "N2", "N3"], ["N1", "N4", "N0", "N3"]]
    result = list(nx.shortest_simple_paths(g1, "N1", "N3", weight="weight"))
    assert result == solution


def test_weighted_shortest_simple_path():
    def cost_func(path):
        return sum(G.adj[u][v]["weight"] for (u, v) in zip(path, path[1:]))

    G = nx.complete_graph(5)
    weight = {(u, v): random.randint(1, 100) for (u, v) in G.edges()}
    nx.set_edge_attributes(G, weight, "weight")
    cost = 0
    for path in nx.shortest_simple_paths(G, 0, 3, weight="weight"):
        this_cost = cost_func(path)
        assert cost <= this_cost
        cost = this_cost


def test_directed_weighted_shortest_simple_path():
    def cost_func(path):
        return sum(G.adj[u][v]["weight"] for (u, v) in zip(path, path[1:]))

    G = nx.complete_graph(5)
    G = G.to_directed()
    weight = {(u, v): random.randint(1, 100) for (u, v) in G.edges()}
    nx.set_edge_attributes(G, weight, "weight")
    cost = 0
    for path in nx.shortest_simple_paths(G, 0, 3, weight="weight"):
        this_cost = cost_func(path)
        assert cost <= this_cost
        cost = this_cost


def test_weighted_shortest_simple_path_issue2427():
    G = nx.Graph()
    G.add_edge("IN", "OUT", weight=2)
    G.add_edge("IN", "A", weight=1)
    G.add_edge("IN", "B", weight=2)
    G.add_edge("B", "OUT", weight=2)
    assert list(nx.shortest_simple_paths(G, "IN", "OUT", weight="weight")) == [
        ["IN", "OUT"],
        ["IN", "B", "OUT"],
    ]
    G = nx.Graph()
    G.add_edge("IN", "OUT", weight=10)
    G.add_edge("IN", "A", weight=1)
    G.add_edge("IN", "B", weight=1)
    G.add_edge("B", "OUT", weight=1)
    assert list(nx.shortest_simple_paths(G, "IN", "OUT", weight="weight")) == [
        ["IN", "B", "OUT"],
        ["IN", "OUT"],
    ]


def test_directed_weighted_shortest_simple_path_issue2427():
    G = nx.DiGraph()
    G.add_edge("IN", "OUT", weight=2)
    G.add_edge("IN", "A", weight=1)
    G.add_edge("IN", "B", weight=2)
    G.add_edge("B", "OUT", weight=2)
    assert list(nx.shortest_simple_paths(G, "IN", "OUT", weight="weight")) == [
        ["IN", "OUT"],
        ["IN", "B", "OUT"],
    ]
    G = nx.DiGraph()
    G.add_edge("IN", "OUT", weight=10)
    G.add_edge("IN", "A", weight=1)
    G.add_edge("IN", "B", weight=1)
    G.add_edge("B", "OUT", weight=1)
    assert list(nx.shortest_simple_paths(G, "IN", "OUT", weight="weight")) == [
        ["IN", "B", "OUT"],
        ["IN", "OUT"],
    ]


def test_weight_name():
    G = nx.cycle_graph(7)
    nx.set_edge_attributes(G, 1, "weight")
    nx.set_edge_attributes(G, 1, "foo")
    G.adj[1][2]["foo"] = 7
    paths = list(nx.shortest_simple_paths(G, 0, 3, weight="foo"))
    solution = [[0, 6, 5, 4, 3], [0, 1, 2, 3]]
    assert paths == solution


def test_ssp_source_missing():
    with pytest.raises(nx.NodeNotFound):
        G = nx.Graph()
        nx.add_path(G, [1, 2, 3])
        list(nx.shortest_simple_paths(G, 0, 3))


def test_ssp_target_missing():
    with pytest.raises(nx.NodeNotFound):
        G = nx.Graph()
        nx.add_path(G, [1, 2, 3])
        list(nx.shortest_simple_paths(G, 1, 4))


def test_ssp_multigraph():
    with pytest.raises(nx.NetworkXNotImplemented):
        G = nx.MultiGraph()
        nx.add_path(G, [1, 2, 3])
        list(nx.shortest_simple_paths(G, 1, 4))


def test_ssp_source_missing2():
    with pytest.raises(nx.NetworkXNoPath):
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2])
        nx.add_path(G, [3, 4, 5])
        list(nx.shortest_simple_paths(G, 0, 3))


def test_bidirectional_shortest_path_restricted_cycle():
    cycle = nx.cycle_graph(7)
    length, path = _bidirectional_shortest_path(cycle, 0, 3)
    assert path == [0, 1, 2, 3]
    length, path = _bidirectional_shortest_path(cycle, 0, 3, ignore_nodes=[1])
    assert path == [0, 6, 5, 4, 3]


def test_bidirectional_shortest_path_restricted_wheel():
    wheel = nx.wheel_graph(6)
    length, path = _bidirectional_shortest_path(wheel, 1, 3)
    assert path in [[1, 0, 3], [1, 2, 3]]
    length, path = _bidirectional_shortest_path(wheel, 1, 3, ignore_nodes=[0])
    assert path == [1, 2, 3]
    length, path = _bidirectional_shortest_path(wheel, 1, 3, ignore_nodes=[0, 2])
    assert path == [1, 5, 4, 3]
    length, path = _bidirectional_shortest_path(
        wheel, 1, 3, ignore_edges=[(1, 0), (5, 0), (2, 3)]
    )
    assert path in [[1, 2, 0, 3], [1, 5, 4, 3]]


def test_bidirectional_shortest_path_restricted_directed_cycle():
    directed_cycle = nx.cycle_graph(7, create_using=nx.DiGraph())
    length, path = _bidirectional_shortest_path(directed_cycle, 0, 3)
    assert path == [0, 1, 2, 3]
    pytest.raises(
        nx.NetworkXNoPath,
        _bidirectional_shortest_path,
        directed_cycle,
        0,
        3,
        ignore_nodes=[1],
    )
    length, path = _bidirectional_shortest_path(
        directed_cycle, 0, 3, ignore_edges=[(2, 1)]
    )
    assert path == [0, 1, 2, 3]
    pytest.raises(
        nx.NetworkXNoPath,
        _bidirectional_shortest_path,
        directed_cycle,
        0,
        3,
        ignore_edges=[(1, 2)],
    )


def test_bidirectional_shortest_path_ignore():
    G = nx.Graph()
    nx.add_path(G, [1, 2])
    nx.add_path(G, [1, 3])
    nx.add_path(G, [1, 4])
    pytest.raises(
        nx.NetworkXNoPath, _bidirectional_shortest_path, G, 1, 2, ignore_nodes=[1]
    )
    pytest.raises(
        nx.NetworkXNoPath, _bidirectional_shortest_path, G, 1, 2, ignore_nodes=[2]
    )
    G = nx.Graph()
    nx.add_path(G, [1, 3])
    nx.add_path(G, [1, 4])
    nx.add_path(G, [3, 2])
    pytest.raises(
        nx.NetworkXNoPath, _bidirectional_shortest_path, G, 1, 2, ignore_nodes=[1, 2]
    )


def validate_path(G, s, t, soln_len, path):
    assert path[0] == s
    assert path[-1] == t
    assert soln_len == sum(
        G[u][v].get("weight", 1) for u, v in zip(path[:-1], path[1:])
    )


def validate_length_path(G, s, t, soln_len, length, path):
    assert soln_len == length
    validate_path(G, s, t, length, path)


def test_bidirectional_dijkstra_restricted():
    XG = nx.DiGraph()
    XG.add_weighted_edges_from(
        [
            ("s", "u", 10),
            ("s", "x", 5),
            ("u", "v", 1),
            ("u", "x", 2),
            ("v", "y", 1),
            ("x", "u", 3),
            ("x", "v", 5),
            ("x", "y", 2),
            ("y", "s", 7),
            ("y", "v", 6),
        ]
    )

    XG3 = nx.Graph()
    XG3.add_weighted_edges_from(
        [[0, 1, 2], [1, 2, 12], [2, 3, 1], [3, 4, 5], [4, 5, 1], [5, 0, 10]]
    )
    validate_length_path(XG, "s", "v", 9, *_bidirectional_dijkstra(XG, "s", "v"))
    validate_length_path(
        XG, "s", "v", 10, *_bidirectional_dijkstra(XG, "s", "v", ignore_nodes=["u"])
    )
    validate_length_path(
        XG,
        "s",
        "v",
        11,
        *_bidirectional_dijkstra(XG, "s", "v", ignore_edges=[("s", "x")]),
    )
    pytest.raises(
        nx.NetworkXNoPath,
        _bidirectional_dijkstra,
        XG,
        "s",
        "v",
        ignore_nodes=["u"],
        ignore_edges=[("s", "x")],
    )
    validate_length_path(XG3, 0, 3, 15, *_bidirectional_dijkstra(XG3, 0, 3))
    validate_length_path(
        XG3, 0, 3, 16, *_bidirectional_dijkstra(XG3, 0, 3, ignore_nodes=[1])
    )
    validate_length_path(
        XG3, 0, 3, 16, *_bidirectional_dijkstra(XG3, 0, 3, ignore_edges=[(2, 3)])
    )
    pytest.raises(
        nx.NetworkXNoPath,
        _bidirectional_dijkstra,
        XG3,
        0,
        3,
        ignore_nodes=[1],
        ignore_edges=[(5, 4)],
    )


def test_bidirectional_dijkstra_no_path():
    with pytest.raises(nx.NetworkXNoPath):
        G = nx.Graph()
        nx.add_path(G, [1, 2, 3])
        nx.add_path(G, [4, 5, 6])
        _bidirectional_dijkstra(G, 1, 6)


def test_bidirectional_dijkstra_ignore():
    G = nx.Graph()
    nx.add_path(G, [1, 2, 10])
    nx.add_path(G, [1, 3, 10])
    pytest.raises(nx.NetworkXNoPath, _bidirectional_dijkstra, G, 1, 2, ignore_nodes=[1])
    pytest.raises(nx.NetworkXNoPath, _bidirectional_dijkstra, G, 1, 2, ignore_nodes=[2])
    pytest.raises(
        nx.NetworkXNoPath, _bidirectional_dijkstra, G, 1, 2, ignore_nodes=[1, 2]
    )
