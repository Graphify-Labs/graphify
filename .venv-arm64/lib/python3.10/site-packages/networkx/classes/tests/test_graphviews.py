import pytest

import networkx as nx
from networkx.utils import edges_equal, nodes_equal

# Note: SubGraph views are not tested here. They have their own testing file


class TestReverseView:
    def setup_method(self):
        self.G = nx.path_graph(9, create_using=nx.DiGraph())
        self.rv = nx.reverse_view(self.G)

    def test_pickle(self):
        import pickle

        rv = self.rv
        prv = pickle.loads(pickle.dumps(rv, -1))
        assert rv._node == prv._node
        assert rv._adj == prv._adj
        assert rv.graph == prv.graph

    def test_contains(self):
        assert (2, 3) in self.G.edges
        assert (3, 2) not in self.G.edges
        assert (2, 3) not in self.rv.edges
        assert (3, 2) in self.rv.edges

    def test_iter(self):
        expected = sorted(tuple(reversed(e)) for e in self.G.edges)
        assert sorted(self.rv.edges) == expected

    def test_exceptions(self):
        G = nx.Graph()
        pytest.raises(nx.NetworkXNotImplemented, nx.reverse_view, G)

    def test_subclass(self):
        class MyGraph(nx.DiGraph):
            def my_method(self):
                return "me"

            def to_directed_class(self):
                return MyGraph()

        M = MyGraph()
        M.add_edge(1, 2)
        RM = nx.reverse_view(M)
        print("RM class", RM.__class__)
        RMC = RM.copy()
        print("RMC class", RMC.__class__)
        print(RMC.edges)
        assert RMC.has_edge(2, 1)
        assert RMC.my_method() == "me"


class TestMultiReverseView:
    def setup_method(self):
        self.G = nx.path_graph(9, create_using=nx.MultiDiGraph())
        self.G.add_edge(4, 5)
        self.rv = nx.reverse_view(self.G)

    def test_pickle(self):
        import pickle

        rv = self.rv
        prv = pickle.loads(pickle.dumps(rv, -1))
        assert rv._node == prv._node
        assert rv._adj == prv._adj
        assert rv.graph == prv.graph

    def test_contains(self):
        assert (2, 3, 0) in self.G.edges
        assert (3, 2, 0) not in self.G.edges
        assert (2, 3, 0) not in self.rv.edges
        assert (3, 2, 0) in self.rv.edges
        assert (5, 4, 1) in self.rv.edges
        assert (4, 5, 1) not in self.rv.edges

    def test_iter(self):
        expected = sorted((v, u, k) for u, v, k in self.G.edges)
        assert sorted(self.rv.edges) == expected

    def test_exceptions(self):
        MG = nx.MultiGraph(self.G)
        pytest.raises(nx.NetworkXNotImplemented, nx.reverse_view, MG)


def test_generic_multitype():
    nxg = nx.graphviews
    G = nx.DiGraph([(1, 2)])
    with pytest.raises(nx.NetworkXError):
        nxg.generic_graph_view(G, create_using=nx.MultiGraph)
    G = nx.MultiDiGraph([(1, 2)])
    with pytest.raises(nx.NetworkXError):
        nxg.generic_graph_view(G, create_using=nx.DiGraph)


class TestToDirected:
    def setup_method(self):
        self.G = nx.path_graph(9)
        self.dv = nx.to_directed(self.G)
        self.MG = nx.path_graph(9, create_using=nx.MultiGraph())
        self.Mdv = nx.to_directed(self.MG)

    def test_directed(self):
        assert not self.G.is_directed()
        assert self.dv.is_directed()

    def test_already_directed(self):
        dd = nx.to_directed(self.dv)
        Mdd = nx.to_directed(self.Mdv)
        assert edges_equal(dd.edges, self.dv.edges)
        assert edges_equal(Mdd.edges, self.Mdv.edges)

    def test_pickle(self):
        import pickle

        dv = self.dv
        pdv = pickle.loads(pickle.dumps(dv, -1))
        assert dv._node == pdv._node
        assert dv._succ == pdv._succ
        assert dv._pred == pdv._pred
        assert dv.graph == pdv.graph

    def test_contains(self):
        assert (2, 3) in self.G.edges
        assert (3, 2) in self.G.edges
        assert (2, 3) in self.dv.edges
        assert (3, 2) in self.dv.edges

    def test_iter(self):
        revd = [tuple(reversed(e)) for e in self.G.edges]
        expected = sorted(list(self.G.edges) + revd)
        assert sorted(self.dv.edges) == expected


