"""
Tests for VF2 isomorphism algorithm.
"""

import importlib.resources
import os
import random
import struct

import networkx as nx
from networkx.algorithms import isomorphism as iso


class TestWikipediaExample:
    # Source: https://en.wikipedia.org/wiki/Graph_isomorphism

    # Nodes 'a', 'b', 'c' and 'd' form a column.
    # Nodes 'g', 'h', 'i' and 'j' form a column.
    g1edges = [
        ["a", "g"],
        ["a", "h"],
        ["a", "i"],
        ["b", "g"],
        ["b", "h"],
        ["b", "j"],
        ["c", "g"],
        ["c", "i"],
        ["c", "j"],
        ["d", "h"],
        ["d", "i"],
        ["d", "j"],
    ]

    # Nodes 1,2,3,4 form the clockwise corners of a large square.
    # Nodes 5,6,7,8 form the clockwise corners of a small square
    g2edges = [
        [1, 2],
        [2, 3],
        [3, 4],
        [4, 1],
        [5, 6],
        [6, 7],
        [7, 8],
        [8, 5],
        [1, 5],
        [2, 6],
        [3, 7],
        [4, 8],
    ]

    def test_graph(self):
        g1 = nx.Graph()
        g2 = nx.Graph()
        g1.add_edges_from(self.g1edges)
        g2.add_edges_from(self.g2edges)
        gm = iso.GraphMatcher(g1, g2)
        assert gm.is_isomorphic()
        # Just testing some cases
        assert gm.subgraph_is_monomorphic()

        mapping = sorted(gm.mapping.items())

    # this mapping is only one of the possibilities
    # so this test needs to be reconsidered
    #        isomap = [('a', 1), ('b', 6), ('c', 3), ('d', 8),
    #                  ('g', 2), ('h', 5), ('i', 4), ('j', 7)]
    #        assert_equal(mapping, isomap)

    def test_subgraph(self):
        g1 = nx.Graph()
        g2 = nx.Graph()
        g1.add_edges_from(self.g1edges)
        g2.add_edges_from(self.g2edges)
        g3 = g2.subgraph([1, 2, 3, 4])
        gm = iso.GraphMatcher(g1, g3)
        assert gm.subgraph_is_isomorphic()

    def test_subgraph_mono(self):
        g1 = nx.Graph()
        g2 = nx.Graph()
        g1.add_edges_from(self.g1edges)
        g2.add_edges_from([[1, 2], [2, 3], [3, 4]])
        gm = iso.GraphMatcher(g1, g2)
        assert gm.subgraph_is_monomorphic()


class TestVF2GraphDB:
    # https://web.archive.org/web/20090303210205/http://amalfi.dis.unina.it/graph/db/

    @staticmethod
    def create_graph(filename):
        """Creates a Graph instance from the filename."""

        # The file is assumed to be in the format from the VF2 graph database.
        # Each file is composed of 16-bit numbers (unsigned short int).
        # So we will want to read 2 bytes at a time.

        # We can read the number as follows:
        #   number = struct.unpack('<H', file.read(2))
        # This says, expect the data in little-endian encoding
        # as an unsigned short int and unpack 2 bytes from the file.

        fh = open(filename, mode="rb")

        # Grab the number of nodes.
        # Node numeration is 0-based, so the first node has index 0.
        nodes = struct.unpack("<H", fh.read(2))[0]

        graph = nx.Graph()
        for from_node in range(nodes):
            # Get the number of edges.
            edges = struct.unpack("<H", fh.read(2))[0]
            for edge in range(edges):
                # Get the terminal node.
                to_node = struct.unpack("<H", fh.read(2))[0]
                graph.add_edge(from_node, to_node)

        fh.close()
        return graph

    def test_graph(self):
        head = importlib.resources.files("networkx.algorithms.isomorphism.tests")
        g1 = self.create_graph(head / "iso_r01_s80.A99")
        g2 = self.create_graph(head / "iso_r01_s80.B99")
        gm = iso.GraphMatcher(g1, g2)
        assert gm.is_isomorphic()

    def test_subgraph(self):
        # A is the subgraph
        # B is the full graph
        head = importlib.resources.files("networkx.algorithms.isomorphism.tests")
        subgraph = self.create_graph(head / "si2_b06_m200.A99")
        graph = self.create_graph(head / "si2_b06_m200.B99")
        gm = iso.GraphMatcher(graph, subgraph)
        assert gm.subgraph_is_isomorphic()
        # Just testing some cases
        assert gm.subgraph_is_monomorphic()

    # There isn't a similar test implemented for subgraph monomorphism,
    # feel free to create one.


