import math
from random import Random

import pytest

import networkx as nx
from networkx import convert_node_labels_to_integers as cnlti
from networkx.algorithms.distance_measures import _extrema_bounding


def test__extrema_bounding_invalid_compute_kwarg():
    G = nx.path_graph(3)
    with pytest.raises(ValueError, match="compute must be one of"):
        _extrema_bounding(G, compute="spam")


class TestDistance:
    def setup_method(self):
        G = cnlti(nx.grid_2d_graph(4, 4), first_label=1, ordering="sorted")
        self.G = G

    def test_eccentricity(self):
        assert nx.eccentricity(self.G, 1) == 6
        e = nx.eccentricity(self.G)
        assert e[1] == 6

        sp = dict(nx.shortest_path_length(self.G))
        e = nx.eccentricity(self.G, sp=sp)
        assert e[1] == 6

        e = nx.eccentricity(self.G, v=1)
        assert e == 6

        # This behavior changed in version 1.8 (ticket #739)
        e = nx.eccentricity(self.G, v=[1, 1])
        assert e[1] == 6
        e = nx.eccentricity(self.G, v=[1, 2])
        assert e[1] == 6

        # test against graph with one node
        G = nx.path_graph(1)
        e = nx.eccentricity(G)
        assert e[0] == 0
        e = nx.eccentricity(G, v=0)
        assert e == 0
        pytest.raises(nx.NetworkXError, nx.eccentricity, G, 1)

        # test against empty graph
        G = nx.empty_graph()
        e = nx.eccentricity(G)
        assert e == {}

    def test_diameter(self):
        assert nx.diameter(self.G) == 6

    def test_harmonic_diameter(self):
        assert abs(nx.harmonic_diameter(self.G) - 2.0477815699658715) < 1e-12

    def test_harmonic_diameter_empty(self):
        assert math.isnan(nx.harmonic_diameter(nx.empty_graph()))

    def test_harmonic_diameter_single_node(self):
        assert math.isnan(nx.harmonic_diameter(nx.empty_graph(1)))

    def test_harmonic_diameter_discrete(self):
        assert math.isinf(nx.harmonic_diameter(nx.empty_graph(3)))

    def test_harmonic_diameter_not_strongly_connected(self):
        DG = nx.DiGraph()
        DG.add_edge(0, 1)
        assert nx.harmonic_diameter(DG) == 2

    def test_radius(self):
        assert nx.radius(self.G) == 4

    def test_periphery(self):
        assert set(nx.periphery(self.G)) == {1, 4, 13, 16}

    def test_center(self):
        assert set(nx.center(self.G)) == {6, 7, 10, 11}

    def test_bound_diameter(self):
        assert nx.diameter(self.G, usebounds=True) == 6

    def test_bound_radius(self):
        assert nx.radius(self.G, usebounds=True) == 4

    def test_bound_periphery(self):
        result = {1, 4, 13, 16}
        assert set(nx.periphery(self.G, usebounds=True)) == result

    def test_bound_center(self):
        result = {6, 7, 10, 11}
        assert set(nx.center(self.G, usebounds=True)) == result

    def test_radius_exception(self):
        G = nx.Graph()
        G.add_edge(1, 2)
        G.add_edge(3, 4)
        pytest.raises(nx.NetworkXError, nx.diameter, G)

    def test_eccentricity_infinite(self):
        with pytest.raises(nx.NetworkXError):
            G = nx.Graph([(1, 2), (3, 4)])
            e = nx.eccentricity(G)

    def test_eccentricity_undirected_not_connected(self):
        with pytest.raises(nx.NetworkXError):
            G = nx.Graph([(1, 2), (3, 4)])
            e = nx.eccentricity(G, sp=1)

    def test_eccentricity_directed_weakly_connected(self):
        with pytest.raises(nx.NetworkXError):
            DG = nx.DiGraph([(1, 2), (1, 3)])
            nx.eccentricity(DG)


