import math
from functools import partial

import pytest

import networkx as nx


def _test_func(G, ebunch, expected, predict_func, **kwargs):
    result = predict_func(G, ebunch, **kwargs)
    exp_dict = {tuple(sorted([u, v])): score for u, v, score in expected}
    res_dict = {tuple(sorted([u, v])): score for u, v, score in result}

    assert len(exp_dict) == len(res_dict)
    for p in exp_dict:
        assert exp_dict[p] == pytest.approx(res_dict[p], abs=1e-7)


class TestResourceAllocationIndex:
    @classmethod
    def setup_class(cls):
        cls.func = staticmethod(nx.resource_allocation_index)
        cls.test = partial(_test_func, predict_func=cls.func)

    def test_K5(self):
        G = nx.complete_graph(5)
        self.test(G, [(0, 1)], [(0, 1, 0.75)])

    def test_P3(self):
        G = nx.path_graph(3)
        self.test(G, [(0, 2)], [(0, 2, 0.5)])

    def test_S4(self):
        G = nx.star_graph(4)
        self.test(G, [(1, 2)], [(1, 2, 0.25)])

    @pytest.mark.parametrize("graph_type", (nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph))
    def test_notimplemented(self, graph_type):
        assert pytest.raises(
            nx.NetworkXNotImplemented, self.func, graph_type([(0, 1), (1, 2)]), [(0, 2)]
        )

    def test_node_not_found(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (2, 3)])
        assert pytest.raises(nx.NodeNotFound, self.func, G, [(0, 4)])

    def test_no_common_neighbor(self):
        G = nx.Graph()
        G.add_nodes_from([0, 1])
        self.test(G, [(0, 1)], [(0, 1, 0)])

    def test_equal_nodes(self):
        G = nx.complete_graph(4)
        self.test(G, [(0, 0)], [(0, 0, 1)])

    def test_all_nonexistent_edges(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (2, 3)])
        self.test(G, None, [(0, 3, 0.5), (1, 2, 0.5), (1, 3, 0)])


class TestJaccardCoefficient:
    @classmethod
    def setup_class(cls):
        cls.func = staticmethod(nx.jaccard_coefficient)
        cls.test = partial(_test_func, predict_func=cls.func)

    def test_K5(self):
        G = nx.complete_graph(5)
        self.test(G, [(0, 1)], [(0, 1, 0.6)])

    def test_P4(self):
        G = nx.path_graph(4)
        self.test(G, [(0, 2)], [(0, 2, 0.5)])

    @pytest.mark.parametrize("graph_type", (nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph))
    def test_notimplemented(self, graph_type):
        assert pytest.raises(
            nx.NetworkXNotImplemented, self.func, graph_type([(0, 1), (1, 2)]), [(0, 2)]
        )

    def test_node_not_found(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (2, 3)])
        assert pytest.raises(nx.NodeNotFound, self.func, G, [(0, 4)])

    def test_no_common_neighbor(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (2, 3)])
        self.test(G, [(0, 2)], [(0, 2, 0)])

    def test_isolated_nodes(self):
        G = nx.Graph()
        G.add_nodes_from([0, 1])
        self.test(G, [(0, 1)], [(0, 1, 0)])

    def test_all_nonexistent_edges(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (2, 3)])
        self.test(G, None, [(0, 3, 0.5), (1, 2, 0.5), (1, 3, 0)])


