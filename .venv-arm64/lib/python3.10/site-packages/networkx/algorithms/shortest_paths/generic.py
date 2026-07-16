"""
Compute the shortest paths and path lengths between nodes in the graph.

These algorithms work with undirected and directed graphs.

"""

import warnings

import networkx as nx

__all__ = [
    "shortest_path",
    "all_shortest_paths",
    "single_source_all_shortest_paths",
    "all_pairs_all_shortest_paths",
    "shortest_path_length",
    "average_shortest_path_length",
    "has_path",
]


@nx._dispatchable
def has_path(G, source, target):
    """Returns *True* if *G* has a path from *source* to *target*.

    Parameters
    ----------
    G : NetworkX graph

    source : node
       Starting node for path

    target : node
       Ending node for path
    """
    try:
        nx.shortest_path(G, source, target)
    except nx.NetworkXNoPath:
        return False
    return True


@nx._dispatchable(edge_attrs="weight")
def shortest_path(G, source=None, target=None, weight=None, method="dijkstra"):
    """Compute shortest paths in the graph.

    Parameters
    ----------
    G : NetworkX graph

    source : node, optional
        Starting node for path. If not specified, compute shortest
        paths for each possible starting node.

    target : node, optional
        Ending node for path. If not specified, compute shortest
        paths to all possible nodes.

    weight : None, string or function, optional (default = None)
        If None, every edge has weight/distance/cost 1.
        If a string, use this edge attribute as the edge weight.
        Any edge attribute not present defaults to 1.
        If this is a function, the weight of an edge is the value
        returned by the function. The function must accept exactly
        three positional arguments: the two endpoints of an edge and
        the dictionary of edge attributes for that edge.
        The function must return a number.

    method : string, optional (default = 'dijkstra')
        The algorithm to use to compute the path.
        Supported options: 'dijkstra', 'bellman-ford'.
        Other inputs produce a ValueError.
        If `weight` is None, unweighted graph methods are used, and this
        suggestion is ignored.

    Returns
    -------
    path: list or dictionary
        All returned paths include both the source and target in the path.

        If the source and target are both specified, return a single list
        of nodes in a shortest path from the source to the target.

        If only the source is specified, return a dictionary keyed by
        targets with a list of nodes in a shortest path from the source
        to one of the targets.

        If only the target is specified, return a dictionary keyed by
        sources with a list of nodes in a shortest path from one of the
        sources to the target.

        If neither the source nor target are specified return a dictionary
        of dictionaries with path[source][target]=[list of nodes in path].

    Raises
    ------
    NodeNotFound
        If `source` is not in `G`.

    ValueError
        If `method` is not among the supported options.

    Examples
    --------
    >>> G = nx.path_graph(5)
    >>> print(nx.shortest_path(G, source=0, target=4))
    [0, 1, 2, 3, 4]
    >>> p = nx.shortest_path(G, source=0)  # target not specified
    >>> p[3]  # shortest path from source=0 to target=3
    [0, 1, 2, 3]
    >>> p = nx.shortest_path(G, target=4)  # source not specified
    >>> p[1]  # shortest path from source=1 to target=4
    [1, 2, 3, 4]
    >>> p = dict(nx.shortest_path(G))  # source, target not specified
    >>> p[2][4]  # shortest path from source=2 to target=4
    [2, 3, 4]

    Notes
    -----
    There may be more than one shortest path between a source and target.
    This returns only one of them.

    See Also
    --------
    all_pairs_shortest_path
    all_pairs_dijkstra_path
    all_pairs_bellman_ford_path
    single_source_shortest_path
    single_source_dijkstra_path
    single_source_bellman_ford_path
    """
    if method not in ("dijkstra", "bellman-ford"):
        # so we don't need to check in each branch later
        raise ValueError(f"method not supported: {method}")
    method = "unweighted" if weight is None else method
    if source is None:
        if target is None:
            warnings.warn(
                (
                    "\n\nshortest_path will return an iterator that yields\n"
                    "(node, path) pairs instead of a dictionary when source\n"
                    "and target are unspecified beginning in version 3.5\n\n"
                    "To keep the current behavior, use:\n\n"
                    "\tdict(nx.shortest_path(G))"
                ),
                FutureWarning,
                stacklevel=3,
            )

            # Find paths between all pairs.
            if method == "unweighted":
                paths = dict(nx.all_pairs_shortest_path(G))
            elif method == "dijkstra":
                paths = dict(nx.all_pairs_dijkstra_path(G, weight=weight))
            else:  # method == 'bellman-ford':
                paths = dict(nx.all_pairs_bellman_ford_path(G, weight=weight))
        else:
            # Find paths from all nodes co-accessible to the target.
            if G.is_directed():
                G = G.reverse(copy=False)
            if method == "unweighted":
                paths = nx.single_source_shortest_path(G, target)
            elif method == "dijkstra":
                paths = nx.single_source_dijkstra_path(G, target, weight=weight)
            else:  # method == 'bellman-ford':
                paths = nx.single_source_bellman_ford_path(G, target, weight=weight)
            # Now flip the paths so they go from a source to the target.
            for target in paths:
                paths[target] = list(reversed(paths[target]))
    else:
        if target is None:
            # Find paths to all nodes accessible from the source.
            if method == "unweighted":
                paths = nx.single_source_shortest_path(G, source)
            elif method == "dijkstra":
                paths = nx.single_source_dijkstra_path(G, source, weight=weight)
            else:  # method == 'bellman-ford':
                paths = nx.single_source_bellman_ford_path(G, source, weight=weight)
        else:
            # Find shortest source-target path.
            if method == "unweighted":
                paths = nx.bidirectional_shortest_path(G, source, target)
            elif method == "dijkstra":
                _, paths = nx.bidirectional_dijkstra(G, source, target, weight)
            else:  # method == 'bellman-ford':
                paths = nx.bellman_ford_path(G, source, target, weight)
    return paths


