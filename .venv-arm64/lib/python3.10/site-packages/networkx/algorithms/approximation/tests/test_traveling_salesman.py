"""Unit tests for the traveling_salesman module."""

import random

import pytest

import networkx as nx
import networkx.algorithms.approximation as nx_app

pairwise = nx.utils.pairwise


def test_christofides_hamiltonian():
    random.seed(42)
    G = nx.complete_graph(20)
    for u, v in G.edges():
        G[u][v]["weight"] = random.randint(0, 10)

    H = nx.Graph()
    H.add_edges_from(pairwise(nx_app.christofides(G)))
    H.remove_edges_from(nx.find_cycle(H))
    assert len(H.edges) == 0

    tree = nx.minimum_spanning_tree(G, weight="weight")
    H = nx.Graph()
    H.add_edges_from(pairwise(nx_app.christofides(G, tree)))
    H.remove_edges_from(nx.find_cycle(H))
    assert len(H.edges) == 0


def test_christofides_incomplete_graph():
    G = nx.complete_graph(10)
    G.remove_edge(0, 1)
    pytest.raises(nx.NetworkXError, nx_app.christofides, G)


def test_christofides_ignore_selfloops():
    G = nx.complete_graph(5)
    G.add_edge(3, 3)
    cycle = nx_app.christofides(G)
    assert len(cycle) - 1 == len(G) == len(set(cycle))


# set up graphs for other tests
class TestBase:
    @classmethod
    def setup_class(cls):
        cls.DG = nx.DiGraph()
        cls.DG.add_weighted_edges_from(
            {
                ("A", "B", 3),
                ("A", "C", 17),
                ("A", "D", 14),
                ("B", "A", 3),
                ("B", "C", 12),
                ("B", "D", 16),
                ("C", "A", 13),
                ("C", "B", 12),
                ("C", "D", 4),
                ("D", "A", 14),
                ("D", "B", 15),
                ("D", "C", 2),
            }
        )
        cls.DG_cycle = ["D", "C", "B", "A", "D"]
        cls.DG_cost = 31.0

        cls.DG2 = nx.DiGraph()
        cls.DG2.add_weighted_edges_from(
            {
                ("A", "B", 3),
                ("A", "C", 17),
                ("A", "D", 14),
                ("B", "A", 30),
                ("B", "C", 2),
                ("B", "D", 16),
                ("C", "A", 33),
                ("C", "B", 32),
                ("C", "D", 34),
                ("D", "A", 14),
                ("D", "B", 15),
                ("D", "C", 2),
            }
        )
        cls.DG2_cycle = ["D", "A", "B", "C", "D"]
        cls.DG2_cost = 53.0

        cls.unweightedUG = nx.complete_graph(5, nx.Graph())
        cls.unweightedDG = nx.complete_graph(5, nx.DiGraph())

        cls.incompleteUG = nx.Graph()
        cls.incompleteUG.add_weighted_edges_from({(0, 1, 1), (1, 2, 3)})
        cls.incompleteDG = nx.DiGraph()
        cls.incompleteDG.add_weighted_edges_from({(0, 1, 1), (1, 2, 3)})

        cls.UG = nx.Graph()
        cls.UG.add_weighted_edges_from(
            {
                ("A", "B", 3),
                ("A", "C", 17),
                ("A", "D", 14),
                ("B", "C", 12),
                ("B", "D", 16),
                ("C", "D", 4),
            }
        )
        cls.UG_cycle = ["D", "C", "B", "A", "D"]
        cls.UG_cost = 33.0

        cls.UG2 = nx.Graph()
        cls.UG2.add_weighted_edges_from(
            {
                ("A", "B", 1),
                ("A", "C", 15),
                ("A", "D", 5),
                ("B", "C", 16),
                ("B", "D", 8),
                ("C", "D", 3),
            }
        )
        cls.UG2_cycle = ["D", "C", "B", "A", "D"]
        cls.UG2_cost = 25.0


def validate_solution(soln, cost, exp_soln, exp_cost):
    assert soln == exp_soln
    assert cost == exp_cost


def validate_symmetric_solution(soln, cost, exp_soln, exp_cost):
    assert soln == exp_soln or soln == exp_soln[::-1]
    assert cost == exp_cost


