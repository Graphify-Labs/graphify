import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

import networkx as nx


class TestFlowClosenessCentrality:
    def test_K4(self):
        """Closeness centrality: K4"""
        G = nx.complete_graph(4)
        b = nx.current_flow_closeness_centrality(G)
        b_answer = {0: 2.0 / 3, 1: 2.0 / 3, 2: 2.0 / 3, 3: 2.0 / 3}
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-7)

    def test_P4(self):
        """Closeness centrality: P4"""
        G = nx.path_graph(4)
        b = nx.current_flow_closeness_centrality(G)
        b_answer = {0: 1.0 / 6, 1: 1.0 / 4, 2: 1.0 / 4, 3: 1.0 / 6}
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-7)

    def test_star(self):
        """Closeness centrality: star"""
        G = nx.Graph()
        nx.add_star(G, ["a", "b", "c", "d"])
        b = nx.current_flow_closeness_centrality(G)
        b_answer = {"a": 1.0 / 3, "b": 0.6 / 3, "c": 0.6 / 3, "d": 0.6 / 3}
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-7)

    def test_current_flow_closeness_centrality_not_connected(self):
        G = nx.Graph()
        G.add_nodes_from([1, 2, 3])
        with pytest.raises(nx.NetworkXError):
            nx.current_flow_closeness_centrality(G)


class TestWeightedFlowClosenessCentrality:
    pass