class TestWeightedDistance:
    def setup_method(self):
        G = nx.Graph()
        G.add_edge(0, 1, weight=0.6, cost=0.6, high_cost=6)
        G.add_edge(0, 2, weight=0.2, cost=0.2, high_cost=2)
        G.add_edge(2, 3, weight=0.1, cost=0.1, high_cost=1)
        G.add_edge(2, 4, weight=0.7, cost=0.7, high_cost=7)
        G.add_edge(2, 5, weight=0.9, cost=0.9, high_cost=9)
        G.add_edge(1, 5, weight=0.3, cost=0.3, high_cost=3)
        self.G = G
        self.weight_fn = lambda v, u, e: 2

    def test_eccentricity_weight_None(self):
        assert nx.eccentricity(self.G, 1, weight=None) == 3
        e = nx.eccentricity(self.G, weight=None)
        assert e[1] == 3

        e = nx.eccentricity(self.G, v=1, weight=None)
        assert e == 3

        # This behavior changed in version 1.8 (ticket #739)
        e = nx.eccentricity(self.G, v=[1, 1], weight=None)
        assert e[1] == 3
        e = nx.eccentricity(self.G, v=[1, 2], weight=None)
        assert e[1] == 3

    def test_eccentricity_weight_attr(self):
        assert nx.eccentricity(self.G, 1, weight="weight") == 1.5
        e = nx.eccentricity(self.G, weight="weight")
        assert (
            e
            == nx.eccentricity(self.G, weight="cost")
            != nx.eccentricity(self.G, weight="high_cost")
        )
        assert e[1] == 1.5

        e = nx.eccentricity(self.G, v=1, weight="weight")
        assert e == 1.5

        # This behavior changed in version 1.8 (ticket #739)
        e = nx.eccentricity(self.G, v=[1, 1], weight="weight")
        assert e[1] == 1.5
        e = nx.eccentricity(self.G, v=[1, 2], weight="weight")
        assert e[1] == 1.5

    def test_eccentricity_weight_fn(self):
        assert nx.eccentricity(self.G, 1, weight=self.weight_fn) == 6
        e = nx.eccentricity(self.G, weight=self.weight_fn)
        assert e[1] == 6

        e = nx.eccentricity(self.G, v=1, weight=self.weight_fn)
        assert e == 6

        # This behavior changed in version 1.8 (ticket #739)
        e = nx.eccentricity(self.G, v=[1, 1], weight=self.weight_fn)
        assert e[1] == 6
        e = nx.eccentricity(self.G, v=[1, 2], weight=self.weight_fn)
        assert e[1] == 6

    def test_diameter_weight_None(self):
        assert nx.diameter(self.G, weight=None) == 3

    def test_diameter_weight_attr(self):
        assert (
            nx.diameter(self.G, weight="weight")
            == nx.diameter(self.G, weight="cost")
            == 1.6
            != nx.diameter(self.G, weight="high_cost")
        )

    def test_diameter_weight_fn(self):
        assert nx.diameter(self.G, weight=self.weight_fn) == 6

    def test_radius_weight_None(self):
        assert pytest.approx(nx.radius(self.G, weight=None)) == 2

    def test_radius_weight_attr(self):
        assert (
            pytest.approx(nx.radius(self.G, weight="weight"))
            == pytest.approx(nx.radius(self.G, weight="cost"))
            == 0.9
            != nx.radius(self.G, weight="high_cost")
        )

    def test_radius_weight_fn(self):
        assert nx.radius(self.G, weight=self.weight_fn) == 4

    def test_periphery_weight_None(self):
        for v in set(nx.periphery(self.G, weight=None)):
            assert nx.eccentricity(self.G, v, weight=None) == nx.diameter(
                self.G, weight=None
            )

    def test_periphery_weight_attr(self):
        periphery = set(nx.periphery(self.G, weight="weight"))
        assert (
            periphery
            == set(nx.periphery(self.G, weight="cost"))
            == set(nx.periphery(self.G, weight="high_cost"))
        )
        for v in periphery:
            assert (
                nx.eccentricity(self.G, v, weight="high_cost")
                != nx.eccentricity(self.G, v, weight="weight")
                == nx.eccentricity(self.G, v, weight="cost")
                == nx.diameter(self.G, weight="weight")
                == nx.diameter(self.G, weight="cost")
                != nx.diameter(self.G, weight="high_cost")
            )
            assert nx.eccentricity(self.G, v, weight="high_cost") == nx.diameter(
                self.G, weight="high_cost"
            )

    def test_periphery_weight_fn(self):
        for v in set(nx.periphery(self.G, weight=self.weight_fn)):
            assert nx.eccentricity(self.G, v, weight=self.weight_fn) == nx.diameter(
                self.G, weight=self.weight_fn
            )

    def test_center_weight_None(self):
        for v in set(nx.center(self.G, weight=None)):
            assert pytest.approx(nx.eccentricity(self.G, v, weight=None)) == nx.radius(
                self.G, weight=None
            )

    def test_center_weight_attr(self):
        center = set(nx.center(self.G, weight="weight"))
        assert (
            center
            == set(nx.center(self.G, weight="cost"))
            != set(nx.center(self.G, weight="high_cost"))
        )
        for v in center:
            assert (
                nx.eccentricity(self.G, v, weight="high_cost")
                != pytest.approx(nx.eccentricity(self.G, v, weight="weight"))
                == pytest.approx(nx.eccentricity(self.G, v, weight="cost"))
                == nx.radius(self.G, weight="weight")
                == nx.radius(self.G, weight="cost")
                != nx.radius(self.G, weight="high_cost")
            )
            assert nx.eccentricity(self.G, v, weight="high_cost") == nx.radius(
                self.G, weight="high_cost"
            )

    def test_center_weight_fn(self):
        for v in set(nx.center(self.G, weight=self.weight_fn)):
            assert nx.eccentricity(self.G, v, weight=self.weight_fn) == nx.radius(
                self.G, weight=self.weight_fn
            )

    def test_bound_diameter_weight_None(self):
        assert nx.diameter(self.G, usebounds=True, weight=None) == 3

    def test_bound_diameter_weight_attr(self):
        assert (
            nx.diameter(self.G, usebounds=True, weight="high_cost")
            != nx.diameter(self.G, usebounds=True, weight="weight")
            == nx.diameter(self.G, usebounds=True, weight="cost")
            == 1.6
            != nx.diameter(self.G, usebounds=True, weight="high_cost")
        )
        assert nx.diameter(self.G, usebounds=True, weight="high_cost") == nx.diameter(
            self.G, usebounds=True, weight="high_cost"
        )

    def test_bound_diameter_weight_fn(self):
        assert nx.diameter(self.G, usebounds=True, weight=self.weight_fn) == 6

    def test_bound_radius_weight_None(self):
        assert pytest.approx(nx.radius(self.G, usebounds=True, weight=None)) == 2

    def test_bound_radius_weight_attr(self):
        assert (
            nx.radius(self.G, usebounds=True, weight="high_cost")
            != pytest.approx(nx.radius(self.G, usebounds=True, weight="weight"))
            == pytest.approx(nx.radius(self.G, usebounds=True, weight="cost"))
            == 0.9
            != nx.radius(self.G, usebounds=True, weight="high_cost")
        )
        assert nx.radius(self.G, usebounds=True, weight="high_cost") == nx.radius(
            self.G, usebounds=True, weight="high_cost"
        )

    def test_bound_radius_weight_fn(self):
        assert nx.radius(self.G, usebounds=True, weight=self.weight_fn) == 4

    def test_bound_periphery_weight_None(self):
        result = {1, 3, 4}
        assert set(nx.periphery(self.G, usebounds=True, weight=None)) == result

    def test_bound_periphery_weight_attr(self):
        result = {4, 5}
        assert (
            set(nx.periphery(self.G, usebounds=True, weight="weight"))
            == set(nx.periphery(self.G, usebounds=True, weight="cost"))
            == result
        )

    def test_bound_periphery_weight_fn(self):
        result = {1, 3, 4}
        assert (
            set(nx.periphery(self.G, usebounds=True, weight=self.weight_fn)) == result
        )

    def test_bound_center_weight_None(self):
        result = {0, 2, 5}
        assert set(nx.center(self.G, usebounds=True, weight=None)) == result

    def test_bound_center_weight_attr(self):
        result = {0}
        assert (
            set(nx.center(self.G, usebounds=True, weight="weight"))
            == set(nx.center(self.G, usebounds=True, weight="cost"))
            == result
        )

    def test_bound_center_weight_fn(self):
        result = {0, 2, 5}
        assert set(nx.center(self.G, usebounds=True, weight=self.weight_fn)) == result


