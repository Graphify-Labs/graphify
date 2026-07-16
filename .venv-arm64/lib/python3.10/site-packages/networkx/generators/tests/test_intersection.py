import pytest

import networkx as nx


class TestIntersectionGraph:
    def test_random_intersection_graph(self):
        G = nx.uniform_random_intersection_graph(10, 5, 0.5)
        assert len(G) == 10

    def test_k_random_intersection_graph(self):
        G = nx.k_random_intersection_graph(10, 5, 2)
        assert len(G) == 10

    def test_k_random_intersection_graph_seeded(self):
        G = nx.k_random_intersection_graph(10, 5, 2, seed=1234)
        assert len(G) == 10

    def test_general_random_intersection_graph(self):
        G = nx.general_random_intersection_graph(10, 5, [0.1, 0.2, 0.2, 0.1, 0.1])
        assert len(G) == 10
        pytest.raises(
            ValueError,
            nx.general_random_intersection_graph,
            10,
            5,
            [0.1, 0.2, 0.2, 0.1],
        )
