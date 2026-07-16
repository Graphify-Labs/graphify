import random

import pytest

import networkx as nx
from networkx.algorithms.approximation import maxcut


@pytest.mark.parametrize(
    "f", (nx.approximation.randomized_partitioning, nx.approximation.one_exchange)
)
@pytest.mark.parametrize("graph_constructor", (nx.DiGraph, nx.MultiGraph))
def test_raises_on_directed_and_multigraphs(f, graph_constructor):
    G = graph_constructor([(0, 1), (1, 2)])
    with pytest.raises(nx.NetworkXNotImplemented):
        f(G)


def _is_valid_cut(G, set1, set2):
    union = set1.union(set2)
    assert union == set(G.nodes)
    assert len(set1) + len(set2) == G.number_of_nodes()


def _cut_is_locally_optimal(G, cut_size, set1):
    # test if cut can be locally improved
    for i, node in enumerate(set1):
        cut_size_without_node = nx.algorithms.cut_size(
            G, set1 - {node}, weight="weight"
        )
        assert cut_size_without_node <= cut_size


def test_random_partitioning():
    G = nx.complete_graph(5)
    _, (set1, set2) = maxcut.randomized_partitioning(G, seed=5)
    _is_valid_cut(G, set1, set2)


def test_random_partitioning_all_to_one():
    G = nx.complete_graph(5)
    _, (set1, set2) = maxcut.randomized_partitioning(G, p=1)
    _is_valid_cut(G, set1, set2)
    assert len(set1) == G.number_of_nodes()
    assert len(set2) == 0


def test_one_exchange_basic():
    G = nx.complete_graph(5)
    random.seed(5)
    for u, v, w in G.edges(data=True):
        w["weight"] = random.randrange(-100, 100, 1) / 10

    initial_cut = set(random.sample(sorted(G.nodes()), k=5))
    cut_size, (set1, set2) = maxcut.one_exchange(
        G, initial_cut, weight="weight", seed=5
    )

    _is_valid_cut(G, set1, set2)
    _cut_is_locally_optimal(G, cut_size, set1)


def test_one_exchange_optimal():
    # Greedy one exchange should find the optimal solution for this graph (14)
    G = nx.Graph()
    G.add_edge(1, 2, weight=3)
    G.add_edge(1, 3, weight=3)
    G.add_edge(1, 4, weight=3)
    G.add_edge(1, 5, weight=3)
    G.add_edge(2, 3, weight=5)

    cut_size, (set1, set2) = maxcut.one_exchange(G, weight="weight", seed=5)

    _is_valid_cut(G, set1, set2)
    _cut_is_locally_optimal(G, cut_size, set1)
    # check global optimality
    assert cut_size == 14


def test_negative_weights():
    G = nx.complete_graph(5)
    random.seed(5)
    for u, v, w in G.edges(data=True):
        w["weight"] = -1 * random.random()

    initial_cut = set(random.sample(sorted(G.nodes()), k=5))
    cut_size, (set1, set2) = maxcut.one_exchange(G, initial_cut, weight="weight")

    # make sure it is a valid cut
    _is_valid_cut(G, set1, set2)
    # check local optimality
    _cut_is_locally_optimal(G, cut_size, set1)
    # test that all nodes are in the same partition
    assert len(set1) == len(G.nodes) or len(set2) == len(G.nodes)
