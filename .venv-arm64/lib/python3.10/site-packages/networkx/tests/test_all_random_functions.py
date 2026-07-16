import pytest

np = pytest.importorskip("numpy")
import random

import networkx as nx
from networkx.algorithms import approximation as approx
from networkx.algorithms import threshold

progress = 0

# store the random numbers after setting a global seed
np.random.seed(42)
np_rv = np.random.rand()
random.seed(42)
py_rv = random.random()


def t(f, *args, **kwds):
    """call one function and check if global RNG changed"""
    global progress
    progress += 1
    print(progress, ",", end="")

    f(*args, **kwds)

    after_np_rv = np.random.rand()
    # if np_rv != after_np_rv:
    #    print(np_rv, after_np_rv, "don't match np!")
    assert np_rv == after_np_rv
    np.random.seed(42)

    after_py_rv = random.random()
    # if py_rv != after_py_rv:
    #    print(py_rv, after_py_rv, "don't match py!")
    assert py_rv == after_py_rv
    random.seed(42)


def run_all_random_functions(seed):
    n = 20
    m = 10
    k = l = 2
    s = v = 10
    p = q = p1 = p2 = p_in = p_out = 0.4
    alpha = radius = theta = 0.75
    sizes = (20, 20, 10)
    colors = [1, 2, 3]
    G = nx.barbell_graph(12, 20)
    H = nx.cycle_graph(3)
    H.add_weighted_edges_from((u, v, 0.2) for u, v in H.edges)
    deg_sequence = [3, 2, 1, 3, 2, 1, 3, 2, 1, 2, 1, 2, 1]
    in_degree_sequence = w = sequence = aseq = bseq = deg_sequence

    # print("starting...")
    t(nx.maximal_independent_set, G, seed=seed)
    t(nx.rich_club_coefficient, G, seed=seed, normalized=False)
    t(nx.random_reference, G, seed=seed)
    t(nx.lattice_reference, G, seed=seed)
    t(nx.sigma, G, 1, 2, seed=seed)
    t(nx.omega, G, 1, 2, seed=seed)
    # print("out of smallworld.py")
    t(nx.double_edge_swap, G, seed=seed)
    # print("starting connected_double_edge_swap")
    t(nx.connected_double_edge_swap, nx.complete_graph(9), seed=seed)
    # print("ending connected_double_edge_swap")
    t(nx.random_layout, G, seed=seed)
    t(nx.fruchterman_reingold_layout, G, seed=seed)
    t(nx.algebraic_connectivity, G, seed=seed)
    t(nx.fiedler_vector, G, seed=seed)
    t(nx.spectral_ordering, G, seed=seed)
    # print('starting average_clustering')
    t(approx.average_clustering, G, seed=seed)
    t(approx.simulated_annealing_tsp, H, "greedy", source=1, seed=seed)
    t(approx.threshold_accepting_tsp, H, "greedy", source=1, seed=seed)
    t(
        approx.traveling_salesman_problem,
        H,
        method=lambda G, weight: approx.simulated_annealing_tsp(
            G, "greedy", weight, seed=seed
        ),
    )
    t(
        approx.traveling_salesman_problem,
        H,
        method=lambda G, weight: approx.threshold_accepting_tsp(
            G, "greedy", weight, seed=seed
        ),
    )
    t(nx.betweenness_centrality, G, seed=seed)
    t(nx.edge_betweenness_centrality, G, seed=seed)
    t(nx.approximate_current_flow_betweenness_centrality, G, seed=seed)
    # print("kernighan")
    t(nx.algorithms.community.kernighan_lin_bisection, G, seed=seed)
    # nx.algorithms.community.asyn_lpa_communities(G, seed=seed)
    t(nx.algorithms.tree.greedy_branching, G, seed=seed)
    # print('done with graph argument functions')

    t(nx.spectral_graph_forge, G, alpha, seed=seed)
    t(nx.algorithms.community.asyn_fluidc, G, k, max_iter=1, seed=seed)
    t(
        nx.algorithms.connectivity.edge_augmentation.greedy_k_edge_augmentation,
        G,
        k,
        seed=seed,
    )
    t(nx.algorithms.coloring.strategy_random_sequential, G, colors, seed=seed)

    cs = ["d", "i", "i", "d", "d", "i"]
    t(threshold.swap_d, cs, seed=seed)
    t(nx.configuration_model, deg_sequence, seed=seed)
    t(
        nx.directed_configuration_model,
        in_degree_sequence,
        in_degree_sequence,
        seed=seed,
    )
    t(nx.expected_degree_graph, w, seed=seed)
    t(nx.random_degree_sequence_graph, sequence, seed=seed)
    joint_degrees = {
        1: {4: 1},
        2: {2: 2, 3: 2, 4: 2},
        3: {2: 2, 4: 1},
        4: {1: 1, 2: 2, 3: 1},
    }
    t(nx.joint_degree_graph, joint_degrees, seed=seed)
    joint_degree_sequence = [
        (1, 0),
        (1, 0),
        (1, 0),
        (2, 0),
        (1, 0),
        (2, 1),
        (0, 1),
        (0, 1),
    ]
    t(nx.random_clustered_graph, joint_degree_sequence, seed=seed)
    constructor = [(3, 3, 0.5), (10, 10, 0.7)]
    t(nx.random_shell_graph, constructor, seed=seed)
    t(nx.random_triad, G.to_directed(), seed=seed)
    mapping = {1: 0.4, 2: 0.3, 3: 0.3}
    t(nx.utils.random_weighted_sample, mapping, k, seed=seed)
    t(nx.utils.weighted_choice, mapping, seed=seed)
    t(nx.algorithms.bipartite.configuration_model, aseq, bseq, seed=seed)
    t(nx.algorithms.bipartite.preferential_attachment_graph, aseq, p, seed=seed)

    def kernel_integral(u, w, z):
        return z - w

    t(nx.random_kernel_graph, n, kernel_integral, seed=seed)

    sizes = [75, 75, 300]
    probs = [[0.25, 0.05, 0.02], [0.05, 0.35, 0.07], [0.02, 0.07, 0.40]]
    t(nx.stochastic_block_model, sizes, probs, seed=seed)
    t(nx.random_partition_graph, sizes, p_in, p_out, seed=seed)

    # print("starting generator functions")
    t(threshold.random_threshold_sequence, n, p, seed=seed)
    t(nx.tournament.random_tournament, n, seed=seed)
    t(nx.relaxed_caveman_graph, l, k, p, seed=seed)
    t(nx.planted_partition_graph, l, k, p_in, p_out, seed=seed)
    t(nx.gaussian_random_partition_graph, n, s, v, p_in, p_out, seed=seed)
    t(nx.gn_graph, n, seed=seed)
    t(nx.gnr_graph, n, p, seed=seed)
    t(nx.gnc_graph, n, seed=seed)
    t(nx.scale_free_graph, n, seed=seed)
    t(nx.directed.random_uniform_k_out_graph, n, k, seed=seed)
    t(nx.random_k_out_graph, n, k, alpha, seed=seed)
    N = 1000
    t(nx.partial_duplication_graph, N, n, p, q, seed=seed)
    t(nx.duplication_divergence_graph, n, p, seed=seed)
    t(nx.random_geometric_graph, n, radius, seed=seed)
    t(nx.soft_random_geometric_graph, n, radius, seed=seed)
    t(nx.geographical_threshold_graph, n, theta, seed=seed)
    t(nx.waxman_graph, n, seed=seed)
    t(nx.navigable_small_world_graph, n, seed=seed)
    t(nx.thresholded_random_geometric_graph, n, radius, theta, seed=seed)
    t(nx.uniform_random_intersection_graph, n, m, p, seed=seed)
    t(nx.k_random_intersection_graph, n, m, k, seed=seed)

    t(nx.general_random_intersection_graph, n, 2, [0.1, 0.5], seed=seed)
    t(nx.fast_gnp_random_graph, n, p, seed=seed)
    t(nx.gnp_random_graph, n, p, seed=seed)
    t(nx.dense_gnm_random_graph, n, m, seed=seed)
    t(nx.gnm_random_graph, n, m, seed=seed)
    t(nx.newman_watts_strogatz_graph, n, k, p, seed=seed)
    t(nx.watts_strogatz_graph, n, k, p, seed=seed)
    t(nx.connected_watts_strogatz_graph, n, k, p, seed=seed)
    t(nx.random_regular_graph, 3, n, seed=seed)
    t(nx.barabasi_albert_graph, n, m, seed=seed)
    t(nx.extended_barabasi_albert_graph, n, m, p, q, seed=seed)
    t(nx.powerlaw_cluster_graph, n, m, p, seed=seed)
    t(nx.random_lobster, n, p1, p2, seed=seed)
    t(nx.random_powerlaw_tree, n, seed=seed, tries=5000)
    t(nx.random_powerlaw_tree_sequence, 10, seed=seed, tries=5000)
    t(nx.random_labeled_tree, n, seed=seed)
    t(nx.utils.powerlaw_sequence, n, seed=seed)
    t(nx.utils.zipf_rv, 2.3, seed=seed)
    cdist = [0.2, 0.4, 0.5, 0.7, 0.9, 1.0]
    t(nx.utils.discrete_sequence, n, cdistribution=cdist, seed=seed)
    t(nx.algorithms.bipartite.random_graph, n, m, p, seed=seed)
    t(nx.algorithms.bipartite.gnmk_random_graph, n, m, k, seed=seed)
    LFR = nx.generators.LFR_benchmark_graph
    t(
        LFR,
        25,
        3,
        1.5,
        0.1,
        average_degree=3,
        min_community=10,
        seed=seed,
        max_community=20,
    )
    t(nx.random_internet_as_graph, n, seed=seed)
    # print("done")


# choose to test an integer seed, or whether a single RNG can be everywhere
# np_rng = np.random.RandomState(14)
# seed = np_rng
# seed = 14


@pytest.mark.slow
# print("NetworkX Version:", nx.__version__)
def test_rng_interface():
    global progress

    # try different kinds of seeds
    for seed in [14, np.random.RandomState(14)]:
        np.random.seed(42)
        random.seed(42)
        run_all_random_functions(seed)
        progress = 0

        # check that both global RNGs are unaffected
        after_np_rv = np.random.rand()
        #        if np_rv != after_np_rv:
        #            print(np_rv, after_np_rv, "don't match np!")
        assert np_rv == after_np_rv
        after_py_rv = random.random()
        #        if py_rv != after_py_rv:
        #            print(py_rv, after_py_rv, "don't match py!")
        assert py_rv == after_py_rv


#        print("\nDone testing seed:", seed)

# test_rng_interface()
