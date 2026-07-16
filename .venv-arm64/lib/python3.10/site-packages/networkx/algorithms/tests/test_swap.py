import pytest

import networkx as nx

cycle = nx.cycle_graph(5, create_using=nx.DiGraph)
tree = nx.DiGraph()
tree.add_edges_from(nx.random_labeled_tree(10, seed=42).edges)
path = nx.path_graph(5, create_using=nx.DiGraph)
binomial = nx.binomial_tree(3, create_using=nx.DiGraph)
HH = nx.directed_havel_hakimi_graph([1, 2, 1, 2, 2, 2], [3, 1, 0, 1, 2, 3])
balanced_tree = nx.balanced_tree(2, 3, create_using=nx.DiGraph)


@pytest.mark.parametrize("G", [path, binomial, HH, cycle, tree, balanced_tree])
def test_directed_edge_swap(G):
    in_degree = set(G.in_degree)
    out_degree = set(G.out_degree)
    edges = set(G.edges)
    nx.directed_edge_swap(G, nswap=1, max_tries=100, seed=1)
    assert in_degree == set(G.in_degree)
    assert out_degree == set(G.out_degree)
    assert edges != set(G.edges)
    assert 3 == sum(e not in edges for e in G.edges)


def test_directed_edge_swap_undo_previous_swap():
    G = nx.DiGraph(nx.path_graph(4).edges)  # only 1 swap possible
    edges = set(G.edges)
    nx.directed_edge_swap(G, nswap=2, max_tries=100)
    assert edges == set(G.edges)

    nx.directed_edge_swap(G, nswap=1, max_tries=100, seed=1)
    assert {(0, 2), (1, 3), (2, 1)} == set(G.edges)
    nx.directed_edge_swap(G, nswap=1, max_tries=100, seed=1)
    assert edges == set(G.edges)


def test_edge_cases_directed_edge_swap():
    # Tests cases when swaps are impossible, either too few edges exist, or self loops/cycles are unavoidable
    # TODO: Rewrite function to explicitly check for impossible swaps and raise error
    e = (
        "Maximum number of swap attempts \\(11\\) exceeded "
        "before desired swaps achieved \\(\\d\\)."
    )
    graph = nx.DiGraph([(0, 0), (0, 1), (1, 0), (2, 3), (3, 2)])
    with pytest.raises(nx.NetworkXAlgorithmError, match=e):
        nx.directed_edge_swap(graph, nswap=1, max_tries=10, seed=1)


def test_double_edge_swap():
    graph = nx.barabasi_albert_graph(200, 1)
    degrees = sorted(d for n, d in graph.degree())
    G = nx.double_edge_swap(graph, 40)
    assert degrees == sorted(d for n, d in graph.degree())


def test_double_edge_swap_seed():
    graph = nx.barabasi_albert_graph(200, 1)
    degrees = sorted(d for n, d in graph.degree())
    G = nx.double_edge_swap(graph, 40, seed=1)
    assert degrees == sorted(d for n, d in graph.degree())


def test_connected_double_edge_swap():
    graph = nx.barabasi_albert_graph(200, 1)
    degrees = sorted(d for n, d in graph.degree())
    G = nx.connected_double_edge_swap(graph, 40, seed=1)
    assert nx.is_connected(graph)
    assert degrees == sorted(d for n, d in graph.degree())


def test_connected_double_edge_swap_low_window_threshold():
    graph = nx.barabasi_albert_graph(200, 1)
    degrees = sorted(d for n, d in graph.degree())
    G = nx.connected_double_edge_swap(graph, 40, _window_threshold=0, seed=1)
    assert nx.is_connected(graph)
    assert degrees == sorted(d for n, d in graph.degree())


def test_connected_double_edge_swap_star():
    # Testing ui==xi in connected_double_edge_swap
    graph = nx.star_graph(40)
    degrees = sorted(d for n, d in graph.degree())
    G = nx.connected_double_edge_swap(graph, 1, seed=4)
    assert nx.is_connected(graph)
    assert degrees == sorted(d for n, d in graph.degree())


def test_connected_double_edge_swap_star_low_window_threshold():
    # Testing ui==xi in connected_double_edge_swap with low window threshold
    graph = nx.star_graph(40)
    degrees = sorted(d for n, d in graph.degree())
    G = nx.connected_double_edge_swap(graph, 1, _window_threshold=0, seed=4)
    assert nx.is_connected(graph)
    assert degrees == sorted(d for n, d in graph.degree())


def test_directed_edge_swap_small():
    with pytest.raises(nx.NetworkXError):
        G = nx.directed_edge_swap(nx.path_graph(3, create_using=nx.DiGraph))


def test_directed_edge_swap_tries():
    with pytest.raises(nx.NetworkXError):
        G = nx.directed_edge_swap(
            nx.path_graph(3, create_using=nx.DiGraph), nswap=1, max_tries=0
        )


def test_directed_exception_undirected():
    graph = nx.Graph([(0, 1), (2, 3)])
    with pytest.raises(nx.NetworkXNotImplemented):
        G = nx.directed_edge_swap(graph)


def test_directed_edge_max_tries():
    with pytest.raises(nx.NetworkXAlgorithmError):
        G = nx.directed_edge_swap(
            nx.complete_graph(4, nx.DiGraph()), nswap=1, max_tries=5
        )


def test_double_edge_swap_small():
    with pytest.raises(nx.NetworkXError):
        G = nx.double_edge_swap(nx.path_graph(3))


def test_double_edge_swap_tries():
    with pytest.raises(nx.NetworkXError):
        G = nx.double_edge_swap(nx.path_graph(10), nswap=1, max_tries=0)


def test_double_edge_directed():
    graph = nx.DiGraph([(0, 1), (2, 3)])
    with pytest.raises(nx.NetworkXError, match="not defined for directed graphs."):
        G = nx.double_edge_swap(graph)


def test_double_edge_max_tries():
    with pytest.raises(nx.NetworkXAlgorithmError):
        G = nx.double_edge_swap(nx.complete_graph(4), nswap=1, max_tries=5)


def test_connected_double_edge_swap_small():
    with pytest.raises(nx.NetworkXError):
        G = nx.connected_double_edge_swap(nx.path_graph(3))


def test_connected_double_edge_swap_not_connected():
    with pytest.raises(nx.NetworkXError):
        G = nx.path_graph(3)
        nx.add_path(G, [10, 11, 12])
        G = nx.connected_double_edge_swap(G)


def test_degree_seq_c4():
    G = nx.cycle_graph(4)
    degrees = sorted(d for n, d in G.degree())
    G = nx.double_edge_swap(G, 1, 100)
    assert degrees == sorted(d for n, d in G.degree())


def test_fewer_than_4_nodes():
    G = nx.DiGraph()
    G.add_nodes_from([0, 1, 2])
    with pytest.raises(nx.NetworkXError, match=".*fewer than four nodes."):
        nx.directed_edge_swap(G)


def test_less_than_3_edges():
    G = nx.DiGraph([(0, 1), (1, 2)])
    G.add_nodes_from([3, 4])
    with pytest.raises(nx.NetworkXError, match=".*fewer than 3 edges"):
        nx.directed_edge_swap(G)

    G = nx.Graph()
    G.add_nodes_from([0, 1, 2, 3])
    with pytest.raises(nx.NetworkXError, match=".*fewer than 2 edges"):
        nx.double_edge_swap(G)
