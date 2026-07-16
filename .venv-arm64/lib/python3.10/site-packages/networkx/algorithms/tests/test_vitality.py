import networkx as nx


class TestClosenessVitality:
    def test_unweighted(self):
        G = nx.cycle_graph(3)
        vitality = nx.closeness_vitality(G)
        assert vitality == {0: 2, 1: 2, 2: 2}

    def test_weighted(self):
        G = nx.Graph()
        nx.add_cycle(G, [0, 1, 2], weight=2)
        vitality = nx.closeness_vitality(G, weight="weight")
        assert vitality == {0: 4, 1: 4, 2: 4}

    def test_unweighted_digraph(self):
        G = nx.DiGraph(nx.cycle_graph(3))
        vitality = nx.closeness_vitality(G)
        assert vitality == {0: 4, 1: 4, 2: 4}

    def test_weighted_digraph(self):
        G = nx.DiGraph()
        nx.add_cycle(G, [0, 1, 2], weight=2)
        nx.add_cycle(G, [2, 1, 0], weight=2)
        vitality = nx.closeness_vitality(G, weight="weight")
        assert vitality == {0: 8, 1: 8, 2: 8}

    def test_weighted_multidigraph(self):
        G = nx.MultiDiGraph()
        nx.add_cycle(G, [0, 1, 2], weight=2)
        nx.add_cycle(G, [2, 1, 0], weight=2)
        vitality = nx.closeness_vitality(G, weight="weight")
        assert vitality == {0: 8, 1: 8, 2: 8}

    def test_disconnecting_graph(self):
        """Tests that the closeness vitality of a node whose removal
        disconnects the graph is negative infinity.

        """
        G = nx.path_graph(3)
        assert nx.closeness_vitality(G, node=1) == -float("inf")
