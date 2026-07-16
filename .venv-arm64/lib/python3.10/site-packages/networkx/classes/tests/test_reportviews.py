import pickle
from copy import deepcopy

import pytest

import networkx as nx
from networkx.classes import reportviews as rv
from networkx.classes.reportviews import NodeDataView


# Nodes
class TestNodeView:
    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(9)
        cls.nv = cls.G.nodes  # NodeView(G)

    def test_pickle(self):
        import pickle

        nv = self.nv
        pnv = pickle.loads(pickle.dumps(nv, -1))
        assert nv == pnv
        assert nv.__slots__ == pnv.__slots__

    def test_str(self):
        assert str(self.nv) == "[0, 1, 2, 3, 4, 5, 6, 7, 8]"

    def test_repr(self):
        assert repr(self.nv) == "NodeView((0, 1, 2, 3, 4, 5, 6, 7, 8))"

    def test_contains(self):
        G = self.G.copy()
        nv = G.nodes
        assert 7 in nv
        assert 9 not in nv
        G.remove_node(7)
        G.add_node(9)
        assert 7 not in nv
        assert 9 in nv

    def test_getitem(self):
        G = self.G.copy()
        nv = G.nodes
        G.nodes[3]["foo"] = "bar"
        assert nv[7] == {}
        assert nv[3] == {"foo": "bar"}
        # slicing
        with pytest.raises(nx.NetworkXError):
            G.nodes[0:5]

    def test_iter(self):
        nv = self.nv
        for i, n in enumerate(nv):
            assert i == n
        inv = iter(nv)
        assert next(inv) == 0
        assert iter(nv) != nv
        assert iter(inv) == inv
        inv2 = iter(nv)
        next(inv2)
        assert list(inv) == list(inv2)
        # odd case where NodeView calls NodeDataView with data=False
        nnv = nv(data=False)
        for i, n in enumerate(nnv):
            assert i == n

    def test_call(self):
        nodes = self.nv
        assert nodes is nodes()
        assert nodes is not nodes(data=True)
        assert nodes is not nodes(data="weight")


class TestNodeDataView:
    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(9)
        cls.nv = NodeDataView(cls.G)
        cls.ndv = cls.G.nodes.data(True)
        cls.nwv = cls.G.nodes.data("foo")

    def test_viewtype(self):
        nv = self.G.nodes
        ndvfalse = nv.data(False)
        assert nv is ndvfalse
        assert nv is not self.ndv

    def test_pickle(self):
        import pickle

        nv = self.nv
        pnv = pickle.loads(pickle.dumps(nv, -1))
        assert nv == pnv
        assert nv.__slots__ == pnv.__slots__

    def test_str(self):
        msg = str([(n, {}) for n in range(9)])
        assert str(self.ndv) == msg

    def test_repr(self):
        expected = "NodeDataView((0, 1, 2, 3, 4, 5, 6, 7, 8))"
        assert repr(self.nv) == expected
        expected = (
            "NodeDataView({0: {}, 1: {}, 2: {}, 3: {}, "
            + "4: {}, 5: {}, 6: {}, 7: {}, 8: {}})"
        )
        assert repr(self.ndv) == expected
        expected = (
            "NodeDataView({0: None, 1: None, 2: None, 3: None, 4: None, "
            + "5: None, 6: None, 7: None, 8: None}, data='foo')"
        )
        assert repr(self.nwv) == expected

    def test_contains(self):
        G = self.G.copy()
        nv = G.nodes.data()
        nwv = G.nodes.data("foo")
        G.nodes[3]["foo"] = "bar"
        assert (7, {}) in nv
        assert (3, {"foo": "bar"}) in nv
        assert (3, "bar") in nwv
        assert (7, None) in nwv
        # default
        nwv_def = G.nodes(data="foo", default="biz")
        assert (7, "biz") in nwv_def
        assert (3, "bar") in nwv_def

    def test_getitem(self):
        G = self.G.copy()
        nv = G.nodes
        G.nodes[3]["foo"] = "bar"
        assert nv[3] == {"foo": "bar"}
        # default
        nwv_def = G.nodes(data="foo", default="biz")
        assert nwv_def[7], "biz"
        assert nwv_def[3] == "bar"
        # slicing
        with pytest.raises(nx.NetworkXError):
            G.nodes.data()[0:5]

    def test_iter(self):
        G = self.G.copy()
        nv = G.nodes.data()
        ndv = G.nodes.data(True)
        nwv = G.nodes.data("foo")
        for i, (n, d) in enumerate(nv):
            assert i == n
            assert d == {}
        inv = iter(nv)
        assert next(inv) == (0, {})
        G.nodes[3]["foo"] = "bar"
        # default
        for n, d in nv:
            if n == 3:
                assert d == {"foo": "bar"}
            else:
                assert d == {}
        # data=True
        for n, d in ndv:
            if n == 3:
                assert d == {"foo": "bar"}
            else:
                assert d == {}
        # data='foo'
        for n, d in nwv:
            if n == 3:
                assert d == "bar"
            else:
                assert d is None
        # data='foo', default=1
        for n, d in G.nodes.data("foo", default=1):
            if n == 3:
                assert d == "bar"
            else:
                assert d == 1


def test_nodedataview_unhashable():
    G = nx.path_graph(9)
    G.nodes[3]["foo"] = "bar"
    nvs = [G.nodes.data()]
    nvs.append(G.nodes.data(True))
    H = G.copy()
    H.nodes[4]["foo"] = {1, 2, 3}
    nvs.append(H.nodes.data(True))
    # raise unhashable
    for nv in nvs:
        pytest.raises(TypeError, set, nv)
        pytest.raises(TypeError, eval, "nv | nv", locals())
    # no raise... hashable
    Gn = G.nodes.data(False)
    set(Gn)
    Gn | Gn
    Gn = G.nodes.data("foo")
    set(Gn)
    Gn | Gn


