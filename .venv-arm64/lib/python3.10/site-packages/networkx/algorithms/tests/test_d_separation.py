from itertools import combinations

import pytest

import networkx as nx


def path_graph():
    """Return a path graph of length three."""
    G = nx.path_graph(3, create_using=nx.DiGraph)
    G.graph["name"] = "path"
    nx.freeze(G)
    return G


def fork_graph():
    """Return a three node fork graph."""
    G = nx.DiGraph(name="fork")
    G.add_edges_from([(0, 1), (0, 2)])
    nx.freeze(G)
    return G


def collider_graph():
    """Return a collider/v-structure graph with three nodes."""
    G = nx.DiGraph(name="collider")
    G.add_edges_from([(0, 2), (1, 2)])
    nx.freeze(G)
    return G


def naive_bayes_graph():
    """Return a simply Naive Bayes PGM graph."""
    G = nx.DiGraph(name="naive_bayes")
    G.add_edges_from([(0, 1), (0, 2), (0, 3), (0, 4)])
    nx.freeze(G)
    return G


def asia_graph():
    """Return the 'Asia' PGM graph."""
    G = nx.DiGraph(name="asia")
    G.add_edges_from(
        [
            ("asia", "tuberculosis"),
            ("smoking", "cancer"),
            ("smoking", "bronchitis"),
            ("tuberculosis", "either"),
            ("cancer", "either"),
            ("either", "xray"),
            ("either", "dyspnea"),
            ("bronchitis", "dyspnea"),
        ]
    )
    nx.freeze(G)
    return G


@pytest.fixture(name="path_graph")
def path_graph_fixture():
    return path_graph()


@pytest.fixture(name="fork_graph")
def fork_graph_fixture():
    return fork_graph()


@pytest.fixture(name="collider_graph")
def collider_graph_fixture():
    return collider_graph()


@pytest.fixture(name="naive_bayes_graph")
def naive_bayes_graph_fixture():
    return naive_bayes_graph()


@pytest.fixture(name="asia_graph")
def asia_graph_fixture():
    return asia_graph()


@pytest.fixture()
def large_collider_graph():
    edge_list = [("A", "B"), ("C", "B"), ("B", "D"), ("D", "E"), ("B", "F"), ("G", "E")]
    G = nx.DiGraph(edge_list)
    return G


@pytest.fixture()
def chain_and_fork_graph():
    edge_list = [("A", "B"), ("B", "C"), ("B", "D"), ("D", "C")]
    G = nx.DiGraph(edge_list)
    return G


@pytest.fixture()
def no_separating_set_graph():
    edge_list = [("A", "B")]
    G = nx.DiGraph(edge_list)
    return G


@pytest.fixture()
def large_no_separating_set_graph():
    edge_list = [("A", "B"), ("C", "A"), ("C", "B")]
    G = nx.DiGraph(edge_list)
    return G


@pytest.fixture()
def collider_trek_graph():
    edge_list = [("A", "B"), ("C", "B"), ("C", "D")]
    G = nx.DiGraph(edge_list)
    return G


@pytest.mark.parametrize(
    "graph",
    [path_graph(), fork_graph(), collider_graph(), naive_bayes_graph(), asia_graph()],
)
def test_markov_condition(graph):
    """Test that the Markov condition holds for each PGM graph."""
    for node in graph.nodes:
        parents = set(graph.predecessors(node))
        non_descendants = graph.nodes - nx.descendants(graph, node) - {node} - parents
        assert nx.is_d_separator(graph, {node}, non_descendants, parents)


def test_path_graph_dsep(path_graph):
    """Example-based test of d-separation for path_graph."""
    assert nx.is_d_separator(path_graph, {0}, {2}, {1})
    assert not nx.is_d_separator(path_graph, {0}, {2}, set())


def test_fork_graph_dsep(fork_graph):
    """Example-based test of d-separation for fork_graph."""
    assert nx.is_d_separator(fork_graph, {1}, {2}, {0})
    assert not nx.is_d_separator(fork_graph, {1}, {2}, set())


def test_collider_graph_dsep(collider_graph):
    """Example-based test of d-separation for collider_graph."""
    assert nx.is_d_separator(collider_graph, {0}, {1}, set())
    assert not nx.is_d_separator(collider_graph, {0}, {1}, {2})


