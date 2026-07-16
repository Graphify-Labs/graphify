import pickle

import pytest

import networkx as nx


class TestAtlasView:
    # node->data
    def setup_method(self):
        self.d = {0: {"color": "blue", "weight": 1.2}, 1: {}, 2: {"color": 1}}
        self.av = nx.classes.coreviews.AtlasView(self.d)

    def test_pickle(self):
        view = self.av
        pview = pickle.loads(pickle.dumps(view, -1))
        assert view == pview
        assert view.__slots__ == pview.__slots__
        pview = pickle.loads(pickle.dumps(view))
        assert view == pview
        assert view.__slots__ == pview.__slots__

    def test_len(self):
        assert len(self.av) == len(self.d)

    def test_iter(self):
        assert list(self.av) == list(self.d)

    def test_getitem(self):
        assert self.av[1] is self.d[1]
        assert self.av[2]["color"] == 1
        pytest.raises(KeyError, self.av.__getitem__, 3)

    def test_copy(self):
        avcopy = self.av.copy()
        assert avcopy[0] == self.av[0]
        assert avcopy == self.av
        assert avcopy[0] is not self.av[0]
        assert avcopy is not self.av
        avcopy[5] = {}
        assert avcopy != self.av

        avcopy[0]["ht"] = 4
        assert avcopy[0] != self.av[0]
        self.av[0]["ht"] = 4
        assert avcopy[0] == self.av[0]
        del self.av[0]["ht"]

        assert not hasattr(self.av, "__setitem__")

    def test_items(self):
        assert sorted(self.av.items()) == sorted(self.d.items())

    def test_str(self):
        out = str(self.d)
        assert str(self.av) == out

    def test_repr(self):
        out = "AtlasView(" + str(self.d) + ")"
        assert repr(self.av) == out


class TestAdjacencyView:
    # node->nbr->data
    def setup_method(self):
        dd = {"color": "blue", "weight": 1.2}
        self.nd = {0: dd, 1: {}, 2: {"color": 1}}
        self.adj = {3: self.nd, 0: {3: dd}, 1: {}, 2: {3: {"color": 1}}}
        self.adjview = nx.classes.coreviews.AdjacencyView(self.adj)

    def test_pickle(self):
        view = self.adjview
        pview = pickle.loads(pickle.dumps(view, -1))
        assert view == pview
        assert view.__slots__ == pview.__slots__

    def test_len(self):
        assert len(self.adjview) == len(self.adj)

    def test_iter(self):
        assert list(self.adjview) == list(self.adj)

    def test_getitem(self):
        assert self.adjview[1] is not self.adj[1]
        assert self.adjview[3][0] is self.adjview[0][3]
        assert self.adjview[2][3]["color"] == 1
        pytest.raises(KeyError, self.adjview.__getitem__, 4)

    def test_copy(self):
        avcopy = self.adjview.copy()
        assert avcopy[0] == self.adjview[0]
        assert avcopy[0] is not self.adjview[0]

        avcopy[2][3]["ht"] = 4
        assert avcopy[2] != self.adjview[2]
        self.adjview[2][3]["ht"] = 4
        assert avcopy[2] == self.adjview[2]
        del self.adjview[2][3]["ht"]

        assert not hasattr(self.adjview, "__setitem__")

    def test_items(self):
        view_items = sorted((n, dict(d)) for n, d in self.adjview.items())
        assert view_items == sorted(self.adj.items())

    def test_str(self):
        out = str(dict(self.adj))
        assert str(self.adjview) == out

    def test_repr(self):
        out = self.adjview.__class__.__name__ + "(" + str(self.adj) + ")"
        assert repr(self.adjview) == out


class TestMultiAdjacencyView(TestAdjacencyView):
    # node->nbr->key->data
    def setup_method(self):
        dd = {"color": "blue", "weight": 1.2}
        self.kd = {0: dd, 1: {}, 2: {"color": 1}}
        self.nd = {3: self.kd, 0: {3: dd}, 1: {0: {}}, 2: {3: {"color": 1}}}
        self.adj = {3: self.nd, 0: {3: {3: dd}}, 1: {}, 2: {3: {8: {}}}}
        self.adjview = nx.classes.coreviews.MultiAdjacencyView(self.adj)

    def test_getitem(self):
        assert self.adjview[1] is not self.adj[1]
        assert self.adjview[3][0][3] is self.adjview[0][3][3]
        assert self.adjview[3][2][3]["color"] == 1
        pytest.raises(KeyError, self.adjview.__getitem__, 4)

    def test_copy(self):
        avcopy = self.adjview.copy()
        assert avcopy[0] == self.adjview[0]
        assert avcopy[0] is not self.adjview[0]

        avcopy[2][3][8]["ht"] = 4
        assert avcopy[2] != self.adjview[2]
        self.adjview[2][3][8]["ht"] = 4
        assert avcopy[2] == self.adjview[2]
        del self.adjview[2][3][8]["ht"]

        assert not hasattr(self.adjview, "__setitem__")


