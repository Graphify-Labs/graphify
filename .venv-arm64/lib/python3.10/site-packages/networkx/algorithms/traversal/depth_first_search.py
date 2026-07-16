"""Basic algorithms for depth-first searching the nodes of a graph."""

from collections import defaultdict

import networkx as nx

__all__ = [
    "dfs_edges",
    "dfs_tree",
    "dfs_predecessors",
    "dfs_successors",
    "dfs_preorder_nodes",
    "dfs_postorder_nodes",
    "dfs_labeled_edges",
]


@nx._dispatchable
def dfs_edges(G, source=None, depth_limit=None, *, sort_neighbors=None):
    """Iterate over edges in a depth-first-search (DFS).

    Perform a depth-first-search over the nodes of `G` and yield
    the edges in order. This may not generate all edges in `G`
    (see `~networkx.algorithms.traversal.edgedfs.edge_dfs`).

    Parameters
    ----------
    G : NetworkX graph

    source : node, optional
       Specify starting node for depth-first search and yield edges in
       the component reachable from source.

    depth_limit : int, optional (default=len(G))
       Specify the maximum search depth.

    sort_neighbors : function (default=None)
        A function that takes an iterator over nodes as the input, and
        returns an iterable of the same nodes with a custom ordering.
        For example, `sorted` will sort the nodes in increasing order.

    Yields
    ------
    edge: 2-tuple of nodes
       Yields edges resulting from the depth-first-search.

    Examples
    --------
    >>> G = nx.path_graph(5)
    >>> list(nx.dfs_edges(G, source=0))
    [(0, 1), (1, 2), (2, 3), (3, 4)]
    >>> list(nx.dfs_edges(G, source=0, depth_limit=2))
    [(0, 1), (1, 2)]

    Notes
    -----
    If a source is not specified then a source is chosen arbitrarily and
    repeatedly until all components in the graph are searched.

    The implementation of this function is adapted from David Eppstein's
    depth-first search function in PADS [1]_, with modifications
    to allow depth limits based on the Wikipedia article
    "Depth-limited search" [2]_.

    See Also
    --------
    dfs_preorder_nodes
    dfs_postorder_nodes
    dfs_labeled_edges
    :func:`~networkx.algorithms.traversal.edgedfs.edge_dfs`
    :func:`~networkx.algorithms.traversal.breadth_first_search.bfs_edges`

    References
    ----------
    .. [1] http://www.ics.uci.edu/~eppstein/PADS
    .. [2] https://en.wikipedia.org/wiki/Depth-limited_search
    """
    if source is None:
        # edges for all components
        nodes = G
    else:
        # edges for components with source
        nodes = [source]
    if depth_limit is None:
        depth_limit = len(G)

    get_children = (
        G.neighbors
        if sort_neighbors is None
        else lambda n: iter(sort_neighbors(G.neighbors(n)))
    )

    visited = set()
    for start in nodes:
        if start in visited:
            continue
        visited.add(start)
        stack = [(start, get_children(start))]
        depth_now = 1
        while stack:
            parent, children = stack[-1]
            for child in children:
                if child not in visited:
                    yield parent, child
                    visited.add(child)
                    if depth_now < depth_limit:
                        stack.append((child, get_children(child)))
                        depth_now += 1
                        break
            else:
                stack.pop()
                depth_now -= 1


@nx._dispatchable(returns_graph=True)
def dfs_tree(G, source=None, depth_limit=None, *, sort_neighbors=None):
    """Returns oriented tree constructed from a depth-first-search from source.

    Parameters
    ----------
    G : NetworkX graph

    source : node, optional
       Specify starting node for depth-first search.

    depth_limit : int, optional (default=len(G))
       Specify the maximum search depth.

    sort_neighbors : function (default=None)
        A function that takes an iterator over nodes as the input, and
        returns an iterable of the same nodes with a custom ordering.
        For example, `sorted` will sort the nodes in increasing order.

    Returns
    -------
    T : NetworkX DiGraph
       An oriented tree

    Examples
    --------
    >>> G = nx.path_graph(5)
    >>> T = nx.dfs_tree(G, source=0, depth_limit=2)
    >>> list(T.edges())
    [(0, 1), (1, 2)]
    >>> T = nx.dfs_tree(G, source=0)
    >>> list(T.edges())
    [(0, 1), (1, 2), (2, 3), (3, 4)]

    See Also
    --------
    dfs_preorder_nodes
    dfs_postorder_nodes
    dfs_labeled_edges
    :func:`~networkx.algorithms.traversal.edgedfs.edge_dfs`
    :func:`~networkx.algorithms.traversal.breadth_first_search.bfs_tree`
    """
    T = nx.DiGraph()
    if source is None:
        T.add_nodes_from(G)
    else:
        T.add_node(source)
    T.add_edges_from(dfs_edges(G, source, depth_limit, sort_neighbors=sort_neighbors))
    return T


