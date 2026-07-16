"""Greedy coloring test suite."""

import itertools

import pytest

import networkx as nx

is_coloring = nx.algorithms.coloring.equitable_coloring.is_coloring
is_equitable = nx.algorithms.coloring.equitable_coloring.is_equitable


ALL_STRATEGIES = [
    "largest_first",
    "random_sequential",
    "smallest_last",
    "independent_set",
    "connected_sequential_bfs",
    "connected_sequential_dfs",
    "connected_sequential",
    "saturation_largest_first",
    "DSATUR",
]

# List of strategies where interchange=True results in an error
INTERCHANGE_INVALID = ["independent_set", "saturation_largest_first", "DSATUR"]


class TestColoring:
    def test_basic_cases(self):
        def check_basic_case(graph_func, n_nodes, strategy, interchange):
            graph = graph_func()
            coloring = nx.coloring.greedy_color(
                graph, strategy=strategy, interchange=interchange
            )
            assert verify_length(coloring, n_nodes)
            assert verify_coloring(graph, coloring)

        for graph_func, n_nodes in BASIC_TEST_CASES.items():
            for interchange in [True, False]:
                for strategy in ALL_STRATEGIES:
                    check_basic_case(graph_func, n_nodes, strategy, False)
                    if strategy not in INTERCHANGE_INVALID:
                        check_basic_case(graph_func, n_nodes, strategy, True)

    def test_special_cases(self):
        def check_special_case(strategy, graph_func, interchange, colors):
            graph = graph_func()
            coloring = nx.coloring.greedy_color(
                graph, strategy=strategy, interchange=interchange
            )
            if not hasattr(colors, "__len__"):
                colors = [colors]
            assert any(verify_length(coloring, n_colors) for n_colors in colors)
            assert verify_coloring(graph, coloring)

        for strategy, arglist in SPECIAL_TEST_CASES.items():
            for args in arglist:
                check_special_case(strategy, args[0], args[1], args[2])

    def test_interchange_invalid(self):
        graph = one_node_graph()
        for strategy in INTERCHANGE_INVALID:
            pytest.raises(
                nx.NetworkXPointlessConcept,
                nx.coloring.greedy_color,
                graph,
                strategy=strategy,
                interchange=True,
            )

    def test_bad_inputs(self):
        graph = one_node_graph()
        pytest.raises(
            nx.NetworkXError,
            nx.coloring.greedy_color,
            graph,
            strategy="invalid strategy",
        )

    def test_strategy_as_function(self):
        graph = lf_shc()
        colors_1 = nx.coloring.greedy_color(graph, "largest_first")
        colors_2 = nx.coloring.greedy_color(graph, nx.coloring.strategy_largest_first)
        assert colors_1 == colors_2

    def test_seed_argument(self):
        graph = lf_shc()
        rs = nx.coloring.strategy_random_sequential
        c1 = nx.coloring.greedy_color(graph, lambda g, c: rs(g, c, seed=1))
        for u, v in graph.edges:
            assert c1[u] != c1[v]

    def test_is_coloring(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2)])
        coloring = {0: 0, 1: 1, 2: 0}
        assert is_coloring(G, coloring)

        coloring[0] = 1
        assert not is_coloring(G, coloring)
        assert not is_equitable(G, coloring)

    def test_is_equitable(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2)])
        coloring = {0: 0, 1: 1, 2: 0}
        assert is_equitable(G, coloring)

        G.add_edges_from([(2, 3), (2, 4), (2, 5)])
        coloring[3] = 1
        coloring[4] = 1
        coloring[5] = 1
        assert is_coloring(G, coloring)
        assert not is_equitable(G, coloring)

    def test_num_colors(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (0, 3)])
        pytest.raises(nx.NetworkXAlgorithmError, nx.coloring.equitable_color, G, 2)

    def test_equitable_color(self):
        G = nx.fast_gnp_random_graph(n=10, p=0.2, seed=42)
        coloring = nx.coloring.equitable_color(G, max_degree(G) + 1)
        assert is_equitable(G, coloring)

    def test_equitable_color_empty(self):
        G = nx.empty_graph()
        coloring = nx.coloring.equitable_color(G, max_degree(G) + 1)
        assert is_equitable(G, coloring)

    def test_equitable_color_large(self):
        G = nx.fast_gnp_random_graph(100, 0.1, seed=42)
        coloring = nx.coloring.equitable_color(G, max_degree(G) + 1)
        assert is_equitable(G, coloring, num_colors=max_degree(G) + 1)

    def test_case_V_plus_not_in_A_cal(self):
        # Hand crafted case to avoid the easy case.
        L = {
            0: [2, 5],
            1: [3, 4],
            2: [0, 8],
            3: [1, 7],
            4: [1, 6],
            5: [0, 6],
            6: [4, 5],
            7: [3],
            8: [2],
        }

        F = {
            # Color 0
            0: 0,
            1: 0,
            # Color 1
            2: 1,
            3: 1,
            4: 1,
            5: 1,
            # Color 2
            6: 2,
            7: 2,
            8: 2,
        }

        C = nx.algorithms.coloring.equitable_coloring.make_C_from_F(F)
        N = nx.algorithms.coloring.equitable_coloring.make_N_from_L_C(L, C)
        H = nx.algorithms.coloring.equitable_coloring.make_H_from_C_N(C, N)

        nx.algorithms.coloring.equitable_coloring.procedure_P(
            V_minus=0, V_plus=1, N=N, H=H, F=F, C=C, L=L
        )
        check_state(L=L, N=N, H=H, F=F, C=C)

    def test_cast_no_solo(self):
        L = {
            0: [8, 9],
            1: [10, 11],
            2: [8],
            3: [9],
            4: [10, 11],
            5: [8],
            6: [9],
            7: [10, 11],
            8: [0, 2, 5],
            9: [0, 3, 6],
            10: [1, 4, 7],
            11: [1, 4, 7],
        }

        F = {0: 0, 1: 0, 2: 2, 3: 2, 4: 2, 5: 3, 6: 3, 7: 3, 8: 1, 9: 1, 10: 1, 11: 1}

        C = nx.algorithms.coloring.equitable_coloring.make_C_from_F(F)
        N = nx.algorithms.coloring.equitable_coloring.make_N_from_L_C(L, C)
        H = nx.algorithms.coloring.equitable_coloring.make_H_from_C_N(C, N)

        nx.algorithms.coloring.equitable_coloring.procedure_P(
            V_minus=0, V_plus=1, N=N, H=H, F=F, C=C, L=L
        )
        check_state(L=L, N=N, H=H, F=F, C=C)

    def test_hard_prob(self):
        # Tests for two levels of recursion.
        num_colors, s = 5, 5

        G = nx.Graph()
        G.add_edges_from(
            [
                (0, 10),
                (0, 11),
                (0, 12),
                (0, 23),
                (10, 4),
                (10, 9),
                (10, 20),
                (11, 4),
                (11, 8),
                (11, 16),
                (12, 9),
                (12, 22),
                (12, 23),
                (23, 7),
                (1, 17),
                (1, 18),
                (1, 19),
                (1, 24),
                (17, 5),
                (17, 13),
                (17, 22),
                (18, 5),
                (19, 5),
                (19, 6),
                (19, 8),
                (24, 7),
                (24, 16),
                (2, 4),
                (2, 13),
                (2, 14),
                (2, 15),
                (4, 6),
                (13, 5),
                (13, 21),
                (14, 6),
                (14, 15),
                (15, 6),
                (15, 21),
                (3, 16),
                (3, 20),
                (3, 21),
                (3, 22),
                (16, 8),
                (20, 8),
                (21, 9),
                (22, 7),
            ]
        )
        F = {node: node // s for node in range(num_colors * s)}
        F[s - 1] = num_colors - 1

        params = make_params_from_graph(G=G, F=F)

        nx.algorithms.coloring.equitable_coloring.procedure_P(
            V_minus=0, V_plus=num_colors - 1, **params
        )
        check_state(**params)

    def test_hardest_prob(self):
        # Tests for two levels of recursion.
        num_colors, s = 10, 4

        G = nx.Graph()
        G.add_edges_from(
            [
                (0, 19),
                (0, 24),
                (0, 29),
                (0, 30),
                (0, 35),
                (19, 3),
                (19, 7),
                (19, 9),
                (19, 15),
                (19, 21),
                (19, 24),
                (19, 30),
                (19, 38),
                (24, 5),
                (24, 11),
                (24, 13),
                (24, 20),
                (24, 30),
                (24, 37),
                (24, 38),
                (29, 6),
                (29, 10),
                (29, 13),
                (29, 15),
                (29, 16),
                (29, 17),
                (29, 20),
                (29, 26),
                (30, 6),
                (30, 10),
                (30, 15),
                (30, 22),
                (30, 23),
                (30, 39),
                (35, 6),
                (35, 9),
                (35, 14),
                (35, 18),
                (35, 22),
                (35, 23),
                (35, 25),
                (35, 27),
                (1, 20),
                (1, 26),
                (1, 31),
                (1, 34),
                (1, 38),
                (20, 4),
                (20, 8),
                (20, 14),
                (20, 18),
                (20, 28),
                (20, 33),
                (26, 7),
                (26, 10),
                (26, 14),
                (26, 18),
                (26, 21),
                (26, 32),
                (26, 39),
                (31, 5),
                (31, 8),
                (31, 13),
                (31, 16),
                (31, 17),
                (31, 21),
                (31, 25),
                (31, 27),
                (34, 7),
                (34, 8),
                (34, 13),
                (34, 18),
                (34, 22),
                (34, 23),
                (34, 25),
                (34, 27),
                (38, 4),
                (38, 9),
                (38, 12),
                (38, 14),
                (38, 21),
                (38, 27),
                (2, 3),
                (2, 18),
                (2, 21),
                (2, 28),
                (2, 32),
                (2, 33),
                (2, 36),
                (2, 37),
                (2, 39),
                (3, 5),
                (3, 9),
                (3, 13),
                (3, 22),
                (3, 23),
                (3, 25),
                (3, 27),
                (18, 6),
                (18, 11),
                (18, 15),
                (18, 39),
                (21, 4),
                (21, 10),
                (21, 14),
                (21, 36),
                (28, 6),
                (28, 10),
                (28, 14),
                (28, 16),
                (28, 17),
                (28, 25),
                (28, 27),
                (32, 5),
                (32, 10),
                (32, 12),
                (32, 16),
                (32, 17),
                (32, 22),
                (32, 23),
                (33, 7),
                (33, 10),
                (33, 12),
                (33, 16),
                (33, 17),
                (33, 25),
                (33, 27),
                (36, 5),
                (36, 8),
                (36, 15),
                (36, 16),
                (36, 17),
                (36, 25),
                (36, 27),
                (37, 5),
                (37, 11),
                (37, 15),
                (37, 16),
                (37, 17),
                (37, 22),
                (37, 23),
                (39, 7),
                (39, 8),
                (39, 15),
                (39, 22),
                (39, 23),
            ]
        )
        F = {node: node // s for node in range(num_colors * s)}
        F[s - 1] = num_colors - 1  # V- = 0, V+ = num_colors - 1

        params = make_params_from_graph(G=G, F=F)

        nx.algorithms.coloring.equitable_coloring.procedure_P(
            V_minus=0, V_plus=num_colors - 1, **params
        )
        check_state(**params)

    def test_strategy_saturation_largest_first(self):
        def color_remaining_nodes(
            G,
            colored_nodes,
            full_color_assignment=None,
            nodes_to_add_between_calls=1,
        ):
            color_assignments = []
            aux_colored_nodes = colored_nodes.copy()

            node_iterator = nx.algorithms.coloring.greedy_coloring.strategy_saturation_largest_first(
                G, aux_colored_nodes
            )

            for u in node_iterator:
                # Set to keep track of colors of neighbors
                nbr_colors = {
                    aux_colored_nodes[v] for v in G[u] if v in aux_colored_nodes
                }
                # Find the first unused color.
                for color in itertools.count():
                    if color not in nbr_colors:
                        break
                aux_colored_nodes[u] = color
                color_assignments.append((u, color))

                # Color nodes between iterations
                for i in range(nodes_to_add_between_calls - 1):
                    if not len(color_assignments) + len(colored_nodes) >= len(
                        full_color_assignment
                    ):
                        full_color_assignment_node, color = full_color_assignment[
                            len(color_assignments) + len(colored_nodes)
                        ]

                        # Assign the new color to the current node.
                        aux_colored_nodes[full_color_assignment_node] = color
                        color_assignments.append((full_color_assignment_node, color))

            return color_assignments, aux_colored_nodes

        for G, _, _ in SPECIAL_TEST_CASES["saturation_largest_first"]:
            G = G()

            # Check that function still works when nodes are colored between iterations
            for nodes_to_add_between_calls in range(1, 5):
                # Get a full color assignment, (including the order in which nodes were colored)
                colored_nodes = {}
                full_color_assignment, full_colored_nodes = color_remaining_nodes(
                    G, colored_nodes
                )

                # For each node in the color assignment, add it to colored_nodes and re-run the function
                for ind, (node, color) in enumerate(full_color_assignment):
                    colored_nodes[node] = color

                    (
                        partial_color_assignment,
                        partial_colored_nodes,
                    ) = color_remaining_nodes(
                        G,
                        colored_nodes,
                        full_color_assignment=full_color_assignment,
                        nodes_to_add_between_calls=nodes_to_add_between_calls,
                    )

                    # Check that the color assignment and order of remaining nodes are the same
                    assert full_color_assignment[ind + 1 :] == partial_color_assignment
                    assert full_colored_nodes == partial_colored_nodes


#  ############################  Utility functions ############################
def verify_coloring(graph, coloring):
    for node in graph.nodes():
        if node not in coloring:
            return False

        color = coloring[node]
        for neighbor in graph.neighbors(node):
            if coloring[neighbor] == color:
                return False

    return True


def verify_length(coloring, expected):
    coloring = dict_to_sets(coloring)
    return len(coloring) == expected


def dict_to_sets(colors):
    if len(colors) == 0:
        return []

    k = max(colors.values()) + 1
    sets = [set() for _ in range(k)]

    for node, color in colors.items():
        sets[color].add(node)

    return sets


#  ############################  Graph Generation ############################


def empty_graph():
    return nx.Graph()


def one_node_graph():
    graph = nx.Graph()
    graph.add_nodes_from([1])
    return graph


def two_node_graph():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2])
    graph.add_edges_from([(1, 2)])
    return graph


