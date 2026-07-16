"""Bridge-finding algorithms."""

from itertools import chain

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = ["bridges", "has_bridges", "local_bridges"]


@not_implemented_for("directed")
@nx._dispatchable
def bridges(G, root=None):
    """Generate all bridges in a graph.

    A *bridge* in a graph is an edge whose removal causes the number of
    connected components of the graph to increase.  Equivalently, a bridge is an
    edge that does not belong to any cycle. Bridges are also known as cut-edges,
    isthmuses, or cut arcs.

    Parameters
    ----------
    G : undirected graph

    root : node (optional)
       A node in the graph `G`. If specified, only the bridges in the
       connected component containing this node will be returned.

    Yields
    ------
    e : edge
       An edge in the graph whose removal disconnects the graph (or
       causes the number of connected components to increase).

    Raises
    ------
    NodeNotFound
       If `root` is not in the graph `G`.

    NetworkXNotImplemented
        If `G` is a directed graph.

    Examples
    --------
    The barbell graph with parameter zero has a single bridge:

    >>> G = nx.barbell_graph(10, 0)
    >>> list(nx.bridges(G))
    [(9, 10)]

    Notes
    -----
    This is an implementation of the algorithm described in [1]_.  An edge is a
    bridge if and only if it is not contained in any chain. Chains are found
    using the :func:`networkx.chain_decomposition` function.

    The algorithm described in [1]_ requires a simple graph. If the provided
    graph is a multigraph, we convert it to a simple graph and verify that any
    bridges discovered by the chain decomposition algorithm are not multi-edges.

    Ignoring polylogarithmic factors, the worst-case time complexity is the
    same as the :func:`networkx.chain_decomposition` function,
    $O(m + n)$, where $n$ is the number of nodes in the graph and $m$ is
    the number of edges.

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/Bridge_%28graph_theory%29#Bridge-Finding_with_Chain_Decompositions
    """
    multigraph = G.is_multigraph()
    H = nx.Graph(G) if multigraph else G
    chains = nx.chain_decomposition(H, root=root)
    chain_edges = set(chain.from_iterable(chains))
    if root is not None:
        H = H.subgraph(nx.node_connected_component(H, root)).copy()
    for u, v in H.edges():
        if (u, v) not in chain_edges and (v, u) not in chain_edges:
            if multigraph and len(G[u][v]) > 1:
                continue
            yield u, v


@not_implemented_for("directed")
@nx._dispatchable
def has_bridges(G, root=None):
    """Decide whether a graph has any bridges.

    A *bridge* in a graph is an edge whose removal causes the number of
    connected components of the graph to increase.

    Parameters
    ----------
    G : undirected graph

    root : node (optional)
       A node in the graph `G`. If specified, only the bridges in the
       connected component containing this node will be considered.

    Returns
    -------
    bool
       Whether the graph (or the connected component containing `root`)
       has any bridges.

    Raises
    ------
    NodeNotFound
       If `root` is not in the graph `G`.

    NetworkXNotImplemented
        If `G` is a directed graph.

    Examples
    --------
    The barbell graph with parameter zero has a single bridge::

        >>> G = nx.barbell_graph(10, 0)
        >>> nx.has_bridges(G)
        True

    On the other hand, the cycle graph has no bridges::

        >>> G = nx.cycle_graph(5)
        >>> nx.has_bridges(G)
        False

    Notes
    -----
    This implementation uses the :func:`networkx.bridges` function, so
    it shares its worst-case time complexity, $O(m + n)$, ignoring
    polylogarithmic factors, where $n$ is the number of nodes in the
    graph and $m$ is the number of edges.

    """
    try:
        next(bridges(G, root=root))
    except StopIteration:
        return False
    else:
        return True


@not_implemented_for("multigraph")
@not_implemented_for("directed")
@nx._dispatchable(edge_attrs="weight")
def local_bridges(G, with_span=True, weight=None):
    """Iterate over local bridges of `G` optionally computing the span

    A *local bridge* is an edge whose endpoints have no common neighbors.
    That is, the edge is not part of a triangle in the graph.

    The *span* of a *local bridge* is the shortest path length between
    the endpoints if the local bridge is removed.

    Parameters
    ----------
    G : undirected graph

    with_span : bool
        If True, yield a 3-tuple `(u, v, span)`

    weight : function, string or None (default: None)
        If function, used to compute edge weights for the span.
        If string, the edge data attribute used in calculating span.
        If None, all edges have weight 1.

    Yields
    ------
    e : edge
        The local bridges as an edge 2-tuple of nodes `(u, v)` or
        as a 3-tuple `(u, v, span)` when `with_span is True`.

    Raises
    ------
    NetworkXNotImplemented
        If `G` is a directed graph or multigraph.

    Examples
    --------
    A cycle graph has every edge a local bridge with span N-1.

       >>> G = nx.cycle_graph(9)
       >>> (0, 8, 8) in set(nx.local_bridges(G))
       True
    """
    if with_span is not True:
        for u, v in G.edges:
            if not (set(G[u]) & set(G[v])):
                yield u, v
    else:
        wt = nx.weighted._weight_function(G, weight)
        for u, v in G.edges:
            if not (set(G[u]) & set(G[v])):
                enodes = {u, v}

                def hide_edge(n, nbr, d):
                    if n not in enodes or nbr not in enodes:
                        return wt(n, nbr, d)
                    return None

                try:
                    span = nx.shortest_path_length(G, u, v, weight=hide_edge)
                    yield u, v, span
                except nx.NetworkXNoPath:
                    yield u, v, float("inf")
