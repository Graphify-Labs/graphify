"""View of Graphs as SubGraph, Reverse, Directed, Undirected.

In some algorithms it is convenient to temporarily morph
a graph to exclude some nodes or edges. It should be better
to do that via a view than to remove and then re-add.
In other algorithms it is convenient to temporarily morph
a graph to reverse directed edges, or treat a directed graph
as undirected, etc. This module provides those graph views.

The resulting views are essentially read-only graphs that
report data from the original graph object. We provide an
attribute G._graph which points to the underlying graph object.

Note: Since graphviews look like graphs, one can end up with
view-of-view-of-view chains. Be careful with chains because
they become very slow with about 15 nested views.
For the common simple case of node induced subgraphs created
from the graph class, we short-cut the chain by returning a
subgraph of the original graph directly rather than a subgraph
of a subgraph. We are careful not to disrupt any edge filter in
the middle subgraph. In general, determining how to short-cut
the chain is tricky and much harder with restricted_views than
with induced subgraphs.
Often it is easiest to use .copy() to avoid chains.
"""

import networkx as nx
from networkx.classes.coreviews import (
    FilterAdjacency,
    FilterAtlas,
    FilterMultiAdjacency,
    UnionAdjacency,
    UnionMultiAdjacency,
)
from networkx.classes.filters import no_filter
from networkx.exception import NetworkXError
from networkx.utils import not_implemented_for

__all__ = ["generic_graph_view", "subgraph_view", "reverse_view"]


def generic_graph_view(G, create_using=None):
    """Returns a read-only view of `G`.

    The graph `G` and its attributes are not copied but viewed through the new graph object
    of the same class as `G` (or of the class specified in `create_using`).

    Parameters
    ----------
    G : graph
        A directed/undirected graph/multigraph.

    create_using : NetworkX graph constructor, optional (default=None)
       Graph type to create. If graph instance, then cleared before populated.
       If `None`, then the appropriate Graph type is inferred from `G`.

    Returns
    -------
    newG : graph
        A view of the input graph `G` and its attributes as viewed through
        the `create_using` class.

    Raises
    ------
    NetworkXError
        If `G` is a multigraph (or multidigraph) but `create_using` is not, or vice versa.

    Notes
    -----
    The returned graph view is read-only (cannot modify the graph).
    Yet the view reflects any changes in `G`. The intent is to mimic dict views.

    Examples
    --------
    >>> G = nx.Graph()
    >>> G.add_edge(1, 2, weight=0.3)
    >>> G.add_edge(2, 3, weight=0.5)
    >>> G.edges(data=True)
    EdgeDataView([(1, 2, {'weight': 0.3}), (2, 3, {'weight': 0.5})])

    The view exposes the attributes from the original graph.

    >>> viewG = nx.graphviews.generic_graph_view(G)
    >>> viewG.edges(data=True)
    EdgeDataView([(1, 2, {'weight': 0.3}), (2, 3, {'weight': 0.5})])

    Changes to `G` are reflected in `viewG`.

    >>> G.remove_edge(2, 3)
    >>> G.edges(data=True)
    EdgeDataView([(1, 2, {'weight': 0.3})])

    >>> viewG.edges(data=True)
    EdgeDataView([(1, 2, {'weight': 0.3})])

    We can change the graph type with the `create_using` parameter.

    >>> type(G)
    <class 'networkx.classes.graph.Graph'>
    >>> viewDG = nx.graphviews.generic_graph_view(G, create_using=nx.DiGraph)
    >>> type(viewDG)
    <class 'networkx.classes.digraph.DiGraph'>
    """
    if create_using is None:
        newG = G.__class__()
    else:
        newG = nx.empty_graph(0, create_using)
    if G.is_multigraph() != newG.is_multigraph():
        raise NetworkXError("Multigraph for G must agree with create_using")
    newG = nx.freeze(newG)

    # create view by assigning attributes from G
    newG._graph = G
    newG.graph = G.graph

    newG._node = G._node
    if newG.is_directed():
        if G.is_directed():
            newG._succ = G._succ
            newG._pred = G._pred
            # newG._adj is synced with _succ
        else:
            newG._succ = G._adj
            newG._pred = G._adj
            # newG._adj is synced with _succ
    elif G.is_directed():
        if G.is_multigraph():
            newG._adj = UnionMultiAdjacency(G._succ, G._pred)
        else:
            newG._adj = UnionAdjacency(G._succ, G._pred)
    else:
        newG._adj = G._adj
    return newG