class TestUnionAtlas:
    # node->data
    def setup_method(self):
        self.s = {0: {"color": "blue", "weight": 1.2}, 1: {}, 2: {"color": 1}}
        self.p = {3: {"color": "blue", "weight": 1.2}, 4: {}, 2: {"watch": 2}}
        self.av = nx.classes.coreviews.UnionAtlas(self.s, self.p)

    def test_pickle(self):
        view = self.av
        pview = pickle.loads(pickle.dumps(view, -1))
        assert view == pview
        assert view.__slots__ == pview.__slots__

    def test_len(self):
        assert len(self.av) == len(self.s.keys() | self.p.keys()) == 5

    def test_iter(self):
        assert set(self.av) == set(self.s) | set(self.p)

    def test_getitem(self):
        assert self.av[0] is self.s[0]
        assert self.av[4] is self.p[4]
        assert self.av[2]["color"] == 1
        pytest.raises(KeyError, self.av[2].__getitem__, "watch")
        pytest.raises(KeyError, self.av.__getitem__, 8)

    def test_copy(self):
        avcopy = self.av.copy()
        assert avcopy[0] == self.av[0]
        assert avcopy[0] is not self.av[0]
        assert avcopy is not self.av
        avcopy[5] = {}
        assert avcopy != self.av

        avcopy[0]["ht"] = 4
        assert avcopy[0] != self.av[0]
        self.av[0]["ht"] = 4
        assert avcopy[0] == self.av[0]
        del self.av[0]["ht"]

        assert not hasattr(self.av, "__setitem__")

    def test_items(self):
        expected = dict(self.p.items())
        expected.update(self.s)
        assert sorted(self.av.items()) == sorted(expected.items())

    def test_str(self):
        out = str(dict(self.av))
        assert str(self.av) == out

    def test_repr(self):
        out = f"{self.av.__class__.__name__}({self.s}, {self.p})"
        assert repr(self.av) == out


class TestUnionAdjacency:
    # node->nbr->data
    def setup_method(self):
        dd = {"color": "blue", "weight": 1.2}
        self.nd = {0: dd, 1: {}, 2: {"color": 1}}
        self.s = {3: self.nd, 0: {}, 1: {}, 2: {3: {"color": 1}}}
        self.p = {3: {}, 0: {3: dd}, 1: {0: {}}, 2: {1: {"color": 1}}}
        self.adjview = nx.classes.coreviews.UnionAdjacency(self.s, self.p)

    def test_pickle(self):
        view = self.adjview
        pview = pickle.loads(pickle.dumps(view, -1))
        assert view == pview
        assert view.__slots__ == pview.__slots__

    def test_len(self):
        assert len(self.adjview) == len(self.s)

    def test_iter(self):
        assert sorted(self.adjview) == sorted(self.s)

    def test_getitem(self):
        assert self.adjview[1] is not self.s[1]
        assert self.adjview[3][0] is self.adjview[0][3]
        assert self.adjview[2][3]["color"] == 1
        pytest.raises(KeyError, self.adjview.__getitem__, 4)

    def test_copy(self):
        avcopy = self.adjview.copy()
        assert avcopy[0] == self.adjview[0]
        assert avcopy[0] is not self.adjview[0]

        avcopy[2][3]["ht"] = 4
        assert avcopy[2] != self.adjview[2]
        self.adjview[2][3]["ht"] = 4
        assert avcopy[2] == self.adjview[2]
        del self.adjview[2][3]["ht"]

        assert not hasattr(self.adjview, "__setitem__")

    def test_str(self):
        out = str(dict(self.adjview))
        assert str(self.adjview) == out

    def test_repr(self):
        clsname = self.adjview.__class__.__name__
        out = f"{clsname}({self.s}, {self.p})"
        assert repr(self.adjview) == out