@nx._dispatchable(edge_attrs="weight")
def shortest_path_length(G, source=None, target=None, weight=None, method="dijkstra"):
    """Compute shortest path lengths in the graph.

    Parameters
    ----------
    G : NetworkX graph

    source : node, optional
        Starting node for path.
        If not specified, compute shortest path lengths using all nodes as
        source nodes.

    target : node, optional
        Ending node for path.
        If not specified, compute shortest path lengths using all nodes as
        target nodes.

    weight : None, string or function, optional (default = None)
        If None, every edge has weight/distance/cost 1.
        If a string, use this edge attribute as the edge weight.
        Any edge attribute not present defaults to 1.
        If this is a function, the weight of an edge is the value
        returned by the function. The function must accept exactly
        three positional arguments: the two endpoints of an edge and
        the dictionary of edge attributes for that edge.
        The function must return a number.

    method : string, optional (default = 'dijkstra')
        The algorithm to use to compute the path length.
        Supported options: 'dijkstra', 'bellman-ford'.
        Other inputs produce a ValueError.
        If `weight` is None, unweighted graph methods are used, and this
        suggestion is ignored.

    Returns
    -------
    length: number or iterator
        If the source and target are both specified, return the length of
        the shortest path from the source to the target.

        If only the source is specified, return a dict keyed by target
        to the shortest path length from the source to that target.

        If only the target is specified, return a dict keyed by source
        to the shortest path length from that source to the target.

        If neither the source nor target are specified, return an iterator
        over (source, dictionary) where dictionary is keyed by target to
        shortest path length from source to that target.

    Raises
    ------
    NodeNotFound
        If `source` is not in `G`.

    NetworkXNoPath
        If no path exists between source and target.

    ValueError
        If `method` is not among the supported options.

    Examples
    --------
    >>> G = nx.path_graph(5)
    >>> nx.shortest_path_length(G, source=0, target=4)
    4
    >>> p = nx.shortest_path_length(G, source=0)  # target not specified
    >>> p[4]
    4
    >>> p = nx.shortest_path_length(G, target=4)  # source not specified
    >>> p[0]
    4
    >>> p = dict(nx.shortest_path_length(G))  # source,target not specified
    >>> p[0][4]
    4

    Notes
    -----
    The length of the path is always 1 less than the number of nodes involved
    in the path since the length measures the number of edges followed.

    For digraphs this returns the shortest directed path length. To find path
    lengths in the reverse direction use G.reverse(copy=False) first to flip
    the edge orientation.

    See Also
    --------
    all_pairs_shortest_path_length
    all_pairs_dijkstra_path_length
    all_pairs_bellman_ford_path_length
    single_source_shortest_path_length
    single_source_dijkstra_path_length
    single_source_bellman_ford_path_length
    """
    if method not in ("dijkstra", "bellman-ford"):
        # so we don't need to check in each branch later
        raise ValueError(f"method not supported: {method}")
    method = "unweighted" if weight is None else method
    if source is None:
        if target is None:
            # Find paths between all pairs.
            if method == "unweighted":
                paths = nx.all_pairs_shortest_path_length(G)
            elif method == "dijkstra":
                paths = nx.all_pairs_dijkstra_path_length(G, weight=weight)
            else:  # method == 'bellman-ford':
                paths = nx.all_pairs_bellman_ford_path_length(G, weight=weight)
        else:
            # Find paths from all nodes co-accessible to the target.
            if G.is_directed():
                G = G.reverse(copy=False)
            if method == "unweighted":
                path_length = nx.single_source_shortest_path_length
                paths = path_length(G, target)
            elif method == "dijkstra":
                path_length = nx.single_source_dijkstra_path_length
                paths = path_length(G, target, weight=weight)
            else:  # method == 'bellman-ford':
                path_length = nx.single_source_bellman_ford_path_length
                paths = path_length(G, target, weight=weight)
    else:
        if target is None:
            # Find paths to all nodes accessible from the source.
            if method == "unweighted":
                paths = nx.single_source_shortest_path_length(G, source)
            elif method == "dijkstra":
                path_length = nx.single_source_dijkstra_path_length
                paths = path_length(G, source, weight=weight)
            else:  # method == 'bellman-ford':
                path_length = nx.single_source_bellman_ford_path_length
                paths = path_length(G, source, weight=weight)
        else:
            # Find shortest source-target path.
            if method == "unweighted":
                p = nx.bidirectional_shortest_path(G, source, target)
                paths = len(p) - 1
            elif method == "dijkstra":
                paths = nx.dijkstra_path_length(G, source, target, weight)
            else:  # method == 'bellman-ford':
                paths = nx.bellman_ford_path_length(G, source, target, weight)
    return paths


