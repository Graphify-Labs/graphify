import pytest

import networkx as nx


def test_random_partition_graph():
    G = nx.random_partition_graph([3, 3, 3], 1, 0, seed=42)
    C = G.graph["partition"]
    assert C == [{0, 1, 2}, {3, 4, 5}, {6, 7, 8}]
    assert len(G) == 9
    assert len(list(G.edges())) == 9

    G = nx.random_partition_graph([3, 3, 3], 0, 1)
    C = G.graph["partition"]
    assert C == [{0, 1, 2}, {3, 4, 5}, {6, 7, 8}]
    assert len(G) == 9
    assert len(list(G.edges())) == 27

    G = nx.random_partition_graph([3, 3, 3], 1, 0, directed=True)
    C = G.graph["partition"]
    assert C == [{0, 1, 2}, {3, 4, 5}, {6, 7, 8}]
    assert len(G) == 9
    assert len(list(G.edges())) == 18

    G = nx.random_partition_graph([3, 3, 3], 0, 1, directed=True)
    C = G.graph["partition"]
    assert C == [{0, 1, 2}, {3, 4, 5}, {6, 7, 8}]
    assert len(G) == 9
    assert len(list(G.edges())) == 54

    G = nx.random_partition_graph([1, 2, 3, 4, 5], 0.5, 0.1)
    C = G.graph["partition"]
    assert C == [{0}, {1, 2}, {3, 4, 5}, {6, 7, 8, 9}, {10, 11, 12, 13, 14}]
    assert len(G) == 15

    rpg = nx.random_partition_graph
    pytest.raises(nx.NetworkXError, rpg, [1, 2, 3], 1.1, 0.1)
    pytest.raises(nx.NetworkXError, rpg, [1, 2, 3], -0.1, 0.1)
    pytest.raises(nx.NetworkXError, rpg, [1, 2, 3], 0.1, 1.1)
    pytest.raises(nx.NetworkXError, rpg, [1, 2, 3], 0.1, -0.1)


def test_planted_partition_graph():
    G = nx.planted_partition_graph(4, 3, 1, 0, seed=42)
    C = G.graph["partition"]
    assert len(C) == 4
    assert len(G) == 12
    assert len(list(G.edges())) == 12

    G = nx.planted_partition_graph(4, 3, 0, 1)
    C = G.graph["partition"]
    assert len(C) == 4
    assert len(G) == 12
    assert len(list(G.edges())) == 54

    G = nx.planted_partition_graph(10, 4, 0.5, 0.1, seed=42)
    C = G.graph["partition"]
    assert len(C) == 10
    assert len(G) == 40

    G = nx.planted_partition_graph(4, 3, 1, 0, directed=True)
    C = G.graph["partition"]
    assert len(C) == 4
    assert len(G) == 12
    assert len(list(G.edges())) == 24

    G = nx.planted_partition_graph(4, 3, 0, 1, directed=True)
    C = G.graph["partition"]
    assert len(C) == 4
    assert len(G) == 12
    assert len(list(G.edges())) == 108

    G = nx.planted_partition_graph(10, 4, 0.5, 0.1, seed=42, directed=True)
    C = G.graph["partition"]
    assert len(C) == 10
    assert len(G) == 40

    ppg = nx.planted_partition_graph
    pytest.raises(nx.NetworkXError, ppg, 3, 3, 1.1, 0.1)
    pytest.raises(nx.NetworkXError, ppg, 3, 3, -0.1, 0.1)
    pytest.raises(nx.NetworkXError, ppg, 3, 3, 0.1, 1.1)
    pytest.raises(nx.NetworkXError, ppg, 3, 3, 0.1, -0.1)


def test_relaxed_caveman_graph():
    G = nx.relaxed_caveman_graph(4, 3, 0)
    assert len(G) == 12
    G = nx.relaxed_caveman_graph(4, 3, 1)
    assert len(G) == 12
    G = nx.relaxed_caveman_graph(4, 3, 0.5)
    assert len(G) == 12
    G = nx.relaxed_caveman_graph(4, 3, 0.5, seed=42)
    assert len(G) == 12


def test_connected_caveman_graph():
    G = nx.connected_caveman_graph(4, 3)
    assert len(G) == 12

    G = nx.connected_caveman_graph(1, 5)
    K5 = nx.complete_graph(5)
    K5.remove_edge(3, 4)
    assert nx.is_isomorphic(G, K5)

    # need at least 2 nodes in each clique
    pytest.raises(nx.NetworkXError, nx.connected_caveman_graph, 4, 1)


