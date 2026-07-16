"""
Shortest path algorithms for unweighted graphs.
"""

import warnings

import networkx as nx

__all__ = [
    "bidirectional_shortest_path",
    "single_source_shortest_path",
    "single_source_shortest_path_length",
    "single_target_shortest_path",
    "single_target_shortest_path_length",
    "all_pairs_shortest_path",
    "all_pairs_shortest_path_length",
    "predecessor",
]


@nx._dispatchable
def single_source_shortest_path_length(G, source, cutoff=None):
    """Compute the shortest path lengths from source to all reachable nodes.

    Parameters
    ----------
    G : NetworkX graph

    source : node
       Starting node for path

    cutoff : integer, optional
        Depth to stop the search. Only paths of length <= cutoff are returned.

    Returns
    -------
    lengths : dict
        Dict keyed by node to shortest path length to source.

    Examples
    --------
    >>> G = nx.path_graph(5)
    >>> length = nx.single_source_shortest_path_length(G, 0)
    >>> length[4]
    4
    >>> for node in length:
    ...     print(f"{node}: {length[node]}")
    0: 0
    1: 1
    2: 2
    3: 3
    4: 4

    See Also
    --------
    shortest_path_length
    """
    if source not in G:
        raise nx.NodeNotFound(f"Source {source} is not in G")
    if cutoff is None:
        cutoff = float("inf")
    nextlevel = [source]
    return dict(_single_shortest_path_length(G._adj, nextlevel, cutoff))


def _single_shortest_path_length(adj, firstlevel, cutoff):
    """Yields (node, level) in a breadth first search

    Shortest Path Length helper function
    Parameters
    ----------
        adj : dict
            Adjacency dict or view
        firstlevel : list
            starting nodes, e.g. [source] or [target]
        cutoff : int or float
            level at which we stop the process
    """
    seen = set(firstlevel)
    nextlevel = firstlevel
    level = 0
    n = len(adj)
    for v in nextlevel:
        yield (v, level)
    while nextlevel and cutoff > level:
        level += 1
        thislevel = nextlevel
        nextlevel = []
        for v in thislevel:
            for w in adj[v]:
                if w not in seen:
                    seen.add(w)
                    nextlevel.append(w)
                    yield (w, level)
            if len(seen) == n:
                return


@nx._dispatchable
def single_target_shortest_path_length(G, target, cutoff=None):
    """Compute the shortest path lengths to target from all reachable nodes.

    Parameters
    ----------
    G : NetworkX graph

    target : node
       Target node for path

    cutoff : integer, optional
        Depth to stop the search. Only paths of length <= cutoff are returned.

    Returns
    -------
    lengths : iterator
        (source, shortest path length) iterator

    Examples
    --------
    >>> G = nx.path_graph(5, create_using=nx.DiGraph())
    >>> length = dict(nx.single_target_shortest_path_length(G, 4))
    >>> length[0]
    4
    >>> for node in range(5):
    ...     print(f"{node}: {length[node]}")
    0: 4
    1: 3
    2: 2
    3: 1
    4: 0

    See Also
    --------
    single_source_shortest_path_length, shortest_path_length
    """
    if target not in G:
        raise nx.NodeNotFound(f"Target {target} is not in G")

    warnings.warn(
        (
            "\n\nsingle_target_shortest_path_length will return a dict instead of"
            "\nan iterator in version 3.5"
        ),
        FutureWarning,
        stacklevel=3,
    )

    if cutoff is None:
        cutoff = float("inf")
    # handle either directed or undirected
    adj = G._pred if G.is_directed() else G._adj
    nextlevel = [target]
    # for version 3.3 we will return a dict like this:
    # return dict(_single_shortest_path_length(adj, nextlevel, cutoff))
    return _single_shortest_path_length(adj, nextlevel, cutoff)


@nx._dispatchable
def all_pairs_shortest_path_length(G, cutoff=None):
    """Computes the shortest path lengths between all nodes in `G`.

    Parameters
    ----------
    G : NetworkX graph

    cutoff : integer, optional
        Depth at which to stop the search. Only paths of length at most
        `cutoff` are returned.

    Returns
    -------
    lengths : iterator
        (source, dictionary) iterator with dictionary keyed by target and
        shortest path length as the key value.

    Notes
    -----
    The iterator returned only has reachable node pairs.

    Examples
    --------
    >>> G = nx.path_graph(5)
    >>> length = dict(nx.all_pairs_shortest_path_length(G))
    >>> for node in [0, 1, 2, 3, 4]:
    ...     print(f"1 - {node}: {length[1][node]}")
    1 - 0: 1
    1 - 1: 0
    1 - 2: 1
    1 - 3: 2
    1 - 4: 3
    >>> length[3][2]
    1
    >>> length[2][2]
    0

    """
    length = single_source_shortest_path_length
    # TODO This can be trivially parallelized.
    for n in G:
        yield (n, length(G, n, cutoff=cutoff))