@nx._dispatchable
def dfs_predecessors(G, source=None, depth_limit=None, *, sort_neighbors=None):
    """Returns dictionary of predecessors in depth-first-search from source.

    Parameters
    ----------
    G : NetworkX graph

    source : node, optional
       Specify starting node for depth-first search.
       Note that you will get predecessors for all nodes in the
       component containing `source`. This input only specifies
       where the DFS starts.

    depth_limit : int, optional (default=len(G))
       Specify the maximum search depth.

    sort_neighbors : function (default=None)
        A function that takes an iterator over nodes as the input, and
        returns an iterable of the same nodes with a custom ordering.
        For example, `sorted` will sort the nodes in increasing order.

    Returns
    -------
    pred: dict
       A dictionary with nodes as keys and predecessor nodes as values.

    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> nx.dfs_predecessors(G, source=0)
    {1: 0, 2: 1, 3: 2}
    >>> nx.dfs_predecessors(G, source=0, depth_limit=2)
    {1: 0, 2: 1}

    Notes
    -----
    If a source is not specified then a source is chosen arbitrarily and
    repeatedly until all components in the graph are searched.

    The implementation of this function is adapted from David Eppstein's
    depth-first search function in `PADS`_, with modifications
    to allow depth limits based on the Wikipedia article
    "`Depth-limited search`_".

    .. _PADS: http://www.ics.uci.edu/~eppstein/PADS
    .. _Depth-limited search: https://en.wikipedia.org/wiki/Depth-limited_search

    See Also
    --------
    dfs_preorder_nodes
    dfs_postorder_nodes
    dfs_labeled_edges
    :func:`~networkx.algorithms.traversal.edgedfs.edge_dfs`
    :func:`~networkx.algorithms.traversal.breadth_first_search.bfs_tree`
    """
    return {
        t: s
        for s, t in dfs_edges(G, source, depth_limit, sort_neighbors=sort_neighbors)
    }


@nx._dispatchable
def dfs_successors(G, source=None, depth_limit=None, *, sort_neighbors=None):
    """Returns dictionary of successors in depth-first-search from source.

    Parameters
    ----------
    G : NetworkX graph

    source : node, optional
       Specify starting node for depth-first search.
       Note that you will get successors for all nodes in the
       component containing `source`. This input only specifies
       where the DFS starts.

    depth_limit : int, optional (default=len(G))
       Specify the maximum search depth.

    sort_neighbors : function (default=None)
        A function that takes an iterator over nodes as the input, and
        returns an iterable of the same nodes with a custom ordering.
        For example, `sorted` will sort the nodes in increasing order.

    Returns
    -------
    succ: dict
       A dictionary with nodes as keys and list of successor nodes as values.

    Examples
    --------
    >>> G = nx.path_graph(5)
    >>> nx.dfs_successors(G, source=0)
    {0: [1], 1: [2], 2: [3], 3: [4]}
    >>> nx.dfs_successors(G, source=0, depth_limit=2)
    {0: [1], 1: [2]}

    Notes
    -----
    If a source is not specified then a source is chosen arbitrarily and
    repeatedly until all components in the graph are searched.

    The implementation of this function is adapted from David Eppstein's
    depth-first search function in `PADS`_, with modifications
    to allow depth limits based on the Wikipedia article
    "`Depth-limited search`_".

    .. _PADS: http://www.ics.uci.edu/~eppstein/PADS
    .. _Depth-limited search: https://en.wikipedia.org/wiki/Depth-limited_search

    See Also
    --------
    dfs_preorder_nodes
    dfs_postorder_nodes
    dfs_labeled_edges
    :func:`~networkx.algorithms.traversal.edgedfs.edge_dfs`
    :func:`~networkx.algorithms.traversal.breadth_first_search.bfs_tree`
    """
    d = defaultdict(list)
    for s, t in dfs_edges(
        G,
        source=source,
        depth_limit=depth_limit,
        sort_neighbors=sort_neighbors,
    ):
        d[s].append(t)
    return dict(d)


