import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

import networkx as nx
from networkx.generators.degree_seq import havel_hakimi_graph


class TestSpectrum:
    @classmethod
    def setup_class(cls):
        deg = [3, 2, 2, 1, 0]
        cls.G = havel_hakimi_graph(deg)
        cls.P = nx.path_graph(3)
        cls.WG = nx.Graph(
            (u, v, {"weight": 0.5, "other": 0.3}) for (u, v) in cls.G.edges()
        )
        cls.WG.add_node(4)
        cls.DG = nx.DiGraph()
        nx.add_path(cls.DG, [0, 1, 2])

    def test_laplacian_spectrum(self):
        "Laplacian eigenvalues"
        evals = np.array([0, 0, 1, 3, 4])
        e = sorted(nx.laplacian_spectrum(self.G))
        np.testing.assert_almost_equal(e, evals)
        e = sorted(nx.laplacian_spectrum(self.WG, weight=None))
        np.testing.assert_almost_equal(e, evals)
        e = sorted(nx.laplacian_spectrum(self.WG))
        np.testing.assert_almost_equal(e, 0.5 * evals)
        e = sorted(nx.laplacian_spectrum(self.WG, weight="other"))
        np.testing.assert_almost_equal(e, 0.3 * evals)

    def test_normalized_laplacian_spectrum(self):
        "Normalized Laplacian eigenvalues"
        evals = np.array([0, 0, 0.7712864461218, 1.5, 1.7287135538781])
        e = sorted(nx.normalized_laplacian_spectrum(self.G))
        np.testing.assert_almost_equal(e, evals)
        e = sorted(nx.normalized_laplacian_spectrum(self.WG, weight=None))
        np.testing.assert_almost_equal(e, evals)
        e = sorted(nx.normalized_laplacian_spectrum(self.WG))
        np.testing.assert_almost_equal(e, evals)
        e = sorted(nx.normalized_laplacian_spectrum(self.WG, weight="other"))
        np.testing.assert_almost_equal(e, evals)

    def test_adjacency_spectrum(self):
        "Adjacency eigenvalues"
        evals = np.array([-np.sqrt(2), 0, np.sqrt(2)])
        e = sorted(nx.adjacency_spectrum(self.P))
        np.testing.assert_almost_equal(e, evals)

    def test_modularity_spectrum(self):
        "Modularity eigenvalues"
        evals = np.array([-1.5, 0.0, 0.0])
        e = sorted(nx.modularity_spectrum(self.P))
        np.testing.assert_almost_equal(e, evals)
        # Directed modularity eigenvalues
        evals = np.array([-0.5, 0.0, 0.0])
        e = sorted(nx.modularity_spectrum(self.DG))
        np.testing.assert_almost_equal(e, evals)

    def test_bethe_hessian_spectrum(self):
        "Bethe Hessian eigenvalues"
        evals = np.array([0.5 * (9 - np.sqrt(33)), 4, 0.5 * (9 + np.sqrt(33))])
        e = sorted(nx.bethe_hessian_spectrum(self.P, r=2))
        np.testing.assert_almost_equal(e, evals)
        # Collapses back to Laplacian:
        e1 = sorted(nx.bethe_hessian_spectrum(self.P, r=1))
        e2 = sorted(nx.laplacian_spectrum(self.P))
        np.testing.assert_almost_equal(e1, e2)
