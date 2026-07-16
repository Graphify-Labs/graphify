import random

import pytest

import networkx as nx
from networkx.utils import edges_equal, nodes_equal


def test_degree_histogram_empty():
    G = nx.Graph()
    assert nx.degree_histogram(G) == []


class TestFunction:
    def setup_method(self):
        self.G = nx.Graph({0: [1, 2, 3], 1: [1, 2, 0], 4: []}, name="Test")
        self.Gdegree = {0: 3, 1: 2, 2: 2, 3: 1, 4: 0}
        self.Gnodes = list(range(5))
        self.Gedges = [(0, 1), (0, 2), (0, 3), (1, 0), (1, 1), (1, 2)]
        self.DG = nx.DiGraph({0: [1, 2, 3], 1: [1, 2, 0], 4: []})
        self.DGin_degree = {0: 1, 1: 2, 2: 2, 3: 1, 4: 0}
        self.DGout_degree = {0: 3, 1: 3, 2: 0, 3: 0, 4: 0}
        self.DGnodes = list(range(5))
        self.DGedges = [(0, 1), (0, 2), (0, 3), (1, 0), (1, 1), (1, 2)]

    def test_nodes(self):
        assert nodes_equal(self.G.nodes(), list(nx.nodes(self.G)))
        assert nodes_equal(self.DG.nodes(), list(nx.nodes(self.DG)))

    def test_edges(self):
        assert edges_equal(self.G.edges(), list(nx.edges(self.G)))
        assert sorted(self.DG.edges()) == sorted(nx.edges(self.DG))
        assert edges_equal(
            self.G.edges(nbunch=[0, 1, 3]), list(nx.edges(self.G, nbunch=[0, 1, 3]))
        )
        assert sorted(self.DG.edges(nbunch=[0, 1, 3])) == sorted(
            nx.edges(self.DG, nbunch=[0, 1, 3])
        )

    def test_degree(self):
        assert edges_equal(self.G.degree(), list(nx.degree(self.G)))
        assert sorted(self.DG.degree()) == sorted(nx.degree(self.DG))
        assert edges_equal(
            self.G.degree(nbunch=[0, 1]), list(nx.degree(self.G, nbunch=[0, 1]))
        )
        assert sorted(self.DG.degree(nbunch=[0, 1])) == sorted(
            nx.degree(self.DG, nbunch=[0, 1])
        )
        assert edges_equal(
            self.G.degree(weight="weight"), list(nx.degree(self.G, weight="weight"))
        )
        assert sorted(self.DG.degree(weight="weight")) == sorted(
            nx.degree(self.DG, weight="weight")
        )

    def test_neighbors(self):
        assert list(self.G.neighbors(1)) == list(nx.neighbors(self.G, 1))
        assert list(self.DG.neighbors(1)) == list(nx.neighbors(self.DG, 1))

    def test_number_of_nodes(self):
        assert self.G.number_of_nodes() == nx.number_of_nodes(self.G)
        assert self.DG.number_of_nodes() == nx.number_of_nodes(self.DG)

    def test_number_of_edges(self):
        assert self.G.number_of_edges() == nx.number_of_edges(self.G)
        assert self.DG.number_of_edges() == nx.number_of_edges(self.DG)

    def test_is_directed(self):
        assert self.G.is_directed() == nx.is_directed(self.G)
        assert self.DG.is_directed() == nx.is_directed(self.DG)

    def test_add_star(self):
        G = self.G.copy()
        nlist = [12, 13, 14, 15]
        nx.add_star(G, nlist)
        assert edges_equal(G.edges(nlist), [(12, 13), (12, 14), (12, 15)])

        G = self.G.copy()
        nx.add_star(G, nlist, weight=2.0)
        assert edges_equal(
            G.edges(nlist, data=True),
            [
                (12, 13, {"weight": 2.0}),
                (12, 14, {"weight": 2.0}),
                (12, 15, {"weight": 2.0}),
            ],
        )

        G = self.G.copy()
        nlist = [12]
        nx.add_star(G, nlist)
        assert nodes_equal(G, list(self.G) + nlist)

        G = self.G.copy()
        nlist = []
        nx.add_star(G, nlist)
        assert nodes_equal(G.nodes, self.Gnodes)
        assert edges_equal(G.edges, self.G.edges)

    def test_add_path(self):
        G = self.G.copy()
        nlist = [12, 13, 14, 15]
        nx.add_path(G, nlist)
        assert edges_equal(G.edges(nlist), [(12, 13), (13, 14), (14, 15)])
        G = self.G.copy()
        nx.add_path(G, nlist, weight=2.0)
        assert edges_equal(
            G.edges(nlist, data=True),
            [
                (12, 13, {"weight": 2.0}),
                (13, 14, {"weight": 2.0}),
                (14, 15, {"weight": 2.0}),
            ],
        )

        G = self.G.copy()
        nlist = ["node"]
        nx.add_path(G, nlist)
        assert edges_equal(G.edges(nlist), [])
        assert nodes_equal(G, list(self.G) + ["node"])

        G = self.G.copy()
        nlist = iter(["node"])
        nx.add_path(G, nlist)
        assert edges_equal(G.edges(["node"]), [])
        assert nodes_equal(G, list(self.G) + ["node"])

        G = self.G.copy()
        nlist = [12]
        nx.add_path(G, nlist)
        assert edges_equal(G.edges(nlist), [])
        assert nodes_equal(G, list(self.G) + [12])

        G = self.G.copy()
        nlist = iter([12])
        nx.add_path(G, nlist)
        assert edges_equal(G.edges([12]), [])
        assert nodes_equal(G, list(self.G) + [12])

        G = self.G.copy()
        nlist = []
        nx.add_path(G, nlist)
        assert edges_equal(G.edges, self.G.edges)
        assert nodes_equal(G, list(self.G))

        G = self.G.copy()
        nlist = iter([])
        nx.add_path(G, nlist)
        assert edges_equal(G.edges, self.G.edges)
        assert nodes_equal(G, list(self.G))

    def test_add_cycle(self):
        G = self.G.copy()
        nlist = [12, 13, 14, 15]
        oklists = [
            [(12, 13), (12, 15), (13, 14), (14, 15)],
            [(12, 13), (13, 14), (14, 15), (15, 12)],
        ]
        nx.add_cycle(G, nlist)
        assert sorted(G.edges(nlist)) in oklists
        G = self.G.copy()
        oklists = [
            [
                (12, 13, {"weight": 1.0}),
                (12, 15, {"weight": 1.0}),
                (13, 14, {"weight": 1.0}),
                (14, 15, {"weight": 1.0}),
            ],
            [
                (12, 13, {"weight": 1.0}),
                (13, 14, {"weight": 1.0}),
                (14, 15, {"weight": 1.0}),
                (15, 12, {"weight": 1.0}),
            ],
        ]
        nx.add_cycle(G, nlist, weight=1.0)
        assert sorted(G.edges(nlist, data=True)) in oklists

        G = self.G.copy()
        nlist = [12]
        nx.add_cycle(G, nlist)
        assert nodes_equal(G, list(self.G) + nlist)

        G = self.G.copy()
        nlist = []
        nx.add_cycle(G, nlist)
        assert nodes_equal(G.nodes, self.Gnodes)
        assert edges_equal(G.edges, self.G.edges)

    def test_subgraph(self):
        assert (
            self.G.subgraph([0, 1, 2, 4]).adj == nx.subgraph(self.G, [0, 1, 2, 4]).adj
        )
        assert (
            self.DG.subgraph([0, 1, 2, 4]).adj == nx.subgraph(self.DG, [0, 1, 2, 4]).adj
        )
        assert (
            self.G.subgraph([0, 1, 2, 4]).adj
            == nx.induced_subgraph(self.G, [0, 1, 2, 4]).adj
        )
        assert (
            self.DG.subgraph([0, 1, 2, 4]).adj
            == nx.induced_subgraph(self.DG, [0, 1, 2, 4]).adj
        )
        # subgraph-subgraph chain is allowed in function interface
        H = nx.induced_subgraph(self.G.subgraph([0, 1, 2, 4]), [0, 1, 4])
        assert H._graph is not self.G
        assert H.adj == self.G.subgraph([0, 1, 4]).adj

    def test_edge_subgraph(self):
        assert (
            self.G.edge_subgraph([(1, 2), (0, 3)]).adj
            == nx.edge_subgraph(self.G, [(1, 2), (0, 3)]).adj
        )
        assert (
            self.DG.edge_subgraph([(1, 2), (0, 3)]).adj
            == nx.edge_subgraph(self.DG, [(1, 2), (0, 3)]).adj
        )

    def test_create_empty_copy(self):
        G = nx.create_empty_copy(self.G, with_data=False)
        assert nodes_equal(G, list(self.G))
        assert G.graph == {}
        assert G._node == {}.fromkeys(self.G.nodes(), {})
        assert G._adj == {}.fromkeys(self.G.nodes(), {})
        G = nx.create_empty_copy(self.G)
        assert nodes_equal(G, list(self.G))
        assert G.graph == self.G.graph
        assert G._node == self.G._node
        assert G._adj == {}.fromkeys(self.G.nodes(), {})

    def test_degree_histogram(self):
        assert nx.degree_histogram(self.G) == [1, 1, 1, 1, 1]

    def test_density(self):
        assert nx.density(self.G) == 0.5
        assert nx.density(self.DG) == 0.3
        G = nx.Graph()
        G.add_node(1)
        assert nx.density(G) == 0.0

    def test_density_selfloop(self):
        G = nx.Graph()
        G.add_edge(1, 1)
        assert nx.density(G) == 0.0
        G.add_edge(1, 2)
        assert nx.density(G) == 2.0

    def test_freeze(self):
        G = nx.freeze(self.G)
        assert G.frozen
        pytest.raises(nx.NetworkXError, G.add_node, 1)
        pytest.raises(nx.NetworkXError, G.add_nodes_from, [1])
        pytest.raises(nx.NetworkXError, G.remove_node, 1)
        pytest.raises(nx.NetworkXError, G.remove_nodes_from, [1])
        pytest.raises(nx.NetworkXError, G.add_edge, 1, 2)
        pytest.raises(nx.NetworkXError, G.add_edges_from, [(1, 2)])
        pytest.raises(nx.NetworkXError, G.remove_edge, 1, 2)
        pytest.raises(nx.NetworkXError, G.remove_edges_from, [(1, 2)])
        pytest.raises(nx.NetworkXError, G.clear_edges)
        pytest.raises(nx.NetworkXError, G.clear)

    def test_is_frozen(self):
        assert not nx.is_frozen(self.G)
        G = nx.freeze(self.G)
        assert G.frozen == nx.is_frozen(self.G)
        assert G.frozen

    def test_node_attributes_are_still_mutable_on_frozen_graph(self):
        G = nx.freeze(nx.path_graph(3))
        node = G.nodes[0]
        node["node_attribute"] = True
        assert node["node_attribute"] == True

    def test_edge_attributes_are_still_mutable_on_frozen_graph(self):
        G = nx.freeze(nx.path_graph(3))
        edge = G.edges[(0, 1)]
        edge["edge_attribute"] = True
        assert edge["edge_attribute"] == True

    def test_neighbors_complete_graph(self):
        graph = nx.complete_graph(100)
        pop = random.sample(list(graph), 1)
        nbors = list(nx.neighbors(graph, pop[0]))
        # should be all the other vertices in the graph
        assert len(nbors) == len(graph) - 1

        graph = nx.path_graph(100)
        node = random.sample(list(graph), 1)[0]
        nbors = list(nx.neighbors(graph, node))
        # should be all the other vertices in the graph
        if node != 0 and node != 99:
            assert len(nbors) == 2
        else:
            assert len(nbors) == 1

        # create a star graph with 99 outer nodes
        graph = nx.star_graph(99)
        nbors = list(nx.neighbors(graph, 0))
        assert len(nbors) == 99

    def test_non_neighbors(self):
        graph = nx.complete_graph(100)
        pop = random.sample(list(graph), 1)
        nbors = nx.non_neighbors(graph, pop[0])
        # should be all the other vertices in the graph
        assert len(nbors) == 0

        graph = nx.path_graph(100)
        node = random.sample(list(graph), 1)[0]
        nbors = nx.non_neighbors(graph, node)
        # should be all the other vertices in the graph
        if node != 0 and node != 99:
            assert len(nbors) == 97
        else:
            assert len(nbors) == 98

        # create a star graph with 99 outer nodes
        graph = nx.star_graph(99)
        nbors = nx.non_neighbors(graph, 0)
        assert len(nbors) == 0

        # disconnected graph
        graph = nx.Graph()
        graph.add_nodes_from(range(10))
        nbors = nx.non_neighbors(graph, 0)
        assert len(nbors) == 9

    def test_non_edges(self):
        # All possible edges exist
        graph = nx.complete_graph(5)
        nedges = list(nx.non_edges(graph))
        assert len(nedges) == 0

        graph = nx.path_graph(4)
        expected = [(0, 2), (0, 3), (1, 3)]
        nedges = list(nx.non_edges(graph))
        for u, v in expected:
            assert (u, v) in nedges or (v, u) in nedges

        graph = nx.star_graph(4)
        expected = [(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)]
        nedges = list(nx.non_edges(graph))
        for u, v in expected:
            assert (u, v) in nedges or (v, u) in nedges

        # Directed graphs
        graph = nx.DiGraph()
        graph.add_edges_from([(0, 2), (2, 0), (2, 1)])
        expected = [(0, 1), (1, 0), (1, 2)]
        nedges = list(nx.non_edges(graph))
        for e in expected:
            assert e in nedges

    def test_is_weighted(self):
        G = nx.Graph()
        assert not nx.is_weighted(G)

        G = nx.path_graph(4)
        assert not nx.is_weighted(G)
        assert not nx.is_weighted(G, (2, 3))

        G.add_node(4)
        G.add_edge(3, 4, weight=4)
        assert not nx.is_weighted(G)
        assert nx.is_weighted(G, (3, 4))

        G = nx.DiGraph()
        G.add_weighted_edges_from(
            [
                ("0", "3", 3),
                ("0", "1", -5),
                ("1", "0", -5),
                ("0", "2", 2),
                ("1", "2", 4),
                ("2", "3", 1),
            ]
        )
        assert nx.is_weighted(G)
        assert nx.is_weighted(G, ("1", "0"))

        G = G.to_undirected()
        assert nx.is_weighted(G)
        assert nx.is_weighted(G, ("1", "0"))

        pytest.raises(nx.NetworkXError, nx.is_weighted, G, (1, 2))

    def test_is_negatively_weighted(self):
        G = nx.Graph()
        assert not nx.is_negatively_weighted(G)

        G.add_node(1)
        G.add_nodes_from([2, 3, 4, 5])
        assert not nx.is_negatively_weighted(G)

        G.add_edge(1, 2, weight=4)
        assert not nx.is_negatively_weighted(G, (1, 2))

        G.add_edges_from([(1, 3), (2, 4), (2, 6)])
        G[1][3]["color"] = "blue"
        assert not nx.is_negatively_weighted(G)
        assert not nx.is_negatively_weighted(G, (1, 3))

        G[2][4]["weight"] = -2
        assert nx.is_negatively_weighted(G, (2, 4))
        assert nx.is_negatively_weighted(G)

        G = nx.DiGraph()
        G.add_weighted_edges_from(
            [
                ("0", "3", 3),
                ("0", "1", -5),
                ("1", "0", -2),
                ("0", "2", 2),
                ("1", "2", -3),
                ("2", "3", 1),
            ]
        )
        assert nx.is_negatively_weighted(G)
        assert not nx.is_negatively_weighted(G, ("0", "3"))
        assert nx.is_negatively_weighted(G, ("1", "0"))

        pytest.raises(nx.NetworkXError, nx.is_negatively_weighted, G, (1, 4))