@nx._dispatchable
def bidirectional_shortest_path(G, source, target):
    """Returns a list of nodes in a shortest path between source and target.

    Parameters
    ----------
    G : NetworkX graph

    source : node label
       starting node for path

    target : node label
       ending node for path

    Returns
    -------
    path: list
       List of nodes in a path from source to target.

    Raises
    ------
    NetworkXNoPath
       If no path exists between source and target.

    Examples
    --------
    >>> G = nx.Graph()
    >>> nx.add_path(G, [0, 1, 2, 3, 0, 4, 5, 6, 7, 4])
    >>> nx.bidirectional_shortest_path(G, 2, 6)
    [2, 1, 0, 4, 5, 6]

    See Also
    --------
    shortest_path

    Notes
    -----
    This algorithm is used by shortest_path(G, source, target).
    """

    if source not in G:
        raise nx.NodeNotFound(f"Source {source} is not in G")

    if target not in G:
        raise nx.NodeNotFound(f"Target {target} is not in G")

    # call helper to do the real work
    results = _bidirectional_pred_succ(G, source, target)
    pred, succ, w = results

    # build path from pred+w+succ
    path = []
    # from source to w
    while w is not None:
        path.append(w)
        w = pred[w]
    path.reverse()
    # from w to target
    w = succ[path[-1]]
    while w is not None:
        path.append(w)
        w = succ[w]

    return path


def _bidirectional_pred_succ(G, source, target):
    """Bidirectional shortest path helper.

    Returns (pred, succ, w) where
    pred is a dictionary of predecessors from w to the source, and
    succ is a dictionary of successors from w to the target.
    """
    # does BFS from both source and target and meets in the middle
    if target == source:
        return ({target: None}, {source: None}, source)

    # handle either directed or undirected
    if G.is_directed():
        Gpred = G.pred
        Gsucc = G.succ
    else:
        Gpred = G.adj
        Gsucc = G.adj

    # predecessor and successors in search
    pred = {source: None}
    succ = {target: None}

    # initialize fringes, start with forward
    forward_fringe = [source]
    reverse_fringe = [target]

    while forward_fringe and reverse_fringe:
        if len(forward_fringe) <= len(reverse_fringe):
            this_level = forward_fringe
            forward_fringe = []
            for v in this_level:
                for w in Gsucc[v]:
                    if w not in pred:
                        forward_fringe.append(w)
                        pred[w] = v
                    if w in succ:  # path found
                        return pred, succ, w
        else:
            this_level = reverse_fringe
            reverse_fringe = []
            for v in this_level:
                for w in Gpred[v]:
                    if w not in succ:
                        succ[w] = v
                        reverse_fringe.append(w)
                    if w in pred:  # found path
                        return pred, succ, w

    raise nx.NetworkXNoPath(f"No path between {source} and {target}.")


@nx._dispatchable
def single_source_shortest_path(G, source, cutoff=None):
    """Compute shortest path between source
    and all other nodes reachable from source.

    Parameters
    ----------
    G : NetworkX graph

    source : node label
       Starting node for path

    cutoff : integer, optional
        Depth to stop the search. Only paths of length <= cutoff are returned.

    Returns
    -------
    paths : dictionary
        Dictionary, keyed by target, of shortest paths.

    Examples
    --------
    >>> G = nx.path_graph(5)
    >>> path = nx.single_source_shortest_path(G, 0)
    >>> path[4]
    [0, 1, 2, 3, 4]

    Notes
    -----
    The shortest path is not necessarily unique. So there can be multiple
    paths between the source and each target node, all of which have the
    same 'shortest' length. For each target node, this function returns
    only one of those paths.

    See Also
    --------
    shortest_path
    """
    if source not in G:
        raise nx.NodeNotFound(f"Source {source} not in G")

    def join(p1, p2):
        return p1 + p2

    if cutoff is None:
        cutoff = float("inf")
    nextlevel = {source: 1}  # list of nodes to check at next level
    paths = {source: [source]}  # paths dictionary  (paths to key from source)
    return dict(_single_shortest_path(G.adj, nextlevel, paths, cutoff, join))


def _single_shortest_path(adj, firstlevel, paths, cutoff, join):
    """Returns shortest paths

    Shortest Path helper function
    Parameters
    ----------
        adj : dict
            Adjacency dict or view
        firstlevel : dict
            starting nodes, e.g. {source: 1} or {target: 1}
        paths : dict
            paths for starting nodes, e.g. {source: [source]}
        cutoff : int or float
            level at which we stop the process
        join : function
            function to construct a path from two partial paths. Requires two
            list inputs `p1` and `p2`, and returns a list. Usually returns
            `p1 + p2` (forward from source) or `p2 + p1` (backward from target)
    """
    level = 0  # the current level
    nextlevel = firstlevel
    while nextlevel and cutoff > level:
        thislevel = nextlevel
        nextlevel = {}
        for v in thislevel:
            for w in adj[v]:
                if w not in paths:
                    paths[w] = join(paths[v], [w])
                    nextlevel[w] = 1
        level += 1
    return paths


