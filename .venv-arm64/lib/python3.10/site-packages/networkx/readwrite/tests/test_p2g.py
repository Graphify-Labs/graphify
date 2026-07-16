import io

import networkx as nx
from networkx.readwrite.p2g import read_p2g, write_p2g
from networkx.utils import edges_equal


class TestP2G:
    @classmethod
    def setup_class(cls):
        cls.G = nx.Graph(name="test")
        e = [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e"), ("e", "f"), ("a", "f")]
        cls.G.add_edges_from(e)
        cls.G.add_node("g")
        cls.DG = nx.DiGraph(cls.G)

    def test_read_p2g(self):
        s = b"""\
name
3 4
a
1 2
b

c
0 2
"""
        bytesIO = io.BytesIO(s)
        G = read_p2g(bytesIO)
        assert G.name == "name"
        assert sorted(G) == ["a", "b", "c"]
        edges = [(str(u), str(v)) for u, v in G.edges()]
        assert edges_equal(G.edges(), [("a", "c"), ("a", "b"), ("c", "a"), ("c", "c")])

    def test_write_p2g(self):
        s = b"""foo
3 2
1
1 
2
2 
3

"""
        fh = io.BytesIO()
        G = nx.DiGraph()
        G.name = "foo"
        G.add_edges_from([(1, 2), (2, 3)])
        write_p2g(G, fh)
        fh.seek(0)
        r = fh.read()
        assert r == s

    def test_write_read_p2g(self):
        fh = io.BytesIO()
        G = nx.DiGraph()
        G.name = "foo"
        G.add_edges_from([("a", "b"), ("b", "c")])
        write_p2g(G, fh)
        fh.seek(0)
        H = read_p2g(fh)
        assert edges_equal(G.edges(), H.edges())
