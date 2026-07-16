from itertools import groupby

import pytest

import networkx as nx
from networkx import graph_atlas, graph_atlas_g
from networkx.generators.atlas import NUM_GRAPHS
from networkx.utils import edges_equal, nodes_equal, pairwise


class TestAtlasGraph:
    """Unit tests for the :func:`~networkx.graph_atlas` function."""

    def test_index_too_small(self):
        with pytest.raises(ValueError):
            graph_atlas(-1)

    def test_index_too_large(self):
        with pytest.raises(ValueError):
            graph_atlas(NUM_GRAPHS)

    def test_graph(self):
        G = graph_atlas(6)
        assert nodes_equal(G.nodes(), range(3))
        assert edges_equal(G.edges(), [(0, 1), (0, 2)])


class TestAtlasGraphG:
    """Unit tests for the :func:`~networkx.graph_atlas_g` function."""

    @classmethod
    def setup_class(cls):
        cls.GAG = graph_atlas_g()

    def test_sizes(self):
        G = self.GAG[0]
        assert G.number_of_nodes() == 0
        assert G.number_of_edges() == 0

        G = self.GAG[7]
        assert G.number_of_nodes() == 3
        assert G.number_of_edges() == 3

    def test_names(self):
        for i, G in enumerate(self.GAG):
            assert int(G.name[1:]) == i

    def test_nondecreasing_nodes(self):
        # check for nondecreasing number of nodes
        for n1, n2 in pairwise(map(len, self.GAG)):
            assert n2 <= n1 + 1

    def test_nondecreasing_edges(self):
        # check for nondecreasing number of edges (for fixed number of
        # nodes)
        for n, group in groupby(self.GAG, key=nx.number_of_nodes):
            for m1, m2 in pairwise(map(nx.number_of_edges, group)):
                assert m2 <= m1 + 1

    def test_nondecreasing_degree_sequence(self):
        # Check for lexicographically nondecreasing degree sequences
        # (for fixed number of nodes and edges).
        #
        # There are three exceptions to this rule in the order given in
        # the "Atlas of Graphs" book, so we need to manually exclude
        # those.
        exceptions = [("G55", "G56"), ("G1007", "G1008"), ("G1012", "G1013")]
        for n, group in groupby(self.GAG, key=nx.number_of_nodes):
            for m, group in groupby(group, key=nx.number_of_edges):
                for G1, G2 in pairwise(group):
                    if (G1.name, G2.name) in exceptions:
                        continue
                    d1 = sorted(d for v, d in G1.degree())
                    d2 = sorted(d for v, d in G2.degree())
                    assert d1 <= d2
