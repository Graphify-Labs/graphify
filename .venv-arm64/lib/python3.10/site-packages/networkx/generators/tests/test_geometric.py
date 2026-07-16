import math
import random
from itertools import combinations

import pytest

import networkx as nx


def l1dist(x, y):
    return sum(abs(a - b) for a, b in zip(x, y))


class TestRandomGeometricGraph:
    """Unit tests for :func:`~networkx.random_geometric_graph`"""

    def test_number_of_nodes(self):
        G = nx.random_geometric_graph(50, 0.25, seed=42)
        assert len(G) == 50
        G = nx.random_geometric_graph(range(50), 0.25, seed=42)
        assert len(G) == 50

    def test_distances(self):
        """Tests that pairs of vertices adjacent if and only if they are
        within the prescribed radius.
        """
        # Use the Euclidean metric, the default according to the
        # documentation.
        G = nx.random_geometric_graph(50, 0.25)
        for u, v in combinations(G, 2):
            # Adjacent vertices must be within the given distance.
            if v in G[u]:
                assert math.dist(G.nodes[u]["pos"], G.nodes[v]["pos"]) <= 0.25
            # Nonadjacent vertices must be at greater distance.
            else:
                assert not math.dist(G.nodes[u]["pos"], G.nodes[v]["pos"]) <= 0.25

    def test_p(self):
        """Tests for providing an alternate distance metric to the generator."""
        # Use the L1 metric.
        G = nx.random_geometric_graph(50, 0.25, p=1)
        for u, v in combinations(G, 2):
            # Adjacent vertices must be within the given distance.
            if v in G[u]:
                assert l1dist(G.nodes[u]["pos"], G.nodes[v]["pos"]) <= 0.25
            # Nonadjacent vertices must be at greater distance.
            else:
                assert not l1dist(G.nodes[u]["pos"], G.nodes[v]["pos"]) <= 0.25

    def test_node_names(self):
        """Tests using values other than sequential numbers as node IDs."""
        import string

        nodes = list(string.ascii_lowercase)
        G = nx.random_geometric_graph(nodes, 0.25)
        assert len(G) == len(nodes)

        for u, v in combinations(G, 2):
            # Adjacent vertices must be within the given distance.
            if v in G[u]:
                assert math.dist(G.nodes[u]["pos"], G.nodes[v]["pos"]) <= 0.25
            # Nonadjacent vertices must be at greater distance.
            else:
                assert not math.dist(G.nodes[u]["pos"], G.nodes[v]["pos"]) <= 0.25

    def test_pos_name(self):
        G = nx.random_geometric_graph(50, 0.25, seed=42, pos_name="coords")
        assert all(len(d["coords"]) == 2 for n, d in G.nodes.items())


