import pytest

import networkx as nx

np = pytest.importorskip("numpy")


@pytest.mark.parametrize(
    "k, weight, expected",
    [
        (None, None, 7.21),  # infers 3 communities
        (2, None, 11.7),
        (None, "weight", 25.45),
        (2, "weight", 38.8),
    ],
)
def test_non_randomness(k, weight, expected):
    G = nx.karate_club_graph()
    np.testing.assert_almost_equal(
        nx.non_randomness(G, k, weight)[0], expected, decimal=2
    )


def test_non_connected():
    G = nx.Graph([(1, 2)])
    G.add_node(3)
    with pytest.raises(nx.NetworkXException, match="Non connected"):
        nx.non_randomness(G)


def test_self_loops():
    G = nx.Graph()
    G.add_edge(1, 2)
    G.add_edge(1, 1)
    with pytest.raises(nx.NetworkXError, match="Graph must not contain self-loops"):
        nx.non_randomness(G)


def test_empty_graph():
    G = nx.empty_graph(1)
    with pytest.raises(nx.NetworkXError, match=".*not applicable to empty graphs"):
        nx.non_randomness(G)
