import pytest

import networkx as nx
from networkx import approximate_current_flow_betweenness_centrality as approximate_cfbc
from networkx import edge_current_flow_betweenness_centrality as edge_current_flow

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")


class TestFlowBetweennessCentrality:
    def test_K4_normalized(self):
        """Betweenness centrality: K4"""
        G = nx.complete_graph(4)
        b = nx.current_flow_betweenness_centrality(G, normalized=True)
        b_answer = {0: 0.25, 1: 0.25, 2: 0.25, 3: 0.25}
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-7)
        G.add_edge(0, 1, weight=0.5, other=0.3)
        b = nx.current_flow_betweenness_centrality(G, normalized=True, weight=None)
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-7)
        wb_answer = {0: 0.2222222, 1: 0.2222222, 2: 0.30555555, 3: 0.30555555}
        b = nx.current_flow_betweenness_centrality(G, normalized=True, weight="weight")
        for n in sorted(G):
            assert b[n] == pytest.approx(wb_answer[n], abs=1e-7)
        wb_answer = {0: 0.2051282, 1: 0.2051282, 2: 0.33974358, 3: 0.33974358}
        b = nx.current_flow_betweenness_centrality(G, normalized=True, weight="other")
        for n in sorted(G):
            assert b[n] == pytest.approx(wb_answer[n], abs=1e-7)

    def test_K4(self):
        """Betweenness centrality: K4"""
        G = nx.complete_graph(4)
        for solver in ["full", "lu", "cg"]:
            b = nx.current_flow_betweenness_centrality(
                G, normalized=False, solver=solver
            )
            b_answer = {0: 0.75, 1: 0.75, 2: 0.75, 3: 0.75}
            for n in sorted(G):
                assert b[n] == pytest.approx(b_answer[n], abs=1e-7)

    def test_P4_normalized(self):
        """Betweenness centrality: P4 normalized"""
        G = nx.path_graph(4)
        b = nx.current_flow_betweenness_centrality(G, normalized=True)
        b_answer = {0: 0, 1: 2.0 / 3, 2: 2.0 / 3, 3: 0}
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-7)

    def test_P4(self):
        """Betweenness centrality: P4"""
        G = nx.path_graph(4)
        b = nx.current_flow_betweenness_centrality(G, normalized=False)
        b_answer = {0: 0, 1: 2, 2: 2, 3: 0}
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-7)

    def test_star(self):
        """Betweenness centrality: star"""
        G = nx.Graph()
        nx.add_star(G, ["a", "b", "c", "d"])
        b = nx.current_flow_betweenness_centrality(G, normalized=True)
        b_answer = {"a": 1.0, "b": 0.0, "c": 0.0, "d": 0.0}
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-7)

    def test_solvers2(self):
        """Betweenness centrality: alternate solvers"""
        G = nx.complete_graph(4)
        for solver in ["full", "lu", "cg"]:
            b = nx.current_flow_betweenness_centrality(
                G, normalized=False, solver=solver
            )
            b_answer = {0: 0.75, 1: 0.75, 2: 0.75, 3: 0.75}
            for n in sorted(G):
                assert b[n] == pytest.approx(b_answer[n], abs=1e-7)


