import networkx as nx
from networkx.algorithms.approximation import average_clustering

# This approximation has to be exact in regular graphs
# with no triangles or with all possible triangles.


def test_petersen():
    # Actual coefficient is 0
    G = nx.petersen_graph()
    assert average_clustering(G, trials=len(G) // 2) == nx.average_clustering(G)


def test_petersen_seed():
    # Actual coefficient is 0
    G = nx.petersen_graph()
    assert average_clustering(G, trials=len(G) // 2, seed=1) == nx.average_clustering(G)


def test_tetrahedral():
    # Actual coefficient is 1
    G = nx.tetrahedral_graph()
    assert average_clustering(G, trials=len(G) // 2) == nx.average_clustering(G)


def test_dodecahedral():
    # Actual coefficient is 0
    G = nx.dodecahedral_graph()
    assert average_clustering(G, trials=len(G) // 2) == nx.average_clustering(G)


def test_empty():
    G = nx.empty_graph(5)
    assert average_clustering(G, trials=len(G) // 2) == 0


def test_complete():
    G = nx.complete_graph(5)
    assert average_clustering(G, trials=len(G) // 2) == 1
    G = nx.complete_graph(7)
    assert average_clustering(G, trials=len(G) // 2) == 1
