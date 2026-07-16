"""
Pajek tests
"""

import networkx as nx
from networkx.utils import edges_equal, nodes_equal


class TestPajek:
    @classmethod
    def setup_class(cls):
        cls.data = """*network Tralala\n*vertices 4\n   1 "A1"         0.0938 0.0896   ellipse x_fact 1 y_fact 1\n   2 "Bb"         0.8188 0.2458   ellipse x_fact 1 y_fact 1\n   3 "C"          0.3688 0.7792   ellipse x_fact 1\n   4 "D2"         0.9583 0.8563   ellipse x_fact 1\n*arcs\n1 1 1  h2 0 w 3 c Blue s 3 a1 -130 k1 0.6 a2 -130 k2 0.6 ap 0.5 l "Bezier loop" lc BlueViolet fos 20 lr 58 lp 0.3 la 360\n2 1 1  h2 0 a1 120 k1 1.3 a2 -120 k2 0.3 ap 25 l "Bezier arc" lphi 270 la 180 lr 19 lp 0.5\n1 2 1  h2 0 a1 40 k1 2.8 a2 30 k2 0.8 ap 25 l "Bezier arc" lphi 90 la 0 lp 0.65\n4 2 -1  h2 0 w 1 k1 -2 k2 250 ap 25 l "Circular arc" c Red lc OrangeRed\n3 4 1  p Dashed h2 0 w 2 c OliveGreen ap 25 l "Straight arc" lc PineGreen\n1 3 1  p Dashed h2 0 w 5 k1 -1 k2 -20 ap 25 l "Oval arc" c Brown lc Black\n3 3 -1  h1 6 w 1 h2 12 k1 -2 k2 -15 ap 0.5 l "Circular loop" c Red lc OrangeRed lphi 270 la 180"""
        cls.G = nx.MultiDiGraph()
        cls.G.add_nodes_from(["A1", "Bb", "C", "D2"])
        cls.G.add_edges_from(
            [
                ("A1", "A1"),
                ("A1", "Bb"),
                ("A1", "C"),
                ("Bb", "A1"),
                ("C", "C"),
                ("C", "D2"),
                ("D2", "Bb"),
            ]
        )

        cls.G.graph["name"] = "Tralala"

    def test_parse_pajek_simple(self):
        # Example without node positions or shape
        data = """*Vertices 2\n1 "1"\n2 "2"\n*Edges\n1 2\n2 1"""
        G = nx.parse_pajek(data)
        assert sorted(G.nodes()) == ["1", "2"]
        assert edges_equal(G.edges(), [("1", "2"), ("1", "2")])

    def test_parse_pajek(self):
        G = nx.parse_pajek(self.data)
        assert sorted(G.nodes()) == ["A1", "Bb", "C", "D2"]
        assert edges_equal(
            G.edges(),
            [
                ("A1", "A1"),
                ("A1", "Bb"),
                ("A1", "C"),
                ("Bb", "A1"),
                ("C", "C"),
                ("C", "D2"),
                ("D2", "Bb"),
            ],
        )

    def test_parse_pajet_mat(self):
        data = """*Vertices 3\n1 "one"\n2 "two"\n3 "three"\n*Matrix\n1 1 0\n0 1 0\n0 1 0\n"""
        G = nx.parse_pajek(data)
        assert set(G.nodes()) == {"one", "two", "three"}
        assert G.nodes["two"] == {"id": "2"}
        assert edges_equal(
            set(G.edges()),
            {("one", "one"), ("two", "one"), ("two", "two"), ("two", "three")},
        )

    def test_read_pajek(self, tmp_path):
        G = nx.parse_pajek(self.data)
        # Read data from file
        fname = tmp_path / "test.pjk"
        with open(fname, "wb") as fh:
            fh.write(self.data.encode("UTF-8"))

        Gin = nx.read_pajek(fname)
        assert sorted(G.nodes()) == sorted(Gin.nodes())
        assert edges_equal(G.edges(), Gin.edges())
        assert self.G.graph == Gin.graph
        for n in G:
            assert G.nodes[n] == Gin.nodes[n]

    def test_write_pajek(self):
        import io

        G = nx.parse_pajek(self.data)
        fh = io.BytesIO()
        nx.write_pajek(G, fh)
        fh.seek(0)
        H = nx.read_pajek(fh)
        assert nodes_equal(list(G), list(H))
        assert edges_equal(list(G.edges()), list(H.edges()))
        # Graph name is left out for now, therefore it is not tested.
        # assert_equal(G.graph, H.graph)

    def test_ignored_attribute(self):
        import io

        G = nx.Graph()
        fh = io.BytesIO()
        G.add_node(1, int_attr=1)
        G.add_node(2, empty_attr="  ")
        G.add_edge(1, 2, int_attr=2)
        G.add_edge(2, 3, empty_attr="  ")

        import warnings

        with warnings.catch_warnings(record=True) as w:
            nx.write_pajek(G, fh)
            assert len(w) == 4

    def test_noname(self):
        # Make sure we can parse a line such as:  *network
        # Issue #952
        line = "*network\n"
        other_lines = self.data.split("\n")[1:]
        data = line + "\n".join(other_lines)
        G = nx.parse_pajek(data)

    def test_unicode(self):
        import io

        G = nx.Graph()
        name1 = chr(2344) + chr(123) + chr(6543)
        name2 = chr(5543) + chr(1543) + chr(324)
        G.add_edge(name1, "Radiohead", foo=name2)
        fh = io.BytesIO()
        nx.write_pajek(G, fh)
        fh.seek(0)
        H = nx.read_pajek(fh)
        assert nodes_equal(list(G), list(H))
        assert edges_equal(list(G.edges()), list(H.edges()))
        assert G.graph == H.graph