class TestResistanceDistance:
    @classmethod
    def setup_class(cls):
        global np
        np = pytest.importorskip("numpy")
        sp = pytest.importorskip("scipy")

    def setup_method(self):
        G = nx.Graph()
        G.add_edge(1, 2, weight=2)
        G.add_edge(2, 3, weight=4)
        G.add_edge(3, 4, weight=1)
        G.add_edge(1, 4, weight=3)
        self.G = G

    def test_resistance_distance_directed_graph(self):
        G = nx.DiGraph()
        with pytest.raises(nx.NetworkXNotImplemented):
            nx.resistance_distance(G)

    def test_resistance_distance_empty(self):
        G = nx.Graph()
        with pytest.raises(nx.NetworkXError):
            nx.resistance_distance(G)

    def test_resistance_distance_not_connected(self):
        with pytest.raises(nx.NetworkXError):
            self.G.add_node(5)
            nx.resistance_distance(self.G, 1, 5)

    def test_resistance_distance_nodeA_not_in_graph(self):
        with pytest.raises(nx.NetworkXError):
            nx.resistance_distance(self.G, 9, 1)

    def test_resistance_distance_nodeB_not_in_graph(self):
        with pytest.raises(nx.NetworkXError):
            nx.resistance_distance(self.G, 1, 9)

    def test_resistance_distance(self):
        rd = nx.resistance_distance(self.G, 1, 3, "weight", True)
        test_data = 1 / (1 / (2 + 4) + 1 / (1 + 3))
        assert round(rd, 5) == round(test_data, 5)

    def test_resistance_distance_noinv(self):
        rd = nx.resistance_distance(self.G, 1, 3, "weight", False)
        test_data = 1 / (1 / (1 / 2 + 1 / 4) + 1 / (1 / 1 + 1 / 3))
        assert round(rd, 5) == round(test_data, 5)

    def test_resistance_distance_no_weight(self):
        rd = nx.resistance_distance(self.G, 1, 3)
        assert round(rd, 5) == 1

    def test_resistance_distance_neg_weight(self):
        self.G[2][3]["weight"] = -4
        rd = nx.resistance_distance(self.G, 1, 3, "weight", True)
        test_data = 1 / (1 / (2 + -4) + 1 / (1 + 3))
        assert round(rd, 5) == round(test_data, 5)

    def test_multigraph(self):
        G = nx.MultiGraph()
        G.add_edge(1, 2, weight=2)
        G.add_edge(2, 3, weight=4)
        G.add_edge(3, 4, weight=1)
        G.add_edge(1, 4, weight=3)
        rd = nx.resistance_distance(G, 1, 3, "weight", True)
        assert np.isclose(rd, 1 / (1 / (2 + 4) + 1 / (1 + 3)))

    def test_resistance_distance_div0(self):
        with pytest.raises(ZeroDivisionError):
            self.G[1][2]["weight"] = 0
            nx.resistance_distance(self.G, 1, 3, "weight")

    def test_resistance_distance_same_node(self):
        assert nx.resistance_distance(self.G, 1, 1) == 0

    def test_resistance_distance_only_nodeA(self):
        rd = nx.resistance_distance(self.G, nodeA=1)
        test_data = {}
        test_data[1] = 0
        test_data[2] = 0.75
        test_data[3] = 1
        test_data[4] = 0.75
        assert type(rd) == dict
        assert sorted(rd.keys()) == sorted(test_data.keys())
        for key in rd:
            assert np.isclose(rd[key], test_data[key])

    def test_resistance_distance_only_nodeB(self):
        rd = nx.resistance_distance(self.G, nodeB=1)
        test_data = {}
        test_data[1] = 0
        test_data[2] = 0.75
        test_data[3] = 1
        test_data[4] = 0.75
        assert type(rd) == dict
        assert sorted(rd.keys()) == sorted(test_data.keys())
        for key in rd:
            assert np.isclose(rd[key], test_data[key])

    def test_resistance_distance_all(self):
        rd = nx.resistance_distance(self.G)
        assert type(rd) == dict
        assert round(rd[1][3], 5) == 1


