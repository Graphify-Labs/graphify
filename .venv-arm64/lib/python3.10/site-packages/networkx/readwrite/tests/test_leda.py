import io

import networkx as nx


class TestLEDA:
    def test_parse_leda(self):
        data = """#header section         \nLEDA.GRAPH \nstring\nint\n-1\n#nodes section\n5 \n|{v1}| \n|{v2}| \n|{v3}| \n|{v4}| \n|{v5}| \n\n#edges section\n7 \n1 2 0 |{4}| \n1 3 0 |{3}| \n2 3 0 |{2}| \n3 4 0 |{3}| \n3 5 0 |{7}| \n4 5 0 |{6}| \n5 1 0 |{foo}|"""
        G = nx.parse_leda(data)
        G = nx.parse_leda(data.split("\n"))
        assert sorted(G.nodes()) == ["v1", "v2", "v3", "v4", "v5"]
        assert sorted(G.edges(data=True)) == [
            ("v1", "v2", {"label": "4"}),
            ("v1", "v3", {"label": "3"}),
            ("v2", "v3", {"label": "2"}),
            ("v3", "v4", {"label": "3"}),
            ("v3", "v5", {"label": "7"}),
            ("v4", "v5", {"label": "6"}),
            ("v5", "v1", {"label": "foo"}),
        ]

    def test_read_LEDA(self):
        fh = io.BytesIO()
        data = """#header section         \nLEDA.GRAPH \nstring\nint\n-1\n#nodes section\n5 \n|{v1}| \n|{v2}| \n|{v3}| \n|{v4}| \n|{v5}| \n\n#edges section\n7 \n1 2 0 |{4}| \n1 3 0 |{3}| \n2 3 0 |{2}| \n3 4 0 |{3}| \n3 5 0 |{7}| \n4 5 0 |{6}| \n5 1 0 |{foo}|"""
        G = nx.parse_leda(data)
        fh.write(data.encode("UTF-8"))
        fh.seek(0)
        Gin = nx.read_leda(fh)
        assert sorted(G.nodes()) == sorted(Gin.nodes())
        assert sorted(G.edges()) == sorted(Gin.edges())