@nx._dispatchable
def dfs_postorder_nodes(G, source=None, depth_limit=None, *, sort_neighbors=None):
    """Generate nodes in a depth-first-search post-ordering starting at source.

    Parameters
    ----------
    G : NetworkX graph

    source : node, optional
       Specify starting node for depth-first search.

    depth_limit : int, optional (default=len(G))
       Specify the maximum search depth.

    sort_neighbors : function (default=None)
        A function that takes an iterator over nodes as the input, and
        returns an iterable of the same nodes with a custom ordering.
        For example, `sorted` will sort the nodes in increasing order.

    Returns
    -------
    nodes: generator
       A generator of nodes in a depth-first-search post-ordering.

    Examples
    --------
    >>> G = nx.path_graph(5)
    >>> list(nx.dfs_postorder_nodes(G, source=0))
    [4, 3, 2, 1, 0]
    >>> list(nx.dfs_postorder_nodes(G, source=0, depth_limit=2))
    [1, 0]

    Notes
    -----
    If a source is not specified then a source is chosen arbitrarily and
    repeatedly until all components in the graph are searched.

    The implementation of this function is adapted from David Eppstein's
    depth-first search function in `PADS`_, with modifications
    to allow depth limits based on the Wikipedia article
    "`Depth-limited search`_".

    .. _PADS: http://www.ics.uci.edu/~eppstein/PADS
    .. _Depth-limited search: https://en.wikipedia.org/wiki/Depth-limited_search

    See Also
    --------
    dfs_edges
    dfs_preorder_nodes
    dfs_labeled_edges
    :func:`~networkx.algorithms.traversal.edgedfs.edge_dfs`
    :func:`~networkx.algorithms.traversal.breadth_first_search.bfs_tree`
    """
    edges = nx.dfs_labeled_edges(
        G, source=source, depth_limit=depth_limit, sort_neighbors=sort_neighbors
    )
    return (v for u, v, d in edges if d == "reverse")


@nx._dispatchable
def dfs_preorder_nodes(G, source=None, depth_limit=None, *, sort_neighbors=None):
    """Generate nodes in a depth-first-search pre-ordering starting at source.

    Parameters
    ----------
    G : NetworkX graph

    source : node, optional
       Specify starting node for depth-first search and return nodes in
       the component reachable from source.

    depth_limit : int, optional (default=len(G))
       Specify the maximum search depth.

    sort_neighbors : function (default=None)
        A function that takes an iterator over nodes as the input, and
        returns an iterable of the same nodes with a custom ordering.
        For example, `sorted` will sort the nodes in increasing order.

    Returns
    -------
    nodes: generator
       A generator of nodes in a depth-first-search pre-ordering.

    Examples
    --------
    >>> G = nx.path_graph(5)
    >>> list(nx.dfs_preorder_nodes(G, source=0))
    [0, 1, 2, 3, 4]
    >>> list(nx.dfs_preorder_nodes(G, source=0, depth_limit=2))
    [0, 1, 2]

    Notes
    -----
    If a source is not specified then a source is chosen arbitrarily and
    repeatedly until all components in the graph are searched.

    The implementation of this function is adapted from David Eppstein's
    depth-first search function in `PADS`_, with modifications
    to allow depth limits based on the Wikipedia article
    "`Depth-limited search`_".

    .. _PADS: http://www.ics.uci.edu/~eppstein/PADS
    .. _Depth-limited search: https://en.wikipedia.org/wiki/Depth-limited_search

    See Also
    --------
    dfs_edges
    dfs_postorder_nodes
    dfs_labeled_edges
    :func:`~networkx.algorithms.traversal.breadth_first_search.bfs_edges`
    """
    edges = nx.dfs_labeled_edges(
        G, source=source, depth_limit=depth_limit, sort_neighbors=sort_neighbors
    )
    return (v for u, v, d in edges if d == "forward")