class TestCommonNeighbors:
    @classmethod
    def setup_class(cls):
        cls.func = staticmethod(nx.common_neighbors)

        def test_func(G, u, v, expected):
            result = sorted(cls.func(G, u, v))
            assert result == expected

        cls.test = staticmethod(test_func)

    def test_K5(self):
        G = nx.complete_graph(5)
        self.test(G, 0, 1, [2, 3, 4])

    def test_P3(self):
        G = nx.path_graph(3)
        self.test(G, 0, 2, [1])

    def test_S4(self):
        G = nx.star_graph(4)
        self.test(G, 1, 2, [0])

    def test_digraph(self):
        with pytest.raises(nx.NetworkXNotImplemented):
            G = nx.DiGraph()
            G.add_edges_from([(0, 1), (1, 2)])
            self.func(G, 0, 2)

    def test_nonexistent_nodes(self):
        G = nx.complete_graph(5)
        pytest.raises(nx.NetworkXError, nx.common_neighbors, G, 5, 4)
        pytest.raises(nx.NetworkXError, nx.common_neighbors, G, 4, 5)
        pytest.raises(nx.NetworkXError, nx.common_neighbors, G, 5, 6)

    def test_custom1(self):
        """Case of no common neighbors."""
        G = nx.Graph()
        G.add_nodes_from([0, 1])
        self.test(G, 0, 1, [])

    def test_custom2(self):
        """Case of equal nodes."""
        G = nx.complete_graph(4)
        self.test(G, 0, 0, [1, 2, 3])


