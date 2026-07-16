import collections

import pytest

import networkx as nx


@pytest.mark.parametrize("f", (nx.is_eulerian, nx.is_semieulerian))
def test_empty_graph_raises(f):
    G = nx.Graph()
    with pytest.raises(nx.NetworkXPointlessConcept, match="Connectivity is undefined"):
        f(G)


class TestIsEulerian:
    def test_is_eulerian(self):
        assert nx.is_eulerian(nx.complete_graph(5))
        assert nx.is_eulerian(nx.complete_graph(7))
        assert nx.is_eulerian(nx.hypercube_graph(4))
        assert nx.is_eulerian(nx.hypercube_graph(6))

        assert not nx.is_eulerian(nx.complete_graph(4))
        assert not nx.is_eulerian(nx.complete_graph(6))
        assert not nx.is_eulerian(nx.hypercube_graph(3))
        assert not nx.is_eulerian(nx.hypercube_graph(5))

        assert not nx.is_eulerian(nx.petersen_graph())
        assert not nx.is_eulerian(nx.path_graph(4))

    def test_is_eulerian2(self):
        # not connected
        G = nx.Graph()
        G.add_nodes_from([1, 2, 3])
        assert not nx.is_eulerian(G)
        # not strongly connected
        G = nx.DiGraph()
        G.add_nodes_from([1, 2, 3])
        assert not nx.is_eulerian(G)
        G = nx.MultiDiGraph()
        G.add_edge(1, 2)
        G.add_edge(2, 3)
        G.add_edge(2, 3)
        G.add_edge(3, 1)
        assert not nx.is_eulerian(G)


class TestEulerianCircuit:
    def test_eulerian_circuit_cycle(self):
        G = nx.cycle_graph(4)

        edges = list(nx.eulerian_circuit(G, source=0))
        nodes = [u for u, v in edges]
        assert nodes == [0, 3, 2, 1]
        assert edges == [(0, 3), (3, 2), (2, 1), (1, 0)]

        edges = list(nx.eulerian_circuit(G, source=1))
        nodes = [u for u, v in edges]
        assert nodes == [1, 2, 3, 0]
        assert edges == [(1, 2), (2, 3), (3, 0), (0, 1)]

        G = nx.complete_graph(3)

        edges = list(nx.eulerian_circuit(G, source=0))
        nodes = [u for u, v in edges]
        assert nodes == [0, 2, 1]
        assert edges == [(0, 2), (2, 1), (1, 0)]

        edges = list(nx.eulerian_circuit(G, source=1))
        nodes = [u for u, v in edges]
        assert nodes == [1, 2, 0]
        assert edges == [(1, 2), (2, 0), (0, 1)]

    def test_eulerian_circuit_digraph(self):
        G = nx.DiGraph()
        nx.add_cycle(G, [0, 1, 2, 3])

        edges = list(nx.eulerian_circuit(G, source=0))
        nodes = [u for u, v in edges]
        assert nodes == [0, 1, 2, 3]
        assert edges == [(0, 1), (1, 2), (2, 3), (3, 0)]

        edges = list(nx.eulerian_circuit(G, source=1))
        nodes = [u for u, v in edges]
        assert nodes == [1, 2, 3, 0]
        assert edges == [(1, 2), (2, 3), (3, 0), (0, 1)]

    def test_multigraph(self):
        G = nx.MultiGraph()
        nx.add_cycle(G, [0, 1, 2, 3])
        G.add_edge(1, 2)
        G.add_edge(1, 2)
        edges = list(nx.eulerian_circuit(G, source=0))
        nodes = [u for u, v in edges]
        assert nodes == [0, 3, 2, 1, 2, 1]
        assert edges == [(0, 3), (3, 2), (2, 1), (1, 2), (2, 1), (1, 0)]

    def test_multigraph_with_keys(self):
        G = nx.MultiGraph()
        nx.add_cycle(G, [0, 1, 2, 3])
        G.add_edge(1, 2)
        G.add_edge(1, 2)
        edges = list(nx.eulerian_circuit(G, source=0, keys=True))
        nodes = [u for u, v, k in edges]
        assert nodes == [0, 3, 2, 1, 2, 1]
        assert edges[:2] == [(0, 3, 0), (3, 2, 0)]
        assert collections.Counter(edges[2:5]) == collections.Counter(
            [(2, 1, 0), (1, 2, 1), (2, 1, 2)]
        )
        assert edges[5:] == [(1, 0, 0)]

    def test_not_eulerian(self):
        with pytest.raises(nx.NetworkXError):
            f = list(nx.eulerian_circuit(nx.complete_graph(4)))


