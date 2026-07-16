import networkx as nx

from .test_digraph import BaseDiGraphTester
from .test_digraph import TestDiGraph as _TestDiGraph
from .test_graph import BaseGraphTester
from .test_graph import TestGraph as _TestGraph
from .test_multidigraph import TestMultiDiGraph as _TestMultiDiGraph
from .test_multigraph import TestMultiGraph as _TestMultiGraph


def test_factories():
    class mydict1(dict):
        pass

    class mydict2(dict):
        pass

    class mydict3(dict):
        pass

    class mydict4(dict):
        pass

    class mydict5(dict):
        pass

    for Graph in (nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph):
        # print("testing class: ", Graph.__name__)
        class MyGraph(Graph):
            node_dict_factory = mydict1
            adjlist_outer_dict_factory = mydict2
            adjlist_inner_dict_factory = mydict3
            edge_key_dict_factory = mydict4
            edge_attr_dict_factory = mydict5

        G = MyGraph()
        assert isinstance(G._node, mydict1)
        assert isinstance(G._adj, mydict2)
        G.add_node(1)
        assert isinstance(G._adj[1], mydict3)
        if G.is_directed():
            assert isinstance(G._pred, mydict2)
            assert isinstance(G._succ, mydict2)
            assert isinstance(G._pred[1], mydict3)
        G.add_edge(1, 2)
        if G.is_multigraph():
            assert isinstance(G._adj[1][2], mydict4)
            assert isinstance(G._adj[1][2][0], mydict5)
        else:
            assert isinstance(G._adj[1][2], mydict5)


class TestSpecialGraph(_TestGraph):
    def setup_method(self):
        _TestGraph.setup_method(self)
        self.Graph = nx.Graph


class TestThinGraph(BaseGraphTester):
    def setup_method(self):
        all_edge_dict = {"weight": 1}

        class MyGraph(nx.Graph):
            def edge_attr_dict_factory(self):
                return all_edge_dict

        self.Graph = MyGraph
        # build dict-of-dict-of-dict K3
        ed1, ed2, ed3 = (all_edge_dict, all_edge_dict, all_edge_dict)
        self.k3adj = {0: {1: ed1, 2: ed2}, 1: {0: ed1, 2: ed3}, 2: {0: ed2, 1: ed3}}
        self.k3edges = [(0, 1), (0, 2), (1, 2)]
        self.k3nodes = [0, 1, 2]
        self.K3 = self.Graph()
        self.K3._adj = self.k3adj
        self.K3._node = {}
        self.K3._node[0] = {}
        self.K3._node[1] = {}
        self.K3._node[2] = {}


class TestSpecialDiGraph(_TestDiGraph):
    def setup_method(self):
        _TestDiGraph.setup_method(self)
        self.Graph = nx.DiGraph


class TestThinDiGraph(BaseDiGraphTester):
    def setup_method(self):
        all_edge_dict = {"weight": 1}

        class MyGraph(nx.DiGraph):
            def edge_attr_dict_factory(self):
                return all_edge_dict

        self.Graph = MyGraph
        # build dict-of-dict-of-dict K3
        ed1, ed2, ed3 = (all_edge_dict, all_edge_dict, all_edge_dict)
        ed4, ed5, ed6 = (all_edge_dict, all_edge_dict, all_edge_dict)
        self.k3adj = {0: {1: ed1, 2: ed2}, 1: {0: ed3, 2: ed4}, 2: {0: ed5, 1: ed6}}
        self.k3edges = [(0, 1), (0, 2), (1, 2)]
        self.k3nodes = [0, 1, 2]
        self.K3 = self.Graph()
        self.K3._succ = self.k3adj
        # K3._adj is synced with K3._succ
        self.K3._pred = {0: {1: ed3, 2: ed5}, 1: {0: ed1, 2: ed6}, 2: {0: ed2, 1: ed4}}
        self.K3._node = {}
        self.K3._node[0] = {}
        self.K3._node[1] = {}
        self.K3._node[2] = {}

        ed1, ed2 = (all_edge_dict, all_edge_dict)
        self.P3 = self.Graph()
        self.P3._succ = {0: {1: ed1}, 1: {2: ed2}, 2: {}}
        # P3._adj is synced with P3._succ
        self.P3._pred = {0: {}, 1: {0: ed1}, 2: {1: ed2}}
        self.P3._node = {}
        self.P3._node[0] = {}
        self.P3._node[1] = {}
        self.P3._node[2] = {}


class TestSpecialMultiGraph(_TestMultiGraph):
    def setup_method(self):
        _TestMultiGraph.setup_method(self)
        self.Graph = nx.MultiGraph


class TestSpecialMultiDiGraph(_TestMultiDiGraph):
    def setup_method(self):
        _TestMultiDiGraph.setup_method(self)
        self.Graph = nx.MultiDiGraph
