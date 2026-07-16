import pytest

import networkx as nx
from networkx import NetworkXNotImplemented


class TestWeaklyConnected:
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
        C = [[3, 4, 5, 7], [1, 2, 8], [6]]
        cls.gc.append((G, C))

        G = nx.DiGraph()
        G.add_edges_from([(1, 2), (1, 3), (1, 4), (4, 2), (3, 4), (2, 3)])
        C = [[2, 3, 4], [1]]
        cls.gc.append((G, C))

        G = nx.DiGraph()
        G.add_edges_from([(1, 2), (2, 3), (3, 2), (2, 1)])
        C = [[1, 2, 3]]
        cls.gc.append((G, C))

        # Eppstein's tests
        G = nx.DiGraph({0: [1], 1: [2, 3], 2: [4, 5], 3: [4, 5], 4: [6], 5: [], 6: []})
        C = [[0], [1], [2], [3], [4], [5], [6]]
        cls.gc.append((G, C))

        G = nx.DiGraph({0: [1], 1: [2, 3, 4], 2: [0, 3], 3: [4], 4: [3]})
        C = [[0, 1, 2], [3, 4]]
        cls.gc.append((G, C))

    def test_weakly_connected_components(self):
        for G, C in self.gc:
            U = G.to_undirected()
            w = {frozenset(g) for g in nx.weakly_connected_components(G)}
            c = {frozenset(g) for g in nx.connected_components(U)}
            assert w == c

    def test_number_weakly_connected_components(self):
        for G, C in self.gc:
            U = G.to_undirected()
            w = nx.number_weakly_connected_components(G)
            c = nx.number_connected_components(U)
            assert w == c

    def test_is_weakly_connected(self):
        for G, C in self.gc:
            U = G.to_undirected()
            assert nx.is_weakly_connected(G) == nx.is_connected(U)

    def test_null_graph(self):
        G = nx.DiGraph()
        assert list(nx.weakly_connected_components(G)) == []
        assert nx.number_weakly_connected_components(G) == 0
        with pytest.raises(nx.NetworkXPointlessConcept):
            next(nx.is_weakly_connected(G))

    def test_connected_raise(self):
        G = nx.Graph()
        with pytest.raises(NetworkXNotImplemented):
            next(nx.weakly_connected_components(G))
        pytest.raises(NetworkXNotImplemented, nx.number_weakly_connected_components, G)
        pytest.raises(NetworkXNotImplemented, nx.is_weakly_connected, G)

    def test_connected_mutability(self):
        DG = nx.path_graph(5, create_using=nx.DiGraph)
        G = nx.disjoint_union(DG, DG)
        seen = set()
        for component in nx.weakly_connected_components(G):
            assert len(seen & component) == 0
            seen.update(component)
            component.clear()


def test_is_weakly_connected_empty_graph_raises():
    G = nx.DiGraph()
    with pytest.raises(nx.NetworkXPointlessConcept, match="Connectivity is undefined"):
        nx.is_weakly_connected(G)