@nx._dispatchable(edge_attrs="weight")
def average_shortest_path_length(G, weight=None, method=None):
    r"""Returns the average shortest path length.

    The average shortest path length is

    .. math::

       a =\sum_{\substack{s,t \in V \\ s\neq t}} \frac{d(s, t)}{n(n-1)}

    where `V` is the set of nodes in `G`,
    `d(s, t)` is the shortest path from `s` to `t`,
    and `n` is the number of nodes in `G`.

    .. versionchanged:: 3.0
       An exception is raised for directed graphs that are not strongly
       connected.

    Parameters
    ----------
    G : NetworkX graph

    weight : None, string or function, optional (default = None)
        If None, every edge has weight/distance/cost 1.
        If a string, use this edge attribute as the edge weight.
        Any edge attribute not present defaults to 1.
        If this is a function, the weight of an edge is the value
        returned by the function. The function must accept exactly
        three positional arguments: the two endpoints of an edge and
        the dictionary of edge attributes for that edge.
        The function must return a number.

    method : string, optional (default = 'unweighted' or 'dijkstra')
        The algorithm to use to compute the path lengths.
        Supported options are 'unweighted', 'dijkstra', 'bellman-ford',
        'floyd-warshall' and 'floyd-warshall-numpy'.
        Other method values produce a ValueError.
        The default method is 'unweighted' if `weight` is None,
        otherwise the default method is 'dijkstra'.

    Raises
    ------
    NetworkXPointlessConcept
        If `G` is the null graph (that is, the graph on zero nodes).

    NetworkXError
        If `G` is not connected (or not strongly connected, in the case
        of a directed graph).

    ValueError
        If `method` is not among the supported options.

    Examples
    --------
    >>> G = nx.path_graph(5)
    >>> nx.average_shortest_path_length(G)
    2.0

    For disconnected graphs, you can compute the average shortest path
    length for each component

    >>> G = nx.Graph([(1, 2), (3, 4)])
    >>> for C in (G.subgraph(c).copy() for c in nx.connected_components(G)):
    ...     print(nx.average_shortest_path_length(C))
    1.0
    1.0

    """
    single_source_methods = ["unweighted", "dijkstra", "bellman-ford"]
    all_pairs_methods = ["floyd-warshall", "floyd-warshall-numpy"]
    supported_methods = single_source_methods + all_pairs_methods

    if method is None:
        method = "unweighted" if weight is None else "dijkstra"
    if method not in supported_methods:
        raise ValueError(f"method not supported: {method}")

    n = len(G)
    # For the special case of the null graph, raise an exception, since
    # there are no paths in the null graph.
    if n == 0:
        msg = (
            "the null graph has no paths, thus there is no average "
            "shortest path length"
        )
        raise nx.NetworkXPointlessConcept(msg)
    # For the special case of the trivial graph, return zero immediately.
    if n == 1:
        return 0
    # Shortest path length is undefined if the graph is not strongly connected.
    if G.is_directed() and not nx.is_strongly_connected(G):
        raise nx.NetworkXError("Graph is not strongly connected.")
    # Shortest path length is undefined if the graph is not connected.
    if not G.is_directed() and not nx.is_connected(G):
        raise nx.NetworkXError("Graph is not connected.")

    # Compute all-pairs shortest paths.
    def path_length(v):
        if method == "unweighted":
            return nx.single_source_shortest_path_length(G, v)
        elif method == "dijkstra":
            return nx.single_source_dijkstra_path_length(G, v, weight=weight)
        elif method == "bellman-ford":
            return nx.single_source_bellman_ford_path_length(G, v, weight=weight)

    if method in single_source_methods:
        # Sum the distances for each (ordered) pair of source and target node.
        s = sum(l for u in G for l in path_length(u).values())
    else:
        if method == "floyd-warshall":
            all_pairs = nx.floyd_warshall(G, weight=weight)
            s = sum(sum(t.values()) for t in all_pairs.values())
        elif method == "floyd-warshall-numpy":
            s = float(nx.floyd_warshall_numpy(G, weight=weight).sum())
    return s / (n * (n - 1))


