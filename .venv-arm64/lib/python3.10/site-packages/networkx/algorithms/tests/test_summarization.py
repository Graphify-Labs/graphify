"""
Unit tests for dedensification and graph summarization
"""

import pytest

import networkx as nx


class TestDirectedDedensification:
    def build_original_graph(self):
        original_matrix = [
            ("1", "BC"),
            ("2", "ABC"),
            ("3", ["A", "B", "6"]),
            ("4", "ABC"),
            ("5", "AB"),
            ("6", ["5"]),
            ("A", ["6"]),
        ]
        graph = nx.DiGraph()
        for source, targets in original_matrix:
            for target in targets:
                graph.add_edge(source, target)
        return graph

    def build_compressed_graph(self):
        compressed_matrix = [
            ("1", "BC"),
            ("2", ["ABC"]),
            ("3", ["A", "B", "6"]),
            ("4", ["ABC"]),
            ("5", "AB"),
            ("6", ["5"]),
            ("A", ["6"]),
            ("ABC", "ABC"),
        ]
        compressed_graph = nx.DiGraph()
        for source, targets in compressed_matrix:
            for target in targets:
                compressed_graph.add_edge(source, target)
        return compressed_graph

    def test_empty(self):
        """
        Verify that an empty directed graph results in no compressor nodes
        """
        G = nx.DiGraph()
        compressed_graph, c_nodes = nx.dedensify(G, threshold=2)
        assert c_nodes == set()

    @staticmethod
    def densify(G, compressor_nodes, copy=True):
        """
        Reconstructs the original graph from a dedensified, directed graph

        Parameters
        ----------
        G: dedensified graph
           A networkx graph
        compressor_nodes: iterable
           Iterable of compressor nodes in the dedensified graph
        inplace: bool, optional (default: False)
           Indicates if densification should be done inplace

        Returns
        -------
        G: graph
           A densified networkx graph
        """
        if copy:
            G = G.copy()
        for compressor_node in compressor_nodes:
            all_neighbors = set(nx.all_neighbors(G, compressor_node))
            out_neighbors = set(G.neighbors(compressor_node))
            for out_neighbor in out_neighbors:
                G.remove_edge(compressor_node, out_neighbor)
            in_neighbors = all_neighbors - out_neighbors
            for in_neighbor in in_neighbors:
                G.remove_edge(in_neighbor, compressor_node)
                for out_neighbor in out_neighbors:
                    G.add_edge(in_neighbor, out_neighbor)
            G.remove_node(compressor_node)
        return G

    def setup_method(self):
        self.c_nodes = ("ABC",)

    def test_dedensify_edges(self):
        """
        Verifies that dedensify produced the correct edges to/from compressor
        nodes in a directed graph
        """
        G = self.build_original_graph()
        compressed_G = self.build_compressed_graph()
        compressed_graph, c_nodes = nx.dedensify(G, threshold=2)
        for s, t in compressed_graph.edges():
            o_s = "".join(sorted(s))
            o_t = "".join(sorted(t))
            compressed_graph_exists = compressed_graph.has_edge(s, t)
            verified_compressed_exists = compressed_G.has_edge(o_s, o_t)
            assert compressed_graph_exists == verified_compressed_exists
        assert len(c_nodes) == len(self.c_nodes)

    def test_dedensify_edge_count(self):
        """
        Verifies that dedensify produced the correct number of compressor nodes
        in a directed graph
        """
        G = self.build_original_graph()
        original_edge_count = len(G.edges())
        c_G, c_nodes = nx.dedensify(G, threshold=2)
        compressed_edge_count = len(c_G.edges())
        assert compressed_edge_count <= original_edge_count
        compressed_G = self.build_compressed_graph()
        assert compressed_edge_count == len(compressed_G.edges())

    def test_densify_edges(self):
        """
        Verifies that densification produces the correct edges from the
        original directed graph
        """
        compressed_G = self.build_compressed_graph()
        original_graph = self.densify(compressed_G, self.c_nodes, copy=True)
        G = self.build_original_graph()
        for s, t in G.edges():
            assert G.has_edge(s, t) == original_graph.has_edge(s, t)

    def test_densify_edge_count(self):
        """
        Verifies that densification produces the correct number of edges in the
        original directed graph
        """
        compressed_G = self.build_compressed_graph()
        compressed_edge_count = len(compressed_G.edges())
        original_graph = self.densify(compressed_G, self.c_nodes)
        original_edge_count = len(original_graph.edges())
        assert compressed_edge_count <= original_edge_count
        G = self.build_original_graph()
        assert original_edge_count == len(G.edges())


