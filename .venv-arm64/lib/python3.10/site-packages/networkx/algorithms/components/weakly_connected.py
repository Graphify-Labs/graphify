"""Weakly connected components."""

import networkx as nx
from networkx.utils.decorators import not_implemented_for

__all__ = [
    "number_weakly_connected_components",
    "weakly_connected_components",
    "is_weakly_connected",
]


@not_implemented_for("undirected")
@nx._dispatchable
def weakly_connected_components(G):
    """Generate weakly connected components of G.

    Parameters
    ----------
    G : NetworkX graph
        A directed graph

    Returns
    -------
    comp : generator of sets
        A generator of sets of nodes, one for each weakly connected
        component of G.

    Raises
    ------
    NetworkXNotImplemented
        If G is undirected.

    Examples
    --------
    Generate a sorted list of weakly connected components, largest first.

    >>> G = nx.path_graph(4, create_using=nx.DiGraph())
    >>> nx.add_path(G, [10, 11, 12])
    >>> [
    ...     len(c)
    ...     for c in sorted(nx.weakly_connected_components(G), key=len, reverse=True)
    ... ]
    [4, 3]

    If you only want the largest component, it's more efficient to
    use max instead of sort:

    >>> largest_cc = max(nx.weakly_connected_components(G), key=len)

    See Also
    --------
    connected_components
    strongly_connected_components

    Notes
    -----
    For directed graphs only.

    """
    seen = set()
    n = len(G)  # must be outside the loop to avoid performance hit with graph views
    for v in G:
        if v not in seen:
            c = set(_plain_bfs(G, n, v))
            seen.update(c)
            yield c


@not_implemented_for("undirected")
@nx._dispatchable
def number_weakly_connected_components(G):
    """Returns the number of weakly connected components in G.

    Parameters
    ----------
    G : NetworkX graph
        A directed graph.

    Returns
    -------
    n : integer
        Number of weakly connected components

    Raises
    ------
    NetworkXNotImplemented
        If G is undirected.

    Examples
    --------
    >>> G = nx.DiGraph([(0, 1), (2, 1), (3, 4)])
    >>> nx.number_weakly_connected_components(G)
    2

    See Also
    --------
    weakly_connected_components
    number_connected_components
    number_strongly_connected_components

    Notes
    -----
    For directed graphs only.

    """
    return sum(1 for wcc in weakly_connected_components(G))


@not_implemented_for("undirected")
@nx._dispatchable
def is_weakly_connected(G):
    """Test directed graph for weak connectivity.

    A directed graph is weakly connected if and only if the graph
    is connected when the direction of the edge between nodes is ignored.

    Note that if a graph is strongly connected (i.e. the graph is connected
    even when we account for directionality), it is by definition weakly
    connected as well.

    Parameters
    ----------
    G : NetworkX Graph
        A directed graph.

    Returns
    -------
    connected : bool
        True if the graph is weakly connected, False otherwise.

    Raises
    ------
    NetworkXNotImplemented
        If G is undirected.

    Examples
    --------
    >>> G = nx.DiGraph([(0, 1), (2, 1)])
    >>> G.add_node(3)
    >>> nx.is_weakly_connected(G)  # node 3 is not connected to the graph
    False
    >>> G.add_edge(2, 3)
    >>> nx.is_weakly_connected(G)
    True

    See Also
    --------
    is_strongly_connected
    is_semiconnected
    is_connected
    is_biconnected
    weakly_connected_components

    Notes
    -----
    For directed graphs only.

    """
    if len(G) == 0:
        raise nx.NetworkXPointlessConcept(
            """Connectivity is undefined for the null graph."""
        )

    return len(next(weakly_connected_components(G))) == len(G)


def _plain_bfs(G, n, source):
    """A fast BFS node generator

    The direction of the edge between nodes is ignored.

    For directed graphs only.

    """
    Gsucc = G._succ
    Gpred = G._pred
    seen = {source}
    nextlevel = [source]

    yield source
    while nextlevel:
        thislevel = nextlevel
        nextlevel = []
        for v in thislevel:
            for w in Gsucc[v]:
                if w not in seen:
                    seen.add(w)
                    nextlevel.append(w)
                    yield w
            for w in Gpred[v]:
                if w not in seen:
                    seen.add(w)
                    nextlevel.append(w)
                    yield w
            if len(seen) == n:
                return
