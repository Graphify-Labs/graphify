"""Connected components."""

import networkx as nx
from networkx.utils.decorators import not_implemented_for

from ...utils import arbitrary_element

__all__ = [
    "number_connected_components",
    "connected_components",
    "is_connected",
    "node_connected_component",
]


@not_implemented_for("directed")
@nx._dispatchable
def connected_components(G):
    """Generate connected components.

    Parameters
    ----------
    G : NetworkX graph
       An undirected graph

    Returns
    -------
    comp : generator of sets
       A generator of sets of nodes, one for each component of G.

    Raises
    ------
    NetworkXNotImplemented
        If G is directed.

    Examples
    --------
    Generate a sorted list of connected components, largest first.

    >>> G = nx.path_graph(4)
    >>> nx.add_path(G, [10, 11, 12])
    >>> [len(c) for c in sorted(nx.connected_components(G), key=len, reverse=True)]
    [4, 3]

    If you only want the largest connected component, it's more
    efficient to use max instead of sort.

    >>> largest_cc = max(nx.connected_components(G), key=len)

    To create the induced subgraph of each component use:

    >>> S = [G.subgraph(c).copy() for c in nx.connected_components(G)]

    See Also
    --------
    strongly_connected_components
    weakly_connected_components

    Notes
    -----
    For undirected graphs only.

    """
    seen = set()
    n = len(G)
    for v in G:
        if v not in seen:
            c = _plain_bfs(G, n, v)
            seen.update(c)
            yield c


@not_implemented_for("directed")
@nx._dispatchable
def number_connected_components(G):
    """Returns the number of connected components.

    Parameters
    ----------
    G : NetworkX graph
       An undirected graph.

    Returns
    -------
    n : integer
       Number of connected components

    Raises
    ------
    NetworkXNotImplemented
        If G is directed.

    Examples
    --------
    >>> G = nx.Graph([(0, 1), (1, 2), (5, 6), (3, 4)])
    >>> nx.number_connected_components(G)
    3

    See Also
    --------
    connected_components
    number_weakly_connected_components
    number_strongly_connected_components

    Notes
    -----
    For undirected graphs only.

    """
    return sum(1 for cc in connected_components(G))


@not_implemented_for("directed")
@nx._dispatchable
def is_connected(G):
    """Returns True if the graph is connected, False otherwise.

    Parameters
    ----------
    G : NetworkX Graph
       An undirected graph.

    Returns
    -------
    connected : bool
      True if the graph is connected, false otherwise.

    Raises
    ------
    NetworkXNotImplemented
        If G is directed.

    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> print(nx.is_connected(G))
    True

    See Also
    --------
    is_strongly_connected
    is_weakly_connected
    is_semiconnected
    is_biconnected
    connected_components

    Notes
    -----
    For undirected graphs only.

    """
    n = len(G)
    if n == 0:
        raise nx.NetworkXPointlessConcept(
            "Connectivity is undefined for the null graph."
        )
    return sum(1 for node in _plain_bfs(G, n, arbitrary_element(G))) == len(G)


@not_implemented_for("directed")
@nx._dispatchable
def node_connected_component(G, n):
    """Returns the set of nodes in the component of graph containing node n.

    Parameters
    ----------
    G : NetworkX Graph
       An undirected graph.

    n : node label
       A node in G

    Returns
    -------
    comp : set
       A set of nodes in the component of G containing node n.

    Raises
    ------
    NetworkXNotImplemented
        If G is directed.

    Examples
    --------
    >>> G = nx.Graph([(0, 1), (1, 2), (5, 6), (3, 4)])
    >>> nx.node_connected_component(G, 0)  # nodes of component that contains node 0
    {0, 1, 2}

    See Also
    --------
    connected_components

    Notes
    -----
    For undirected graphs only.

    """
    return _plain_bfs(G, len(G), n)


def _plain_bfs(G, n, source):
    """A fast BFS node generator"""
    adj = G._adj
    seen = {source}
    nextlevel = [source]
    while nextlevel:
        thislevel = nextlevel
        nextlevel = []
        for v in thislevel:
            for w in adj[v]:
                if w not in seen:
                    seen.add(w)
                    nextlevel.append(w)
            if len(seen) == n:
                return seen
    return seen
