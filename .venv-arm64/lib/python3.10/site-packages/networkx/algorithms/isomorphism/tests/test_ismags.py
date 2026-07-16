"""
Tests for ISMAGS isomorphism algorithm.
"""

import pytest

import networkx as nx
from networkx.algorithms import isomorphism as iso


def _matches_to_sets(matches):
    """
    Helper function to facilitate comparing collections of dictionaries in
    which order does not matter.
    """
    return {frozenset(m.items()) for m in matches}


class TestSelfIsomorphism:
    data = [
        (
            [
                (0, {"name": "a"}),
                (1, {"name": "a"}),
                (2, {"name": "b"}),
                (3, {"name": "b"}),
                (4, {"name": "a"}),
                (5, {"name": "a"}),
            ],
            [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)],
        ),
        (range(1, 5), [(1, 2), (2, 4), (4, 3), (3, 1)]),
        (
            [],
            [
                (0, 1),
                (1, 2),
                (2, 3),
                (3, 4),
                (4, 5),
                (5, 0),
                (0, 6),
                (6, 7),
                (2, 8),
                (8, 9),
                (4, 10),
                (10, 11),
            ],
        ),
        ([], [(0, 1), (1, 2), (1, 4), (2, 3), (3, 5), (3, 6)]),
    ]

    def test_self_isomorphism(self):
        """
        For some small, symmetric graphs, make sure that 1) they are isomorphic
        to themselves, and 2) that only the identity mapping is found.
        """
        for node_data, edge_data in self.data:
            graph = nx.Graph()
            graph.add_nodes_from(node_data)
            graph.add_edges_from(edge_data)

            ismags = iso.ISMAGS(
                graph, graph, node_match=iso.categorical_node_match("name", None)
            )
            assert ismags.is_isomorphic()
            assert ismags.subgraph_is_isomorphic()
            assert list(ismags.subgraph_isomorphisms_iter(symmetry=True)) == [
                {n: n for n in graph.nodes}
            ]

    def test_edgecase_self_isomorphism(self):
        """
        This edgecase is one of the cases in which it is hard to find all
        symmetry elements.
        """
        graph = nx.Graph()
        nx.add_path(graph, range(5))
        graph.add_edges_from([(2, 5), (5, 6)])

        ismags = iso.ISMAGS(graph, graph)
        ismags_answer = list(ismags.find_isomorphisms(True))
        assert ismags_answer == [{n: n for n in graph.nodes}]

        graph = nx.relabel_nodes(graph, {0: 0, 1: 1, 2: 2, 3: 3, 4: 6, 5: 4, 6: 5})
        ismags = iso.ISMAGS(graph, graph)
        ismags_answer = list(ismags.find_isomorphisms(True))
        assert ismags_answer == [{n: n for n in graph.nodes}]

    def test_directed_self_isomorphism(self):
        """
        For some small, directed, symmetric graphs, make sure that 1) they are
        isomorphic to themselves, and 2) that only the identity mapping is
        found.
        """
        for node_data, edge_data in self.data:
            graph = nx.Graph()
            graph.add_nodes_from(node_data)
            graph.add_edges_from(edge_data)

            ismags = iso.ISMAGS(
                graph, graph, node_match=iso.categorical_node_match("name", None)
            )
            assert ismags.is_isomorphic()
            assert ismags.subgraph_is_isomorphic()
            assert list(ismags.subgraph_isomorphisms_iter(symmetry=True)) == [
                {n: n for n in graph.nodes}
            ]


class TestSubgraphIsomorphism:
    def test_isomorphism(self):
        g1 = nx.Graph()
        nx.add_cycle(g1, range(4))

        g2 = nx.Graph()
        nx.add_cycle(g2, range(4))
        g2.add_edges_from(list(zip(g2, range(4, 8))))
        ismags = iso.ISMAGS(g2, g1)
        assert list(ismags.subgraph_isomorphisms_iter(symmetry=True)) == [
            {n: n for n in g1.nodes}
        ]

    def test_isomorphism2(self):
        g1 = nx.Graph()
        nx.add_path(g1, range(3))

        g2 = g1.copy()
        g2.add_edge(1, 3)

        ismags = iso.ISMAGS(g2, g1)
        matches = ismags.subgraph_isomorphisms_iter(symmetry=True)
        expected_symmetric = [
            {0: 0, 1: 1, 2: 2},
            {0: 0, 1: 1, 3: 2},
            {2: 0, 1: 1, 3: 2},
        ]
        assert _matches_to_sets(matches) == _matches_to_sets(expected_symmetric)

        matches = ismags.subgraph_isomorphisms_iter(symmetry=False)
        expected_asymmetric = [
            {0: 2, 1: 1, 2: 0},
            {0: 2, 1: 1, 3: 0},
            {2: 2, 1: 1, 3: 0},
        ]
        assert _matches_to_sets(matches) == _matches_to_sets(
            expected_symmetric + expected_asymmetric
        )

    def test_labeled_nodes(self):
        g1 = nx.Graph()
        nx.add_cycle(g1, range(3))
        g1.nodes[1]["attr"] = True

        g2 = g1.copy()
        g2.add_edge(1, 3)
        ismags = iso.ISMAGS(g2, g1, node_match=lambda x, y: x == y)
        matches = ismags.subgraph_isomorphisms_iter(symmetry=True)
        expected_symmetric = [{0: 0, 1: 1, 2: 2}]
        assert _matches_to_sets(matches) == _matches_to_sets(expected_symmetric)

        matches = ismags.subgraph_isomorphisms_iter(symmetry=False)
        expected_asymmetric = [{0: 2, 1: 1, 2: 0}]
        assert _matches_to_sets(matches) == _matches_to_sets(
            expected_symmetric + expected_asymmetric
        )

    def test_labeled_edges(self):
        g1 = nx.Graph()
        nx.add_cycle(g1, range(3))
        g1.edges[1, 2]["attr"] = True

        g2 = g1.copy()
        g2.add_edge(1, 3)
        ismags = iso.ISMAGS(g2, g1, edge_match=lambda x, y: x == y)
        matches = ismags.subgraph_isomorphisms_iter(symmetry=True)
        expected_symmetric = [{0: 0, 1: 1, 2: 2}]
        assert _matches_to_sets(matches) == _matches_to_sets(expected_symmetric)

        matches = ismags.subgraph_isomorphisms_iter(symmetry=False)
        expected_asymmetric = [{1: 2, 0: 0, 2: 1}]
        assert _matches_to_sets(matches) == _matches_to_sets(
            expected_symmetric + expected_asymmetric
        )