@nx._dispatchable(edge_attrs="weight")
def all_shortest_paths(G, source, target, weight=None, method="dijkstra"):
    """Compute all shortest simple paths in the graph.

    Parameters
    ----------
    G : NetworkX graph

    source : node
       Starting node for path.

    target : node
       Ending node for path.

    weight : None, string or function, optional (default = None)
        If None, every edge has weight/distance/cost 1.
        If a string, use this edge attribute as the edge weight.
        Any edge attribute not present defaults to 1.
        If this is a function, the weight of an edge is the value
        returned by the function. The function must accept exactly
        three positional arguments: the two endpoints of an edge and
        the dictionary of edge attributes for that edge.
        The function must return a number.

    method : string, optional (default = 'dijkstra')
       The algorithm to use to compute the path lengths.
       Supported options: 'dijkstra', 'bellman-ford'.
       Other inputs produce a ValueError.
       If `weight` is None, unweighted graph methods are used, and this
       suggestion is ignored.

    Returns
    -------
    paths : generator of lists
        A generator of all paths between source and target.

    Raises
    ------
    ValueError
        If `method` is not among the supported options.

    NetworkXNoPath
        If `target` cannot be reached from `source`.

    Examples
    --------
    >>> G = nx.Graph()
    >>> nx.add_path(G, [0, 1, 2])
    >>> nx.add_path(G, [0, 10, 2])
    >>> print([p for p in nx.all_shortest_paths(G, source=0, target=2)])
    [[0, 1, 2], [0, 10, 2]]

    Notes
    -----
    There may be many shortest paths between the source and target.  If G
    contains zero-weight cycles, this function will not produce all shortest
    paths because doing so would produce infinitely many paths of unbounded
    length -- instead, we only produce the shortest simple paths.

    See Also
    --------
    shortest_path
    single_source_shortest_path
    all_pairs_shortest_path
    """
    method = "unweighted" if weight is None else method
    if method == "unweighted":
        pred = nx.predecessor(G, source)
    elif method == "dijkstra":
        pred, dist = nx.dijkstra_predecessor_and_distance(G, source, weight=weight)
    elif method == "bellman-ford":
        pred, dist = nx.bellman_ford_predecessor_and_distance(G, source, weight=weight)
    else:
        raise ValueError(f"method not supported: {method}")

    return _build_paths_from_predecessors({source}, target, pred)


