"""Maximum flow algorithms test suite."""

import pytest

import networkx as nx
from networkx.algorithms.flow import (
    boykov_kolmogorov,
    build_flow_dict,
    build_residual_network,
    dinitz,
    edmonds_karp,
    preflow_push,
    shortest_augmenting_path,
)

flow_funcs = {
    boykov_kolmogorov,
    dinitz,
    edmonds_karp,
    preflow_push,
    shortest_augmenting_path,
}

max_min_funcs = {nx.maximum_flow, nx.minimum_cut}
flow_value_funcs = {nx.maximum_flow_value, nx.minimum_cut_value}
interface_funcs = max_min_funcs | flow_value_funcs
all_funcs = flow_funcs | interface_funcs


def compute_cutset(G, partition):
    reachable, non_reachable = partition
    cutset = set()
    for u, nbrs in ((n, G[n]) for n in reachable):
        cutset.update((u, v) for v in nbrs if v in non_reachable)
    return cutset


def validate_flows(G, s, t, flowDict, solnValue, capacity, flow_func):
    errmsg = f"Assertion failed in function: {flow_func.__name__}"
    assert set(G) == set(flowDict), errmsg
    for u in G:
        assert set(G[u]) == set(flowDict[u]), errmsg
    excess = {u: 0 for u in flowDict}
    for u in flowDict:
        for v, flow in flowDict[u].items():
            if capacity in G[u][v]:
                assert flow <= G[u][v][capacity]
            assert flow >= 0, errmsg
            excess[u] -= flow
            excess[v] += flow
    for u, exc in excess.items():
        if u == s:
            assert exc == -solnValue, errmsg
        elif u == t:
            assert exc == solnValue, errmsg
        else:
            assert exc == 0, errmsg


def validate_cuts(G, s, t, solnValue, partition, capacity, flow_func):
    errmsg = f"Assertion failed in function: {flow_func.__name__}"
    assert all(n in G for n in partition[0]), errmsg
    assert all(n in G for n in partition[1]), errmsg
    cutset = compute_cutset(G, partition)
    assert all(G.has_edge(u, v) for (u, v) in cutset), errmsg
    assert solnValue == sum(G[u][v][capacity] for (u, v) in cutset), errmsg
    H = G.copy()
    H.remove_edges_from(cutset)
    if not G.is_directed():
        assert not nx.is_connected(H), errmsg
    else:
        assert not nx.is_strongly_connected(H), errmsg


def compare_flows_and_cuts(G, s, t, solnValue, capacity="capacity"):
    for flow_func in flow_funcs:
        errmsg = f"Assertion failed in function: {flow_func.__name__}"
        R = flow_func(G, s, t, capacity)
        # Test both legacy and new implementations.
        flow_value = R.graph["flow_value"]
        flow_dict = build_flow_dict(G, R)
        assert flow_value == solnValue, errmsg
        validate_flows(G, s, t, flow_dict, solnValue, capacity, flow_func)
        # Minimum cut
        cut_value, partition = nx.minimum_cut(
            G, s, t, capacity=capacity, flow_func=flow_func
        )
        validate_cuts(G, s, t, solnValue, partition, capacity, flow_func)


