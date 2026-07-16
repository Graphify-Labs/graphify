import pytest

import networkx as nx
from networkx.convert import (
    from_dict_of_dicts,
    from_dict_of_lists,
    to_dict_of_dicts,
    to_dict_of_lists,
    to_networkx_graph,
)
from networkx.generators.classic import barbell_graph, cycle_graph
from networkx.utils import edges_equal, graphs_equal, nodes_equal


class TestConvert:
    def edgelists_equal(self, e1, e2):
        return sorted(sorted(e) for e in e1) == sorted(sorted(e) for e in e2)

    def test_simple_graphs(self):
        for dest, source in [
            (to_dict_of_dicts, from_dict_of_dicts),
            (to_dict_of_lists, from_dict_of_lists),
        ]:
            G = barbell_graph(10, 3)
            G.graph = {}
            dod = dest(G)

            # Dict of [dicts, lists]
            GG = source(dod)
            assert graphs_equal(G, GG)
            GW = to_networkx_graph(dod)
            assert graphs_equal(G, GW)
            GI = nx.Graph(dod)
            assert graphs_equal(G, GI)

            # With nodelist keyword
            P4 = nx.path_graph(4)
            P3 = nx.path_graph(3)
            P4.graph = {}
            P3.graph = {}
            dod = dest(P4, nodelist=[0, 1, 2])
            Gdod = nx.Graph(dod)
            assert graphs_equal(Gdod, P3)

    def test_exceptions(self):
        # NX graph
        class G:
            adj = None

        pytest.raises(nx.NetworkXError, to_networkx_graph, G)

        # pygraphviz  agraph
        class G:
            is_strict = None

        pytest.raises(nx.NetworkXError, to_networkx_graph, G)

        # Dict of [dicts, lists]
        G = {"a": 0}
        pytest.raises(TypeError, to_networkx_graph, G)

        # list or generator of edges
        class G:
            next = None

        pytest.raises(nx.NetworkXError, to_networkx_graph, G)

        # no match
        pytest.raises(nx.NetworkXError, to_networkx_graph, "a")

    def test_digraphs(self):
        for dest, source in [
            (to_dict_of_dicts, from_dict_of_dicts),
            (to_dict_of_lists, from_dict_of_lists),
        ]:
            G = cycle_graph(10)

            # Dict of [dicts, lists]
            dod = dest(G)
            GG = source(dod)
            assert nodes_equal(sorted(G.nodes()), sorted(GG.nodes()))
            assert edges_equal(sorted(G.edges()), sorted(GG.edges()))
            GW = to_networkx_graph(dod)
            assert nodes_equal(sorted(G.nodes()), sorted(GW.nodes()))
            assert edges_equal(sorted(G.edges()), sorted(GW.edges()))
            GI = nx.Graph(dod)
            assert nodes_equal(sorted(G.nodes()), sorted(GI.nodes()))
            assert edges_equal(sorted(G.edges()), sorted(GI.edges()))

            G = cycle_graph(10, create_using=nx.DiGraph)
            dod = dest(G)
            GG = source(dod, create_using=nx.DiGraph)
            assert sorted(G.nodes()) == sorted(GG.nodes())
            assert sorted(G.edges()) == sorted(GG.edges())
            GW = to_networkx_graph(dod, create_using=nx.DiGraph)
            assert sorted(G.nodes()) == sorted(GW.nodes())
            assert sorted(G.edges()) == sorted(GW.edges())
            GI = nx.DiGraph(dod)
            assert sorted(G.nodes()) == sorted(GI.nodes())
            assert sorted(G.edges()) == sorted(GI.edges())

    def test_graph(self):
        g = nx.cycle_graph(10)
        G = nx.Graph()
        G.add_nodes_from(g)
        G.add_weighted_edges_from((u, v, u) for u, v in g.edges())

        # Dict of dicts
        dod = to_dict_of_dicts(G)
        GG = from_dict_of_dicts(dod, create_using=nx.Graph)
        assert nodes_equal(sorted(G.nodes()), sorted(GG.nodes()))
        assert edges_equal(sorted(G.edges()), sorted(GG.edges()))
        GW = to_networkx_graph(dod, create_using=nx.Graph)
        assert nodes_equal(sorted(G.nodes()), sorted(GW.nodes()))
        assert edges_equal(sorted(G.edges()), sorted(GW.edges()))
        GI = nx.Graph(dod)
        assert sorted(G.nodes()) == sorted(GI.nodes())
        assert sorted(G.edges()) == sorted(GI.edges())

        # Dict of lists
        dol = to_dict_of_lists(G)
        GG = from_dict_of_lists(dol, create_using=nx.Graph)
        # dict of lists throws away edge data so set it to none
        enone = [(u, v, {}) for (u, v, d) in G.edges(data=True)]
        assert nodes_equal(sorted(G.nodes()), sorted(GG.nodes()))
        assert edges_equal(enone, sorted(GG.edges(data=True)))
        GW = to_networkx_graph(dol, create_using=nx.Graph)
        assert nodes_equal(sorted(G.nodes()), sorted(GW.nodes()))
        assert edges_equal(enone, sorted(GW.edges(data=True)))
        GI = nx.Graph(dol)
        assert nodes_equal(sorted(G.nodes()), sorted(GI.nodes()))
        assert edges_equal(enone, sorted(GI.edges(data=True)))

    def test_with_multiedges_self_loops(self):
        G = cycle_graph(10)
        XG = nx.Graph()
        XG.add_nodes_from(G)
        XG.add_weighted_edges_from((u, v, u) for u, v in G.edges())
        XGM = nx.MultiGraph()
        XGM.add_nodes_from(G)
        XGM.add_weighted_edges_from((u, v, u) for u, v in G.edges())
        XGM.add_edge(0, 1, weight=2)  # multiedge
        XGS = nx.Graph()
        XGS.add_nodes_from(G)
        XGS.add_weighted_edges_from((u, v, u) for u, v in G.edges())
        XGS.add_edge(0, 0, weight=100)  # self loop

        # Dict of dicts
        # with self loops, OK
        dod = to_dict_of_dicts(XGS)
        GG = from_dict_of_dicts(dod, create_using=nx.Graph)
        assert nodes_equal(XGS.nodes(), GG.nodes())
        assert edges_equal(XGS.edges(), GG.edges())
        GW = to_networkx_graph(dod, create_using=nx.Graph)
        assert nodes_equal(XGS.nodes(), GW.nodes())
        assert edges_equal(XGS.edges(), GW.edges())
        GI = nx.Graph(dod)
        assert nodes_equal(XGS.nodes(), GI.nodes())
        assert edges_equal(XGS.edges(), GI.edges())

        # Dict of lists
        # with self loops, OK
        dol = to_dict_of_lists(XGS)
        GG = from_dict_of_lists(dol, create_using=nx.Graph)
        # dict of lists throws away edge data so set it to none
        enone = [(u, v, {}) for (u, v, d) in XGS.edges(data=True)]
        assert nodes_equal(sorted(XGS.nodes()), sorted(GG.nodes()))
        assert edges_equal(enone, sorted(GG.edges(data=True)))
        GW = to_networkx_graph(dol, create_using=nx.Graph)
        assert nodes_equal(sorted(XGS.nodes()), sorted(GW.nodes()))
        assert edges_equal(enone, sorted(GW.edges(data=True)))
        GI = nx.Graph(dol)
        assert nodes_equal(sorted(XGS.nodes()), sorted(GI.nodes()))
        assert edges_equal(enone, sorted(GI.edges(data=True)))

        # Dict of dicts
        # with multiedges, OK
        dod = to_dict_of_dicts(XGM)
        GG = from_dict_of_dicts(dod, create_using=nx.MultiGraph, multigraph_input=True)
        assert nodes_equal(sorted(XGM.nodes()), sorted(GG.nodes()))
        assert edges_equal(sorted(XGM.edges()), sorted(GG.edges()))
        GW = to_networkx_graph(dod, create_using=nx.MultiGraph, multigraph_input=True)
        assert nodes_equal(sorted(XGM.nodes()), sorted(GW.nodes()))
        assert edges_equal(sorted(XGM.edges()), sorted(GW.edges()))
        GI = nx.MultiGraph(dod)
        assert nodes_equal(sorted(XGM.nodes()), sorted(GI.nodes()))
        assert sorted(XGM.edges()) == sorted(GI.edges())
        GE = from_dict_of_dicts(dod, create_using=nx.MultiGraph, multigraph_input=False)
        assert nodes_equal(sorted(XGM.nodes()), sorted(GE.nodes()))
        assert sorted(XGM.edges()) != sorted(GE.edges())
        GI = nx.MultiGraph(XGM)
        assert nodes_equal(sorted(XGM.nodes()), sorted(GI.nodes()))
        assert edges_equal(sorted(XGM.edges()), sorted(GI.edges()))
        GM = nx.MultiGraph(G)
        assert nodes_equal(sorted(GM.nodes()), sorted(G.nodes()))
        assert edges_equal(sorted(GM.edges()), sorted(G.edges()))

        # Dict of lists
        # with multiedges, OK, but better write as DiGraph else you'll
        # get double edges
        dol = to_dict_of_lists(G)
        GG = from_dict_of_lists(dol, create_using=nx.MultiGraph)
        assert nodes_equal(sorted(G.nodes()), sorted(GG.nodes()))
        assert edges_equal(sorted(G.edges()), sorted(GG.edges()))
        GW = to_networkx_graph(dol, create_using=nx.MultiGraph)
        assert nodes_equal(sorted(G.nodes()), sorted(GW.nodes()))
        assert edges_equal(sorted(G.edges()), sorted(GW.edges()))
        GI = nx.MultiGraph(dol)
        assert nodes_equal(sorted(G.nodes()), sorted(GI.nodes()))
        assert edges_equal(sorted(G.edges()), sorted(GI.edges()))

    def test_edgelists(self):
        P = nx.path_graph(4)
        e = [(0, 1), (1, 2), (2, 3)]
        G = nx.Graph(e)
        assert nodes_equal(sorted(G.nodes()), sorted(P.nodes()))
        assert edges_equal(sorted(G.edges()), sorted(P.edges()))
        assert edges_equal(sorted(G.edges(data=True)), sorted(P.edges(data=True)))

        e = [(0, 1, {}), (1, 2, {}), (2, 3, {})]
        G = nx.Graph(e)
        assert nodes_equal(sorted(G.nodes()), sorted(P.nodes()))
        assert edges_equal(sorted(G.edges()), sorted(P.edges()))
        assert edges_equal(sorted(G.edges(data=True)), sorted(P.edges(data=True)))

        e = ((n, n + 1) for n in range(3))
        G = nx.Graph(e)
        assert nodes_equal(sorted(G.nodes()), sorted(P.nodes()))
        assert edges_equal(sorted(G.edges()), sorted(P.edges()))
        assert edges_equal(sorted(G.edges(data=True)), sorted(P.edges(data=True)))

    def test_directed_to_undirected(self):
        edges1 = [(0, 1), (1, 2), (2, 0)]
        edges2 = [(0, 1), (1, 2), (0, 2)]
        assert self.edgelists_equal(nx.Graph(nx.DiGraph(edges1)).edges(), edges1)
        assert self.edgelists_equal(nx.Graph(nx.DiGraph(edges2)).edges(), edges1)
        assert self.edgelists_equal(nx.MultiGraph(nx.DiGraph(edges1)).edges(), edges1)
        assert self.edgelists_equal(nx.MultiGraph(nx.DiGraph(edges2)).edges(), edges1)

        assert self.edgelists_equal(
            nx.MultiGraph(nx.MultiDiGraph(edges1)).edges(), edges1
        )
        assert self.edgelists_equal(
            nx.MultiGraph(nx.MultiDiGraph(edges2)).edges(), edges1
        )

        assert self.edgelists_equal(nx.Graph(nx.MultiDiGraph(edges1)).edges(), edges1)
        assert self.edgelists_equal(nx.Graph(nx.MultiDiGraph(edges2)).edges(), edges1)

    def test_attribute_dict_integrity(self):
        # we must not replace dict-like graph data structures with dicts
        G = nx.Graph()
        G.add_nodes_from("abc")
        H = to_networkx_graph(G, create_using=nx.Graph)
        assert list(H.nodes) == list(G.nodes)
        H = nx.DiGraph(G)
        assert list(H.nodes) == list(G.nodes)

    def test_to_edgelist(self):
        G = nx.Graph([(1, 1)])
        elist = nx.to_edgelist(G, nodelist=list(G))
        assert edges_equal(G.edges(data=True), elist)

    def test_custom_node_attr_dict_safekeeping(self):
        class custom_dict(dict):
            pass

        class Custom(nx.Graph):
            node_attr_dict_factory = custom_dict

        g = nx.Graph()
        g.add_node(1, weight=1)

        h = Custom(g)
        assert isinstance(g._node[1], dict)
        assert isinstance(h._node[1], custom_dict)

        # this raise exception
        # h._node.update((n, dd.copy()) for n, dd in g.nodes.items())
        # assert isinstance(h._node[1], custom_dict)