class TestNodeViewSetOps:
    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(9)
        cls.G.nodes[3]["foo"] = "bar"
        cls.nv = cls.G.nodes

    def n_its(self, nodes):
        return set(nodes)

    def test_len(self):
        G = self.G.copy()
        nv = G.nodes
        assert len(nv) == 9
        G.remove_node(7)
        assert len(nv) == 8
        G.add_node(9)
        assert len(nv) == 9

    def test_and(self):
        # print("G & H nodes:", gnv & hnv)
        nv = self.nv
        some_nodes = self.n_its(range(5, 12))
        assert nv & some_nodes == self.n_its(range(5, 9))
        assert some_nodes & nv == self.n_its(range(5, 9))

    def test_or(self):
        # print("G | H nodes:", gnv | hnv)
        nv = self.nv
        some_nodes = self.n_its(range(5, 12))
        assert nv | some_nodes == self.n_its(range(12))
        assert some_nodes | nv == self.n_its(range(12))

    def test_xor(self):
        # print("G ^ H nodes:", gnv ^ hnv)
        nv = self.nv
        some_nodes = self.n_its(range(5, 12))
        nodes = {0, 1, 2, 3, 4, 9, 10, 11}
        assert nv ^ some_nodes == self.n_its(nodes)
        assert some_nodes ^ nv == self.n_its(nodes)

    def test_sub(self):
        # print("G - H nodes:", gnv - hnv)
        nv = self.nv
        some_nodes = self.n_its(range(5, 12))
        assert nv - some_nodes == self.n_its(range(5))
        assert some_nodes - nv == self.n_its(range(9, 12))


class TestNodeDataViewSetOps(TestNodeViewSetOps):
    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(9)
        cls.G.nodes[3]["foo"] = "bar"
        cls.nv = cls.G.nodes.data("foo")

    def n_its(self, nodes):
        return {(node, "bar" if node == 3 else None) for node in nodes}


class TestNodeDataViewDefaultSetOps(TestNodeDataViewSetOps):
    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(9)
        cls.G.nodes[3]["foo"] = "bar"
        cls.nv = cls.G.nodes.data("foo", default=1)

    def n_its(self, nodes):
        return {(node, "bar" if node == 3 else 1) for node in nodes}


# Edges Data View
class TestEdgeDataView:
    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(9)
        cls.eview = nx.reportviews.EdgeView

    def test_pickle(self):
        import pickle

        ev = self.eview(self.G)(data=True)
        pev = pickle.loads(pickle.dumps(ev, -1))
        assert list(ev) == list(pev)
        assert ev.__slots__ == pev.__slots__

    def modify_edge(self, G, e, **kwds):
        G._adj[e[0]][e[1]].update(kwds)

    def test_str(self):
        ev = self.eview(self.G)(data=True)
        rep = str([(n, n + 1, {}) for n in range(8)])
        assert str(ev) == rep

    def test_repr(self):
        ev = self.eview(self.G)(data=True)
        rep = (
            "EdgeDataView([(0, 1, {}), (1, 2, {}), "
            + "(2, 3, {}), (3, 4, {}), "
            + "(4, 5, {}), (5, 6, {}), "
            + "(6, 7, {}), (7, 8, {})])"
        )
        assert repr(ev) == rep

    def test_iterdata(self):
        G = self.G.copy()
        evr = self.eview(G)
        ev = evr(data=True)
        ev_def = evr(data="foo", default=1)

        for u, v, d in ev:
            pass
        assert d == {}

        for u, v, wt in ev_def:
            pass
        assert wt == 1

        self.modify_edge(G, (2, 3), foo="bar")
        for e in ev:
            assert len(e) == 3
            if set(e[:2]) == {2, 3}:
                assert e[2] == {"foo": "bar"}
                checked = True
            else:
                assert e[2] == {}
        assert checked

        for e in ev_def:
            assert len(e) == 3
            if set(e[:2]) == {2, 3}:
                assert e[2] == "bar"
                checked_wt = True
            else:
                assert e[2] == 1
        assert checked_wt

    def test_iter(self):
        evr = self.eview(self.G)
        ev = evr()
        for u, v in ev:
            pass
        iev = iter(ev)
        assert next(iev) == (0, 1)
        assert iter(ev) != ev
        assert iter(iev) == iev

    def test_contains(self):
        evr = self.eview(self.G)
        ev = evr()
        if self.G.is_directed():
            assert (1, 2) in ev and (2, 1) not in ev
        else:
            assert (1, 2) in ev and (2, 1) in ev
        assert (1, 4) not in ev
        assert (1, 90) not in ev
        assert (90, 1) not in ev

    def test_contains_with_nbunch(self):
        evr = self.eview(self.G)
        ev = evr(nbunch=[0, 2])
        if self.G.is_directed():
            assert (0, 1) in ev
            assert (1, 2) not in ev
            assert (2, 3) in ev
        else:
            assert (0, 1) in ev
            assert (1, 2) in ev
            assert (2, 3) in ev
        assert (3, 4) not in ev
        assert (4, 5) not in ev
        assert (5, 6) not in ev
        assert (7, 8) not in ev
        assert (8, 9) not in ev

    def test_len(self):
        evr = self.eview(self.G)
        ev = evr(data="foo")
        assert len(ev) == 8
        assert len(evr(1)) == 2
        assert len(evr([1, 2, 3])) == 4

        assert len(self.G.edges(1)) == 2
        assert len(self.G.edges()) == 8
        assert len(self.G.edges) == 8

        H = self.G.copy()
        H.add_edge(1, 1)
        assert len(H.edges(1)) == 3
        assert len(H.edges()) == 9
        assert len(H.edges) == 9