def test_caveman_graph():
    G = nx.caveman_graph(4, 3)
    assert len(G) == 12

    G = nx.caveman_graph(5, 1)
    E5 = nx.empty_graph(5)
    assert nx.is_isomorphic(G, E5)

    G = nx.caveman_graph(1, 5)
    K5 = nx.complete_graph(5)
    assert nx.is_isomorphic(G, K5)


def test_gaussian_random_partition_graph():
    G = nx.gaussian_random_partition_graph(100, 10, 10, 0.3, 0.01)
    assert len(G) == 100
    G = nx.gaussian_random_partition_graph(100, 10, 10, 0.3, 0.01, directed=True)
    assert len(G) == 100
    G = nx.gaussian_random_partition_graph(
        100, 10, 10, 0.3, 0.01, directed=False, seed=42
    )
    assert len(G) == 100
    assert not isinstance(G, nx.DiGraph)
    G = nx.gaussian_random_partition_graph(
        100, 10, 10, 0.3, 0.01, directed=True, seed=42
    )
    assert len(G) == 100
    assert isinstance(G, nx.DiGraph)
    pytest.raises(
        nx.NetworkXError, nx.gaussian_random_partition_graph, 100, 101, 10, 1, 0
    )
    # Test when clusters are likely less than 1
    G = nx.gaussian_random_partition_graph(10, 0.5, 0.5, 0.5, 0.5, seed=1)
    assert len(G) == 10