@pytest.mark.parametrize(
    "graph_type", (nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph)
)
def test_set_node_attributes(graph_type):
    # Test single value
    G = nx.path_graph(3, create_using=graph_type)
    vals = 100
    attr = "hello"
    nx.set_node_attributes(G, vals, attr)
    assert G.nodes[0][attr] == vals
    assert G.nodes[1][attr] == vals
    assert G.nodes[2][attr] == vals

    # Test dictionary
    G = nx.path_graph(3, create_using=graph_type)
    vals = dict(zip(sorted(G.nodes()), range(len(G))))
    attr = "hi"
    nx.set_node_attributes(G, vals, attr)
    assert G.nodes[0][attr] == 0
    assert G.nodes[1][attr] == 1
    assert G.nodes[2][attr] == 2

    # Test dictionary of dictionaries
    G = nx.path_graph(3, create_using=graph_type)
    d = {"hi": 0, "hello": 200}
    vals = dict.fromkeys(G.nodes(), d)
    vals.pop(0)
    nx.set_node_attributes(G, vals)
    assert G.nodes[0] == {}
    assert G.nodes[1]["hi"] == 0
    assert G.nodes[2]["hello"] == 200


@pytest.mark.parametrize(
    ("values", "name"),
    (
        ({0: "red", 1: "blue"}, "color"),  # values dictionary
        ({0: {"color": "red"}, 1: {"color": "blue"}}, None),  # dict-of-dict
    ),
)
def test_set_node_attributes_ignores_extra_nodes(values, name):
    """
    When `values` is a dict or dict-of-dict keyed by nodes, ensure that keys
    that correspond to nodes not in G are ignored.
    """
    G = nx.Graph()
    G.add_node(0)
    nx.set_node_attributes(G, values, name)
    assert G.nodes[0]["color"] == "red"
    assert 1 not in G.nodes