class TestAdamicAdarIndex:
    @classmethod
    def setup_class(cls):
        cls.func = staticmethod(nx.adamic_adar_index)
        cls.test = partial(_test_func, predict_func=cls.func)

    def test_K5(self):
        G = nx.complete_graph(5)
        self.test(G, [(0, 1)], [(0, 1, 3 / math.log(4))])

    def test_P3(self):
        G = nx.path_graph(3)
        self.test(G, [(0, 2)], [(0, 2, 1 / math.log(2))])

    def test_S4(self):
        G = nx.star_graph(4)
        self.test(G, [(1, 2)], [(1, 2, 1 / math.log(4))])

    @pytest.mark.parametrize("graph_type", (nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph))
    def test_notimplemented(self, graph_type):
        assert pytest.raises(
            nx.NetworkXNotImplemented, self.func, graph_type([(0, 1), (1, 2)]), [(0, 2)]
        )

    def test_node_not_found(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (2, 3)])
        assert pytest.raises(nx.NodeNotFound, self.func, G, [(0, 4)])

    def test_no_common_neighbor(self):
        G = nx.Graph()
        G.add_nodes_from([0, 1])
        self.test(G, [(0, 1)], [(0, 1, 0)])

    def test_equal_nodes(self):
        G = nx.complete_graph(4)
        self.test(G, [(0, 0)], [(0, 0, 3 / math.log(3))])

    def test_all_nonexistent_edges(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (2, 3)])
        self.test(
            G, None, [(0, 3, 1 / math.log(2)), (1, 2, 1 / math.log(2)), (1, 3, 0)]
        )


class TestCommonNeighborCentrality:
    @classmethod
    def setup_class(cls):
        cls.func = staticmethod(nx.common_neighbor_centrality)
        cls.test = partial(_test_func, predict_func=cls.func)

    def test_K5(self):
        G = nx.complete_graph(5)
        self.test(G, [(0, 1)], [(0, 1, 3.0)], alpha=1)
        self.test(G, [(0, 1)], [(0, 1, 5.0)], alpha=0)

    def test_P3(self):
        G = nx.path_graph(3)
        self.test(G, [(0, 2)], [(0, 2, 1.25)], alpha=0.5)

    def test_S4(self):
        G = nx.star_graph(4)
        self.test(G, [(1, 2)], [(1, 2, 1.75)], alpha=0.5)

    @pytest.mark.parametrize("graph_type", (nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph))
    def test_notimplemented(self, graph_type):
        assert pytest.raises(
            nx.NetworkXNotImplemented, self.func, graph_type([(0, 1), (1, 2)]), [(0, 2)]
        )

    def test_node_u_not_found(self):
        G = nx.Graph()
        G.add_edges_from([(1, 3), (2, 3)])
        assert pytest.raises(nx.NodeNotFound, self.func, G, [(0, 1)])

    def test_node_v_not_found(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (2, 3)])
        assert pytest.raises(nx.NodeNotFound, self.func, G, [(0, 4)])

    def test_no_common_neighbor(self):
        G = nx.Graph()
        G.add_nodes_from([0, 1])
        self.test(G, [(0, 1)], [(0, 1, 0)])

    def test_equal_nodes(self):
        G = nx.complete_graph(4)
        assert pytest.raises(nx.NetworkXAlgorithmError, self.test, G, [(0, 0)], [])

    def test_equal_nodes_with_alpha_one_raises_error(self):
        G = nx.complete_graph(4)
        assert pytest.raises(
            nx.NetworkXAlgorithmError, self.test, G, [(0, 0)], [], alpha=1.0
        )

    def test_all_nonexistent_edges(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (2, 3)])
        self.test(G, None, [(0, 3, 1.5), (1, 2, 1.5), (1, 3, 2 / 3)], alpha=0.5)


class TestPreferentialAttachment:
    @classmethod
    def setup_class(cls):
        cls.func = staticmethod(nx.preferential_attachment)
        cls.test = partial(_test_func, predict_func=cls.func)

    def test_K5(self):
        G = nx.complete_graph(5)
        self.test(G, [(0, 1)], [(0, 1, 16)])

    def test_P3(self):
        G = nx.path_graph(3)
        self.test(G, [(0, 1)], [(0, 1, 2)])

    def test_S4(self):
        G = nx.star_graph(4)
        self.test(G, [(0, 2)], [(0, 2, 4)])

    @pytest.mark.parametrize("graph_type", (nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph))
    def test_notimplemented(self, graph_type):
        assert pytest.raises(
            nx.NetworkXNotImplemented, self.func, graph_type([(0, 1), (1, 2)]), [(0, 2)]
        )

    def test_node_not_found(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (2, 3)])
        assert pytest.raises(nx.NodeNotFound, self.func, G, [(0, 4)])

    def test_zero_degrees(self):
        G = nx.Graph()
        G.add_nodes_from([0, 1])
        self.test(G, [(0, 1)], [(0, 1, 0)])

    def test_all_nonexistent_edges(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (2, 3)])
        self.test(G, None, [(0, 3, 2), (1, 2, 2), (1, 3, 1)])


