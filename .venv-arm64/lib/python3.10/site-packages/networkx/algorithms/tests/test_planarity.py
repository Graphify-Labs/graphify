import pytest

import networkx as nx
from networkx.algorithms.planarity import (
    check_planarity_recursive,
    get_counterexample,
    get_counterexample_recursive,
)


class TestLRPlanarity:
    """Nose Unit tests for the :mod:`networkx.algorithms.planarity` module.

    Tests three things:
    1. Check that the result is correct
        (returns planar if and only if the graph is actually planar)
    2. In case a counter example is returned: Check if it is correct
    3. In case an embedding is returned: Check if its actually an embedding
    """

    @staticmethod
    def check_graph(G, is_planar=None):
        """Raises an exception if the lr_planarity check returns a wrong result

        Parameters
        ----------
        G : NetworkX graph
        is_planar : bool
            The expected result of the planarity check.
            If set to None only counter example or embedding are verified.

        """

        # obtain results of planarity check
        is_planar_lr, result = nx.check_planarity(G, True)
        is_planar_lr_rec, result_rec = check_planarity_recursive(G, True)

        if is_planar is not None:
            # set a message for the assert
            if is_planar:
                msg = "Wrong planarity check result. Should be planar."
            else:
                msg = "Wrong planarity check result. Should be non-planar."

            # check if the result is as expected
            assert is_planar == is_planar_lr, msg
            assert is_planar == is_planar_lr_rec, msg

        if is_planar_lr:
            # check embedding
            check_embedding(G, result)
            check_embedding(G, result_rec)
        else:
            # check counter example
            check_counterexample(G, result)
            check_counterexample(G, result_rec)

    def test_simple_planar_graph(self):
        e = [
            (1, 2),
            (2, 3),
            (3, 4),
            (4, 6),
            (6, 7),
            (7, 1),
            (1, 5),
            (5, 2),
            (2, 4),
            (4, 5),
            (5, 7),
        ]
        self.check_graph(nx.Graph(e), is_planar=True)

    def test_planar_with_selfloop(self):
        e = [
            (1, 1),
            (2, 2),
            (3, 3),
            (4, 4),
            (5, 5),
            (1, 2),
            (1, 3),
            (1, 5),
            (2, 5),
            (2, 4),
            (3, 4),
            (3, 5),
            (4, 5),
        ]
        self.check_graph(nx.Graph(e), is_planar=True)

    def test_k3_3(self):
        self.check_graph(nx.complete_bipartite_graph(3, 3), is_planar=False)

    def test_k5(self):
        self.check_graph(nx.complete_graph(5), is_planar=False)

    def test_multiple_components_planar(self):
        e = [(1, 2), (2, 3), (3, 1), (4, 5), (5, 6), (6, 4)]
        self.check_graph(nx.Graph(e), is_planar=True)

    def test_multiple_components_non_planar(self):
        G = nx.complete_graph(5)
        # add another planar component to the non planar component
        # G stays non planar
        G.add_edges_from([(6, 7), (7, 8), (8, 6)])
        self.check_graph(G, is_planar=False)

    def test_non_planar_with_selfloop(self):
        G = nx.complete_graph(5)
        # add self loops
        for i in range(5):
            G.add_edge(i, i)
        self.check_graph(G, is_planar=False)

    def test_non_planar1(self):
        # tests a graph that has no subgraph directly isomorph to K5 or K3_3
        e = [
            (1, 5),
            (1, 6),
            (1, 7),
            (2, 6),
            (2, 3),
            (3, 5),
            (3, 7),
            (4, 5),
            (4, 6),
            (4, 7),
        ]
        self.check_graph(nx.Graph(e), is_planar=False)

    def test_loop(self):
        # test a graph with a selfloop
        e = [(1, 2), (2, 2)]
        G = nx.Graph(e)
        self.check_graph(G, is_planar=True)

    def test_comp(self):
        # test multiple component graph
        e = [(1, 2), (3, 4)]
        G = nx.Graph(e)
        G.remove_edge(1, 2)
        self.check_graph(G, is_planar=True)

    def test_goldner_harary(self):
        # test goldner-harary graph (a maximal planar graph)
        e = [
            (1, 2),
            (1, 3),
            (1, 4),
            (1, 5),
            (1, 7),
            (1, 8),
            (1, 10),
            (1, 11),
            (2, 3),
            (2, 4),
            (2, 6),
            (2, 7),
            (2, 9),
            (2, 10),
            (2, 11),
            (3, 4),
            (4, 5),
            (4, 6),
            (4, 7),
            (5, 7),
            (6, 7),
            (7, 8),
            (7, 9),
            (7, 10),
            (8, 10),
            (9, 10),
            (10, 11),
        ]
        G = nx.Graph(e)
        self.check_graph(G, is_planar=True)

    def test_planar_multigraph(self):
        G = nx.MultiGraph([(1, 2), (1, 2), (1, 2), (1, 2), (2, 3), (3, 1)])
        self.check_graph(G, is_planar=True)

    def test_non_planar_multigraph(self):
        G = nx.MultiGraph(nx.complete_graph(5))
        G.add_edges_from([(1, 2)] * 5)
        self.check_graph(G, is_planar=False)

    def test_planar_digraph(self):
        G = nx.DiGraph([(1, 2), (2, 3), (2, 4), (4, 1), (4, 2), (1, 4), (3, 2)])
        self.check_graph(G, is_planar=True)

    def test_non_planar_digraph(self):
        G = nx.DiGraph(nx.complete_graph(5))
        G.remove_edge(1, 2)
        G.remove_edge(4, 1)
        self.check_graph(G, is_planar=False)

    def test_single_component(self):
        # Test a graph with only a single node
        G = nx.Graph()
        G.add_node(1)
        self.check_graph(G, is_planar=True)

    def test_graph1(self):
        G = nx.Graph(
            [
                (3, 10),
                (2, 13),
                (1, 13),
                (7, 11),
                (0, 8),
                (8, 13),
                (0, 2),
                (0, 7),
                (0, 10),
                (1, 7),
            ]
        )
        self.check_graph(G, is_planar=True)

    def test_graph2(self):
        G = nx.Graph(
            [
                (1, 2),
                (4, 13),
                (0, 13),
                (4, 5),
                (7, 10),
                (1, 7),
                (0, 3),
                (2, 6),
                (5, 6),
                (7, 13),
                (4, 8),
                (0, 8),
                (0, 9),
                (2, 13),
                (6, 7),
                (3, 6),
                (2, 8),
            ]
        )
        self.check_graph(G, is_planar=False)

    def test_graph3(self):
        G = nx.Graph(
            [
                (0, 7),
                (3, 11),
                (3, 4),
                (8, 9),
                (4, 11),
                (1, 7),
                (1, 13),
                (1, 11),
                (3, 5),
                (5, 7),
                (1, 3),
                (0, 4),
                (5, 11),
                (5, 13),
            ]
        )
        self.check_graph(G, is_planar=False)

    def test_counterexample_planar(self):
        with pytest.raises(nx.NetworkXException):
            # Try to get a counterexample of a planar graph
            G = nx.Graph()
            G.add_node(1)
            get_counterexample(G)

    def test_counterexample_planar_recursive(self):
        with pytest.raises(nx.NetworkXException):
            # Try to get a counterexample of a planar graph
            G = nx.Graph()
            G.add_node(1)
            get_counterexample_recursive(G)

    def test_edge_removal_from_planar_embedding(self):
        # PlanarEmbedding.check_structure() must succeed after edge removal
        edges = ((0, 1), (1, 2), (2, 3), (3, 4), (4, 0), (0, 2), (0, 3))
        G = nx.Graph(edges)
        cert, P = nx.check_planarity(G)
        assert cert is True
        P.remove_edge(0, 2)
        self.check_graph(P, is_planar=True)
        P.add_half_edge_ccw(1, 3, 2)
        P.add_half_edge_cw(3, 1, 2)
        self.check_graph(P, is_planar=True)
        P.remove_edges_from(((0, 3), (1, 3)))
        self.check_graph(P, is_planar=True)


