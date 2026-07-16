"""Tests for the :mod:`networkx.algorithms.triads` module."""

import itertools
from collections import defaultdict
from random import sample

import pytest

import networkx as nx


def test_all_triplets_deprecated():
    G = nx.DiGraph([(1, 2), (2, 3), (3, 4)])
    with pytest.deprecated_call():
        nx.all_triplets(G)


def test_random_triad_deprecated():
    G = nx.path_graph(3, create_using=nx.DiGraph)
    with pytest.deprecated_call():
        nx.random_triad(G)


def test_triadic_census():
    """Tests the triadic_census function."""
    G = nx.DiGraph()
    G.add_edges_from(["01", "02", "03", "04", "05", "12", "16", "51", "56", "65"])
    expected = {
        "030T": 2,
        "120C": 1,
        "210": 0,
        "120U": 0,
        "012": 9,
        "102": 3,
        "021U": 0,
        "111U": 0,
        "003": 8,
        "030C": 0,
        "021D": 9,
        "201": 0,
        "111D": 1,
        "300": 0,
        "120D": 0,
        "021C": 2,
    }
    actual = nx.triadic_census(G)
    assert expected == actual


def test_is_triad():
    """Tests the is_triad function"""
    G = nx.karate_club_graph()
    G = G.to_directed()
    for i in range(100):
        nodes = sample(sorted(G.nodes()), 3)
        G2 = G.subgraph(nodes)
        assert nx.is_triad(G2)


def test_all_triplets():
    """Tests the all_triplets function."""
    G = nx.DiGraph()
    G.add_edges_from(["01", "02", "03", "04", "05", "12", "16", "51", "56", "65"])
    expected = [
        f"{i},{j},{k}"
        for i in range(7)
        for j in range(i + 1, 7)
        for k in range(j + 1, 7)
    ]
    expected = [set(x.split(",")) for x in expected]
    actual = [set(x) for x in nx.all_triplets(G)]
    assert all(any(s1 == s2 for s1 in expected) for s2 in actual)


def test_all_triads():
    """Tests the all_triplets function."""
    G = nx.DiGraph()
    G.add_edges_from(["01", "02", "03", "04", "05", "12", "16", "51", "56", "65"])
    expected = [
        f"{i},{j},{k}"
        for i in range(7)
        for j in range(i + 1, 7)
        for k in range(j + 1, 7)
    ]
    expected = [G.subgraph(x.split(",")) for x in expected]
    actual = list(nx.all_triads(G))
    assert all(any(nx.is_isomorphic(G1, G2) for G1 in expected) for G2 in actual)


def test_triad_type():
    """Tests the triad_type function."""
    # 0 edges (1 type)
    G = nx.DiGraph({0: [], 1: [], 2: []})
    assert nx.triad_type(G) == "003"
    # 1 edge (1 type)
    G = nx.DiGraph({0: [1], 1: [], 2: []})
    assert nx.triad_type(G) == "012"
    # 2 edges (4 types)
    G = nx.DiGraph([(0, 1), (0, 2)])
    assert nx.triad_type(G) == "021D"
    G = nx.DiGraph({0: [1], 1: [0], 2: []})
    assert nx.triad_type(G) == "102"
    G = nx.DiGraph([(0, 1), (2, 1)])
    assert nx.triad_type(G) == "021U"
    G = nx.DiGraph([(0, 1), (1, 2)])
    assert nx.triad_type(G) == "021C"
    # 3 edges (4 types)
    G = nx.DiGraph([(0, 1), (1, 0), (2, 1)])
    assert nx.triad_type(G) == "111D"
    G = nx.DiGraph([(0, 1), (1, 0), (1, 2)])
    assert nx.triad_type(G) == "111U"
    G = nx.DiGraph([(0, 1), (1, 2), (0, 2)])
    assert nx.triad_type(G) == "030T"
    G = nx.DiGraph([(0, 1), (1, 2), (2, 0)])
    assert nx.triad_type(G) == "030C"
    # 4 edges (4 types)
    G = nx.DiGraph([(0, 1), (1, 0), (2, 0), (0, 2)])
    assert nx.triad_type(G) == "201"
    G = nx.DiGraph([(0, 1), (1, 0), (2, 0), (2, 1)])
    assert nx.triad_type(G) == "120D"
    G = nx.DiGraph([(0, 1), (1, 0), (0, 2), (1, 2)])
    assert nx.triad_type(G) == "120U"
    G = nx.DiGraph([(0, 1), (1, 0), (0, 2), (2, 1)])
    assert nx.triad_type(G) == "120C"
    # 5 edges (1 type)
    G = nx.DiGraph([(0, 1), (1, 0), (2, 1), (1, 2), (0, 2)])
    assert nx.triad_type(G) == "210"
    # 6 edges (1 type)
    G = nx.DiGraph([(0, 1), (1, 0), (1, 2), (2, 1), (0, 2), (2, 0)])
    assert nx.triad_type(G) == "300"


def test_triads_by_type():
    """Tests the all_triplets function."""
    G = nx.DiGraph()
    G.add_edges_from(["01", "02", "03", "04", "05", "12", "16", "51", "56", "65"])
    all_triads = nx.all_triads(G)
    expected = defaultdict(list)
    for triad in all_triads:
        name = nx.triad_type(triad)
        expected[name].append(triad)
    actual = nx.triads_by_type(G)
    assert set(actual.keys()) == set(expected.keys())
    for tri_type, actual_Gs in actual.items():
        expected_Gs = expected[tri_type]
        for a in actual_Gs:
            assert any(nx.is_isomorphic(a, e) for e in expected_Gs)


