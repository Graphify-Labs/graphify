"""
Threshold Graphs
================
"""

import pytest

import networkx as nx
import networkx.algorithms.threshold as nxt
from networkx.algorithms.isomorphism.isomorph import graph_could_be_isomorphic

cnlti = nx.convert_node_labels_to_integers


class TestGeneratorThreshold:
    def test_threshold_sequence_graph_test(self):
        G = nx.star_graph(10)
        assert nxt.is_threshold_graph(G)
        assert nxt.is_threshold_sequence([d for n, d in G.degree()])

        G = nx.complete_graph(10)
        assert nxt.is_threshold_graph(G)
        assert nxt.is_threshold_sequence([d for n, d in G.degree()])

        deg = [3, 2, 2, 1, 1, 1]
        assert not nxt.is_threshold_sequence(deg)

        deg = [3, 2, 2, 1]
        assert nxt.is_threshold_sequence(deg)

        G = nx.generators.havel_hakimi_graph(deg)
        assert nxt.is_threshold_graph(G)

    def test_creation_sequences(self):
        deg = [3, 2, 2, 1]
        G = nx.generators.havel_hakimi_graph(deg)

        with pytest.raises(ValueError):
            nxt.creation_sequence(deg, with_labels=True, compact=True)

        cs0 = nxt.creation_sequence(deg)
        H0 = nxt.threshold_graph(cs0)
        assert "".join(cs0) == "ddid"

        cs1 = nxt.creation_sequence(deg, with_labels=True)
        H1 = nxt.threshold_graph(cs1)
        assert cs1 == [(1, "d"), (2, "d"), (3, "i"), (0, "d")]

        cs2 = nxt.creation_sequence(deg, compact=True)
        H2 = nxt.threshold_graph(cs2)
        assert cs2 == [2, 1, 1]
        assert "".join(nxt.uncompact(cs2)) == "ddid"
        assert graph_could_be_isomorphic(H0, G)
        assert graph_could_be_isomorphic(H0, H1)
        assert graph_could_be_isomorphic(H0, H2)

    def test_make_compact(self):
        assert nxt.make_compact(["d", "d", "d", "i", "d", "d"]) == [3, 1, 2]
        assert nxt.make_compact([3, 1, 2]) == [3, 1, 2]
        assert pytest.raises(TypeError, nxt.make_compact, [3.0, 1.0, 2.0])

    def test_uncompact(self):
        assert nxt.uncompact([3, 1, 2]) == ["d", "d", "d", "i", "d", "d"]
        assert nxt.uncompact(["d", "d", "i", "d"]) == ["d", "d", "i", "d"]
        assert nxt.uncompact(
            nxt.uncompact([(1, "d"), (2, "d"), (3, "i"), (0, "d")])
        ) == nxt.uncompact([(1, "d"), (2, "d"), (3, "i"), (0, "d")])
        assert pytest.raises(TypeError, nxt.uncompact, [3.0, 1.0, 2.0])

    def test_creation_sequence_to_weights(self):
        assert nxt.creation_sequence_to_weights([3, 1, 2]) == [
            0.5,
            0.5,
            0.5,
            0.25,
            0.75,
            0.75,
        ]
        assert pytest.raises(
            TypeError, nxt.creation_sequence_to_weights, [3.0, 1.0, 2.0]
        )

    def test_weights_to_creation_sequence(self):
        deg = [3, 2, 2, 1]
        with pytest.raises(ValueError):
            nxt.weights_to_creation_sequence(deg, with_labels=True, compact=True)
        assert nxt.weights_to_creation_sequence(deg, with_labels=True) == [
            (3, "d"),
            (1, "d"),
            (2, "d"),
            (0, "d"),
        ]
        assert nxt.weights_to_creation_sequence(deg, compact=True) == [4]

    def test_find_alternating_4_cycle(self):
        G = nx.Graph()
        G.add_edge(1, 2)
        assert not nxt.find_alternating_4_cycle(G)

    def test_shortest_path(self):
        deg = [3, 2, 2, 1]
        G = nx.generators.havel_hakimi_graph(deg)
        cs1 = nxt.creation_sequence(deg, with_labels=True)
        for n, m in [(3, 0), (0, 3), (0, 2), (0, 1), (1, 3), (3, 1), (1, 2), (2, 3)]:
            assert nxt.shortest_path(cs1, n, m) == nx.shortest_path(G, n, m)

        spl = nxt.shortest_path_length(cs1, 3)
        spl2 = nxt.shortest_path_length([t for v, t in cs1], 2)
        assert spl == spl2

        spld = {}
        for j, pl in enumerate(spl):
            n = cs1[j][0]
            spld[n] = pl
        assert spld == nx.single_source_shortest_path_length(G, 3)

        assert nxt.shortest_path(["d", "d", "d", "i", "d", "d"], 1, 2) == [1, 2]
        assert nxt.shortest_path([3, 1, 2], 1, 2) == [1, 2]
        assert pytest.raises(TypeError, nxt.shortest_path, [3.0, 1.0, 2.0], 1, 2)
        assert pytest.raises(ValueError, nxt.shortest_path, [3, 1, 2], "a", 2)
        assert pytest.raises(ValueError, nxt.shortest_path, [3, 1, 2], 1, "b")
        assert nxt.shortest_path([3, 1, 2], 1, 1) == [1]

    def test_shortest_path_length(self):
        assert nxt.shortest_path_length([3, 1, 2], 1) == [1, 0, 1, 2, 1, 1]
        assert nxt.shortest_path_length(["d", "d", "d", "i", "d", "d"], 1) == [
            1,
            0,
            1,
            2,
            1,
            1,
        ]
        assert nxt.shortest_path_length(("d", "d", "d", "i", "d", "d"), 1) == [
            1,
            0,
            1,
            2,
            1,
            1,
        ]
        assert pytest.raises(TypeError, nxt.shortest_path, [3.0, 1.0, 2.0], 1)

    def test_random_threshold_sequence(self):
        assert len(nxt.random_threshold_sequence(10, 0.5)) == 10
        assert nxt.random_threshold_sequence(10, 0.5, seed=42) == [
            "d",
            "i",
            "d",
            "d",
            "d",
            "i",
            "i",
            "i",
            "d",
            "d",
        ]
        assert pytest.raises(ValueError, nxt.random_threshold_sequence, 10, 1.5)

    def test_right_d_threshold_sequence(self):
        assert nxt.right_d_threshold_sequence(3, 2) == ["d", "i", "d"]
        assert pytest.raises(ValueError, nxt.right_d_threshold_sequence, 2, 3)

    def test_left_d_threshold_sequence(self):
        assert nxt.left_d_threshold_sequence(3, 2) == ["d", "i", "d"]
        assert pytest.raises(ValueError, nxt.left_d_threshold_sequence, 2, 3)

    def test_weights_thresholds(self):
        wseq = [3, 4, 3, 3, 5, 6, 5, 4, 5, 6]
        cs = nxt.weights_to_creation_sequence(wseq, threshold=10)
        wseq = nxt.creation_sequence_to_weights(cs)
        cs2 = nxt.weights_to_creation_sequence(wseq)
        assert cs == cs2

        wseq = nxt.creation_sequence_to_weights(nxt.uncompact([3, 1, 2, 3, 3, 2, 3]))
        assert wseq == [
            s * 0.125 for s in [4, 4, 4, 3, 5, 5, 2, 2, 2, 6, 6, 6, 1, 1, 7, 7, 7]
        ]

        wseq = nxt.creation_sequence_to_weights([3, 1, 2, 3, 3, 2, 3])
        assert wseq == [
            s * 0.125 for s in [4, 4, 4, 3, 5, 5, 2, 2, 2, 6, 6, 6, 1, 1, 7, 7, 7]
        ]

        wseq = nxt.creation_sequence_to_weights(list(enumerate("ddidiiidididi")))
        assert wseq == [s * 0.1 for s in [5, 5, 4, 6, 3, 3, 3, 7, 2, 8, 1, 9, 0]]

        wseq = nxt.creation_sequence_to_weights("ddidiiidididi")
        assert wseq == [s * 0.1 for s in [5, 5, 4, 6, 3, 3, 3, 7, 2, 8, 1, 9, 0]]

        wseq = nxt.creation_sequence_to_weights("ddidiiidididid")
        ws = [s / 12 for s in [6, 6, 5, 7, 4, 4, 4, 8, 3, 9, 2, 10, 1, 11]]
        assert sum(abs(c - d) for c, d in zip(wseq, ws)) < 1e-14

    def test_finding_routines(self):
        G = nx.Graph({1: [2], 2: [3], 3: [4], 4: [5], 5: [6]})
        G.add_edge(2, 4)
        G.add_edge(2, 5)
        G.add_edge(2, 7)
        G.add_edge(3, 6)
        G.add_edge(4, 6)

        # Alternating 4 cycle
        assert nxt.find_alternating_4_cycle(G) == [1, 2, 3, 6]

        # Threshold graph
        TG = nxt.find_threshold_graph(G)
        assert nxt.is_threshold_graph(TG)
        assert sorted(TG.nodes()) == [1, 2, 3, 4, 5, 7]

        cs = nxt.creation_sequence(dict(TG.degree()), with_labels=True)
        assert nxt.find_creation_sequence(G) == cs

    def test_fast_versions_properties_threshold_graphs(self):
        cs = "ddiiddid"
        G = nxt.threshold_graph(cs)
        assert nxt.density("ddiiddid") == nx.density(G)
        assert sorted(nxt.degree_sequence(cs)) == sorted(d for n, d in G.degree())

        ts = nxt.triangle_sequence(cs)
        assert ts == list(nx.triangles(G).values())
        assert sum(ts) // 3 == nxt.triangles(cs)

        c1 = nxt.cluster_sequence(cs)
        c2 = list(nx.clustering(G).values())
        assert sum(abs(c - d) for c, d in zip(c1, c2)) == pytest.approx(0, abs=1e-7)

        b1 = nx.betweenness_centrality(G).values()
        b2 = nxt.betweenness_sequence(cs)
        assert sum(abs(c - d) for c, d in zip(b1, b2)) < 1e-7

        assert nxt.eigenvalues(cs) == [0, 1, 3, 3, 5, 7, 7, 8]

        # Degree Correlation
        assert abs(nxt.degree_correlation(cs) + 0.593038821954) < 1e-12
        assert nxt.degree_correlation("diiiddi") == -0.8
        assert nxt.degree_correlation("did") == -1.0
        assert nxt.degree_correlation("ddd") == 1.0
        assert nxt.eigenvalues("dddiii") == [0, 0, 0, 0, 3, 3]
        assert nxt.eigenvalues("dddiiid") == [0, 1, 1, 1, 4, 4, 7]

    def test_tg_creation_routines(self):
        s = nxt.left_d_threshold_sequence(5, 7)
        s = nxt.right_d_threshold_sequence(5, 7)
        s1 = nxt.swap_d(s, 1.0, 1.0)
        s1 = nxt.swap_d(s, 1.0, 1.0, seed=1)

    def test_eigenvectors(self):
        np = pytest.importorskip("numpy")
        eigenval = np.linalg.eigvals
        pytest.importorskip("scipy")

        cs = "ddiiddid"
        G = nxt.threshold_graph(cs)
        (tgeval, tgevec) = nxt.eigenvectors(cs)
        np.testing.assert_allclose([np.dot(lv, lv) for lv in tgevec], 1.0, rtol=1e-9)
        lapl = nx.laplacian_matrix(G)

    def test_create_using(self):
        cs = "ddiiddid"
        G = nxt.threshold_graph(cs)
        assert pytest.raises(
            nx.exception.NetworkXError,
            nxt.threshold_graph,
            cs,
            create_using=nx.DiGraph(),
        )
        MG = nxt.threshold_graph(cs, create_using=nx.MultiGraph())
        assert sorted(MG.edges()) == sorted(G.edges())
