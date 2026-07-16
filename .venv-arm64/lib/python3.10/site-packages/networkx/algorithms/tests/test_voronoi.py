import networkx as nx
from networkx.utils import pairwise


class TestVoronoiCells:
    """Unit tests for the Voronoi cells function."""

    def test_isolates(self):
        """Tests that a graph with isolated nodes has all isolates in
        one block of the partition.

        """
        G = nx.empty_graph(5)
        cells = nx.voronoi_cells(G, {0, 2, 4})
        expected = {0: {0}, 2: {2}, 4: {4}, "unreachable": {1, 3}}
        assert expected == cells

    def test_undirected_unweighted(self):
        G = nx.cycle_graph(6)
        cells = nx.voronoi_cells(G, {0, 3})
        expected = {0: {0, 1, 5}, 3: {2, 3, 4}}
        assert expected == cells

    def test_directed_unweighted(self):
        # This is the singly-linked directed cycle graph on six nodes.
        G = nx.DiGraph(pairwise(range(6), cyclic=True))
        cells = nx.voronoi_cells(G, {0, 3})
        expected = {0: {0, 1, 2}, 3: {3, 4, 5}}
        assert expected == cells

    def test_directed_inward(self):
        """Tests that reversing the graph gives the "inward" Voronoi
        partition.

        """
        # This is the singly-linked reverse directed cycle graph on six nodes.
        G = nx.DiGraph(pairwise(range(6), cyclic=True))
        G = G.reverse(copy=False)
        cells = nx.voronoi_cells(G, {0, 3})
        expected = {0: {0, 4, 5}, 3: {1, 2, 3}}
        assert expected == cells

    def test_undirected_weighted(self):
        edges = [(0, 1, 10), (1, 2, 1), (2, 3, 1)]
        G = nx.Graph()
        G.add_weighted_edges_from(edges)
        cells = nx.voronoi_cells(G, {0, 3})
        expected = {0: {0}, 3: {1, 2, 3}}
        assert expected == cells

    def test_directed_weighted(self):
        edges = [(0, 1, 10), (1, 2, 1), (2, 3, 1), (3, 2, 1), (2, 1, 1)]
        G = nx.DiGraph()
        G.add_weighted_edges_from(edges)
        cells = nx.voronoi_cells(G, {0, 3})
        expected = {0: {0}, 3: {1, 2, 3}}
        assert expected == cells

    def test_multigraph_unweighted(self):
        """Tests that the Voronoi cells for a multigraph are the same as
        for a simple graph.

        """
        edges = [(0, 1), (1, 2), (2, 3)]
        G = nx.MultiGraph(2 * edges)
        H = nx.Graph(G)
        G_cells = nx.voronoi_cells(G, {0, 3})
        H_cells = nx.voronoi_cells(H, {0, 3})
        assert G_cells == H_cells

    def test_multidigraph_unweighted(self):
        # This is the twice-singly-linked directed cycle graph on six nodes.
        edges = list(pairwise(range(6), cyclic=True))
        G = nx.MultiDiGraph(2 * edges)
        H = nx.DiGraph(G)
        G_cells = nx.voronoi_cells(G, {0, 3})
        H_cells = nx.voronoi_cells(H, {0, 3})
        assert G_cells == H_cells

    def test_multigraph_weighted(self):
        edges = [(0, 1, 10), (0, 1, 10), (1, 2, 1), (1, 2, 100), (2, 3, 1), (2, 3, 100)]
        G = nx.MultiGraph()
        G.add_weighted_edges_from(edges)
        cells = nx.voronoi_cells(G, {0, 3})
        expected = {0: {0}, 3: {1, 2, 3}}
        assert expected == cells

    def test_multidigraph_weighted(self):
        edges = [
            (0, 1, 10),
            (0, 1, 10),
            (1, 2, 1),
            (2, 3, 1),
            (3, 2, 10),
            (3, 2, 1),
            (2, 1, 10),
            (2, 1, 1),
        ]
        G = nx.MultiDiGraph()
        G.add_weighted_edges_from(edges)
        cells = nx.voronoi_cells(G, {0, 3})
        expected = {0: {0}, 3: {1, 2, 3}}
        assert expected == cells
