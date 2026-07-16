import itertools as it

import pytest

import networkx as nx
from networkx import vf2pp_is_isomorphic, vf2pp_isomorphism

labels_same = ["blue"]

labels_many = [
    "white",
    "red",
    "blue",
    "green",
    "orange",
    "black",
    "purple",
    "yellow",
    "brown",
    "cyan",
    "solarized",
    "pink",
    "none",
]


class TestPreCheck:
    def test_first_graph_empty(self):
        G1 = nx.Graph()
        G2 = nx.Graph([(0, 1), (1, 2)])
        assert not vf2pp_is_isomorphic(G1, G2)

    def test_second_graph_empty(self):
        G1 = nx.Graph([(0, 1), (1, 2)])
        G2 = nx.Graph()
        assert not vf2pp_is_isomorphic(G1, G2)

    def test_different_order1(self):
        G1 = nx.path_graph(5)
        G2 = nx.path_graph(6)
        assert not vf2pp_is_isomorphic(G1, G2)

    def test_different_order2(self):
        G1 = nx.barbell_graph(100, 20)
        G2 = nx.barbell_graph(101, 20)
        assert not vf2pp_is_isomorphic(G1, G2)

    def test_different_order3(self):
        G1 = nx.complete_graph(7)
        G2 = nx.complete_graph(8)
        assert not vf2pp_is_isomorphic(G1, G2)

    def test_different_degree_sequences1(self):
        G1 = nx.Graph([(0, 1), (0, 2), (1, 2), (1, 3), (0, 4)])
        G2 = nx.Graph([(0, 1), (0, 2), (1, 2), (1, 3), (0, 4), (2, 5)])
        assert not vf2pp_is_isomorphic(G1, G2)

        G2.remove_node(3)
        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(["a"]))), "label")
        nx.set_node_attributes(G2, dict(zip(G2, it.cycle("a"))), "label")

        assert vf2pp_is_isomorphic(G1, G2)

    def test_different_degree_sequences2(self):
        G1 = nx.Graph(
            [
                (0, 1),
                (1, 2),
                (0, 2),
                (2, 3),
                (3, 4),
                (4, 5),
                (5, 6),
                (6, 3),
                (4, 7),
                (7, 8),
                (8, 3),
            ]
        )
        G2 = G1.copy()
        G2.add_edge(8, 0)
        assert not vf2pp_is_isomorphic(G1, G2)

        G1.add_edge(6, 1)
        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(["a"]))), "label")
        nx.set_node_attributes(G2, dict(zip(G2, it.cycle("a"))), "label")

        assert vf2pp_is_isomorphic(G1, G2)

    def test_different_degree_sequences3(self):
        G1 = nx.Graph([(0, 1), (0, 2), (1, 2), (2, 3), (2, 4), (3, 4), (2, 5), (2, 6)])
        G2 = nx.Graph(
            [(0, 1), (0, 6), (0, 2), (1, 2), (2, 3), (2, 4), (3, 4), (2, 5), (2, 6)]
        )
        assert not vf2pp_is_isomorphic(G1, G2)

        G1.add_edge(3, 5)
        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(["a"]))), "label")
        nx.set_node_attributes(G2, dict(zip(G2, it.cycle("a"))), "label")

        assert vf2pp_is_isomorphic(G1, G2)

    def test_label_distribution(self):
        G1 = nx.Graph([(0, 1), (0, 2), (1, 2), (2, 3), (2, 4), (3, 4), (2, 5), (2, 6)])
        G2 = nx.Graph([(0, 1), (0, 2), (1, 2), (2, 3), (2, 4), (3, 4), (2, 5), (2, 6)])

        colors1 = ["blue", "blue", "blue", "yellow", "black", "purple", "purple"]
        colors2 = ["blue", "blue", "yellow", "yellow", "black", "purple", "purple"]

        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(colors1[::-1]))), "label")
        nx.set_node_attributes(G2, dict(zip(G2, it.cycle(colors2[::-1]))), "label")

        assert not vf2pp_is_isomorphic(G1, G2, node_label="label")
        G2.nodes[3]["label"] = "blue"
        assert vf2pp_is_isomorphic(G1, G2, node_label="label")


class TestAllGraphTypesEdgeCases:
    @pytest.mark.parametrize("graph_type", (nx.Graph, nx.MultiGraph, nx.DiGraph))
    def test_both_graphs_empty(self, graph_type):
        G = graph_type()
        H = graph_type()
        assert vf2pp_isomorphism(G, H) is None

        G.add_node(0)

        assert vf2pp_isomorphism(G, H) is None
        assert vf2pp_isomorphism(H, G) is None

        H.add_node(0)
        assert vf2pp_isomorphism(G, H) == {0: 0}

    @pytest.mark.parametrize("graph_type", (nx.Graph, nx.MultiGraph, nx.DiGraph))
    def test_first_graph_empty(self, graph_type):
        G = graph_type()
        H = graph_type([(0, 1)])
        assert vf2pp_isomorphism(G, H) is None

    @pytest.mark.parametrize("graph_type", (nx.Graph, nx.MultiGraph, nx.DiGraph))
    def test_second_graph_empty(self, graph_type):
        G = graph_type([(0, 1)])
        H = graph_type()
        assert vf2pp_isomorphism(G, H) is None


