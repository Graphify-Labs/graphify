import networkx as nx


def test_wiener_index_of_disconnected_graph():
    assert nx.wiener_index(nx.empty_graph(2)) == float("inf")


def test_wiener_index_of_directed_graph():
    G = nx.complete_graph(3)
    H = nx.DiGraph(G)
    assert (2 * nx.wiener_index(G)) == nx.wiener_index(H)


def test_wiener_index_of_complete_graph():
    n = 10
    G = nx.complete_graph(n)
    assert nx.wiener_index(G) == (n * (n - 1) / 2)


def test_wiener_index_of_path_graph():
    # In P_n, there are n - 1 pairs of vertices at distance one, n -
    # 2 pairs at distance two, n - 3 at distance three, ..., 1 at
    # distance n - 1, so the Wiener index should be
    #
    #     1 * (n - 1) + 2 * (n - 2) + ... + (n - 2) * 2 + (n - 1) * 1
    #
    # For example, in P_5,
    #
    #     1 * 4 + 2 * 3 + 3 * 2 + 4 * 1 = 2 (1 * 4 + 2 * 3)
    #
    # and in P_6,
    #
    #     1 * 5 + 2 * 4 + 3 * 3 + 4 * 2 + 5 * 1 = 2 (1 * 5 + 2 * 4) + 3 * 3
    #
    # assuming n is *odd*, this gives the formula
    #
    #     2 \sum_{i = 1}^{(n - 1) / 2} [i * (n - i)]
    #
    # assuming n is *even*, this gives the formula
    #
    #     2 \sum_{i = 1}^{n / 2} [i * (n - i)] - (n / 2) ** 2
    #
    n = 9
    G = nx.path_graph(n)
    expected = 2 * sum(i * (n - i) for i in range(1, (n // 2) + 1))
    actual = nx.wiener_index(G)
    assert expected == actual


def test_schultz_and_gutman_index_of_disconnected_graph():
    n = 4
    G = nx.Graph()
    G.add_nodes_from(list(range(1, n + 1)))
    expected = float("inf")

    G.add_edge(1, 2)
    G.add_edge(3, 4)

    actual_1 = nx.schultz_index(G)
    actual_2 = nx.gutman_index(G)

    assert expected == actual_1
    assert expected == actual_2


def test_schultz_and_gutman_index_of_complete_bipartite_graph_1():
    n = 3
    m = 3
    cbg = nx.complete_bipartite_graph(n, m)

    expected_1 = n * m * (n + m) + 2 * n * (n - 1) * m + 2 * m * (m - 1) * n
    actual_1 = nx.schultz_index(cbg)

    expected_2 = n * m * (n * m) + n * (n - 1) * m * m + m * (m - 1) * n * n
    actual_2 = nx.gutman_index(cbg)

    assert expected_1 == actual_1
    assert expected_2 == actual_2


def test_schultz_and_gutman_index_of_complete_bipartite_graph_2():
    n = 2
    m = 5
    cbg = nx.complete_bipartite_graph(n, m)

    expected_1 = n * m * (n + m) + 2 * n * (n - 1) * m + 2 * m * (m - 1) * n
    actual_1 = nx.schultz_index(cbg)

    expected_2 = n * m * (n * m) + n * (n - 1) * m * m + m * (m - 1) * n * n
    actual_2 = nx.gutman_index(cbg)

    assert expected_1 == actual_1
    assert expected_2 == actual_2


def test_schultz_and_gutman_index_of_complete_graph():
    n = 5
    cg = nx.complete_graph(n)

    expected_1 = n * (n - 1) * (n - 1)
    actual_1 = nx.schultz_index(cg)

    assert expected_1 == actual_1

    expected_2 = n * (n - 1) * (n - 1) * (n - 1) / 2
    actual_2 = nx.gutman_index(cg)

    assert expected_2 == actual_2


def test_schultz_and_gutman_index_of_odd_cycle_graph():
    k = 5
    n = 2 * k + 1
    ocg = nx.cycle_graph(n)

    expected_1 = 2 * n * k * (k + 1)
    actual_1 = nx.schultz_index(ocg)

    expected_2 = 2 * n * k * (k + 1)
    actual_2 = nx.gutman_index(ocg)

    assert expected_1 == actual_1
    assert expected_2 == actual_2
