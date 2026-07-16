import gc
import pickle
import platform
import weakref

import pytest

import networkx as nx
from networkx.utils import edges_equal, graphs_equal, nodes_equal


class BaseGraphTester:
    """Tests for data-structure independent graph class features."""

    def test_contains(self):
        G = self.K3
        assert 1 in G
        assert 4 not in G
        assert "b" not in G
        assert [] not in G  # no exception for nonhashable
        assert {1: 1} not in G  # no exception for nonhashable

    def test_order(self):
        G = self.K3
        assert len(G) == 3
        assert G.order() == 3
        assert G.number_of_nodes() == 3

    def test_nodes(self):
        G = self.K3
        assert isinstance(G._node, G.node_dict_factory)
        assert isinstance(G._adj, G.adjlist_outer_dict_factory)
        assert all(
            isinstance(adj, G.adjlist_inner_dict_factory) for adj in G._adj.values()
        )
        assert sorted(G.nodes()) == self.k3nodes
        assert sorted(G.nodes(data=True)) == [(0, {}), (1, {}), (2, {})]

    def test_none_node(self):
        G = self.Graph()
        with pytest.raises(ValueError):
            G.add_node(None)
        with pytest.raises(ValueError):
            G.add_nodes_from([None])
        with pytest.raises(ValueError):
            G.add_edge(0, None)
        with pytest.raises(ValueError):
            G.add_edges_from([(0, None)])

    def test_has_node(self):
        G = self.K3
        assert G.has_node(1)
        assert not G.has_node(4)
        assert not G.has_node([])  # no exception for nonhashable
        assert not G.has_node({1: 1})  # no exception for nonhashable

    def test_has_edge(self):
        G = self.K3
        assert G.has_edge(0, 1)
        assert not G.has_edge(0, -1)

    def test_neighbors(self):
        G = self.K3
        assert sorted(G.neighbors(0)) == [1, 2]
        with pytest.raises(nx.NetworkXError):
            G.neighbors(-1)

    @pytest.mark.skipif(
        platform.python_implementation() == "PyPy", reason="PyPy gc is different"
    )
    def test_memory_leak(self):
        G = self.Graph()

        def count_objects_of_type(_type):
            # Iterating over all objects tracked by gc can include weak references
            # whose weakly-referenced objects may no longer exist. Calling `isinstance`
            # on such a weak reference will raise ReferenceError. There are at least
            # three workarounds for this: one is to compare type names instead of using
            # `isinstance` such as `type(obj).__name__ == typename`, another is to use
            # `type(obj) == _type`, and the last is to ignore ProxyTypes as we do below.
            # NOTE: even if this safeguard is deemed unnecessary to pass NetworkX tests,
            # we should still keep it for maximum safety for other NetworkX backends.
            return sum(
                1
                for obj in gc.get_objects()
                if not isinstance(obj, weakref.ProxyTypes) and isinstance(obj, _type)
            )

        gc.collect()
        before = count_objects_of_type(self.Graph)
        G.copy()
        gc.collect()
        after = count_objects_of_type(self.Graph)
        assert before == after

        # test a subgraph of the base class
        class MyGraph(self.Graph):
            pass

        gc.collect()
        G = MyGraph()
        before = count_objects_of_type(MyGraph)
        G.copy()
        gc.collect()
        after = count_objects_of_type(MyGraph)
        assert before == after

    def test_edges(self):
        G = self.K3
        assert isinstance(G._adj, G.adjlist_outer_dict_factory)
        assert edges_equal(G.edges(), [(0, 1), (0, 2), (1, 2)])
        assert edges_equal(G.edges(0), [(0, 1), (0, 2)])
        assert edges_equal(G.edges([0, 1]), [(0, 1), (0, 2), (1, 2)])
        with pytest.raises(nx.NetworkXError):
            G.edges(-1)

    def test_degree(self):
        G = self.K3
        assert sorted(G.degree()) == [(0, 2), (1, 2), (2, 2)]
        assert dict(G.degree()) == {0: 2, 1: 2, 2: 2}
        assert G.degree(0) == 2
        with pytest.raises(nx.NetworkXError):
            G.degree(-1)  # node not in graph

    def test_size(self):
        G = self.K3
        assert G.size() == 3
        assert G.number_of_edges() == 3

    def test_nbunch_iter(self):
        G = self.K3
        assert nodes_equal(G.nbunch_iter(), self.k3nodes)  # all nodes
        assert nodes_equal(G.nbunch_iter(0), [0])  # single node
        assert nodes_equal(G.nbunch_iter([0, 1]), [0, 1])  # sequence
        # sequence with none in graph
        assert nodes_equal(G.nbunch_iter([-1]), [])
        # string sequence with none in graph
        assert nodes_equal(G.nbunch_iter("foo"), [])
        # node not in graph doesn't get caught upon creation of iterator
        bunch = G.nbunch_iter(-1)
        # but gets caught when iterator used
        with pytest.raises(nx.NetworkXError, match="is not a node or a sequence"):
            list(bunch)
        # unhashable doesn't get caught upon creation of iterator
        bunch = G.nbunch_iter([0, 1, 2, {}])
        # but gets caught when iterator hits the unhashable
        with pytest.raises(
            nx.NetworkXError, match="in sequence nbunch is not a valid node"
        ):
            list(bunch)

    def test_nbunch_iter_node_format_raise(self):
        # Tests that a node that would have failed string formatting
        # doesn't cause an error when attempting to raise a
        # :exc:`nx.NetworkXError`.

        # For more information, see pull request #1813.
        G = self.Graph()
        nbunch = [("x", set())]
        with pytest.raises(nx.NetworkXError):
            list(G.nbunch_iter(nbunch))

    def test_selfloop_degree(self):
        G = self.Graph()
        G.add_edge(1, 1)
        assert sorted(G.degree()) == [(1, 2)]
        assert dict(G.degree()) == {1: 2}
        assert G.degree(1) == 2
        assert sorted(G.degree([1])) == [(1, 2)]
        assert G.degree(1, weight="weight") == 2

    def test_selfloops(self):
        G = self.K3.copy()
        G.add_edge(0, 0)
        assert nodes_equal(nx.nodes_with_selfloops(G), [0])
        assert edges_equal(nx.selfloop_edges(G), [(0, 0)])
        assert nx.number_of_selfloops(G) == 1
        G.remove_edge(0, 0)
        G.add_edge(0, 0)
        G.remove_edges_from([(0, 0)])
        G.add_edge(1, 1)
        G.remove_node(1)
        G.add_edge(0, 0)
        G.add_edge(1, 1)
        G.remove_nodes_from([0, 1])

    def test_cache_reset(self):
        G = self.K3.copy()
        old_adj = G.adj
        assert id(G.adj) == id(old_adj)
        G._adj = {}
        assert id(G.adj) != id(old_adj)

        old_nodes = G.nodes
        assert id(G.nodes) == id(old_nodes)
        G._node = {}
        assert id(G.nodes) != id(old_nodes)

    def test_attributes_cached(self):
        G = self.K3.copy()
        assert id(G.nodes) == id(G.nodes)
        assert id(G.edges) == id(G.edges)
        assert id(G.degree) == id(G.degree)
        assert id(G.adj) == id(G.adj)


