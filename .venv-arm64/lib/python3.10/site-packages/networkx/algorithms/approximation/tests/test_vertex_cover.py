import networkx as nx
from networkx.algorithms.approximation import min_weighted_vertex_cover


def is_cover(G, node_cover):
    return all({u, v} & node_cover for u, v in G.edges())


class TestMWVC:
    """Unit tests for the approximate minimum weighted vertex cover
    function,
    :func:`~networkx.algorithms.approximation.vertex_cover.min_weighted_vertex_cover`.

    """

    def test_unweighted_directed(self):
        # Create a star graph in which half the nodes are directed in
        # and half are directed out.
        G = nx.DiGraph()
        G.add_edges_from((0, v) for v in range(1, 26))
        G.add_edges_from((v, 0) for v in range(26, 51))
        cover = min_weighted_vertex_cover(G)
        assert 1 == len(cover)
        assert is_cover(G, cover)

    def test_unweighted_undirected(self):
        # create a simple star graph
        size = 50
        sg = nx.star_graph(size)
        cover = min_weighted_vertex_cover(sg)
        assert 1 == len(cover)
        assert is_cover(sg, cover)

    def test_weighted(self):
        wg = nx.Graph()
        wg.add_node(0, weight=10)
        wg.add_node(1, weight=1)
        wg.add_node(2, weight=1)
        wg.add_node(3, weight=1)
        wg.add_node(4, weight=1)

        wg.add_edge(0, 1)
        wg.add_edge(0, 2)
        wg.add_edge(0, 3)
        wg.add_edge(0, 4)

        wg.add_edge(1, 2)
        wg.add_edge(2, 3)
        wg.add_edge(3, 4)
        wg.add_edge(4, 1)

        cover = min_weighted_vertex_cover(wg, weight="weight")
        csum = sum(wg.nodes[node]["weight"] for node in cover)
        assert 4 == csum
        assert is_cover(wg, cover)

    def test_unweighted_self_loop(self):
        slg = nx.Graph()
        slg.add_node(0)
        slg.add_node(1)
        slg.add_node(2)

        slg.add_edge(0, 1)
        slg.add_edge(2, 2)

        cover = min_weighted_vertex_cover(slg)
        assert 2 == len(cover)
        assert is_cover(slg, cover)
