import networkx as nx
from networkx.algorithms.moral import moral_graph


def test_get_moral_graph():
    graph = nx.DiGraph()
    graph.add_nodes_from([1, 2, 3, 4, 5, 6, 7])
    graph.add_edges_from([(1, 2), (3, 2), (4, 1), (4, 5), (6, 5), (7, 5)])
    H = moral_graph(graph)
    assert not H.is_directed()
    assert H.has_edge(1, 3)
    assert H.has_edge(4, 6)
    assert H.has_edge(6, 7)
    assert H.has_edge(4, 7)
    assert not H.has_edge(1, 5)
