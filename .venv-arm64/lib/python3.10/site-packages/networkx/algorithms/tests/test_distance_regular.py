import pytest

import networkx as nx
from networkx import is_strongly_regular


@pytest.mark.parametrize(
    "f", (nx.is_distance_regular, nx.intersection_array, nx.is_strongly_regular)
)
@pytest.mark.parametrize("graph_constructor", (nx.DiGraph, nx.MultiGraph))
def test_raises_on_directed_and_multigraphs(f, graph_constructor):
    G = graph_constructor([(0, 1), (1, 2)])
    with pytest.raises(nx.NetworkXNotImplemented):
        f(G)


class TestDistanceRegular:
    def test_is_distance_regular(self):
        assert nx.is_distance_regular(nx.icosahedral_graph())
        assert nx.is_distance_regular(nx.petersen_graph())
        assert nx.is_distance_regular(nx.cubical_graph())
        assert nx.is_distance_regular(nx.complete_bipartite_graph(3, 3))
        assert nx.is_distance_regular(nx.tetrahedral_graph())
        assert nx.is_distance_regular(nx.dodecahedral_graph())
        assert nx.is_distance_regular(nx.pappus_graph())
        assert nx.is_distance_regular(nx.heawood_graph())
        assert nx.is_distance_regular(nx.cycle_graph(3))
        # no distance regular
        assert not nx.is_distance_regular(nx.path_graph(4))

    def test_not_connected(self):
        G = nx.cycle_graph(4)
        nx.add_cycle(G, [5, 6, 7])
        assert not nx.is_distance_regular(G)

    def test_global_parameters(self):
        b, c = nx.intersection_array(nx.cycle_graph(5))
        g = nx.global_parameters(b, c)
        assert list(g) == [(0, 0, 2), (1, 0, 1), (1, 1, 0)]
        b, c = nx.intersection_array(nx.cycle_graph(3))
        g = nx.global_parameters(b, c)
        assert list(g) == [(0, 0, 2), (1, 1, 0)]

    def test_intersection_array(self):
        b, c = nx.intersection_array(nx.cycle_graph(5))
        assert b == [2, 1]
        assert c == [1, 1]
        b, c = nx.intersection_array(nx.dodecahedral_graph())
        assert b == [3, 2, 1, 1, 1]
        assert c == [1, 1, 1, 2, 3]
        b, c = nx.intersection_array(nx.icosahedral_graph())
        assert b == [5, 2, 1]
        assert c == [1, 2, 5]


@pytest.mark.parametrize("f", (nx.is_distance_regular, nx.is_strongly_regular))
def test_empty_graph_raises(f):
    G = nx.Graph()
    with pytest.raises(nx.NetworkXPointlessConcept, match="Graph has no nodes"):
        f(G)


class TestStronglyRegular:
    """Unit tests for the :func:`~networkx.is_strongly_regular`
    function.

    """

    def test_cycle_graph(self):
        """Tests that the cycle graph on five vertices is strongly
        regular.

        """
        G = nx.cycle_graph(5)
        assert is_strongly_regular(G)

    def test_petersen_graph(self):
        """Tests that the Petersen graph is strongly regular."""
        G = nx.petersen_graph()
        assert is_strongly_regular(G)

    def test_path_graph(self):
        """Tests that the path graph is not strongly regular."""
        G = nx.path_graph(4)
        assert not is_strongly_regular(G)