class TestOutEdgeDataView(TestEdgeDataView):
    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(9, create_using=nx.DiGraph())
        cls.eview = nx.reportviews.OutEdgeView

    def test_repr(self):
        ev = self.eview(self.G)(data=True)
        rep = (
            "OutEdgeDataView([(0, 1, {}), (1, 2, {}), "
            + "(2, 3, {}), (3, 4, {}), "
            + "(4, 5, {}), (5, 6, {}), "
            + "(6, 7, {}), (7, 8, {})])"
        )
        assert repr(ev) == rep

    def test_len(self):
        evr = self.eview(self.G)
        ev = evr(data="foo")
        assert len(ev) == 8
        assert len(evr(1)) == 1
        assert len(evr([1, 2, 3])) == 3

        assert len(self.G.edges(1)) == 1
        assert len(self.G.edges()) == 8
        assert len(self.G.edges) == 8

        H = self.G.copy()
        H.add_edge(1, 1)
        assert len(H.edges(1)) == 2
        assert len(H.edges()) == 9
        assert len(H.edges) == 9

    def test_contains_with_nbunch(self):
        evr = self.eview(self.G)
        ev = evr(nbunch=[0, 2])
        assert (0, 1) in ev
        assert (1, 2) not in ev
        assert (2, 3) in ev
        assert (3, 4) not in ev
        assert (4, 5) not in ev
        assert (5, 6) not in ev
        assert (7, 8) not in ev
        assert (8, 9) not in ev


class TestInEdgeDataView(TestOutEdgeDataView):
    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(9, create_using=nx.DiGraph())
        cls.eview = nx.reportviews.InEdgeView

    def test_repr(self):
        ev = self.eview(self.G)(data=True)
        rep = (
            "InEdgeDataView([(0, 1, {}), (1, 2, {}), "
            + "(2, 3, {}), (3, 4, {}), "
            + "(4, 5, {}), (5, 6, {}), "
            + "(6, 7, {}), (7, 8, {})])"
        )
        assert repr(ev) == rep

    def test_contains_with_nbunch(self):
        evr = self.eview(self.G)
        ev = evr(nbunch=[0, 2])
        assert (0, 1) not in ev
        assert (1, 2) in ev
        assert (2, 3) not in ev
        assert (3, 4) not in ev
        assert (4, 5) not in ev
        assert (5, 6) not in ev
        assert (7, 8) not in ev
        assert (8, 9) not in ev


class TestMultiEdgeDataView(TestEdgeDataView):
    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(9, create_using=nx.MultiGraph())
        cls.eview = nx.reportviews.MultiEdgeView

    def modify_edge(self, G, e, **kwds):
        G._adj[e[0]][e[1]][0].update(kwds)

    def test_repr(self):
        ev = self.eview(self.G)(data=True)
        rep = (
            "MultiEdgeDataView([(0, 1, {}), (1, 2, {}), "
            + "(2, 3, {}), (3, 4, {}), "
            + "(4, 5, {}), (5, 6, {}), "
            + "(6, 7, {}), (7, 8, {})])"
        )
        assert repr(ev) == rep

    def test_contains_with_nbunch(self):
        evr = self.eview(self.G)
        ev = evr(nbunch=[0, 2])
        assert (0, 1) in ev
        assert (1, 2) in ev
        assert (2, 3) in ev
        assert (3, 4) not in ev
        assert (4, 5) not in ev
        assert (5, 6) not in ev
        assert (7, 8) not in ev
        assert (8, 9) not in ev


class TestOutMultiEdgeDataView(TestOutEdgeDataView):
    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(9, create_using=nx.MultiDiGraph())
        cls.eview = nx.reportviews.OutMultiEdgeView

    def modify_edge(self, G, e, **kwds):
        G._adj[e[0]][e[1]][0].update(kwds)

    def test_repr(self):
        ev = self.eview(self.G)(data=True)
        rep = (
            "OutMultiEdgeDataView([(0, 1, {}), (1, 2, {}), "
            + "(2, 3, {}), (3, 4, {}), "
            + "(4, 5, {}), (5, 6, {}), "
            + "(6, 7, {}), (7, 8, {})])"
        )
        assert repr(ev) == rep

    def test_contains_with_nbunch(self):
        evr = self.eview(self.G)
        ev = evr(nbunch=[0, 2])
        assert (0, 1) in ev
        assert (1, 2) not in ev
        assert (2, 3) in ev
        assert (3, 4) not in ev
        assert (4, 5) not in ev
        assert (5, 6) not in ev
        assert (7, 8) not in ev
        assert (8, 9) not in ev


class TestInMultiEdgeDataView(TestOutMultiEdgeDataView):
    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(9, create_using=nx.MultiDiGraph())
        cls.eview = nx.reportviews.InMultiEdgeView

    def test_repr(self):
        ev = self.eview(self.G)(data=True)
        rep = (
            "InMultiEdgeDataView([(0, 1, {}), (1, 2, {}), "
            + "(2, 3, {}), (3, 4, {}), "
            + "(4, 5, {}), (5, 6, {}), "
            + "(6, 7, {}), (7, 8, {})])"
        )
        assert repr(ev) == rep

    def test_contains_with_nbunch(self):
        evr = self.eview(self.G)
        ev = evr(nbunch=[0, 2])
        assert (0, 1) not in ev
        assert (1, 2) in ev
        assert (2, 3) not in ev
        assert (3, 4) not in ev
        assert (4, 5) not in ev
        assert (5, 6) not in ev
        assert (7, 8) not in ev
        assert (8, 9) not in ev


