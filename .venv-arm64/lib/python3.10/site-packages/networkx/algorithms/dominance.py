"""
Dominance algorithms.
"""

from functools import reduce

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = ["immediate_dominators", "dominance_frontiers"]


@not_implemented_for("undirected")
@nx._dispatchable
def immediate_dominators(G, start):
    """Returns the immediate dominators of all nodes of a directed graph.

    Parameters
    ----------
    G : a DiGraph or MultiDiGraph
        The graph where dominance is to be computed.

    start : node
        The start node of dominance computation.

    Returns
    -------
    idom : dict keyed by nodes
        A dict containing the immediate dominators of each node reachable from
        `start`.

    Raises
    ------
    NetworkXNotImplemented
        If `G` is undirected.

    NetworkXError
        If `start` is not in `G`.

    Notes
    -----
    Except for `start`, the immediate dominators are the parents of their
    corresponding nodes in the dominator tree.

    Examples
    --------
    >>> G = nx.DiGraph([(1, 2), (1, 3), (2, 5), (3, 4), (4, 5)])
    >>> sorted(nx.immediate_dominators(G, 1).items())
    [(1, 1), (2, 1), (3, 1), (4, 3), (5, 1)]

    References
    ----------
    .. [1] Cooper, Keith D., Harvey, Timothy J. and Kennedy, Ken.
           "A simple, fast dominance algorithm." (2006).
           https://hdl.handle.net/1911/96345
    """
    if start not in G:
        raise nx.NetworkXError("start is not in G")

    idom = {start: start}

    order = list(nx.dfs_postorder_nodes(G, start))
    dfn = {u: i for i, u in enumerate(order)}
    order.pop()
    order.reverse()

    def intersect(u, v):
        while u != v:
            while dfn[u] < dfn[v]:
                u = idom[u]
            while dfn[u] > dfn[v]:
                v = idom[v]
        return u

    changed = True
    while changed:
        changed = False
        for u in order:
            new_idom = reduce(intersect, (v for v in G.pred[u] if v in idom))
            if u not in idom or idom[u] != new_idom:
                idom[u] = new_idom
                changed = True

    return idom


@nx._dispatchable
def dominance_frontiers(G, start):
    """Returns the dominance frontiers of all nodes of a directed graph.

    Parameters
    ----------
    G : a DiGraph or MultiDiGraph
        The graph where dominance is to be computed.

    start : node
        The start node of dominance computation.

    Returns
    -------
    df : dict keyed by nodes
        A dict containing the dominance frontiers of each node reachable from
        `start` as lists.

    Raises
    ------
    NetworkXNotImplemented
        If `G` is undirected.

    NetworkXError
        If `start` is not in `G`.

    Examples
    --------
    >>> G = nx.DiGraph([(1, 2), (1, 3), (2, 5), (3, 4), (4, 5)])
    >>> sorted((u, sorted(df)) for u, df in nx.dominance_frontiers(G, 1).items())
    [(1, []), (2, [5]), (3, [5]), (4, [5]), (5, [])]

    References
    ----------
    .. [1] Cooper, Keith D., Harvey, Timothy J. and Kennedy, Ken.
           "A simple, fast dominance algorithm." (2006).
           https://hdl.handle.net/1911/96345
    """
    idom = nx.immediate_dominators(G, start)

    df = {u: set() for u in idom}
    for u in idom:
        if len(G.pred[u]) >= 2:
            for v in G.pred[u]:
                if v in idom:
                    while v != idom[u]:
                        df[v].add(u)
                        v = idom[v]
    return df
