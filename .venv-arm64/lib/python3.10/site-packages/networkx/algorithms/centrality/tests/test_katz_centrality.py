import math

import pytest

import networkx as nx


class TestKatzCentrality:
    def test_K5(self):
        """Katz centrality: K5"""
        G = nx.complete_graph(5)
        alpha = 0.1
        b = nx.katz_centrality(G, alpha)
        v = math.sqrt(1 / 5.0)
        b_answer = dict.fromkeys(G, v)
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-7)
        nstart = {n: 1 for n in G}
        b = nx.katz_centrality(G, alpha, nstart=nstart)
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-7)

    def test_P3(self):
        """Katz centrality: P3"""
        alpha = 0.1
        G = nx.path_graph(3)
        b_answer = {0: 0.5598852584152165, 1: 0.6107839182711449, 2: 0.5598852584152162}
        b = nx.katz_centrality(G, alpha)
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-4)

    def test_maxiter(self):
        with pytest.raises(nx.PowerIterationFailedConvergence):
            nx.katz_centrality(nx.path_graph(3), 0.1, max_iter=0)

    def test_beta_as_scalar(self):
        alpha = 0.1
        beta = 0.1
        b_answer = {0: 0.5598852584152165, 1: 0.6107839182711449, 2: 0.5598852584152162}
        G = nx.path_graph(3)
        b = nx.katz_centrality(G, alpha, beta)
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-4)

    def test_beta_as_dict(self):
        alpha = 0.1
        beta = {0: 1.0, 1: 1.0, 2: 1.0}
        b_answer = {0: 0.5598852584152165, 1: 0.6107839182711449, 2: 0.5598852584152162}
        G = nx.path_graph(3)
        b = nx.katz_centrality(G, alpha, beta)
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-4)

    def test_multiple_alpha(self):
        alpha_list = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
        for alpha in alpha_list:
            b_answer = {
                0.1: {
                    0: 0.5598852584152165,
                    1: 0.6107839182711449,
                    2: 0.5598852584152162,
                },
                0.2: {
                    0: 0.5454545454545454,
                    1: 0.6363636363636365,
                    2: 0.5454545454545454,
                },
                0.3: {
                    0: 0.5333964609104419,
                    1: 0.6564879518897746,
                    2: 0.5333964609104419,
                },
                0.4: {
                    0: 0.5232045649263551,
                    1: 0.6726915834767423,
                    2: 0.5232045649263551,
                },
                0.5: {
                    0: 0.5144957746691622,
                    1: 0.6859943117075809,
                    2: 0.5144957746691622,
                },
                0.6: {
                    0: 0.5069794004195823,
                    1: 0.6970966755769258,
                    2: 0.5069794004195823,
                },
            }
            G = nx.path_graph(3)
            b = nx.katz_centrality(G, alpha)
            for n in sorted(G):
                assert b[n] == pytest.approx(b_answer[alpha][n], abs=1e-4)

    def test_multigraph(self):
        with pytest.raises(nx.NetworkXException):
            nx.katz_centrality(nx.MultiGraph(), 0.1)

    def test_empty(self):
        e = nx.katz_centrality(nx.Graph(), 0.1)
        assert e == {}

    def test_bad_beta(self):
        with pytest.raises(nx.NetworkXException):
            G = nx.Graph([(0, 1)])
            beta = {0: 77}
            nx.katz_centrality(G, 0.1, beta=beta)

    def test_bad_beta_number(self):
        with pytest.raises(nx.NetworkXException):
            G = nx.Graph([(0, 1)])
            nx.katz_centrality(G, 0.1, beta="foo")