class TestSoftRandomGeometricGraph:
    """Unit tests for :func:`~networkx.soft_random_geometric_graph`"""

    def test_number_of_nodes(self):
        G = nx.soft_random_geometric_graph(50, 0.25, seed=42)
        assert len(G) == 50
        G = nx.soft_random_geometric_graph(range(50), 0.25, seed=42)
        assert len(G) == 50

    def test_distances(self):
        """Tests that pairs of vertices adjacent if and only if they are
        within the prescribed radius.
        """
        # Use the Euclidean metric, the default according to the
        # documentation.
        G = nx.soft_random_geometric_graph(50, 0.25)
        for u, v in combinations(G, 2):
            # Adjacent vertices must be within the given distance.
            if v in G[u]:
                assert math.dist(G.nodes[u]["pos"], G.nodes[v]["pos"]) <= 0.25

    def test_p(self):
        """Tests for providing an alternate distance metric to the generator."""

        # Use the L1 metric.
        def dist(x, y):
            return sum(abs(a - b) for a, b in zip(x, y))

        G = nx.soft_random_geometric_graph(50, 0.25, p=1)
        for u, v in combinations(G, 2):
            # Adjacent vertices must be within the given distance.
            if v in G[u]:
                assert dist(G.nodes[u]["pos"], G.nodes[v]["pos"]) <= 0.25

    def test_node_names(self):
        """Tests using values other than sequential numbers as node IDs."""
        import string

        nodes = list(string.ascii_lowercase)
        G = nx.soft_random_geometric_graph(nodes, 0.25)
        assert len(G) == len(nodes)

        for u, v in combinations(G, 2):
            # Adjacent vertices must be within the given distance.
            if v in G[u]:
                assert math.dist(G.nodes[u]["pos"], G.nodes[v]["pos"]) <= 0.25

    def test_p_dist_default(self):
        """Tests default p_dict = 0.5 returns graph with edge count <= RGG with
        same n, radius, dim and positions
        """
        nodes = 50
        dim = 2
        pos = {v: [random.random() for i in range(dim)] for v in range(nodes)}
        RGG = nx.random_geometric_graph(50, 0.25, pos=pos)
        SRGG = nx.soft_random_geometric_graph(50, 0.25, pos=pos)
        assert len(SRGG.edges()) <= len(RGG.edges())

    def test_p_dist_zero(self):
        """Tests if p_dict = 0 returns disconnected graph with 0 edges"""

        def p_dist(dist):
            return 0

        G = nx.soft_random_geometric_graph(50, 0.25, p_dist=p_dist)
        assert len(G.edges) == 0

    def test_pos_name(self):
        G = nx.soft_random_geometric_graph(50, 0.25, seed=42, pos_name="coords")
        assert all(len(d["coords"]) == 2 for n, d in G.nodes.items())


def join(G, u, v, theta, alpha, metric):
    """Returns ``True`` if and only if the nodes whose attributes are
    ``du`` and ``dv`` should be joined, according to the threshold
    condition for geographical threshold graphs.

    ``G`` is an undirected NetworkX graph, and ``u`` and ``v`` are nodes
    in that graph. The nodes must have node attributes ``'pos'`` and
    ``'weight'``.

    ``metric`` is a distance metric.
    """
    du, dv = G.nodes[u], G.nodes[v]
    u_pos, v_pos = du["pos"], dv["pos"]
    u_weight, v_weight = du["weight"], dv["weight"]
    return (u_weight + v_weight) * metric(u_pos, v_pos) ** alpha >= theta


class TestGeographicalThresholdGraph:
    """Unit tests for :func:`~networkx.geographical_threshold_graph`"""

    def test_number_of_nodes(self):
        G = nx.geographical_threshold_graph(50, 100, seed=42)
        assert len(G) == 50
        G = nx.geographical_threshold_graph(range(50), 100, seed=42)
        assert len(G) == 50

    def test_distances(self):
        """Tests that pairs of vertices adjacent if and only if their
        distances meet the given threshold.
        """
        # Use the Euclidean metric and alpha = -2
        # the default according to the documentation.
        G = nx.geographical_threshold_graph(50, 10)
        for u, v in combinations(G, 2):
            # Adjacent vertices must exceed the threshold.
            if v in G[u]:
                assert join(G, u, v, 10, -2, math.dist)
            # Nonadjacent vertices must not exceed the threshold.
            else:
                assert not join(G, u, v, 10, -2, math.dist)

    def test_metric(self):
        """Tests for providing an alternate distance metric to the generator."""
        # Use the L1 metric.
        G = nx.geographical_threshold_graph(50, 10, metric=l1dist)
        for u, v in combinations(G, 2):
            # Adjacent vertices must exceed the threshold.
            if v in G[u]:
                assert join(G, u, v, 10, -2, l1dist)
            # Nonadjacent vertices must not exceed the threshold.
            else:
                assert not join(G, u, v, 10, -2, l1dist)

    def test_p_dist_zero(self):
        """Tests if p_dict = 0 returns disconnected graph with 0 edges"""

        def p_dist(dist):
            return 0

        G = nx.geographical_threshold_graph(50, 1, p_dist=p_dist)
        assert len(G.edges) == 0

    def test_pos_weight_name(self):
        gtg = nx.geographical_threshold_graph
        G = gtg(50, 100, seed=42, pos_name="coords", weight_name="wt")
        assert all(len(d["coords"]) == 2 for n, d in G.nodes.items())
        assert all(d["wt"] > 0 for n, d in G.nodes.items())


