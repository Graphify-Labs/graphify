import copy
import json

import pytest

import networkx as nx
from networkx.readwrite.json_graph import adjacency_data, adjacency_graph
from networkx.utils import graphs_equal


class TestAdjacency:
    def test_graph(self):
        G = nx.path_graph(4)
        H = adjacency_graph(adjacency_data(G))
        assert graphs_equal(G, H)

    def test_graph_attributes(self):
        G = nx.path_graph(4)
        G.add_node(1, color="red")
        G.add_edge(1, 2, width=7)
        G.graph["foo"] = "bar"
        G.graph[1] = "one"

        H = adjacency_graph(adjacency_data(G))
        assert graphs_equal(G, H)
        assert H.graph["foo"] == "bar"
        assert H.nodes[1]["color"] == "red"
        assert H[1][2]["width"] == 7

        d = json.dumps(adjacency_data(G))
        H = adjacency_graph(json.loads(d))
        assert graphs_equal(G, H)
        assert H.graph["foo"] == "bar"
        assert H.graph[1] == "one"
        assert H.nodes[1]["color"] == "red"
        assert H[1][2]["width"] == 7

    def test_digraph(self):
        G = nx.DiGraph()
        nx.add_path(G, [1, 2, 3])
        H = adjacency_graph(adjacency_data(G))
        assert H.is_directed()
        assert graphs_equal(G, H)

    def test_multidigraph(self):
        G = nx.MultiDiGraph()
        nx.add_path(G, [1, 2, 3])
        H = adjacency_graph(adjacency_data(G))
        assert H.is_directed()
        assert H.is_multigraph()
        assert graphs_equal(G, H)

    def test_multigraph(self):
        G = nx.MultiGraph()
        G.add_edge(1, 2, key="first")
        G.add_edge(1, 2, key="second", color="blue")
        H = adjacency_graph(adjacency_data(G))
        assert graphs_equal(G, H)
        assert H[1][2]["second"]["color"] == "blue"

    def test_input_data_is_not_modified_when_building_graph(self):
        G = nx.path_graph(4)
        input_data = adjacency_data(G)
        orig_data = copy.deepcopy(input_data)
        # Ensure input is unmodified by deserialisation
        assert graphs_equal(G, adjacency_graph(input_data))
        assert input_data == orig_data

    def test_adjacency_form_json_serialisable(self):
        G = nx.path_graph(4)
        H = adjacency_graph(json.loads(json.dumps(adjacency_data(G))))
        assert graphs_equal(G, H)

    def test_exception(self):
        with pytest.raises(nx.NetworkXError):
            G = nx.MultiDiGraph()
            attrs = {"id": "node", "key": "node"}
            adjacency_data(G, attrs)