class TestKatzCentralityNumpy:
    @classmethod
    def setup_class(cls):
        global np
        np = pytest.importorskip("numpy")
        pytest.importorskip("scipy")

    def test_K5(self):
        """Katz centrality: K5"""
        G = nx.complete_graph(5)
        alpha = 0.1
        b = nx.katz_centrality(G, alpha)
        v = math.sqrt(1 / 5.0)
        b_answer = dict.fromkeys(G, v)
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-7)
        b = nx.eigenvector_centrality_numpy(G)
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-3)

    def test_P3(self):
        """Katz centrality: P3"""
        alpha = 0.1
        G = nx.path_graph(3)
        b_answer = {0: 0.5598852584152165, 1: 0.6107839182711449, 2: 0.5598852584152162}
        b = nx.katz_centrality_numpy(G, alpha)
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-4)

    def test_beta_as_scalar(self):
        alpha = 0.1
        beta = 0.1
        b_answer = {0: 0.5598852584152165, 1: 0.6107839182711449, 2: 0.5598852584152162}
        G = nx.path_graph(3)
        b = nx.katz_centrality_numpy(G, alpha, beta)
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-4)

    def test_beta_as_dict(self):
        alpha = 0.1
        beta = {0: 1.0, 1: 1.0, 2: 1.0}
        b_answer = {0: 0.5598852584152165, 1: 0.6107839182711449, 2: 0.5598852584152162}
        G = nx.path_graph(3)
        b = nx.katz_centrality_numpy(G, alpha, beta)
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-4)

    def test_multiple_alpha(self):
        alpha_list = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
        for alpha in alpha_list:
            b_answer = {
                0.1: {
                    0: 0.5598852584152165,
                    1: 0.6107839182711449,
                    2: 0.5598852584152162,
                },
                0.2: {
                    0: 0.5454545454545454,
                    1: 0.6363636363636365,
                    2: 0.5454545454545454,
                },
                0.3: {
                    0: 0.5333964609104419,
                    1: 0.6564879518897746,
                    2: 0.5333964609104419,
                },
                0.4: {
                    0: 0.5232045649263551,
                    1: 0.6726915834767423,
                    2: 0.5232045649263551,
                },
                0.5: {
                    0: 0.5144957746691622,
                    1: 0.6859943117075809,
                    2: 0.5144957746691622,
                },
                0.6: {
                    0: 0.5069794004195823,
                    1: 0.6970966755769258,
                    2: 0.5069794004195823,
                },
            }
            G = nx.path_graph(3)
            b = nx.katz_centrality_numpy(G, alpha)
            for n in sorted(G):
                assert b[n] == pytest.approx(b_answer[alpha][n], abs=1e-4)

    def test_multigraph(self):
        with pytest.raises(nx.NetworkXException):
            nx.katz_centrality(nx.MultiGraph(), 0.1)

    def test_empty(self):
        e = nx.katz_centrality(nx.Graph(), 0.1)
        assert e == {}

    def test_bad_beta(self):
        with pytest.raises(nx.NetworkXException):
            G = nx.Graph([(0, 1)])
            beta = {0: 77}
            nx.katz_centrality_numpy(G, 0.1, beta=beta)

    def test_bad_beta_numbe(self):
        with pytest.raises(nx.NetworkXException):
            G = nx.Graph([(0, 1)])
            nx.katz_centrality_numpy(G, 0.1, beta="foo")

    def test_K5_unweighted(self):
        """Katz centrality: K5"""
        G = nx.complete_graph(5)
        alpha = 0.1
        b = nx.katz_centrality(G, alpha, weight=None)
        v = math.sqrt(1 / 5.0)
        b_answer = dict.fromkeys(G, v)
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-7)
        b = nx.eigenvector_centrality_numpy(G, weight=None)
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-3)

    def test_P3_unweighted(self):
        """Katz centrality: P3"""
        alpha = 0.1
        G = nx.path_graph(3)
        b_answer = {0: 0.5598852584152165, 1: 0.6107839182711449, 2: 0.5598852584152162}
        b = nx.katz_centrality_numpy(G, alpha, weight=None)
        for n in sorted(G):
            assert b[n] == pytest.approx(b_answer[n], abs=1e-4)


class TestKatzCentralityDirected:
    @classmethod
    def setup_class(cls):
        G = nx.DiGraph()
        edges = [
            (1, 2),
            (1, 3),
            (2, 4),
            (3, 2),
            (3, 5),
            (4, 2),
            (4, 5),
            (4, 6),
            (5, 6),
            (5, 7),
            (5, 8),
            (6, 8),
            (7, 1),
            (7, 5),
            (7, 8),
            (8, 6),
            (8, 7),
        ]
        G.add_edges_from(edges, weight=2.0)
        cls.G = G.reverse()
        cls.G.alpha = 0.1
        cls.G.evc = [
            0.3289589783189635,
            0.2832077296243516,
            0.3425906003685471,
            0.3970420865198392,
            0.41074871061646284,
            0.272257430756461,
            0.4201989685435462,
            0.34229059218038554,
        ]

        H = nx.DiGraph(edges)
        cls.H = G.reverse()
        cls.H.alpha = 0.1
        cls.H.evc = [
            0.3289589783189635,
            0.2832077296243516,
            0.3425906003685471,
            0.3970420865198392,
            0.41074871061646284,
            0.272257430756461,
            0.4201989685435462,
            0.34229059218038554,
        ]

    def test_katz_centrality_weighted(self):
        G = self.G
        alpha = self.G.alpha
        p = nx.katz_centrality(G, alpha, weight="weight")
        for a, b in zip(list(p.values()), self.G.evc):
            assert a == pytest.approx(b, abs=1e-7)

    def test_katz_centrality_unweighted(self):
        H = self.H
        alpha = self.H.alpha
        p = nx.katz_centrality(H, alpha, weight="weight")
        for a, b in zip(list(p.values()), self.H.evc):
            assert a == pytest.approx(b, abs=1e-7)


class TestKatzCentralityDirectedNumpy(TestKatzCentralityDirected):
    @classmethod
    def setup_class(cls):
        global np
        np = pytest.importorskip("numpy")
        pytest.importorskip("scipy")
        super().setup_class()

    def test_katz_centrality_weighted(self):
        G = self.G
        alpha = self.G.alpha
        p = nx.katz_centrality_numpy(G, alpha, weight="weight")
        for a, b in zip(list(p.values()), self.G.evc):
            assert a == pytest.approx(b, abs=1e-7)

    def test_katz_centrality_unweighted(self):
        H = self.H
        alpha = self.H.alpha
        p = nx.katz_centrality_numpy(H, alpha, weight="weight")
        for a, b in zip(list(p.values()), self.H.evc):
            assert a == pytest.approx(b, abs=1e-7)


class TestKatzEigenvectorVKatz:
    @classmethod
    def setup_class(cls):
        global np
        np = pytest.importorskip("numpy")
        pytest.importorskip("scipy")

    def test_eigenvector_v_katz_random(self):
        G = nx.gnp_random_graph(10, 0.5, seed=1234)
        l = max(np.linalg.eigvals(nx.adjacency_matrix(G).todense()))
        e = nx.eigenvector_centrality_numpy(G)
        k = nx.katz_centrality_numpy(G, 1.0 / l)
        for n in G:
            assert e[n] == pytest.approx(k[n], abs=1e-7)