class TestAtlas:
    @classmethod
    def setup_class(cls):
        global atlas
        from networkx.generators import atlas

        cls.GAG = atlas.graph_atlas_g()

    def test_graph_atlas(self):
        # Atlas = nx.graph_atlas_g()[0:208] # 208, 6 nodes or less
        Atlas = self.GAG[0:100]
        alphabet = list(range(26))
        for graph in Atlas:
            nlist = list(graph)
            labels = alphabet[: len(nlist)]
            for s in range(10):
                random.shuffle(labels)
                d = dict(zip(nlist, labels))
                relabel = nx.relabel_nodes(graph, d)
                gm = iso.GraphMatcher(graph, relabel)
                assert gm.is_isomorphic()


def test_multiedge():
    # Simple test for multigraphs
    # Need something much more rigorous
    edges = [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 4),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 8),
        (8, 9),
        (9, 10),
        (10, 11),
        (10, 11),
        (11, 12),
        (11, 12),
        (12, 13),
        (12, 13),
        (13, 14),
        (13, 14),
        (14, 15),
        (14, 15),
        (15, 16),
        (15, 16),
        (16, 17),
        (16, 17),
        (17, 18),
        (17, 18),
        (18, 19),
        (18, 19),
        (19, 0),
        (19, 0),
    ]
    nodes = list(range(20))

    for g1 in [nx.MultiGraph(), nx.MultiDiGraph()]:
        g1.add_edges_from(edges)
        for _ in range(10):
            new_nodes = list(nodes)
            random.shuffle(new_nodes)
            d = dict(zip(nodes, new_nodes))
            g2 = nx.relabel_nodes(g1, d)
            if not g1.is_directed():
                gm = iso.GraphMatcher(g1, g2)
            else:
                gm = iso.DiGraphMatcher(g1, g2)
            assert gm.is_isomorphic()
            # Testing if monomorphism works in multigraphs
            assert gm.subgraph_is_monomorphic()


def test_selfloop():
    # Simple test for graphs with selfloops
    edges = [
        (0, 1),
        (0, 2),
        (1, 2),
        (1, 3),
        (2, 2),
        (2, 4),
        (3, 1),
        (3, 2),
        (4, 2),
        (4, 5),
        (5, 4),
    ]
    nodes = list(range(6))

    for g1 in [nx.Graph(), nx.DiGraph()]:
        g1.add_edges_from(edges)
        for _ in range(100):
            new_nodes = list(nodes)
            random.shuffle(new_nodes)
            d = dict(zip(nodes, new_nodes))
            g2 = nx.relabel_nodes(g1, d)
            if not g1.is_directed():
                gm = iso.GraphMatcher(g1, g2)
            else:
                gm = iso.DiGraphMatcher(g1, g2)
            assert gm.is_isomorphic()


def test_selfloop_mono():
    # Simple test for graphs with selfloops
    edges0 = [
        (0, 1),
        (0, 2),
        (1, 2),
        (1, 3),
        (2, 4),
        (3, 1),
        (3, 2),
        (4, 2),
        (4, 5),
        (5, 4),
    ]
    edges = edges0 + [(2, 2)]
    nodes = list(range(6))

    for g1 in [nx.Graph(), nx.DiGraph()]:
        g1.add_edges_from(edges)
        for _ in range(100):
            new_nodes = list(nodes)
            random.shuffle(new_nodes)
            d = dict(zip(nodes, new_nodes))
            g2 = nx.relabel_nodes(g1, d)
            g2.remove_edges_from(nx.selfloop_edges(g2))
            if not g1.is_directed():
                gm = iso.GraphMatcher(g2, g1)
            else:
                gm = iso.DiGraphMatcher(g2, g1)
            assert not gm.subgraph_is_monomorphic()


def test_isomorphism_iter1():
    # As described in:
    # http://groups.google.com/group/networkx-discuss/browse_thread/thread/2ff65c67f5e3b99f/d674544ebea359bb?fwc=1
    g1 = nx.DiGraph()
    g2 = nx.DiGraph()
    g3 = nx.DiGraph()
    g1.add_edge("A", "B")
    g1.add_edge("B", "C")
    g2.add_edge("Y", "Z")
    g3.add_edge("Z", "Y")
    gm12 = iso.DiGraphMatcher(g1, g2)
    gm13 = iso.DiGraphMatcher(g1, g3)
    x = list(gm12.subgraph_isomorphisms_iter())
    y = list(gm13.subgraph_isomorphisms_iter())
    assert {"A": "Y", "B": "Z"} in x
    assert {"B": "Y", "C": "Z"} in x
    assert {"A": "Z", "B": "Y"} in y
    assert {"B": "Z", "C": "Y"} in y
    assert len(x) == len(y)
    assert len(x) == 2