def test_naive_bayes_dsep(naive_bayes_graph):
    """Example-based test of d-separation for naive_bayes_graph."""
    for u, v in combinations(range(1, 5), 2):
        assert nx.is_d_separator(naive_bayes_graph, {u}, {v}, {0})
        assert not nx.is_d_separator(naive_bayes_graph, {u}, {v}, set())


def test_asia_graph_dsep(asia_graph):
    """Example-based test of d-separation for asia_graph."""
    assert nx.is_d_separator(
        asia_graph, {"asia", "smoking"}, {"dyspnea", "xray"}, {"bronchitis", "either"}
    )
    assert nx.is_d_separator(
        asia_graph, {"tuberculosis", "cancer"}, {"bronchitis"}, {"smoking", "xray"}
    )


def test_undirected_graphs_are_not_supported():
    """
    Test that undirected graphs are not supported.

    d-separation and its related algorithms do not apply in
    the case of undirected graphs.
    """
    g = nx.path_graph(3, nx.Graph)
    with pytest.raises(nx.NetworkXNotImplemented):
        nx.is_d_separator(g, {0}, {1}, {2})
    with pytest.raises(nx.NetworkXNotImplemented):
        nx.is_minimal_d_separator(g, {0}, {1}, {2})
    with pytest.raises(nx.NetworkXNotImplemented):
        nx.find_minimal_d_separator(g, {0}, {1})


def test_cyclic_graphs_raise_error():
    """
    Test that cycle graphs should cause erroring.

    This is because PGMs assume a directed acyclic graph.
    """
    g = nx.cycle_graph(3, nx.DiGraph)
    with pytest.raises(nx.NetworkXError):
        nx.is_d_separator(g, {0}, {1}, {2})
    with pytest.raises(nx.NetworkXError):
        nx.find_minimal_d_separator(g, {0}, {1})
    with pytest.raises(nx.NetworkXError):
        nx.is_minimal_d_separator(g, {0}, {1}, {2})


def test_invalid_nodes_raise_error(asia_graph):
    """
    Test that graphs that have invalid nodes passed in raise errors.
    """
    # Check both set and node arguments
    with pytest.raises(nx.NodeNotFound):
        nx.is_d_separator(asia_graph, {0}, {1}, {2})
    with pytest.raises(nx.NodeNotFound):
        nx.is_d_separator(asia_graph, 0, 1, 2)
    with pytest.raises(nx.NodeNotFound):
        nx.is_minimal_d_separator(asia_graph, {0}, {1}, {2})
    with pytest.raises(nx.NodeNotFound):
        nx.is_minimal_d_separator(asia_graph, 0, 1, 2)
    with pytest.raises(nx.NodeNotFound):
        nx.find_minimal_d_separator(asia_graph, {0}, {1})
    with pytest.raises(nx.NodeNotFound):
        nx.find_minimal_d_separator(asia_graph, 0, 1)


def test_nondisjoint_node_sets_raise_error(collider_graph):
    """
    Test that error is raised when node sets aren't disjoint.
    """
    with pytest.raises(nx.NetworkXError):
        nx.is_d_separator(collider_graph, 0, 1, 0)
    with pytest.raises(nx.NetworkXError):
        nx.is_d_separator(collider_graph, 0, 2, 0)
    with pytest.raises(nx.NetworkXError):
        nx.is_d_separator(collider_graph, 0, 0, 1)
    with pytest.raises(nx.NetworkXError):
        nx.is_d_separator(collider_graph, 1, 0, 0)
    with pytest.raises(nx.NetworkXError):
        nx.find_minimal_d_separator(collider_graph, 0, 0)
    with pytest.raises(nx.NetworkXError):
        nx.find_minimal_d_separator(collider_graph, 0, 1, included=0)
    with pytest.raises(nx.NetworkXError):
        nx.find_minimal_d_separator(collider_graph, 1, 0, included=0)
    with pytest.raises(nx.NetworkXError):
        nx.is_minimal_d_separator(collider_graph, 0, 0, set())
    with pytest.raises(nx.NetworkXError):
        nx.is_minimal_d_separator(collider_graph, 0, 1, set(), included=0)
    with pytest.raises(nx.NetworkXError):
        nx.is_minimal_d_separator(collider_graph, 1, 0, set(), included=0)