@pytest.mark.parametrize(
    "edgelist",
    (
        # Graph with no edge data
        [(0, 1), (1, 2)],
        # Graph with edge data
        [(0, 1, {"weight": 1.0}), (1, 2, {"weight": 2.0})],
    ),
)
def test_to_dict_of_dicts_with_edgedata_param(edgelist):
    G = nx.Graph()
    G.add_edges_from(edgelist)
    # Innermost dict value == edge_data when edge_data != None.
    # In the case when G has edge data, it is overwritten
    expected = {0: {1: 10}, 1: {0: 10, 2: 10}, 2: {1: 10}}
    assert nx.to_dict_of_dicts(G, edge_data=10) == expected


def test_to_dict_of_dicts_with_edgedata_and_nodelist():
    G = nx.path_graph(5)
    nodelist = [2, 3, 4]
    expected = {2: {3: 10}, 3: {2: 10, 4: 10}, 4: {3: 10}}
    assert nx.to_dict_of_dicts(G, nodelist=nodelist, edge_data=10) == expected


def test_to_dict_of_dicts_with_edgedata_multigraph():
    """Multi edge data overwritten when edge_data != None"""
    G = nx.MultiGraph()
    G.add_edge(0, 1, key="a")
    G.add_edge(0, 1, key="b")
    # Multi edge data lost when edge_data is not None
    expected = {0: {1: 10}, 1: {0: 10}}
    assert nx.to_dict_of_dicts(G, edge_data=10) == expected


def test_to_networkx_graph_non_edgelist():
    invalid_edgelist = [1, 2, 3]
    with pytest.raises(nx.NetworkXError, match="Input is not a valid edge list"):
        nx.to_networkx_graph(invalid_edgelist)