class TestToUndirected:
    def setup_method(self):
        self.DG = nx.path_graph(9, create_using=nx.DiGraph())
        self.uv = nx.to_undirected(self.DG)
        self.MDG = nx.path_graph(9, create_using=nx.MultiDiGraph())
        self.Muv = nx.to_undirected(self.MDG)

    def test_directed(self):
        assert self.DG.is_directed()
        assert not self.uv.is_directed()

    def test_already_directed(self):
        uu = nx.to_undirected(self.uv)
        Muu = nx.to_undirected(self.Muv)
        assert edges_equal(uu.edges, self.uv.edges)
        assert edges_equal(Muu.edges, self.Muv.edges)

    def test_pickle(self):
        import pickle

        uv = self.uv
        puv = pickle.loads(pickle.dumps(uv, -1))
        assert uv._node == puv._node
        assert uv._adj == puv._adj
        assert uv.graph == puv.graph
        assert hasattr(uv, "_graph")

    def test_contains(self):
        assert (2, 3) in self.DG.edges
        assert (3, 2) not in self.DG.edges
        assert (2, 3) in self.uv.edges
        assert (3, 2) in self.uv.edges

    def test_iter(self):
        expected = sorted(self.DG.edges)
        assert sorted(self.uv.edges) == expected


class TestChainsOfViews:
    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(9)
        cls.DG = nx.path_graph(9, create_using=nx.DiGraph())
        cls.MG = nx.path_graph(9, create_using=nx.MultiGraph())
        cls.MDG = nx.path_graph(9, create_using=nx.MultiDiGraph())
        cls.Gv = nx.to_undirected(cls.DG)
        cls.DGv = nx.to_directed(cls.G)
        cls.MGv = nx.to_undirected(cls.MDG)
        cls.MDGv = nx.to_directed(cls.MG)
        cls.Rv = cls.DG.reverse()
        cls.MRv = cls.MDG.reverse()
        cls.graphs = [
            cls.G,
            cls.DG,
            cls.MG,
            cls.MDG,
            cls.Gv,
            cls.DGv,
            cls.MGv,
            cls.MDGv,
            cls.Rv,
            cls.MRv,
        ]
        for G in cls.graphs:
            G.edges, G.nodes, G.degree

    def test_pickle(self):
        import pickle

        for G in self.graphs:
            H = pickle.loads(pickle.dumps(G, -1))
            assert edges_equal(H.edges, G.edges)
            assert nodes_equal(H.nodes, G.nodes)

    def test_subgraph_of_subgraph(self):
        SGv = nx.subgraph(self.G, range(3, 7))
        SDGv = nx.subgraph(self.DG, range(3, 7))
        SMGv = nx.subgraph(self.MG, range(3, 7))
        SMDGv = nx.subgraph(self.MDG, range(3, 7))
        for G in self.graphs + [SGv, SDGv, SMGv, SMDGv]:
            SG = nx.induced_subgraph(G, [4, 5, 6])
            assert list(SG) == [4, 5, 6]
            SSG = SG.subgraph([6, 7])
            assert list(SSG) == [6]
            # subgraph-subgraph chain is short-cut in base class method
            assert SSG._graph is G

    def test_restricted_induced_subgraph_chains(self):
        """Test subgraph chains that both restrict and show nodes/edges.

        A restricted_view subgraph should allow induced subgraphs using
        G.subgraph that automagically without a chain (meaning the result
        is a subgraph view of the original graph not a subgraph-of-subgraph.
        """
        hide_nodes = [3, 4, 5]
        hide_edges = [(6, 7)]
        RG = nx.restricted_view(self.G, hide_nodes, hide_edges)
        nodes = [4, 5, 6, 7, 8]
        SG = nx.induced_subgraph(RG, nodes)
        SSG = RG.subgraph(nodes)
        assert RG._graph is self.G
        assert SSG._graph is self.G
        assert SG._graph is RG
        assert edges_equal(SG.edges, SSG.edges)
        # should be same as morphing the graph
        CG = self.G.copy()
        CG.remove_nodes_from(hide_nodes)
        CG.remove_edges_from(hide_edges)
        assert edges_equal(CG.edges(nodes), SSG.edges)
        CG.remove_nodes_from([0, 1, 2, 3])
        assert edges_equal(CG.edges, SSG.edges)
        # switch order: subgraph first, then restricted view
        SSSG = self.G.subgraph(nodes)
        RSG = nx.restricted_view(SSSG, hide_nodes, hide_edges)
        assert RSG._graph is not self.G
        assert edges_equal(RSG.edges, CG.edges)

    def test_subgraph_copy(self):
        for origG in self.graphs:
            G = nx.Graph(origG)
            SG = G.subgraph([4, 5, 6])
            H = SG.copy()
            assert type(G) == type(H)

    def test_subgraph_todirected(self):
        SG = nx.induced_subgraph(self.G, [4, 5, 6])
        SSG = SG.to_directed()
        assert sorted(SSG) == [4, 5, 6]
        assert sorted(SSG.edges) == [(4, 5), (5, 4), (5, 6), (6, 5)]

    def test_subgraph_toundirected(self):
        SG = nx.induced_subgraph(self.G, [4, 5, 6])
        SSG = SG.to_undirected()
        assert list(SSG) == [4, 5, 6]
        assert sorted(SSG.edges) == [(4, 5), (5, 6)]

    def test_reverse_subgraph_toundirected(self):
        G = self.DG.reverse(copy=False)
        SG = G.subgraph([4, 5, 6])
        SSG = SG.to_undirected()
        assert list(SSG) == [4, 5, 6]
        assert sorted(SSG.edges) == [(4, 5), (5, 6)]

    def test_reverse_reverse_copy(self):
        G = self.DG.reverse(copy=False)
        H = G.reverse(copy=True)
        assert H.nodes == self.DG.nodes
        assert H.edges == self.DG.edges
        G = self.MDG.reverse(copy=False)
        H = G.reverse(copy=True)
        assert H.nodes == self.MDG.nodes
        assert H.edges == self.MDG.edges

    def test_subgraph_edgesubgraph_toundirected(self):
        G = self.G.copy()
        SG = G.subgraph([4, 5, 6])
        SSG = SG.edge_subgraph([(4, 5), (5, 4)])
        USSG = SSG.to_undirected()
        assert list(USSG) == [4, 5]
        assert sorted(USSG.edges) == [(4, 5)]

    def test_copy_subgraph(self):
        G = self.G.copy()
        SG = G.subgraph([4, 5, 6])
        CSG = SG.copy(as_view=True)
        DCSG = SG.copy(as_view=False)
        assert hasattr(CSG, "_graph")  # is a view
        assert not hasattr(DCSG, "_graph")  # not a view

    def test_copy_disubgraph(self):
        G = self.DG.copy()
        SG = G.subgraph([4, 5, 6])
        CSG = SG.copy(as_view=True)
        DCSG = SG.copy(as_view=False)
        assert hasattr(CSG, "_graph")  # is a view
        assert not hasattr(DCSG, "_graph")  # not a view

    def test_copy_multidisubgraph(self):
        G = self.MDG.copy()
        SG = G.subgraph([4, 5, 6])
        CSG = SG.copy(as_view=True)
        DCSG = SG.copy(as_view=False)
        assert hasattr(CSG, "_graph")  # is a view
        assert not hasattr(DCSG, "_graph")  # not a view

    def test_copy_multisubgraph(self):
        G = self.MG.copy()
        SG = G.subgraph([4, 5, 6])
        CSG = SG.copy(as_view=True)
        DCSG = SG.copy(as_view=False)
        assert hasattr(CSG, "_graph")  # is a view
        assert not hasattr(DCSG, "_graph")  # not a view

    def test_copy_of_view(self):
        G = nx.MultiGraph(self.MGv)
        assert G.__class__.__name__ == "MultiGraph"
        G = G.copy(as_view=True)
        assert G.__class__.__name__ == "MultiGraph"

    def test_subclass(self):
        class MyGraph(nx.DiGraph):
            def my_method(self):
                return "me"

            def to_directed_class(self):
                return MyGraph()

        for origG in self.graphs:
            G = MyGraph(origG)
            SG = G.subgraph([4, 5, 6])
            H = SG.copy()
            assert SG.my_method() == "me"
            assert H.my_method() == "me"
            assert 3 not in H or 3 in SG