class TestGreedyTSP(TestBase):
    def test_greedy(self):
        cycle = nx_app.greedy_tsp(self.DG, source="D")
        cost = sum(self.DG[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        validate_solution(cycle, cost, ["D", "C", "B", "A", "D"], 31.0)

        cycle = nx_app.greedy_tsp(self.DG2, source="D")
        cost = sum(self.DG2[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        validate_solution(cycle, cost, ["D", "C", "B", "A", "D"], 78.0)

        cycle = nx_app.greedy_tsp(self.UG, source="D")
        cost = sum(self.UG[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        validate_solution(cycle, cost, ["D", "C", "B", "A", "D"], 33.0)

        cycle = nx_app.greedy_tsp(self.UG2, source="D")
        cost = sum(self.UG2[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        validate_solution(cycle, cost, ["D", "C", "A", "B", "D"], 27.0)

    def test_not_complete_graph(self):
        pytest.raises(nx.NetworkXError, nx_app.greedy_tsp, self.incompleteUG)
        pytest.raises(nx.NetworkXError, nx_app.greedy_tsp, self.incompleteDG)

    def test_not_weighted_graph(self):
        nx_app.greedy_tsp(self.unweightedUG)
        nx_app.greedy_tsp(self.unweightedDG)

    def test_two_nodes(self):
        G = nx.Graph()
        G.add_weighted_edges_from({(1, 2, 1)})
        cycle = nx_app.greedy_tsp(G)
        cost = sum(G[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        validate_solution(cycle, cost, [1, 2, 1], 2)

    def test_ignore_selfloops(self):
        G = nx.complete_graph(5)
        G.add_edge(3, 3)
        cycle = nx_app.greedy_tsp(G)
        assert len(cycle) - 1 == len(G) == len(set(cycle))


class TestSimulatedAnnealingTSP(TestBase):
    tsp = staticmethod(nx_app.simulated_annealing_tsp)

    def test_simulated_annealing_directed(self):
        cycle = self.tsp(self.DG, "greedy", source="D", seed=42)
        cost = sum(self.DG[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        validate_solution(cycle, cost, self.DG_cycle, self.DG_cost)

        initial_sol = ["D", "B", "A", "C", "D"]
        cycle = self.tsp(self.DG, initial_sol, source="D", seed=42)
        cost = sum(self.DG[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        validate_solution(cycle, cost, self.DG_cycle, self.DG_cost)

        initial_sol = ["D", "A", "C", "B", "D"]
        cycle = self.tsp(self.DG, initial_sol, move="1-0", source="D", seed=42)
        cost = sum(self.DG[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        validate_solution(cycle, cost, self.DG_cycle, self.DG_cost)

        cycle = self.tsp(self.DG2, "greedy", source="D", seed=42)
        cost = sum(self.DG2[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        validate_solution(cycle, cost, self.DG2_cycle, self.DG2_cost)

        cycle = self.tsp(self.DG2, "greedy", move="1-0", source="D", seed=42)
        cost = sum(self.DG2[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        validate_solution(cycle, cost, self.DG2_cycle, self.DG2_cost)

    def test_simulated_annealing_undirected(self):
        cycle = self.tsp(self.UG, "greedy", source="D", seed=42)
        cost = sum(self.UG[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        validate_solution(cycle, cost, self.UG_cycle, self.UG_cost)

        cycle = self.tsp(self.UG2, "greedy", source="D", seed=42)
        cost = sum(self.UG2[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        validate_symmetric_solution(cycle, cost, self.UG2_cycle, self.UG2_cost)

        cycle = self.tsp(self.UG2, "greedy", move="1-0", source="D", seed=42)
        cost = sum(self.UG2[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        validate_symmetric_solution(cycle, cost, self.UG2_cycle, self.UG2_cost)

    def test_error_on_input_order_mistake(self):
        # see issue #4846 https://github.com/networkx/networkx/issues/4846
        pytest.raises(TypeError, self.tsp, self.UG, weight="weight")
        pytest.raises(nx.NetworkXError, self.tsp, self.UG, "weight")

    def test_not_complete_graph(self):
        pytest.raises(nx.NetworkXError, self.tsp, self.incompleteUG, "greedy", source=0)
        pytest.raises(nx.NetworkXError, self.tsp, self.incompleteDG, "greedy", source=0)

    def test_ignore_selfloops(self):
        G = nx.complete_graph(5)
        G.add_edge(3, 3)
        cycle = self.tsp(G, "greedy")
        assert len(cycle) - 1 == len(G) == len(set(cycle))

    def test_not_weighted_graph(self):
        self.tsp(self.unweightedUG, "greedy")
        self.tsp(self.unweightedDG, "greedy")

    def test_two_nodes(self):
        G = nx.Graph()
        G.add_weighted_edges_from({(1, 2, 1)})

        cycle = self.tsp(G, "greedy", source=1, seed=42)
        cost = sum(G[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        validate_solution(cycle, cost, [1, 2, 1], 2)

        cycle = self.tsp(G, [1, 2, 1], source=1, seed=42)
        cost = sum(G[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        validate_solution(cycle, cost, [1, 2, 1], 2)

    def test_failure_of_costs_too_high_when_iterations_low(self):
        # Simulated Annealing Version:
        # set number of moves low and alpha high
        cycle = self.tsp(
            self.DG2, "greedy", source="D", move="1-0", alpha=1, N_inner=1, seed=42
        )
        cost = sum(self.DG2[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        print(cycle, cost)
        assert cost > self.DG2_cost

        # Try with an incorrect initial guess
        initial_sol = ["D", "A", "B", "C", "D"]
        cycle = self.tsp(
            self.DG,
            initial_sol,
            source="D",
            move="1-0",
            alpha=0.1,
            N_inner=1,
            max_iterations=1,
            seed=42,
        )
        cost = sum(self.DG[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        print(cycle, cost)
        assert cost > self.DG_cost


class TestThresholdAcceptingTSP(TestSimulatedAnnealingTSP):
    tsp = staticmethod(nx_app.threshold_accepting_tsp)

    def test_failure_of_costs_too_high_when_iterations_low(self):
        # Threshold Version:
        # set number of moves low and number of iterations low
        cycle = self.tsp(
            self.DG2,
            "greedy",
            source="D",
            move="1-0",
            N_inner=1,
            max_iterations=1,
            seed=4,
        )
        cost = sum(self.DG2[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        assert cost > self.DG2_cost

        # set threshold too low
        initial_sol = ["D", "A", "B", "C", "D"]
        cycle = self.tsp(
            self.DG, initial_sol, source="D", move="1-0", threshold=-3, seed=42
        )
        cost = sum(self.DG[n][nbr]["weight"] for n, nbr in pairwise(cycle))
        assert cost > self.DG_cost


# Tests for function traveling_salesman_problem
def test_TSP_method():
    G = nx.cycle_graph(9)
    G[4][5]["weight"] = 10

    # Test using the old currying method
    sa_tsp = lambda G, weight: nx_app.simulated_annealing_tsp(
        G, "greedy", weight, source=4, seed=1
    )

    path = nx_app.traveling_salesman_problem(
        G,
        method=sa_tsp,
        cycle=False,
    )
    print(path)
    assert path == [4, 3, 2, 1, 0, 8, 7, 6, 5]


def test_TSP_unweighted():
    G = nx.cycle_graph(9)
    path = nx_app.traveling_salesman_problem(G, nodes=[3, 6], cycle=False)
    assert path in ([3, 4, 5, 6], [6, 5, 4, 3])

    cycle = nx_app.traveling_salesman_problem(G, nodes=[3, 6])
    assert cycle in ([3, 4, 5, 6, 5, 4, 3], [6, 5, 4, 3, 4, 5, 6])


def test_TSP_weighted():
    G = nx.cycle_graph(9)
    G[0][1]["weight"] = 2
    G[1][2]["weight"] = 2
    G[2][3]["weight"] = 2
    G[3][4]["weight"] = 4
    G[4][5]["weight"] = 5
    G[5][6]["weight"] = 4
    G[6][7]["weight"] = 2
    G[7][8]["weight"] = 2
    G[8][0]["weight"] = 2
    tsp = nx_app.traveling_salesman_problem

    # path between 3 and 6
    expected_paths = ([3, 2, 1, 0, 8, 7, 6], [6, 7, 8, 0, 1, 2, 3])
    # cycle between 3 and 6
    expected_cycles = (
        [3, 2, 1, 0, 8, 7, 6, 7, 8, 0, 1, 2, 3],
        [6, 7, 8, 0, 1, 2, 3, 2, 1, 0, 8, 7, 6],
    )
    # path through all nodes
    expected_tourpaths = ([5, 6, 7, 8, 0, 1, 2, 3, 4], [4, 3, 2, 1, 0, 8, 7, 6, 5])

    # Check default method
    cycle = tsp(G, nodes=[3, 6], weight="weight")
    assert cycle in expected_cycles

    path = tsp(G, nodes=[3, 6], weight="weight", cycle=False)
    assert path in expected_paths

    tourpath = tsp(G, weight="weight", cycle=False)
    assert tourpath in expected_tourpaths

    # Check all methods
    methods = [
        (nx_app.christofides, {}),
        (nx_app.greedy_tsp, {}),
        (
            nx_app.simulated_annealing_tsp,
            {"init_cycle": "greedy"},
        ),
        (
            nx_app.threshold_accepting_tsp,
            {"init_cycle": "greedy"},
        ),
    ]
    for method, kwargs in methods:
        cycle = tsp(G, nodes=[3, 6], weight="weight", method=method, **kwargs)
        assert cycle in expected_cycles

        path = tsp(
            G, nodes=[3, 6], weight="weight", method=method, cycle=False, **kwargs
        )
        assert path in expected_paths

        tourpath = tsp(G, weight="weight", method=method, cycle=False, **kwargs)
        assert tourpath in expected_tourpaths


def test_TSP_incomplete_graph_short_path():
    G = nx.cycle_graph(9)
    G.add_edges_from([(4, 9), (9, 10), (10, 11), (11, 0)])
    G[4][5]["weight"] = 5

    cycle = nx_app.traveling_salesman_problem(G)
    print(cycle)
    assert len(cycle) == 17 and len(set(cycle)) == 12

    # make sure that cutting one edge out of complete graph formulation
    # cuts out many edges out of the path of the TSP
    path = nx_app.traveling_salesman_problem(G, cycle=False)
    print(path)
    assert len(path) == 13 and len(set(path)) == 12


def test_held_karp_ascent():
    """
    Test the Held-Karp relaxation with the ascent method
    """
    import networkx.algorithms.approximation.traveling_salesman as tsp

    np = pytest.importorskip("numpy")
    pytest.importorskip("scipy")

    # Adjacency matrix from page 1153 of the 1970 Held and Karp paper
    # which have been edited to be directional, but also symmetric
    G_array = np.array(
        [
            [0, 97, 60, 73, 17, 52],
            [97, 0, 41, 52, 90, 30],
            [60, 41, 0, 21, 35, 41],
            [73, 52, 21, 0, 95, 46],
            [17, 90, 35, 95, 0, 81],
            [52, 30, 41, 46, 81, 0],
        ]
    )

    solution_edges = [(1, 3), (2, 4), (3, 2), (4, 0), (5, 1), (0, 5)]

    G = nx.from_numpy_array(G_array, create_using=nx.DiGraph)
    opt_hk, z_star = tsp.held_karp_ascent(G)

    # Check that the optimal weights are the same
    assert round(opt_hk, 2) == 207.00
    # Check that the z_stars are the same
    solution = nx.DiGraph()
    solution.add_edges_from(solution_edges)
    assert nx.utils.edges_equal(z_star.edges, solution.edges)


def test_ascent_fractional_solution():
    """
    Test the ascent method using a modified version of Figure 2 on page 1140
    in 'The Traveling Salesman Problem and Minimum Spanning Trees' by Held and
    Karp
    """
    import networkx.algorithms.approximation.traveling_salesman as tsp

    np = pytest.importorskip("numpy")
    pytest.importorskip("scipy")

    # This version of Figure 2 has all of the edge weights multiplied by 100
    # and is a complete directed graph with infinite edge weights for the
    # edges not listed in the original graph
    G_array = np.array(
        [
            [0, 100, 100, 100000, 100000, 1],
            [100, 0, 100, 100000, 1, 100000],
            [100, 100, 0, 1, 100000, 100000],
            [100000, 100000, 1, 0, 100, 100],
            [100000, 1, 100000, 100, 0, 100],
            [1, 100000, 100000, 100, 100, 0],
        ]
    )

    solution_z_star = {
        (0, 1): 5 / 12,
        (0, 2): 5 / 12,
        (0, 5): 5 / 6,
        (1, 0): 5 / 12,
        (1, 2): 1 / 3,
        (1, 4): 5 / 6,
        (2, 0): 5 / 12,
        (2, 1): 1 / 3,
        (2, 3): 5 / 6,
        (3, 2): 5 / 6,
        (3, 4): 1 / 3,
        (3, 5): 1 / 2,
        (4, 1): 5 / 6,
        (4, 3): 1 / 3,
        (4, 5): 1 / 2,
        (5, 0): 5 / 6,
        (5, 3): 1 / 2,
        (5, 4): 1 / 2,
    }

    G = nx.from_numpy_array(G_array, create_using=nx.DiGraph)
    opt_hk, z_star = tsp.held_karp_ascent(G)

    # Check that the optimal weights are the same
    assert round(opt_hk, 2) == 303.00
    # Check that the z_stars are the same
    assert {key: round(z_star[key], 4) for key in z_star} == {
        key: round(solution_z_star[key], 4) for key in solution_z_star
    }


def test_ascent_method_asymmetric():
    """
    Tests the ascent method using a truly asymmetric graph for which the
    solution has been brute forced
    """
    import networkx.algorithms.approximation.traveling_salesman as tsp

    np = pytest.importorskip("numpy")
    pytest.importorskip("scipy")

    G_array = np.array(
        [
            [0, 26, 63, 59, 69, 31, 41],
            [62, 0, 91, 53, 75, 87, 47],
            [47, 82, 0, 90, 15, 9, 18],
            [68, 19, 5, 0, 58, 34, 93],
            [11, 58, 53, 55, 0, 61, 79],
            [88, 75, 13, 76, 98, 0, 40],
            [41, 61, 55, 88, 46, 45, 0],
        ]
    )

    solution_edges = [(0, 1), (1, 3), (3, 2), (2, 5), (5, 6), (4, 0), (6, 4)]

    G = nx.from_numpy_array(G_array, create_using=nx.DiGraph)
    opt_hk, z_star = tsp.held_karp_ascent(G)

    # Check that the optimal weights are the same
    assert round(opt_hk, 2) == 190.00
    # Check that the z_stars match.
    solution = nx.DiGraph()
    solution.add_edges_from(solution_edges)
    assert nx.utils.edges_equal(z_star.edges, solution.edges)


def test_ascent_method_asymmetric_2():
    """
    Tests the ascent method using a truly asymmetric graph for which the
    solution has been brute forced
    """
    import networkx.algorithms.approximation.traveling_salesman as tsp

    np = pytest.importorskip("numpy")
    pytest.importorskip("scipy")

    G_array = np.array(
        [
            [0, 45, 39, 92, 29, 31],
            [72, 0, 4, 12, 21, 60],
            [81, 6, 0, 98, 70, 53],
            [49, 71, 59, 0, 98, 94],
            [74, 95, 24, 43, 0, 47],
            [56, 43, 3, 65, 22, 0],
        ]
    )

    solution_edges = [(0, 5), (5, 4), (1, 3), (3, 0), (2, 1), (4, 2)]

    G = nx.from_numpy_array(G_array, create_using=nx.DiGraph)
    opt_hk, z_star = tsp.held_karp_ascent(G)

    # Check that the optimal weights are the same
    assert round(opt_hk, 2) == 144.00
    # Check that the z_stars match.
    solution = nx.DiGraph()
    solution.add_edges_from(solution_edges)
    assert nx.utils.edges_equal(z_star.edges, solution.edges)


def test_held_karp_ascent_asymmetric_3():
    """
    Tests the ascent method using a truly asymmetric graph with a fractional
    solution for which the solution has been brute forced.

    In this graph their are two different optimal, integral solutions (which
    are also the overall atsp solutions) to the Held Karp relaxation. However,
    this particular graph has two different tours of optimal value and the
    possible solutions in the held_karp_ascent function are not stored in an
    ordered data structure.
    """
    import networkx.algorithms.approximation.traveling_salesman as tsp

    np = pytest.importorskip("numpy")
    pytest.importorskip("scipy")

    G_array = np.array(
        [
            [0, 1, 5, 2, 7, 4],
            [7, 0, 7, 7, 1, 4],
            [4, 7, 0, 9, 2, 1],
            [7, 2, 7, 0, 4, 4],
            [5, 5, 4, 4, 0, 3],
            [3, 9, 1, 3, 4, 0],
        ]
    )

    solution1_edges = [(0, 3), (1, 4), (2, 5), (3, 1), (4, 2), (5, 0)]

    solution2_edges = [(0, 3), (3, 1), (1, 4), (4, 5), (2, 0), (5, 2)]

    G = nx.from_numpy_array(G_array, create_using=nx.DiGraph)
    opt_hk, z_star = tsp.held_karp_ascent(G)

    assert round(opt_hk, 2) == 13.00
    # Check that the z_stars are the same
    solution1 = nx.DiGraph()
    solution1.add_edges_from(solution1_edges)
    solution2 = nx.DiGraph()
    solution2.add_edges_from(solution2_edges)
    assert nx.utils.edges_equal(z_star.edges, solution1.edges) or nx.utils.edges_equal(
        z_star.edges, solution2.edges
    )


def test_held_karp_ascent_fractional_asymmetric():
    """
    Tests the ascent method using a truly asymmetric graph with a fractional
    solution for which the solution has been brute forced
    """
    import networkx.algorithms.approximation.traveling_salesman as tsp

    np = pytest.importorskip("numpy")
    pytest.importorskip("scipy")

    G_array = np.array(
        [
            [0, 100, 150, 100000, 100000, 1],
            [150, 0, 100, 100000, 1, 100000],
            [100, 150, 0, 1, 100000, 100000],
            [100000, 100000, 1, 0, 150, 100],
            [100000, 2, 100000, 100, 0, 150],
            [2, 100000, 100000, 150, 100, 0],
        ]
    )

    solution_z_star = {
        (0, 1): 5 / 12,
        (0, 2): 5 / 12,
        (0, 5): 5 / 6,
        (1, 0): 5 / 12,
        (1, 2): 5 / 12,
        (1, 4): 5 / 6,
        (2, 0): 5 / 12,
        (2, 1): 5 / 12,
        (2, 3): 5 / 6,
        (3, 2): 5 / 6,
        (3, 4): 5 / 12,
        (3, 5): 5 / 12,
        (4, 1): 5 / 6,
        (4, 3): 5 / 12,
        (4, 5): 5 / 12,
        (5, 0): 5 / 6,
        (5, 3): 5 / 12,
        (5, 4): 5 / 12,
    }

    G = nx.from_numpy_array(G_array, create_using=nx.DiGraph)
    opt_hk, z_star = tsp.held_karp_ascent(G)

    # Check that the optimal weights are the same
    assert round(opt_hk, 2) == 304.00
    # Check that the z_stars are the same
    assert {key: round(z_star[key], 4) for key in z_star} == {
        key: round(solution_z_star[key], 4) for key in solution_z_star
    }


def test_spanning_tree_distribution():
    """
    Test that we can create an exponential distribution of spanning trees such
    that the probability of each tree is proportional to the product of edge
    weights.

    Results of this test have been confirmed with hypothesis testing from the
    created distribution.

    This test uses the symmetric, fractional Held Karp solution.
    """
    import networkx.algorithms.approximation.traveling_salesman as tsp

    pytest.importorskip("numpy")
    pytest.importorskip("scipy")

    z_star = {
        (0, 1): 5 / 12,
        (0, 2): 5 / 12,
        (0, 5): 5 / 6,
        (1, 0): 5 / 12,
        (1, 2): 1 / 3,
        (1, 4): 5 / 6,
        (2, 0): 5 / 12,
        (2, 1): 1 / 3,
        (2, 3): 5 / 6,
        (3, 2): 5 / 6,
        (3, 4): 1 / 3,
        (3, 5): 1 / 2,
        (4, 1): 5 / 6,
        (4, 3): 1 / 3,
        (4, 5): 1 / 2,
        (5, 0): 5 / 6,
        (5, 3): 1 / 2,
        (5, 4): 1 / 2,
    }

    solution_gamma = {
        (0, 1): -0.6383,
        (0, 2): -0.6827,
        (0, 5): 0,
        (1, 2): -1.0781,
        (1, 4): 0,
        (2, 3): 0,
        (5, 3): -0.2820,
        (5, 4): -0.3327,
        (4, 3): -0.9927,
    }

    # The undirected support of z_star
    G = nx.MultiGraph()
    for u, v in z_star:
        if (u, v) in G.edges or (v, u) in G.edges:
            continue
        G.add_edge(u, v)

    gamma = tsp.spanning_tree_distribution(G, z_star)

    assert {key: round(gamma[key], 4) for key in gamma} == solution_gamma


def test_asadpour_tsp():
    """
    Test the complete asadpour tsp algorithm with the fractional, symmetric
    Held Karp solution. This test also uses an incomplete graph as input.
    """
    # This version of Figure 2 has all of the edge weights multiplied by 100
    # and the 0 weight edges have a weight of 1.
    pytest.importorskip("numpy")
    pytest.importorskip("scipy")

    edge_list = [
        (0, 1, 100),
        (0, 2, 100),
        (0, 5, 1),
        (1, 2, 100),
        (1, 4, 1),
        (2, 3, 1),
        (3, 4, 100),
        (3, 5, 100),
        (4, 5, 100),
        (1, 0, 100),
        (2, 0, 100),
        (5, 0, 1),
        (2, 1, 100),
        (4, 1, 1),
        (3, 2, 1),
        (4, 3, 100),
        (5, 3, 100),
        (5, 4, 100),
    ]

    G = nx.DiGraph()
    G.add_weighted_edges_from(edge_list)

    tour = nx_app.traveling_salesman_problem(
        G, weight="weight", method=nx_app.asadpour_atsp, seed=19
    )

    # Check that the returned list is a valid tour. Because this is an
    # incomplete graph, the conditions are not as strict. We need the tour to
    #
    #   Start and end at the same node
    #   Pass through every vertex at least once
    #   Have a total cost at most ln(6) / ln(ln(6)) = 3.0723 times the optimal
    #
    # For the second condition it is possible to have the tour pass through the
    # same vertex more then. Imagine that the tour on the complete version takes
    # an edge not in the original graph. In the output this is substituted with
    # the shortest path between those vertices, allowing vertices to appear more
    # than once.
    #
    # Even though we are using a fixed seed, multiple tours have been known to
    # be returned. The first two are from the original development of this test,
    # and the third one from issue #5913 on GitHub. If other tours are returned,
    # add it on the list of expected tours.
    expected_tours = [
        [1, 4, 5, 0, 2, 3, 2, 1],
        [3, 2, 0, 1, 4, 5, 3],
        [3, 2, 1, 0, 5, 4, 3],
    ]

    assert tour in expected_tours


def test_asadpour_real_world():
    """
    This test uses airline prices between the six largest cities in the US.

        * New York City -> JFK
        * Los Angeles -> LAX
        * Chicago -> ORD
        * Houston -> IAH
        * Phoenix -> PHX
        * Philadelphia -> PHL

    Flight prices from August 2021 using Delta or American airlines to get
    nonstop flight. The brute force solution found the optimal tour to cost $872

    This test also uses the `source` keyword argument to ensure that the tour
    always starts at city 0.
    """
    np = pytest.importorskip("numpy")
    pytest.importorskip("scipy")

    G_array = np.array(
        [
            # JFK  LAX  ORD  IAH  PHX  PHL
            [0, 243, 199, 208, 169, 183],  # JFK
            [277, 0, 217, 123, 127, 252],  # LAX
            [297, 197, 0, 197, 123, 177],  # ORD
            [303, 169, 197, 0, 117, 117],  # IAH
            [257, 127, 160, 117, 0, 319],  # PHX
            [183, 332, 217, 117, 319, 0],  # PHL
        ]
    )

    node_list = ["JFK", "LAX", "ORD", "IAH", "PHX", "PHL"]

    expected_tours = [
        ["JFK", "LAX", "PHX", "ORD", "IAH", "PHL", "JFK"],
        ["JFK", "ORD", "PHX", "LAX", "IAH", "PHL", "JFK"],
    ]

    G = nx.from_numpy_array(G_array, nodelist=node_list, create_using=nx.DiGraph)

    tour = nx_app.traveling_salesman_problem(
        G, weight="weight", method=nx_app.asadpour_atsp, seed=37, source="JFK"
    )

    assert tour in expected_tours


def test_asadpour_real_world_path():
    """
    This test uses airline prices between the six largest cities in the US. This
    time using a path, not a cycle.

        * New York City -> JFK
        * Los Angeles -> LAX
        * Chicago -> ORD
        * Houston -> IAH
        * Phoenix -> PHX
        * Philadelphia -> PHL

    Flight prices from August 2021 using Delta or American airlines to get
    nonstop flight. The brute force solution found the optimal tour to cost $872
    """
    np = pytest.importorskip("numpy")
    pytest.importorskip("scipy")

    G_array = np.array(
        [
            # JFK  LAX  ORD  IAH  PHX  PHL
            [0, 243, 199, 208, 169, 183],  # JFK
            [277, 0, 217, 123, 127, 252],  # LAX
            [297, 197, 0, 197, 123, 177],  # ORD
            [303, 169, 197, 0, 117, 117],  # IAH
            [257, 127, 160, 117, 0, 319],  # PHX
            [183, 332, 217, 117, 319, 0],  # PHL
        ]
    )

    node_list = ["JFK", "LAX", "ORD", "IAH", "PHX", "PHL"]

    expected_paths = [
        ["ORD", "PHX", "LAX", "IAH", "PHL", "JFK"],
        ["JFK", "PHL", "IAH", "ORD", "PHX", "LAX"],
    ]

    G = nx.from_numpy_array(G_array, nodelist=node_list, create_using=nx.DiGraph)

    path = nx_app.traveling_salesman_problem(
        G, weight="weight", cycle=False, method=nx_app.asadpour_atsp, seed=56
    )

    assert path in expected_paths


def test_asadpour_disconnected_graph():
    """
    Test that the proper exception is raised when asadpour_atsp is given an
    disconnected graph.
    """

    G = nx.complete_graph(4, create_using=nx.DiGraph)
    # have to set edge weights so that if the exception is not raised, the
    # function will complete and we will fail the test
    nx.set_edge_attributes(G, 1, "weight")
    G.add_node(5)

    pytest.raises(nx.NetworkXError, nx_app.asadpour_atsp, G)


def test_asadpour_incomplete_graph():
    """
    Test that the proper exception is raised when asadpour_atsp is given an
    incomplete graph
    """

    G = nx.complete_graph(4, create_using=nx.DiGraph)
    # have to set edge weights so that if the exception is not raised, the
    # function will complete and we will fail the test
    nx.set_edge_attributes(G, 1, "weight")
    G.remove_edge(0, 1)

    pytest.raises(nx.NetworkXError, nx_app.asadpour_atsp, G)


def test_asadpour_empty_graph():
    """
    Test the asadpour_atsp function with an empty graph
    """
    G = nx.DiGraph()

    pytest.raises(nx.NetworkXError, nx_app.asadpour_atsp, G)


@pytest.mark.slow
def test_asadpour_integral_held_karp():
    """
    This test uses an integral held karp solution and the held karp function
    will return a graph rather than a dict, bypassing most of the asadpour
    algorithm.

    At first glance, this test probably doesn't look like it ensures that we
    skip the rest of the asadpour algorithm, but it does. We are not fixing a
    see for the random number generator, so if we sample any spanning trees
    the approximation would be different basically every time this test is
    executed but it is not since held karp is deterministic and we do not
    reach the portion of the code with the dependence on random numbers.
    """
    np = pytest.importorskip("numpy")

    G_array = np.array(
        [
            [0, 26, 63, 59, 69, 31, 41],
            [62, 0, 91, 53, 75, 87, 47],
            [47, 82, 0, 90, 15, 9, 18],
            [68, 19, 5, 0, 58, 34, 93],
            [11, 58, 53, 55, 0, 61, 79],
            [88, 75, 13, 76, 98, 0, 40],
            [41, 61, 55, 88, 46, 45, 0],
        ]
    )

    G = nx.from_numpy_array(G_array, create_using=nx.DiGraph)

    for _ in range(2):
        tour = nx_app.traveling_salesman_problem(G, method=nx_app.asadpour_atsp)

        assert [1, 3, 2, 5, 2, 6, 4, 0, 1] == tour


def test_directed_tsp_impossible():
    """
    Test the asadpour algorithm with a graph without a hamiltonian circuit
    """
    pytest.importorskip("numpy")

    # In this graph, once we leave node 0 we cannot return
    edges = [
        (0, 1, 10),
        (0, 2, 11),
        (0, 3, 12),
        (1, 2, 4),
        (1, 3, 6),
        (2, 1, 3),
        (2, 3, 2),
        (3, 1, 5),
        (3, 2, 1),
    ]

    G = nx.DiGraph()
    G.add_weighted_edges_from(edges)

    pytest.raises(nx.NetworkXError, nx_app.traveling_salesman_problem, G)