class TestEffectiveGraphResistance:
    @classmethod
    def setup_class(cls):
        global np
        np = pytest.importorskip("numpy")
        sp = pytest.importorskip("scipy")

    def setup_method(self):
        G = nx.Graph()
        G.add_edge(1, 2, weight=2)
        G.add_edge(1, 3, weight=1)
        G.add_edge(2, 3, weight=4)
        self.G = G

    def test_effective_graph_resistance_directed_graph(self):
        G = nx.DiGraph()
        with pytest.raises(nx.NetworkXNotImplemented):
            nx.effective_graph_resistance(G)

    def test_effective_graph_resistance_empty(self):
        G = nx.Graph()
        with pytest.raises(nx.NetworkXError):
            nx.effective_graph_resistance(G)

    def test_effective_graph_resistance_not_connected(self):
        G = nx.Graph([(1, 2), (3, 4)])
        RG = nx.effective_graph_resistance(G)
        assert np.isinf(RG)

    def test_effective_graph_resistance(self):
        RG = nx.effective_graph_resistance(self.G, "weight", True)
        rd12 = 1 / (1 / (1 + 4) + 1 / 2)
        rd13 = 1 / (1 / (1 + 2) + 1 / 4)
        rd23 = 1 / (1 / (2 + 4) + 1 / 1)
        assert np.isclose(RG, rd12 + rd13 + rd23)

    def test_effective_graph_resistance_noinv(self):
        RG = nx.effective_graph_resistance(self.G, "weight", False)
        rd12 = 1 / (1 / (1 / 1 + 1 / 4) + 1 / (1 / 2))
        rd13 = 1 / (1 / (1 / 1 + 1 / 2) + 1 / (1 / 4))
        rd23 = 1 / (1 / (1 / 2 + 1 / 4) + 1 / (1 / 1))
        assert np.isclose(RG, rd12 + rd13 + rd23)

    def test_effective_graph_resistance_no_weight(self):
        RG = nx.effective_graph_resistance(self.G)
        assert np.isclose(RG, 2)

    def test_effective_graph_resistance_neg_weight(self):
        self.G[2][3]["weight"] = -4
        RG = nx.effective_graph_resistance(self.G, "weight", True)
        rd12 = 1 / (1 / (1 + -4) + 1 / 2)
        rd13 = 1 / (1 / (1 + 2) + 1 / (-4))
        rd23 = 1 / (1 / (2 + -4) + 1 / 1)
        assert np.isclose(RG, rd12 + rd13 + rd23)

    def test_effective_graph_resistance_multigraph(self):
        G = nx.MultiGraph()
        G.add_edge(1, 2, weight=2)
        G.add_edge(1, 3, weight=1)
        G.add_edge(2, 3, weight=1)
        G.add_edge(2, 3, weight=3)
        RG = nx.effective_graph_resistance(G, "weight", True)
        edge23 = 1 / (1 / 1 + 1 / 3)
        rd12 = 1 / (1 / (1 + edge23) + 1 / 2)
        rd13 = 1 / (1 / (1 + 2) + 1 / edge23)
        rd23 = 1 / (1 / (2 + edge23) + 1 / 1)
        assert np.isclose(RG, rd12 + rd13 + rd23)

    def test_effective_graph_resistance_div0(self):
        with pytest.raises(ZeroDivisionError):
            self.G[1][2]["weight"] = 0
            nx.effective_graph_resistance(self.G, "weight")

    def test_effective_graph_resistance_complete_graph(self):
        N = 10
        G = nx.complete_graph(N)
        RG = nx.effective_graph_resistance(G)
        assert np.isclose(RG, N - 1)

    def test_effective_graph_resistance_path_graph(self):
        N = 10
        G = nx.path_graph(N)
        RG = nx.effective_graph_resistance(G)
        assert np.isclose(RG, (N - 1) * N * (N + 1) // 6)


class TestBarycenter:
    """Test :func:`networkx.algorithms.distance_measures.barycenter`."""

    def barycenter_as_subgraph(self, g, **kwargs):
        """Return the subgraph induced on the barycenter of g"""
        b = nx.barycenter(g, **kwargs)
        assert isinstance(b, list)
        assert set(b) <= set(g)
        return g.subgraph(b)

    def test_must_be_connected(self):
        pytest.raises(nx.NetworkXNoPath, nx.barycenter, nx.empty_graph(5))

    def test_sp_kwarg(self):
        # Complete graph K_5. Normally it works...
        K_5 = nx.complete_graph(5)
        sp = dict(nx.shortest_path_length(K_5))
        assert nx.barycenter(K_5, sp=sp) == list(K_5)

        # ...but not with the weight argument
        for u, v, data in K_5.edges.data():
            data["weight"] = 1
        pytest.raises(ValueError, nx.barycenter, K_5, sp=sp, weight="weight")

        # ...and a corrupted sp can make it seem like K_5 is disconnected
        del sp[0][1]
        pytest.raises(nx.NetworkXNoPath, nx.barycenter, K_5, sp=sp)

    def test_trees(self):
        """The barycenter of a tree is a single vertex or an edge.

        See [West01]_, p. 78.
        """
        prng = Random(0xDEADBEEF)
        for i in range(50):
            RT = nx.random_labeled_tree(prng.randint(1, 75), seed=prng)
            b = self.barycenter_as_subgraph(RT)
            if len(b) == 2:
                assert b.size() == 1
            else:
                assert len(b) == 1
                assert b.size() == 0

    def test_this_one_specific_tree(self):
        """Test the tree pictured at the bottom of [West01]_, p. 78."""
        g = nx.Graph(
            {
                "a": ["b"],
                "b": ["a", "x"],
                "x": ["b", "y"],
                "y": ["x", "z"],
                "z": ["y", 0, 1, 2, 3, 4],
                0: ["z"],
                1: ["z"],
                2: ["z"],
                3: ["z"],
                4: ["z"],
            }
        )
        b = self.barycenter_as_subgraph(g, attr="barycentricity")
        assert list(b) == ["z"]
        assert not b.edges
        expected_barycentricity = {
            0: 23,
            1: 23,
            2: 23,
            3: 23,
            4: 23,
            "a": 35,
            "b": 27,
            "x": 21,
            "y": 17,
            "z": 15,
        }
        for node, barycentricity in expected_barycentricity.items():
            assert g.nodes[node]["barycentricity"] == barycentricity

        # Doubling weights should do nothing but double the barycentricities
        for edge in g.edges:
            g.edges[edge]["weight"] = 2
        b = self.barycenter_as_subgraph(g, weight="weight", attr="barycentricity2")
        assert list(b) == ["z"]
        assert not b.edges
        for node, barycentricity in expected_barycentricity.items():
            assert g.nodes[node]["barycentricity2"] == barycentricity * 2


class TestKemenyConstant:
    @classmethod
    def setup_class(cls):
        global np
        np = pytest.importorskip("numpy")
        sp = pytest.importorskip("scipy")

    def setup_method(self):
        G = nx.Graph()
        w12 = 2
        w13 = 3
        w23 = 4
        G.add_edge(1, 2, weight=w12)
        G.add_edge(1, 3, weight=w13)
        G.add_edge(2, 3, weight=w23)
        self.G = G

    def test_kemeny_constant_directed(self):
        G = nx.DiGraph()
        G.add_edge(1, 2)
        G.add_edge(1, 3)
        G.add_edge(2, 3)
        with pytest.raises(nx.NetworkXNotImplemented):
            nx.kemeny_constant(G)

    def test_kemeny_constant_not_connected(self):
        self.G.add_node(5)
        with pytest.raises(nx.NetworkXError):
            nx.kemeny_constant(self.G)

    def test_kemeny_constant_no_nodes(self):
        G = nx.Graph()
        with pytest.raises(nx.NetworkXError):
            nx.kemeny_constant(G)

    def test_kemeny_constant_negative_weight(self):
        G = nx.Graph()
        w12 = 2
        w13 = 3
        w23 = -10
        G.add_edge(1, 2, weight=w12)
        G.add_edge(1, 3, weight=w13)
        G.add_edge(2, 3, weight=w23)
        with pytest.raises(nx.NetworkXError):
            nx.kemeny_constant(G, weight="weight")

    def test_kemeny_constant(self):
        K = nx.kemeny_constant(self.G, weight="weight")
        w12 = 2
        w13 = 3
        w23 = 4
        test_data = (
            3
            / 2
            * (w12 + w13)
            * (w12 + w23)
            * (w13 + w23)
            / (
                w12**2 * (w13 + w23)
                + w13**2 * (w12 + w23)
                + w23**2 * (w12 + w13)
                + 3 * w12 * w13 * w23
            )
        )
        assert np.isclose(K, test_data)

    def test_kemeny_constant_no_weight(self):
        K = nx.kemeny_constant(self.G)
        assert np.isclose(K, 4 / 3)

    def test_kemeny_constant_multigraph(self):
        G = nx.MultiGraph()
        w12_1 = 2
        w12_2 = 1
        w13 = 3
        w23 = 4
        G.add_edge(1, 2, weight=w12_1)
        G.add_edge(1, 2, weight=w12_2)
        G.add_edge(1, 3, weight=w13)
        G.add_edge(2, 3, weight=w23)
        K = nx.kemeny_constant(G, weight="weight")
        w12 = w12_1 + w12_2
        test_data = (
            3
            / 2
            * (w12 + w13)
            * (w12 + w23)
            * (w13 + w23)
            / (
                w12**2 * (w13 + w23)
                + w13**2 * (w12 + w23)
                + w23**2 * (w12 + w13)
                + 3 * w12 * w13 * w23
            )
        )
        assert np.isclose(K, test_data)

    def test_kemeny_constant_weight0(self):
        G = nx.Graph()
        w12 = 0
        w13 = 3
        w23 = 4
        G.add_edge(1, 2, weight=w12)
        G.add_edge(1, 3, weight=w13)
        G.add_edge(2, 3, weight=w23)
        K = nx.kemeny_constant(G, weight="weight")
        test_data = (
            3
            / 2
            * (w12 + w13)
            * (w12 + w23)
            * (w13 + w23)
            / (
                w12**2 * (w13 + w23)
                + w13**2 * (w12 + w23)
                + w23**2 * (w12 + w13)
                + 3 * w12 * w13 * w23
            )
        )
        assert np.isclose(K, test_data)

    def test_kemeny_constant_selfloop(self):
        G = nx.Graph()
        w11 = 1
        w12 = 2
        w13 = 3
        w23 = 4
        G.add_edge(1, 1, weight=w11)
        G.add_edge(1, 2, weight=w12)
        G.add_edge(1, 3, weight=w13)
        G.add_edge(2, 3, weight=w23)
        K = nx.kemeny_constant(G, weight="weight")
        test_data = (
            (2 * w11 + 3 * w12 + 3 * w13)
            * (w12 + w23)
            * (w13 + w23)
            / (
                (w12 * w13 + w12 * w23 + w13 * w23)
                * (w11 + 2 * w12 + 2 * w13 + 2 * w23)
            )
        )
        assert np.isclose(K, test_data)

    def test_kemeny_constant_complete_bipartite_graph(self):
        # Theorem 1 in https://www.sciencedirect.com/science/article/pii/S0166218X20302912
        n1 = 5
        n2 = 4
        G = nx.complete_bipartite_graph(n1, n2)
        K = nx.kemeny_constant(G)
        assert np.isclose(K, n1 + n2 - 3 / 2)

    def test_kemeny_constant_path_graph(self):
        # Theorem 2 in https://www.sciencedirect.com/science/article/pii/S0166218X20302912
        n = 10
        G = nx.path_graph(n)
        K = nx.kemeny_constant(G)
        assert np.isclose(K, n**2 / 3 - 2 * n / 3 + 1 / 2)