class TestWaxmanGraph:
    """Unit tests for the :func:`~networkx.waxman_graph` function."""

    def test_number_of_nodes_1(self):
        G = nx.waxman_graph(50, 0.5, 0.1, seed=42)
        assert len(G) == 50
        G = nx.waxman_graph(range(50), 0.5, 0.1, seed=42)
        assert len(G) == 50

    def test_number_of_nodes_2(self):
        G = nx.waxman_graph(50, 0.5, 0.1, L=1)
        assert len(G) == 50
        G = nx.waxman_graph(range(50), 0.5, 0.1, L=1)
        assert len(G) == 50

    def test_metric(self):
        """Tests for providing an alternate distance metric to the generator."""
        # Use the L1 metric.
        G = nx.waxman_graph(50, 0.5, 0.1, metric=l1dist)
        assert len(G) == 50

    def test_pos_name(self):
        G = nx.waxman_graph(50, 0.5, 0.1, seed=42, pos_name="coords")
        assert all(len(d["coords"]) == 2 for n, d in G.nodes.items())


class TestNavigableSmallWorldGraph:
    def test_navigable_small_world(self):
        G = nx.navigable_small_world_graph(5, p=1, q=0, seed=42)
        gg = nx.grid_2d_graph(5, 5).to_directed()
        assert nx.is_isomorphic(G, gg)

        G = nx.navigable_small_world_graph(5, p=1, q=0, dim=3)
        gg = nx.grid_graph([5, 5, 5]).to_directed()
        assert nx.is_isomorphic(G, gg)

        G = nx.navigable_small_world_graph(5, p=1, q=0, dim=1)
        gg = nx.grid_graph([5]).to_directed()
        assert nx.is_isomorphic(G, gg)

    def test_invalid_diameter_value(self):
        with pytest.raises(nx.NetworkXException, match=".*p must be >= 1"):
            nx.navigable_small_world_graph(5, p=0, q=0, dim=1)

    def test_invalid_long_range_connections_value(self):
        with pytest.raises(nx.NetworkXException, match=".*q must be >= 0"):
            nx.navigable_small_world_graph(5, p=1, q=-1, dim=1)

    def test_invalid_exponent_for_decaying_probability_value(self):
        with pytest.raises(nx.NetworkXException, match=".*r must be >= 0"):
            nx.navigable_small_world_graph(5, p=1, q=0, r=-1, dim=1)

    def test_r_between_0_and_1(self):
        """Smoke test for radius in range [0, 1]"""
        # q=0 means no long-range connections
        G = nx.navigable_small_world_graph(3, p=1, q=0, r=0.5, dim=2, seed=42)
        expected = nx.grid_2d_graph(3, 3, create_using=nx.DiGraph)
        assert nx.utils.graphs_equal(G, expected)

    @pytest.mark.parametrize("seed", range(2478, 2578, 10))
    def test_r_general_scaling(self, seed):
        """The probability of adding a long-range edge scales with `1 / dist**r`,
        so a navigable_small_world graph created with r < 1 should generally
        result in more edges than a navigable_small_world graph with r >= 1
        (for 0 < q << n).

        N.B. this is probabilistic, so this test may not hold for all seeds."""
        G1 = nx.navigable_small_world_graph(7, q=3, r=0.5, seed=seed)
        G2 = nx.navigable_small_world_graph(7, q=3, r=1, seed=seed)
        G3 = nx.navigable_small_world_graph(7, q=3, r=2, seed=seed)
        assert G1.number_of_edges() > G2.number_of_edges()
        assert G2.number_of_edges() > G3.number_of_edges()