class TestGraphISOVF2pp:
    def test_custom_graph1_same_labels(self):
        G1 = nx.Graph()

        mapped = {1: "A", 2: "B", 3: "C", 4: "D", 5: "Z", 6: "E"}
        edges1 = [(1, 2), (1, 3), (1, 4), (2, 3), (2, 6), (3, 4), (5, 1), (5, 2)]

        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)
        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_same))), "label")
        nx.set_node_attributes(G2, dict(zip(G2, it.cycle(labels_same))), "label")
        assert vf2pp_isomorphism(G1, G2, node_label="label")

        # Add edge making G1 symmetrical
        G1.add_edge(3, 7)
        G1.nodes[7]["label"] = "blue"
        assert vf2pp_isomorphism(G1, G2, node_label="label") is None

        # Make G2 isomorphic to G1
        G2.add_edges_from([(mapped[3], "X"), (mapped[6], mapped[5])])
        G1.add_edge(4, 7)
        G2.nodes["X"]["label"] = "blue"
        assert vf2pp_isomorphism(G1, G2, node_label="label")

        # Re-structure maintaining isomorphism
        G1.remove_edges_from([(1, 4), (1, 3)])
        G2.remove_edges_from([(mapped[1], mapped[5]), (mapped[1], mapped[2])])
        assert vf2pp_isomorphism(G1, G2, node_label="label")

    def test_custom_graph1_different_labels(self):
        G1 = nx.Graph()

        mapped = {1: "A", 2: "B", 3: "C", 4: "D", 5: "Z", 6: "E"}
        edges1 = [(1, 2), (1, 3), (1, 4), (2, 3), (2, 6), (3, 4), (5, 1), (5, 2)]

        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)
        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_many))), "label")
        nx.set_node_attributes(
            G2,
            dict(zip([mapped[n] for n in G1], it.cycle(labels_many))),
            "label",
        )
        assert vf2pp_isomorphism(G1, G2, node_label="label") == mapped

    def test_custom_graph2_same_labels(self):
        G1 = nx.Graph()

        mapped = {1: "A", 2: "C", 3: "D", 4: "E", 5: "G", 7: "B", 6: "F"}
        edges1 = [(1, 2), (1, 5), (5, 6), (2, 3), (2, 4), (3, 4), (4, 5), (2, 7)]

        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)
        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_same))), "label")
        nx.set_node_attributes(G2, dict(zip(G2, it.cycle(labels_same))), "label")

        assert vf2pp_isomorphism(G1, G2, node_label="label")

        # Obtain two isomorphic subgraphs from the graph
        G2.remove_edge(mapped[1], mapped[2])
        G2.add_edge(mapped[1], mapped[4])
        H1 = nx.Graph(G1.subgraph([2, 3, 4, 7]))
        H2 = nx.Graph(G2.subgraph([mapped[1], mapped[4], mapped[5], mapped[6]]))
        assert vf2pp_isomorphism(H1, H2, node_label="label")

        # Add edges maintaining isomorphism
        H1.add_edges_from([(3, 7), (4, 7)])
        H2.add_edges_from([(mapped[1], mapped[6]), (mapped[4], mapped[6])])
        assert vf2pp_isomorphism(H1, H2, node_label="label")

    def test_custom_graph2_different_labels(self):
        G1 = nx.Graph()

        mapped = {1: "A", 2: "C", 3: "D", 4: "E", 5: "G", 7: "B", 6: "F"}
        edges1 = [(1, 2), (1, 5), (5, 6), (2, 3), (2, 4), (3, 4), (4, 5), (2, 7)]

        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)
        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_many))), "label")
        nx.set_node_attributes(
            G2,
            dict(zip([mapped[n] for n in G1], it.cycle(labels_many))),
            "label",
        )

        # Adding new nodes
        G1.add_node(0)
        G2.add_node("Z")
        G1.nodes[0]["label"] = G1.nodes[1]["label"]
        G2.nodes["Z"]["label"] = G1.nodes[1]["label"]
        mapped.update({0: "Z"})

        assert vf2pp_isomorphism(G1, G2, node_label="label") == mapped

        # Change the color of one of the nodes
        G2.nodes["Z"]["label"] = G1.nodes[2]["label"]
        assert vf2pp_isomorphism(G1, G2, node_label="label") is None

        # Add an extra edge
        G1.nodes[0]["label"] = "blue"
        G2.nodes["Z"]["label"] = "blue"
        G1.add_edge(0, 1)

        assert vf2pp_isomorphism(G1, G2, node_label="label") is None

        # Add extra edge to both
        G2.add_edge("Z", "A")
        assert vf2pp_isomorphism(G1, G2, node_label="label") == mapped

    def test_custom_graph3_same_labels(self):
        G1 = nx.Graph()

        mapped = {1: 9, 2: 8, 3: 7, 4: 6, 5: 3, 8: 5, 9: 4, 7: 1, 6: 2}
        edges1 = [
            (1, 2),
            (1, 3),
            (2, 3),
            (3, 4),
            (4, 5),
            (4, 7),
            (4, 9),
            (5, 8),
            (8, 9),
            (5, 6),
            (6, 7),
            (5, 2),
        ]
        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)
        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_same))), "label")
        nx.set_node_attributes(G2, dict(zip(G2, it.cycle(labels_same))), "label")
        assert vf2pp_isomorphism(G1, G2, node_label="label")

        # Connect nodes maintaining symmetry
        G1.add_edges_from([(6, 9), (7, 8)])
        G2.add_edges_from([(mapped[6], mapped[8]), (mapped[7], mapped[9])])
        assert vf2pp_isomorphism(G1, G2, node_label="label") is None

        # Make isomorphic
        G1.add_edges_from([(6, 8), (7, 9)])
        G2.add_edges_from([(mapped[6], mapped[9]), (mapped[7], mapped[8])])
        assert vf2pp_isomorphism(G1, G2, node_label="label")

        # Connect more nodes
        G1.add_edges_from([(2, 7), (3, 6)])
        G2.add_edges_from([(mapped[2], mapped[7]), (mapped[3], mapped[6])])
        G1.add_node(10)
        G2.add_node("Z")
        G1.nodes[10]["label"] = "blue"
        G2.nodes["Z"]["label"] = "blue"

        assert vf2pp_isomorphism(G1, G2, node_label="label")

        # Connect the newly added node, to opposite sides of the graph
        G1.add_edges_from([(10, 1), (10, 5), (10, 8)])
        G2.add_edges_from([("Z", mapped[1]), ("Z", mapped[4]), ("Z", mapped[9])])
        assert vf2pp_isomorphism(G1, G2, node_label="label")

        # Get two subgraphs that are not isomorphic but are easy to make
        H1 = nx.Graph(G1.subgraph([2, 3, 4, 5, 6, 7, 10]))
        H2 = nx.Graph(
            G2.subgraph(
                [mapped[4], mapped[5], mapped[6], mapped[7], mapped[8], mapped[9], "Z"]
            )
        )
        assert vf2pp_isomorphism(H1, H2, node_label="label") is None

        # Restructure both to make them isomorphic
        H1.add_edges_from([(10, 2), (10, 6), (3, 6), (2, 7), (2, 6), (3, 7)])
        H2.add_edges_from(
            [("Z", mapped[7]), (mapped[6], mapped[9]), (mapped[7], mapped[8])]
        )
        assert vf2pp_isomorphism(H1, H2, node_label="label")

        # Add edges with opposite direction in each Graph
        H1.add_edge(3, 5)
        H2.add_edge(mapped[5], mapped[7])
        assert vf2pp_isomorphism(H1, H2, node_label="label") is None

    def test_custom_graph3_different_labels(self):
        G1 = nx.Graph()

        mapped = {1: 9, 2: 8, 3: 7, 4: 6, 5: 3, 8: 5, 9: 4, 7: 1, 6: 2}
        edges1 = [
            (1, 2),
            (1, 3),
            (2, 3),
            (3, 4),
            (4, 5),
            (4, 7),
            (4, 9),
            (5, 8),
            (8, 9),
            (5, 6),
            (6, 7),
            (5, 2),
        ]
        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)
        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_many))), "label")
        nx.set_node_attributes(
            G2,
            dict(zip([mapped[n] for n in G1], it.cycle(labels_many))),
            "label",
        )
        assert vf2pp_isomorphism(G1, G2, node_label="label") == mapped

        # Add extra edge to G1
        G1.add_edge(1, 7)
        assert vf2pp_isomorphism(G1, G2, node_label="label") is None

        # Compensate in G2
        G2.add_edge(9, 1)
        assert vf2pp_isomorphism(G1, G2, node_label="label") == mapped

        # Add extra node
        G1.add_node("A")
        G2.add_node("K")
        G1.nodes["A"]["label"] = "green"
        G2.nodes["K"]["label"] = "green"
        mapped.update({"A": "K"})

        assert vf2pp_isomorphism(G1, G2, node_label="label") == mapped

        # Connect A to one side of G1 and K to the opposite
        G1.add_edge("A", 6)
        G2.add_edge("K", 5)
        assert vf2pp_isomorphism(G1, G2, node_label="label") is None

        # Make the graphs symmetrical
        G1.add_edge(1, 5)
        G1.add_edge(2, 9)
        G2.add_edge(9, 3)
        G2.add_edge(8, 4)
        assert vf2pp_isomorphism(G1, G2, node_label="label") is None

        # Assign same colors so the two opposite sides are identical
        for node in G1.nodes():
            color = "red"
            G1.nodes[node]["label"] = color
            G2.nodes[mapped[node]]["label"] = color

        assert vf2pp_isomorphism(G1, G2, node_label="label")

    def test_custom_graph4_different_labels(self):
        G1 = nx.Graph()
        edges1 = [
            (1, 2),
            (2, 3),
            (3, 8),
            (3, 4),
            (4, 5),
            (4, 6),
            (3, 6),
            (8, 7),
            (8, 9),
            (5, 9),
            (10, 11),
            (11, 12),
            (12, 13),
            (11, 13),
        ]

        mapped = {
            1: "n",
            2: "m",
            3: "l",
            4: "j",
            5: "k",
            6: "i",
            7: "g",
            8: "h",
            9: "f",
            10: "b",
            11: "a",
            12: "d",
            13: "e",
        }

        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)
        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_many))), "label")
        nx.set_node_attributes(
            G2,
            dict(zip([mapped[n] for n in G1], it.cycle(labels_many))),
            "label",
        )
        assert vf2pp_isomorphism(G1, G2, node_label="label") == mapped

    def test_custom_graph4_same_labels(self):
        G1 = nx.Graph()
        edges1 = [
            (1, 2),
            (2, 3),
            (3, 8),
            (3, 4),
            (4, 5),
            (4, 6),
            (3, 6),
            (8, 7),
            (8, 9),
            (5, 9),
            (10, 11),
            (11, 12),
            (12, 13),
            (11, 13),
        ]

        mapped = {
            1: "n",
            2: "m",
            3: "l",
            4: "j",
            5: "k",
            6: "i",
            7: "g",
            8: "h",
            9: "f",
            10: "b",
            11: "a",
            12: "d",
            13: "e",
        }

        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)
        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_same))), "label")
        nx.set_node_attributes(G2, dict(zip(G2, it.cycle(labels_same))), "label")
        assert vf2pp_isomorphism(G1, G2, node_label="label")

        # Add nodes of different label
        G1.add_node(0)
        G2.add_node("z")
        G1.nodes[0]["label"] = "green"
        G2.nodes["z"]["label"] = "blue"

        assert vf2pp_isomorphism(G1, G2, node_label="label") is None

        # Make the labels identical
        G2.nodes["z"]["label"] = "green"
        assert vf2pp_isomorphism(G1, G2, node_label="label")

        # Change the structure of the graphs, keeping them isomorphic
        G1.add_edge(2, 5)
        G2.remove_edge("i", "l")
        G2.add_edge("g", "l")
        G2.add_edge("m", "f")
        assert vf2pp_isomorphism(G1, G2, node_label="label")

        # Change the structure of the disconnected sub-graph, keeping it isomorphic
        G1.remove_node(13)
        G2.remove_node("d")
        assert vf2pp_isomorphism(G1, G2, node_label="label")

        # Connect the newly added node to the disconnected graph, which now is just a path of size 3
        G1.add_edge(0, 10)
        G2.add_edge("e", "z")
        assert vf2pp_isomorphism(G1, G2, node_label="label")

        # Connect the two disconnected sub-graphs, forming a single graph
        G1.add_edge(11, 3)
        G1.add_edge(0, 8)
        G2.add_edge("a", "l")
        G2.add_edge("z", "j")
        assert vf2pp_isomorphism(G1, G2, node_label="label")

    def test_custom_graph5_same_labels(self):
        G1 = nx.Graph()
        edges1 = [
            (1, 5),
            (1, 2),
            (1, 4),
            (2, 3),
            (2, 6),
            (3, 4),
            (3, 7),
            (4, 8),
            (5, 8),
            (5, 6),
            (6, 7),
            (7, 8),
        ]
        mapped = {1: "a", 2: "h", 3: "d", 4: "i", 5: "g", 6: "b", 7: "j", 8: "c"}

        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)
        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_same))), "label")
        nx.set_node_attributes(G2, dict(zip(G2, it.cycle(labels_same))), "label")
        assert vf2pp_isomorphism(G1, G2, node_label="label")

        # Add different edges in each graph, maintaining symmetry
        G1.add_edges_from([(3, 6), (2, 7), (2, 5), (1, 3), (4, 7), (6, 8)])
        G2.add_edges_from(
            [
                (mapped[6], mapped[3]),
                (mapped[2], mapped[7]),
                (mapped[1], mapped[6]),
                (mapped[5], mapped[7]),
                (mapped[3], mapped[8]),
                (mapped[2], mapped[4]),
            ]
        )
        assert vf2pp_isomorphism(G1, G2, node_label="label")

        # Obtain two different but isomorphic subgraphs from G1 and G2
        H1 = nx.Graph(G1.subgraph([1, 5, 8, 6, 7, 3]))
        H2 = nx.Graph(
            G2.subgraph(
                [mapped[1], mapped[4], mapped[8], mapped[7], mapped[3], mapped[5]]
            )
        )
        assert vf2pp_isomorphism(H1, H2, node_label="label")

        # Delete corresponding node from the two graphs
        H1.remove_node(8)
        H2.remove_node(mapped[7])
        assert vf2pp_isomorphism(H1, H2, node_label="label")

        # Re-orient, maintaining isomorphism
        H1.add_edge(1, 6)
        H1.remove_edge(3, 6)
        assert vf2pp_isomorphism(H1, H2, node_label="label")

    def test_custom_graph5_different_labels(self):
        G1 = nx.Graph()
        edges1 = [
            (1, 5),
            (1, 2),
            (1, 4),
            (2, 3),
            (2, 6),
            (3, 4),
            (3, 7),
            (4, 8),
            (5, 8),
            (5, 6),
            (6, 7),
            (7, 8),
        ]
        mapped = {1: "a", 2: "h", 3: "d", 4: "i", 5: "g", 6: "b", 7: "j", 8: "c"}

        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)

        colors = ["red", "blue", "grey", "none", "brown", "solarized", "yellow", "pink"]
        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_many))), "label")
        nx.set_node_attributes(
            G2,
            dict(zip([mapped[n] for n in G1], it.cycle(labels_many))),
            "label",
        )
        assert vf2pp_isomorphism(G1, G2, node_label="label") == mapped

        # Assign different colors to matching nodes
        c = 0
        for node in G1.nodes():
            color1 = colors[c]
            color2 = colors[(c + 3) % len(colors)]
            G1.nodes[node]["label"] = color1
            G2.nodes[mapped[node]]["label"] = color2
            c += 1

        assert vf2pp_isomorphism(G1, G2, node_label="label") is None

        # Get symmetrical sub-graphs of G1,G2 and compare them
        H1 = G1.subgraph([1, 5])
        H2 = G2.subgraph(["i", "c"])
        c = 0
        for node1, node2 in zip(H1.nodes(), H2.nodes()):
            H1.nodes[node1]["label"] = "red"
            H2.nodes[node2]["label"] = "red"
            c += 1

        assert vf2pp_isomorphism(H1, H2, node_label="label")

    def test_disconnected_graph_all_same_labels(self):
        G1 = nx.Graph()
        G1.add_nodes_from(list(range(10)))

        mapped = {0: 9, 1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1, 9: 0}
        G2 = nx.relabel_nodes(G1, mapped)
        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_same))), "label")
        nx.set_node_attributes(G2, dict(zip(G2, it.cycle(labels_same))), "label")
        assert vf2pp_isomorphism(G1, G2, node_label="label")

    def test_disconnected_graph_all_different_labels(self):
        G1 = nx.Graph()
        G1.add_nodes_from(list(range(10)))

        mapped = {0: 9, 1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1, 9: 0}
        G2 = nx.relabel_nodes(G1, mapped)

        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_many))), "label")
        nx.set_node_attributes(
            G2,
            dict(zip([mapped[n] for n in G1], it.cycle(labels_many))),
            "label",
        )
        assert vf2pp_isomorphism(G1, G2, node_label="label") == mapped

    def test_disconnected_graph_some_same_labels(self):
        G1 = nx.Graph()
        G1.add_nodes_from(list(range(10)))

        mapped = {0: 9, 1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1, 9: 0}
        G2 = nx.relabel_nodes(G1, mapped)

        colors = [
            "white",
            "white",
            "white",
            "purple",
            "purple",
            "red",
            "red",
            "pink",
            "pink",
            "pink",
        ]

        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(colors))), "label")
        nx.set_node_attributes(
            G2, dict(zip([mapped[n] for n in G1], it.cycle(colors))), "label"
        )

        assert vf2pp_isomorphism(G1, G2, node_label="label")


