import pytest

import networkx as nx
from networkx.generators.classic import empty_graph
from networkx.utils import edges_equal, nodes_equal


class TestRelabel:
    def test_convert_node_labels_to_integers(self):
        # test that empty graph converts fine for all options
        G = empty_graph()
        H = nx.convert_node_labels_to_integers(G, 100)
        assert list(H.nodes()) == []
        assert list(H.edges()) == []

        for opt in ["default", "sorted", "increasing degree", "decreasing degree"]:
            G = empty_graph()
            H = nx.convert_node_labels_to_integers(G, 100, ordering=opt)
            assert list(H.nodes()) == []
            assert list(H.edges()) == []

        G = empty_graph()
        G.add_edges_from([("A", "B"), ("A", "C"), ("B", "C"), ("C", "D")])
        H = nx.convert_node_labels_to_integers(G)
        degH = (d for n, d in H.degree())
        degG = (d for n, d in G.degree())
        assert sorted(degH) == sorted(degG)

        H = nx.convert_node_labels_to_integers(G, 1000)
        degH = (d for n, d in H.degree())
        degG = (d for n, d in G.degree())
        assert sorted(degH) == sorted(degG)
        assert nodes_equal(H.nodes(), [1000, 1001, 1002, 1003])

        H = nx.convert_node_labels_to_integers(G, ordering="increasing degree")
        degH = (d for n, d in H.degree())
        degG = (d for n, d in G.degree())
        assert sorted(degH) == sorted(degG)
        assert H.degree(0) == 1
        assert H.degree(1) == 2
        assert H.degree(2) == 2
        assert H.degree(3) == 3

        H = nx.convert_node_labels_to_integers(G, ordering="decreasing degree")
        degH = (d for n, d in H.degree())
        degG = (d for n, d in G.degree())
        assert sorted(degH) == sorted(degG)
        assert H.degree(0) == 3
        assert H.degree(1) == 2
        assert H.degree(2) == 2
        assert H.degree(3) == 1

        H = nx.convert_node_labels_to_integers(
            G, ordering="increasing degree", label_attribute="label"
        )
        degH = (d for n, d in H.degree())
        degG = (d for n, d in G.degree())
        assert sorted(degH) == sorted(degG)
        assert H.degree(0) == 1
        assert H.degree(1) == 2
        assert H.degree(2) == 2
        assert H.degree(3) == 3

        # check mapping
        assert H.nodes[3]["label"] == "C"
        assert H.nodes[0]["label"] == "D"
        assert H.nodes[1]["label"] == "A" or H.nodes[2]["label"] == "A"
        assert H.nodes[1]["label"] == "B" or H.nodes[2]["label"] == "B"

    def test_convert_to_integers2(self):
        G = empty_graph()
        G.add_edges_from([("C", "D"), ("A", "B"), ("A", "C"), ("B", "C")])
        H = nx.convert_node_labels_to_integers(G, ordering="sorted")
        degH = (d for n, d in H.degree())
        degG = (d for n, d in G.degree())
        assert sorted(degH) == sorted(degG)

        H = nx.convert_node_labels_to_integers(
            G, ordering="sorted", label_attribute="label"
        )
        assert H.nodes[0]["label"] == "A"
        assert H.nodes[1]["label"] == "B"
        assert H.nodes[2]["label"] == "C"
        assert H.nodes[3]["label"] == "D"

    def test_convert_to_integers_raise(self):
        with pytest.raises(nx.NetworkXError):
            G = nx.Graph()
            H = nx.convert_node_labels_to_integers(G, ordering="increasing age")

    def test_relabel_nodes_copy(self):
        G = nx.empty_graph()
        G.add_edges_from([("A", "B"), ("A", "C"), ("B", "C"), ("C", "D")])
        mapping = {"A": "aardvark", "B": "bear", "C": "cat", "D": "dog"}
        H = nx.relabel_nodes(G, mapping)
        assert nodes_equal(H.nodes(), ["aardvark", "bear", "cat", "dog"])

    def test_relabel_nodes_function(self):
        G = nx.empty_graph()
        G.add_edges_from([("A", "B"), ("A", "C"), ("B", "C"), ("C", "D")])
        # function mapping no longer encouraged but works

        def mapping(n):
            return ord(n)

        H = nx.relabel_nodes(G, mapping)
        assert nodes_equal(H.nodes(), [65, 66, 67, 68])

    def test_relabel_nodes_callable_type(self):
        G = nx.path_graph(4)
        H = nx.relabel_nodes(G, str)
        assert nodes_equal(H.nodes, ["0", "1", "2", "3"])

    @pytest.mark.parametrize("non_mc", ("0123", ["0", "1", "2", "3"]))
    def test_relabel_nodes_non_mapping_or_callable(self, non_mc):
        """If `mapping` is neither a Callable or a Mapping, an exception
        should be raised."""
        G = nx.path_graph(4)
        with pytest.raises(AttributeError):
            nx.relabel_nodes(G, non_mc)

    def test_relabel_nodes_graph(self):
        G = nx.Graph([("A", "B"), ("A", "C"), ("B", "C"), ("C", "D")])
        mapping = {"A": "aardvark", "B": "bear", "C": "cat", "D": "dog"}
        H = nx.relabel_nodes(G, mapping)
        assert nodes_equal(H.nodes(), ["aardvark", "bear", "cat", "dog"])

    def test_relabel_nodes_orderedgraph(self):
        G = nx.Graph()
        G.add_nodes_from([1, 2, 3])
        G.add_edges_from([(1, 3), (2, 3)])
        mapping = {1: "a", 2: "b", 3: "c"}
        H = nx.relabel_nodes(G, mapping)
        assert list(H.nodes) == ["a", "b", "c"]

    def test_relabel_nodes_digraph(self):
        G = nx.DiGraph([("A", "B"), ("A", "C"), ("B", "C"), ("C", "D")])
        mapping = {"A": "aardvark", "B": "bear", "C": "cat", "D": "dog"}
        H = nx.relabel_nodes(G, mapping, copy=False)
        assert nodes_equal(H.nodes(), ["aardvark", "bear", "cat", "dog"])

    def test_relabel_nodes_multigraph(self):
        G = nx.MultiGraph([("a", "b"), ("a", "b")])
        mapping = {"a": "aardvark", "b": "bear"}
        G = nx.relabel_nodes(G, mapping, copy=False)
        assert nodes_equal(G.nodes(), ["aardvark", "bear"])
        assert edges_equal(G.edges(), [("aardvark", "bear"), ("aardvark", "bear")])

    def test_relabel_nodes_multidigraph(self):
        G = nx.MultiDiGraph([("a", "b"), ("a", "b")])
        mapping = {"a": "aardvark", "b": "bear"}
        G = nx.relabel_nodes(G, mapping, copy=False)
        assert nodes_equal(G.nodes(), ["aardvark", "bear"])
        assert edges_equal(G.edges(), [("aardvark", "bear"), ("aardvark", "bear")])

    def test_relabel_isolated_nodes_to_same(self):
        G = nx.Graph()
        G.add_nodes_from(range(4))
        mapping = {1: 1}
        H = nx.relabel_nodes(G, mapping, copy=False)
        assert nodes_equal(H.nodes(), list(range(4)))

    def test_relabel_nodes_missing(self):
        G = nx.Graph([("A", "B"), ("A", "C"), ("B", "C"), ("C", "D")])
        mapping = {0: "aardvark"}
        # copy=True
        H = nx.relabel_nodes(G, mapping, copy=True)
        assert nodes_equal(H.nodes, G.nodes)
        # copy=False
        GG = G.copy()
        nx.relabel_nodes(G, mapping, copy=False)
        assert nodes_equal(G.nodes, GG.nodes)

    def test_relabel_copy_name(self):
        G = nx.Graph()
        H = nx.relabel_nodes(G, {}, copy=True)
        assert H.graph == G.graph
        H = nx.relabel_nodes(G, {}, copy=False)
        assert H.graph == G.graph
        G.name = "first"
        H = nx.relabel_nodes(G, {}, copy=True)
        assert H.graph == G.graph
        H = nx.relabel_nodes(G, {}, copy=False)
        assert H.graph == G.graph

    def test_relabel_toposort(self):
        K5 = nx.complete_graph(4)
        G = nx.complete_graph(4)
        G = nx.relabel_nodes(G, {i: i + 1 for i in range(4)}, copy=False)
        assert nx.is_isomorphic(K5, G)
        G = nx.complete_graph(4)
        G = nx.relabel_nodes(G, {i: i - 1 for i in range(4)}, copy=False)
        assert nx.is_isomorphic(K5, G)

    def test_relabel_selfloop(self):
        G = nx.DiGraph([(1, 1), (1, 2), (2, 3)])
        G = nx.relabel_nodes(G, {1: "One", 2: "Two", 3: "Three"}, copy=False)
        assert nodes_equal(G.nodes(), ["One", "Three", "Two"])
        G = nx.MultiDiGraph([(1, 1), (1, 2), (2, 3)])
        G = nx.relabel_nodes(G, {1: "One", 2: "Two", 3: "Three"}, copy=False)
        assert nodes_equal(G.nodes(), ["One", "Three", "Two"])
        G = nx.MultiDiGraph([(1, 1)])
        G = nx.relabel_nodes(G, {1: 0}, copy=False)
        assert nodes_equal(G.nodes(), [0])

    def test_relabel_multidigraph_inout_merge_nodes(self):
        for MG in (nx.MultiGraph, nx.MultiDiGraph):
            for cc in (True, False):
                G = MG([(0, 4), (1, 4), (4, 2), (4, 3)])
                G[0][4][0]["value"] = "a"
                G[1][4][0]["value"] = "b"
                G[4][2][0]["value"] = "c"
                G[4][3][0]["value"] = "d"
                G.add_edge(0, 4, key="x", value="e")
                G.add_edge(4, 3, key="x", value="f")
                mapping = {0: 9, 1: 9, 2: 9, 3: 9}
                H = nx.relabel_nodes(G, mapping, copy=cc)
                # No ordering on keys enforced
                assert {"value": "a"} in H[9][4].values()
                assert {"value": "b"} in H[9][4].values()
                assert {"value": "c"} in H[4][9].values()
                assert len(H[4][9]) == 3 if G.is_directed() else 6
                assert {"value": "d"} in H[4][9].values()
                assert {"value": "e"} in H[9][4].values()
                assert {"value": "f"} in H[4][9].values()
                assert len(H[9][4]) == 3 if G.is_directed() else 6

    def test_relabel_multigraph_merge_inplace(self):
        G = nx.MultiGraph([(0, 1), (0, 2), (0, 3), (0, 1), (0, 2), (0, 3)])
        G[0][1][0]["value"] = "a"
        G[0][2][0]["value"] = "b"
        G[0][3][0]["value"] = "c"
        mapping = {1: 4, 2: 4, 3: 4}
        nx.relabel_nodes(G, mapping, copy=False)
        # No ordering on keys enforced
        assert {"value": "a"} in G[0][4].values()
        assert {"value": "b"} in G[0][4].values()
        assert {"value": "c"} in G[0][4].values()

    def test_relabel_multidigraph_merge_inplace(self):
        G = nx.MultiDiGraph([(0, 1), (0, 2), (0, 3)])
        G[0][1][0]["value"] = "a"
        G[0][2][0]["value"] = "b"
        G[0][3][0]["value"] = "c"
        mapping = {1: 4, 2: 4, 3: 4}
        nx.relabel_nodes(G, mapping, copy=False)
        # No ordering on keys enforced
        assert {"value": "a"} in G[0][4].values()
        assert {"value": "b"} in G[0][4].values()
        assert {"value": "c"} in G[0][4].values()

    def test_relabel_multidigraph_inout_copy(self):
        G = nx.MultiDiGraph([(0, 4), (1, 4), (4, 2), (4, 3)])
        G[0][4][0]["value"] = "a"
        G[1][4][0]["value"] = "b"
        G[4][2][0]["value"] = "c"
        G[4][3][0]["value"] = "d"
        G.add_edge(0, 4, key="x", value="e")
        G.add_edge(4, 3, key="x", value="f")
        mapping = {0: 9, 1: 9, 2: 9, 3: 9}
        H = nx.relabel_nodes(G, mapping, copy=True)
        # No ordering on keys enforced
        assert {"value": "a"} in H[9][4].values()
        assert {"value": "b"} in H[9][4].values()
        assert {"value": "c"} in H[4][9].values()
        assert len(H[4][9]) == 3
        assert {"value": "d"} in H[4][9].values()
        assert {"value": "e"} in H[9][4].values()
        assert {"value": "f"} in H[4][9].values()
        assert len(H[9][4]) == 3

    def test_relabel_multigraph_merge_copy(self):
        G = nx.MultiGraph([(0, 1), (0, 2), (0, 3)])
        G[0][1][0]["value"] = "a"
        G[0][2][0]["value"] = "b"
        G[0][3][0]["value"] = "c"
        mapping = {1: 4, 2: 4, 3: 4}
        H = nx.relabel_nodes(G, mapping, copy=True)
        assert {"value": "a"} in H[0][4].values()
        assert {"value": "b"} in H[0][4].values()
        assert {"value": "c"} in H[0][4].values()

    def test_relabel_multidigraph_merge_copy(self):
        G = nx.MultiDiGraph([(0, 1), (0, 2), (0, 3)])
        G[0][1][0]["value"] = "a"
        G[0][2][0]["value"] = "b"
        G[0][3][0]["value"] = "c"
        mapping = {1: 4, 2: 4, 3: 4}
        H = nx.relabel_nodes(G, mapping, copy=True)
        assert {"value": "a"} in H[0][4].values()
        assert {"value": "b"} in H[0][4].values()
        assert {"value": "c"} in H[0][4].values()

    def test_relabel_multigraph_nonnumeric_key(self):
        for MG in (nx.MultiGraph, nx.MultiDiGraph):
            for cc in (True, False):
                G = nx.MultiGraph()
                G.add_edge(0, 1, key="I", value="a")
                G.add_edge(0, 2, key="II", value="b")
                G.add_edge(0, 3, key="II", value="c")
                mapping = {1: 4, 2: 4, 3: 4}
                nx.relabel_nodes(G, mapping, copy=False)
                assert {"value": "a"} in G[0][4].values()
                assert {"value": "b"} in G[0][4].values()
                assert {"value": "c"} in G[0][4].values()
                assert 0 in G[0][4]
                assert "I" in G[0][4]
                assert "II" in G[0][4]

    def test_relabel_circular(self):
        G = nx.path_graph(3)
        mapping = {0: 1, 1: 0}
        H = nx.relabel_nodes(G, mapping, copy=True)
        with pytest.raises(nx.NetworkXUnfeasible):
            H = nx.relabel_nodes(G, mapping, copy=False)

    def test_relabel_preserve_node_order_full_mapping_with_copy_true(self):
        G = nx.path_graph(3)
        original_order = list(G.nodes())
        mapping = {2: "a", 1: "b", 0: "c"}  # dictionary keys out of order on purpose
        H = nx.relabel_nodes(G, mapping, copy=True)
        new_order = list(H.nodes())
        assert [mapping.get(i, i) for i in original_order] == new_order

    def test_relabel_preserve_node_order_full_mapping_with_copy_false(self):
        G = nx.path_graph(3)
        original_order = list(G)
        mapping = {2: "a", 1: "b", 0: "c"}  # dictionary keys out of order on purpose
        H = nx.relabel_nodes(G, mapping, copy=False)
        new_order = list(H)
        assert [mapping.get(i, i) for i in original_order] == new_order

    def test_relabel_preserve_node_order_partial_mapping_with_copy_true(self):
        G = nx.path_graph(3)
        original_order = list(G)
        mapping = {1: "a", 0: "b"}  # partial mapping and keys out of order on purpose
        H = nx.relabel_nodes(G, mapping, copy=True)
        new_order = list(H)
        assert [mapping.get(i, i) for i in original_order] == new_order

    def test_relabel_preserve_node_order_partial_mapping_with_copy_false(self):
        G = nx.path_graph(3)
        original_order = list(G)
        mapping = {1: "a", 0: "b"}  # partial mapping and keys out of order on purpose
        H = nx.relabel_nodes(G, mapping, copy=False)
        new_order = list(H)
        assert [mapping.get(i, i) for i in original_order] != new_order
