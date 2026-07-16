"""Maximum weight clique test suite."""

import pytest

import networkx as nx


class TestMaximumWeightClique:
    def test_basic_cases(self):
        def check_basic_case(graph_func, expected_weight, weight_accessor):
            graph = graph_func()
            clique, weight = nx.algorithms.max_weight_clique(graph, weight_accessor)
            assert verify_clique(
                graph, clique, weight, expected_weight, weight_accessor
            )

        for graph_func, (expected_weight, expected_size) in TEST_CASES.items():
            check_basic_case(graph_func, expected_weight, "weight")
            check_basic_case(graph_func, expected_size, None)

    def test_key_error(self):
        graph = two_node_graph()
        with pytest.raises(KeyError):
            nx.algorithms.max_weight_clique(graph, "nonexistent-key")

    def test_error_on_non_integer_weight(self):
        graph = two_node_graph()
        graph.nodes[2]["weight"] = 1.5
        with pytest.raises(ValueError):
            nx.algorithms.max_weight_clique(graph)

    def test_unaffected_by_self_loops(self):
        graph = two_node_graph()
        graph.add_edge(1, 1)
        graph.add_edge(2, 2)
        clique, weight = nx.algorithms.max_weight_clique(graph, "weight")
        assert verify_clique(graph, clique, weight, 30, "weight")
        graph = three_node_independent_set()
        graph.add_edge(1, 1)
        clique, weight = nx.algorithms.max_weight_clique(graph, "weight")
        assert verify_clique(graph, clique, weight, 20, "weight")

    def test_30_node_prob(self):
        G = nx.Graph()
        G.add_nodes_from(range(1, 31))
        for i in range(1, 31):
            G.nodes[i]["weight"] = i + 1
        # fmt: off
        G.add_edges_from(
            [
                (1, 12), (1, 13), (1, 15), (1, 16), (1, 18), (1, 19), (1, 20),
                (1, 23), (1, 26), (1, 28), (1, 29), (1, 30), (2, 3), (2, 4),
                (2, 5), (2, 8), (2, 9), (2, 10), (2, 14), (2, 17), (2, 18),
                (2, 21), (2, 22), (2, 23), (2, 27), (3, 9), (3, 15), (3, 21),
                (3, 22), (3, 23), (3, 24), (3, 27), (3, 28), (3, 29), (4, 5),
                (4, 6), (4, 8), (4, 21), (4, 22), (4, 23), (4, 26), (4, 28),
                (4, 30), (5, 6), (5, 8), (5, 9), (5, 13), (5, 14), (5, 15),
                (5, 16), (5, 20), (5, 21), (5, 22), (5, 25), (5, 28), (5, 29),
                (6, 7), (6, 8), (6, 13), (6, 17), (6, 18), (6, 19), (6, 24),
                (6, 26), (6, 27), (6, 28), (6, 29), (7, 12), (7, 14), (7, 15),
                (7, 16), (7, 17), (7, 20), (7, 25), (7, 27), (7, 29), (7, 30),
                (8, 10), (8, 15), (8, 16), (8, 18), (8, 20), (8, 22), (8, 24),
                (8, 26), (8, 27), (8, 28), (8, 30), (9, 11), (9, 12), (9, 13),
                (9, 14), (9, 15), (9, 16), (9, 19), (9, 20), (9, 21), (9, 24),
                (9, 30), (10, 12), (10, 15), (10, 18), (10, 19), (10, 20),
                (10, 22), (10, 23), (10, 24), (10, 26), (10, 27), (10, 29),
                (10, 30), (11, 13), (11, 15), (11, 16), (11, 17), (11, 18),
                (11, 19), (11, 20), (11, 22), (11, 29), (11, 30), (12, 14),
                (12, 17), (12, 18), (12, 19), (12, 20), (12, 21), (12, 23),
                (12, 25), (12, 26), (12, 30), (13, 20), (13, 22), (13, 23),
                (13, 24), (13, 30), (14, 16), (14, 20), (14, 21), (14, 22),
                (14, 23), (14, 25), (14, 26), (14, 27), (14, 29), (14, 30),
                (15, 17), (15, 18), (15, 20), (15, 21), (15, 26), (15, 27),
                (15, 28), (16, 17), (16, 18), (16, 19), (16, 20), (16, 21),
                (16, 29), (16, 30), (17, 18), (17, 21), (17, 22), (17, 25),
                (17, 27), (17, 28), (17, 30), (18, 19), (18, 20), (18, 21),
                (18, 22), (18, 23), (18, 24), (19, 20), (19, 22), (19, 23),
                (19, 24), (19, 25), (19, 27), (19, 30), (20, 21), (20, 23),
                (20, 24), (20, 26), (20, 28), (20, 29), (21, 23), (21, 26),
                (21, 27), (21, 29), (22, 24), (22, 25), (22, 26), (22, 29),
                (23, 25), (23, 30), (24, 25), (24, 26), (25, 27), (25, 29),
                (26, 27), (26, 28), (26, 30), (28, 29), (29, 30),
            ]
        )
        # fmt: on
        clique, weight = nx.algorithms.max_weight_clique(G)
        assert verify_clique(G, clique, weight, 111, "weight")


#  ############################  Utility functions ############################
def verify_clique(
    graph, clique, reported_clique_weight, expected_clique_weight, weight_accessor
):
    for node1 in clique:
        for node2 in clique:
            if node1 == node2:
                continue
            if not graph.has_edge(node1, node2):
                return False

    if weight_accessor is None:
        clique_weight = len(clique)
    else:
        clique_weight = sum(graph.nodes[v]["weight"] for v in clique)

    if clique_weight != expected_clique_weight:
        return False
    if clique_weight != reported_clique_weight:
        return False

    return True


#  ############################  Graph Generation ############################


def empty_graph():
    return nx.Graph()


def one_node_graph():
    graph = nx.Graph()
    graph.add_nodes_from([1])
    graph.nodes[1]["weight"] = 10
    return graph


def two_node_graph():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2])
    graph.add_edges_from([(1, 2)])
    graph.nodes[1]["weight"] = 10
    graph.nodes[2]["weight"] = 20
    return graph


def three_node_clique():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3])
    graph.add_edges_from([(1, 2), (1, 3), (2, 3)])
    graph.nodes[1]["weight"] = 10
    graph.nodes[2]["weight"] = 20
    graph.nodes[3]["weight"] = 5
    return graph


def three_node_independent_set():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3])
    graph.nodes[1]["weight"] = 10
    graph.nodes[2]["weight"] = 20
    graph.nodes[3]["weight"] = 5
    return graph


def disconnected():
    graph = nx.Graph()
    graph.add_edges_from([(1, 2), (2, 3), (4, 5), (5, 6)])
    graph.nodes[1]["weight"] = 10
    graph.nodes[2]["weight"] = 20
    graph.nodes[3]["weight"] = 5
    graph.nodes[4]["weight"] = 100
    graph.nodes[5]["weight"] = 200
    graph.nodes[6]["weight"] = 50
    return graph


# --------------------------------------------------------------------------
# Basic tests for all strategies
# For each basic graph function, specify expected weight of max weight clique
# and expected size of maximum clique
TEST_CASES = {
    empty_graph: (0, 0),
    one_node_graph: (10, 1),
    two_node_graph: (30, 2),
    three_node_clique: (35, 3),
    three_node_independent_set: (20, 1),
    disconnected: (300, 2),
}