@pytest.mark.parametrize("graph_type", (nx.Graph, nx.DiGraph))
def test_set_edge_attributes(graph_type):
    # Test single value
    G = nx.path_graph(3, create_using=graph_type)
    attr = "hello"
    vals = 3
    nx.set_edge_attributes(G, vals, attr)
    assert G[0][1][attr] == vals
    assert G[1][2][attr] == vals

    # Test multiple values
    G = nx.path_graph(3, create_using=graph_type)
    attr = "hi"
    edges = [(0, 1), (1, 2)]
    vals = dict(zip(edges, range(len(edges))))
    nx.set_edge_attributes(G, vals, attr)
    assert G[0][1][attr] == 0
    assert G[1][2][attr] == 1

    # Test dictionary of dictionaries
    G = nx.path_graph(3, create_using=graph_type)
    d = {"hi": 0, "hello": 200}
    edges = [(0, 1)]
    vals = dict.fromkeys(edges, d)
    nx.set_edge_attributes(G, vals)
    assert G[0][1]["hi"] == 0
    assert G[0][1]["hello"] == 200
    assert G[1][2] == {}


@pytest.mark.parametrize(
    ("values", "name"),
    (
        ({(0, 1): 1.0, (0, 2): 2.0}, "weight"),  # values dict
        ({(0, 1): {"weight": 1.0}, (0, 2): {"weight": 2.0}}, None),  # values dod
    ),
)
def test_set_edge_attributes_ignores_extra_edges(values, name):
    """If `values` is a dict or dict-of-dicts containing edges that are not in
    G, data associate with these edges should be ignored.
    """
    G = nx.Graph([(0, 1)])
    nx.set_edge_attributes(G, values, name)
    assert G[0][1]["weight"] == 1.0
    assert (0, 2) not in G.edges