class TestThresholdedRandomGeometricGraph:
    """Unit tests for :func:`~networkx.thresholded_random_geometric_graph`"""

    def test_number_of_nodes(self):
        G = nx.thresholded_random_geometric_graph(50, 0.2, 0.1, seed=42)
        assert len(G) == 50
        G = nx.thresholded_random_geometric_graph(range(50), 0.2, 0.1, seed=42)
        assert len(G) == 50

    def test_distances(self):
        """Tests that pairs of vertices adjacent if and only if they are
        within the prescribed radius.
        """
        # Use the Euclidean metric, the default according to the
        # documentation.
        G = nx.thresholded_random_geometric_graph(50, 0.25, 0.1, seed=42)
        for u, v in combinations(G, 2):
            # Adjacent vertices must be within the given distance.
            if v in G[u]:
                assert math.dist(G.nodes[u]["pos"], G.nodes[v]["pos"]) <= 0.25

    def test_p(self):
        """Tests for providing an alternate distance metric to the generator."""

        # Use the L1 metric.
        def dist(x, y):
            return sum(abs(a - b) for a, b in zip(x, y))

        G = nx.thresholded_random_geometric_graph(50, 0.25, 0.1, p=1, seed=42)
        for u, v in combinations(G, 2):
            # Adjacent vertices must be within the given distance.
            if v in G[u]:
                assert dist(G.nodes[u]["pos"], G.nodes[v]["pos"]) <= 0.25

    def test_node_names(self):
        """Tests using values other than sequential numbers as node IDs."""
        import string

        nodes = list(string.ascii_lowercase)
        G = nx.thresholded_random_geometric_graph(nodes, 0.25, 0.1, seed=42)
        assert len(G) == len(nodes)

        for u, v in combinations(G, 2):
            # Adjacent vertices must be within the given distance.
            if v in G[u]:
                assert math.dist(G.nodes[u]["pos"], G.nodes[v]["pos"]) <= 0.25

    def test_theta(self):
        """Tests that pairs of vertices adjacent if and only if their sum
        weights exceeds the threshold parameter theta.
        """
        G = nx.thresholded_random_geometric_graph(50, 0.25, 0.1, seed=42)

        for u, v in combinations(G, 2):
            # Adjacent vertices must be within the given distance.
            if v in G[u]:
                assert (G.nodes[u]["weight"] + G.nodes[v]["weight"]) >= 0.1

    def test_pos_name(self):
        trgg = nx.thresholded_random_geometric_graph
        G = trgg(50, 0.25, 0.1, seed=42, pos_name="p", weight_name="wt")
        assert all(len(d["p"]) == 2 for n, d in G.nodes.items())
        assert all(d["wt"] > 0 for n, d in G.nodes.items())


def test_geometric_edges_pos_attribute():
    G = nx.Graph()
    G.add_nodes_from(
        [
            (0, {"position": (0, 0)}),
            (1, {"position": (0, 1)}),
            (2, {"position": (1, 0)}),
        ]
    )
    expected_edges = [(0, 1), (0, 2)]
    assert expected_edges == nx.geometric_edges(G, radius=1, pos_name="position")


def test_geometric_edges_raises_no_pos():
    G = nx.path_graph(3)
    msg = "all nodes. must have a '"
    with pytest.raises(nx.NetworkXError, match=msg):
        nx.geometric_edges(G, radius=1)


def test_number_of_nodes_S1():
    G = nx.geometric_soft_configuration_graph(
        beta=1.5, n=100, gamma=2.7, mean_degree=10, seed=42
    )
    assert len(G) == 100


def test_set_attributes_S1():
    G = nx.geometric_soft_configuration_graph(
        beta=1.5, n=100, gamma=2.7, mean_degree=10, seed=42
    )
    kappas = nx.get_node_attributes(G, "kappa")
    assert len(kappas) == 100
    thetas = nx.get_node_attributes(G, "theta")
    assert len(thetas) == 100
    radii = nx.get_node_attributes(G, "radius")
    assert len(radii) == 100