def test_is_minimal_d_separator(
    large_collider_graph,
    chain_and_fork_graph,
    no_separating_set_graph,
    large_no_separating_set_graph,
    collider_trek_graph,
):
    # Case 1:
    # create a graph A -> B <- C
    # B -> D -> E;
    # B -> F;
    # G -> E;
    assert not nx.is_d_separator(large_collider_graph, {"B"}, {"E"}, set())

    # minimal set of the corresponding graph
    # for B and E should be (D,)
    Zmin = nx.find_minimal_d_separator(large_collider_graph, "B", "E")
    # check that the minimal d-separator is a d-separating set
    assert nx.is_d_separator(large_collider_graph, "B", "E", Zmin)
    # the minimal separating set should also pass the test for minimality
    assert nx.is_minimal_d_separator(large_collider_graph, "B", "E", Zmin)
    # function should also work with set arguments
    assert nx.is_minimal_d_separator(large_collider_graph, {"A", "B"}, {"G", "E"}, Zmin)
    assert Zmin == {"D"}

    # Case 2:
    # create a graph A -> B -> C
    # B -> D -> C;
    assert not nx.is_d_separator(chain_and_fork_graph, {"A"}, {"C"}, set())
    Zmin = nx.find_minimal_d_separator(chain_and_fork_graph, "A", "C")

    # the minimal separating set should pass the test for minimality
    assert nx.is_minimal_d_separator(chain_and_fork_graph, "A", "C", Zmin)
    assert Zmin == {"B"}
    Znotmin = Zmin.union({"D"})
    assert not nx.is_minimal_d_separator(chain_and_fork_graph, "A", "C", Znotmin)

    # Case 3:
    # create a graph A -> B

    # there is no m-separating set between A and B at all, so
    # no minimal m-separating set can exist
    assert not nx.is_d_separator(no_separating_set_graph, {"A"}, {"B"}, set())
    assert nx.find_minimal_d_separator(no_separating_set_graph, "A", "B") is None

    # Case 4:
    # create a graph A -> B with A <- C -> B

    # there is no m-separating set between A and B at all, so
    # no minimal m-separating set can exist
    # however, the algorithm will initially propose C as a
    # minimal (but invalid) separating set
    assert not nx.is_d_separator(large_no_separating_set_graph, {"A"}, {"B"}, {"C"})
    assert nx.find_minimal_d_separator(large_no_separating_set_graph, "A", "B") is None

    # Test `included` and `excluded` args
    # create graph A -> B <- C -> D
    assert nx.find_minimal_d_separator(collider_trek_graph, "A", "D", included="B") == {
        "B",
        "C",
    }
    assert (
        nx.find_minimal_d_separator(
            collider_trek_graph, "A", "D", included="B", restricted="B"
        )
        is None
    )


def test_is_minimal_d_separator_checks_dsep():
    """Test that is_minimal_d_separator checks for d-separation as well."""
    g = nx.DiGraph()
    g.add_edges_from(
        [
            ("A", "B"),
            ("A", "E"),
            ("B", "C"),
            ("B", "D"),
            ("D", "C"),
            ("D", "F"),
            ("E", "D"),
            ("E", "F"),
        ]
    )

    assert not nx.is_d_separator(g, {"C"}, {"F"}, {"D"})

    # since {'D'} and {} are not d-separators, we return false
    assert not nx.is_minimal_d_separator(g, "C", "F", {"D"})
    assert not nx.is_minimal_d_separator(g, "C", "F", set())


def test__reachable(large_collider_graph):
    reachable = nx.algorithms.d_separation._reachable
    g = large_collider_graph
    x = {"F", "D"}
    ancestors = {"A", "B", "C", "D", "F"}
    assert reachable(g, x, ancestors, {"B"}) == {"B", "F", "D"}
    assert reachable(g, x, ancestors, set()) == ancestors


def test_deprecations():
    G = nx.DiGraph([(0, 1), (1, 2)])
    with pytest.deprecated_call():
        nx.d_separated(G, 0, 2, {1})
    with pytest.deprecated_call():
        z = nx.minimal_d_separator(G, 0, 2)
