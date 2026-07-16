import pytest

import networkx as nx

np = pytest.importorskip("numpy")
sp = pytest.importorskip("scipy")

from networkx.algorithms.link_analysis.hits_alg import (
    _hits_numpy,
    _hits_python,
    _hits_scipy,
)

# Example from
# A. Langville and C. Meyer, "A survey of eigenvector methods of web
# information retrieval."  http://citeseer.ist.psu.edu/713792.html


class TestHITS:
    @classmethod
    def setup_class(cls):
        G = nx.DiGraph()

        edges = [(1, 3), (1, 5), (2, 1), (3, 5), (5, 4), (5, 3), (6, 5)]

        G.add_edges_from(edges, weight=1)
        cls.G = G
        cls.G.a = dict(
            zip(sorted(G), [0.000000, 0.000000, 0.366025, 0.133975, 0.500000, 0.000000])
        )
        cls.G.h = dict(
            zip(sorted(G), [0.366025, 0.000000, 0.211325, 0.000000, 0.211325, 0.211325])
        )

    def test_hits_numpy(self):
        G = self.G
        h, a = _hits_numpy(G)
        for n in G:
            assert h[n] == pytest.approx(G.h[n], abs=1e-4)
        for n in G:
            assert a[n] == pytest.approx(G.a[n], abs=1e-4)

    @pytest.mark.parametrize("hits_alg", (nx.hits, _hits_python, _hits_scipy))
    def test_hits(self, hits_alg):
        G = self.G
        h, a = hits_alg(G, tol=1.0e-08)
        for n in G:
            assert h[n] == pytest.approx(G.h[n], abs=1e-4)
        for n in G:
            assert a[n] == pytest.approx(G.a[n], abs=1e-4)
        nstart = {i: 1.0 / 2 for i in G}
        h, a = hits_alg(G, nstart=nstart)
        for n in G:
            assert h[n] == pytest.approx(G.h[n], abs=1e-4)
        for n in G:
            assert a[n] == pytest.approx(G.a[n], abs=1e-4)

    def test_empty(self):
        G = nx.Graph()
        assert nx.hits(G) == ({}, {})
        assert _hits_numpy(G) == ({}, {})
        assert _hits_python(G) == ({}, {})
        assert _hits_scipy(G) == ({}, {})

    def test_hits_not_convergent(self):
        G = nx.path_graph(50)
        with pytest.raises(nx.PowerIterationFailedConvergence):
            _hits_scipy(G, max_iter=1)
        with pytest.raises(nx.PowerIterationFailedConvergence):
            _hits_python(G, max_iter=1)
        with pytest.raises(nx.PowerIterationFailedConvergence):
            _hits_scipy(G, max_iter=0)
        with pytest.raises(nx.PowerIterationFailedConvergence):
            _hits_python(G, max_iter=0)
        with pytest.raises(nx.PowerIterationFailedConvergence):
            nx.hits(G, max_iter=0)
        with pytest.raises(nx.PowerIterationFailedConvergence):
            nx.hits(G, max_iter=1)
