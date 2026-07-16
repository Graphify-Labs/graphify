import pytest

import networkx as nx


def test_complement():
    null = nx.null_graph()
    empty1 = nx.empty_graph(1)
    empty10 = nx.empty_graph(10)
    K3 = nx.complete_graph(3)
    K5 = nx.complete_graph(5)
    K10 = nx.complete_graph(10)
    P2 = nx.path_graph(2)
    P3 = nx.path_graph(3)
    P5 = nx.path_graph(5)
    P10 = nx.path_graph(10)
    # complement of the complete graph is empty

    G = nx.complement(K3)
    assert nx.is_isomorphic(G, nx.empty_graph(3))
    G = nx.complement(K5)
    assert nx.is_isomorphic(G, nx.empty_graph(5))
    # for any G, G=complement(complement(G))
    P3cc = nx.complement(nx.complement(P3))
    assert nx.is_isomorphic(P3, P3cc)
    nullcc = nx.complement(nx.complement(null))
    assert nx.is_isomorphic(null, nullcc)
    b = nx.bull_graph()
    bcc = nx.complement(nx.complement(b))
    assert nx.is_isomorphic(b, bcc)


def test_complement_2():
    G1 = nx.DiGraph()
    G1.add_edge("A", "B")
    G1.add_edge("A", "C")
    G1.add_edge("A", "D")
    G1C = nx.complement(G1)
    assert sorted(G1C.edges()) == [
        ("B", "A"),
        ("B", "C"),
        ("B", "D"),
        ("C", "A"),
        ("C", "B"),
        ("C", "D"),
        ("D", "A"),
        ("D", "B"),
        ("D", "C"),
    ]


def test_reverse1():
    # Other tests for reverse are done by the DiGraph and MultiDigraph.
    G1 = nx.Graph()
    pytest.raises(nx.NetworkXError, nx.reverse, G1)