@nx._dispatchable(edge_attrs="weight")
def single_source_all_shortest_paths(G, source, weight=None, method="dijkstra"):
    """Compute all shortest simple paths from the given source in the graph.

    Parameters
    ----------
    G : NetworkX graph

    source : node
       Starting node for path.

    weight : None, string or function, optional (default = None)
        If None, every edge has weight/distance/cost 1.
        If a string, use this edge attribute as the edge weight.
        Any edge attribute not present defaults to 1.
        If this is a function, the weight of an edge is the value
        returned by the function. The function must accept exactly
        three positional arguments: the two endpoints of an edge and
        the dictionary of edge attributes for that edge.
        The function must return a number.

    method : string, optional (default = 'dijkstra')
       The algorithm to use to compute the path lengths.
       Supported options: 'dijkstra', 'bellman-ford'.
       Other inputs produce a ValueError.
       If `weight` is None, unweighted graph methods are used, and this
       suggestion is ignored.

    Returns
    -------
    paths : generator of dictionary
        A generator of all paths between source and all nodes in the graph.

    Raises
    ------
    ValueError
        If `method` is not among the supported options.

    Examples
    --------
    >>> G = nx.Graph()
    >>> nx.add_path(G, [0, 1, 2, 3, 0])
    >>> dict(nx.single_source_all_shortest_paths(G, source=0))
    {0: [[0]], 1: [[0, 1]], 2: [[0, 1, 2], [0, 3, 2]], 3: [[0, 3]]}

    Notes
    -----
    There may be many shortest paths between the source and target.  If G
    contains zero-weight cycles, this function will not produce all shortest
    paths because doing so would produce infinitely many paths of unbounded
    length -- instead, we only produce the shortest simple paths.

    See Also
    --------
    shortest_path
    all_shortest_paths
    single_source_shortest_path
    all_pairs_shortest_path
    all_pairs_all_shortest_paths
    """
    method = "unweighted" if weight is None else method
    if method == "unweighted":
        pred = nx.predecessor(G, source)
    elif method == "dijkstra":
        pred, dist = nx.dijkstra_predecessor_and_distance(G, source, weight=weight)
    elif method == "bellman-ford":
        pred, dist = nx.bellman_ford_predecessor_and_distance(G, source, weight=weight)
    else:
        raise ValueError(f"method not supported: {method}")
    for n in G:
        try:
            yield n, list(_build_paths_from_predecessors({source}, n, pred))
        except nx.NetworkXNoPath:
            pass


@nx._dispatchable(edge_attrs="weight")
def all_pairs_all_shortest_paths(G, weight=None, method="dijkstra"):
    """Compute all shortest paths between all nodes.

    Parameters
    ----------
    G : NetworkX graph

    weight : None, string or function, optional (default = None)
        If None, every edge has weight/distance/cost 1.
        If a string, use this edge attribute as the edge weight.
        Any edge attribute not present defaults to 1.
        If this is a function, the weight of an edge is the value
        returned by the function. The function must accept exactly
        three positional arguments: the two endpoints of an edge and
        the dictionary of edge attributes for that edge.
        The function must return a number.

    method : string, optional (default = 'dijkstra')
       The algorithm to use to compute the path lengths.
       Supported options: 'dijkstra', 'bellman-ford'.
       Other inputs produce a ValueError.
       If `weight` is None, unweighted graph methods are used, and this
       suggestion is ignored.

    Returns
    -------
    paths : generator of dictionary
        Dictionary of arrays, keyed by source and target, of all shortest paths.

    Raises
    ------
    ValueError
        If `method` is not among the supported options.

    Examples
    --------
    >>> G = nx.cycle_graph(4)
    >>> dict(nx.all_pairs_all_shortest_paths(G))[0][2]
    [[0, 1, 2], [0, 3, 2]]
    >>> dict(nx.all_pairs_all_shortest_paths(G))[0][3]
    [[0, 3]]

    Notes
    -----
    There may be multiple shortest paths with equal lengths. Unlike
    all_pairs_shortest_path, this method returns all shortest paths.

    See Also
    --------
    all_pairs_shortest_path
    single_source_all_shortest_paths
    """
    for n in G:
        yield (
            n,
            dict(single_source_all_shortest_paths(G, n, weight=weight, method=method)),
        )


def _build_paths_from_predecessors(sources, target, pred):
    """Compute all simple paths to target, given the predecessors found in
    pred, terminating when any source in sources is found.

    Parameters
    ----------
    sources : set
       Starting nodes for path.

    target : node
       Ending node for path.

    pred : dict
       A dictionary of predecessor lists, keyed by node

    Returns
    -------
    paths : generator of lists
        A generator of all paths between source and target.

    Raises
    ------
    NetworkXNoPath
        If `target` cannot be reached from `source`.

    Notes
    -----
    There may be many paths between the sources and target.  If there are
    cycles among the predecessors, this function will not produce all
    possible paths because doing so would produce infinitely many paths
    of unbounded length -- instead, we only produce simple paths.

    See Also
    --------
    shortest_path
    single_source_shortest_path
    all_pairs_shortest_path
    all_shortest_paths
    bellman_ford_path
    """
    if target not in pred:
        raise nx.NetworkXNoPath(f"Target {target} cannot be reached from given sources")

    seen = {target}
    stack = [[target, 0]]
    top = 0
    while top >= 0:
        node, i = stack[top]
        if node in sources:
            yield [p for p, n in reversed(stack[: top + 1])]
        if len(pred[node]) > i:
            stack[top][1] = i + 1
            next = pred[node][i]
            if next in seen:
                continue
            else:
                seen.add(next)
            top += 1
            if top == len(stack):
                stack.append([next, 0])
            else:
                stack[top][:] = [next, 0]
        else:
            seen.discard(node)
            top -= 1