def test_monomorphism_iter1():
    g1 = nx.DiGraph()
    g2 = nx.DiGraph()
    g1.add_edge("A", "B")
    g1.add_edge("B", "C")
    g1.add_edge("C", "A")
    g2.add_edge("X", "Y")
    g2.add_edge("Y", "Z")
    gm12 = iso.DiGraphMatcher(g1, g2)
    x = list(gm12.subgraph_monomorphisms_iter())
    assert {"A": "X", "B": "Y", "C": "Z"} in x
    assert {"A": "Y", "B": "Z", "C": "X"} in x
    assert {"A": "Z", "B": "X", "C": "Y"} in x
    assert len(x) == 3
    gm21 = iso.DiGraphMatcher(g2, g1)
    # Check if StopIteration exception returns False
    assert not gm21.subgraph_is_monomorphic()


def test_isomorphism_iter2():
    # Path
    for L in range(2, 10):
        g1 = nx.path_graph(L)
        gm = iso.GraphMatcher(g1, g1)
        s = len(list(gm.isomorphisms_iter()))
        assert s == 2
    # Cycle
    for L in range(3, 10):
        g1 = nx.cycle_graph(L)
        gm = iso.GraphMatcher(g1, g1)
        s = len(list(gm.isomorphisms_iter()))
        assert s == 2 * L


def test_multiple():
    # Verify that we can use the graph matcher multiple times
    edges = [("A", "B"), ("B", "A"), ("B", "C")]
    for g1, g2 in [(nx.Graph(), nx.Graph()), (nx.DiGraph(), nx.DiGraph())]:
        g1.add_edges_from(edges)
        g2.add_edges_from(edges)
        g3 = nx.subgraph(g2, ["A", "B"])
        if not g1.is_directed():
            gmA = iso.GraphMatcher(g1, g2)
            gmB = iso.GraphMatcher(g1, g3)
        else:
            gmA = iso.DiGraphMatcher(g1, g2)
            gmB = iso.DiGraphMatcher(g1, g3)
        assert gmA.is_isomorphic()
        g2.remove_node("C")
        if not g1.is_directed():
            gmA = iso.GraphMatcher(g1, g2)
        else:
            gmA = iso.DiGraphMatcher(g1, g2)
        assert gmA.subgraph_is_isomorphic()
        assert gmB.subgraph_is_isomorphic()
        assert gmA.subgraph_is_monomorphic()
        assert gmB.subgraph_is_monomorphic()


#        for m in [gmB.mapping, gmB.mapping]:
#            assert_true(m['A'] == 'A')
#            assert_true(m['B'] == 'B')
#            assert_true('C' not in m)


def test_noncomparable_nodes():
    node1 = object()
    node2 = object()
    node3 = object()

    # Graph
    G = nx.path_graph([node1, node2, node3])
    gm = iso.GraphMatcher(G, G)
    assert gm.is_isomorphic()
    # Just testing some cases
    assert gm.subgraph_is_monomorphic()

    # DiGraph
    G = nx.path_graph([node1, node2, node3], create_using=nx.DiGraph)
    H = nx.path_graph([node3, node2, node1], create_using=nx.DiGraph)
    dgm = iso.DiGraphMatcher(G, H)
    assert dgm.is_isomorphic()
    # Just testing some cases
    assert gm.subgraph_is_monomorphic()


def test_monomorphism_edge_match():
    G = nx.DiGraph()
    G.add_node(1)
    G.add_node(2)
    G.add_edge(1, 2, label="A")
    G.add_edge(2, 1, label="B")
    G.add_edge(2, 2, label="C")

    SG = nx.DiGraph()
    SG.add_node(5)
    SG.add_node(6)
    SG.add_edge(5, 6, label="A")

    gm = iso.DiGraphMatcher(G, SG, edge_match=iso.categorical_edge_match("label", None))
    assert gm.subgraph_is_monomorphic()


def test_isomorphvf2pp_multidigraphs():
    g = nx.MultiDiGraph({0: [1, 1, 2, 2, 3], 1: [2, 3, 3], 2: [3]})
    h = nx.MultiDiGraph({0: [1, 1, 2, 2, 3], 1: [2, 3, 3], 3: [2]})
    assert not (nx.vf2pp_is_isomorphic(g, h))