class TestMaxflowMinCutCommon:
    def test_graph1(self):
        # Trivial undirected graph
        G = nx.Graph()
        G.add_edge(1, 2, capacity=1.0)

        # solution flows
        # {1: {2: 1.0}, 2: {1: 1.0}}

        compare_flows_and_cuts(G, 1, 2, 1.0)

    def test_graph2(self):
        # A more complex undirected graph
        # adapted from https://web.archive.org/web/20220815055650/https://www.topcoder.com/thrive/articles/Maximum%20Flow:%20Part%20One
        G = nx.Graph()
        G.add_edge("x", "a", capacity=3.0)
        G.add_edge("x", "b", capacity=1.0)
        G.add_edge("a", "c", capacity=3.0)
        G.add_edge("b", "c", capacity=5.0)
        G.add_edge("b", "d", capacity=4.0)
        G.add_edge("d", "e", capacity=2.0)
        G.add_edge("c", "y", capacity=2.0)
        G.add_edge("e", "y", capacity=3.0)

        # H
        # {
        #     "x": {"a": 3, "b": 1},
        #     "a": {"c": 3, "x": 3},
        #     "b": {"c": 1, "d": 2, "x": 1},
        #     "c": {"a": 3, "b": 1, "y": 2},
        #     "d": {"b": 2, "e": 2},
        #     "e": {"d": 2, "y": 2},
        #     "y": {"c": 2, "e": 2},
        # }

        compare_flows_and_cuts(G, "x", "y", 4.0)

    def test_digraph1(self):
        # The classic directed graph example
        G = nx.DiGraph()
        G.add_edge("a", "b", capacity=1000.0)
        G.add_edge("a", "c", capacity=1000.0)
        G.add_edge("b", "c", capacity=1.0)
        G.add_edge("b", "d", capacity=1000.0)
        G.add_edge("c", "d", capacity=1000.0)

        # H
        # {
        #     "a": {"b": 1000.0, "c": 1000.0},
        #     "b": {"c": 0, "d": 1000.0},
        #     "c": {"d": 1000.0},
        #     "d": {},
        # }

        compare_flows_and_cuts(G, "a", "d", 2000.0)

    def test_digraph2(self):
        # An example in which some edges end up with zero flow.
        G = nx.DiGraph()
        G.add_edge("s", "b", capacity=2)
        G.add_edge("s", "c", capacity=1)
        G.add_edge("c", "d", capacity=1)
        G.add_edge("d", "a", capacity=1)
        G.add_edge("b", "a", capacity=2)
        G.add_edge("a", "t", capacity=2)

        # H
        # {
        #     "s": {"b": 2, "c": 0},
        #     "c": {"d": 0},
        #     "d": {"a": 0},
        #     "b": {"a": 2},
        #     "a": {"t": 2},
        #     "t": {},
        # }

        compare_flows_and_cuts(G, "s", "t", 2)

    def test_digraph3(self):
        # A directed graph example from Cormen et al.
        G = nx.DiGraph()
        G.add_edge("s", "v1", capacity=16.0)
        G.add_edge("s", "v2", capacity=13.0)
        G.add_edge("v1", "v2", capacity=10.0)
        G.add_edge("v2", "v1", capacity=4.0)
        G.add_edge("v1", "v3", capacity=12.0)
        G.add_edge("v3", "v2", capacity=9.0)
        G.add_edge("v2", "v4", capacity=14.0)
        G.add_edge("v4", "v3", capacity=7.0)
        G.add_edge("v3", "t", capacity=20.0)
        G.add_edge("v4", "t", capacity=4.0)

        # H
        # {
        #     "s": {"v1": 12.0, "v2": 11.0},
        #     "v2": {"v1": 0, "v4": 11.0},
        #     "v1": {"v2": 0, "v3": 12.0},
        #     "v3": {"v2": 0, "t": 19.0},
        #     "v4": {"v3": 7.0, "t": 4.0},
        #     "t": {},
        # }

        compare_flows_and_cuts(G, "s", "t", 23.0)

    def test_digraph4(self):
        # A more complex directed graph
        # from https://web.archive.org/web/20220815055650/https://www.topcoder.com/thrive/articles/Maximum%20Flow:%20Part%20One
        G = nx.DiGraph()
        G.add_edge("x", "a", capacity=3.0)
        G.add_edge("x", "b", capacity=1.0)
        G.add_edge("a", "c", capacity=3.0)
        G.add_edge("b", "c", capacity=5.0)
        G.add_edge("b", "d", capacity=4.0)
        G.add_edge("d", "e", capacity=2.0)
        G.add_edge("c", "y", capacity=2.0)
        G.add_edge("e", "y", capacity=3.0)

        # H
        # {
        #     "x": {"a": 2.0, "b": 1.0},
        #     "a": {"c": 2.0},
        #     "b": {"c": 0, "d": 1.0},
        #     "c": {"y": 2.0},
        #     "d": {"e": 1.0},
        #     "e": {"y": 1.0},
        #     "y": {},
        # }

        compare_flows_and_cuts(G, "x", "y", 3.0)

    def test_wikipedia_dinitz_example(self):
        # Nice example from https://en.wikipedia.org/wiki/Dinic's_algorithm
        G = nx.DiGraph()
        G.add_edge("s", 1, capacity=10)
        G.add_edge("s", 2, capacity=10)
        G.add_edge(1, 3, capacity=4)
        G.add_edge(1, 4, capacity=8)
        G.add_edge(1, 2, capacity=2)
        G.add_edge(2, 4, capacity=9)
        G.add_edge(3, "t", capacity=10)
        G.add_edge(4, 3, capacity=6)
        G.add_edge(4, "t", capacity=10)

        # solution flows
        # {
        #     1: {2: 0, 3: 4, 4: 6},
        #     2: {4: 9},
        #     3: {"t": 9},
        #     4: {3: 5, "t": 10},
        #     "s": {1: 10, 2: 9},
        #     "t": {},
        # }

        compare_flows_and_cuts(G, "s", "t", 19)

    def test_optional_capacity(self):
        # Test optional capacity parameter.
        G = nx.DiGraph()
        G.add_edge("x", "a", spam=3.0)
        G.add_edge("x", "b", spam=1.0)
        G.add_edge("a", "c", spam=3.0)
        G.add_edge("b", "c", spam=5.0)
        G.add_edge("b", "d", spam=4.0)
        G.add_edge("d", "e", spam=2.0)
        G.add_edge("c", "y", spam=2.0)
        G.add_edge("e", "y", spam=3.0)

        # solution flows
        # {
        #     "x": {"a": 2.0, "b": 1.0},
        #     "a": {"c": 2.0},
        #     "b": {"c": 0, "d": 1.0},
        #     "c": {"y": 2.0},
        #     "d": {"e": 1.0},
        #     "e": {"y": 1.0},
        #     "y": {},
        # }
        solnValue = 3.0
        s = "x"
        t = "y"

        compare_flows_and_cuts(G, s, t, solnValue, capacity="spam")

    def test_digraph_infcap_edges(self):
        # DiGraph with infinite capacity edges
        G = nx.DiGraph()
        G.add_edge("s", "a")
        G.add_edge("s", "b", capacity=30)
        G.add_edge("a", "c", capacity=25)
        G.add_edge("b", "c", capacity=12)
        G.add_edge("a", "t", capacity=60)
        G.add_edge("c", "t")

        # H
        # {
        #     "s": {"a": 85, "b": 12},
        #     "a": {"c": 25, "t": 60},
        #     "b": {"c": 12},
        #     "c": {"t": 37},
        #     "t": {},
        # }

        compare_flows_and_cuts(G, "s", "t", 97)

        # DiGraph with infinite capacity digon
        G = nx.DiGraph()
        G.add_edge("s", "a", capacity=85)
        G.add_edge("s", "b", capacity=30)
        G.add_edge("a", "c")
        G.add_edge("c", "a")
        G.add_edge("b", "c", capacity=12)
        G.add_edge("a", "t", capacity=60)
        G.add_edge("c", "t", capacity=37)

        # H
        # {
        #     "s": {"a": 85, "b": 12},
        #     "a": {"c": 25, "t": 60},
        #     "c": {"a": 0, "t": 37},
        #     "b": {"c": 12},
        #     "t": {},
        # }

        compare_flows_and_cuts(G, "s", "t", 97)

    def test_digraph_infcap_path(self):
        # Graph with infinite capacity (s, t)-path
        G = nx.DiGraph()
        G.add_edge("s", "a")
        G.add_edge("s", "b", capacity=30)
        G.add_edge("a", "c")
        G.add_edge("b", "c", capacity=12)
        G.add_edge("a", "t", capacity=60)
        G.add_edge("c", "t")

        for flow_func in all_funcs:
            pytest.raises(nx.NetworkXUnbounded, flow_func, G, "s", "t")

    def test_graph_infcap_edges(self):
        # Undirected graph with infinite capacity edges
        G = nx.Graph()
        G.add_edge("s", "a")
        G.add_edge("s", "b", capacity=30)
        G.add_edge("a", "c", capacity=25)
        G.add_edge("b", "c", capacity=12)
        G.add_edge("a", "t", capacity=60)
        G.add_edge("c", "t")

        # H
        # {
        #     "s": {"a": 85, "b": 12},
        #     "a": {"c": 25, "s": 85, "t": 60},
        #     "b": {"c": 12, "s": 12},
        #     "c": {"a": 25, "b": 12, "t": 37},
        #     "t": {"a": 60, "c": 37},
        # }

        compare_flows_and_cuts(G, "s", "t", 97)

    def test_digraph5(self):
        # From ticket #429 by mfrasca.
        G = nx.DiGraph()
        G.add_edge("s", "a", capacity=2)
        G.add_edge("s", "b", capacity=2)
        G.add_edge("a", "b", capacity=5)
        G.add_edge("a", "t", capacity=1)
        G.add_edge("b", "a", capacity=1)
        G.add_edge("b", "t", capacity=3)
        # flow solution
        # {
        #     "a": {"b": 1, "t": 1},
        #     "b": {"a": 0, "t": 3},
        #     "s": {"a": 2, "b": 2},
        #     "t": {},
        # }
        compare_flows_and_cuts(G, "s", "t", 4)

    def test_disconnected(self):
        G = nx.Graph()
        G.add_weighted_edges_from([(0, 1, 1), (1, 2, 1), (2, 3, 1)], weight="capacity")
        G.remove_node(1)
        assert nx.maximum_flow_value(G, 0, 3) == 0
        # flow solution
        # {0: {}, 2: {3: 0}, 3: {2: 0}}
        compare_flows_and_cuts(G, 0, 3, 0)

    def test_source_target_not_in_graph(self):
        G = nx.Graph()
        G.add_weighted_edges_from([(0, 1, 1), (1, 2, 1), (2, 3, 1)], weight="capacity")
        G.remove_node(0)
        for flow_func in all_funcs:
            pytest.raises(nx.NetworkXError, flow_func, G, 0, 3)
        G.add_weighted_edges_from([(0, 1, 1), (1, 2, 1), (2, 3, 1)], weight="capacity")
        G.remove_node(3)
        for flow_func in all_funcs:
            pytest.raises(nx.NetworkXError, flow_func, G, 0, 3)

    def test_source_target_coincide(self):
        G = nx.Graph()
        G.add_node(0)
        for flow_func in all_funcs:
            pytest.raises(nx.NetworkXError, flow_func, G, 0, 0)

    def test_multigraphs_raise(self):
        G = nx.MultiGraph()
        M = nx.MultiDiGraph()
        G.add_edges_from([(0, 1), (1, 0)], capacity=True)
        for flow_func in all_funcs:
            pytest.raises(nx.NetworkXError, flow_func, G, 0, 0)


