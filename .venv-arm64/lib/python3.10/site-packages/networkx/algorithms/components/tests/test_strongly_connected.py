import pytest

import networkx as nx
from networkx import NetworkXNotImplemented


class TestStronglyConnected:
    @classmethod
    def setup_class(cls):
        cls.gc = []
        G = nx.DiGraph()
        G.add_edges_from(
            [
                (1, 2),
                (2, 3),
                (2, 8),
                (3, 4),
                (3, 7),
                (4, 5),
                (5, 3),
                (5, 6),
                (7, 4),
                (7, 6),
                (8, 1),
                (8, 7),
            ]
        )
        C = {frozenset([3, 4, 5, 7]), frozenset([1, 2, 8]), frozenset([6])}
        cls.gc.append((G, C))

        G = nx.DiGraph()
        G.add_edges_from([(1, 2), (1, 3), (1, 4), (4, 2), (3, 4), (2, 3)])
        C = {frozenset([2, 3, 4]), frozenset([1])}
        cls.gc.append((G, C))

        G = nx.DiGraph()
        G.add_edges_from([(1, 2), (2, 3), (3, 2), (2, 1)])
        C = {frozenset([1, 2, 3])}
        cls.gc.append((G, C))

        # Eppstein's tests
        G = nx.DiGraph({0: [1], 1: [2, 3], 2: [4, 5], 3: [4, 5], 4: [6], 5: [], 6: []})
        C = {
            frozenset([0]),
            frozenset([1]),
            frozenset([2]),
            frozenset([3]),
            frozenset([4]),
            frozenset([5]),
            frozenset([6]),
        }
        cls.gc.append((G, C))

        G = nx.DiGraph({0: [1], 1: [2, 3, 4], 2: [0, 3], 3: [4], 4: [3]})
        C = {frozenset([0, 1, 2]), frozenset([3, 4])}
        cls.gc.append((G, C))

    def test_tarjan(self):
        scc = nx.strongly_connected_components
        for G, C in self.gc:
            assert {frozenset(g) for g in scc(G)} == C

    def test_kosaraju(self):
        scc = nx.kosaraju_strongly_connected_components
        for G, C in self.gc:
            assert {frozenset(g) for g in scc(G)} == C

    def test_number_strongly_connected_components(self):
        ncc = nx.number_strongly_connected_components
        for G, C in self.gc:
            assert ncc(G) == len(C)

    def test_is_strongly_connected(self):
        for G, C in self.gc:
            if len(C) == 1:
                assert nx.is_strongly_connected(G)
            else:
                assert not nx.is_strongly_connected(G)

    def test_contract_scc1(self):
        G = nx.DiGraph()
        G.add_edges_from(
            [
                (1, 2),
                (2, 3),
                (2, 11),
                (2, 12),
                (3, 4),
                (4, 3),
                (4, 5),
                (5, 6),
                (6, 5),
                (6, 7),
                (7, 8),
                (7, 9),
                (7, 10),
                (8, 9),
                (9, 7),
                (10, 6),
                (11, 2),
                (11, 4),
                (11, 6),
                (12, 6),
                (12, 11),
            ]
        )
        scc = list(nx.strongly_connected_components(G))
        cG = nx.condensation(G, scc)
        # DAG
        assert nx.is_directed_acyclic_graph(cG)
        # nodes
        assert sorted(cG.nodes()) == [0, 1, 2, 3]
        # edges
        mapping = {}
        for i, component in enumerate(scc):
            for n in component:
                mapping[n] = i
        edge = (mapping[2], mapping[3])
        assert cG.has_edge(*edge)
        edge = (mapping[2], mapping[5])
        assert cG.has_edge(*edge)
        edge = (mapping[3], mapping[5])
        assert cG.has_edge(*edge)

    def test_contract_scc_isolate(self):
        # Bug found and fixed in [1687].
        G = nx.DiGraph()
        G.add_edge(1, 2)
        G.add_edge(2, 1)
        scc = list(nx.strongly_connected_components(G))
        cG = nx.condensation(G, scc)
        assert list(cG.nodes()) == [0]
        assert list(cG.edges()) == []

    def test_contract_scc_edge(self):
        G = nx.DiGraph()
        G.add_edge(1, 2)
        G.add_edge(2, 1)
        G.add_edge(2, 3)
        G.add_edge(3, 4)
        G.add_edge(4, 3)
        scc = list(nx.strongly_connected_components(G))
        cG = nx.condensation(G, scc)
        assert sorted(cG.nodes()) == [0, 1]
        if 1 in scc[0]:
            edge = (0, 1)
        else:
            edge = (1, 0)
        assert list(cG.edges()) == [edge]

    def test_condensation_mapping_and_members(self):
        G, C = self.gc[1]
        C = sorted(C, key=len, reverse=True)
        cG = nx.condensation(G)
        mapping = cG.graph["mapping"]
        assert all(n in G for n in mapping)
        assert all(0 == cN for n, cN in mapping.items() if n in C[0])
        assert all(1 == cN for n, cN in mapping.items() if n in C[1])
        for n, d in cG.nodes(data=True):
            assert set(C[n]) == cG.nodes[n]["members"]

    def test_null_graph(self):
        G = nx.DiGraph()
        assert list(nx.strongly_connected_components(G)) == []
        assert list(nx.kosaraju_strongly_connected_components(G)) == []
        assert len(nx.condensation(G)) == 0
        pytest.raises(
            nx.NetworkXPointlessConcept, nx.is_strongly_connected, nx.DiGraph()
        )

    def test_connected_raise(self):
        G = nx.Graph()
        with pytest.raises(NetworkXNotImplemented):
            next(nx.strongly_connected_components(G))
        with pytest.raises(NetworkXNotImplemented):
            next(nx.kosaraju_strongly_connected_components(G))
        pytest.raises(NetworkXNotImplemented, nx.is_strongly_connected, G)
        pytest.raises(NetworkXNotImplemented, nx.condensation, G)

    strong_cc_methods = (
        nx.strongly_connected_components,
        nx.kosaraju_strongly_connected_components,
    )

    @pytest.mark.parametrize("get_components", strong_cc_methods)
    def test_connected_mutability(self, get_components):
        DG = nx.path_graph(5, create_using=nx.DiGraph)
        G = nx.disjoint_union(DG, DG)
        seen = set()
        for component in get_components(G):
            assert len(seen & component) == 0
            seen.update(component)
            component.clear()