@pytest.mark.parametrize("graph_type", (nx.MultiGraph, nx.MultiDiGraph))
def test_set_edge_attributes_multi(graph_type):
    # Test single value
    G = nx.path_graph(3, create_using=graph_type)
    attr = "hello"
    vals = 3
    nx.set_edge_attributes(G, vals, attr)
    assert G[0][1][0][attr] == vals
    assert G[1][2][0][attr] == vals

    # Test multiple values
    G = nx.path_graph(3, create_using=graph_type)
    attr = "hi"
    edges = [(0, 1, 0), (1, 2, 0)]
    vals = dict(zip(edges, range(len(edges))))
    nx.set_edge_attributes(G, vals, attr)
    assert G[0][1][0][attr] == 0
    assert G[1][2][0][attr] == 1

    # Test dictionary of dictionaries
    G = nx.path_graph(3, create_using=graph_type)
    d = {"hi": 0, "hello": 200}
    edges = [(0, 1, 0)]
    vals = dict.fromkeys(edges, d)
    nx.set_edge_attributes(G, vals)
    assert G[0][1][0]["hi"] == 0
    assert G[0][1][0]["hello"] == 200
    assert G[1][2][0] == {}


@pytest.mark.parametrize(
    ("values", "name"),
    (
        ({(0, 1, 0): 1.0, (0, 2, 0): 2.0}, "weight"),  # values dict
        ({(0, 1, 0): {"weight": 1.0}, (0, 2, 0): {"weight": 2.0}}, None),  # values dod
    ),
)
def test_set_edge_attributes_multi_ignores_extra_edges(values, name):
    """If `values` is a dict or dict-of-dicts containing edges that are not in
    G, data associate with these edges should be ignored.
    """
    G = nx.MultiGraph([(0, 1, 0), (0, 1, 1)])
    nx.set_edge_attributes(G, values, name)
    assert G[0][1][0]["weight"] == 1.0
    assert G[0][1][1] == {}
    assert (0, 2) not in G.edges()


def test_get_node_attributes():
    graphs = [nx.Graph(), nx.DiGraph(), nx.MultiGraph(), nx.MultiDiGraph()]
    for G in graphs:
        G = nx.path_graph(3, create_using=G)
        attr = "hello"
        vals = 100
        nx.set_node_attributes(G, vals, attr)
        attrs = nx.get_node_attributes(G, attr)
        assert attrs[0] == vals
        assert attrs[1] == vals
        assert attrs[2] == vals
        default_val = 1
        G.add_node(4)
        attrs = nx.get_node_attributes(G, attr, default=default_val)
        assert attrs[4] == default_val


def test_get_edge_attributes():
    graphs = [nx.Graph(), nx.DiGraph(), nx.MultiGraph(), nx.MultiDiGraph()]
    for G in graphs:
        G = nx.path_graph(3, create_using=G)
        attr = "hello"
        vals = 100
        nx.set_edge_attributes(G, vals, attr)
        attrs = nx.get_edge_attributes(G, attr)
        assert len(attrs) == 2

        for edge in G.edges:
            assert attrs[edge] == vals

        default_val = vals
        G.add_edge(4, 5)
        deafult_attrs = nx.get_edge_attributes(G, attr, default=default_val)
        assert len(deafult_attrs) == 3

        for edge in G.edges:
            assert deafult_attrs[edge] == vals