# Edge Views
class TestEdgeView:
    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(9)
        cls.eview = nx.reportviews.EdgeView

    def test_pickle(self):
        import pickle

        ev = self.eview(self.G)
        pev = pickle.loads(pickle.dumps(ev, -1))
        assert ev == pev
        assert ev.__slots__ == pev.__slots__

    def modify_edge(self, G, e, **kwds):
        G._adj[e[0]][e[1]].update(kwds)

    def test_str(self):
        ev = self.eview(self.G)
        rep = str([(n, n + 1) for n in range(8)])
        assert str(ev) == rep

    def test_repr(self):
        ev = self.eview(self.G)
        rep = (
            "EdgeView([(0, 1), (1, 2), (2, 3), (3, 4), "
            + "(4, 5), (5, 6), (6, 7), (7, 8)])"
        )
        assert repr(ev) == rep

    def test_getitem(self):
        G = self.G.copy()
        ev = G.edges
        G.edges[0, 1]["foo"] = "bar"
        assert ev[0, 1] == {"foo": "bar"}

        # slicing
        with pytest.raises(nx.NetworkXError, match=".*does not support slicing"):
            G.edges[0:5]

        # Invalid edge
        with pytest.raises(KeyError, match=r".*edge.*is not in the graph."):
            G.edges[0, 9]

    def test_call(self):
        ev = self.eview(self.G)
        assert id(ev) == id(ev())
        assert id(ev) == id(ev(data=False))
        assert id(ev) != id(ev(data=True))
        assert id(ev) != id(ev(nbunch=1))

    def test_data(self):
        ev = self.eview(self.G)
        assert id(ev) != id(ev.data())
        assert id(ev) == id(ev.data(data=False))
        assert id(ev) != id(ev.data(data=True))
        assert id(ev) != id(ev.data(nbunch=1))

    def test_iter(self):
        ev = self.eview(self.G)
        for u, v in ev:
            pass
        iev = iter(ev)
        assert next(iev) == (0, 1)
        assert iter(ev) != ev
        assert iter(iev) == iev

    def test_contains(self):
        ev = self.eview(self.G)
        edv = ev()
        if self.G.is_directed():
            assert (1, 2) in ev and (2, 1) not in ev
            assert (1, 2) in edv and (2, 1) not in edv
        else:
            assert (1, 2) in ev and (2, 1) in ev
            assert (1, 2) in edv and (2, 1) in edv
        assert (1, 4) not in ev
        assert (1, 4) not in edv
        # edge not in graph
        assert (1, 90) not in ev
        assert (90, 1) not in ev
        assert (1, 90) not in edv
        assert (90, 1) not in edv

    def test_contains_with_nbunch(self):
        ev = self.eview(self.G)
        evn = ev(nbunch=[0, 2])
        assert (0, 1) in evn
        assert (1, 2) in evn
        assert (2, 3) in evn
        assert (3, 4) not in evn
        assert (4, 5) not in evn
        assert (5, 6) not in evn
        assert (7, 8) not in evn
        assert (8, 9) not in evn

    def test_len(self):
        ev = self.eview(self.G)
        num_ed = 9 if self.G.is_multigraph() else 8
        assert len(ev) == num_ed

        H = self.G.copy()
        H.add_edge(1, 1)
        assert len(H.edges(1)) == 3 + H.is_multigraph() - H.is_directed()
        assert len(H.edges()) == num_ed + 1
        assert len(H.edges) == num_ed + 1

    def test_and(self):
        # print("G & H edges:", gnv & hnv)
        ev = self.eview(self.G)
        some_edges = {(0, 1), (1, 0), (0, 2)}
        if self.G.is_directed():
            assert some_edges & ev, {(0, 1)}
            assert ev & some_edges, {(0, 1)}
        else:
            assert ev & some_edges == {(0, 1), (1, 0)}
            assert some_edges & ev == {(0, 1), (1, 0)}
        return

    def test_or(self):
        # print("G | H edges:", gnv | hnv)
        ev = self.eview(self.G)
        some_edges = {(0, 1), (1, 0), (0, 2)}
        result1 = {(n, n + 1) for n in range(8)}
        result1.update(some_edges)
        result2 = {(n + 1, n) for n in range(8)}
        result2.update(some_edges)
        assert (ev | some_edges) in (result1, result2)
        assert (some_edges | ev) in (result1, result2)

    def test_xor(self):
        # print("G ^ H edges:", gnv ^ hnv)
        ev = self.eview(self.G)
        some_edges = {(0, 1), (1, 0), (0, 2)}
        if self.G.is_directed():
            result = {(n, n + 1) for n in range(1, 8)}
            result.update({(1, 0), (0, 2)})
            assert ev ^ some_edges == result
        else:
            result = {(n, n + 1) for n in range(1, 8)}
            result.update({(0, 2)})
            assert ev ^ some_edges == result
        return

    def test_sub(self):
        # print("G - H edges:", gnv - hnv)
        ev = self.eview(self.G)
        some_edges = {(0, 1), (1, 0), (0, 2)}
        result = {(n, n + 1) for n in range(8)}
        result.remove((0, 1))
        assert ev - some_edges, result


class TestOutEdgeView(TestEdgeView):
    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(9, nx.DiGraph())
        cls.eview = nx.reportviews.OutEdgeView

    def test_repr(self):
        ev = self.eview(self.G)
        rep = (
            "OutEdgeView([(0, 1), (1, 2), (2, 3), (3, 4), "
            + "(4, 5), (5, 6), (6, 7), (7, 8)])"
        )
        assert repr(ev) == rep

    def test_contains_with_nbunch(self):
        ev = self.eview(self.G)
        evn = ev(nbunch=[0, 2])
        assert (0, 1) in evn
        assert (1, 2) not in evn
        assert (2, 3) in evn
        assert (3, 4) not in evn
        assert (4, 5) not in evn
        assert (5, 6) not in evn
        assert (7, 8) not in evn
        assert (8, 9) not in evn


class TestInEdgeView(TestEdgeView):
    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(9, nx.DiGraph())
        cls.eview = nx.reportviews.InEdgeView

    def test_repr(self):
        ev = self.eview(self.G)
        rep = (
            "InEdgeView([(0, 1), (1, 2), (2, 3), (3, 4), "
            + "(4, 5), (5, 6), (6, 7), (7, 8)])"
        )
        assert repr(ev) == rep

    def test_contains_with_nbunch(self):
        ev = self.eview(self.G)
        evn = ev(nbunch=[0, 2])
        assert (0, 1) not in evn
        assert (1, 2) in evn
        assert (2, 3) not in evn
        assert (3, 4) not in evn
        assert (4, 5) not in evn
        assert (5, 6) not in evn
        assert (7, 8) not in evn
        assert (8, 9) not in evn