class BaseAttrGraphTester(BaseGraphTester):
    """Tests of graph class attribute features."""

    def test_weighted_degree(self):
        G = self.Graph()
        G.add_edge(1, 2, weight=2, other=3)
        G.add_edge(2, 3, weight=3, other=4)
        assert sorted(d for n, d in G.degree(weight="weight")) == [2, 3, 5]
        assert dict(G.degree(weight="weight")) == {1: 2, 2: 5, 3: 3}
        assert G.degree(1, weight="weight") == 2
        assert nodes_equal((G.degree([1], weight="weight")), [(1, 2)])

        assert nodes_equal((d for n, d in G.degree(weight="other")), [3, 7, 4])
        assert dict(G.degree(weight="other")) == {1: 3, 2: 7, 3: 4}
        assert G.degree(1, weight="other") == 3
        assert edges_equal((G.degree([1], weight="other")), [(1, 3)])

    def add_attributes(self, G):
        G.graph["foo"] = []
        G.nodes[0]["foo"] = []
        G.remove_edge(1, 2)
        ll = []
        G.add_edge(1, 2, foo=ll)
        G.add_edge(2, 1, foo=ll)

    def test_name(self):
        G = self.Graph(name="")
        assert G.name == ""
        G = self.Graph(name="test")
        assert G.name == "test"

    def test_str_unnamed(self):
        G = self.Graph()
        G.add_edges_from([(1, 2), (2, 3)])
        assert str(G) == f"{type(G).__name__} with 3 nodes and 2 edges"

    def test_str_named(self):
        G = self.Graph(name="foo")
        G.add_edges_from([(1, 2), (2, 3)])
        assert str(G) == f"{type(G).__name__} named 'foo' with 3 nodes and 2 edges"

    def test_graph_chain(self):
        G = self.Graph([(0, 1), (1, 2)])
        DG = G.to_directed(as_view=True)
        SDG = DG.subgraph([0, 1])
        RSDG = SDG.reverse(copy=False)
        assert G is DG._graph
        assert DG is SDG._graph
        assert SDG is RSDG._graph

    def test_copy(self):
        G = self.Graph()
        G.add_node(0)
        G.add_edge(1, 2)
        self.add_attributes(G)
        # copy edge datadict but any container attr are same
        H = G.copy()
        self.graphs_equal(H, G)
        self.different_attrdict(H, G)
        self.shallow_copy_attrdict(H, G)

    def test_class_copy(self):
        G = self.Graph()
        G.add_node(0)
        G.add_edge(1, 2)
        self.add_attributes(G)
        # copy edge datadict but any container attr are same
        H = G.__class__(G)
        self.graphs_equal(H, G)
        self.different_attrdict(H, G)
        self.shallow_copy_attrdict(H, G)

    def test_fresh_copy(self):
        G = self.Graph()
        G.add_node(0)
        G.add_edge(1, 2)
        self.add_attributes(G)
        # copy graph structure but use fresh datadict
        H = G.__class__()
        H.add_nodes_from(G)
        H.add_edges_from(G.edges())
        assert len(G.nodes[0]) == 1
        ddict = G.adj[1][2][0] if G.is_multigraph() else G.adj[1][2]
        assert len(ddict) == 1
        assert len(H.nodes[0]) == 0
        ddict = H.adj[1][2][0] if H.is_multigraph() else H.adj[1][2]
        assert len(ddict) == 0

    def is_deepcopy(self, H, G):
        self.graphs_equal(H, G)
        self.different_attrdict(H, G)
        self.deep_copy_attrdict(H, G)

    def deep_copy_attrdict(self, H, G):
        self.deepcopy_graph_attr(H, G)
        self.deepcopy_node_attr(H, G)
        self.deepcopy_edge_attr(H, G)

    def deepcopy_graph_attr(self, H, G):
        assert G.graph["foo"] == H.graph["foo"]
        G.graph["foo"].append(1)
        assert G.graph["foo"] != H.graph["foo"]

    def deepcopy_node_attr(self, H, G):
        assert G.nodes[0]["foo"] == H.nodes[0]["foo"]
        G.nodes[0]["foo"].append(1)
        assert G.nodes[0]["foo"] != H.nodes[0]["foo"]

    def deepcopy_edge_attr(self, H, G):
        assert G[1][2]["foo"] == H[1][2]["foo"]
        G[1][2]["foo"].append(1)
        assert G[1][2]["foo"] != H[1][2]["foo"]

    def is_shallow_copy(self, H, G):
        self.graphs_equal(H, G)
        self.shallow_copy_attrdict(H, G)

    def shallow_copy_attrdict(self, H, G):
        self.shallow_copy_graph_attr(H, G)
        self.shallow_copy_node_attr(H, G)
        self.shallow_copy_edge_attr(H, G)

    def shallow_copy_graph_attr(self, H, G):
        assert G.graph["foo"] == H.graph["foo"]
        G.graph["foo"].append(1)
        assert G.graph["foo"] == H.graph["foo"]

    def shallow_copy_node_attr(self, H, G):
        assert G.nodes[0]["foo"] == H.nodes[0]["foo"]
        G.nodes[0]["foo"].append(1)
        assert G.nodes[0]["foo"] == H.nodes[0]["foo"]

    def shallow_copy_edge_attr(self, H, G):
        assert G[1][2]["foo"] == H[1][2]["foo"]
        G[1][2]["foo"].append(1)
        assert G[1][2]["foo"] == H[1][2]["foo"]

    def same_attrdict(self, H, G):
        old_foo = H[1][2]["foo"]
        H.adj[1][2]["foo"] = "baz"
        assert G.edges == H.edges
        H.adj[1][2]["foo"] = old_foo
        assert G.edges == H.edges

        old_foo = H.nodes[0]["foo"]
        H.nodes[0]["foo"] = "baz"
        assert G.nodes == H.nodes
        H.nodes[0]["foo"] = old_foo
        assert G.nodes == H.nodes

    def different_attrdict(self, H, G):
        old_foo = H[1][2]["foo"]
        H.adj[1][2]["foo"] = "baz"
        assert G._adj != H._adj
        H.adj[1][2]["foo"] = old_foo
        assert G._adj == H._adj

        old_foo = H.nodes[0]["foo"]
        H.nodes[0]["foo"] = "baz"
        assert G._node != H._node
        H.nodes[0]["foo"] = old_foo
        assert G._node == H._node

    def graphs_equal(self, H, G):
        assert G._adj == H._adj
        assert G._node == H._node
        assert G.graph == H.graph
        assert G.name == H.name
        if not G.is_directed() and not H.is_directed():
            assert H._adj[1][2] is H._adj[2][1]
            assert G._adj[1][2] is G._adj[2][1]
        else:  # at least one is directed
            if not G.is_directed():
                G._pred = G._adj
                G._succ = G._adj
            if not H.is_directed():
                H._pred = H._adj
                H._succ = H._adj
            assert G._pred == H._pred
            assert G._succ == H._succ
            assert H._succ[1][2] is H._pred[2][1]
            assert G._succ[1][2] is G._pred[2][1]

    def test_graph_attr(self):
        G = self.K3.copy()
        G.graph["foo"] = "bar"
        assert isinstance(G.graph, G.graph_attr_dict_factory)
        assert G.graph["foo"] == "bar"
        del G.graph["foo"]
        assert G.graph == {}
        H = self.Graph(foo="bar")
        assert H.graph["foo"] == "bar"

    def test_node_attr(self):
        G = self.K3.copy()
        G.add_node(1, foo="bar")
        assert all(
            isinstance(d, G.node_attr_dict_factory) for u, d in G.nodes(data=True)
        )
        assert nodes_equal(G.nodes(), [0, 1, 2])
        assert nodes_equal(G.nodes(data=True), [(0, {}), (1, {"foo": "bar"}), (2, {})])
        G.nodes[1]["foo"] = "baz"
        assert nodes_equal(G.nodes(data=True), [(0, {}), (1, {"foo": "baz"}), (2, {})])
        assert nodes_equal(G.nodes(data="foo"), [(0, None), (1, "baz"), (2, None)])
        assert nodes_equal(
            G.nodes(data="foo", default="bar"), [(0, "bar"), (1, "baz"), (2, "bar")]
        )

    def test_node_attr2(self):
        G = self.K3.copy()
        a = {"foo": "bar"}
        G.add_node(3, **a)
        assert nodes_equal(G.nodes(), [0, 1, 2, 3])
        assert nodes_equal(
            G.nodes(data=True), [(0, {}), (1, {}), (2, {}), (3, {"foo": "bar"})]
        )

    def test_edge_lookup(self):
        G = self.Graph()
        G.add_edge(1, 2, foo="bar")
        assert edges_equal(G.edges[1, 2], {"foo": "bar"})

    def test_edge_attr(self):
        G = self.Graph()
        G.add_edge(1, 2, foo="bar")
        assert all(
            isinstance(d, G.edge_attr_dict_factory) for u, v, d in G.edges(data=True)
        )
        assert edges_equal(G.edges(data=True), [(1, 2, {"foo": "bar"})])
        assert edges_equal(G.edges(data="foo"), [(1, 2, "bar")])

    def test_edge_attr2(self):
        G = self.Graph()
        G.add_edges_from([(1, 2), (3, 4)], foo="foo")
        assert edges_equal(
            G.edges(data=True), [(1, 2, {"foo": "foo"}), (3, 4, {"foo": "foo"})]
        )
        assert edges_equal(G.edges(data="foo"), [(1, 2, "foo"), (3, 4, "foo")])

    def test_edge_attr3(self):
        G = self.Graph()
        G.add_edges_from([(1, 2, {"weight": 32}), (3, 4, {"weight": 64})], foo="foo")
        assert edges_equal(
            G.edges(data=True),
            [
                (1, 2, {"foo": "foo", "weight": 32}),
                (3, 4, {"foo": "foo", "weight": 64}),
            ],
        )

        G.remove_edges_from([(1, 2), (3, 4)])
        G.add_edge(1, 2, data=7, spam="bar", bar="foo")
        assert edges_equal(
            G.edges(data=True), [(1, 2, {"data": 7, "spam": "bar", "bar": "foo"})]
        )

    def test_edge_attr4(self):
        G = self.Graph()
        G.add_edge(1, 2, data=7, spam="bar", bar="foo")
        assert edges_equal(
            G.edges(data=True), [(1, 2, {"data": 7, "spam": "bar", "bar": "foo"})]
        )
        G[1][2]["data"] = 10  # OK to set data like this
        assert edges_equal(
            G.edges(data=True), [(1, 2, {"data": 10, "spam": "bar", "bar": "foo"})]
        )

        G.adj[1][2]["data"] = 20
        assert edges_equal(
            G.edges(data=True), [(1, 2, {"data": 20, "spam": "bar", "bar": "foo"})]
        )
        G.edges[1, 2]["data"] = 21  # another spelling, "edge"
        assert edges_equal(
            G.edges(data=True), [(1, 2, {"data": 21, "spam": "bar", "bar": "foo"})]
        )
        G.adj[1][2]["listdata"] = [20, 200]
        G.adj[1][2]["weight"] = 20
        dd = {
            "data": 21,
            "spam": "bar",
            "bar": "foo",
            "listdata": [20, 200],
            "weight": 20,
        }
        assert edges_equal(G.edges(data=True), [(1, 2, dd)])

    def test_to_undirected(self):
        G = self.K3
        self.add_attributes(G)
        H = nx.Graph(G)
        self.is_shallow_copy(H, G)
        self.different_attrdict(H, G)
        H = G.to_undirected()
        self.is_deepcopy(H, G)

    def test_to_directed_as_view(self):
        H = nx.path_graph(2, create_using=self.Graph)
        H2 = H.to_directed(as_view=True)
        assert H is H2._graph
        assert H2.has_edge(0, 1)
        assert H2.has_edge(1, 0) or H.is_directed()
        pytest.raises(nx.NetworkXError, H2.add_node, -1)
        pytest.raises(nx.NetworkXError, H2.add_edge, 1, 2)
        H.add_edge(1, 2)
        assert H2.has_edge(1, 2)
        assert H2.has_edge(2, 1) or H.is_directed()

    def test_to_undirected_as_view(self):
        H = nx.path_graph(2, create_using=self.Graph)
        H2 = H.to_undirected(as_view=True)
        assert H is H2._graph
        assert H2.has_edge(0, 1)
        assert H2.has_edge(1, 0)
        pytest.raises(nx.NetworkXError, H2.add_node, -1)
        pytest.raises(nx.NetworkXError, H2.add_edge, 1, 2)
        H.add_edge(1, 2)
        assert H2.has_edge(1, 2)
        assert H2.has_edge(2, 1)

    def test_directed_class(self):
        G = self.Graph()

        class newGraph(G.to_undirected_class()):
            def to_directed_class(self):
                return newDiGraph

            def to_undirected_class(self):
                return newGraph

        class newDiGraph(G.to_directed_class()):
            def to_directed_class(self):
                return newDiGraph

            def to_undirected_class(self):
                return newGraph

        G = newDiGraph() if G.is_directed() else newGraph()
        H = G.to_directed()
        assert isinstance(H, newDiGraph)
        H = G.to_undirected()
        assert isinstance(H, newGraph)

    def test_to_directed(self):
        G = self.K3
        self.add_attributes(G)
        H = nx.DiGraph(G)
        self.is_shallow_copy(H, G)
        self.different_attrdict(H, G)
        H = G.to_directed()
        self.is_deepcopy(H, G)

    def test_subgraph(self):
        G = self.K3
        self.add_attributes(G)
        H = G.subgraph([0, 1, 2, 5])
        self.graphs_equal(H, G)
        self.same_attrdict(H, G)
        self.shallow_copy_attrdict(H, G)

        H = G.subgraph(0)
        assert H.adj == {0: {}}
        H = G.subgraph([])
        assert H.adj == {}
        assert G.adj != {}

    def test_selfloops_attr(self):
        G = self.K3.copy()
        G.add_edge(0, 0)
        G.add_edge(1, 1, weight=2)
        assert edges_equal(
            nx.selfloop_edges(G, data=True), [(0, 0, {}), (1, 1, {"weight": 2})]
        )
        assert edges_equal(
            nx.selfloop_edges(G, data="weight"), [(0, 0, None), (1, 1, 2)]
        )