class TestIsSemiEulerian:
    def test_is_semieulerian(self):
        # Test graphs with Eulerian paths but no cycles return True.
        assert nx.is_semieulerian(nx.path_graph(4))
        G = nx.path_graph(6, create_using=nx.DiGraph)
        assert nx.is_semieulerian(G)

        # Test graphs with Eulerian cycles return False.
        assert not nx.is_semieulerian(nx.complete_graph(5))
        assert not nx.is_semieulerian(nx.complete_graph(7))
        assert not nx.is_semieulerian(nx.hypercube_graph(4))
        assert not nx.is_semieulerian(nx.hypercube_graph(6))


class TestHasEulerianPath:
    def test_has_eulerian_path_cyclic(self):
        # Test graphs with Eulerian cycles return True.
        assert nx.has_eulerian_path(nx.complete_graph(5))
        assert nx.has_eulerian_path(nx.complete_graph(7))
        assert nx.has_eulerian_path(nx.hypercube_graph(4))
        assert nx.has_eulerian_path(nx.hypercube_graph(6))

    def test_has_eulerian_path_non_cyclic(self):
        # Test graphs with Eulerian paths but no cycles return True.
        assert nx.has_eulerian_path(nx.path_graph(4))
        G = nx.path_graph(6, create_using=nx.DiGraph)
        assert nx.has_eulerian_path(G)

    def test_has_eulerian_path_directed_graph(self):
        # Test directed graphs and returns False
        G = nx.DiGraph()
        G.add_edges_from([(0, 1), (1, 2), (0, 2)])
        assert not nx.has_eulerian_path(G)

        # Test directed graphs without isolated node returns True
        G = nx.DiGraph()
        G.add_edges_from([(0, 1), (1, 2), (2, 0)])
        assert nx.has_eulerian_path(G)

        # Test directed graphs with isolated node returns False
        G.add_node(3)
        assert not nx.has_eulerian_path(G)

    @pytest.mark.parametrize("G", (nx.Graph(), nx.DiGraph()))
    def test_has_eulerian_path_not_weakly_connected(self, G):
        G.add_edges_from([(0, 1), (2, 3), (3, 2)])
        assert not nx.has_eulerian_path(G)

    @pytest.mark.parametrize("G", (nx.Graph(), nx.DiGraph()))
    def test_has_eulerian_path_unbalancedins_more_than_one(self, G):
        G.add_edges_from([(0, 1), (2, 3)])
        assert not nx.has_eulerian_path(G)


class TestFindPathStart:
    def testfind_path_start(self):
        find_path_start = nx.algorithms.euler._find_path_start
        # Test digraphs return correct starting node.
        G = nx.path_graph(6, create_using=nx.DiGraph)
        assert find_path_start(G) == 0
        edges = [(0, 1), (1, 2), (2, 0), (4, 0)]
        assert find_path_start(nx.DiGraph(edges)) == 4

        # Test graph with no Eulerian path return None.
        edges = [(0, 1), (1, 2), (2, 3), (2, 4)]
        assert find_path_start(nx.DiGraph(edges)) is None