@pytest.mark.parametrize(
    "graph_type", (nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph)
)
def test_remove_node_attributes(graph_type):
    # Test removing single attribute
    G = nx.path_graph(3, create_using=graph_type)
    vals = 100
    attr = "hello"
    nx.set_node_attributes(G, vals, attr)
    nx.remove_node_attributes(G, attr)
    assert attr not in G.nodes[0]
    assert attr not in G.nodes[1]
    assert attr not in G.nodes[2]

    # Test removing single attribute when multiple present
    G = nx.path_graph(3, create_using=graph_type)
    other_vals = 200
    other_attr = "other"
    nx.set_node_attributes(G, vals, attr)
    nx.set_node_attributes(G, other_vals, other_attr)
    nx.remove_node_attributes(G, attr)
    assert attr not in G.nodes[0]
    assert G.nodes[0][other_attr] == other_vals
    assert attr not in G.nodes[1]
    assert G.nodes[1][other_attr] == other_vals
    assert attr not in G.nodes[2]
    assert G.nodes[2][other_attr] == other_vals

    # Test removing multiple attributes
    G = nx.path_graph(3, create_using=graph_type)
    nx.set_node_attributes(G, vals, attr)
    nx.set_node_attributes(G, other_vals, other_attr)
    nx.remove_node_attributes(G, attr, other_attr)
    assert attr not in G.nodes[0] and other_attr not in G.nodes[0]
    assert attr not in G.nodes[1] and other_attr not in G.nodes[1]
    assert attr not in G.nodes[2] and other_attr not in G.nodes[2]

    # Test removing multiple (but not all) attributes
    G = nx.path_graph(3, create_using=graph_type)
    third_vals = 300
    third_attr = "three"
    nx.set_node_attributes(
        G,
        {
            n: {attr: vals, other_attr: other_vals, third_attr: third_vals}
            for n in G.nodes()
        },
    )
    nx.remove_node_attributes(G, other_attr, third_attr)
    assert other_attr not in G.nodes[0] and third_attr not in G.nodes[0]
    assert other_attr not in G.nodes[1] and third_attr not in G.nodes[1]
    assert other_attr not in G.nodes[2] and third_attr not in G.nodes[2]
    assert G.nodes[0][attr] == vals
    assert G.nodes[1][attr] == vals
    assert G.nodes[2][attr] == vals

    # Test incomplete node attributes
    G = nx.path_graph(3, create_using=graph_type)
    nx.set_node_attributes(
        G,
        {
            1: {attr: vals, other_attr: other_vals},
            2: {attr: vals, other_attr: other_vals},
        },
    )
    nx.remove_node_attributes(G, attr)
    assert attr not in G.nodes[0]
    assert attr not in G.nodes[1]
    assert attr not in G.nodes[2]
    assert G.nodes[1][other_attr] == other_vals
    assert G.nodes[2][other_attr] == other_vals

    # Test removing on a subset of nodes
    G = nx.path_graph(3, create_using=graph_type)
    nx.set_node_attributes(
        G,
        {
            n: {attr: vals, other_attr: other_vals, third_attr: third_vals}
            for n in G.nodes()
        },
    )
    nx.remove_node_attributes(G, attr, other_attr, nbunch=[0, 1])
    assert attr not in G.nodes[0] and other_attr not in G.nodes[0]
    assert attr not in G.nodes[1] and other_attr not in G.nodes[1]
    assert attr in G.nodes[2] and other_attr in G.nodes[2]
    assert third_attr in G.nodes[0] and G.nodes[0][third_attr] == third_vals
    assert third_attr in G.nodes[1] and G.nodes[1][third_attr] == third_vals


@pytest.mark.parametrize("graph_type", (nx.Graph, nx.DiGraph))
def test_remove_edge_attributes(graph_type):
    # Test removing single attribute
    G = nx.path_graph(3, create_using=graph_type)
    attr = "hello"
    vals = 100
    nx.set_edge_attributes(G, vals, attr)
    nx.remove_edge_attributes(G, attr)
    assert len(nx.get_edge_attributes(G, attr)) == 0

    # Test removing only some attributes
    G = nx.path_graph(3, create_using=graph_type)
    other_attr = "other"
    other_vals = 200
    nx.set_edge_attributes(G, vals, attr)
    nx.set_edge_attributes(G, other_vals, other_attr)
    nx.remove_edge_attributes(G, attr)

    assert attr not in G[0][1]
    assert attr not in G[1][2]
    assert G[0][1][other_attr] == 200
    assert G[1][2][other_attr] == 200

    # Test removing multiple attributes
    G = nx.path_graph(3, create_using=graph_type)
    nx.set_edge_attributes(G, vals, attr)
    nx.set_edge_attributes(G, other_vals, other_attr)
    nx.remove_edge_attributes(G, attr, other_attr)
    assert attr not in G[0][1] and other_attr not in G[0][1]
    assert attr not in G[1][2] and other_attr not in G[1][2]

    # Test removing multiple (not all) attributes
    G = nx.path_graph(3, create_using=graph_type)
    third_attr = "third"
    third_vals = 300
    nx.set_edge_attributes(
        G,
        {
            (u, v): {attr: vals, other_attr: other_vals, third_attr: third_vals}
            for u, v in G.edges()
        },
    )
    nx.remove_edge_attributes(G, other_attr, third_attr)
    assert other_attr not in G[0][1] and third_attr not in G[0][1]
    assert other_attr not in G[1][2] and third_attr not in G[1][2]
    assert G[0][1][attr] == vals
    assert G[1][2][attr] == vals

    # Test removing incomplete edge attributes
    G = nx.path_graph(3, create_using=graph_type)
    nx.set_edge_attributes(G, {(0, 1): {attr: vals, other_attr: other_vals}})
    nx.remove_edge_attributes(G, other_attr)
    assert other_attr not in G[0][1] and G[0][1][attr] == vals
    assert other_attr not in G[1][2]

    # Test removing subset of edge attributes
    G = nx.path_graph(3, create_using=graph_type)
    nx.set_edge_attributes(
        G,
        {
            (u, v): {attr: vals, other_attr: other_vals, third_attr: third_vals}
            for u, v in G.edges()
        },
    )
    nx.remove_edge_attributes(G, other_attr, third_attr, ebunch=[(0, 1)])
    assert other_attr not in G[0][1] and third_attr not in G[0][1]
    assert other_attr in G[1][2] and third_attr in G[1][2]