class TestCNSoundarajanHopcroft:
    @classmethod
    def setup_class(cls):
        cls.func = staticmethod(nx.cn_soundarajan_hopcroft)
        cls.test = partial(_test_func, predict_func=cls.func, community="community")

    def test_K5(self):
        G = nx.complete_graph(5)
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 0
        G.nodes[2]["community"] = 0
        G.nodes[3]["community"] = 0
        G.nodes[4]["community"] = 1
        self.test(G, [(0, 1)], [(0, 1, 5)])

    def test_P3(self):
        G = nx.path_graph(3)
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 1
        G.nodes[2]["community"] = 0
        self.test(G, [(0, 2)], [(0, 2, 1)])

    def test_S4(self):
        G = nx.star_graph(4)
        G.nodes[0]["community"] = 1
        G.nodes[1]["community"] = 1
        G.nodes[2]["community"] = 1
        G.nodes[3]["community"] = 0
        G.nodes[4]["community"] = 0
        self.test(G, [(1, 2)], [(1, 2, 2)])

    @pytest.mark.parametrize("graph_type", (nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph))
    def test_notimplemented(self, graph_type):
        G = graph_type([(0, 1), (1, 2)])
        G.add_nodes_from([0, 1, 2], community=0)
        assert pytest.raises(nx.NetworkXNotImplemented, self.func, G, [(0, 2)])

    def test_node_not_found(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (2, 3)])
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 1
        G.nodes[2]["community"] = 0
        G.nodes[3]["community"] = 0
        assert pytest.raises(nx.NodeNotFound, self.func, G, [(0, 4)])

    def test_no_common_neighbor(self):
        G = nx.Graph()
        G.add_nodes_from([0, 1])
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 0
        self.test(G, [(0, 1)], [(0, 1, 0)])

    def test_equal_nodes(self):
        G = nx.complete_graph(3)
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 0
        G.nodes[2]["community"] = 0
        self.test(G, [(0, 0)], [(0, 0, 4)])

    def test_different_community(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (1, 3), (2, 3)])
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 0
        G.nodes[2]["community"] = 0
        G.nodes[3]["community"] = 1
        self.test(G, [(0, 3)], [(0, 3, 2)])

    def test_no_community_information(self):
        G = nx.complete_graph(5)
        assert pytest.raises(nx.NetworkXAlgorithmError, list, self.func(G, [(0, 1)]))

    def test_insufficient_community_information(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (1, 3), (2, 3)])
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 0
        G.nodes[3]["community"] = 0
        assert pytest.raises(nx.NetworkXAlgorithmError, list, self.func(G, [(0, 3)]))

    def test_sufficient_community_information(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2), (1, 3), (2, 4), (3, 4), (4, 5)])
        G.nodes[1]["community"] = 0
        G.nodes[2]["community"] = 0
        G.nodes[3]["community"] = 0
        G.nodes[4]["community"] = 0
        self.test(G, [(1, 4)], [(1, 4, 4)])

    def test_custom_community_attribute_name(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (1, 3), (2, 3)])
        G.nodes[0]["cmty"] = 0
        G.nodes[1]["cmty"] = 0
        G.nodes[2]["cmty"] = 0
        G.nodes[3]["cmty"] = 1
        self.test(G, [(0, 3)], [(0, 3, 2)], community="cmty")

    def test_all_nonexistent_edges(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (2, 3)])
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 1
        G.nodes[2]["community"] = 0
        G.nodes[3]["community"] = 0
        self.test(G, None, [(0, 3, 2), (1, 2, 1), (1, 3, 0)])