class TestMultiEdgeView(TestEdgeView):
    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(9, nx.MultiGraph())
        cls.G.add_edge(1, 2, key=3, foo="bar")
        cls.eview = nx.reportviews.MultiEdgeView

    def modify_edge(self, G, e, **kwds):
        if len(e) == 2:
            e = e + (0,)
        G._adj[e[0]][e[1]][e[2]].update(kwds)

    def test_str(self):
        ev = self.eview(self.G)
        replist = [(n, n + 1, 0) for n in range(8)]
        replist.insert(2, (1, 2, 3))
        rep = str(replist)
        assert str(ev) == rep

    def test_getitem(self):
        G = self.G.copy()
        ev = G.edges
        G.edges[0, 1, 0]["foo"] = "bar"
        assert ev[0, 1, 0] == {"foo": "bar"}

        # slicing
        with pytest.raises(nx.NetworkXError):
            G.edges[0:5]

    def test_repr(self):
        ev = self.eview(self.G)
        rep = (
            "MultiEdgeView([(0, 1, 0), (1, 2, 0), (1, 2, 3), (2, 3, 0), "
            + "(3, 4, 0), (4, 5, 0), (5, 6, 0), (6, 7, 0), (7, 8, 0)])"
        )
        assert repr(ev) == rep

    def test_call(self):
        ev = self.eview(self.G)
        assert id(ev) == id(ev(keys=True))
        assert id(ev) == id(ev(data=False, keys=True))
        assert id(ev) != id(ev(keys=False))
        assert id(ev) != id(ev(data=True))
        assert id(ev) != id(ev(nbunch=1))

    def test_data(self):
        ev = self.eview(self.G)
        assert id(ev) != id(ev.data())
        assert id(ev) == id(ev.data(data=False, keys=True))
        assert id(ev) != id(ev.data(keys=False))
        assert id(ev) != id(ev.data(data=True))
        assert id(ev) != id(ev.data(nbunch=1))

    def test_iter(self):
        ev = self.eview(self.G)
        for u, v, k in ev:
            pass
        iev = iter(ev)
        assert next(iev) == (0, 1, 0)
        assert iter(ev) != ev
        assert iter(iev) == iev

    def test_iterkeys(self):
        G = self.G
        evr = self.eview(G)
        ev = evr(keys=True)
        for u, v, k in ev:
            pass
        assert k == 0
        ev = evr(keys=True, data="foo", default=1)
        for u, v, k, wt in ev:
            pass
        assert wt == 1

        self.modify_edge(G, (2, 3, 0), foo="bar")
        ev = evr(keys=True, data=True)
        for e in ev:
            assert len(e) == 4
            print("edge:", e)
            if set(e[:2]) == {2, 3}:
                print(self.G._adj[2][3])
                assert e[2] == 0
                assert e[3] == {"foo": "bar"}
                checked = True
            elif set(e[:3]) == {1, 2, 3}:
                assert e[2] == 3
                assert e[3] == {"foo": "bar"}
                checked_multi = True
            else:
                assert e[2] == 0
                assert e[3] == {}
        assert checked
        assert checked_multi
        ev = evr(keys=True, data="foo", default=1)
        for e in ev:
            if set(e[:2]) == {1, 2} and e[2] == 3:
                assert e[3] == "bar"
            if set(e[:2]) == {1, 2} and e[2] == 0:
                assert e[3] == 1
            if set(e[:2]) == {2, 3}:
                assert e[2] == 0
                assert e[3] == "bar"
                assert len(e) == 4
                checked_wt = True
        assert checked_wt
        ev = evr(keys=True)
        for e in ev:
            assert len(e) == 3
        elist = sorted([(i, i + 1, 0) for i in range(8)] + [(1, 2, 3)])
        assert sorted(ev) == elist
        # test that the keyword arguments are passed correctly
        ev = evr((1, 2), "foo", keys=True, default=1)
        with pytest.raises(TypeError):
            evr((1, 2), "foo", True, 1)
        with pytest.raises(TypeError):
            evr((1, 2), "foo", True, default=1)
        for e in ev:
            if set(e[:2]) == {1, 2}:
                assert e[2] in {0, 3}
                if e[2] == 3:
                    assert e[3] == "bar"
                else:  # e[2] == 0
                    assert e[3] == 1
        if G.is_directed():
            assert len(list(ev)) == 3
        else:
            assert len(list(ev)) == 4

    def test_or(self):
        # print("G | H edges:", gnv | hnv)
        ev = self.eview(self.G)
        some_edges = {(0, 1, 0), (1, 0, 0), (0, 2, 0)}
        result = {(n, n + 1, 0) for n in range(8)}
        result.update(some_edges)
        result.update({(1, 2, 3)})
        assert ev | some_edges == result
        assert some_edges | ev == result

    def test_sub(self):
        # print("G - H edges:", gnv - hnv)
        ev = self.eview(self.G)
        some_edges = {(0, 1, 0), (1, 0, 0), (0, 2, 0)}
        result = {(n, n + 1, 0) for n in range(8)}
        result.remove((0, 1, 0))
        result.update({(1, 2, 3)})
        assert ev - some_edges, result
        assert some_edges - ev, result

    def test_xor(self):
        # print("G ^ H edges:", gnv ^ hnv)
        ev = self.eview(self.G)
        some_edges = {(0, 1, 0), (1, 0, 0), (0, 2, 0)}
        if self.G.is_directed():
            result = {(n, n + 1, 0) for n in range(1, 8)}
            result.update({(1, 0, 0), (0, 2, 0), (1, 2, 3)})
            assert ev ^ some_edges == result
            assert some_edges ^ ev == result
        else:
            result = {(n, n + 1, 0) for n in range(1, 8)}
            result.update({(0, 2, 0), (1, 2, 3)})
            assert ev ^ some_edges == result
            assert some_edges ^ ev == result

    def test_and(self):
        # print("G & H edges:", gnv & hnv)
        ev = self.eview(self.G)
        some_edges = {(0, 1, 0), (1, 0, 0), (0, 2, 0)}
        if self.G.is_directed():
            assert ev & some_edges == {(0, 1, 0)}
            assert some_edges & ev == {(0, 1, 0)}
        else:
            assert ev & some_edges == {(0, 1, 0), (1, 0, 0)}
            assert some_edges & ev == {(0, 1, 0), (1, 0, 0)}

    def test_contains_with_nbunch(self):
        ev = self.eview(self.G)
        evn = ev(nbunch=[0, 2])
        assert (0, 1) in evn
        assert (1, 2) in evn
        assert (2, 3) in evn
        assert (3, 4) not in evn
        assert (4, 5) not in evn
        assert (5, 6) not in evn
        assert (7, 8) not in evn
        assert (8, 9) not in evn


