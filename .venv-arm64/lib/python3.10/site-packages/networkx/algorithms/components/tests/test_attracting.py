import pytest

import networkx as nx
from networkx import NetworkXNotImplemented


class TestAttractingComponents:
    @classmethod
    def setup_class(cls):
        cls.G1 = nx.DiGraph()
        cls.G1.add_edges_from(
            [
                (5, 11),
                (11, 2),
                (11, 9),
                (11, 10),
                (7, 11),
                (7, 8),
                (8, 9),
                (3, 8),
                (3, 10),
            ]
        )
        cls.G2 = nx.DiGraph()
        cls.G2.add_edges_from([(0, 1), (0, 2), (1, 1), (1, 2), (2, 1)])

        cls.G3 = nx.DiGraph()
        cls.G3.add_edges_from([(0, 1), (1, 2), (2, 1), (0, 3), (3, 4), (4, 3)])

        cls.G4 = nx.DiGraph()

    def test_attracting_components(self):
        ac = list(nx.attracting_components(self.G1))
        assert {2} in ac
        assert {9} in ac
        assert {10} in ac

        ac = list(nx.attracting_components(self.G2))
        ac = [tuple(sorted(x)) for x in ac]
        assert ac == [(1, 2)]

        ac = list(nx.attracting_components(self.G3))
        ac = [tuple(sorted(x)) for x in ac]
        assert (1, 2) in ac
        assert (3, 4) in ac
        assert len(ac) == 2

        ac = list(nx.attracting_components(self.G4))
        assert ac == []

    def test_number_attacting_components(self):
        assert nx.number_attracting_components(self.G1) == 3
        assert nx.number_attracting_components(self.G2) == 1
        assert nx.number_attracting_components(self.G3) == 2
        assert nx.number_attracting_components(self.G4) == 0

    def test_is_attracting_component(self):
        assert not nx.is_attracting_component(self.G1)
        assert not nx.is_attracting_component(self.G2)
        assert not nx.is_attracting_component(self.G3)
        g2 = self.G3.subgraph([1, 2])
        assert nx.is_attracting_component(g2)
        assert not nx.is_attracting_component(self.G4)

    def test_connected_raise(self):
        G = nx.Graph()
        with pytest.raises(NetworkXNotImplemented):
            next(nx.attracting_components(G))
        pytest.raises(NetworkXNotImplemented, nx.number_attracting_components, G)
        pytest.raises(NetworkXNotImplemented, nx.is_attracting_component, G)