class TestGraph(BaseAttrGraphTester):
    """Tests specific to dict-of-dict-of-dict graph data structure"""

    def setup_method(self):
        self.Graph = nx.Graph
        # build dict-of-dict-of-dict K3
        ed1, ed2, ed3 = ({}, {}, {})
        self.k3adj = {0: {1: ed1, 2: ed2}, 1: {0: ed1, 2: ed3}, 2: {0: ed2, 1: ed3}}
        self.k3edges = [(0, 1), (0, 2), (1, 2)]
        self.k3nodes = [0, 1, 2]
        self.K3 = self.Graph()
        self.K3._adj = self.k3adj
        self.K3._node = {}
        self.K3._node[0] = {}
        self.K3._node[1] = {}
        self.K3._node[2] = {}

    def test_pickle(self):
        G = self.K3
        pg = pickle.loads(pickle.dumps(G, -1))
        self.graphs_equal(pg, G)
        pg = pickle.loads(pickle.dumps(G))
        self.graphs_equal(pg, G)

    def test_data_input(self):
        G = self.Graph({1: [2], 2: [1]}, name="test")
        assert G.name == "test"
        assert sorted(G.adj.items()) == [(1, {2: {}}), (2, {1: {}})]

    def test_adjacency(self):
        G = self.K3
        assert dict(G.adjacency()) == {
            0: {1: {}, 2: {}},
            1: {0: {}, 2: {}},
            2: {0: {}, 1: {}},
        }

    def test_getitem(self):
        G = self.K3
        assert G.adj[0] == {1: {}, 2: {}}
        assert G[0] == {1: {}, 2: {}}
        with pytest.raises(KeyError):
            G.__getitem__("j")
        with pytest.raises(TypeError):
            G.__getitem__(["A"])

    def test_add_node(self):
        G = self.Graph()
        G.add_node(0)
        assert G.adj == {0: {}}
        # test add attributes
        G.add_node(1, c="red")
        G.add_node(2, c="blue")
        G.add_node(3, c="red")
        assert G.nodes[1]["c"] == "red"
        assert G.nodes[2]["c"] == "blue"
        assert G.nodes[3]["c"] == "red"
        # test updating attributes
        G.add_node(1, c="blue")
        G.add_node(2, c="red")
        G.add_node(3, c="blue")
        assert G.nodes[1]["c"] == "blue"
        assert G.nodes[2]["c"] == "red"
        assert G.nodes[3]["c"] == "blue"

    def test_add_nodes_from(self):
        G = self.Graph()
        G.add_nodes_from([0, 1, 2])
        assert G.adj == {0: {}, 1: {}, 2: {}}
        # test add attributes
        G.add_nodes_from([0, 1, 2], c="red")
        assert G.nodes[0]["c"] == "red"
        assert G.nodes[2]["c"] == "red"
        # test that attribute dicts are not the same
        assert G.nodes[0] is not G.nodes[1]
        # test updating attributes
        G.add_nodes_from([0, 1, 2], c="blue")
        assert G.nodes[0]["c"] == "blue"
        assert G.nodes[2]["c"] == "blue"
        assert G.nodes[0] is not G.nodes[1]
        # test tuple input
        H = self.Graph()
        H.add_nodes_from(G.nodes(data=True))
        assert H.nodes[0]["c"] == "blue"
        assert H.nodes[2]["c"] == "blue"
        assert H.nodes[0] is not H.nodes[1]
        # specific overrides general
        H.add_nodes_from([0, (1, {"c": "green"}), (3, {"c": "cyan"})], c="red")
        assert H.nodes[0]["c"] == "red"
        assert H.nodes[1]["c"] == "green"
        assert H.nodes[2]["c"] == "blue"
        assert H.nodes[3]["c"] == "cyan"

    def test_remove_node(self):
        G = self.K3.copy()
        G.remove_node(0)
        assert G.adj == {1: {2: {}}, 2: {1: {}}}
        with pytest.raises(nx.NetworkXError):
            G.remove_node(-1)

        # generator here to implement list,set,string...

    def test_remove_nodes_from(self):
        G = self.K3.copy()
        G.remove_nodes_from([0, 1])
        assert G.adj == {2: {}}
        G.remove_nodes_from([-1])  # silent fail

    def test_add_edge(self):
        G = self.Graph()
        G.add_edge(0, 1)
        assert G.adj == {0: {1: {}}, 1: {0: {}}}
        G = self.Graph()
        G.add_edge(*(0, 1))
        assert G.adj == {0: {1: {}}, 1: {0: {}}}
        G = self.Graph()
        with pytest.raises(ValueError):
            G.add_edge(None, "anything")

    def test_add_edges_from(self):
        G = self.Graph()
        G.add_edges_from([(0, 1), (0, 2, {"weight": 3})])
        assert G.adj == {
            0: {1: {}, 2: {"weight": 3}},
            1: {0: {}},
            2: {0: {"weight": 3}},
        }
        G = self.Graph()
        G.add_edges_from([(0, 1), (0, 2, {"weight": 3}), (1, 2, {"data": 4})], data=2)
        assert G.adj == {
            0: {1: {"data": 2}, 2: {"weight": 3, "data": 2}},
            1: {0: {"data": 2}, 2: {"data": 4}},
            2: {0: {"weight": 3, "data": 2}, 1: {"data": 4}},
        }

        with pytest.raises(nx.NetworkXError):
            G.add_edges_from([(0,)])  # too few in tuple
        with pytest.raises(nx.NetworkXError):
            G.add_edges_from([(0, 1, 2, 3)])  # too many in tuple
        with pytest.raises(TypeError):
            G.add_edges_from([0])  # not a tuple
        with pytest.raises(ValueError):
            G.add_edges_from([(None, 3), (3, 2)])  # None cannot be a node

    def test_remove_edge(self):
        G = self.K3.copy()
        G.remove_edge(0, 1)
        assert G.adj == {0: {2: {}}, 1: {2: {}}, 2: {0: {}, 1: {}}}
        with pytest.raises(nx.NetworkXError):
            G.remove_edge(-1, 0)

    def test_remove_edges_from(self):
        G = self.K3.copy()
        G.remove_edges_from([(0, 1)])
        assert G.adj == {0: {2: {}}, 1: {2: {}}, 2: {0: {}, 1: {}}}
        G.remove_edges_from([(0, 0)])  # silent fail

    def test_clear(self):
        G = self.K3.copy()
        G.graph["name"] = "K3"
        G.clear()
        assert list(G.nodes) == []
        assert G.adj == {}
        assert G.graph == {}

    def test_clear_edges(self):
        G = self.K3.copy()
        G.graph["name"] = "K3"
        nodes = list(G.nodes)
        G.clear_edges()
        assert list(G.nodes) == nodes
        assert G.adj == {0: {}, 1: {}, 2: {}}
        assert list(G.edges) == []
        assert G.graph["name"] == "K3"

    def test_edges_data(self):
        G = self.K3
        all_edges = [(0, 1, {}), (0, 2, {}), (1, 2, {})]
        assert edges_equal(G.edges(data=True), all_edges)
        assert edges_equal(G.edges(0, data=True), [(0, 1, {}), (0, 2, {})])
        assert edges_equal(G.edges([0, 1], data=True), all_edges)
        with pytest.raises(nx.NetworkXError):
            G.edges(-1, True)

    def test_get_edge_data(self):
        G = self.K3.copy()
        assert G.get_edge_data(0, 1) == {}
        assert G[0][1] == {}
        assert G.get_edge_data(10, 20) is None
        assert G.get_edge_data(-1, 0) is None
        assert G.get_edge_data(-1, 0, default=1) == 1

    def test_update(self):
        # specify both edges and nodes
        G = self.K3.copy()
        G.update(nodes=[3, (4, {"size": 2})], edges=[(4, 5), (6, 7, {"weight": 2})])
        nlist = [
            (0, {}),
            (1, {}),
            (2, {}),
            (3, {}),
            (4, {"size": 2}),
            (5, {}),
            (6, {}),
            (7, {}),
        ]
        assert sorted(G.nodes.data()) == nlist
        if G.is_directed():
            elist = [
                (0, 1, {}),
                (0, 2, {}),
                (1, 0, {}),
                (1, 2, {}),
                (2, 0, {}),
                (2, 1, {}),
                (4, 5, {}),
                (6, 7, {"weight": 2}),
            ]
        else:
            elist = [
                (0, 1, {}),
                (0, 2, {}),
                (1, 2, {}),
                (4, 5, {}),
                (6, 7, {"weight": 2}),
            ]
        assert sorted(G.edges.data()) == elist
        assert G.graph == {}

        # no keywords -- order is edges, nodes
        G = self.K3.copy()
        G.update([(4, 5), (6, 7, {"weight": 2})], [3, (4, {"size": 2})])
        assert sorted(G.nodes.data()) == nlist
        assert sorted(G.edges.data()) == elist
        assert G.graph == {}

        # update using only a graph
        G = self.Graph()
        G.graph["foo"] = "bar"
        G.add_node(2, data=4)
        G.add_edge(0, 1, weight=0.5)
        GG = G.copy()
        H = self.Graph()
        GG.update(H)
        assert graphs_equal(G, GG)
        H.update(G)
        assert graphs_equal(H, G)

        # update nodes only
        H = self.Graph()
        H.update(nodes=[3, 4])
        assert H.nodes ^ {3, 4} == set()
        assert H.size() == 0

        # update edges only
        H = self.Graph()
        H.update(edges=[(3, 4)])
        assert sorted(H.edges.data()) == [(3, 4, {})]
        assert H.size() == 1

        # No inputs -> exception
        with pytest.raises(nx.NetworkXError):
            nx.Graph().update()