@nx._dispatchable
def single_target_shortest_path(G, target, cutoff=None):
    """Compute shortest path to target from all nodes that reach target.

    Parameters
    ----------
    G : NetworkX graph

    target : node label
       Target node for path

    cutoff : integer, optional
        Depth to stop the search. Only paths of length <= cutoff are returned.

    Returns
    -------
    paths : dictionary
        Dictionary, keyed by target, of shortest paths.

    Examples
    --------
    >>> G = nx.path_graph(5, create_using=nx.DiGraph())
    >>> path = nx.single_target_shortest_path(G, 4)
    >>> path[0]
    [0, 1, 2, 3, 4]

    Notes
    -----
    The shortest path is not necessarily unique. So there can be multiple
    paths between the source and each target node, all of which have the
    same 'shortest' length. For each target node, this function returns
    only one of those paths.

    See Also
    --------
    shortest_path, single_source_shortest_path
    """
    if target not in G:
        raise nx.NodeNotFound(f"Target {target} not in G")

    def join(p1, p2):
        return p2 + p1

    # handle undirected graphs
    adj = G.pred if G.is_directed() else G.adj
    if cutoff is None:
        cutoff = float("inf")
    nextlevel = {target: 1}  # list of nodes to check at next level
    paths = {target: [target]}  # paths dictionary  (paths to key from source)
    return dict(_single_shortest_path(adj, nextlevel, paths, cutoff, join))


@nx._dispatchable
def all_pairs_shortest_path(G, cutoff=None):
    """Compute shortest paths between all nodes.

    Parameters
    ----------
    G : NetworkX graph

    cutoff : integer, optional
        Depth at which to stop the search. Only paths of length at most
        `cutoff` are returned.

    Returns
    -------
    paths : iterator
        Dictionary, keyed by source and target, of shortest paths.

    Examples
    --------
    >>> G = nx.path_graph(5)
    >>> path = dict(nx.all_pairs_shortest_path(G))
    >>> print(path[0][4])
    [0, 1, 2, 3, 4]

    Notes
    -----
    There may be multiple shortest paths with the same length between
    two nodes. For each pair, this function returns only one of those paths.

    See Also
    --------
    floyd_warshall
    all_pairs_all_shortest_paths

    """
    # TODO This can be trivially parallelized.
    for n in G:
        yield (n, single_source_shortest_path(G, n, cutoff=cutoff))


@nx._dispatchable
def predecessor(G, source, target=None, cutoff=None, return_seen=None):
    """Returns dict of predecessors for the path from source to all nodes in G.

    Parameters
    ----------
    G : NetworkX graph

    source : node label
       Starting node for path

    target : node label, optional
       Ending node for path. If provided only predecessors between
       source and target are returned

    cutoff : integer, optional
        Depth to stop the search. Only paths of length <= cutoff are returned.

    return_seen : bool, optional (default=None)
        Whether to return a dictionary, keyed by node, of the level (number of
        hops) to reach the node (as seen during breadth-first-search).

    Returns
    -------
    pred : dictionary
        Dictionary, keyed by node, of predecessors in the shortest path.


    (pred, seen): tuple of dictionaries
        If `return_seen` argument is set to `True`, then a tuple of dictionaries
        is returned. The first element is the dictionary, keyed by node, of
        predecessors in the shortest path. The second element is the dictionary,
        keyed by node, of the level (number of hops) to reach the node (as seen
        during breadth-first-search).

    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> list(G)
    [0, 1, 2, 3]
    >>> nx.predecessor(G, 0)
    {0: [], 1: [0], 2: [1], 3: [2]}
    >>> nx.predecessor(G, 0, return_seen=True)
    ({0: [], 1: [0], 2: [1], 3: [2]}, {0: 0, 1: 1, 2: 2, 3: 3})


    """
    if source not in G:
        raise nx.NodeNotFound(f"Source {source} not in G")

    level = 0  # the current level
    nextlevel = [source]  # list of nodes to check at next level
    seen = {source: level}  # level (number of hops) when seen in BFS
    pred = {source: []}  # predecessor dictionary
    while nextlevel:
        level = level + 1
        thislevel = nextlevel
        nextlevel = []
        for v in thislevel:
            for w in G[v]:
                if w not in seen:
                    pred[w] = [v]
                    seen[w] = level
                    nextlevel.append(w)
                elif seen[w] == level:  # add v to predecessor list if it
                    pred[w].append(v)  # is at the correct level
        if cutoff and cutoff <= level:
            break

    if target is not None:
        if return_seen:
            if target not in pred:
                return ([], -1)  # No predecessor
            return (pred[target], seen[target])
        else:
            if target not in pred:
                return []  # No predecessor
            return pred[target]
    else:
        if return_seen:
            return (pred, seen)
        else:
            return pred
