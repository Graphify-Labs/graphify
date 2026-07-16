import pytest

import networkx as nx


class TestReciprocity:
    # test overall reciprocity by passing whole graph
    def test_reciprocity_digraph(self):
        DG = nx.DiGraph([(1, 2), (2, 1)])
        reciprocity = nx.reciprocity(DG)
        assert reciprocity == 1.0

    # test empty graph's overall reciprocity which will throw an error
    def test_overall_reciprocity_empty_graph(self):
        with pytest.raises(nx.NetworkXError):
            DG = nx.DiGraph()
            nx.overall_reciprocity(DG)

    # test for reciprocity for a list of nodes
    def test_reciprocity_graph_nodes(self):
        DG = nx.DiGraph([(1, 2), (2, 3), (3, 2)])
        reciprocity = nx.reciprocity(DG, [1, 2])
        expected_reciprocity = {1: 0.0, 2: 0.6666666666666666}
        assert reciprocity == expected_reciprocity

    # test for reciprocity for a single node
    def test_reciprocity_graph_node(self):
        DG = nx.DiGraph([(1, 2), (2, 3), (3, 2)])
        reciprocity = nx.reciprocity(DG, 2)
        assert reciprocity == 0.6666666666666666

    # test for reciprocity for an isolated node
    def test_reciprocity_graph_isolated_nodes(self):
        with pytest.raises(nx.NetworkXError):
            DG = nx.DiGraph([(1, 2)])
            DG.add_node(4)
            nx.reciprocity(DG, 4)