def three_node_clique():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3])
    graph.add_edges_from([(1, 2), (1, 3), (2, 3)])
    return graph


def disconnected():
    graph = nx.Graph()
    graph.add_edges_from([(1, 2), (2, 3), (4, 5), (5, 6)])
    return graph


def rs_shc():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3, 4])
    graph.add_edges_from([(1, 2), (2, 3), (3, 4)])
    return graph


def slf_shc():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3, 4, 5, 6, 7])
    graph.add_edges_from(
        [(1, 2), (1, 5), (1, 6), (2, 3), (2, 7), (3, 4), (3, 7), (4, 5), (4, 6), (5, 6)]
    )
    return graph


def slf_hc():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3, 4, 5, 6, 7, 8])
    graph.add_edges_from(
        [
            (1, 2),
            (1, 3),
            (1, 4),
            (1, 5),
            (2, 3),
            (2, 4),
            (2, 6),
            (5, 7),
            (5, 8),
            (6, 7),
            (6, 8),
            (7, 8),
        ]
    )
    return graph


def lf_shc():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3, 4, 5, 6])
    graph.add_edges_from([(6, 1), (1, 4), (4, 3), (3, 2), (2, 5)])
    return graph


def lf_hc():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3, 4, 5, 6, 7])
    graph.add_edges_from(
        [
            (1, 7),
            (1, 6),
            (1, 3),
            (1, 4),
            (7, 2),
            (2, 6),
            (2, 3),
            (2, 5),
            (5, 3),
            (5, 4),
            (4, 3),
        ]
    )
    return graph