class TestOutMultiEdgeView(TestMultiEdgeView):
    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(9, nx.MultiDiGraph())
        cls.G.add_edge(1, 2, key=3, foo="bar")
        cls.eview = nx.reportviews.OutMultiEdgeView

    def modify_edge(self, G, e, **kwds):
        if len(e) == 2:
            e = e + (0,)
        G._adj[e[0]][e[1]][e[2]].update(kwds)

    def test_repr(self):
        ev = self.eview(self.G)
        rep = (
            "OutMultiEdgeView([(0, 1, 0), (1, 2, 0), (1, 2, 3), (2, 3, 0),"
            + " (3, 4, 0), (4, 5, 0), (5, 6, 0), (6, 7, 0), (7, 8, 0)])"
        )
        assert repr(ev) == rep

    def test_contains_with_nbunch(self):
        ev = self.eview(self.G)
        evn = ev(nbunch=[0, 2])
        assert (0, 1) in evn
        assert (1, 2) not in evn
        assert (2, 3) in evn
        assert (3, 4) not in evn
        assert (4, 5) not in evn
        assert (5, 6) not in evn
        assert (7, 8) not in evn
        assert (8, 9) not in evn


class TestInMultiEdgeView(TestMultiEdgeView):
    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(9, nx.MultiDiGraph())
        cls.G.add_edge(1, 2, key=3, foo="bar")
        cls.eview = nx.reportviews.InMultiEdgeView

    def modify_edge(self, G, e, **kwds):
        if len(e) == 2:
            e = e + (0,)
        G._adj[e[0]][e[1]][e[2]].update(kwds)

    def test_repr(self):
        ev = self.eview(self.G)
        rep = (
            "InMultiEdgeView([(0, 1, 0), (1, 2, 0), (1, 2, 3), (2, 3, 0), "
            + "(3, 4, 0), (4, 5, 0), (5, 6, 0), (6, 7, 0), (7, 8, 0)])"
        )
        assert repr(ev) == rep

    def test_contains_with_nbunch(self):
        ev = self.eview(self.G)
        evn = ev(nbunch=[0, 2])
        assert (0, 1) not in evn
        assert (1, 2) in evn
        assert (2, 3) not in evn
        assert (3, 4) not in evn
        assert (4, 5) not in evn
        assert (5, 6) not in evn
        assert (7, 8) not in evn
        assert (8, 9) not in evn


# Degrees
class TestDegreeView:
    GRAPH = nx.Graph
    dview = nx.reportviews.DegreeView

    @classmethod
    def setup_class(cls):
        cls.G = nx.path_graph(6, cls.GRAPH())
        cls.G.add_edge(1, 3, foo=2)
        cls.G.add_edge(1, 3, foo=3)

    def test_pickle(self):
        import pickle

        deg = self.G.degree
        pdeg = pickle.loads(pickle.dumps(deg, -1))
        assert dict(deg) == dict(pdeg)

    def test_str(self):
        dv = self.dview(self.G)
        rep = str([(0, 1), (1, 3), (2, 2), (3, 3), (4, 2), (5, 1)])
        assert str(dv) == rep
        dv = self.G.degree()
        assert str(dv) == rep

    def test_repr(self):
        dv = self.dview(self.G)
        rep = "DegreeView({0: 1, 1: 3, 2: 2, 3: 3, 4: 2, 5: 1})"
        assert repr(dv) == rep

    def test_iter(self):
        dv = self.dview(self.G)
        for n, d in dv:
            pass
        idv = iter(dv)
        assert iter(dv) != dv
        assert iter(idv) == idv
        assert next(idv) == (0, dv[0])
        assert next(idv) == (1, dv[1])
        # weighted
        dv = self.dview(self.G, weight="foo")
        for n, d in dv:
            pass
        idv = iter(dv)
        assert iter(dv) != dv
        assert iter(idv) == idv
        assert next(idv) == (0, dv[0])
        assert next(idv) == (1, dv[1])

    def test_nbunch(self):
        dv = self.dview(self.G)
        dvn = dv(0)
        assert dvn == 1
        dvn = dv([2, 3])
        assert sorted(dvn) == [(2, 2), (3, 3)]

    def test_getitem(self):
        dv = self.dview(self.G)
        assert dv[0] == 1
        assert dv[1] == 3
        assert dv[2] == 2
        assert dv[3] == 3
        dv = self.dview(self.G, weight="foo")
        assert dv[0] == 1
        assert dv[1] == 5
        assert dv[2] == 2
        assert dv[3] == 5

    def test_weight(self):
        dv = self.dview(self.G)
        dvw = dv(0, weight="foo")
        assert dvw == 1
        dvw = dv(1, weight="foo")
        assert dvw == 5
        dvw = dv([2, 3], weight="foo")
        assert sorted(dvw) == [(2, 2), (3, 5)]
        dvd = dict(dv(weight="foo"))
        assert dvd[0] == 1
        assert dvd[1] == 5
        assert dvd[2] == 2
        assert dvd[3] == 5

    def test_len(self):
        dv = self.dview(self.G)
        assert len(dv) == 6