class TestMaxFlowMinCutInterface:
    def setup_method(self):
        G = nx.DiGraph()
        G.add_edge("x", "a", capacity=3.0)
        G.add_edge("x", "b", capacity=1.0)
        G.add_edge("a", "c", capacity=3.0)
        G.add_edge("b", "c", capacity=5.0)
        G.add_edge("b", "d", capacity=4.0)
        G.add_edge("d", "e", capacity=2.0)
        G.add_edge("c", "y", capacity=2.0)
        G.add_edge("e", "y", capacity=3.0)
        self.G = G
        H = nx.DiGraph()
        H.add_edge(0, 1, capacity=1.0)
        H.add_edge(1, 2, capacity=1.0)
        self.H = H

    def test_flow_func_not_callable(self):
        elements = ["this_should_be_callable", 10, {1, 2, 3}]
        G = nx.Graph()
        G.add_weighted_edges_from([(0, 1, 1), (1, 2, 1), (2, 3, 1)], weight="capacity")
        for flow_func in interface_funcs:
            for element in elements:
                pytest.raises(nx.NetworkXError, flow_func, G, 0, 1, flow_func=element)
                pytest.raises(nx.NetworkXError, flow_func, G, 0, 1, flow_func=element)

    def test_flow_func_parameters(self):
        G = self.G
        fv = 3.0
        for interface_func in interface_funcs:
            for flow_func in flow_funcs:
                errmsg = (
                    f"Assertion failed in function: {flow_func.__name__} "
                    f"in interface {interface_func.__name__}"
                )
                result = interface_func(G, "x", "y", flow_func=flow_func)
                if interface_func in max_min_funcs:
                    result = result[0]
                assert fv == result, errmsg

    def test_minimum_cut_no_cutoff(self):
        G = self.G
        pytest.raises(
            nx.NetworkXError,
            nx.minimum_cut,
            G,
            "x",
            "y",
            flow_func=preflow_push,
            cutoff=1.0,
        )
        pytest.raises(
            nx.NetworkXError,
            nx.minimum_cut_value,
            G,
            "x",
            "y",
            flow_func=preflow_push,
            cutoff=1.0,
        )

    def test_kwargs(self):
        G = self.H
        fv = 1.0
        to_test = (
            (shortest_augmenting_path, {"two_phase": True}),
            (preflow_push, {"global_relabel_freq": 5}),
        )
        for interface_func in interface_funcs:
            for flow_func, kwargs in to_test:
                errmsg = (
                    f"Assertion failed in function: {flow_func.__name__} "
                    f"in interface {interface_func.__name__}"
                )
                result = interface_func(G, 0, 2, flow_func=flow_func, **kwargs)
                if interface_func in max_min_funcs:
                    result = result[0]
                assert fv == result, errmsg

    def test_kwargs_default_flow_func(self):
        G = self.H
        for interface_func in interface_funcs:
            pytest.raises(
                nx.NetworkXError, interface_func, G, 0, 1, global_relabel_freq=2
            )

    def test_reusing_residual(self):
        G = self.G
        fv = 3.0
        s, t = "x", "y"
        R = build_residual_network(G, "capacity")
        for interface_func in interface_funcs:
            for flow_func in flow_funcs:
                errmsg = (
                    f"Assertion failed in function: {flow_func.__name__} "
                    f"in interface {interface_func.__name__}"
                )
                for i in range(3):
                    result = interface_func(
                        G, "x", "y", flow_func=flow_func, residual=R
                    )
                    if interface_func in max_min_funcs:
                        result = result[0]
                    assert fv == result, errmsg