class TestApproximateFlowBetweennessCentrality:
    def test_K4_normalized(self):
        "Approximate current-flow betweenness centrality: K4 normalized"
        G = nx.complete_graph(4)
        b = nx.current_flow_betweenness_centrality(G, normalized=True)
        epsilon = 0.1
        ba = approximate_cfbc(G, normalized=True, epsilon=0.5 * epsilon)
        for n in sorted(G):
            np.testing.assert_allclose(b[n], ba[n], atol=epsilon)

    def test_K4(self):
        "Approximate current-flow betweenness centrality: K4"
        G = nx.complete_graph(4)
        b = nx.current_flow_betweenness_centrality(G, normalized=False)
        epsilon = 0.1
        ba = approximate_cfbc(G, normalized=False, epsilon=0.5 * epsilon)
        for n in sorted(G):
            np.testing.assert_allclose(b[n], ba[n], atol=epsilon * len(G) ** 2)

    def test_star(self):
        "Approximate current-flow betweenness centrality: star"
        G = nx.Graph()
        nx.add_star(G, ["a", "b", "c", "d"])
        b = nx.current_flow_betweenness_centrality(G, normalized=True)
        epsilon = 0.1
        ba = approximate_cfbc(G, normalized=True, epsilon=0.5 * epsilon)
        for n in sorted(G):
            np.testing.assert_allclose(b[n], ba[n], atol=epsilon)

    def test_grid(self):
        "Approximate current-flow betweenness centrality: 2d grid"
        G = nx.grid_2d_graph(4, 4)
        b = nx.current_flow_betweenness_centrality(G, normalized=True)
        epsilon = 0.1
        ba = approximate_cfbc(G, normalized=True, epsilon=0.5 * epsilon)
        for n in sorted(G):
            np.testing.assert_allclose(b[n], ba[n], atol=epsilon)

    def test_seed(self):
        G = nx.complete_graph(4)
        b = approximate_cfbc(G, normalized=False, epsilon=0.05, seed=1)
        b_answer = {0: 0.75, 1: 0.75, 2: 0.75, 3: 0.75}
        for n in sorted(G):
            np.testing.assert_allclose(b[n], b_answer[n], atol=0.1)

    def test_solvers(self):
        "Approximate current-flow betweenness centrality: solvers"
        G = nx.complete_graph(4)
        epsilon = 0.1
        for solver in ["full", "lu", "cg"]:
            b = approximate_cfbc(
                G, normalized=False, solver=solver, epsilon=0.5 * epsilon
            )
            b_answer = {0: 0.75, 1: 0.75, 2: 0.75, 3: 0.75}
            for n in sorted(G):
                np.testing.assert_allclose(b[n], b_answer[n], atol=epsilon)

    def test_lower_kmax(self):
        G = nx.complete_graph(4)
        with pytest.raises(nx.NetworkXError, match="Increase kmax or epsilon"):
            nx.approximate_current_flow_betweenness_centrality(G, kmax=4)


class TestWeightedFlowBetweennessCentrality:
    pass


class TestEdgeFlowBetweennessCentrality:
    def test_K4(self):
        """Edge flow betweenness centrality: K4"""
        G = nx.complete_graph(4)
        b = edge_current_flow(G, normalized=True)
        b_answer = dict.fromkeys(G.edges(), 0.25)
        for (s, t), v1 in b_answer.items():
            v2 = b.get((s, t), b.get((t, s)))
            assert v1 == pytest.approx(v2, abs=1e-7)

    def test_K4_normalized(self):
        """Edge flow betweenness centrality: K4"""
        G = nx.complete_graph(4)
        b = edge_current_flow(G, normalized=False)
        b_answer = dict.fromkeys(G.edges(), 0.75)
        for (s, t), v1 in b_answer.items():
            v2 = b.get((s, t), b.get((t, s)))
            assert v1 == pytest.approx(v2, abs=1e-7)

    def test_C4(self):
        """Edge flow betweenness centrality: C4"""
        G = nx.cycle_graph(4)
        b = edge_current_flow(G, normalized=False)
        b_answer = {(0, 1): 1.25, (0, 3): 1.25, (1, 2): 1.25, (2, 3): 1.25}
        for (s, t), v1 in b_answer.items():
            v2 = b.get((s, t), b.get((t, s)))
            assert v1 == pytest.approx(v2, abs=1e-7)

    def test_P4(self):
        """Edge betweenness centrality: P4"""
        G = nx.path_graph(4)
        b = edge_current_flow(G, normalized=False)
        b_answer = {(0, 1): 1.5, (1, 2): 2.0, (2, 3): 1.5}
        for (s, t), v1 in b_answer.items():
            v2 = b.get((s, t), b.get((t, s)))
            assert v1 == pytest.approx(v2, abs=1e-7)


@pytest.mark.parametrize(
    "centrality_func",
    (
        nx.current_flow_betweenness_centrality,
        nx.edge_current_flow_betweenness_centrality,
        nx.approximate_current_flow_betweenness_centrality,
    ),
)
def test_unconnected_graphs_betweenness_centrality(centrality_func):
    G = nx.Graph([(1, 2), (3, 4)])
    G.add_node(5)
    with pytest.raises(nx.NetworkXError, match="Graph not connected"):
        centrality_func(G)
