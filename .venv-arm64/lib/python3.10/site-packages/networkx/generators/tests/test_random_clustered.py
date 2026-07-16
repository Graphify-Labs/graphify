import pytest

import networkx as nx


class TestRandomClusteredGraph:
    def test_custom_joint_degree_sequence(self):
        node = [1, 1, 1, 2, 1, 2, 0, 0]
        tri = [0, 0, 0, 0, 0, 1, 1, 1]
        joint_degree_sequence = zip(node, tri)
        G = nx.random_clustered_graph(joint_degree_sequence)
        assert G.number_of_nodes() == 8
        assert G.number_of_edges() == 7

    def test_tuple_joint_degree_sequence(self):
        G = nx.random_clustered_graph([(1, 2), (2, 1), (1, 1), (1, 1), (1, 1), (2, 0)])
        assert G.number_of_nodes() == 6
        assert G.number_of_edges() == 10

    def test_invalid_joint_degree_sequence_type(self):
        with pytest.raises(nx.NetworkXError, match="Invalid degree sequence"):
            nx.random_clustered_graph([[1, 1], [2, 1], [0, 1]])

    def test_invalid_joint_degree_sequence_value(self):
        with pytest.raises(nx.NetworkXError, match="Invalid degree sequence"):
            nx.random_clustered_graph([[1, 1], [1, 2], [0, 1]])

    def test_directed_graph_raises_error(self):
        with pytest.raises(nx.NetworkXError, match="Directed Graph not supported"):
            nx.random_clustered_graph(
                [(1, 2), (2, 1), (1, 1), (1, 1), (1, 1), (2, 0)],
                create_using=nx.DiGraph,
            )