def subgraph_view(G, *, filter_node=no_filter, filter_edge=no_filter):
    """View of `G` applying a filter on nodes and edges.

    `subgraph_view` provides a read-only view of the input graph that excludes
    nodes and edges based on the outcome of two filter functions `filter_node`
    and `filter_edge`.

    The `filter_node` function takes one argument --- the node --- and returns
    `True` if the node should be included in the subgraph, and `False` if it
    should not be included.

    The `filter_edge` function takes two (or three arguments if `G` is a
    multi-graph) --- the nodes describing an edge, plus the edge-key if
    parallel edges are possible --- and returns `True` if the edge should be
    included in the subgraph, and `False` if it should not be included.

    Both node and edge filter functions are called on graph elements as they
    are queried, meaning there is no up-front cost to creating the view.

    Parameters
    ----------
    G : networkx.Graph
        A directed/undirected graph/multigraph

    filter_node : callable, optional
        A function taking a node as input, which returns `True` if the node
        should appear in the view.

    filter_edge : callable, optional
        A function taking as input the two nodes describing an edge (plus the
        edge-key if `G` is a multi-graph), which returns `True` if the edge
        should appear in the view.

    Returns
    -------
    graph : networkx.Graph
        A read-only graph view of the input graph.

    Examples
    --------
    >>> G = nx.path_graph(6)

    Filter functions operate on the node, and return `True` if the node should
    appear in the view:

    >>> def filter_node(n1):
    ...     return n1 != 5
    >>> view = nx.subgraph_view(G, filter_node=filter_node)
    >>> view.nodes()
    NodeView((0, 1, 2, 3, 4))

    We can use a closure pattern to filter graph elements based on additional
    data --- for example, filtering on edge data attached to the graph:

    >>> G[3][4]["cross_me"] = False
    >>> def filter_edge(n1, n2):
    ...     return G[n1][n2].get("cross_me", True)
    >>> view = nx.subgraph_view(G, filter_edge=filter_edge)
    >>> view.edges()
    EdgeView([(0, 1), (1, 2), (2, 3), (4, 5)])

    >>> view = nx.subgraph_view(
    ...     G,
    ...     filter_node=filter_node,
    ...     filter_edge=filter_edge,
    ... )
    >>> view.nodes()
    NodeView((0, 1, 2, 3, 4))
    >>> view.edges()
    EdgeView([(0, 1), (1, 2), (2, 3)])
    """
    newG = nx.freeze(G.__class__())
    newG._NODE_OK = filter_node
    newG._EDGE_OK = filter_edge

    # create view by assigning attributes from G
    newG._graph = G
    newG.graph = G.graph

    newG._node = FilterAtlas(G._node, filter_node)
    if G.is_multigraph():
        Adj = FilterMultiAdjacency

        def reverse_edge(u, v, k=None):
            return filter_edge(v, u, k)

    else:
        Adj = FilterAdjacency

        def reverse_edge(u, v, k=None):
            return filter_edge(v, u)

    if G.is_directed():
        newG._succ = Adj(G._succ, filter_node, filter_edge)
        newG._pred = Adj(G._pred, filter_node, reverse_edge)
        # newG._adj is synced with _succ
    else:
        newG._adj = Adj(G._adj, filter_node, filter_edge)
    return newG


@not_implemented_for("undirected")
def reverse_view(G):
    """View of `G` with edge directions reversed

    `reverse_view` returns a read-only view of the input graph where
    edge directions are reversed.

    Identical to digraph.reverse(copy=False)

    Parameters
    ----------
    G : networkx.DiGraph

    Returns
    -------
    graph : networkx.DiGraph

    Examples
    --------
    >>> G = nx.DiGraph()
    >>> G.add_edge(1, 2)
    >>> G.add_edge(2, 3)
    >>> G.edges()
    OutEdgeView([(1, 2), (2, 3)])

    >>> view = nx.reverse_view(G)
    >>> view.edges()
    OutEdgeView([(2, 1), (3, 2)])
    """
    newG = generic_graph_view(G)
    newG._succ, newG._pred = G._pred, G._succ
    # newG._adj is synced with _succ
    return newG