class TestUnDirectedDedensification:
    def build_original_graph(self):
        """
        Builds graph shown in the original research paper
        """
        original_matrix = [
            ("1", "CB"),
            ("2", "ABC"),
            ("3", ["A", "B", "6"]),
            ("4", "ABC"),
            ("5", "AB"),
            ("6", ["5"]),
            ("A", ["6"]),
        ]
        graph = nx.Graph()
        for source, targets in original_matrix:
            for target in targets:
                graph.add_edge(source, target)
        return graph

    def test_empty(self):
        """
        Verify that an empty undirected graph results in no compressor nodes
        """
        G = nx.Graph()
        compressed_G, c_nodes = nx.dedensify(G, threshold=2)
        assert c_nodes == set()

    def setup_method(self):
        self.c_nodes = ("6AB", "ABC")

    def build_compressed_graph(self):
        compressed_matrix = [
            ("1", ["B", "C"]),
            ("2", ["ABC"]),
            ("3", ["6AB"]),
            ("4", ["ABC"]),
            ("5", ["6AB"]),
            ("6", ["6AB", "A"]),
            ("A", ["6AB", "ABC"]),
            ("B", ["ABC", "6AB"]),
            ("C", ["ABC"]),
        ]
        compressed_graph = nx.Graph()
        for source, targets in compressed_matrix:
            for target in targets:
                compressed_graph.add_edge(source, target)
        return compressed_graph

    def test_dedensify_edges(self):
        """
        Verifies that dedensify produced correct compressor nodes and the
        correct edges to/from the compressor nodes in an undirected graph
        """
        G = self.build_original_graph()
        c_G, c_nodes = nx.dedensify(G, threshold=2)
        v_compressed_G = self.build_compressed_graph()
        for s, t in c_G.edges():
            o_s = "".join(sorted(s))
            o_t = "".join(sorted(t))
            has_compressed_edge = c_G.has_edge(s, t)
            verified_has_compressed_edge = v_compressed_G.has_edge(o_s, o_t)
            assert has_compressed_edge == verified_has_compressed_edge
        assert len(c_nodes) == len(self.c_nodes)

    def test_dedensify_edge_count(self):
        """
        Verifies that dedensify produced the correct number of edges in an
        undirected graph
        """
        G = self.build_original_graph()
        c_G, c_nodes = nx.dedensify(G, threshold=2, copy=True)
        compressed_edge_count = len(c_G.edges())
        verified_original_edge_count = len(G.edges())
        assert compressed_edge_count <= verified_original_edge_count
        verified_compressed_G = self.build_compressed_graph()
        verified_compressed_edge_count = len(verified_compressed_G.edges())
        assert compressed_edge_count == verified_compressed_edge_count


@pytest.mark.parametrize(
    "graph_type", [nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph]
)
def test_summarization_empty(graph_type):
    G = graph_type()
    summary_graph = nx.snap_aggregation(G, node_attributes=("color",))
    assert nx.is_isomorphic(summary_graph, G)


class AbstractSNAP:
    node_attributes = ("color",)

    def build_original_graph(self):
        pass

    def build_summary_graph(self):
        pass

    def test_summary_graph(self):
        original_graph = self.build_original_graph()
        summary_graph = self.build_summary_graph()

        relationship_attributes = ("type",)
        generated_summary_graph = nx.snap_aggregation(
            original_graph, self.node_attributes, relationship_attributes
        )
        relabeled_summary_graph = self.deterministic_labels(generated_summary_graph)
        assert nx.is_isomorphic(summary_graph, relabeled_summary_graph)

    def deterministic_labels(self, G):
        node_labels = list(G.nodes)
        node_labels = sorted(node_labels, key=lambda n: sorted(G.nodes[n]["group"])[0])
        node_labels.sort()

        label_mapping = {}
        for index, node in enumerate(node_labels):
            label = f"Supernode-{index}"
            label_mapping[node] = label

        return nx.relabel_nodes(G, label_mapping)