class TestEulerianPath:
    def test_eulerian_path(self):
        x = [(4, 0), (0, 1), (1, 2), (2, 0)]
        for e1, e2 in zip(x, nx.eulerian_path(nx.DiGraph(x))):
            assert e1 == e2

    def test_eulerian_path_straight_link(self):
        G = nx.DiGraph()
        result = [(1, 2), (2, 3), (3, 4), (4, 5)]
        G.add_edges_from(result)
        assert result == list(nx.eulerian_path(G))
        assert result == list(nx.eulerian_path(G, source=1))
        with pytest.raises(nx.NetworkXError):
            list(nx.eulerian_path(G, source=3))
        with pytest.raises(nx.NetworkXError):
            list(nx.eulerian_path(G, source=4))
        with pytest.raises(nx.NetworkXError):
            list(nx.eulerian_path(G, source=5))

    def test_eulerian_path_multigraph(self):
        G = nx.MultiDiGraph()
        result = [(2, 1), (1, 2), (2, 1), (1, 2), (2, 3), (3, 4), (4, 3)]
        G.add_edges_from(result)
        assert result == list(nx.eulerian_path(G))
        assert result == list(nx.eulerian_path(G, source=2))
        with pytest.raises(nx.NetworkXError):
            list(nx.eulerian_path(G, source=3))
        with pytest.raises(nx.NetworkXError):
            list(nx.eulerian_path(G, source=4))

    def test_eulerian_path_eulerian_circuit(self):
        G = nx.DiGraph()
        result = [(1, 2), (2, 3), (3, 4), (4, 1)]
        result2 = [(2, 3), (3, 4), (4, 1), (1, 2)]
        result3 = [(3, 4), (4, 1), (1, 2), (2, 3)]
        G.add_edges_from(result)
        assert result == list(nx.eulerian_path(G))
        assert result == list(nx.eulerian_path(G, source=1))
        assert result2 == list(nx.eulerian_path(G, source=2))
        assert result3 == list(nx.eulerian_path(G, source=3))

    def test_eulerian_path_undirected(self):
        G = nx.Graph()
        result = [(1, 2), (2, 3), (3, 4), (4, 5)]
        result2 = [(5, 4), (4, 3), (3, 2), (2, 1)]
        G.add_edges_from(result)
        assert list(nx.eulerian_path(G)) in (result, result2)
        assert result == list(nx.eulerian_path(G, source=1))
        assert result2 == list(nx.eulerian_path(G, source=5))
        with pytest.raises(nx.NetworkXError):
            list(nx.eulerian_path(G, source=3))
        with pytest.raises(nx.NetworkXError):
            list(nx.eulerian_path(G, source=2))

    def test_eulerian_path_multigraph_undirected(self):
        G = nx.MultiGraph()
        result = [(2, 1), (1, 2), (2, 1), (1, 2), (2, 3), (3, 4)]
        G.add_edges_from(result)
        assert result == list(nx.eulerian_path(G))
        assert result == list(nx.eulerian_path(G, source=2))
        with pytest.raises(nx.NetworkXError):
            list(nx.eulerian_path(G, source=3))
        with pytest.raises(nx.NetworkXError):
            list(nx.eulerian_path(G, source=1))

    @pytest.mark.parametrize(
        ("graph_type", "result"),
        (
            (nx.MultiGraph, [(0, 1, 0), (1, 0, 1)]),
            (nx.MultiDiGraph, [(0, 1, 0), (1, 0, 0)]),
        ),
    )
    def test_eulerian_with_keys(self, graph_type, result):
        G = graph_type([(0, 1), (1, 0)])
        answer = nx.eulerian_path(G, keys=True)
        assert list(answer) == result


class TestEulerize:
    def test_disconnected(self):
        with pytest.raises(nx.NetworkXError):
            G = nx.from_edgelist([(0, 1), (2, 3)])
            nx.eulerize(G)

    def test_null_graph(self):
        with pytest.raises(nx.NetworkXPointlessConcept):
            nx.eulerize(nx.Graph())

    def test_null_multigraph(self):
        with pytest.raises(nx.NetworkXPointlessConcept):
            nx.eulerize(nx.MultiGraph())

    def test_on_empty_graph(self):
        with pytest.raises(nx.NetworkXError):
            nx.eulerize(nx.empty_graph(3))

    def test_on_eulerian(self):
        G = nx.cycle_graph(3)
        H = nx.eulerize(G)
        assert nx.is_isomorphic(G, H)

    def test_on_eulerian_multigraph(self):
        G = nx.MultiGraph(nx.cycle_graph(3))
        G.add_edge(0, 1)
        H = nx.eulerize(G)
        assert nx.is_eulerian(H)

    def test_on_complete_graph(self):
        G = nx.complete_graph(4)
        assert nx.is_eulerian(nx.eulerize(G))
        assert nx.is_eulerian(nx.eulerize(nx.MultiGraph(G)))

    def test_on_non_eulerian_graph(self):
        G = nx.cycle_graph(18)
        G.add_edge(0, 18)
        G.add_edge(18, 19)
        G.add_edge(17, 19)
        G.add_edge(4, 20)
        G.add_edge(20, 21)
        G.add_edge(21, 22)
        G.add_edge(22, 23)
        G.add_edge(23, 24)
        G.add_edge(24, 25)
        G.add_edge(25, 26)
        G.add_edge(26, 27)
        G.add_edge(27, 28)
        G.add_edge(28, 13)
        assert not nx.is_eulerian(G)
        G = nx.eulerize(G)
        assert nx.is_eulerian(G)
        assert nx.number_of_edges(G) == 39