@nx._dispatchable
def dfs_labeled_edges(G, source=None, depth_limit=None, *, sort_neighbors=None):
    """Iterate over edges in a depth-first-search (DFS) labeled by type.

    Parameters
    ----------
    G : NetworkX graph

    source : node, optional
       Specify starting node for depth-first search and return edges in
       the component reachable from source.

    depth_limit : int, optional (default=len(G))
       Specify the maximum search depth.

    sort_neighbors : function (default=None)
        A function that takes an iterator over nodes as the input, and
        returns an iterable of the same nodes with a custom ordering.
        For example, `sorted` will sort the nodes in increasing order.

    Returns
    -------
    edges: generator
       A generator of triples of the form (*u*, *v*, *d*), where (*u*,
       *v*) is the edge being explored in the depth-first search and *d*
       is one of the strings 'forward', 'nontree', 'reverse', or 'reverse-depth_limit'.
       A 'forward' edge is one in which *u* has been visited but *v* has
       not. A 'nontree' edge is one in which both *u* and *v* have been
       visited but the edge is not in the DFS tree. A 'reverse' edge is
       one in which both *u* and *v* have been visited and the edge is in
       the DFS tree. When the `depth_limit` is reached via a 'forward' edge,
       a 'reverse' edge is immediately generated rather than the subtree
       being explored. To indicate this flavor of 'reverse' edge, the string
       yielded is 'reverse-depth_limit'.

    Examples
    --------

    The labels reveal the complete transcript of the depth-first search
    algorithm in more detail than, for example, :func:`dfs_edges`::

        >>> from pprint import pprint
        >>>
        >>> G = nx.DiGraph([(0, 1), (1, 2), (2, 1)])
        >>> pprint(list(nx.dfs_labeled_edges(G, source=0)))
        [(0, 0, 'forward'),
         (0, 1, 'forward'),
         (1, 2, 'forward'),
         (2, 1, 'nontree'),
         (1, 2, 'reverse'),
         (0, 1, 'reverse'),
         (0, 0, 'reverse')]

    Notes
    -----
    If a source is not specified then a source is chosen arbitrarily and
    repeatedly until all components in the graph are searched.

    The implementation of this function is adapted from David Eppstein's
    depth-first search function in `PADS`_, with modifications
    to allow depth limits based on the Wikipedia article
    "`Depth-limited search`_".

    .. _PADS: http://www.ics.uci.edu/~eppstein/PADS
    .. _Depth-limited search: https://en.wikipedia.org/wiki/Depth-limited_search

    See Also
    --------
    dfs_edges
    dfs_preorder_nodes
    dfs_postorder_nodes
    """
    # Based on http://www.ics.uci.edu/~eppstein/PADS/DFS.py
    # by D. Eppstein, July 2004.
    if source is None:
        # edges for all components
        nodes = G
    else:
        # edges for components with source
        nodes = [source]
    if depth_limit is None:
        depth_limit = len(G)

    get_children = (
        G.neighbors
        if sort_neighbors is None
        else lambda n: iter(sort_neighbors(G.neighbors(n)))
    )

    visited = set()
    for start in nodes:
        if start in visited:
            continue
        yield start, start, "forward"
        visited.add(start)
        stack = [(start, get_children(start))]
        depth_now = 1
        while stack:
            parent, children = stack[-1]
            for child in children:
                if child in visited:
                    yield parent, child, "nontree"
                else:
                    yield parent, child, "forward"
                    visited.add(child)
                    if depth_now < depth_limit:
                        stack.append((child, iter(get_children(child))))
                        depth_now += 1
                        break
                    else:
                        yield parent, child, "reverse-depth_limit"
            else:
                stack.pop()
                depth_now -= 1
                if stack:
                    yield stack[-1][0], parent, "reverse"
        yield start, start, "reverse"