class TestSNAPNoEdgeTypes(AbstractSNAP):
    relationship_attributes = ()

    def test_summary_graph(self):
        original_graph = self.build_original_graph()
        summary_graph = self.build_summary_graph()

        relationship_attributes = ("type",)
        generated_summary_graph = nx.snap_aggregation(
            original_graph, self.node_attributes
        )
        relabeled_summary_graph = self.deterministic_labels(generated_summary_graph)
        assert nx.is_isomorphic(summary_graph, relabeled_summary_graph)

    def build_original_graph(self):
        nodes = {
            "A": {"color": "Red"},
            "B": {"color": "Red"},
            "C": {"color": "Red"},
            "D": {"color": "Red"},
            "E": {"color": "Blue"},
            "F": {"color": "Blue"},
            "G": {"color": "Blue"},
            "H": {"color": "Blue"},
            "I": {"color": "Yellow"},
            "J": {"color": "Yellow"},
            "K": {"color": "Yellow"},
            "L": {"color": "Yellow"},
        }
        edges = [
            ("A", "B"),
            ("A", "C"),
            ("A", "E"),
            ("A", "I"),
            ("B", "D"),
            ("B", "J"),
            ("B", "F"),
            ("C", "G"),
            ("D", "H"),
            ("I", "J"),
            ("J", "K"),
            ("I", "L"),
        ]
        G = nx.Graph()
        for node in nodes:
            attributes = nodes[node]
            G.add_node(node, **attributes)

        for source, target in edges:
            G.add_edge(source, target)

        return G

    def build_summary_graph(self):
        nodes = {
            "Supernode-0": {"color": "Red"},
            "Supernode-1": {"color": "Red"},
            "Supernode-2": {"color": "Blue"},
            "Supernode-3": {"color": "Blue"},
            "Supernode-4": {"color": "Yellow"},
            "Supernode-5": {"color": "Yellow"},
        }
        edges = [
            ("Supernode-0", "Supernode-0"),
            ("Supernode-0", "Supernode-1"),
            ("Supernode-0", "Supernode-2"),
            ("Supernode-0", "Supernode-4"),
            ("Supernode-1", "Supernode-3"),
            ("Supernode-4", "Supernode-4"),
            ("Supernode-4", "Supernode-5"),
        ]
        G = nx.Graph()
        for node in nodes:
            attributes = nodes[node]
            G.add_node(node, **attributes)

        for source, target in edges:
            G.add_edge(source, target)

        supernodes = {
            "Supernode-0": {"A", "B"},
            "Supernode-1": {"C", "D"},
            "Supernode-2": {"E", "F"},
            "Supernode-3": {"G", "H"},
            "Supernode-4": {"I", "J"},
            "Supernode-5": {"K", "L"},
        }
        nx.set_node_attributes(G, supernodes, "group")
        return G


class TestSNAPUndirected(AbstractSNAP):
    def build_original_graph(self):
        nodes = {
            "A": {"color": "Red"},
            "B": {"color": "Red"},
            "C": {"color": "Red"},
            "D": {"color": "Red"},
            "E": {"color": "Blue"},
            "F": {"color": "Blue"},
            "G": {"color": "Blue"},
            "H": {"color": "Blue"},
            "I": {"color": "Yellow"},
            "J": {"color": "Yellow"},
            "K": {"color": "Yellow"},
            "L": {"color": "Yellow"},
        }
        edges = [
            ("A", "B", "Strong"),
            ("A", "C", "Weak"),
            ("A", "E", "Strong"),
            ("A", "I", "Weak"),
            ("B", "D", "Weak"),
            ("B", "J", "Weak"),
            ("B", "F", "Strong"),
            ("C", "G", "Weak"),
            ("D", "H", "Weak"),
            ("I", "J", "Strong"),
            ("J", "K", "Strong"),
            ("I", "L", "Strong"),
        ]
        G = nx.Graph()
        for node in nodes:
            attributes = nodes[node]
            G.add_node(node, **attributes)

        for source, target, type in edges:
            G.add_edge(source, target, type=type)

        return G

    def build_summary_graph(self):
        nodes = {
            "Supernode-0": {"color": "Red"},
            "Supernode-1": {"color": "Red"},
            "Supernode-2": {"color": "Blue"},
            "Supernode-3": {"color": "Blue"},
            "Supernode-4": {"color": "Yellow"},
            "Supernode-5": {"color": "Yellow"},
        }
        edges = [
            ("Supernode-0", "Supernode-0", "Strong"),
            ("Supernode-0", "Supernode-1", "Weak"),
            ("Supernode-0", "Supernode-2", "Strong"),
            ("Supernode-0", "Supernode-4", "Weak"),
            ("Supernode-1", "Supernode-3", "Weak"),
            ("Supernode-4", "Supernode-4", "Strong"),
            ("Supernode-4", "Supernode-5", "Strong"),
        ]
        G = nx.Graph()
        for node in nodes:
            attributes = nodes[node]
            G.add_node(node, **attributes)

        for source, target, type in edges:
            G.add_edge(source, target, types=[{"type": type}])

        supernodes = {
            "Supernode-0": {"A", "B"},
            "Supernode-1": {"C", "D"},
            "Supernode-2": {"E", "F"},
            "Supernode-3": {"G", "H"},
            "Supernode-4": {"I", "J"},
            "Supernode-5": {"K", "L"},
        }
        nx.set_node_attributes(G, supernodes, "group")
        return G