class TestMultiGraphISOVF2pp:
    def test_custom_multigraph1_same_labels(self):
        G1 = nx.MultiGraph()

        mapped = {1: "A", 2: "B", 3: "C", 4: "D", 5: "Z", 6: "E"}
        edges1 = [
            (1, 2),
            (1, 3),
            (1, 4),
            (1, 4),
            (1, 4),
            (2, 3),
            (2, 6),
            (2, 6),
            (3, 4),
            (3, 4),
            (5, 1),
            (5, 1),
            (5, 2),
            (5, 2),
        ]

        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)

        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_same))), "label")
        nx.set_node_attributes(G2, dict(zip(G2, it.cycle(labels_same))), "label")
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

        # Transfer the 2-clique to the right side of G1
        G1.remove_edges_from([(2, 6), (2, 6)])
        G1.add_edges_from([(3, 6), (3, 6)])
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert not m

        # Delete an edges, making them symmetrical, so the position of the 2-clique doesn't matter
        G2.remove_edge(mapped[1], mapped[4])
        G1.remove_edge(1, 4)
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

        # Add self-loops
        G1.add_edges_from([(5, 5), (5, 5), (1, 1)])
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert not m

        # Compensate in G2
        G2.add_edges_from(
            [(mapped[1], mapped[1]), (mapped[4], mapped[4]), (mapped[4], mapped[4])]
        )
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

    def test_custom_multigraph1_different_labels(self):
        G1 = nx.MultiGraph()

        mapped = {1: "A", 2: "B", 3: "C", 4: "D", 5: "Z", 6: "E"}
        edges1 = [
            (1, 2),
            (1, 3),
            (1, 4),
            (1, 4),
            (1, 4),
            (2, 3),
            (2, 6),
            (2, 6),
            (3, 4),
            (3, 4),
            (5, 1),
            (5, 1),
            (5, 2),
            (5, 2),
        ]

        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)

        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_many))), "label")
        nx.set_node_attributes(
            G2,
            dict(zip([mapped[n] for n in G1], it.cycle(labels_many))),
            "label",
        )
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m
        assert m == mapped

        # Re-structure G1, maintaining the degree sequence
        G1.remove_edge(1, 4)
        G1.add_edge(1, 5)
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert not m

        # Restructure G2, making it isomorphic to G1
        G2.remove_edge("A", "D")
        G2.add_edge("A", "Z")
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m
        assert m == mapped

        # Add edge from node to itself
        G1.add_edges_from([(6, 6), (6, 6), (6, 6)])
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert not m

        # Same for G2
        G2.add_edges_from([("E", "E"), ("E", "E"), ("E", "E")])
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m
        assert m == mapped

    def test_custom_multigraph2_same_labels(self):
        G1 = nx.MultiGraph()

        mapped = {1: "A", 2: "C", 3: "D", 4: "E", 5: "G", 7: "B", 6: "F"}
        edges1 = [
            (1, 2),
            (1, 2),
            (1, 5),
            (1, 5),
            (1, 5),
            (5, 6),
            (2, 3),
            (2, 3),
            (2, 4),
            (3, 4),
            (3, 4),
            (4, 5),
            (4, 5),
            (4, 5),
            (2, 7),
            (2, 7),
            (2, 7),
        ]

        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)

        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_same))), "label")
        nx.set_node_attributes(G2, dict(zip(G2, it.cycle(labels_same))), "label")
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

        # Obtain two non-isomorphic subgraphs from the graph
        G2.remove_edges_from([(mapped[1], mapped[2]), (mapped[1], mapped[2])])
        G2.add_edge(mapped[1], mapped[4])
        H1 = nx.MultiGraph(G1.subgraph([2, 3, 4, 7]))
        H2 = nx.MultiGraph(G2.subgraph([mapped[1], mapped[4], mapped[5], mapped[6]]))

        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert not m

        # Make them isomorphic
        H1.remove_edge(3, 4)
        H1.add_edges_from([(2, 3), (2, 4), (2, 4)])
        H2.add_edges_from([(mapped[5], mapped[6]), (mapped[5], mapped[6])])
        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert m

        # Remove triangle edge
        H1.remove_edges_from([(2, 3), (2, 3), (2, 3)])
        H2.remove_edges_from([(mapped[5], mapped[4])] * 3)
        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert m

        # Change the edge orientation such that H1 is rotated H2
        H1.remove_edges_from([(2, 7), (2, 7)])
        H1.add_edges_from([(3, 4), (3, 4)])
        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert m

        # Add extra edges maintaining degree sequence, but in a non-symmetrical manner
        H2.add_edge(mapped[5], mapped[1])
        H1.add_edge(3, 4)
        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert not m

    def test_custom_multigraph2_different_labels(self):
        G1 = nx.MultiGraph()

        mapped = {1: "A", 2: "C", 3: "D", 4: "E", 5: "G", 7: "B", 6: "F"}
        edges1 = [
            (1, 2),
            (1, 2),
            (1, 5),
            (1, 5),
            (1, 5),
            (5, 6),
            (2, 3),
            (2, 3),
            (2, 4),
            (3, 4),
            (3, 4),
            (4, 5),
            (4, 5),
            (4, 5),
            (2, 7),
            (2, 7),
            (2, 7),
        ]

        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)

        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_many))), "label")
        nx.set_node_attributes(
            G2,
            dict(zip([mapped[n] for n in G1], it.cycle(labels_many))),
            "label",
        )
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m
        assert m == mapped

        # Re-structure G1
        G1.remove_edge(2, 7)
        G1.add_edge(5, 6)

        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert not m

        # Same for G2
        G2.remove_edge("B", "C")
        G2.add_edge("G", "F")

        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m
        assert m == mapped

        # Delete node from G1 and G2, keeping them isomorphic
        G1.remove_node(3)
        G2.remove_node("D")
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

        # Change G1 edges
        G1.remove_edge(1, 2)
        G1.remove_edge(2, 7)
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert not m

        # Make G2 identical to G1, but with different edge orientation and different labels
        G2.add_edges_from([("A", "C"), ("C", "E"), ("C", "E")])
        G2.remove_edges_from(
            [("A", "G"), ("A", "G"), ("F", "G"), ("E", "G"), ("E", "G")]
        )

        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert not m

        # Make all labels the same, so G1 and G2 are also isomorphic
        for n1, n2 in zip(G1.nodes(), G2.nodes()):
            G1.nodes[n1]["label"] = "blue"
            G2.nodes[n2]["label"] = "blue"

        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

    def test_custom_multigraph3_same_labels(self):
        G1 = nx.MultiGraph()

        mapped = {1: 9, 2: 8, 3: 7, 4: 6, 5: 3, 8: 5, 9: 4, 7: 1, 6: 2}
        edges1 = [
            (1, 2),
            (1, 3),
            (1, 3),
            (2, 3),
            (2, 3),
            (3, 4),
            (4, 5),
            (4, 7),
            (4, 9),
            (4, 9),
            (4, 9),
            (5, 8),
            (5, 8),
            (8, 9),
            (8, 9),
            (5, 6),
            (6, 7),
            (6, 7),
            (6, 7),
            (5, 2),
        ]
        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)

        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_same))), "label")
        nx.set_node_attributes(G2, dict(zip(G2, it.cycle(labels_same))), "label")
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

        # Connect nodes maintaining symmetry
        G1.add_edges_from([(6, 9), (7, 8), (5, 8), (4, 9), (4, 9)])
        G2.add_edges_from(
            [
                (mapped[6], mapped[8]),
                (mapped[7], mapped[9]),
                (mapped[5], mapped[8]),
                (mapped[4], mapped[9]),
                (mapped[4], mapped[9]),
            ]
        )
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert not m

        # Make isomorphic
        G1.add_edges_from([(6, 8), (6, 8), (7, 9), (7, 9), (7, 9)])
        G2.add_edges_from(
            [
                (mapped[6], mapped[8]),
                (mapped[6], mapped[9]),
                (mapped[7], mapped[8]),
                (mapped[7], mapped[9]),
                (mapped[7], mapped[9]),
            ]
        )
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

        # Connect more nodes
        G1.add_edges_from([(2, 7), (2, 7), (3, 6), (3, 6)])
        G2.add_edges_from(
            [
                (mapped[2], mapped[7]),
                (mapped[2], mapped[7]),
                (mapped[3], mapped[6]),
                (mapped[3], mapped[6]),
            ]
        )
        G1.add_node(10)
        G2.add_node("Z")
        G1.nodes[10]["label"] = "blue"
        G2.nodes["Z"]["label"] = "blue"

        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

        # Connect the newly added node, to opposite sides of the graph
        G1.add_edges_from([(10, 1), (10, 5), (10, 8), (10, 10), (10, 10)])
        G2.add_edges_from(
            [
                ("Z", mapped[1]),
                ("Z", mapped[4]),
                ("Z", mapped[9]),
                ("Z", "Z"),
                ("Z", "Z"),
            ]
        )
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert not m

        # We connected the new node to opposite sides, so G1 must be symmetrical to G2. Re-structure them to be so
        G1.remove_edges_from([(1, 3), (4, 9), (4, 9), (7, 9)])
        G2.remove_edges_from(
            [
                (mapped[1], mapped[3]),
                (mapped[4], mapped[9]),
                (mapped[4], mapped[9]),
                (mapped[7], mapped[9]),
            ]
        )
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

        # Get two subgraphs that are not isomorphic but are easy to make
        H1 = nx.Graph(G1.subgraph([2, 3, 4, 5, 6, 7, 10]))
        H2 = nx.Graph(
            G2.subgraph(
                [mapped[4], mapped[5], mapped[6], mapped[7], mapped[8], mapped[9], "Z"]
            )
        )

        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert not m

        # Restructure both to make them isomorphic
        H1.add_edges_from([(10, 2), (10, 6), (3, 6), (2, 7), (2, 6), (3, 7)])
        H2.add_edges_from(
            [("Z", mapped[7]), (mapped[6], mapped[9]), (mapped[7], mapped[8])]
        )
        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert m

        # Remove one self-loop in H2
        H2.remove_edge("Z", "Z")
        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert not m

        # Compensate in H1
        H1.remove_edge(10, 10)
        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert m

    def test_custom_multigraph3_different_labels(self):
        G1 = nx.MultiGraph()

        mapped = {1: 9, 2: 8, 3: 7, 4: 6, 5: 3, 8: 5, 9: 4, 7: 1, 6: 2}
        edges1 = [
            (1, 2),
            (1, 3),
            (1, 3),
            (2, 3),
            (2, 3),
            (3, 4),
            (4, 5),
            (4, 7),
            (4, 9),
            (4, 9),
            (4, 9),
            (5, 8),
            (5, 8),
            (8, 9),
            (8, 9),
            (5, 6),
            (6, 7),
            (6, 7),
            (6, 7),
            (5, 2),
        ]

        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)

        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_many))), "label")
        nx.set_node_attributes(
            G2,
            dict(zip([mapped[n] for n in G1], it.cycle(labels_many))),
            "label",
        )
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m
        assert m == mapped

        # Delete edge maintaining isomorphism
        G1.remove_edge(4, 9)
        G2.remove_edge(4, 6)

        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m
        assert m == mapped

        # Change edge orientation such that G1 mirrors G2
        G1.add_edges_from([(4, 9), (1, 2), (1, 2)])
        G1.remove_edges_from([(1, 3), (1, 3)])
        G2.add_edges_from([(3, 5), (7, 9)])
        G2.remove_edge(8, 9)

        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert not m

        # Make all labels the same, so G1 and G2 are also isomorphic
        for n1, n2 in zip(G1.nodes(), G2.nodes()):
            G1.nodes[n1]["label"] = "blue"
            G2.nodes[n2]["label"] = "blue"

        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

        G1.add_node(10)
        G2.add_node("Z")
        G1.nodes[10]["label"] = "green"
        G2.nodes["Z"]["label"] = "green"

        # Add different number of edges between the new nodes and themselves
        G1.add_edges_from([(10, 10), (10, 10)])
        G2.add_edges_from([("Z", "Z")])

        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert not m

        # Make the number of self-edges equal
        G1.remove_edge(10, 10)
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

        # Connect the new node to the graph
        G1.add_edges_from([(10, 3), (10, 4)])
        G2.add_edges_from([("Z", 8), ("Z", 3)])

        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

        # Remove central node
        G1.remove_node(4)
        G2.remove_node(3)
        G1.add_edges_from([(5, 6), (5, 6), (5, 7)])
        G2.add_edges_from([(1, 6), (1, 6), (6, 2)])

        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

    def test_custom_multigraph4_same_labels(self):
        G1 = nx.MultiGraph()
        edges1 = [
            (1, 2),
            (1, 2),
            (2, 2),
            (2, 3),
            (3, 8),
            (3, 8),
            (3, 4),
            (4, 5),
            (4, 5),
            (4, 5),
            (4, 6),
            (3, 6),
            (3, 6),
            (6, 6),
            (8, 7),
            (7, 7),
            (8, 9),
            (9, 9),
            (8, 9),
            (8, 9),
            (5, 9),
            (10, 11),
            (11, 12),
            (12, 13),
            (11, 13),
            (10, 10),
            (10, 11),
            (11, 13),
        ]

        mapped = {
            1: "n",
            2: "m",
            3: "l",
            4: "j",
            5: "k",
            6: "i",
            7: "g",
            8: "h",
            9: "f",
            10: "b",
            11: "a",
            12: "d",
            13: "e",
        }

        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)

        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_same))), "label")
        nx.set_node_attributes(G2, dict(zip(G2, it.cycle(labels_same))), "label")
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

        # Add extra but corresponding edges to both graphs
        G1.add_edges_from([(2, 2), (2, 3), (2, 8), (3, 4)])
        G2.add_edges_from([("m", "m"), ("m", "l"), ("m", "h"), ("l", "j")])
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

        # Obtain subgraphs
        H1 = nx.MultiGraph(G1.subgraph([2, 3, 4, 6, 10, 11, 12, 13]))
        H2 = nx.MultiGraph(
            G2.subgraph(
                [
                    mapped[2],
                    mapped[3],
                    mapped[8],
                    mapped[9],
                    mapped[10],
                    mapped[11],
                    mapped[12],
                    mapped[13],
                ]
            )
        )

        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert not m

        # Make them isomorphic
        H2.remove_edges_from(
            [(mapped[3], mapped[2]), (mapped[9], mapped[8]), (mapped[2], mapped[2])]
        )
        H2.add_edges_from([(mapped[9], mapped[9]), (mapped[2], mapped[8])])
        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert m

        # Re-structure the disconnected sub-graph
        H1.remove_node(12)
        H2.remove_node(mapped[12])
        H1.add_edge(13, 13)
        H2.add_edge(mapped[13], mapped[13])

        # Connect the two disconnected components, forming a single graph
        H1.add_edges_from([(3, 13), (6, 11)])
        H2.add_edges_from([(mapped[8], mapped[10]), (mapped[2], mapped[11])])
        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert m

        # Change orientation of self-loops in one graph, maintaining the degree sequence
        H1.remove_edges_from([(2, 2), (3, 6)])
        H1.add_edges_from([(6, 6), (2, 3)])
        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert not m

    def test_custom_multigraph4_different_labels(self):
        G1 = nx.MultiGraph()
        edges1 = [
            (1, 2),
            (1, 2),
            (2, 2),
            (2, 3),
            (3, 8),
            (3, 8),
            (3, 4),
            (4, 5),
            (4, 5),
            (4, 5),
            (4, 6),
            (3, 6),
            (3, 6),
            (6, 6),
            (8, 7),
            (7, 7),
            (8, 9),
            (9, 9),
            (8, 9),
            (8, 9),
            (5, 9),
            (10, 11),
            (11, 12),
            (12, 13),
            (11, 13),
        ]

        mapped = {
            1: "n",
            2: "m",
            3: "l",
            4: "j",
            5: "k",
            6: "i",
            7: "g",
            8: "h",
            9: "f",
            10: "b",
            11: "a",
            12: "d",
            13: "e",
        }

        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)

        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_many))), "label")
        nx.set_node_attributes(
            G2,
            dict(zip([mapped[n] for n in G1], it.cycle(labels_many))),
            "label",
        )
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m == mapped

        # Add extra but corresponding edges to both graphs
        G1.add_edges_from([(2, 2), (2, 3), (2, 8), (3, 4)])
        G2.add_edges_from([("m", "m"), ("m", "l"), ("m", "h"), ("l", "j")])
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m == mapped

        # Obtain isomorphic subgraphs
        H1 = nx.MultiGraph(G1.subgraph([2, 3, 4, 6]))
        H2 = nx.MultiGraph(G2.subgraph(["m", "l", "j", "i"]))

        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert m

        # Delete the 3-clique, keeping only the path-graph. Also, H1 mirrors H2
        H1.remove_node(4)
        H2.remove_node("j")
        H1.remove_edges_from([(2, 2), (2, 3), (6, 6)])
        H2.remove_edges_from([("l", "i"), ("m", "m"), ("m", "m")])

        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert not m

        # Assign the same labels so that mirroring means isomorphic
        for n1, n2 in zip(H1.nodes(), H2.nodes()):
            H1.nodes[n1]["label"] = "red"
            H2.nodes[n2]["label"] = "red"

        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert m

        # Leave only one node with self-loop
        H1.remove_nodes_from([3, 6])
        H2.remove_nodes_from(["m", "l"])
        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert m

        # Remove one self-loop from H1
        H1.remove_edge(2, 2)
        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert not m

        # Same for H2
        H2.remove_edge("i", "i")
        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert m

        # Compose H1 with the disconnected sub-graph of G1. Same for H2
        S1 = nx.compose(H1, nx.MultiGraph(G1.subgraph([10, 11, 12, 13])))
        S2 = nx.compose(H2, nx.MultiGraph(G2.subgraph(["a", "b", "d", "e"])))

        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert m

        # Connect the two components
        S1.add_edges_from([(13, 13), (13, 13), (2, 13)])
        S2.add_edges_from([("a", "a"), ("a", "a"), ("i", "e")])
        m = vf2pp_isomorphism(H1, H2, node_label="label")
        assert m

    def test_custom_multigraph5_same_labels(self):
        G1 = nx.MultiGraph()

        edges1 = [
            (1, 5),
            (1, 2),
            (1, 4),
            (2, 3),
            (2, 6),
            (3, 4),
            (3, 7),
            (4, 8),
            (5, 8),
            (5, 6),
            (6, 7),
            (7, 8),
        ]
        mapped = {1: "a", 2: "h", 3: "d", 4: "i", 5: "g", 6: "b", 7: "j", 8: "c"}

        G1.add_edges_from(edges1)
        G2 = nx.relabel_nodes(G1, mapped)
        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_same))), "label")
        nx.set_node_attributes(G2, dict(zip(G2, it.cycle(labels_same))), "label")

        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

        # Add multiple edges and self-loops, maintaining isomorphism
        G1.add_edges_from(
            [(1, 2), (1, 2), (3, 7), (8, 8), (8, 8), (7, 8), (2, 3), (5, 6)]
        )
        G2.add_edges_from(
            [
                ("a", "h"),
                ("a", "h"),
                ("d", "j"),
                ("c", "c"),
                ("c", "c"),
                ("j", "c"),
                ("d", "h"),
                ("g", "b"),
            ]
        )

        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

        # Make G2 to be the rotated G1
        G2.remove_edges_from(
            [
                ("a", "h"),
                ("a", "h"),
                ("d", "j"),
                ("c", "c"),
                ("c", "c"),
                ("j", "c"),
                ("d", "h"),
                ("g", "b"),
            ]
        )
        G2.add_edges_from(
            [
                ("d", "i"),
                ("a", "h"),
                ("g", "b"),
                ("g", "b"),
                ("i", "i"),
                ("i", "i"),
                ("b", "j"),
                ("d", "j"),
            ]
        )

        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

    def test_disconnected_multigraph_all_same_labels(self):
        G1 = nx.MultiGraph()
        G1.add_nodes_from(list(range(10)))
        G1.add_edges_from([(i, i) for i in range(10)])

        mapped = {0: 9, 1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1, 9: 0}
        G2 = nx.relabel_nodes(G1, mapped)

        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_same))), "label")
        nx.set_node_attributes(G2, dict(zip(G2, it.cycle(labels_same))), "label")

        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

        # Add self-loops to non-mapped nodes. Should be the same, as the graph is disconnected.
        G1.add_edges_from([(i, i) for i in range(5, 8)] * 3)
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert not m

        # Compensate in G2
        G2.add_edges_from([(i, i) for i in range(3)] * 3)
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

        # Add one more self-loop in G2
        G2.add_edges_from([(0, 0), (1, 1), (1, 1)])
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert not m

        # Compensate in G1
        G1.add_edges_from([(5, 5), (7, 7), (7, 7)])
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m

    def test_disconnected_multigraph_all_different_labels(self):
        G1 = nx.MultiGraph()
        G1.add_nodes_from(list(range(10)))
        G1.add_edges_from([(i, i) for i in range(10)])

        mapped = {0: 9, 1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1, 9: 0}
        G2 = nx.relabel_nodes(G1, mapped)

        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_many))), "label")
        nx.set_node_attributes(
            G2,
            dict(zip([mapped[n] for n in G1], it.cycle(labels_many))),
            "label",
        )
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m
        assert m == mapped

        # Add self-loops to non-mapped nodes. Now it is not the same, as there are different labels
        G1.add_edges_from([(i, i) for i in range(5, 8)] * 3)
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert not m

        # Add self-loops to non mapped nodes in G2 as well
        G2.add_edges_from([(mapped[i], mapped[i]) for i in range(3)] * 7)
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert not m

        # Add self-loops to mapped nodes in G2
        G2.add_edges_from([(mapped[i], mapped[i]) for i in range(5, 8)] * 3)
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert not m

        # Add self-loops to G1 so that they are even in both graphs
        G1.add_edges_from([(i, i) for i in range(3)] * 7)
        m = vf2pp_isomorphism(G1, G2, node_label="label")
        assert m


