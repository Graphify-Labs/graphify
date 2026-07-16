import networkx as nx

from .base_test import BaseTestAttributeMixing, BaseTestDegreeMixing


class TestAttributeMixingXY(BaseTestAttributeMixing):
    def test_node_attribute_xy_undirected(self):
        attrxy = sorted(nx.node_attribute_xy(self.G, "fish"))
        attrxy_result = sorted(
            [
                ("one", "one"),
                ("one", "one"),
                ("two", "two"),
                ("two", "two"),
                ("one", "red"),
                ("red", "one"),
                ("blue", "two"),
                ("two", "blue"),
            ]
        )
        assert attrxy == attrxy_result

    def test_node_attribute_xy_undirected_nodes(self):
        attrxy = sorted(nx.node_attribute_xy(self.G, "fish", nodes=["one", "yellow"]))
        attrxy_result = sorted([])
        assert attrxy == attrxy_result

    def test_node_attribute_xy_directed(self):
        attrxy = sorted(nx.node_attribute_xy(self.D, "fish"))
        attrxy_result = sorted(
            [("one", "one"), ("two", "two"), ("one", "red"), ("two", "blue")]
        )
        assert attrxy == attrxy_result

    def test_node_attribute_xy_multigraph(self):
        attrxy = sorted(nx.node_attribute_xy(self.M, "fish"))
        attrxy_result = [
            ("one", "one"),
            ("one", "one"),
            ("one", "one"),
            ("one", "one"),
            ("two", "two"),
            ("two", "two"),
        ]
        assert attrxy == attrxy_result

    def test_node_attribute_xy_selfloop(self):
        attrxy = sorted(nx.node_attribute_xy(self.S, "fish"))
        attrxy_result = [("one", "one"), ("two", "two")]
        assert attrxy == attrxy_result


class TestDegreeMixingXY(BaseTestDegreeMixing):
    def test_node_degree_xy_undirected(self):
        xy = sorted(nx.node_degree_xy(self.P4))
        xy_result = sorted([(1, 2), (2, 1), (2, 2), (2, 2), (1, 2), (2, 1)])
        assert xy == xy_result

    def test_node_degree_xy_undirected_nodes(self):
        xy = sorted(nx.node_degree_xy(self.P4, nodes=[0, 1, -1]))
        xy_result = sorted([(1, 2), (2, 1)])
        assert xy == xy_result

    def test_node_degree_xy_directed(self):
        xy = sorted(nx.node_degree_xy(self.D))
        xy_result = sorted([(2, 1), (2, 3), (1, 3), (1, 3)])
        assert xy == xy_result

    def test_node_degree_xy_multigraph(self):
        xy = sorted(nx.node_degree_xy(self.M))
        xy_result = sorted(
            [(2, 3), (2, 3), (3, 2), (3, 2), (2, 3), (3, 2), (1, 2), (2, 1)]
        )
        assert xy == xy_result

    def test_node_degree_xy_selfloop(self):
        xy = sorted(nx.node_degree_xy(self.S))
        xy_result = sorted([(2, 2), (2, 2)])
        assert xy == xy_result

    def test_node_degree_xy_weighted(self):
        G = nx.Graph()
        G.add_edge(1, 2, weight=7)
        G.add_edge(2, 3, weight=10)
        xy = sorted(nx.node_degree_xy(G, weight="weight"))
        xy_result = sorted([(7, 17), (17, 10), (17, 7), (10, 17)])
        assert xy == xy_result