class TestSNAPDirected(AbstractSNAP):
    def build_original_graph(self):
        nodes = {
            "A": {"color": "Red"},
            "B": {"color": "Red"},
            "C": {"color": "Green"},
            "D": {"color": "Green"},
            "E": {"color": "Blue"},
            "F": {"color": "Blue"},
            "G": {"color": "Yellow"},
            "H": {"color": "Yellow"},
        }
        edges = [
            ("A", "C", "Strong"),
            ("A", "E", "Strong"),
            ("A", "F", "Weak"),
            ("B", "D", "Strong"),
            ("B", "E", "Weak"),
            ("B", "F", "Strong"),
            ("C", "G", "Strong"),
            ("C", "F", "Strong"),
            ("D", "E", "Strong"),
            ("D", "H", "Strong"),
            ("G", "E", "Strong"),
            ("H", "F", "Strong"),
        ]
        G = nx.DiGraph()
        for node in nodes:
            attributes = nodes[node]
            G.add_node(node, **attributes)

        for source, target, type in edges:
            G.add_edge(source, target, type=type)

        return G

    def build_summary_graph(self):
        nodes = {
            "Supernode-0": {"color": "Red"},
            "Supernode-1": {"color": "Green"},
            "Supernode-2": {"color": "Blue"},
            "Supernode-3": {"color": "Yellow"},
        }
        edges = [
            ("Supernode-0", "Supernode-1", [{"type": "Strong"}]),
            ("Supernode-0", "Supernode-2", [{"type": "Weak"}, {"type": "Strong"}]),
            ("Supernode-1", "Supernode-2", [{"type": "Strong"}]),
            ("Supernode-1", "Supernode-3", [{"type": "Strong"}]),
            ("Supernode-3", "Supernode-2", [{"type": "Strong"}]),
        ]
        G = nx.DiGraph()
        for node in nodes:
            attributes = nodes[node]
            G.add_node(node, **attributes)

        for source, target, types in edges:
            G.add_edge(source, target, types=types)

        supernodes = {
            "Supernode-0": {"A", "B"},
            "Supernode-1": {"C", "D"},
            "Supernode-2": {"E", "F"},
            "Supernode-3": {"G", "H"},
            "Supernode-4": {"I", "J"},
            "Supernode-5": {"K", "L"},
        }
        nx.set_node_attributes(G, supernodes, "group")
        return G