class TestEdgeSubgraph:
    """Unit tests for the :meth:`Graph.edge_subgraph` method."""

    def setup_method(self):
        # Create a path graph on five nodes.
        G = nx.path_graph(5)
        # Add some node, edge, and graph attributes.
        for i in range(5):
            G.nodes[i]["name"] = f"node{i}"
        G.edges[0, 1]["name"] = "edge01"
        G.edges[3, 4]["name"] = "edge34"
        G.graph["name"] = "graph"
        # Get the subgraph induced by the first and last edges.
        self.G = G
        self.H = G.edge_subgraph([(0, 1), (3, 4)])

    def test_correct_nodes(self):
        """Tests that the subgraph has the correct nodes."""
        assert [0, 1, 3, 4] == sorted(self.H.nodes())

    def test_correct_edges(self):
        """Tests that the subgraph has the correct edges."""
        assert [(0, 1, "edge01"), (3, 4, "edge34")] == sorted(self.H.edges(data="name"))

    def test_add_node(self):
        """Tests that adding a node to the original graph does not
        affect the nodes of the subgraph.

        """
        self.G.add_node(5)
        assert [0, 1, 3, 4] == sorted(self.H.nodes())

    def test_remove_node(self):
        """Tests that removing a node in the original graph does
        affect the nodes of the subgraph.

        """
        self.G.remove_node(0)
        assert [1, 3, 4] == sorted(self.H.nodes())

    def test_node_attr_dict(self):
        """Tests that the node attribute dictionary of the two graphs is
        the same object.

        """
        for v in self.H:
            assert self.G.nodes[v] == self.H.nodes[v]
        # Making a change to G should make a change in H and vice versa.
        self.G.nodes[0]["name"] = "foo"
        assert self.G.nodes[0] == self.H.nodes[0]
        self.H.nodes[1]["name"] = "bar"
        assert self.G.nodes[1] == self.H.nodes[1]

    def test_edge_attr_dict(self):
        """Tests that the edge attribute dictionary of the two graphs is
        the same object.

        """
        for u, v in self.H.edges():
            assert self.G.edges[u, v] == self.H.edges[u, v]
        # Making a change to G should make a change in H and vice versa.
        self.G.edges[0, 1]["name"] = "foo"
        assert self.G.edges[0, 1]["name"] == self.H.edges[0, 1]["name"]
        self.H.edges[3, 4]["name"] = "bar"
        assert self.G.edges[3, 4]["name"] == self.H.edges[3, 4]["name"]

    def test_graph_attr_dict(self):
        """Tests that the graph attribute dictionary of the two graphs
        is the same object.

        """
        assert self.G.graph is self.H.graph
