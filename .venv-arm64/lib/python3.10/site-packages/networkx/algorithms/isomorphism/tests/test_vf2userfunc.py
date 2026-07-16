"""
Tests for VF2 isomorphism algorithm for weighted graphs.
"""

import math
from operator import eq

import networkx as nx
import networkx.algorithms.isomorphism as iso


def test_simple():
    # 16 simple tests
    w = "weight"
    edges = [(0, 0, 1), (0, 0, 1.5), (0, 1, 2), (1, 0, 3)]
    for g1 in [nx.Graph(), nx.DiGraph(), nx.MultiGraph(), nx.MultiDiGraph()]:
        g1.add_weighted_edges_from(edges)
        g2 = g1.subgraph(g1.nodes())
        if g1.is_multigraph():
            em = iso.numerical_multiedge_match("weight", 1)
        else:
            em = iso.numerical_edge_match("weight", 1)
        assert nx.is_isomorphic(g1, g2, edge_match=em)

        for mod1, mod2 in [(False, True), (True, False), (True, True)]:
            # mod1 tests a regular edge
            # mod2 tests a selfloop
            if g2.is_multigraph():
                if mod1:
                    data1 = {0: {"weight": 10}}
                if mod2:
                    data2 = {0: {"weight": 1}, 1: {"weight": 2.5}}
            else:
                if mod1:
                    data1 = {"weight": 10}
                if mod2:
                    data2 = {"weight": 2.5}

            g2 = g1.subgraph(g1.nodes()).copy()
            if mod1:
                if not g1.is_directed():
                    g2._adj[1][0] = data1
                    g2._adj[0][1] = data1
                else:
                    g2._succ[1][0] = data1
                    g2._pred[0][1] = data1
            if mod2:
                if not g1.is_directed():
                    g2._adj[0][0] = data2
                else:
                    g2._succ[0][0] = data2
                    g2._pred[0][0] = data2

            assert not nx.is_isomorphic(g1, g2, edge_match=em)


def test_weightkey():
    g1 = nx.DiGraph()
    g2 = nx.DiGraph()

    g1.add_edge("A", "B", weight=1)
    g2.add_edge("C", "D", weight=0)

    assert nx.is_isomorphic(g1, g2)
    em = iso.numerical_edge_match("nonexistent attribute", 1)
    assert nx.is_isomorphic(g1, g2, edge_match=em)
    em = iso.numerical_edge_match("weight", 1)
    assert not nx.is_isomorphic(g1, g2, edge_match=em)

    g2 = nx.DiGraph()
    g2.add_edge("C", "D")
    assert nx.is_isomorphic(g1, g2, edge_match=em)


class TestNodeMatch_Graph:
    def setup_method(self):
        self.g1 = nx.Graph()
        self.g2 = nx.Graph()
        self.build()

    def build(self):
        self.nm = iso.categorical_node_match("color", "")
        self.em = iso.numerical_edge_match("weight", 1)

        self.g1.add_node("A", color="red")
        self.g2.add_node("C", color="blue")

        self.g1.add_edge("A", "B", weight=1)
        self.g2.add_edge("C", "D", weight=1)

    def test_noweight_nocolor(self):
        assert nx.is_isomorphic(self.g1, self.g2)

    def test_color1(self):
        assert not nx.is_isomorphic(self.g1, self.g2, node_match=self.nm)

    def test_color2(self):
        self.g1.nodes["A"]["color"] = "blue"
        assert nx.is_isomorphic(self.g1, self.g2, node_match=self.nm)

    def test_weight1(self):
        assert nx.is_isomorphic(self.g1, self.g2, edge_match=self.em)

    def test_weight2(self):
        self.g1.add_edge("A", "B", weight=2)
        assert not nx.is_isomorphic(self.g1, self.g2, edge_match=self.em)

    def test_colorsandweights1(self):
        iso = nx.is_isomorphic(self.g1, self.g2, node_match=self.nm, edge_match=self.em)
        assert not iso

    def test_colorsandweights2(self):
        self.g1.nodes["A"]["color"] = "blue"
        iso = nx.is_isomorphic(self.g1, self.g2, node_match=self.nm, edge_match=self.em)
        assert iso

    def test_colorsandweights3(self):
        # make the weights disagree
        self.g1.add_edge("A", "B", weight=2)
        assert not nx.is_isomorphic(
            self.g1, self.g2, node_match=self.nm, edge_match=self.em
        )


class TestEdgeMatch_MultiGraph:
    def setup_method(self):
        self.g1 = nx.MultiGraph()
        self.g2 = nx.MultiGraph()
        self.GM = iso.MultiGraphMatcher
        self.build()

    def build(self):
        g1 = self.g1
        g2 = self.g2

        # We will assume integer weights only.
        g1.add_edge("A", "B", color="green", weight=0, size=0.5)
        g1.add_edge("A", "B", color="red", weight=1, size=0.35)
        g1.add_edge("A", "B", color="red", weight=2, size=0.65)

        g2.add_edge("C", "D", color="green", weight=1, size=0.5)
        g2.add_edge("C", "D", color="red", weight=0, size=0.45)
        g2.add_edge("C", "D", color="red", weight=2, size=0.65)

        if g1.is_multigraph():
            self.em = iso.numerical_multiedge_match("weight", 1)
            self.emc = iso.categorical_multiedge_match("color", "")
            self.emcm = iso.categorical_multiedge_match(["color", "weight"], ["", 1])
            self.emg1 = iso.generic_multiedge_match("color", "red", eq)
            self.emg2 = iso.generic_multiedge_match(
                ["color", "weight", "size"],
                ["red", 1, 0.5],
                [eq, eq, math.isclose],
            )
        else:
            self.em = iso.numerical_edge_match("weight", 1)
            self.emc = iso.categorical_edge_match("color", "")
            self.emcm = iso.categorical_edge_match(["color", "weight"], ["", 1])
            self.emg1 = iso.generic_multiedge_match("color", "red", eq)
            self.emg2 = iso.generic_edge_match(
                ["color", "weight", "size"],
                ["red", 1, 0.5],
                [eq, eq, math.isclose],
            )

    def test_weights_only(self):
        assert nx.is_isomorphic(self.g1, self.g2, edge_match=self.em)

    def test_colors_only(self):
        gm = self.GM(self.g1, self.g2, edge_match=self.emc)
        assert gm.is_isomorphic()

    def test_colorsandweights(self):
        gm = self.GM(self.g1, self.g2, edge_match=self.emcm)
        assert not gm.is_isomorphic()

    def test_generic1(self):
        gm = self.GM(self.g1, self.g2, edge_match=self.emg1)
        assert gm.is_isomorphic()

    def test_generic2(self):
        gm = self.GM(self.g1, self.g2, edge_match=self.emg2)
        assert not gm.is_isomorphic()


class TestEdgeMatch_DiGraph(TestNodeMatch_Graph):
    def setup_method(self):
        TestNodeMatch_Graph.setup_method(self)
        self.g1 = nx.DiGraph()
        self.g2 = nx.DiGraph()
        self.build()


class TestEdgeMatch_MultiDiGraph(TestEdgeMatch_MultiGraph):
    def setup_method(self):
        TestEdgeMatch_MultiGraph.setup_method(self)
        self.g1 = nx.MultiDiGraph()
        self.g2 = nx.MultiDiGraph()
        self.GM = iso.MultiDiGraphMatcher
        self.build()