class TestRAIndexSoundarajanHopcroft:
    @classmethod
    def setup_class(cls):
        cls.func = staticmethod(nx.ra_index_soundarajan_hopcroft)
        cls.test = partial(_test_func, predict_func=cls.func, community="community")

    def test_K5(self):
        G = nx.complete_graph(5)
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 0
        G.nodes[2]["community"] = 0
        G.nodes[3]["community"] = 0
        G.nodes[4]["community"] = 1
        self.test(G, [(0, 1)], [(0, 1, 0.5)])

    def test_P3(self):
        G = nx.path_graph(3)
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 1
        G.nodes[2]["community"] = 0
        self.test(G, [(0, 2)], [(0, 2, 0)])

    def test_S4(self):
        G = nx.star_graph(4)
        G.nodes[0]["community"] = 1
        G.nodes[1]["community"] = 1
        G.nodes[2]["community"] = 1
        G.nodes[3]["community"] = 0
        G.nodes[4]["community"] = 0
        self.test(G, [(1, 2)], [(1, 2, 0.25)])

    @pytest.mark.parametrize("graph_type", (nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph))
    def test_notimplemented(self, graph_type):
        G = graph_type([(0, 1), (1, 2)])
        G.add_nodes_from([0, 1, 2], community=0)
        assert pytest.raises(nx.NetworkXNotImplemented, self.func, G, [(0, 2)])

    def test_node_not_found(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (2, 3)])
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 1
        G.nodes[2]["community"] = 0
        G.nodes[3]["community"] = 0
        assert pytest.raises(nx.NodeNotFound, self.func, G, [(0, 4)])

    def test_no_common_neighbor(self):
        G = nx.Graph()
        G.add_nodes_from([0, 1])
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 0
        self.test(G, [(0, 1)], [(0, 1, 0)])

    def test_equal_nodes(self):
        G = nx.complete_graph(3)
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 0
        G.nodes[2]["community"] = 0
        self.test(G, [(0, 0)], [(0, 0, 1)])

    def test_different_community(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (1, 3), (2, 3)])
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 0
        G.nodes[2]["community"] = 0
        G.nodes[3]["community"] = 1
        self.test(G, [(0, 3)], [(0, 3, 0)])

    def test_no_community_information(self):
        G = nx.complete_graph(5)
        assert pytest.raises(nx.NetworkXAlgorithmError, list, self.func(G, [(0, 1)]))

    def test_insufficient_community_information(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (1, 3), (2, 3)])
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 0
        G.nodes[3]["community"] = 0
        assert pytest.raises(nx.NetworkXAlgorithmError, list, self.func(G, [(0, 3)]))

    def test_sufficient_community_information(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2), (1, 3), (2, 4), (3, 4), (4, 5)])
        G.nodes[1]["community"] = 0
        G.nodes[2]["community"] = 0
        G.nodes[3]["community"] = 0
        G.nodes[4]["community"] = 0
        self.test(G, [(1, 4)], [(1, 4, 1)])

    def test_custom_community_attribute_name(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (1, 3), (2, 3)])
        G.nodes[0]["cmty"] = 0
        G.nodes[1]["cmty"] = 0
        G.nodes[2]["cmty"] = 0
        G.nodes[3]["cmty"] = 1
        self.test(G, [(0, 3)], [(0, 3, 0)], community="cmty")

    def test_all_nonexistent_edges(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (2, 3)])
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 1
        G.nodes[2]["community"] = 0
        G.nodes[3]["community"] = 0
        self.test(G, None, [(0, 3, 0.5), (1, 2, 0), (1, 3, 0)])