# Tests specific to one algorithm
def test_preflow_push_global_relabel_freq():
    G = nx.DiGraph()
    G.add_edge(1, 2, capacity=1)
    R = preflow_push(G, 1, 2, global_relabel_freq=None)
    assert R.graph["flow_value"] == 1
    pytest.raises(nx.NetworkXError, preflow_push, G, 1, 2, global_relabel_freq=-1)


def test_preflow_push_makes_enough_space():
    # From ticket #1542
    G = nx.DiGraph()
    nx.add_path(G, [0, 1, 3], capacity=1)
    nx.add_path(G, [1, 2, 3], capacity=1)
    R = preflow_push(G, 0, 3, value_only=False)
    assert R.graph["flow_value"] == 1


def test_shortest_augmenting_path_two_phase():
    k = 5
    p = 1000
    G = nx.DiGraph()
    for i in range(k):
        G.add_edge("s", (i, 0), capacity=1)
        nx.add_path(G, ((i, j) for j in range(p)), capacity=1)
        G.add_edge((i, p - 1), "t", capacity=1)
    R = shortest_augmenting_path(G, "s", "t", two_phase=True)
    assert R.graph["flow_value"] == k
    R = shortest_augmenting_path(G, "s", "t", two_phase=False)
    assert R.graph["flow_value"] == k