def test_random_triad():
    """Tests the random_triad function"""
    G = nx.karate_club_graph()
    G = G.to_directed()
    for i in range(100):
        assert nx.is_triad(nx.random_triad(G))

    G = nx.DiGraph()
    msg = "at least 3 nodes to form a triad"
    with pytest.raises(nx.NetworkXError, match=msg):
        nx.random_triad(G)


def test_triadic_census_short_path_nodelist():
    G = nx.path_graph("abc", create_using=nx.DiGraph)
    expected = {"021C": 1}
    for nl in ["a", "b", "c", "ab", "ac", "bc", "abc"]:
        triad_census = nx.triadic_census(G, nodelist=nl)
        assert expected == {typ: cnt for typ, cnt in triad_census.items() if cnt > 0}


def test_triadic_census_correct_nodelist_values():
    G = nx.path_graph(5, create_using=nx.DiGraph)
    msg = r"nodelist includes duplicate nodes or nodes not in G"
    with pytest.raises(ValueError, match=msg):
        nx.triadic_census(G, [1, 2, 2, 3])
    with pytest.raises(ValueError, match=msg):
        nx.triadic_census(G, [1, 2, "a", 3])


def test_triadic_census_tiny_graphs():
    tc = nx.triadic_census(nx.empty_graph(0, create_using=nx.DiGraph))
    assert {} == {typ: cnt for typ, cnt in tc.items() if cnt > 0}
    tc = nx.triadic_census(nx.empty_graph(1, create_using=nx.DiGraph))
    assert {} == {typ: cnt for typ, cnt in tc.items() if cnt > 0}
    tc = nx.triadic_census(nx.empty_graph(2, create_using=nx.DiGraph))
    assert {} == {typ: cnt for typ, cnt in tc.items() if cnt > 0}
    tc = nx.triadic_census(nx.DiGraph([(1, 2)]))
    assert {} == {typ: cnt for typ, cnt in tc.items() if cnt > 0}


def test_triadic_census_selfloops():
    GG = nx.path_graph("abc", create_using=nx.DiGraph)
    expected = {"021C": 1}
    for n in GG:
        G = GG.copy()
        G.add_edge(n, n)
        tc = nx.triadic_census(G)
        assert expected == {typ: cnt for typ, cnt in tc.items() if cnt > 0}

    GG = nx.path_graph("abcde", create_using=nx.DiGraph)
    tbt = nx.triads_by_type(GG)
    for n in GG:
        GG.add_edge(n, n)
    tc = nx.triadic_census(GG)
    assert tc == {tt: len(tbt[tt]) for tt in tc}


def test_triadic_census_four_path():
    G = nx.path_graph("abcd", create_using=nx.DiGraph)
    expected = {"012": 2, "021C": 2}
    triad_census = nx.triadic_census(G)
    assert expected == {typ: cnt for typ, cnt in triad_census.items() if cnt > 0}


def test_triadic_census_four_path_nodelist():
    G = nx.path_graph("abcd", create_using=nx.DiGraph)
    expected_end = {"012": 2, "021C": 1}
    expected_mid = {"012": 1, "021C": 2}
    a_triad_census = nx.triadic_census(G, nodelist=["a"])
    assert expected_end == {typ: cnt for typ, cnt in a_triad_census.items() if cnt > 0}
    b_triad_census = nx.triadic_census(G, nodelist=["b"])
    assert expected_mid == {typ: cnt for typ, cnt in b_triad_census.items() if cnt > 0}
    c_triad_census = nx.triadic_census(G, nodelist=["c"])
    assert expected_mid == {typ: cnt for typ, cnt in c_triad_census.items() if cnt > 0}
    d_triad_census = nx.triadic_census(G, nodelist=["d"])
    assert expected_end == {typ: cnt for typ, cnt in d_triad_census.items() if cnt > 0}


def test_triadic_census_nodelist():
    """Tests the triadic_census function."""
    G = nx.DiGraph()
    G.add_edges_from(["01", "02", "03", "04", "05", "12", "16", "51", "56", "65"])
    expected = {
        "030T": 2,
        "120C": 1,
        "210": 0,
        "120U": 0,
        "012": 9,
        "102": 3,
        "021U": 0,
        "111U": 0,
        "003": 8,
        "030C": 0,
        "021D": 9,
        "201": 0,
        "111D": 1,
        "300": 0,
        "120D": 0,
        "021C": 2,
    }
    actual = {k: 0 for k in expected}
    for node in G.nodes():
        node_triad_census = nx.triadic_census(G, nodelist=[node])
        for triad_key in expected:
            actual[triad_key] += node_triad_census[triad_key]
    # Divide all counts by 3
    for k, v in actual.items():
        actual[k] //= 3
    assert expected == actual


@pytest.mark.parametrize("N", [5, 10])
def test_triadic_census_on_random_graph(N):
    G = nx.binomial_graph(N, 0.3, directed=True, seed=42)
    tc1 = nx.triadic_census(G)
    tbt = nx.triads_by_type(G)
    tc2 = {tt: len(tbt[tt]) for tt in tc1}
    assert tc1 == tc2

    for n in G:
        tc1 = nx.triadic_census(G, nodelist={n})
        tc2 = {tt: sum(1 for t in tbt.get(tt, []) if n in t) for tt in tc1}
        assert tc1 == tc2

    for ns in itertools.combinations(G, 2):
        ns = set(ns)
        tc1 = nx.triadic_census(G, nodelist=ns)
        tc2 = {
            tt: sum(1 for t in tbt.get(tt, []) if any(n in ns for n in t)) for tt in tc1
        }
        assert tc1 == tc2

    for ns in itertools.combinations(G, 3):
        ns = set(ns)
        tc1 = nx.triadic_census(G, nodelist=ns)
        tc2 = {
            tt: sum(1 for t in tbt.get(tt, []) if any(n in ns for n in t)) for tt in tc1
        }
        assert tc1 == tc2