@pytest.mark.parametrize("graph_type", (nx.MultiGraph, nx.MultiDiGraph))
def test_remove_multi_edge_attributes(graph_type):
    # Test removing single attribute
    G = nx.path_graph(3, create_using=graph_type)
    G.add_edge(1, 2)
    attr = "hello"
    vals = 100
    nx.set_edge_attributes(G, vals, attr)
    nx.remove_edge_attributes(G, attr)
    assert attr not in G[0][1][0]
    assert attr not in G[1][2][0]
    assert attr not in G[1][2][1]

    # Test removing only some attributes
    G = nx.path_graph(3, create_using=graph_type)
    G.add_edge(1, 2)
    other_attr = "other"
    other_vals = 200
    nx.set_edge_attributes(G, vals, attr)
    nx.set_edge_attributes(G, other_vals, other_attr)
    nx.remove_edge_attributes(G, attr)
    assert attr not in G[0][1][0]
    assert attr not in G[1][2][0]
    assert attr not in G[1][2][1]
    assert G[0][1][0][other_attr] == other_vals
    assert G[1][2][0][other_attr] == other_vals
    assert G[1][2][1][other_attr] == other_vals

    # Test removing multiple attributes
    G = nx.path_graph(3, create_using=graph_type)
    G.add_edge(1, 2)
    nx.set_edge_attributes(G, vals, attr)
    nx.set_edge_attributes(G, other_vals, other_attr)
    nx.remove_edge_attributes(G, attr, other_attr)
    assert attr not in G[0][1][0] and other_attr not in G[0][1][0]
    assert attr not in G[1][2][0] and other_attr not in G[1][2][0]
    assert attr not in G[1][2][1] and other_attr not in G[1][2][1]

    # Test removing multiple (not all) attributes
    G = nx.path_graph(3, create_using=graph_type)
    G.add_edge(1, 2)
    third_attr = "third"
    third_vals = 300
    nx.set_edge_attributes(
        G,
        {
            (u, v, k): {attr: vals, other_attr: other_vals, third_attr: third_vals}
            for u, v, k in G.edges(keys=True)
        },
    )
    nx.remove_edge_attributes(G, other_attr, third_attr)
    assert other_attr not in G[0][1][0] and third_attr not in G[0][1][0]
    assert other_attr not in G[1][2][0] and other_attr not in G[1][2][0]
    assert other_attr not in G[1][2][1] and other_attr not in G[1][2][1]
    assert G[0][1][0][attr] == vals
    assert G[1][2][0][attr] == vals
    assert G[1][2][1][attr] == vals

    # Test removing incomplete edge attributes
    G = nx.path_graph(3, create_using=graph_type)
    G.add_edge(1, 2)
    nx.set_edge_attributes(
        G,
        {
            (0, 1, 0): {attr: vals, other_attr: other_vals},
            (1, 2, 1): {attr: vals, other_attr: other_vals},
        },
    )
    nx.remove_edge_attributes(G, other_attr)
    assert other_attr not in G[0][1][0] and G[0][1][0][attr] == vals
    assert other_attr not in G[1][2][0]
    assert other_attr not in G[1][2][1]

    # Test removing subset of edge attributes
    G = nx.path_graph(3, create_using=graph_type)
    G.add_edge(1, 2)
    nx.set_edge_attributes(
        G,
        {
            (0, 1, 0): {attr: vals, other_attr: other_vals},
            (1, 2, 0): {attr: vals, other_attr: other_vals},
            (1, 2, 1): {attr: vals, other_attr: other_vals},
        },
    )
    nx.remove_edge_attributes(G, attr, ebunch=[(0, 1, 0), (1, 2, 0)])
    assert attr not in G[0][1][0] and other_attr in G[0][1][0]
    assert attr not in G[1][2][0] and other_attr in G[1][2][0]
    assert attr in G[1][2][1] and other_attr in G[1][2][1]


def test_is_empty():
    graphs = [nx.Graph(), nx.DiGraph(), nx.MultiGraph(), nx.MultiDiGraph()]
    for G in graphs:
        assert nx.is_empty(G)
        G.add_nodes_from(range(5))
        assert nx.is_empty(G)
        G.add_edges_from([(1, 2), (3, 4)])
        assert not nx.is_empty(G)


@pytest.mark.parametrize(
    "graph_type", [nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph]
)
def test_selfloops(graph_type):
    G = nx.complete_graph(3, create_using=graph_type)
    G.add_edge(0, 0)
    assert nodes_equal(nx.nodes_with_selfloops(G), [0])
    assert edges_equal(nx.selfloop_edges(G), [(0, 0)])
    assert edges_equal(nx.selfloop_edges(G, data=True), [(0, 0, {})])
    assert nx.number_of_selfloops(G) == 1