class TestSNAPUndirectedMulti(AbstractSNAP):
    def build_original_graph(self):
        nodes = {
            "A": {"color": "Red"},
            "B": {"color": "Red"},
            "C": {"color": "Red"},
            "D": {"color": "Blue"},
            "E": {"color": "Blue"},
            "F": {"color": "Blue"},
            "G": {"color": "Yellow"},
            "H": {"color": "Yellow"},
            "I": {"color": "Yellow"},
        }
        edges = [
            ("A", "D", ["Weak", "Strong"]),
            ("B", "E", ["Weak", "Strong"]),
            ("D", "I", ["Strong"]),
            ("E", "H", ["Strong"]),
            ("F", "G", ["Weak"]),
            ("I", "G", ["Weak", "Strong"]),
            ("I", "H", ["Weak", "Strong"]),
            ("G", "H", ["Weak", "Strong"]),
        ]
        G = nx.MultiGraph()
        for node in nodes:
            attributes = nodes[node]
            G.add_node(node, **attributes)

        for source, target, types in edges:
            for type in types:
                G.add_edge(source, target, type=type)

        return G

    def build_summary_graph(self):
        nodes = {
            "Supernode-0": {"color": "Red"},
            "Supernode-1": {"color": "Blue"},
            "Supernode-2": {"color": "Yellow"},
            "Supernode-3": {"color": "Blue"},
            "Supernode-4": {"color": "Yellow"},
            "Supernode-5": {"color": "Red"},
        }
        edges = [
            ("Supernode-1", "Supernode-2", [{"type": "Weak"}]),
            ("Supernode-2", "Supernode-4", [{"type": "Weak"}, {"type": "Strong"}]),
            ("Supernode-3", "Supernode-4", [{"type": "Strong"}]),
            ("Supernode-3", "Supernode-5", [{"type": "Weak"}, {"type": "Strong"}]),
            ("Supernode-4", "Supernode-4", [{"type": "Weak"}, {"type": "Strong"}]),
        ]
        G = nx.MultiGraph()
        for node in nodes:
            attributes = nodes[node]
            G.add_node(node, **attributes)

        for source, target, types in edges:
            for type in types:
                G.add_edge(source, target, type=type)

        supernodes = {
            "Supernode-0": {"A", "B"},
            "Supernode-1": {"C", "D"},
            "Supernode-2": {"E", "F"},
            "Supernode-3": {"G", "H"},
            "Supernode-4": {"I", "J"},
            "Supernode-5": {"K", "L"},
        }
        nx.set_node_attributes(G, supernodes, "group")
        return G


class TestSNAPDirectedMulti(AbstractSNAP):
    def build_original_graph(self):
        nodes = {
            "A": {"color": "Red"},
            "B": {"color": "Red"},
            "C": {"color": "Green"},
            "D": {"color": "Green"},
            "E": {"color": "Blue"},
            "F": {"color": "Blue"},
            "G": {"color": "Yellow"},
            "H": {"color": "Yellow"},
        }
        edges = [
            ("A", "C", ["Weak", "Strong"]),
            ("A", "E", ["Strong"]),
            ("A", "F", ["Weak"]),
            ("B", "D", ["Weak", "Strong"]),
            ("B", "E", ["Weak"]),
            ("B", "F", ["Strong"]),
            ("C", "G", ["Weak", "Strong"]),
            ("C", "F", ["Strong"]),
            ("D", "E", ["Strong"]),
            ("D", "H", ["Weak", "Strong"]),
            ("G", "E", ["Strong"]),
            ("H", "F", ["Strong"]),
        ]
        G = nx.MultiDiGraph()
        for node in nodes:
            attributes = nodes[node]
            G.add_node(node, **attributes)

        for source, target, types in edges:
            for type in types:
                G.add_edge(source, target, type=type)

        return G

    def build_summary_graph(self):
        nodes = {
            "Supernode-0": {"color": "Red"},
            "Supernode-1": {"color": "Blue"},
            "Supernode-2": {"color": "Yellow"},
            "Supernode-3": {"color": "Blue"},
        }
        edges = [
            ("Supernode-0", "Supernode-1", ["Weak", "Strong"]),
            ("Supernode-0", "Supernode-2", ["Weak", "Strong"]),
            ("Supernode-1", "Supernode-2", ["Strong"]),
            ("Supernode-1", "Supernode-3", ["Weak", "Strong"]),
            ("Supernode-3", "Supernode-2", ["Strong"]),
        ]
        G = nx.MultiDiGraph()
        for node in nodes:
            attributes = nodes[node]
            G.add_node(node, **attributes)

        for source, target, types in edges:
            for type in types:
                G.add_edge(source, target, type=type)

        supernodes = {
            "Supernode-0": {"A", "B"},
            "Supernode-1": {"C", "D"},
            "Supernode-2": {"E", "F"},
            "Supernode-3": {"G", "H"},
        }
        nx.set_node_attributes(G, supernodes, "group")
        return G