def sl_shc():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3, 4, 5, 6])
    graph.add_edges_from(
        [(1, 2), (1, 3), (2, 3), (1, 4), (2, 5), (3, 6), (4, 5), (4, 6), (5, 6)]
    )
    return graph


def sl_hc():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3, 4, 5, 6, 7, 8])
    graph.add_edges_from(
        [
            (1, 2),
            (1, 3),
            (1, 5),
            (1, 7),
            (2, 3),
            (2, 4),
            (2, 8),
            (8, 4),
            (8, 6),
            (8, 7),
            (7, 5),
            (7, 6),
            (3, 4),
            (4, 6),
            (6, 5),
            (5, 3),
        ]
    )
    return graph


def gis_shc():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3, 4])
    graph.add_edges_from([(1, 2), (2, 3), (3, 4)])
    return graph


def gis_hc():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3, 4, 5, 6])
    graph.add_edges_from([(1, 5), (2, 5), (3, 6), (4, 6), (5, 6)])
    return graph


def cs_shc():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3, 4, 5])
    graph.add_edges_from([(1, 2), (1, 5), (2, 3), (2, 4), (2, 5), (3, 4), (4, 5)])
    return graph


def rsi_shc():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3, 4, 5, 6])
    graph.add_edges_from(
        [(1, 2), (1, 5), (1, 6), (2, 3), (3, 4), (4, 5), (4, 6), (5, 6)]
    )
    return graph


