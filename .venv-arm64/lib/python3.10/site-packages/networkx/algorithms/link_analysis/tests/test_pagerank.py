import random

import pytest

import networkx as nx
from networkx.classes.tests import dispatch_interface

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

from networkx.algorithms.link_analysis.pagerank_alg import (
    _pagerank_numpy,
    _pagerank_python,
    _pagerank_scipy,
)

# Example from
# A. Langville and C. Meyer, "A survey of eigenvector methods of web
# information retrieval."  http://citeseer.ist.psu.edu/713792.html


class TestPageRank:
    @classmethod
    def setup_class(cls):
        G = nx.DiGraph()
        edges = [
            (1, 2),
            (1, 3),
            # 2 is a dangling node
            (3, 1),
            (3, 2),
            (3, 5),
            (4, 5),
            (4, 6),
            (5, 4),
            (5, 6),
            (6, 4),
        ]
        G.add_edges_from(edges)
        cls.G = G
        cls.G.pagerank = dict(
            zip(
                sorted(G),
                [
                    0.03721197,
                    0.05395735,
                    0.04150565,
                    0.37508082,
                    0.20599833,
                    0.28624589,
                ],
            )
        )
        cls.dangling_node_index = 1
        cls.dangling_edges = {1: 2, 2: 3, 3: 0, 4: 0, 5: 0, 6: 0}
        cls.G.dangling_pagerank = dict(
            zip(
                sorted(G),
                [0.10844518, 0.18618601, 0.0710892, 0.2683668, 0.15919783, 0.20671497],
            )
        )

    @pytest.mark.parametrize("alg", (nx.pagerank, _pagerank_python))
    def test_pagerank(self, alg):
        G = self.G
        p = alg(G, alpha=0.9, tol=1.0e-08)
        for n in G:
            assert p[n] == pytest.approx(G.pagerank[n], abs=1e-4)

        nstart = {n: random.random() for n in G}
        p = alg(G, alpha=0.9, tol=1.0e-08, nstart=nstart)
        for n in G:
            assert p[n] == pytest.approx(G.pagerank[n], abs=1e-4)

    @pytest.mark.parametrize("alg", (nx.pagerank, _pagerank_python))
    def test_pagerank_max_iter(self, alg):
        with pytest.raises(nx.PowerIterationFailedConvergence):
            alg(self.G, max_iter=0)

    def test_numpy_pagerank(self):
        G = self.G
        p = _pagerank_numpy(G, alpha=0.9)
        for n in G:
            assert p[n] == pytest.approx(G.pagerank[n], abs=1e-4)

    def test_google_matrix(self):
        G = self.G
        M = nx.google_matrix(G, alpha=0.9, nodelist=sorted(G))
        _, ev = np.linalg.eig(M.T)
        p = ev[:, 0] / ev[:, 0].sum()
        for a, b in zip(p, self.G.pagerank.values()):
            assert a == pytest.approx(b, abs=1e-7)

    @pytest.mark.parametrize("alg", (nx.pagerank, _pagerank_python, _pagerank_numpy))
    def test_personalization(self, alg):
        G = nx.complete_graph(4)
        personalize = {0: 1, 1: 1, 2: 4, 3: 4}
        answer = {
            0: 0.23246732615667579,
            1: 0.23246732615667579,
            2: 0.267532673843324,
            3: 0.2675326738433241,
        }
        p = alg(G, alpha=0.85, personalization=personalize)
        for n in G:
            assert p[n] == pytest.approx(answer[n], abs=1e-4)

    @pytest.mark.parametrize("alg", (nx.pagerank, _pagerank_python, nx.google_matrix))
    def test_zero_personalization_vector(self, alg):
        G = nx.complete_graph(4)
        personalize = {0: 0, 1: 0, 2: 0, 3: 0}
        pytest.raises(ZeroDivisionError, alg, G, personalization=personalize)

    @pytest.mark.parametrize("alg", (nx.pagerank, _pagerank_python))
    def test_one_nonzero_personalization_value(self, alg):
        G = nx.complete_graph(4)
        personalize = {0: 0, 1: 0, 2: 0, 3: 1}
        answer = {
            0: 0.22077931820379187,
            1: 0.22077931820379187,
            2: 0.22077931820379187,
            3: 0.3376620453886241,
        }
        p = alg(G, alpha=0.85, personalization=personalize)
        for n in G:
            assert p[n] == pytest.approx(answer[n], abs=1e-4)

    @pytest.mark.parametrize("alg", (nx.pagerank, _pagerank_python))
    def test_incomplete_personalization(self, alg):
        G = nx.complete_graph(4)
        personalize = {3: 1}
        answer = {
            0: 0.22077931820379187,
            1: 0.22077931820379187,
            2: 0.22077931820379187,
            3: 0.3376620453886241,
        }
        p = alg(G, alpha=0.85, personalization=personalize)
        for n in G:
            assert p[n] == pytest.approx(answer[n], abs=1e-4)

    def test_dangling_matrix(self):
        """
        Tests that the google_matrix doesn't change except for the dangling
        nodes.
        """
        G = self.G
        dangling = self.dangling_edges
        dangling_sum = sum(dangling.values())
        M1 = nx.google_matrix(G, personalization=dangling)
        M2 = nx.google_matrix(G, personalization=dangling, dangling=dangling)
        for i in range(len(G)):
            for j in range(len(G)):
                if i == self.dangling_node_index and (j + 1) in dangling:
                    assert M2[i, j] == pytest.approx(
                        dangling[j + 1] / dangling_sum, abs=1e-4
                    )
                else:
                    assert M2[i, j] == pytest.approx(M1[i, j], abs=1e-4)

    @pytest.mark.parametrize("alg", (nx.pagerank, _pagerank_python, _pagerank_numpy))
    def test_dangling_pagerank(self, alg):
        pr = alg(self.G, dangling=self.dangling_edges)
        for n in self.G:
            assert pr[n] == pytest.approx(self.G.dangling_pagerank[n], abs=1e-4)

    def test_empty(self):
        G = nx.Graph()
        assert nx.pagerank(G) == {}
        assert _pagerank_python(G) == {}
        assert _pagerank_numpy(G) == {}
        assert nx.google_matrix(G).shape == (0, 0)

    @pytest.mark.parametrize("alg", (nx.pagerank, _pagerank_python))
    def test_multigraph(self, alg):
        G = nx.MultiGraph()
        G.add_edges_from([(1, 2), (1, 2), (1, 2), (2, 3), (2, 3), ("3", 3), ("3", 3)])
        answer = {
            1: 0.21066048614468322,
            2: 0.3395308825985378,
            3: 0.28933951385531687,
            "3": 0.16046911740146227,
        }
        p = alg(G)
        for n in G:
            assert p[n] == pytest.approx(answer[n], abs=1e-4)


class TestPageRankScipy(TestPageRank):
    def test_scipy_pagerank(self):
        G = self.G
        p = _pagerank_scipy(G, alpha=0.9, tol=1.0e-08)
        for n in G:
            assert p[n] == pytest.approx(G.pagerank[n], abs=1e-4)
        personalize = {n: random.random() for n in G}
        p = _pagerank_scipy(G, alpha=0.9, tol=1.0e-08, personalization=personalize)

        nstart = {n: random.random() for n in G}
        p = _pagerank_scipy(G, alpha=0.9, tol=1.0e-08, nstart=nstart)
        for n in G:
            assert p[n] == pytest.approx(G.pagerank[n], abs=1e-4)

    def test_scipy_pagerank_max_iter(self):
        with pytest.raises(nx.PowerIterationFailedConvergence):
            _pagerank_scipy(self.G, max_iter=0)

    def test_dangling_scipy_pagerank(self):
        pr = _pagerank_scipy(self.G, dangling=self.dangling_edges)
        for n in self.G:
            assert pr[n] == pytest.approx(self.G.dangling_pagerank[n], abs=1e-4)

    def test_empty_scipy(self):
        G = nx.Graph()
        assert _pagerank_scipy(G) == {}
