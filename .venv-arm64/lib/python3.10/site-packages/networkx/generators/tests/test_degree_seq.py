import pytest

import networkx as nx


class TestConfigurationModel:
    """Unit tests for the :func:`~networkx.configuration_model`
    function.

    """

    def test_empty_degree_sequence(self):
        """Tests that an empty degree sequence yields the null graph."""
        G = nx.configuration_model([])
        assert len(G) == 0

    def test_degree_zero(self):
        """Tests that a degree sequence of all zeros yields the empty
        graph.

        """
        G = nx.configuration_model([0, 0, 0])
        assert len(G) == 3
        assert G.number_of_edges() == 0

    def test_degree_sequence(self):
        """Tests that the degree sequence of the generated graph matches
        the input degree sequence.

        """
        deg_seq = [5, 3, 3, 3, 3, 2, 2, 2, 1, 1, 1]
        G = nx.configuration_model(deg_seq, seed=12345678)
        assert sorted((d for n, d in G.degree()), reverse=True) == [
            5,
            3,
            3,
            3,
            3,
            2,
            2,
            2,
            1,
            1,
            1,
        ]
        assert sorted((d for n, d in G.degree(range(len(deg_seq)))), reverse=True) == [
            5,
            3,
            3,
            3,
            3,
            2,
            2,
            2,
            1,
            1,
            1,
        ]

    def test_random_seed(self):
        """Tests that each call with the same random seed generates the
        same graph.

        """
        deg_seq = [3] * 12
        G1 = nx.configuration_model(deg_seq, seed=1000)
        G2 = nx.configuration_model(deg_seq, seed=1000)
        assert nx.is_isomorphic(G1, G2)
        G1 = nx.configuration_model(deg_seq, seed=10)
        G2 = nx.configuration_model(deg_seq, seed=10)
        assert nx.is_isomorphic(G1, G2)

    def test_directed_disallowed(self):
        """Tests that attempting to create a configuration model graph
        using a directed graph yields an exception.

        """
        with pytest.raises(nx.NetworkXNotImplemented):
            nx.configuration_model([], create_using=nx.DiGraph())

    def test_odd_degree_sum(self):
        """Tests that a degree sequence whose sum is odd yields an
        exception.

        """
        with pytest.raises(nx.NetworkXError):
            nx.configuration_model([1, 2])


def test_directed_configuration_raise_unequal():
    with pytest.raises(nx.NetworkXError):
        zin = [5, 3, 3, 3, 3, 2, 2, 2, 1, 1]
        zout = [5, 3, 3, 3, 3, 2, 2, 2, 1, 2]
        nx.directed_configuration_model(zin, zout)


def test_directed_configuration_model():
    G = nx.directed_configuration_model([], [], seed=0)
    assert len(G) == 0


def test_simple_directed_configuration_model():
    G = nx.directed_configuration_model([1, 1], [1, 1], seed=0)
    assert len(G) == 2


def test_expected_degree_graph_empty():
    # empty graph has empty degree sequence
    deg_seq = []
    G = nx.expected_degree_graph(deg_seq)
    assert dict(G.degree()) == {}


def test_expected_degree_graph():
    # test that fixed seed delivers the same graph
    deg_seq = [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3]
    G1 = nx.expected_degree_graph(deg_seq, seed=1000)
    assert len(G1) == 12

    G2 = nx.expected_degree_graph(deg_seq, seed=1000)
    assert nx.is_isomorphic(G1, G2)

    G1 = nx.expected_degree_graph(deg_seq, seed=10)
    G2 = nx.expected_degree_graph(deg_seq, seed=10)
    assert nx.is_isomorphic(G1, G2)


def test_expected_degree_graph_selfloops():
    deg_seq = [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3]
    G1 = nx.expected_degree_graph(deg_seq, seed=1000, selfloops=False)
    G2 = nx.expected_degree_graph(deg_seq, seed=1000, selfloops=False)
    assert nx.is_isomorphic(G1, G2)
    assert len(G1) == 12


def test_expected_degree_graph_skew():
    deg_seq = [10, 2, 2, 2, 2]
    G1 = nx.expected_degree_graph(deg_seq, seed=1000)
    G2 = nx.expected_degree_graph(deg_seq, seed=1000)
    assert nx.is_isomorphic(G1, G2)
    assert len(G1) == 5