def check_embedding(G, embedding):
    """Raises an exception if the combinatorial embedding is not correct

    Parameters
    ----------
    G : NetworkX graph
    embedding : a dict mapping nodes to a list of edges
        This specifies the ordering of the outgoing edges from a node for
        a combinatorial embedding

    Notes
    -----
    Checks the following things:
        - The type of the embedding is correct
        - The nodes and edges match the original graph
        - Every half edge has its matching opposite half edge
        - No intersections of edges (checked by Euler's formula)
    """

    if not isinstance(embedding, nx.PlanarEmbedding):
        raise nx.NetworkXException("Bad embedding. Not of type nx.PlanarEmbedding")

    # Check structure
    embedding.check_structure()

    # Check that graphs are equivalent

    assert set(G.nodes) == set(
        embedding.nodes
    ), "Bad embedding. Nodes don't match the original graph."

    # Check that the edges are equal
    g_edges = set()
    for edge in G.edges:
        if edge[0] != edge[1]:
            g_edges.add((edge[0], edge[1]))
            g_edges.add((edge[1], edge[0]))
    assert g_edges == set(
        embedding.edges
    ), "Bad embedding. Edges don't match the original graph."


def check_counterexample(G, sub_graph):
    """Raises an exception if the counterexample is wrong.

    Parameters
    ----------
    G : NetworkX graph
    subdivision_nodes : set
        A set of nodes inducing a subgraph as a counterexample
    """
    # 1. Create the sub graph
    sub_graph = nx.Graph(sub_graph)

    # 2. Remove self loops
    for u in sub_graph:
        if sub_graph.has_edge(u, u):
            sub_graph.remove_edge(u, u)

    # keep track of nodes we might need to contract
    contract = list(sub_graph)

    # 3. Contract Edges
    while len(contract) > 0:
        contract_node = contract.pop()
        if contract_node not in sub_graph:
            # Node was already contracted
            continue
        degree = sub_graph.degree[contract_node]
        # Check if we can remove the node
        if degree == 2:
            # Get the two neighbors
            neighbors = iter(sub_graph[contract_node])
            u = next(neighbors)
            v = next(neighbors)
            # Save nodes for later
            contract.append(u)
            contract.append(v)
            # Contract edge
            sub_graph.remove_node(contract_node)
            sub_graph.add_edge(u, v)

    # 4. Check for isomorphism with K5 or K3_3 graphs
    if len(sub_graph) == 5:
        if not nx.is_isomorphic(nx.complete_graph(5), sub_graph):
            raise nx.NetworkXException("Bad counter example.")
    elif len(sub_graph) == 6:
        if not nx.is_isomorphic(nx.complete_bipartite_graph(3, 3), sub_graph):
            raise nx.NetworkXException("Bad counter example.")
    else:
        raise nx.NetworkXException("Bad counter example.")