def lfi_shc():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3, 4, 5, 6, 7])
    graph.add_edges_from(
        [(1, 2), (1, 5), (1, 6), (2, 3), (2, 7), (3, 4), (3, 7), (4, 5), (4, 6), (5, 6)]
    )
    return graph


def lfi_hc():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3, 4, 5, 6, 7, 8, 9])
    graph.add_edges_from(
        [
            (1, 2),
            (1, 5),
            (1, 6),
            (1, 7),
            (2, 3),
            (2, 8),
            (2, 9),
            (3, 4),
            (3, 8),
            (3, 9),
            (4, 5),
            (4, 6),
            (4, 7),
            (5, 6),
        ]
    )
    return graph


def sli_shc():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3, 4, 5, 6, 7])
    graph.add_edges_from(
        [
            (1, 2),
            (1, 3),
            (1, 5),
            (1, 7),
            (2, 3),
            (2, 6),
            (3, 4),
            (4, 5),
            (4, 6),
            (5, 7),
            (6, 7),
        ]
    )
    return graph


def sli_hc():
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3, 4, 5, 6, 7, 8, 9])
    graph.add_edges_from(
        [
            (1, 2),
            (1, 3),
            (1, 4),
            (1, 5),
            (2, 3),
            (2, 7),
            (2, 8),
            (2, 9),
            (3, 6),
            (3, 7),
            (3, 9),
            (4, 5),
            (4, 6),
            (4, 8),
            (4, 9),
            (5, 6),
            (5, 7),
            (5, 8),
            (6, 7),
            (6, 9),
            (7, 8),
            (8, 9),
        ]
    )
    return graph


