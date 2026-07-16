import networkx as nx
from networkx.algorithms.tree.decomposition import junction_tree


def test_junction_tree_directed_confounders():
    B = nx.DiGraph()
    B.add_edges_from([("A", "C"), ("B", "C"), ("C", "D"), ("C", "E")])

    G = junction_tree(B)
    J = nx.Graph()
    J.add_edges_from(
        [
            (("C", "E"), ("C",)),
            (("C",), ("A", "B", "C")),
            (("A", "B", "C"), ("C",)),
            (("C",), ("C", "D")),
        ]
    )

    assert nx.is_isomorphic(G, J)


def test_junction_tree_directed_unconnected_nodes():
    B = nx.DiGraph()
    B.add_nodes_from([("A", "B", "C", "D")])
    G = junction_tree(B)

    J = nx.Graph()
    J.add_nodes_from([("A", "B", "C", "D")])

    assert nx.is_isomorphic(G, J)


def test_junction_tree_directed_cascade():
    B = nx.DiGraph()
    B.add_edges_from([("A", "B"), ("B", "C"), ("C", "D")])
    G = junction_tree(B)

    J = nx.Graph()
    J.add_edges_from(
        [
            (("A", "B"), ("B",)),
            (("B",), ("B", "C")),
            (("B", "C"), ("C",)),
            (("C",), ("C", "D")),
        ]
    )
    assert nx.is_isomorphic(G, J)


def test_junction_tree_directed_unconnected_edges():
    B = nx.DiGraph()
    B.add_edges_from([("A", "B"), ("C", "D"), ("E", "F")])
    G = junction_tree(B)

    J = nx.Graph()
    J.add_nodes_from([("A", "B"), ("C", "D"), ("E", "F")])

    assert nx.is_isomorphic(G, J)


def test_junction_tree_undirected():
    B = nx.Graph()
    B.add_edges_from([("A", "C"), ("A", "D"), ("B", "C"), ("C", "E")])
    G = junction_tree(B)

    J = nx.Graph()
    J.add_edges_from(
        [
            (("A", "D"), ("A",)),
            (("A",), ("A", "C")),
            (("A", "C"), ("C",)),
            (("C",), ("B", "C")),
            (("B", "C"), ("C",)),
            (("C",), ("C", "E")),
        ]
    )

    assert nx.is_isomorphic(G, J)