class TestDiGraphISOVF2pp:
    def test_wikipedia_graph(self):
        edges1 = [
            (1, 5),
            (1, 2),
            (1, 4),
            (3, 2),
            (6, 2),
            (3, 4),
            (7, 3),
            (4, 8),
            (5, 8),
            (6, 5),
            (6, 7),
            (7, 8),
        ]
        mapped = {1: "a", 2: "h", 3: "d", 4: "i", 5: "g", 6: "b", 7: "j", 8: "c"}

        G1 = nx.DiGraph(edges1)
        G2 = nx.relabel_nodes(G1, mapped)

        assert vf2pp_isomorphism(G1, G2) == mapped

        # Change the direction of an edge
        G1.remove_edge(1, 5)
        G1.add_edge(5, 1)
        assert vf2pp_isomorphism(G1, G2) is None

    def test_non_isomorphic_same_degree_sequence(self):
        r"""
                G1                           G2
        x--------------x              x--------------x
        | \            |              | \            |
        |  x-------x   |              |  x-------x   |
        |  |       |   |              |  |       |   |
        |  x-------x   |              |  x-------x   |
        | /            |              |            \ |
        x--------------x              x--------------x
        """
        edges1 = [
            (1, 5),
            (1, 2),
            (4, 1),
            (3, 2),
            (3, 4),
            (4, 8),
            (5, 8),
            (6, 5),
            (6, 7),
            (7, 8),
        ]
        edges2 = [
            (1, 5),
            (1, 2),
            (4, 1),
            (3, 2),
            (4, 3),
            (5, 8),
            (6, 5),
            (6, 7),
            (3, 7),
            (8, 7),
        ]

        G1 = nx.DiGraph(edges1)
        G2 = nx.DiGraph(edges2)
        assert vf2pp_isomorphism(G1, G2) is None