class TestDiDegreeView(TestDegreeView):
    GRAPH = nx.DiGraph
    dview = nx.reportviews.DiDegreeView

    def test_repr(self):
        dv = self.G.degree()
        rep = "DiDegreeView({0: 1, 1: 3, 2: 2, 3: 3, 4: 2, 5: 1})"
        assert repr(dv) == rep


class TestOutDegreeView(TestDegreeView):
    GRAPH = nx.DiGraph
    dview = nx.reportviews.OutDegreeView

    def test_str(self):
        dv = self.dview(self.G)
        rep = str([(0, 1), (1, 2), (2, 1), (3, 1), (4, 1), (5, 0)])
        assert str(dv) == rep
        dv = self.G.out_degree()
        assert str(dv) == rep

    def test_repr(self):
        dv = self.G.out_degree()
        rep = "OutDegreeView({0: 1, 1: 2, 2: 1, 3: 1, 4: 1, 5: 0})"
        assert repr(dv) == rep

    def test_nbunch(self):
        dv = self.dview(self.G)
        dvn = dv(0)
        assert dvn == 1
        dvn = dv([2, 3])
        assert sorted(dvn) == [(2, 1), (3, 1)]

    def test_getitem(self):
        dv = self.dview(self.G)
        assert dv[0] == 1
        assert dv[1] == 2
        assert dv[2] == 1
        assert dv[3] == 1
        dv = self.dview(self.G, weight="foo")
        assert dv[0] == 1
        assert dv[1] == 4
        assert dv[2] == 1
        assert dv[3] == 1

    def test_weight(self):
        dv = self.dview(self.G)
        dvw = dv(0, weight="foo")
        assert dvw == 1
        dvw = dv(1, weight="foo")
        assert dvw == 4
        dvw = dv([2, 3], weight="foo")
        assert sorted(dvw) == [(2, 1), (3, 1)]
        dvd = dict(dv(weight="foo"))
        assert dvd[0] == 1
        assert dvd[1] == 4
        assert dvd[2] == 1
        assert dvd[3] == 1


class TestInDegreeView(TestDegreeView):
    GRAPH = nx.DiGraph
    dview = nx.reportviews.InDegreeView

    def test_str(self):
        dv = self.dview(self.G)
        rep = str([(0, 0), (1, 1), (2, 1), (3, 2), (4, 1), (5, 1)])
        assert str(dv) == rep
        dv = self.G.in_degree()
        assert str(dv) == rep

    def test_repr(self):
        dv = self.G.in_degree()
        rep = "InDegreeView({0: 0, 1: 1, 2: 1, 3: 2, 4: 1, 5: 1})"
        assert repr(dv) == rep

    def test_nbunch(self):
        dv = self.dview(self.G)
        dvn = dv(0)
        assert dvn == 0
        dvn = dv([2, 3])
        assert sorted(dvn) == [(2, 1), (3, 2)]

    def test_getitem(self):
        dv = self.dview(self.G)
        assert dv[0] == 0
        assert dv[1] == 1
        assert dv[2] == 1
        assert dv[3] == 2
        dv = self.dview(self.G, weight="foo")
        assert dv[0] == 0
        assert dv[1] == 1
        assert dv[2] == 1
        assert dv[3] == 4

    def test_weight(self):
        dv = self.dview(self.G)
        dvw = dv(0, weight="foo")
        assert dvw == 0
        dvw = dv(1, weight="foo")
        assert dvw == 1
        dvw = dv([2, 3], weight="foo")
        assert sorted(dvw) == [(2, 1), (3, 4)]
        dvd = dict(dv(weight="foo"))
        assert dvd[0] == 0
        assert dvd[1] == 1
        assert dvd[2] == 1
        assert dvd[3] == 4


class TestMultiDegreeView(TestDegreeView):
    GRAPH = nx.MultiGraph
    dview = nx.reportviews.MultiDegreeView

    def test_str(self):
        dv = self.dview(self.G)
        rep = str([(0, 1), (1, 4), (2, 2), (3, 4), (4, 2), (5, 1)])
        assert str(dv) == rep
        dv = self.G.degree()
        assert str(dv) == rep

    def test_repr(self):
        dv = self.G.degree()
        rep = "MultiDegreeView({0: 1, 1: 4, 2: 2, 3: 4, 4: 2, 5: 1})"
        assert repr(dv) == rep

    def test_nbunch(self):
        dv = self.dview(self.G)
        dvn = dv(0)
        assert dvn == 1
        dvn = dv([2, 3])
        assert sorted(dvn) == [(2, 2), (3, 4)]

    def test_getitem(self):
        dv = self.dview(self.G)
        assert dv[0] == 1
        assert dv[1] == 4
        assert dv[2] == 2
        assert dv[3] == 4
        dv = self.dview(self.G, weight="foo")
        assert dv[0] == 1
        assert dv[1] == 7
        assert dv[2] == 2
        assert dv[3] == 7

    def test_weight(self):
        dv = self.dview(self.G)
        dvw = dv(0, weight="foo")
        assert dvw == 1
        dvw = dv(1, weight="foo")
        assert dvw == 7
        dvw = dv([2, 3], weight="foo")
        assert sorted(dvw) == [(2, 2), (3, 7)]
        dvd = dict(dv(weight="foo"))
        assert dvd[0] == 1
        assert dvd[1] == 7
        assert dvd[2] == 2
        assert dvd[3] == 7