@pytest.mark.parametrize(
    "graph_type", [nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph]
)
def test_selfloop_edges_attr(graph_type):
    G = nx.complete_graph(3, create_using=graph_type)
    G.add_edge(0, 0)
    G.add_edge(1, 1, weight=2)
    assert edges_equal(
        nx.selfloop_edges(G, data=True), [(0, 0, {}), (1, 1, {"weight": 2})]
    )
    assert edges_equal(nx.selfloop_edges(G, data="weight"), [(0, 0, None), (1, 1, 2)])


def test_selfloop_edges_multi_with_data_and_keys():
    G = nx.complete_graph(3, create_using=nx.MultiGraph)
    G.add_edge(0, 0, weight=10)
    G.add_edge(0, 0, weight=100)
    assert edges_equal(
        nx.selfloop_edges(G, data="weight", keys=True), [(0, 0, 0, 10), (0, 0, 1, 100)]
    )


@pytest.mark.parametrize("graph_type", [nx.Graph, nx.DiGraph])
def test_selfloops_removal(graph_type):
    G = nx.complete_graph(3, create_using=graph_type)
    G.add_edge(0, 0)
    G.remove_edges_from(nx.selfloop_edges(G, keys=True))
    G.add_edge(0, 0)
    G.remove_edges_from(nx.selfloop_edges(G, data=True))
    G.add_edge(0, 0)
    G.remove_edges_from(nx.selfloop_edges(G, keys=True, data=True))


@pytest.mark.parametrize("graph_type", [nx.MultiGraph, nx.MultiDiGraph])
def test_selfloops_removal_multi(graph_type):
    """test removing selfloops behavior vis-a-vis altering a dict while iterating.
    cf. gh-4068"""
    G = nx.complete_graph(3, create_using=graph_type)
    # Defaults - see gh-4080
    G.add_edge(0, 0)
    G.add_edge(0, 0)
    G.remove_edges_from(nx.selfloop_edges(G))
    assert (0, 0) not in G.edges()
    # With keys
    G.add_edge(0, 0)
    G.add_edge(0, 0)
    with pytest.raises(RuntimeError):
        G.remove_edges_from(nx.selfloop_edges(G, keys=True))
    # With data
    G.add_edge(0, 0)
    G.add_edge(0, 0)
    with pytest.raises(TypeError):
        G.remove_edges_from(nx.selfloop_edges(G, data=True))
    # With keys and data
    G.add_edge(0, 0)
    G.add_edge(0, 0)
    with pytest.raises(RuntimeError):
        G.remove_edges_from(nx.selfloop_edges(G, data=True, keys=True))


def test_pathweight():
    valid_path = [1, 2, 3]
    invalid_path = [1, 3, 2]
    graphs = [nx.Graph(), nx.DiGraph(), nx.MultiGraph(), nx.MultiDiGraph()]
    edges = [
        (1, 2, {"cost": 5, "dist": 6}),
        (2, 3, {"cost": 3, "dist": 4}),
        (1, 2, {"cost": 1, "dist": 2}),
    ]
    for graph in graphs:
        graph.add_edges_from(edges)
        assert nx.path_weight(graph, valid_path, "cost") == 4
        assert nx.path_weight(graph, valid_path, "dist") == 6
        pytest.raises(nx.NetworkXNoPath, nx.path_weight, graph, invalid_path, "cost")


@pytest.mark.parametrize(
    "G", (nx.Graph(), nx.DiGraph(), nx.MultiGraph(), nx.MultiDiGraph())
)
def test_ispath(G):
    G.add_edges_from([(1, 2), (2, 3), (1, 2), (3, 4)])
    valid_path = [1, 2, 3, 4]
    invalid_path = [1, 2, 4, 3]  # wrong node order
    another_invalid_path = [1, 2, 3, 4, 5]  # contains node not in G
    assert nx.is_path(G, valid_path)
    assert not nx.is_path(G, invalid_path)
    assert not nx.is_path(G, another_invalid_path)


@pytest.mark.parametrize("G", (nx.Graph(), nx.DiGraph()))
def test_restricted_view(G):
    G.add_edges_from([(0, 1), (0, 2), (0, 3), (1, 0), (1, 1), (1, 2)])
    G.add_node(4)
    H = nx.restricted_view(G, [0, 2, 5], [(1, 2), (3, 4)])
    assert set(H.nodes()) == {1, 3, 4}
    assert set(H.edges()) == {(1, 1)}


@pytest.mark.parametrize("G", (nx.MultiGraph(), nx.MultiDiGraph()))
def test_restricted_view_multi(G):
    G.add_edges_from(
        [(0, 1, 0), (0, 2, 0), (0, 3, 0), (0, 1, 1), (1, 0, 0), (1, 1, 0), (1, 2, 0)]
    )
    G.add_node(4)
    H = nx.restricted_view(G, [0, 2, 5], [(1, 2, 0), (3, 4, 0)])
    assert set(H.nodes()) == {1, 3, 4}
    assert set(H.edges()) == {(1, 1)}