class TestCutoff:
    def test_cutoff(self):
        k = 5
        p = 1000
        G = nx.DiGraph()
        for i in range(k):
            G.add_edge("s", (i, 0), capacity=2)
            nx.add_path(G, ((i, j) for j in range(p)), capacity=2)
            G.add_edge((i, p - 1), "t", capacity=2)
        R = shortest_augmenting_path(G, "s", "t", two_phase=True, cutoff=k)
        assert k <= R.graph["flow_value"] <= (2 * k)
        R = shortest_augmenting_path(G, "s", "t", two_phase=False, cutoff=k)
        assert k <= R.graph["flow_value"] <= (2 * k)
        R = edmonds_karp(G, "s", "t", cutoff=k)
        assert k <= R.graph["flow_value"] <= (2 * k)
        R = dinitz(G, "s", "t", cutoff=k)
        assert k <= R.graph["flow_value"] <= (2 * k)
        R = boykov_kolmogorov(G, "s", "t", cutoff=k)
        assert k <= R.graph["flow_value"] <= (2 * k)

    def test_complete_graph_cutoff(self):
        G = nx.complete_graph(5)
        nx.set_edge_attributes(G, {(u, v): 1 for u, v in G.edges()}, "capacity")
        for flow_func in [
            shortest_augmenting_path,
            edmonds_karp,
            dinitz,
            boykov_kolmogorov,
        ]:
            for cutoff in [3, 2, 1]:
                result = nx.maximum_flow_value(
                    G, 0, 4, flow_func=flow_func, cutoff=cutoff
                )
                assert cutoff == result, f"cutoff error in {flow_func.__name__}"
