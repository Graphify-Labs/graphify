"""Unit tests for the :mod:`networkx.algorithms.community.centrality`
module.

"""

from operator import itemgetter

import networkx as nx


def set_of_sets(iterable):
    return set(map(frozenset, iterable))


def validate_communities(result, expected):
    assert set_of_sets(result) == set_of_sets(expected)


def validate_possible_communities(result, *expected):
    assert any(set_of_sets(result) == set_of_sets(p) for p in expected)


class TestGirvanNewman:
    """Unit tests for the
    :func:`networkx.algorithms.community.centrality.girvan_newman`
    function.

    """

    def test_no_edges(self):
        G = nx.empty_graph(3)
        communities = list(nx.community.girvan_newman(G))
        assert len(communities) == 1
        validate_communities(communities[0], [{0}, {1}, {2}])

    def test_undirected(self):
        # Start with the graph .-.-.-.
        G = nx.path_graph(4)
        communities = list(nx.community.girvan_newman(G))
        assert len(communities) == 3
        # After one removal, we get the graph .-. .-.
        validate_communities(communities[0], [{0, 1}, {2, 3}])
        # After the next, we get the graph .-. . ., but there are two
        # symmetric possible versions.
        validate_possible_communities(
            communities[1], [{0}, {1}, {2, 3}], [{0, 1}, {2}, {3}]
        )
        # After the last removal, we always get the empty graph.
        validate_communities(communities[2], [{0}, {1}, {2}, {3}])

    def test_directed(self):
        G = nx.DiGraph(nx.path_graph(4))
        communities = list(nx.community.girvan_newman(G))
        assert len(communities) == 3
        validate_communities(communities[0], [{0, 1}, {2, 3}])
        validate_possible_communities(
            communities[1], [{0}, {1}, {2, 3}], [{0, 1}, {2}, {3}]
        )
        validate_communities(communities[2], [{0}, {1}, {2}, {3}])

    def test_selfloops(self):
        G = nx.path_graph(4)
        G.add_edge(0, 0)
        G.add_edge(2, 2)
        communities = list(nx.community.girvan_newman(G))
        assert len(communities) == 3
        validate_communities(communities[0], [{0, 1}, {2, 3}])
        validate_possible_communities(
            communities[1], [{0}, {1}, {2, 3}], [{0, 1}, {2}, {3}]
        )
        validate_communities(communities[2], [{0}, {1}, {2}, {3}])

    def test_most_valuable_edge(self):
        G = nx.Graph()
        G.add_weighted_edges_from([(0, 1, 3), (1, 2, 2), (2, 3, 1)])
        # Let the most valuable edge be the one with the highest weight.

        def heaviest(G):
            return max(G.edges(data="weight"), key=itemgetter(2))[:2]

        communities = list(nx.community.girvan_newman(G, heaviest))
        assert len(communities) == 3
        validate_communities(communities[0], [{0}, {1, 2, 3}])
        validate_communities(communities[1], [{0}, {1}, {2, 3}])
        validate_communities(communities[2], [{0}, {1}, {2}, {3}])
