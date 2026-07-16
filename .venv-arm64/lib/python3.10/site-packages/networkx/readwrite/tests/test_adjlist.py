"""
Unit tests for adjlist.
"""

import io

import pytest

import networkx as nx
from networkx.utils import edges_equal, graphs_equal, nodes_equal


class TestAdjlist:
    @classmethod
    def setup_class(cls):
        cls.G = nx.Graph(name="test")
        e = [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e"), ("e", "f"), ("a", "f")]
        cls.G.add_edges_from(e)
        cls.G.add_node("g")
        cls.DG = nx.DiGraph(cls.G)
        cls.XG = nx.MultiGraph()
        cls.XG.add_weighted_edges_from([(1, 2, 5), (1, 2, 5), (1, 2, 1), (3, 3, 42)])
        cls.XDG = nx.MultiDiGraph(cls.XG)

    def test_read_multiline_adjlist_1(self):
        # Unit test for https://networkx.lanl.gov/trac/ticket/252
        s = b"""# comment line
1 2
# comment line
2
3
"""
        bytesIO = io.BytesIO(s)
        G = nx.read_multiline_adjlist(bytesIO)
        adj = {"1": {"3": {}, "2": {}}, "3": {"1": {}}, "2": {"1": {}}}
        assert graphs_equal(G, nx.Graph(adj))

    def test_unicode(self, tmp_path):
        G = nx.Graph()
        name1 = chr(2344) + chr(123) + chr(6543)
        name2 = chr(5543) + chr(1543) + chr(324)
        G.add_edge(name1, "Radiohead", **{name2: 3})

        fname = tmp_path / "adjlist.txt"
        nx.write_multiline_adjlist(G, fname)
        H = nx.read_multiline_adjlist(fname)
        assert graphs_equal(G, H)

    def test_latin1_err(self, tmp_path):
        G = nx.Graph()
        name1 = chr(2344) + chr(123) + chr(6543)
        name2 = chr(5543) + chr(1543) + chr(324)
        G.add_edge(name1, "Radiohead", **{name2: 3})
        fname = tmp_path / "adjlist.txt"
        with pytest.raises(UnicodeEncodeError):
            nx.write_multiline_adjlist(G, fname, encoding="latin-1")

    def test_latin1(self, tmp_path):
        G = nx.Graph()
        name1 = "Bj" + chr(246) + "rk"
        name2 = chr(220) + "ber"
        G.add_edge(name1, "Radiohead", **{name2: 3})
        fname = tmp_path / "adjlist.txt"
        nx.write_multiline_adjlist(G, fname, encoding="latin-1")
        H = nx.read_multiline_adjlist(fname, encoding="latin-1")
        assert graphs_equal(G, H)

    def test_parse_adjlist(self):
        lines = ["1 2 5", "2 3 4", "3 5", "4", "5"]
        nx.parse_adjlist(lines, nodetype=int)  # smoke test
        with pytest.raises(TypeError):
            nx.parse_adjlist(lines, nodetype="int")
        lines = ["1 2 5", "2 b", "c"]
        with pytest.raises(TypeError):
            nx.parse_adjlist(lines, nodetype=int)

    def test_adjlist_graph(self, tmp_path):
        G = self.G
        fname = tmp_path / "adjlist.txt"
        nx.write_adjlist(G, fname)
        H = nx.read_adjlist(fname)
        H2 = nx.read_adjlist(fname)
        assert H is not H2  # they should be different graphs
        assert nodes_equal(list(H), list(G))
        assert edges_equal(list(H.edges()), list(G.edges()))

    def test_adjlist_digraph(self, tmp_path):
        G = self.DG
        fname = tmp_path / "adjlist.txt"
        nx.write_adjlist(G, fname)
        H = nx.read_adjlist(fname, create_using=nx.DiGraph())
        H2 = nx.read_adjlist(fname, create_using=nx.DiGraph())
        assert H is not H2  # they should be different graphs
        assert nodes_equal(list(H), list(G))
        assert edges_equal(list(H.edges()), list(G.edges()))

    def test_adjlist_integers(self, tmp_path):
        fname = tmp_path / "adjlist.txt"
        G = nx.convert_node_labels_to_integers(self.G)
        nx.write_adjlist(G, fname)
        H = nx.read_adjlist(fname, nodetype=int)
        H2 = nx.read_adjlist(fname, nodetype=int)
        assert H is not H2  # they should be different graphs
        assert nodes_equal(list(H), list(G))
        assert edges_equal(list(H.edges()), list(G.edges()))

    def test_adjlist_multigraph(self, tmp_path):
        G = self.XG
        fname = tmp_path / "adjlist.txt"
        nx.write_adjlist(G, fname)
        H = nx.read_adjlist(fname, nodetype=int, create_using=nx.MultiGraph())
        H2 = nx.read_adjlist(fname, nodetype=int, create_using=nx.MultiGraph())
        assert H is not H2  # they should be different graphs
        assert nodes_equal(list(H), list(G))
        assert edges_equal(list(H.edges()), list(G.edges()))

    def test_adjlist_multidigraph(self, tmp_path):
        G = self.XDG
        fname = tmp_path / "adjlist.txt"
        nx.write_adjlist(G, fname)
        H = nx.read_adjlist(fname, nodetype=int, create_using=nx.MultiDiGraph())
        H2 = nx.read_adjlist(fname, nodetype=int, create_using=nx.MultiDiGraph())
        assert H is not H2  # they should be different graphs
        assert nodes_equal(list(H), list(G))
        assert edges_equal(list(H.edges()), list(G.edges()))

    def test_adjlist_delimiter(self):
        fh = io.BytesIO()
        G = nx.path_graph(3)
        nx.write_adjlist(G, fh, delimiter=":")
        fh.seek(0)
        H = nx.read_adjlist(fh, nodetype=int, delimiter=":")
        assert nodes_equal(list(H), list(G))
        assert edges_equal(list(H.edges()), list(G.edges()))


class TestMultilineAdjlist:
    @classmethod
    def setup_class(cls):
        cls.G = nx.Graph(name="test")
        e = [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e"), ("e", "f"), ("a", "f")]
        cls.G.add_edges_from(e)
        cls.G.add_node("g")
        cls.DG = nx.DiGraph(cls.G)
        cls.DG.remove_edge("b", "a")
        cls.DG.remove_edge("b", "c")
        cls.XG = nx.MultiGraph()
        cls.XG.add_weighted_edges_from([(1, 2, 5), (1, 2, 5), (1, 2, 1), (3, 3, 42)])
        cls.XDG = nx.MultiDiGraph(cls.XG)

    def test_parse_multiline_adjlist(self):
        lines = [
            "1 2",
            "b {'weight':3, 'name': 'Frodo'}",
            "c {}",
            "d 1",
            "e {'weight':6, 'name': 'Saruman'}",
        ]
        nx.parse_multiline_adjlist(iter(lines))  # smoke test
        with pytest.raises(TypeError):
            nx.parse_multiline_adjlist(iter(lines), nodetype=int)
        nx.parse_multiline_adjlist(iter(lines), edgetype=str)  # smoke test
        with pytest.raises(TypeError):
            nx.parse_multiline_adjlist(iter(lines), nodetype=int)
        lines = ["1 a"]
        with pytest.raises(TypeError):
            nx.parse_multiline_adjlist(iter(lines))
        lines = ["a 2"]
        with pytest.raises(TypeError):
            nx.parse_multiline_adjlist(iter(lines), nodetype=int)
        lines = ["1 2"]
        with pytest.raises(TypeError):
            nx.parse_multiline_adjlist(iter(lines))
        lines = ["1 2", "2 {}"]
        with pytest.raises(TypeError):
            nx.parse_multiline_adjlist(iter(lines))

    def test_multiline_adjlist_graph(self, tmp_path):
        G = self.G
        fname = tmp_path / "adjlist.txt"
        nx.write_multiline_adjlist(G, fname)
        H = nx.read_multiline_adjlist(fname)
        H2 = nx.read_multiline_adjlist(fname)
        assert H is not H2  # they should be different graphs
        assert nodes_equal(list(H), list(G))
        assert edges_equal(list(H.edges()), list(G.edges()))

    def test_multiline_adjlist_digraph(self, tmp_path):
        G = self.DG
        fname = tmp_path / "adjlist.txt"
        nx.write_multiline_adjlist(G, fname)
        H = nx.read_multiline_adjlist(fname, create_using=nx.DiGraph())
        H2 = nx.read_multiline_adjlist(fname, create_using=nx.DiGraph())
        assert H is not H2  # they should be different graphs
        assert nodes_equal(list(H), list(G))
        assert edges_equal(list(H.edges()), list(G.edges()))

    def test_multiline_adjlist_integers(self, tmp_path):
        fname = tmp_path / "adjlist.txt"
        G = nx.convert_node_labels_to_integers(self.G)
        nx.write_multiline_adjlist(G, fname)
        H = nx.read_multiline_adjlist(fname, nodetype=int)
        H2 = nx.read_multiline_adjlist(fname, nodetype=int)
        assert H is not H2  # they should be different graphs
        assert nodes_equal(list(H), list(G))
        assert edges_equal(list(H.edges()), list(G.edges()))

    def test_multiline_adjlist_multigraph(self, tmp_path):
        G = self.XG
        fname = tmp_path / "adjlist.txt"
        nx.write_multiline_adjlist(G, fname)
        H = nx.read_multiline_adjlist(fname, nodetype=int, create_using=nx.MultiGraph())
        H2 = nx.read_multiline_adjlist(
            fname, nodetype=int, create_using=nx.MultiGraph()
        )
        assert H is not H2  # they should be different graphs
        assert nodes_equal(list(H), list(G))
        assert edges_equal(list(H.edges()), list(G.edges()))

    def test_multiline_adjlist_multidigraph(self, tmp_path):
        G = self.XDG
        fname = tmp_path / "adjlist.txt"
        nx.write_multiline_adjlist(G, fname)
        H = nx.read_multiline_adjlist(
            fname, nodetype=int, create_using=nx.MultiDiGraph()
        )
        H2 = nx.read_multiline_adjlist(
            fname, nodetype=int, create_using=nx.MultiDiGraph()
        )
        assert H is not H2  # they should be different graphs
        assert nodes_equal(list(H), list(G))
        assert edges_equal(list(H.edges()), list(G.edges()))

    def test_multiline_adjlist_delimiter(self):
        fh = io.BytesIO()
        G = nx.path_graph(3)
        nx.write_multiline_adjlist(G, fh, delimiter=":")
        fh.seek(0)
        H = nx.read_multiline_adjlist(fh, nodetype=int, delimiter=":")
        assert nodes_equal(list(H), list(G))
        assert edges_equal(list(H.edges()), list(G.edges()))


@pytest.mark.parametrize(
    ("lines", "delim"),
    (
        (["1 2 5", "2 3 4", "3 5", "4", "5"], None),  # No extra whitespace
        (["1\t2\t5", "2\t3\t4", "3\t5", "4", "5"], "\t"),  # tab-delimited
        (
            ["1\t2\t5", "2\t3\t4", "3\t5\t", "4\t", "5"],
            "\t",
        ),  # tab-delimited, extra delims
        (
            ["1\t2\t5", "2\t3\t4", "3\t5\t\t\n", "4\t", "5"],
            "\t",
        ),  # extra delim+newlines
    ),
)
def test_adjlist_rstrip_parsing(lines, delim):
    """Regression test related to gh-7465"""
    expected = nx.Graph([(1, 2), (1, 5), (2, 3), (2, 4), (3, 5)])
    nx.utils.graphs_equal(nx.parse_adjlist(lines, delimiter=delim), expected)