class TestUnionMultiInner(TestUnionAdjacency):
    # nbr->key->data
    def setup_method(self):
        dd = {"color": "blue", "weight": 1.2}
        self.kd = {7: {}, "ekey": {}, 9: {"color": 1}}
        self.s = {3: self.kd, 0: {7: dd}, 1: {}, 2: {"key": {"color": 1}}}
        self.p = {3: {}, 0: {3: dd}, 1: {}, 2: {1: {"span": 2}}}
        self.adjview = nx.classes.coreviews.UnionMultiInner(self.s, self.p)

    def test_len(self):
        assert len(self.adjview) == len(self.s.keys() | self.p.keys()) == 4

    def test_getitem(self):
        assert self.adjview[1] is not self.s[1]
        assert self.adjview[0][7] is self.adjview[0][3]
        assert self.adjview[2]["key"]["color"] == 1
        assert self.adjview[2][1]["span"] == 2
        pytest.raises(KeyError, self.adjview.__getitem__, 4)
        pytest.raises(KeyError, self.adjview[1].__getitem__, "key")

    def test_copy(self):
        avcopy = self.adjview.copy()
        assert avcopy[0] == self.adjview[0]
        assert avcopy[0] is not self.adjview[0]

        avcopy[2][1]["width"] = 8
        assert avcopy[2] != self.adjview[2]
        self.adjview[2][1]["width"] = 8
        assert avcopy[2] == self.adjview[2]
        del self.adjview[2][1]["width"]

        assert not hasattr(self.adjview, "__setitem__")
        assert hasattr(avcopy, "__setitem__")


class TestUnionMultiAdjacency(TestUnionAdjacency):
    # node->nbr->key->data
    def setup_method(self):
        dd = {"color": "blue", "weight": 1.2}
        self.kd = {7: {}, 8: {}, 9: {"color": 1}}
        self.nd = {3: self.kd, 0: {9: dd}, 1: {8: {}}, 2: {9: {"color": 1}}}
        self.s = {3: self.nd, 0: {3: {7: dd}}, 1: {}, 2: {3: {8: {}}}}
        self.p = {3: {}, 0: {3: {9: dd}}, 1: {}, 2: {1: {8: {}}}}
        self.adjview = nx.classes.coreviews.UnionMultiAdjacency(self.s, self.p)

    def test_getitem(self):
        assert self.adjview[1] is not self.s[1]
        assert self.adjview[3][0][9] is self.adjview[0][3][9]
        assert self.adjview[3][2][9]["color"] == 1
        pytest.raises(KeyError, self.adjview.__getitem__, 4)

    def test_copy(self):
        avcopy = self.adjview.copy()
        assert avcopy[0] == self.adjview[0]
        assert avcopy[0] is not self.adjview[0]

        avcopy[2][3][8]["ht"] = 4
        assert avcopy[2] != self.adjview[2]
        self.adjview[2][3][8]["ht"] = 4
        assert avcopy[2] == self.adjview[2]
        del self.adjview[2][3][8]["ht"]

        assert not hasattr(self.adjview, "__setitem__")
        assert hasattr(avcopy, "__setitem__")


class TestFilteredGraphs:
    def setup_method(self):
        self.Graphs = [nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph]

    def test_hide_show_nodes(self):
        SubGraph = nx.subgraph_view
        for Graph in self.Graphs:
            G = nx.path_graph(4, Graph)
            SG = G.subgraph([2, 3])
            RG = SubGraph(G, filter_node=nx.filters.hide_nodes([0, 1]))
            assert SG.nodes == RG.nodes
            assert SG.edges == RG.edges
            SGC = SG.copy()
            RGC = RG.copy()
            assert SGC.nodes == RGC.nodes
            assert SGC.edges == RGC.edges

    def test_str_repr(self):
        SubGraph = nx.subgraph_view
        for Graph in self.Graphs:
            G = nx.path_graph(4, Graph)
            SG = G.subgraph([2, 3])
            RG = SubGraph(G, filter_node=nx.filters.hide_nodes([0, 1]))
            str(SG.adj)
            str(RG.adj)
            repr(SG.adj)
            repr(RG.adj)
            str(SG.adj[2])
            str(RG.adj[2])
            repr(SG.adj[2])
            repr(RG.adj[2])

    def test_copy(self):
        SubGraph = nx.subgraph_view
        for Graph in self.Graphs:
            G = nx.path_graph(4, Graph)
            SG = G.subgraph([2, 3])
            RG = SubGraph(G, filter_node=nx.filters.hide_nodes([0, 1]))
            RsG = SubGraph(G, filter_node=nx.filters.show_nodes([2, 3]))
            assert G.adj.copy() == G.adj
            assert G.adj[2].copy() == G.adj[2]
            assert SG.adj.copy() == SG.adj
            assert SG.adj[2].copy() == SG.adj[2]
            assert RG.adj.copy() == RG.adj
            assert RG.adj[2].copy() == RG.adj[2]
            assert RsG.adj.copy() == RsG.adj
            assert RsG.adj[2].copy() == RsG.adj[2]
