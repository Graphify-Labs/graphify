import json

import pytest

import networkx as nx
from networkx.readwrite.json_graph import tree_data, tree_graph


def test_graph():
    G = nx.DiGraph()
    G.add_nodes_from([1, 2, 3], color="red")
    G.add_edge(1, 2, foo=7)
    G.add_edge(1, 3, foo=10)
    G.add_edge(3, 4, foo=10)
    H = tree_graph(tree_data(G, 1))
    assert nx.is_isomorphic(G, H)


def test_graph_attributes():
    G = nx.DiGraph()
    G.add_nodes_from([1, 2, 3], color="red")
    G.add_edge(1, 2, foo=7)
    G.add_edge(1, 3, foo=10)
    G.add_edge(3, 4, foo=10)
    H = tree_graph(tree_data(G, 1))
    assert H.nodes[1]["color"] == "red"

    d = json.dumps(tree_data(G, 1))
    H = tree_graph(json.loads(d))
    assert H.nodes[1]["color"] == "red"


def test_exceptions():
    with pytest.raises(TypeError, match="is not a tree."):
        G = nx.complete_graph(3)
        tree_data(G, 0)
    with pytest.raises(TypeError, match="is not directed."):
        G = nx.path_graph(3)
        tree_data(G, 0)
    with pytest.raises(TypeError, match="is not weakly connected."):
        G = nx.path_graph(3, create_using=nx.DiGraph)
        G.add_edge(2, 0)
        G.add_node(3)
        tree_data(G, 0)
    with pytest.raises(nx.NetworkXError, match="must be different."):
        G = nx.MultiDiGraph()
        G.add_node(0)
        tree_data(G, 0, ident="node", children="node")