# --------------------------------------------------------------------------
# Basic tests for all strategies
# For each basic graph function, specify the number of expected colors.
BASIC_TEST_CASES = {
    empty_graph: 0,
    one_node_graph: 1,
    two_node_graph: 2,
    disconnected: 2,
    three_node_clique: 3,
}


# --------------------------------------------------------------------------
# Special test cases. Each strategy has a list of tuples of the form
# (graph function, interchange, valid # of colors)
SPECIAL_TEST_CASES = {
    "random_sequential": [
        (rs_shc, False, (2, 3)),
        (rs_shc, True, 2),
        (rsi_shc, True, (3, 4)),
    ],
    "saturation_largest_first": [(slf_shc, False, (3, 4)), (slf_hc, False, 4)],
    "largest_first": [
        (lf_shc, False, (2, 3)),
        (lf_hc, False, 4),
        (lf_shc, True, 2),
        (lf_hc, True, 3),
        (lfi_shc, True, (3, 4)),
        (lfi_hc, True, 4),
    ],
    "smallest_last": [
        (sl_shc, False, (3, 4)),
        (sl_hc, False, 5),
        (sl_shc, True, 3),
        (sl_hc, True, 4),
        (sli_shc, True, (3, 4)),
        (sli_hc, True, 5),
    ],
    "independent_set": [(gis_shc, False, (2, 3)), (gis_hc, False, 3)],
    "connected_sequential": [(cs_shc, False, (3, 4)), (cs_shc, True, 3)],
    "connected_sequential_dfs": [(cs_shc, False, (3, 4))],
}


# --------------------------------------------------------------------------
# Helper functions to test
# (graph function, interchange, valid # of colors)


def check_state(L, N, H, F, C):
    s = len(C[0])
    num_colors = len(C.keys())

    assert all(u in L[v] for u in L for v in L[u])
    assert all(F[u] != F[v] for u in L for v in L[u])
    assert all(len(L[u]) < num_colors for u in L)
    assert all(len(C[x]) == s for x in C)
    assert all(H[(c1, c2)] >= 0 for c1 in C for c2 in C)
    assert all(N[(u, F[u])] == 0 for u in F)


def max_degree(G):
    """Get the maximum degree of any node in G."""
    return max(G.degree(node) for node in G.nodes) if len(G.nodes) > 0 else 0


def make_params_from_graph(G, F):
    """Returns {N, L, H, C} from the given graph."""
    num_nodes = len(G)
    L = {u: [] for u in range(num_nodes)}
    for u, v in G.edges:
        L[u].append(v)
        L[v].append(u)

    C = nx.algorithms.coloring.equitable_coloring.make_C_from_F(F)
    N = nx.algorithms.coloring.equitable_coloring.make_N_from_L_C(L, C)
    H = nx.algorithms.coloring.equitable_coloring.make_H_from_C_N(C, N)

    return {"N": N, "F": F, "C": C, "H": H, "L": L}
