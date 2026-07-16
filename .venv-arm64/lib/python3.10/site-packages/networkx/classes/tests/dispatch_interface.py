# This file contains utilities for testing the dispatching feature

# A full test of all dispatchable algorithms is performed by
# modifying the pytest invocation and setting an environment variable
# NETWORKX_TEST_BACKEND=nx_loopback pytest
# This is comprehensive, but only tests the `test_override_dispatch`
# function in networkx.classes.backends.

# To test the `_dispatchable` function directly, several tests scattered throughout
# NetworkX have been augmented to test normal and dispatch mode.
# Searching for `dispatch_interface` should locate the specific tests.

import networkx as nx
from networkx import DiGraph, Graph, MultiDiGraph, MultiGraph, PlanarEmbedding
from networkx.classes.reportviews import NodeView


class LoopbackGraph(Graph):
    __networkx_backend__ = "nx_loopback"


class LoopbackDiGraph(DiGraph):
    __networkx_backend__ = "nx_loopback"


class LoopbackMultiGraph(MultiGraph):
    __networkx_backend__ = "nx_loopback"


class LoopbackMultiDiGraph(MultiDiGraph):
    __networkx_backend__ = "nx_loopback"


class LoopbackPlanarEmbedding(PlanarEmbedding):
    __networkx_backend__ = "nx_loopback"


def convert(graph):
    if isinstance(graph, PlanarEmbedding):
        return LoopbackPlanarEmbedding(graph)
    if isinstance(graph, MultiDiGraph):
        return LoopbackMultiDiGraph(graph)
    if isinstance(graph, MultiGraph):
        return LoopbackMultiGraph(graph)
    if isinstance(graph, DiGraph):
        return LoopbackDiGraph(graph)
    if isinstance(graph, Graph):
        return LoopbackGraph(graph)
    raise TypeError(f"Unsupported type of graph: {type(graph)}")


class LoopbackBackendInterface:
    def __getattr__(self, item):
        try:
            return nx.utils.backends._registered_algorithms[item].orig_func
        except KeyError:
            raise AttributeError(item) from None

    @staticmethod
    def convert_from_nx(
        graph,
        *,
        edge_attrs=None,
        node_attrs=None,
        preserve_edge_attrs=None,
        preserve_node_attrs=None,
        preserve_graph_attrs=None,
        name=None,
        graph_name=None,
    ):
        if name in {
            # Raise if input graph changes. See test_dag.py::test_topological_sort6
            "lexicographical_topological_sort",
            "topological_generations",
            "topological_sort",
            # Would be nice to some day avoid these cutoffs of full testing
        }:
            return graph
        if isinstance(graph, NodeView):
            # Convert to a Graph with only nodes (no edges)
            new_graph = Graph()
            new_graph.add_nodes_from(graph.items())
            graph = new_graph
            G = LoopbackGraph()
        elif not isinstance(graph, Graph):
            raise TypeError(
                f"Bad type for graph argument {graph_name} in {name}: {type(graph)}"
            )
        elif graph.__class__ in {Graph, LoopbackGraph}:
            G = LoopbackGraph()
        elif graph.__class__ in {DiGraph, LoopbackDiGraph}:
            G = LoopbackDiGraph()
        elif graph.__class__ in {MultiGraph, LoopbackMultiGraph}:
            G = LoopbackMultiGraph()
        elif graph.__class__ in {MultiDiGraph, LoopbackMultiDiGraph}:
            G = LoopbackMultiDiGraph()
        elif graph.__class__ in {PlanarEmbedding, LoopbackPlanarEmbedding}:
            G = LoopbackDiGraph()  # or LoopbackPlanarEmbedding
        else:
            # Would be nice to handle these better some day
            # nx.algorithms.approximation.kcomponents._AntiGraph
            # nx.classes.tests.test_multidigraph.MultiDiGraphSubClass
            # nx.classes.tests.test_multigraph.MultiGraphSubClass
            G = graph.__class__()

        if preserve_graph_attrs:
            G.graph.update(graph.graph)

        # add nodes
        G.add_nodes_from(graph)
        if preserve_node_attrs:
            for n, dd in G._node.items():
                dd.update(graph.nodes[n])
        elif node_attrs:
            for n, dd in G._node.items():
                dd.update(
                    (attr, graph._node[n].get(attr, default))
                    for attr, default in node_attrs.items()
                    if default is not None or attr in graph._node[n]
                )

        # tools to build datadict and keydict
        if preserve_edge_attrs:

            def G_new_datadict(old_dd):
                return G.edge_attr_dict_factory(old_dd)
        elif edge_attrs:

            def G_new_datadict(old_dd):
                return G.edge_attr_dict_factory(
                    (attr, old_dd.get(attr, default))
                    for attr, default in edge_attrs.items()
                    if default is not None or attr in old_dd
                )
        else:

            def G_new_datadict(old_dd):
                return G.edge_attr_dict_factory()

        if G.is_multigraph():

            def G_new_inner(keydict):
                kd = G.adjlist_inner_dict_factory(
                    (k, G_new_datadict(dd)) for k, dd in keydict.items()
                )
                return kd
        else:
            G_new_inner = G_new_datadict

        # add edges keeping the same order in _adj and _pred
        G_adj = G._adj
        if G.is_directed():
            for n, nbrs in graph._adj.items():
                G_adj[n].update((nbr, G_new_inner(dd)) for nbr, dd in nbrs.items())
            # ensure same datadict for pred and adj; and pred order of graph._pred
            G_pred = G._pred
            for n, nbrs in graph._pred.items():
                G_pred[n].update((nbr, G_adj[nbr][n]) for nbr in nbrs)
        else:  # undirected
            for n, nbrs in graph._adj.items():
                # ensure same datadict for both ways; and adj order of graph._adj
                G_adj[n].update(
                    (nbr, G_adj[nbr][n] if n in G_adj[nbr] else G_new_inner(dd))
                    for nbr, dd in nbrs.items()
                )

        return G

    @staticmethod
    def convert_to_nx(obj, *, name=None):
        return obj

    @staticmethod
    def on_start_tests(items):
        # Verify that items can be xfailed
        for item in items:
            assert hasattr(item, "add_marker")

    def can_run(self, name, args, kwargs):
        # It is unnecessary to define this function if algorithms are fully supported.
        # We include it for illustration purposes.
        return hasattr(self, name)


backend_interface = LoopbackBackendInterface()