class TestWithinInterCluster:
    @classmethod
    def setup_class(cls):
        cls.delta = 0.001
        cls.func = staticmethod(nx.within_inter_cluster)
        cls.test = partial(
            _test_func, predict_func=cls.func, delta=cls.delta, community="community"
        )

    def test_K5(self):
        G = nx.complete_graph(5)
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 0
        G.nodes[2]["community"] = 0
        G.nodes[3]["community"] = 0
        G.nodes[4]["community"] = 1
        self.test(G, [(0, 1)], [(0, 1, 2 / (1 + self.delta))])

    def test_P3(self):
        G = nx.path_graph(3)
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 1
        G.nodes[2]["community"] = 0
        self.test(G, [(0, 2)], [(0, 2, 0)])

    def test_S4(self):
        G = nx.star_graph(4)
        G.nodes[0]["community"] = 1
        G.nodes[1]["community"] = 1
        G.nodes[2]["community"] = 1
        G.nodes[3]["community"] = 0
        G.nodes[4]["community"] = 0
        self.test(G, [(1, 2)], [(1, 2, 1 / self.delta)])

    @pytest.mark.parametrize("graph_type", (nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph))
    def test_notimplemented(self, graph_type):
        G = graph_type([(0, 1), (1, 2)])
        G.add_nodes_from([0, 1, 2], community=0)
        assert pytest.raises(nx.NetworkXNotImplemented, self.func, G, [(0, 2)])

    def test_node_not_found(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (2, 3)])
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 1
        G.nodes[2]["community"] = 0
        G.nodes[3]["community"] = 0
        assert pytest.raises(nx.NodeNotFound, self.func, G, [(0, 4)])

    def test_no_common_neighbor(self):
        G = nx.Graph()
        G.add_nodes_from([0, 1])
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 0
        self.test(G, [(0, 1)], [(0, 1, 0)])

    def test_equal_nodes(self):
        G = nx.complete_graph(3)
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 0
        G.nodes[2]["community"] = 0
        self.test(G, [(0, 0)], [(0, 0, 2 / self.delta)])

    def test_different_community(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (1, 3), (2, 3)])
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 0
        G.nodes[2]["community"] = 0
        G.nodes[3]["community"] = 1
        self.test(G, [(0, 3)], [(0, 3, 0)])

    def test_no_inter_cluster_common_neighbor(self):
        G = nx.complete_graph(4)
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 0
        G.nodes[2]["community"] = 0
        G.nodes[3]["community"] = 0
        self.test(G, [(0, 3)], [(0, 3, 2 / self.delta)])

    def test_no_community_information(self):
        G = nx.complete_graph(5)
        assert pytest.raises(nx.NetworkXAlgorithmError, list, self.func(G, [(0, 1)]))

    def test_insufficient_community_information(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (1, 3), (2, 3)])
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 0
        G.nodes[3]["community"] = 0
        assert pytest.raises(nx.NetworkXAlgorithmError, list, self.func(G, [(0, 3)]))

    def test_sufficient_community_information(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2), (1, 3), (2, 4), (3, 4), (4, 5)])
        G.nodes[1]["community"] = 0
        G.nodes[2]["community"] = 0
        G.nodes[3]["community"] = 0
        G.nodes[4]["community"] = 0
        self.test(G, [(1, 4)], [(1, 4, 2 / self.delta)])

    def test_invalid_delta(self):
        G = nx.complete_graph(3)
        G.add_nodes_from([0, 1, 2], community=0)
        assert pytest.raises(nx.NetworkXAlgorithmError, self.func, G, [(0, 1)], 0)
        assert pytest.raises(nx.NetworkXAlgorithmError, self.func, G, [(0, 1)], -0.5)

    def test_custom_community_attribute_name(self):
        G = nx.complete_graph(4)
        G.nodes[0]["cmty"] = 0
        G.nodes[1]["cmty"] = 0
        G.nodes[2]["cmty"] = 0
        G.nodes[3]["cmty"] = 0
        self.test(G, [(0, 3)], [(0, 3, 2 / self.delta)], community="cmty")

    def test_all_nonexistent_edges(self):
        G = nx.Graph()
        G.add_edges_from([(0, 1), (0, 2), (2, 3)])
        G.nodes[0]["community"] = 0
        G.nodes[1]["community"] = 1
        G.nodes[2]["community"] = 0
        G.nodes[3]["community"] = 0
        self.test(G, None, [(0, 3, 1 / self.delta), (1, 2, 0), (1, 3, 0)])