class TestWikipediaExample:
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
        gm = iso.ISMAGS(g1, g2)
        assert gm.is_isomorphic()


class TestLargestCommonSubgraph:
    def test_mcis(self):
        # Example graphs from DOI: 10.1002/spe.588
        graph1 = nx.Graph()
        graph1.add_edges_from([(1, 2), (2, 3), (2, 4), (3, 4), (4, 5)])
        graph1.nodes[1]["color"] = 0

        graph2 = nx.Graph()
        graph2.add_edges_from(
            [(1, 2), (2, 3), (2, 4), (3, 4), (3, 5), (5, 6), (5, 7), (6, 7)]
        )
        graph2.nodes[1]["color"] = 1
        graph2.nodes[6]["color"] = 2
        graph2.nodes[7]["color"] = 2

        ismags = iso.ISMAGS(
            graph1, graph2, node_match=iso.categorical_node_match("color", None)
        )
        assert list(ismags.subgraph_isomorphisms_iter(True)) == []
        assert list(ismags.subgraph_isomorphisms_iter(False)) == []
        found_mcis = _matches_to_sets(ismags.largest_common_subgraph())
        expected = _matches_to_sets(
            [{2: 2, 3: 4, 4: 3, 5: 5}, {2: 4, 3: 2, 4: 3, 5: 5}]
        )
        assert expected == found_mcis

        ismags = iso.ISMAGS(
            graph2, graph1, node_match=iso.categorical_node_match("color", None)
        )
        assert list(ismags.subgraph_isomorphisms_iter(True)) == []
        assert list(ismags.subgraph_isomorphisms_iter(False)) == []
        found_mcis = _matches_to_sets(ismags.largest_common_subgraph())
        # Same answer, but reversed.
        expected = _matches_to_sets(
            [{2: 2, 3: 4, 4: 3, 5: 5}, {4: 2, 2: 3, 3: 4, 5: 5}]
        )
        assert expected == found_mcis

    def test_symmetry_mcis(self):
        graph1 = nx.Graph()
        nx.add_path(graph1, range(4))

        graph2 = nx.Graph()
        nx.add_path(graph2, range(3))
        graph2.add_edge(1, 3)

        # Only the symmetry of graph2 is taken into account here.
        ismags1 = iso.ISMAGS(
            graph1, graph2, node_match=iso.categorical_node_match("color", None)
        )
        assert list(ismags1.subgraph_isomorphisms_iter(True)) == []
        found_mcis = _matches_to_sets(ismags1.largest_common_subgraph())
        expected = _matches_to_sets([{0: 0, 1: 1, 2: 2}, {1: 0, 3: 2, 2: 1}])
        assert expected == found_mcis

        # Only the symmetry of graph1 is taken into account here.
        ismags2 = iso.ISMAGS(
            graph2, graph1, node_match=iso.categorical_node_match("color", None)
        )
        assert list(ismags2.subgraph_isomorphisms_iter(True)) == []
        found_mcis = _matches_to_sets(ismags2.largest_common_subgraph())
        expected = _matches_to_sets(
            [
                {3: 2, 0: 0, 1: 1},
                {2: 0, 0: 2, 1: 1},
                {3: 0, 0: 2, 1: 1},
                {3: 0, 1: 1, 2: 2},
                {0: 0, 1: 1, 2: 2},
                {2: 0, 3: 2, 1: 1},
            ]
        )

        assert expected == found_mcis

        found_mcis1 = _matches_to_sets(ismags1.largest_common_subgraph(False))
        found_mcis2 = ismags2.largest_common_subgraph(False)
        found_mcis2 = [{v: k for k, v in d.items()} for d in found_mcis2]
        found_mcis2 = _matches_to_sets(found_mcis2)

        expected = _matches_to_sets(
            [
                {3: 2, 1: 3, 2: 1},
                {2: 0, 0: 2, 1: 1},
                {1: 2, 3: 3, 2: 1},
                {3: 0, 1: 3, 2: 1},
                {0: 2, 2: 3, 1: 1},
                {3: 0, 1: 2, 2: 1},
                {2: 0, 0: 3, 1: 1},
                {0: 0, 2: 3, 1: 1},
                {1: 0, 3: 3, 2: 1},
                {1: 0, 3: 2, 2: 1},
                {0: 3, 1: 1, 2: 2},
                {0: 0, 1: 1, 2: 2},
            ]
        )
        assert expected == found_mcis1
        assert expected == found_mcis2