class TestDiMultiDegreeView(TestMultiDegreeView):
    GRAPH = nx.MultiDiGraph
    dview = nx.reportviews.DiMultiDegreeView

    def test_repr(self):
        dv = self.G.degree()
        rep = "DiMultiDegreeView({0: 1, 1: 4, 2: 2, 3: 4, 4: 2, 5: 1})"
        assert repr(dv) == rep


class TestOutMultiDegreeView(TestDegreeView):
    GRAPH = nx.MultiDiGraph
    dview = nx.reportviews.OutMultiDegreeView

    def test_str(self):
        dv = self.dview(self.G)
        rep = str([(0, 1), (1, 3), (2, 1), (3, 1), (4, 1), (5, 0)])
        assert str(dv) == rep
        dv = self.G.out_degree()
        assert str(dv) == rep

    def test_repr(self):
        dv = self.G.out_degree()
        rep = "OutMultiDegreeView({0: 1, 1: 3, 2: 1, 3: 1, 4: 1, 5: 0})"
        assert repr(dv) == rep

    def test_nbunch(self):
        dv = self.dview(self.G)
        dvn = dv(0)
        assert dvn == 1
        dvn = dv([2, 3])
        assert sorted(dvn) == [(2, 1), (3, 1)]

    def test_getitem(self):
        dv = self.dview(self.G)
        assert dv[0] == 1
        assert dv[1] == 3
        assert dv[2] == 1
        assert dv[3] == 1
        dv = self.dview(self.G, weight="foo")
        assert dv[0] == 1
        assert dv[1] == 6
        assert dv[2] == 1
        assert dv[3] == 1

    def test_weight(self):
        dv = self.dview(self.G)
        dvw = dv(0, weight="foo")
        assert dvw == 1
        dvw = dv(1, weight="foo")
        assert dvw == 6
        dvw = dv([2, 3], weight="foo")
        assert sorted(dvw) == [(2, 1), (3, 1)]
        dvd = dict(dv(weight="foo"))
        assert dvd[0] == 1
        assert dvd[1] == 6
        assert dvd[2] == 1
        assert dvd[3] == 1


class TestInMultiDegreeView(TestDegreeView):
    GRAPH = nx.MultiDiGraph
    dview = nx.reportviews.InMultiDegreeView

    def test_str(self):
        dv = self.dview(self.G)
        rep = str([(0, 0), (1, 1), (2, 1), (3, 3), (4, 1), (5, 1)])
        assert str(dv) == rep
        dv = self.G.in_degree()
        assert str(dv) == rep

    def test_repr(self):
        dv = self.G.in_degree()
        rep = "InMultiDegreeView({0: 0, 1: 1, 2: 1, 3: 3, 4: 1, 5: 1})"
        assert repr(dv) == rep

    def test_nbunch(self):
        dv = self.dview(self.G)
        dvn = dv(0)
        assert dvn == 0
        dvn = dv([2, 3])
        assert sorted(dvn) == [(2, 1), (3, 3)]

    def test_getitem(self):
        dv = self.dview(self.G)
        assert dv[0] == 0
        assert dv[1] == 1
        assert dv[2] == 1
        assert dv[3] == 3
        dv = self.dview(self.G, weight="foo")
        assert dv[0] == 0
        assert dv[1] == 1
        assert dv[2] == 1
        assert dv[3] == 6

    def test_weight(self):
        dv = self.dview(self.G)
        dvw = dv(0, weight="foo")
        assert dvw == 0
        dvw = dv(1, weight="foo")
        assert dvw == 1
        dvw = dv([2, 3], weight="foo")
        assert sorted(dvw) == [(2, 1), (3, 6)]
        dvd = dict(dv(weight="foo"))
        assert dvd[0] == 0
        assert dvd[1] == 1
        assert dvd[2] == 1
        assert dvd[3] == 6


@pytest.mark.parametrize(
    ("reportview", "err_msg_terms"),
    (
        (rv.NodeView, "list(G.nodes"),
        (rv.NodeDataView, "list(G.nodes.data"),
        (rv.EdgeView, "list(G.edges"),
        # Directed EdgeViews
        (rv.InEdgeView, "list(G.in_edges"),
        (rv.OutEdgeView, "list(G.edges"),
        # Multi EdgeViews
        (rv.MultiEdgeView, "list(G.edges"),
        (rv.InMultiEdgeView, "list(G.in_edges"),
        (rv.OutMultiEdgeView, "list(G.edges"),
    ),
)
def test_slicing_reportviews(reportview, err_msg_terms):
    G = nx.complete_graph(3)
    view = reportview(G)
    with pytest.raises(nx.NetworkXError) as exc:
        view[0:2]
    errmsg = str(exc.value)
    assert type(view).__name__ in errmsg
    assert err_msg_terms in errmsg


@pytest.mark.parametrize(
    "graph", [nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph]
)
def test_cache_dict_get_set_state(graph):
    G = nx.path_graph(5, graph())
    G.nodes, G.edges, G.adj, G.degree
    if G.is_directed():
        G.pred, G.succ, G.in_edges, G.out_edges, G.in_degree, G.out_degree
    cached_dict = G.__dict__
    assert "nodes" in cached_dict
    assert "edges" in cached_dict
    assert "adj" in cached_dict
    assert "degree" in cached_dict
    if G.is_directed():
        assert "pred" in cached_dict
        assert "succ" in cached_dict
        assert "in_edges" in cached_dict
        assert "out_edges" in cached_dict
        assert "in_degree" in cached_dict
        assert "out_degree" in cached_dict

    # Raises error if the cached properties and views do not work
    pickle.loads(pickle.dumps(G, -1))
    deepcopy(G)


def test_edge_views_inherit_from_EdgeViewABC():
    all_edge_view_classes = (v for v in dir(nx.reportviews) if "Edge" in v)
    for eview_class in all_edge_view_classes:
        assert issubclass(
            getattr(nx.reportviews, eview_class), nx.reportviews.EdgeViewABC
        )
