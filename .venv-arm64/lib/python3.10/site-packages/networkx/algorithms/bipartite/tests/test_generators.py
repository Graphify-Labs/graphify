import numbers

import pytest

import networkx as nx

from ..generators import (
    alternating_havel_hakimi_graph,
    complete_bipartite_graph,
    configuration_model,
    gnmk_random_graph,
    havel_hakimi_graph,
    preferential_attachment_graph,
    random_graph,
    reverse_havel_hakimi_graph,
)

"""
Generators - Bipartite
----------------------
"""


class TestGeneratorsBipartite:
    def test_complete_bipartite_graph(self):
        G = complete_bipartite_graph(0, 0)
        assert nx.is_isomorphic(G, nx.null_graph())

        for i in [1, 5]:
            G = complete_bipartite_graph(i, 0)
            assert nx.is_isomorphic(G, nx.empty_graph(i))
            G = complete_bipartite_graph(0, i)
            assert nx.is_isomorphic(G, nx.empty_graph(i))

        G = complete_bipartite_graph(2, 2)
        assert nx.is_isomorphic(G, nx.cycle_graph(4))

        G = complete_bipartite_graph(1, 5)
        assert nx.is_isomorphic(G, nx.star_graph(5))

        G = complete_bipartite_graph(5, 1)
        assert nx.is_isomorphic(G, nx.star_graph(5))

        # complete_bipartite_graph(m1,m2) is a connected graph with
        # m1+m2 nodes and  m1*m2 edges
        for m1, m2 in [(5, 11), (7, 3)]:
            G = complete_bipartite_graph(m1, m2)
            assert nx.number_of_nodes(G) == m1 + m2
            assert nx.number_of_edges(G) == m1 * m2

        with pytest.raises(nx.NetworkXError):
            complete_bipartite_graph(7, 3, create_using=nx.DiGraph)
        with pytest.raises(nx.NetworkXError):
            complete_bipartite_graph(7, 3, create_using=nx.MultiDiGraph)

        mG = complete_bipartite_graph(7, 3, create_using=nx.MultiGraph)
        assert mG.is_multigraph()
        assert sorted(mG.edges()) == sorted(G.edges())

        mG = complete_bipartite_graph(7, 3, create_using=nx.MultiGraph)
        assert mG.is_multigraph()
        assert sorted(mG.edges()) == sorted(G.edges())

        mG = complete_bipartite_graph(7, 3)  # default to Graph
        assert sorted(mG.edges()) == sorted(G.edges())
        assert not mG.is_multigraph()
        assert not mG.is_directed()

        # specify nodes rather than number of nodes
        for n1, n2 in [([1, 2], "ab"), (3, 2), (3, "ab"), ("ab", 3)]:
            G = complete_bipartite_graph(n1, n2)
            if isinstance(n1, numbers.Integral):
                if isinstance(n2, numbers.Integral):
                    n2 = range(n1, n1 + n2)
                n1 = range(n1)
            elif isinstance(n2, numbers.Integral):
                n2 = range(n2)
            edges = {(u, v) for u in n1 for v in n2}
            assert edges == set(G.edges)
            assert G.size() == len(edges)

        # raise when node sets are not distinct
        for n1, n2 in [([1, 2], 3), (3, [1, 2]), ("abc", "bcd")]:
            pytest.raises(nx.NetworkXError, complete_bipartite_graph, n1, n2)

    def test_configuration_model(self):
        aseq = []
        bseq = []
        G = configuration_model(aseq, bseq)
        assert len(G) == 0

        aseq = [0, 0]
        bseq = [0, 0]
        G = configuration_model(aseq, bseq)
        assert len(G) == 4
        assert G.number_of_edges() == 0

        aseq = [3, 3, 3, 3]
        bseq = [2, 2, 2, 2, 2]
        pytest.raises(nx.NetworkXError, configuration_model, aseq, bseq)

        aseq = [3, 3, 3, 3]
        bseq = [2, 2, 2, 2, 2, 2]
        G = configuration_model(aseq, bseq)
        assert sorted(d for n, d in G.degree()) == [2, 2, 2, 2, 2, 2, 3, 3, 3, 3]

        aseq = [2, 2, 2, 2, 2, 2]
        bseq = [3, 3, 3, 3]
        G = configuration_model(aseq, bseq)
        assert sorted(d for n, d in G.degree()) == [2, 2, 2, 2, 2, 2, 3, 3, 3, 3]

        aseq = [2, 2, 2, 1, 1, 1]
        bseq = [3, 3, 3]
        G = configuration_model(aseq, bseq)
        assert G.is_multigraph()
        assert not G.is_directed()
        assert sorted(d for n, d in G.degree()) == [1, 1, 1, 2, 2, 2, 3, 3, 3]

        GU = nx.projected_graph(nx.Graph(G), range(len(aseq)))
        assert GU.number_of_nodes() == 6

        GD = nx.projected_graph(nx.Graph(G), range(len(aseq), len(aseq) + len(bseq)))
        assert GD.number_of_nodes() == 3

        G = reverse_havel_hakimi_graph(aseq, bseq, create_using=nx.Graph)
        assert not G.is_multigraph()
        assert not G.is_directed()

        pytest.raises(
            nx.NetworkXError, configuration_model, aseq, bseq, create_using=nx.DiGraph()
        )
        pytest.raises(
            nx.NetworkXError, configuration_model, aseq, bseq, create_using=nx.DiGraph
        )
        pytest.raises(
            nx.NetworkXError,
            configuration_model,
            aseq,
            bseq,
            create_using=nx.MultiDiGraph,
        )

    def test_havel_hakimi_graph(self):
        aseq = []
        bseq = []
        G = havel_hakimi_graph(aseq, bseq)
        assert len(G) == 0

        aseq = [0, 0]
        bseq = [0, 0]
        G = havel_hakimi_graph(aseq, bseq)
        assert len(G) == 4
        assert G.number_of_edges() == 0

        aseq = [3, 3, 3, 3]
        bseq = [2, 2, 2, 2, 2]
        pytest.raises(nx.NetworkXError, havel_hakimi_graph, aseq, bseq)

        bseq = [2, 2, 2, 2, 2, 2]
        G = havel_hakimi_graph(aseq, bseq)
        assert sorted(d for n, d in G.degree()) == [2, 2, 2, 2, 2, 2, 3, 3, 3, 3]

        aseq = [2, 2, 2, 2, 2, 2]
        bseq = [3, 3, 3, 3]
        G = havel_hakimi_graph(aseq, bseq)
        assert G.is_multigraph()
        assert not G.is_directed()
        assert sorted(d for n, d in G.degree()) == [2, 2, 2, 2, 2, 2, 3, 3, 3, 3]

        GU = nx.projected_graph(nx.Graph(G), range(len(aseq)))
        assert GU.number_of_nodes() == 6

        GD = nx.projected_graph(nx.Graph(G), range(len(aseq), len(aseq) + len(bseq)))
        assert GD.number_of_nodes() == 4

        G = reverse_havel_hakimi_graph(aseq, bseq, create_using=nx.Graph)
        assert not G.is_multigraph()
        assert not G.is_directed()

        pytest.raises(
            nx.NetworkXError, havel_hakimi_graph, aseq, bseq, create_using=nx.DiGraph
        )
        pytest.raises(
            nx.NetworkXError, havel_hakimi_graph, aseq, bseq, create_using=nx.DiGraph
        )
        pytest.raises(
            nx.NetworkXError,
            havel_hakimi_graph,
            aseq,
            bseq,
            create_using=nx.MultiDiGraph,
        )

    def test_reverse_havel_hakimi_graph(self):
        aseq = []
        bseq = []
        G = reverse_havel_hakimi_graph(aseq, bseq)
        assert len(G) == 0

        aseq = [0, 0]
        bseq = [0, 0]
        G = reverse_havel_hakimi_graph(aseq, bseq)
        assert len(G) == 4
        assert G.number_of_edges() == 0

        aseq = [3, 3, 3, 3]
        bseq = [2, 2, 2, 2, 2]
        pytest.raises(nx.NetworkXError, reverse_havel_hakimi_graph, aseq, bseq)

        bseq = [2, 2, 2, 2, 2, 2]
        G = reverse_havel_hakimi_graph(aseq, bseq)
        assert sorted(d for n, d in G.degree()) == [2, 2, 2, 2, 2, 2, 3, 3, 3, 3]

        aseq = [2, 2, 2, 2, 2, 2]
        bseq = [3, 3, 3, 3]
        G = reverse_havel_hakimi_graph(aseq, bseq)
        assert sorted(d for n, d in G.degree()) == [2, 2, 2, 2, 2, 2, 3, 3, 3, 3]

        aseq = [2, 2, 2, 1, 1, 1]
        bseq = [3, 3, 3]
        G = reverse_havel_hakimi_graph(aseq, bseq)
        assert G.is_multigraph()
        assert not G.is_directed()
        assert sorted(d for n, d in G.degree()) == [1, 1, 1, 2, 2, 2, 3, 3, 3]

        GU = nx.projected_graph(nx.Graph(G), range(len(aseq)))
        assert GU.number_of_nodes() == 6

        GD = nx.projected_graph(nx.Graph(G), range(len(aseq), len(aseq) + len(bseq)))
        assert GD.number_of_nodes() == 3

        G = reverse_havel_hakimi_graph(aseq, bseq, create_using=nx.Graph)
        assert not G.is_multigraph()
        assert not G.is_directed()

        pytest.raises(
            nx.NetworkXError,
            reverse_havel_hakimi_graph,
            aseq,
            bseq,
            create_using=nx.DiGraph,
        )
        pytest.raises(
            nx.NetworkXError,
            reverse_havel_hakimi_graph,
            aseq,
            bseq,
            create_using=nx.DiGraph,
        )
        pytest.raises(
            nx.NetworkXError,
            reverse_havel_hakimi_graph,
            aseq,
            bseq,
            create_using=nx.MultiDiGraph,
        )

    def test_alternating_havel_hakimi_graph(self):
        aseq = []
        bseq = []
        G = alternating_havel_hakimi_graph(aseq, bseq)
        assert len(G) == 0

        aseq = [0, 0]
        bseq = [0, 0]
        G = alternating_havel_hakimi_graph(aseq, bseq)
        assert len(G) == 4
        assert G.number_of_edges() == 0

        aseq = [3, 3, 3, 3]
        bseq = [2, 2, 2, 2, 2]
        pytest.raises(nx.NetworkXError, alternating_havel_hakimi_graph, aseq, bseq)

        bseq = [2, 2, 2, 2, 2, 2]
        G = alternating_havel_hakimi_graph(aseq, bseq)
        assert sorted(d for n, d in G.degree()) == [2, 2, 2, 2, 2, 2, 3, 3, 3, 3]

        aseq = [2, 2, 2, 2, 2, 2]
        bseq = [3, 3, 3, 3]
        G = alternating_havel_hakimi_graph(aseq, bseq)
        assert sorted(d for n, d in G.degree()) == [2, 2, 2, 2, 2, 2, 3, 3, 3, 3]

        aseq = [2, 2, 2, 1, 1, 1]
        bseq = [3, 3, 3]
        G = alternating_havel_hakimi_graph(aseq, bseq)
        assert G.is_multigraph()
        assert not G.is_directed()
        assert sorted(d for n, d in G.degree()) == [1, 1, 1, 2, 2, 2, 3, 3, 3]

        GU = nx.projected_graph(nx.Graph(G), range(len(aseq)))
        assert GU.number_of_nodes() == 6

        GD = nx.projected_graph(nx.Graph(G), range(len(aseq), len(aseq) + len(bseq)))
        assert GD.number_of_nodes() == 3

        G = reverse_havel_hakimi_graph(aseq, bseq, create_using=nx.Graph)
        assert not G.is_multigraph()
        assert not G.is_directed()

        pytest.raises(
            nx.NetworkXError,
            alternating_havel_hakimi_graph,
            aseq,
            bseq,
            create_using=nx.DiGraph,
        )
        pytest.raises(
            nx.NetworkXError,
            alternating_havel_hakimi_graph,
            aseq,
            bseq,
            create_using=nx.DiGraph,
        )
        pytest.raises(
            nx.NetworkXError,
            alternating_havel_hakimi_graph,
            aseq,
            bseq,
            create_using=nx.MultiDiGraph,
        )

    def test_preferential_attachment(self):
        aseq = [3, 2, 1, 1]
        G = preferential_attachment_graph(aseq, 0.5)
        assert G.is_multigraph()
        assert not G.is_directed()

        G = preferential_attachment_graph(aseq, 0.5, create_using=nx.Graph)
        assert not G.is_multigraph()
        assert not G.is_directed()

        pytest.raises(
            nx.NetworkXError,
            preferential_attachment_graph,
            aseq,
            0.5,
            create_using=nx.DiGraph(),
        )
        pytest.raises(
            nx.NetworkXError,
            preferential_attachment_graph,
            aseq,
            0.5,
            create_using=nx.DiGraph(),
        )
        pytest.raises(
            nx.NetworkXError,
            preferential_attachment_graph,
            aseq,
            0.5,
            create_using=nx.DiGraph(),
        )

    def test_random_graph(self):
        n = 10
        m = 20
        G = random_graph(n, m, 0.9)
        assert len(G) == 30
        assert nx.is_bipartite(G)
        X, Y = nx.algorithms.bipartite.sets(G)
        assert set(range(n)) == X
        assert set(range(n, n + m)) == Y

    def test_random_digraph(self):
        n = 10
        m = 20
        G = random_graph(n, m, 0.9, directed=True)
        assert len(G) == 30
        assert nx.is_bipartite(G)
        X, Y = nx.algorithms.bipartite.sets(G)
        assert set(range(n)) == X
        assert set(range(n, n + m)) == Y

    def test_gnmk_random_graph(self):
        n = 10
        m = 20
        edges = 100
        # set seed because sometimes it is not connected
        # which raises an error in bipartite.sets(G) below.
        G = gnmk_random_graph(n, m, edges, seed=1234)
        assert len(G) == n + m
        assert nx.is_bipartite(G)
        X, Y = nx.algorithms.bipartite.sets(G)
        # print(X)
        assert set(range(n)) == X
        assert set(range(n, n + m)) == Y
        assert edges == len(list(G.edges()))

    def test_gnmk_random_graph_complete(self):
        n = 10
        m = 20
        edges = 200
        G = gnmk_random_graph(n, m, edges)
        assert len(G) == n + m
        assert nx.is_bipartite(G)
        X, Y = nx.algorithms.bipartite.sets(G)
        # print(X)
        assert set(range(n)) == X
        assert set(range(n, n + m)) == Y
        assert edges == len(list(G.edges()))

    @pytest.mark.parametrize("n", (4, range(4), {0, 1, 2, 3}))
    @pytest.mark.parametrize("m", (range(4, 7), {4, 5, 6}))
    def test_complete_bipartite_graph_str(self, n, m):
        """Ensure G.name is consistent for all inputs accepted by nodes_or_number.
        See gh-7396"""
        G = nx.complete_bipartite_graph(n, m)
        ans = "Graph named 'complete_bipartite_graph(4, 3)' with 7 nodes and 12 edges"
        assert str(G) == ans
