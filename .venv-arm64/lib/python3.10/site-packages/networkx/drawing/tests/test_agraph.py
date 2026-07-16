"""Unit tests for PyGraphviz interface."""

import warnings

import pytest

pygraphviz = pytest.importorskip("pygraphviz")


import networkx as nx
from networkx.utils import edges_equal, graphs_equal, nodes_equal


class TestAGraph:
    def build_graph(self, G):
        edges = [("A", "B"), ("A", "C"), ("A", "C"), ("B", "C"), ("A", "D")]
        G.add_edges_from(edges)
        G.add_node("E")
        G.graph["metal"] = "bronze"
        return G

    def assert_equal(self, G1, G2):
        assert nodes_equal(G1.nodes(), G2.nodes())
        assert edges_equal(G1.edges(), G2.edges())
        assert G1.graph["metal"] == G2.graph["metal"]

    @pytest.mark.parametrize(
        "G", (nx.Graph(), nx.DiGraph(), nx.MultiGraph(), nx.MultiDiGraph())
    )
    def test_agraph_roundtripping(self, G, tmp_path):
        G = self.build_graph(G)
        A = nx.nx_agraph.to_agraph(G)
        H = nx.nx_agraph.from_agraph(A)
        self.assert_equal(G, H)

        fname = tmp_path / "test.dot"
        nx.drawing.nx_agraph.write_dot(H, fname)
        Hin = nx.nx_agraph.read_dot(fname)
        self.assert_equal(H, Hin)

        fname = tmp_path / "fh_test.dot"
        with open(fname, "w") as fh:
            nx.drawing.nx_agraph.write_dot(H, fh)

        with open(fname) as fh:
            Hin = nx.nx_agraph.read_dot(fh)
        self.assert_equal(H, Hin)

    def test_from_agraph_name(self):
        G = nx.Graph(name="test")
        A = nx.nx_agraph.to_agraph(G)
        H = nx.nx_agraph.from_agraph(A)
        assert G.name == "test"

    @pytest.mark.parametrize(
        "graph_class", (nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph)
    )
    def test_from_agraph_create_using(self, graph_class):
        G = nx.path_graph(3)
        A = nx.nx_agraph.to_agraph(G)
        H = nx.nx_agraph.from_agraph(A, create_using=graph_class)
        assert isinstance(H, graph_class)

    def test_from_agraph_named_edges(self):
        # Create an AGraph from an existing (non-multi) Graph
        G = nx.Graph()
        G.add_nodes_from([0, 1])
        A = nx.nx_agraph.to_agraph(G)
        # Add edge (+ name, given by key) to the AGraph
        A.add_edge(0, 1, key="foo")
        # Verify a.name roundtrips out to 'key' in from_agraph
        H = nx.nx_agraph.from_agraph(A)
        assert isinstance(H, nx.Graph)
        assert ("0", "1", {"key": "foo"}) in H.edges(data=True)

    def test_to_agraph_with_nodedata(self):
        G = nx.Graph()
        G.add_node(1, color="red")
        A = nx.nx_agraph.to_agraph(G)
        assert dict(A.nodes()[0].attr) == {"color": "red"}

    @pytest.mark.parametrize("graph_class", (nx.Graph, nx.MultiGraph))
    def test_to_agraph_with_edgedata(self, graph_class):
        G = graph_class()
        G.add_nodes_from([0, 1])
        G.add_edge(0, 1, color="yellow")
        A = nx.nx_agraph.to_agraph(G)
        assert dict(A.edges()[0].attr) == {"color": "yellow"}

    def test_view_pygraphviz_path(self, tmp_path):
        G = nx.complete_graph(3)
        input_path = str(tmp_path / "graph.png")
        out_path, A = nx.nx_agraph.view_pygraphviz(G, path=input_path, show=False)
        assert out_path == input_path
        # Ensure file is not empty
        with open(input_path, "rb") as fh:
            data = fh.read()
        assert len(data) > 0

    def test_view_pygraphviz_file_suffix(self, tmp_path):
        G = nx.complete_graph(3)
        path, A = nx.nx_agraph.view_pygraphviz(G, suffix=1, show=False)
        assert path[-6:] == "_1.png"

    def test_view_pygraphviz(self):
        G = nx.Graph()  # "An empty graph cannot be drawn."
        pytest.raises(nx.NetworkXException, nx.nx_agraph.view_pygraphviz, G)
        G = nx.barbell_graph(4, 6)
        nx.nx_agraph.view_pygraphviz(G, show=False)

    def test_view_pygraphviz_edgelabel(self):
        G = nx.Graph()
        G.add_edge(1, 2, weight=7)
        G.add_edge(2, 3, weight=8)
        path, A = nx.nx_agraph.view_pygraphviz(G, edgelabel="weight", show=False)
        for edge in A.edges():
            assert edge.attr["weight"] in ("7", "8")

    def test_view_pygraphviz_callable_edgelabel(self):
        G = nx.complete_graph(3)

        def foo_label(data):
            return "foo"

        path, A = nx.nx_agraph.view_pygraphviz(G, edgelabel=foo_label, show=False)
        for edge in A.edges():
            assert edge.attr["label"] == "foo"

    def test_view_pygraphviz_multigraph_edgelabels(self):
        G = nx.MultiGraph()
        G.add_edge(0, 1, key=0, name="left_fork")
        G.add_edge(0, 1, key=1, name="right_fork")
        path, A = nx.nx_agraph.view_pygraphviz(G, edgelabel="name", show=False)
        edges = A.edges()
        assert len(edges) == 2
        for edge in edges:
            assert edge.attr["label"].strip() in ("left_fork", "right_fork")

    def test_graph_with_reserved_keywords(self):
        # test attribute/keyword clash case for #1582
        # node: n
        # edges: u,v
        G = nx.Graph()
        G = self.build_graph(G)
        G.nodes["E"]["n"] = "keyword"
        G.edges[("A", "B")]["u"] = "keyword"
        G.edges[("A", "B")]["v"] = "keyword"
        A = nx.nx_agraph.to_agraph(G)

    def test_view_pygraphviz_no_added_attrs_to_input(self):
        G = nx.complete_graph(2)
        path, A = nx.nx_agraph.view_pygraphviz(G, show=False)
        assert G.graph == {}

    @pytest.mark.xfail(reason="known bug in clean_attrs")
    def test_view_pygraphviz_leaves_input_graph_unmodified(self):
        G = nx.complete_graph(2)
        # Add entries to graph dict that to_agraph handles specially
        G.graph["node"] = {"width": "0.80"}
        G.graph["edge"] = {"fontsize": "14"}
        path, A = nx.nx_agraph.view_pygraphviz(G, show=False)
        assert G.graph == {"node": {"width": "0.80"}, "edge": {"fontsize": "14"}}

    def test_graph_with_AGraph_attrs(self):
        G = nx.complete_graph(2)
        # Add entries to graph dict that to_agraph handles specially
        G.graph["node"] = {"width": "0.80"}
        G.graph["edge"] = {"fontsize": "14"}
        path, A = nx.nx_agraph.view_pygraphviz(G, show=False)
        # Ensure user-specified values are not lost
        assert dict(A.node_attr)["width"] == "0.80"
        assert dict(A.edge_attr)["fontsize"] == "14"

    def test_round_trip_empty_graph(self):
        G = nx.Graph()
        A = nx.nx_agraph.to_agraph(G)
        H = nx.nx_agraph.from_agraph(A)
        # assert graphs_equal(G, H)
        AA = nx.nx_agraph.to_agraph(H)
        HH = nx.nx_agraph.from_agraph(AA)
        assert graphs_equal(H, HH)
        G.graph["graph"] = {}
        G.graph["node"] = {}
        G.graph["edge"] = {}
        assert graphs_equal(G, HH)

    @pytest.mark.xfail(reason="integer->string node conversion in round trip")
    def test_round_trip_integer_nodes(self):
        G = nx.complete_graph(3)
        A = nx.nx_agraph.to_agraph(G)
        H = nx.nx_agraph.from_agraph(A)
        assert graphs_equal(G, H)

    def test_graphviz_alias(self):
        G = self.build_graph(nx.Graph())
        pos_graphviz = nx.nx_agraph.graphviz_layout(G)
        pos_pygraphviz = nx.nx_agraph.pygraphviz_layout(G)
        assert pos_graphviz == pos_pygraphviz

    @pytest.mark.parametrize("root", range(5))
    def test_pygraphviz_layout_root(self, root):
        # NOTE: test depends on layout prog being deterministic
        G = nx.complete_graph(5)
        A = nx.nx_agraph.to_agraph(G)
        # Get layout with root arg is not None
        pygv_layout = nx.nx_agraph.pygraphviz_layout(G, prog="circo", root=root)
        # Equivalent layout directly on AGraph
        A.layout(args=f"-Groot={root}", prog="circo")
        # Parse AGraph layout
        a1_pos = tuple(float(v) for v in dict(A.get_node("1").attr)["pos"].split(","))
        assert pygv_layout[1] == a1_pos

    def test_2d_layout(self):
        G = nx.Graph()
        G = self.build_graph(G)
        G.graph["dimen"] = 2
        pos = nx.nx_agraph.pygraphviz_layout(G, prog="neato")
        pos = list(pos.values())
        assert len(pos) == 5
        assert len(pos[0]) == 2

    def test_3d_layout(self):
        G = nx.Graph()
        G = self.build_graph(G)
        G.graph["dimen"] = 3
        pos = nx.nx_agraph.pygraphviz_layout(G, prog="neato")
        pos = list(pos.values())
        assert len(pos) == 5
        assert len(pos[0]) == 3

    def test_no_warnings_raised(self):
        # Test that no warnings are raised when Networkx graph
        # is converted to Pygraphviz graph and 'pos'
        # attribute is given
        G = nx.Graph()
        G.add_node(0, pos=(0, 0))
        G.add_node(1, pos=(1, 1))
        A = nx.nx_agraph.to_agraph(G)
        with warnings.catch_warnings(record=True) as record:
            A.layout()
        assert len(record) == 0