def test_ring_of_cliques():
    for i in range(2, 20, 3):
        for j in range(2, 20, 3):
            G = nx.ring_of_cliques(i, j)
            assert G.number_of_nodes() == i * j
            if i != 2 or j != 1:
                expected_num_edges = i * (((j * (j - 1)) // 2) + 1)
            else:
                # the edge that already exists cannot be duplicated
                expected_num_edges = i * (((j * (j - 1)) // 2) + 1) - 1
            assert G.number_of_edges() == expected_num_edges
    with pytest.raises(
        nx.NetworkXError, match="A ring of cliques must have at least two cliques"
    ):
        nx.ring_of_cliques(1, 5)
    with pytest.raises(
        nx.NetworkXError, match="The cliques must have at least two nodes"
    ):
        nx.ring_of_cliques(3, 0)


def test_windmill_graph():
    for n in range(2, 20, 3):
        for k in range(2, 20, 3):
            G = nx.windmill_graph(n, k)
            assert G.number_of_nodes() == (k - 1) * n + 1
            assert G.number_of_edges() == n * k * (k - 1) / 2
            assert G.degree(0) == G.number_of_nodes() - 1
            for i in range(1, G.number_of_nodes()):
                assert G.degree(i) == k - 1
    with pytest.raises(
        nx.NetworkXError, match="A windmill graph must have at least two cliques"
    ):
        nx.windmill_graph(1, 3)
    with pytest.raises(
        nx.NetworkXError, match="The cliques must have at least two nodes"
    ):
        nx.windmill_graph(3, 0)


def test_stochastic_block_model():
    sizes = [75, 75, 300]
    probs = [[0.25, 0.05, 0.02], [0.05, 0.35, 0.07], [0.02, 0.07, 0.40]]
    G = nx.stochastic_block_model(sizes, probs, seed=0)
    C = G.graph["partition"]
    assert len(C) == 3
    assert len(G) == 450
    assert G.size() == 22160

    GG = nx.stochastic_block_model(sizes, probs, range(450), seed=0)
    assert G.nodes == GG.nodes

    # Test Exceptions
    sbm = nx.stochastic_block_model
    badnodelist = list(range(400))  # not enough nodes to match sizes
    badprobs1 = [[0.25, 0.05, 1.02], [0.05, 0.35, 0.07], [0.02, 0.07, 0.40]]
    badprobs2 = [[0.25, 0.05, 0.02], [0.05, -0.35, 0.07], [0.02, 0.07, 0.40]]
    probs_rect1 = [[0.25, 0.05, 0.02], [0.05, -0.35, 0.07]]
    probs_rect2 = [[0.25, 0.05], [0.05, -0.35], [0.02, 0.07]]
    asymprobs = [[0.25, 0.05, 0.01], [0.05, -0.35, 0.07], [0.02, 0.07, 0.40]]
    pytest.raises(nx.NetworkXException, sbm, sizes, badprobs1)
    pytest.raises(nx.NetworkXException, sbm, sizes, badprobs2)
    pytest.raises(nx.NetworkXException, sbm, sizes, probs_rect1, directed=True)
    pytest.raises(nx.NetworkXException, sbm, sizes, probs_rect2, directed=True)
    pytest.raises(nx.NetworkXException, sbm, sizes, asymprobs, directed=False)
    pytest.raises(nx.NetworkXException, sbm, sizes, probs, badnodelist)
    nodelist = [0] + list(range(449))  # repeated node name in nodelist
    pytest.raises(nx.NetworkXException, sbm, sizes, probs, nodelist)

    # Extra keyword arguments test
    GG = nx.stochastic_block_model(sizes, probs, seed=0, selfloops=True)
    assert G.nodes == GG.nodes
    GG = nx.stochastic_block_model(sizes, probs, selfloops=True, directed=True)
    assert G.nodes == GG.nodes
    GG = nx.stochastic_block_model(sizes, probs, seed=0, sparse=False)
    assert G.nodes == GG.nodes


def test_generator():
    n = 250
    tau1 = 3
    tau2 = 1.5
    mu = 0.1
    G = nx.LFR_benchmark_graph(
        n, tau1, tau2, mu, average_degree=5, min_community=20, seed=10
    )
    assert len(G) == 250
    C = {frozenset(G.nodes[v]["community"]) for v in G}
    assert nx.community.is_partition(G.nodes(), C)


def test_invalid_tau1():
    with pytest.raises(nx.NetworkXError, match="tau2 must be greater than one"):
        n = 100
        tau1 = 2
        tau2 = 1
        mu = 0.1
        nx.LFR_benchmark_graph(n, tau1, tau2, mu, min_degree=2)


def test_invalid_tau2():
    with pytest.raises(nx.NetworkXError, match="tau1 must be greater than one"):
        n = 100
        tau1 = 1
        tau2 = 2
        mu = 0.1
        nx.LFR_benchmark_graph(n, tau1, tau2, mu, min_degree=2)


def test_mu_too_large():
    with pytest.raises(nx.NetworkXError, match="mu must be in the interval \\[0, 1\\]"):
        n = 100
        tau1 = 2
        tau2 = 2
        mu = 1.1
        nx.LFR_benchmark_graph(n, tau1, tau2, mu, min_degree=2)


def test_mu_too_small():
    with pytest.raises(nx.NetworkXError, match="mu must be in the interval \\[0, 1\\]"):
        n = 100
        tau1 = 2
        tau2 = 2
        mu = -1
        nx.LFR_benchmark_graph(n, tau1, tau2, mu, min_degree=2)


def test_both_degrees_none():
    with pytest.raises(
        nx.NetworkXError,
        match="Must assign exactly one of min_degree and average_degree",
    ):
        n = 100
        tau1 = 2
        tau2 = 2
        mu = 1
        nx.LFR_benchmark_graph(n, tau1, tau2, mu)


def test_neither_degrees_none():
    with pytest.raises(
        nx.NetworkXError,
        match="Must assign exactly one of min_degree and average_degree",
    ):
        n = 100
        tau1 = 2
        tau2 = 2
        mu = 1
        nx.LFR_benchmark_graph(n, tau1, tau2, mu, min_degree=2, average_degree=5)


def test_max_iters_exceeded():
    with pytest.raises(
        nx.ExceededMaxIterations,
        match="Could not assign communities; try increasing min_community",
    ):
        n = 10
        tau1 = 2
        tau2 = 2
        mu = 0.1
        nx.LFR_benchmark_graph(n, tau1, tau2, mu, min_degree=2, max_iters=10, seed=1)


def test_max_deg_out_of_range():
    with pytest.raises(
        nx.NetworkXError, match="max_degree must be in the interval \\(0, n\\]"
    ):
        n = 10
        tau1 = 2
        tau2 = 2
        mu = 0.1
        nx.LFR_benchmark_graph(
            n, tau1, tau2, mu, max_degree=n + 1, max_iters=10, seed=1
        )


def test_max_community():
    n = 250
    tau1 = 3
    tau2 = 1.5
    mu = 0.1
    G = nx.LFR_benchmark_graph(
        n,
        tau1,
        tau2,
        mu,
        average_degree=5,
        max_degree=100,
        min_community=50,
        max_community=200,
        seed=10,
    )
    assert len(G) == 250
    C = {frozenset(G.nodes[v]["community"]) for v in G}
    assert nx.community.is_partition(G.nodes(), C)


def test_powerlaw_iterations_exceeded():
    with pytest.raises(
        nx.ExceededMaxIterations, match="Could not create power law sequence"
    ):
        n = 100
        tau1 = 2
        tau2 = 2
        mu = 1
        nx.LFR_benchmark_graph(n, tau1, tau2, mu, min_degree=2, max_iters=0)


def test_no_scipy_zeta():
    zeta2 = 1.6449340668482264
    assert abs(zeta2 - nx.generators.community._hurwitz_zeta(2, 1, 0.0001)) < 0.01


def test_generate_min_degree_itr():
    with pytest.raises(
        nx.ExceededMaxIterations, match="Could not match average_degree"
    ):
        nx.generators.community._generate_min_degree(2, 2, 1, 0.01, 0)
