import pytest

pytest.importorskip("scipy")

import networkx as nx
from networkx.algorithms.bipartite import spectral_bipartivity as sb

# Examples from Figure 1
# E. Estrada and J. A. Rodríguez-Velázquez, "Spectral measures of
# bipartivity in complex networks", PhysRev E 72, 046105 (2005)


class TestSpectralBipartivity:
    def test_star_like(self):
        # star-like

        G = nx.star_graph(2)
        G.add_edge(1, 2)
        assert sb(G) == pytest.approx(0.843, abs=1e-3)

        G = nx.star_graph(3)
        G.add_edge(1, 2)
        assert sb(G) == pytest.approx(0.871, abs=1e-3)

        G = nx.star_graph(4)
        G.add_edge(1, 2)
        assert sb(G) == pytest.approx(0.890, abs=1e-3)

    def test_k23_like(self):
        # K2,3-like
        G = nx.complete_bipartite_graph(2, 3)
        G.add_edge(0, 1)
        assert sb(G) == pytest.approx(0.769, abs=1e-3)

        G = nx.complete_bipartite_graph(2, 3)
        G.add_edge(2, 4)
        assert sb(G) == pytest.approx(0.829, abs=1e-3)

        G = nx.complete_bipartite_graph(2, 3)
        G.add_edge(2, 4)
        G.add_edge(3, 4)
        assert sb(G) == pytest.approx(0.731, abs=1e-3)

        G = nx.complete_bipartite_graph(2, 3)
        G.add_edge(0, 1)
        G.add_edge(2, 4)
        assert sb(G) == pytest.approx(0.692, abs=1e-3)

        G = nx.complete_bipartite_graph(2, 3)
        G.add_edge(2, 4)
        G.add_edge(3, 4)
        G.add_edge(0, 1)
        assert sb(G) == pytest.approx(0.645, abs=1e-3)

        G = nx.complete_bipartite_graph(2, 3)
        G.add_edge(2, 4)
        G.add_edge(3, 4)
        G.add_edge(2, 3)
        assert sb(G) == pytest.approx(0.645, abs=1e-3)

        G = nx.complete_bipartite_graph(2, 3)
        G.add_edge(2, 4)
        G.add_edge(3, 4)
        G.add_edge(2, 3)
        G.add_edge(0, 1)
        assert sb(G) == pytest.approx(0.597, abs=1e-3)

    def test_single_nodes(self):
        # single nodes
        G = nx.complete_bipartite_graph(2, 3)
        G.add_edge(2, 4)
        sbn = sb(G, nodes=[1, 2])
        assert sbn[1] == pytest.approx(0.85, abs=1e-2)
        assert sbn[2] == pytest.approx(0.77, abs=1e-2)

        G = nx.complete_bipartite_graph(2, 3)
        G.add_edge(0, 1)
        sbn = sb(G, nodes=[1, 2])
        assert sbn[1] == pytest.approx(0.73, abs=1e-2)
        assert sbn[2] == pytest.approx(0.82, abs=1e-2)