def test_mean_kappas_mean_degree_S1():
    G = nx.geometric_soft_configuration_graph(
        beta=2.5, n=50, gamma=2.7, mean_degree=10, seed=8023
    )

    kappas = nx.get_node_attributes(G, "kappa")
    mean_kappas = sum(kappas.values()) / len(kappas)
    assert math.fabs(mean_kappas - 10) < 0.5

    degrees = dict(G.degree())
    mean_degree = sum(degrees.values()) / len(degrees)
    assert math.fabs(mean_degree - 10) < 1


def test_dict_kappas_S1():
    kappas = {i: 10 for i in range(1000)}
    G = nx.geometric_soft_configuration_graph(beta=1, kappas=kappas)
    assert len(G) == 1000
    kappas = nx.get_node_attributes(G, "kappa")
    assert all(kappa == 10 for kappa in kappas.values())


def test_beta_clustering_S1():
    G1 = nx.geometric_soft_configuration_graph(
        beta=1.5, n=100, gamma=3.5, mean_degree=10, seed=42
    )
    G2 = nx.geometric_soft_configuration_graph(
        beta=3.0, n=100, gamma=3.5, mean_degree=10, seed=42
    )
    assert nx.average_clustering(G1) < nx.average_clustering(G2)


def test_wrong_parameters_S1():
    with pytest.raises(
        nx.NetworkXError,
        match="Please provide either kappas, or all 3 of: n, gamma and mean_degree.",
    ):
        G = nx.geometric_soft_configuration_graph(
            beta=1.5, gamma=3.5, mean_degree=10, seed=42
        )

    with pytest.raises(
        nx.NetworkXError,
        match="When kappas is input, n, gamma and mean_degree must not be.",
    ):
        kappas = {i: 10 for i in range(1000)}
        G = nx.geometric_soft_configuration_graph(
            beta=1.5, kappas=kappas, gamma=2.3, seed=42
        )

    with pytest.raises(
        nx.NetworkXError,
        match="Please provide either kappas, or all 3 of: n, gamma and mean_degree.",
    ):
        G = nx.geometric_soft_configuration_graph(beta=1.5, seed=42)


def test_negative_beta_S1():
    with pytest.raises(
        nx.NetworkXError, match="The parameter beta cannot be smaller or equal to 0."
    ):
        G = nx.geometric_soft_configuration_graph(
            beta=-1, n=100, gamma=2.3, mean_degree=10, seed=42
        )


def test_non_zero_clustering_beta_lower_one_S1():
    G = nx.geometric_soft_configuration_graph(
        beta=0.5, n=100, gamma=3.5, mean_degree=10, seed=42
    )
    assert nx.average_clustering(G) > 0


def test_mean_degree_influence_on_connectivity_S1():
    low_mean_degree = 2
    high_mean_degree = 20
    G_low = nx.geometric_soft_configuration_graph(
        beta=1.2, n=100, gamma=2.7, mean_degree=low_mean_degree, seed=42
    )
    G_high = nx.geometric_soft_configuration_graph(
        beta=1.2, n=100, gamma=2.7, mean_degree=high_mean_degree, seed=42
    )
    assert nx.number_connected_components(G_low) > nx.number_connected_components(
        G_high
    )


def test_compare_mean_kappas_different_gammas_S1():
    G1 = nx.geometric_soft_configuration_graph(
        beta=1.5, n=20, gamma=2.7, mean_degree=5, seed=42
    )
    G2 = nx.geometric_soft_configuration_graph(
        beta=1.5, n=20, gamma=3.5, mean_degree=5, seed=42
    )
    kappas1 = nx.get_node_attributes(G1, "kappa")
    mean_kappas1 = sum(kappas1.values()) / len(kappas1)
    kappas2 = nx.get_node_attributes(G2, "kappa")
    mean_kappas2 = sum(kappas2.values()) / len(kappas2)
    assert math.fabs(mean_kappas1 - mean_kappas2) < 1
