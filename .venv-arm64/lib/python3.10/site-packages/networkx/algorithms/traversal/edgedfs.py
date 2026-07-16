"""
===========================
Depth First Search on Edges
===========================

Algorithms for a depth-first traversal of edges in a graph.

"""

import networkx as nx

FORWARD = "forward"
REVERSE = "reverse"

__all__ = ["edge_dfs"]


@nx._dispatchable
def edge_dfs(G, source=None, orientation=None):
    """A directed, depth-first-search of edges in `G`, beginning at `source`.

    Yield the edges of G in a depth-first-search order continuing until
    all edges are generated.

    Parameters
    ----------
    G : graph
        A directed/undirected graph/multigraph.

    source : node, list of nodes
        The node from which the traversal begins. If None, then a source
        is chosen arbitrarily and repeatedly until all edges from each node in
        the graph are searched.

    orientation : None | 'original' | 'reverse' | 'ignore' (default: None)
        For directed graphs and directed multigraphs, edge traversals need not
        respect the original orientation of the edges.
        When set to 'reverse' every edge is traversed in the reverse direction.
        When set to 'ignore', every edge is treated as undirected.
        When set to 'original', every edge is treated as directed.
        In all three cases, the yielded edge tuples add a last entry to
        indicate the direction in which that edge was traversed.
        If orientation is None, the yielded edge has no direction indicated.
        The direction is respected, but not reported.

    Yields
    ------
    edge : directed edge
        A directed edge indicating the path taken by the depth-first traversal.
        For graphs, `edge` is of the form `(u, v)` where `u` and `v`
        are the tail and head of the edge as determined by the traversal.
        For multigraphs, `edge` is of the form `(u, v, key)`, where `key` is
        the key of the edge. When the graph is directed, then `u` and `v`
        are always in the order of the actual directed edge.
        If orientation is not None then the edge tuple is extended to include
        the direction of traversal ('forward' or 'reverse') on that edge.

    Examples
    --------
    >>> nodes = [0, 1, 2, 3]
    >>> edges = [(0, 1), (1, 0), (1, 0), (2, 1), (3, 1)]

    >>> list(nx.edge_dfs(nx.Graph(edges), nodes))
    [(0, 1), (1, 2), (1, 3)]

    >>> list(nx.edge_dfs(nx.DiGraph(edges), nodes))
    [(0, 1), (1, 0), (2, 1), (3, 1)]

    >>> list(nx.edge_dfs(nx.MultiGraph(edges), nodes))
    [(0, 1, 0), (1, 0, 1), (0, 1, 2), (1, 2, 0), (1, 3, 0)]

    >>> list(nx.edge_dfs(nx.MultiDiGraph(edges), nodes))
    [(0, 1, 0), (1, 0, 0), (1, 0, 1), (2, 1, 0), (3, 1, 0)]

    >>> list(nx.edge_dfs(nx.DiGraph(edges), nodes, orientation="ignore"))
    [(0, 1, 'forward'), (1, 0, 'forward'), (2, 1, 'reverse'), (3, 1, 'reverse')]

    >>> list(nx.edge_dfs(nx.MultiDiGraph(edges), nodes, orientation="ignore"))
    [(0, 1, 0, 'forward'), (1, 0, 0, 'forward'), (1, 0, 1, 'reverse'), (2, 1, 0, 'reverse'), (3, 1, 0, 'reverse')]

    Notes
    -----
    The goal of this function is to visit edges. It differs from the more
    familiar depth-first traversal of nodes, as provided by
    :func:`~networkx.algorithms.traversal.depth_first_search.dfs_edges`, in
    that it does not stop once every node has been visited. In a directed graph
    with edges [(0, 1), (1, 2), (2, 1)], the edge (2, 1) would not be visited
    if not for the functionality provided by this function.

    See Also
    --------
    :func:`~networkx.algorithms.traversal.depth_first_search.dfs_edges`

    """
    nodes = list(G.nbunch_iter(source))
    if not nodes:
        return

    directed = G.is_directed()
    kwds = {"data": False}
    if G.is_multigraph() is True:
        kwds["keys"] = True

    # set up edge lookup
    if orientation is None:

        def edges_from(node):
            return iter(G.edges(node, **kwds))

    elif not directed or orientation == "original":

        def edges_from(node):
            for e in G.edges(node, **kwds):
                yield e + (FORWARD,)

    elif orientation == "reverse":

        def edges_from(node):
            for e in G.in_edges(node, **kwds):
                yield e + (REVERSE,)

    elif orientation == "ignore":

        def edges_from(node):
            for e in G.edges(node, **kwds):
                yield e + (FORWARD,)
            for e in G.in_edges(node, **kwds):
                yield e + (REVERSE,)

    else:
        raise nx.NetworkXError("invalid orientation argument.")

    # set up formation of edge_id to easily look up if edge already returned
    if directed:

        def edge_id(edge):
            # remove direction indicator
            return edge[:-1] if orientation is not None else edge

    else:

        def edge_id(edge):
            # single id for undirected requires frozenset on nodes
            return (frozenset(edge[:2]),) + edge[2:]

    # Basic setup
    check_reverse = directed and orientation in ("reverse", "ignore")

    visited_edges = set()
    visited_nodes = set()
    edges = {}

    # start DFS
    for start_node in nodes:
        stack = [start_node]
        while stack:
            current_node = stack[-1]
            if current_node not in visited_nodes:
                edges[current_node] = edges_from(current_node)
                visited_nodes.add(current_node)

            try:
                edge = next(edges[current_node])
            except StopIteration:
                # No more edges from the current node.
                stack.pop()
            else:
                edgeid = edge_id(edge)
                if edgeid not in visited_edges:
                    visited_edges.add(edgeid)
                    # Mark the traversed "to" node as to-be-explored.
                    if check_reverse and edge[-1] == REVERSE:
                        stack.append(edge[0])
                    else:
                        stack.append(edge[1])
                    yield edge