class TestPlanarEmbeddingClass:
    def test_add_half_edge(self):
        embedding = nx.PlanarEmbedding()
        embedding.add_half_edge(0, 1)
        with pytest.raises(
            nx.NetworkXException, match="Invalid clockwise reference node."
        ):
            embedding.add_half_edge(0, 2, cw=3)
        with pytest.raises(
            nx.NetworkXException, match="Invalid counterclockwise reference node."
        ):
            embedding.add_half_edge(0, 2, ccw=3)
        with pytest.raises(
            nx.NetworkXException, match="Only one of cw/ccw can be specified."
        ):
            embedding.add_half_edge(0, 2, cw=1, ccw=1)
        with pytest.raises(
            nx.NetworkXException,
            match=(
                r"Node already has out-half-edge\(s\), either"
                " cw or ccw reference node required."
            ),
        ):
            embedding.add_half_edge(0, 2)
        # these should work
        embedding.add_half_edge(0, 2, cw=1)
        embedding.add_half_edge(0, 3, ccw=1)
        assert sorted(embedding.edges(data=True)) == [
            (0, 1, {"ccw": 2, "cw": 3}),
            (0, 2, {"cw": 1, "ccw": 3}),
            (0, 3, {"cw": 2, "ccw": 1}),
        ]

    def test_get_data(self):
        embedding = self.get_star_embedding(4)
        data = embedding.get_data()
        data_cmp = {0: [3, 2, 1], 1: [0], 2: [0], 3: [0]}
        assert data == data_cmp

    def test_edge_removal(self):
        embedding = nx.PlanarEmbedding()
        embedding.set_data(
            {
                1: [2, 5, 7],
                2: [1, 3, 4, 5],
                3: [2, 4],
                4: [3, 6, 5, 2],
                5: [7, 1, 2, 4],
                6: [4, 7],
                7: [6, 1, 5],
            }
        )
        # remove_edges_from() calls remove_edge(), so both are tested here
        embedding.remove_edges_from(((5, 4), (1, 5)))
        embedding.check_structure()
        embedding_expected = nx.PlanarEmbedding()
        embedding_expected.set_data(
            {
                1: [2, 7],
                2: [1, 3, 4, 5],
                3: [2, 4],
                4: [3, 6, 2],
                5: [7, 2],
                6: [4, 7],
                7: [6, 1, 5],
            }
        )
        assert nx.utils.graphs_equal(embedding, embedding_expected)

    def test_missing_edge_orientation(self):
        embedding = nx.PlanarEmbedding({1: {2: {}}, 2: {1: {}}})
        with pytest.raises(nx.NetworkXException):
            # Invalid structure because the orientation of the edge was not set
            embedding.check_structure()

    def test_invalid_edge_orientation(self):
        embedding = nx.PlanarEmbedding(
            {
                1: {2: {"cw": 2, "ccw": 2}},
                2: {1: {"cw": 1, "ccw": 1}},
                1: {3: {}},
                3: {1: {}},
            }
        )
        with pytest.raises(nx.NetworkXException):
            embedding.check_structure()

    def test_missing_half_edge(self):
        embedding = nx.PlanarEmbedding()
        embedding.add_half_edge(1, 2)
        with pytest.raises(nx.NetworkXException):
            # Invalid structure because other half edge is missing
            embedding.check_structure()

    def test_not_fulfilling_euler_formula(self):
        embedding = nx.PlanarEmbedding()
        for i in range(5):
            ref = None
            for j in range(5):
                if i != j:
                    embedding.add_half_edge(i, j, cw=ref)
                    ref = j
        with pytest.raises(nx.NetworkXException):
            embedding.check_structure()

    def test_missing_reference(self):
        embedding = nx.PlanarEmbedding()
        with pytest.raises(nx.NetworkXException, match="Invalid reference node."):
            embedding.add_half_edge(1, 2, ccw=3)

    def test_connect_components(self):
        embedding = nx.PlanarEmbedding()
        embedding.connect_components(1, 2)

    def test_successful_face_traversal(self):
        embedding = nx.PlanarEmbedding()
        embedding.add_half_edge(1, 2)
        embedding.add_half_edge(2, 1)
        face = embedding.traverse_face(1, 2)
        assert face == [1, 2]

    def test_unsuccessful_face_traversal(self):
        embedding = nx.PlanarEmbedding(
            {1: {2: {"cw": 3, "ccw": 2}}, 2: {1: {"cw": 3, "ccw": 1}}}
        )
        with pytest.raises(nx.NetworkXException):
            embedding.traverse_face(1, 2)

    def test_forbidden_methods(self):
        embedding = nx.PlanarEmbedding()
        embedding.add_node(42)  # no exception
        embedding.add_nodes_from([(23, 24)])  # no exception
        with pytest.raises(NotImplementedError):
            embedding.add_edge(1, 3)
        with pytest.raises(NotImplementedError):
            embedding.add_edges_from([(0, 2), (1, 4)])
        with pytest.raises(NotImplementedError):
            embedding.add_weighted_edges_from([(0, 2, 350), (1, 4, 125)])

    @staticmethod
    def get_star_embedding(n):
        embedding = nx.PlanarEmbedding()
        ref = None
        for i in range(1, n):
            embedding.add_half_edge(0, i, cw=ref)
            ref = i
            embedding.add_half_edge(i, 0)
        return embedding