def test_havel_hakimi_construction():
    G = nx.havel_hakimi_graph([])
    assert len(G) == 0

    z = [1000, 3, 3, 3, 3, 2, 2, 2, 1, 1, 1]
    pytest.raises(nx.NetworkXError, nx.havel_hakimi_graph, z)
    z = ["A", 3, 3, 3, 3, 2, 2, 2, 1, 1, 1]
    pytest.raises(nx.NetworkXError, nx.havel_hakimi_graph, z)

    z = [5, 4, 3, 3, 3, 2, 2, 2]
    G = nx.havel_hakimi_graph(z)
    G = nx.configuration_model(z)
    z = [6, 5, 4, 4, 2, 1, 1, 1]
    pytest.raises(nx.NetworkXError, nx.havel_hakimi_graph, z)

    z = [10, 3, 3, 3, 3, 2, 2, 2, 2, 2, 2]

    G = nx.havel_hakimi_graph(z)

    pytest.raises(nx.NetworkXError, nx.havel_hakimi_graph, z, create_using=nx.DiGraph())


def test_directed_havel_hakimi():
    # Test range of valid directed degree sequences
    n, r = 100, 10
    p = 1.0 / r
    for i in range(r):
        G1 = nx.erdos_renyi_graph(n, p * (i + 1), None, True)
        din1 = [d for n, d in G1.in_degree()]
        dout1 = [d for n, d in G1.out_degree()]
        G2 = nx.directed_havel_hakimi_graph(din1, dout1)
        din2 = [d for n, d in G2.in_degree()]
        dout2 = [d for n, d in G2.out_degree()]
        assert sorted(din1) == sorted(din2)
        assert sorted(dout1) == sorted(dout2)

    # Test non-graphical sequence
    dout = [1000, 3, 3, 3, 3, 2, 2, 2, 1, 1, 1]
    din = [103, 102, 102, 102, 102, 102, 102, 102, 102, 102]
    pytest.raises(nx.exception.NetworkXError, nx.directed_havel_hakimi_graph, din, dout)
    # Test valid sequences
    dout = [1, 1, 1, 1, 1, 2, 2, 2, 3, 4]
    din = [2, 2, 2, 2, 2, 2, 2, 2, 0, 2]
    G2 = nx.directed_havel_hakimi_graph(din, dout)
    dout2 = (d for n, d in G2.out_degree())
    din2 = (d for n, d in G2.in_degree())
    assert sorted(dout) == sorted(dout2)
    assert sorted(din) == sorted(din2)
    # Test unequal sums
    din = [2, 2, 2, 2, 2, 2, 2, 2, 2, 2]
    pytest.raises(nx.exception.NetworkXError, nx.directed_havel_hakimi_graph, din, dout)
    # Test for negative values
    din = [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, -2]
    pytest.raises(nx.exception.NetworkXError, nx.directed_havel_hakimi_graph, din, dout)


def test_degree_sequence_tree():
    z = [1, 1, 1, 1, 1, 2, 2, 2, 3, 4]
    G = nx.degree_sequence_tree(z)
    assert len(G) == len(z)
    assert len(list(G.edges())) == sum(z) / 2

    pytest.raises(
        nx.NetworkXError, nx.degree_sequence_tree, z, create_using=nx.DiGraph()
    )

    z = [1, 1, 1, 1, 1, 1, 2, 2, 2, 3, 4]
    pytest.raises(nx.NetworkXError, nx.degree_sequence_tree, z)


def test_random_degree_sequence_graph():
    d = [1, 2, 2, 3]
    G = nx.random_degree_sequence_graph(d, seed=42)
    assert d == sorted(d for n, d in G.degree())


def test_random_degree_sequence_graph_raise():
    z = [1, 1, 1, 1, 1, 1, 2, 2, 2, 3, 4]
    pytest.raises(nx.NetworkXUnfeasible, nx.random_degree_sequence_graph, z)


def test_random_degree_sequence_large():
    G1 = nx.fast_gnp_random_graph(100, 0.1, seed=42)
    d1 = (d for n, d in G1.degree())
    G2 = nx.random_degree_sequence_graph(d1, seed=42)
    d2 = (d for n, d in G2.degree())
    assert sorted(d1) == sorted(d2)
