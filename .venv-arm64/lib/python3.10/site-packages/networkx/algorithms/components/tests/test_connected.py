import pytest

import networkx as nx
from networkx import NetworkXNotImplemented
from networkx import convert_node_labels_to_integers as cnlti
from networkx.classes.tests import dispatch_interface


class TestConnected:
    @classmethod
    def setup_class(cls):
        G1 = cnlti(nx.grid_2d_graph(2, 2), first_label=0, ordering="sorted")
        G2 = cnlti(nx.lollipop_graph(3, 3), first_label=4, ordering="sorted")
        G3 = cnlti(nx.house_graph(), first_label=10, ordering="sorted")
        cls.G = nx.union(G1, G2)
        cls.G = nx.union(cls.G, G3)
        cls.DG = nx.DiGraph([(1, 2), (1, 3), (2, 3)])
        cls.grid = cnlti(nx.grid_2d_graph(4, 4), first_label=1)

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

        G = nx.DiGraph()
        C = []
        cls.gc.append((G, C))

    def test_connected_components(self):
        # Test duplicated below
        cc = nx.connected_components
        G = self.G
        C = {
            frozenset([0, 1, 2, 3]),
            frozenset([4, 5, 6, 7, 8, 9]),
            frozenset([10, 11, 12, 13, 14]),
        }
        assert {frozenset(g) for g in cc(G)} == C

    def test_connected_components_nx_loopback(self):
        # This tests the @nx._dispatchable mechanism, treating nx.connected_components
        # as if it were a re-implementation from another package.
        # Test duplicated from above
        cc = nx.connected_components
        G = dispatch_interface.convert(self.G)
        C = {
            frozenset([0, 1, 2, 3]),
            frozenset([4, 5, 6, 7, 8, 9]),
            frozenset([10, 11, 12, 13, 14]),
        }
        if "nx_loopback" in nx.config.backends or not nx.config.backends:
            # If `nx.config.backends` is empty, then `_dispatchable.__call__` takes a
            # "fast path" and does not check graph inputs, so using an unknown backend
            # here will still work.
            assert {frozenset(g) for g in cc(G)} == C
        else:
            # This raises, because "nx_loopback" is not registered as a backend.
            with pytest.raises(
                ImportError, match="'nx_loopback' backend is not installed"
            ):
                cc(G)

    def test_number_connected_components(self):
        ncc = nx.number_connected_components
        assert ncc(self.G) == 3

    def test_number_connected_components2(self):
        ncc = nx.number_connected_components
        assert ncc(self.grid) == 1

    def test_connected_components2(self):
        cc = nx.connected_components
        G = self.grid
        C = {frozenset([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16])}
        assert {frozenset(g) for g in cc(G)} == C

    def test_node_connected_components(self):
        ncc = nx.node_connected_component
        G = self.grid
        C = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16}
        assert ncc(G, 1) == C

    def test_is_connected(self):
        assert nx.is_connected(self.grid)
        G = nx.Graph()
        G.add_nodes_from([1, 2])
        assert not nx.is_connected(G)

    def test_connected_raise(self):
        with pytest.raises(NetworkXNotImplemented):
            next(nx.connected_components(self.DG))
        pytest.raises(NetworkXNotImplemented, nx.number_connected_components, self.DG)
        pytest.raises(NetworkXNotImplemented, nx.node_connected_component, self.DG, 1)
        pytest.raises(NetworkXNotImplemented, nx.is_connected, self.DG)
        pytest.raises(nx.NetworkXPointlessConcept, nx.is_connected, nx.Graph())

    def test_connected_mutability(self):
        G = self.grid
        seen = set()
        for component in nx.connected_components(G):
            assert len(seen & component) == 0
            seen.update(component)
            component.clear()
