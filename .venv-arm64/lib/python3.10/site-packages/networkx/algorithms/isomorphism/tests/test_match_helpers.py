from operator import eq

import networkx as nx
from networkx.algorithms import isomorphism as iso


def test_categorical_node_match():
    nm = iso.categorical_node_match(["x", "y", "z"], [None] * 3)
    assert nm({"x": 1, "y": 2, "z": 3}, {"x": 1, "y": 2, "z": 3})
    assert not nm({"x": 1, "y": 2, "z": 2}, {"x": 1, "y": 2, "z": 1})


class TestGenericMultiEdgeMatch:
    def setup_method(self):
        self.G1 = nx.MultiDiGraph()
        self.G2 = nx.MultiDiGraph()
        self.G3 = nx.MultiDiGraph()
        self.G4 = nx.MultiDiGraph()
        attr_dict1 = {"id": "edge1", "minFlow": 0, "maxFlow": 10}
        attr_dict2 = {"id": "edge2", "minFlow": -3, "maxFlow": 7}
        attr_dict3 = {"id": "edge3", "minFlow": 13, "maxFlow": 117}
        attr_dict4 = {"id": "edge4", "minFlow": 13, "maxFlow": 117}
        attr_dict5 = {"id": "edge5", "minFlow": 8, "maxFlow": 12}
        attr_dict6 = {"id": "edge6", "minFlow": 8, "maxFlow": 12}
        for attr_dict in [
            attr_dict1,
            attr_dict2,
            attr_dict3,
            attr_dict4,
            attr_dict5,
            attr_dict6,
        ]:
            self.G1.add_edge(1, 2, **attr_dict)
        for attr_dict in [
            attr_dict5,
            attr_dict3,
            attr_dict6,
            attr_dict1,
            attr_dict4,
            attr_dict2,
        ]:
            self.G2.add_edge(2, 3, **attr_dict)
        for attr_dict in [attr_dict3, attr_dict5]:
            self.G3.add_edge(3, 4, **attr_dict)
        for attr_dict in [attr_dict6, attr_dict4]:
            self.G4.add_edge(4, 5, **attr_dict)

    def test_generic_multiedge_match(self):
        full_match = iso.generic_multiedge_match(
            ["id", "flowMin", "flowMax"], [None] * 3, [eq] * 3
        )
        flow_match = iso.generic_multiedge_match(
            ["flowMin", "flowMax"], [None] * 2, [eq] * 2
        )
        min_flow_match = iso.generic_multiedge_match("flowMin", None, eq)
        id_match = iso.generic_multiedge_match("id", None, eq)
        assert flow_match(self.G1[1][2], self.G2[2][3])
        assert min_flow_match(self.G1[1][2], self.G2[2][3])
        assert id_match(self.G1[1][2], self.G2[2][3])
        assert full_match(self.G1[1][2], self.G2[2][3])
        assert flow_match(self.G3[3][4], self.G4[4][5])
        assert min_flow_match(self.G3[3][4], self.G4[4][5])
        assert not id_match(self.G3[3][4], self.G4[4][5])
        assert not full_match(self.G3[3][4], self.G4[4][5])
