"""
==========================
Bipartite Graph Algorithms
==========================
"""

import networkx as nx
from networkx.algorithms.components import connected_components
from networkx.exception import AmbiguousSolution

__all__ = [
    "is_bipartite",
    "is_bipartite_node_set",
    "color",
    "sets",
    "density",
    "degrees",
]


@nx._dispatchable
def color(G):
    """Returns a two-coloring of the graph.

    Raises an exception if the graph is not bipartite.

    Parameters
    ----------
    G : NetworkX graph

    Returns
    -------
    color : dictionary
        A dictionary keyed by node with a 1 or 0 as data for each node color.

    Raises
    ------
    NetworkXError
        If the graph is not two-colorable.

    Examples
    --------
    >>> from networkx.algorithms import bipartite
    >>> G = nx.path_graph(4)
    >>> c = bipartite.color(G)
    >>> print(c)
    {0: 1, 1: 0, 2: 1, 3: 0}

    You can use this to set a node attribute indicating the bipartite set:

    >>> nx.set_node_attributes(G, c, "bipartite")
    >>> print(G.nodes[0]["bipartite"])
    1
    >>> print(G.nodes[1]["bipartite"])
    0
    """
    if G.is_directed():
        import itertools

        def neighbors(v):
            return itertools.chain.from_iterable([G.predecessors(v), G.successors(v)])

    else:
        neighbors = G.neighbors

    color = {}
    for n in G:  # handle disconnected graphs
        if n in color or len(G[n]) == 0:  # skip isolates
            continue
        queue = [n]
        color[n] = 1  # nodes seen with color (1 or 0)
        while queue:
            v = queue.pop()
            c = 1 - color[v]  # opposite color of node v
            for w in neighbors(v):
                if w in color:
                    if color[w] == color[v]:
                        raise nx.NetworkXError("Graph is not bipartite.")
                else:
                    color[w] = c
                    queue.append(w)
    # color isolates with 0
    color.update(dict.fromkeys(nx.isolates(G), 0))
    return color


@nx._dispatchable
def is_bipartite(G):
    """Returns True if graph G is bipartite, False if not.

    Parameters
    ----------
    G : NetworkX graph

    Examples
    --------
    >>> from networkx.algorithms import bipartite
    >>> G = nx.path_graph(4)
    >>> print(bipartite.is_bipartite(G))
    True

    See Also
    --------
    color, is_bipartite_node_set
    """
    try:
        color(G)
        return True
    except nx.NetworkXError:
        return False


@nx._dispatchable
def is_bipartite_node_set(G, nodes):
    """Returns True if nodes and G/nodes are a bipartition of G.

    Parameters
    ----------
    G : NetworkX graph

    nodes: list or container
      Check if nodes are a one of a bipartite set.

    Examples
    --------
    >>> from networkx.algorithms import bipartite
    >>> G = nx.path_graph(4)
    >>> X = set([1, 3])
    >>> bipartite.is_bipartite_node_set(G, X)
    True

    Notes
    -----
    An exception is raised if the input nodes are not distinct, because in this
    case some bipartite algorithms will yield incorrect results.
    For connected graphs the bipartite sets are unique.  This function handles
    disconnected graphs.
    """
    S = set(nodes)

    if len(S) < len(nodes):
        # this should maybe just return False?
        raise AmbiguousSolution(
            "The input node set contains duplicates.\n"
            "This may lead to incorrect results when using it in bipartite algorithms.\n"
            "Consider using set(nodes) as the input"
        )

    for CC in (G.subgraph(c).copy() for c in connected_components(G)):
        X, Y = sets(CC)
        if not (
            (X.issubset(S) and Y.isdisjoint(S)) or (Y.issubset(S) and X.isdisjoint(S))
        ):
            return False
    return True


@nx._dispatchable
def sets(G, top_nodes=None):
    """Returns bipartite node sets of graph G.

    Raises an exception if the graph is not bipartite or if the input
    graph is disconnected and thus more than one valid solution exists.
    See :mod:`bipartite documentation <networkx.algorithms.bipartite>`
    for further details on how bipartite graphs are handled in NetworkX.

    Parameters
    ----------
    G : NetworkX graph

    top_nodes : container, optional
      Container with all nodes in one bipartite node set. If not supplied
      it will be computed. But if more than one solution exists an exception
      will be raised.

    Returns
    -------
    X : set
      Nodes from one side of the bipartite graph.
    Y : set
      Nodes from the other side.

    Raises
    ------
    AmbiguousSolution
      Raised if the input bipartite graph is disconnected and no container
      with all nodes in one bipartite set is provided. When determining
      the nodes in each bipartite set more than one valid solution is
      possible if the input graph is disconnected.
    NetworkXError
      Raised if the input graph is not bipartite.

    Examples
    --------
    >>> from networkx.algorithms import bipartite
    >>> G = nx.path_graph(4)
    >>> X, Y = bipartite.sets(G)
    >>> list(X)
    [0, 2]
    >>> list(Y)
    [1, 3]

    See Also
    --------
    color

    """
    if G.is_directed():
        is_connected = nx.is_weakly_connected
    else:
        is_connected = nx.is_connected
    if top_nodes is not None:
        X = set(top_nodes)
        Y = set(G) - X
    else:
        if not is_connected(G):
            msg = "Disconnected graph: Ambiguous solution for bipartite sets."
            raise nx.AmbiguousSolution(msg)
        c = color(G)
        X = {n for n, is_top in c.items() if is_top}
        Y = {n for n, is_top in c.items() if not is_top}
    return (X, Y)


@nx._dispatchable(graphs="B")
def density(B, nodes):
    """Returns density of bipartite graph B.

    Parameters
    ----------
    B : NetworkX graph

    nodes: list or container
      Nodes in one node set of the bipartite graph.

    Returns
    -------
    d : float
       The bipartite density

    Examples
    --------
    >>> from networkx.algorithms import bipartite
    >>> G = nx.complete_bipartite_graph(3, 2)
    >>> X = set([0, 1, 2])
    >>> bipartite.density(G, X)
    1.0
    >>> Y = set([3, 4])
    >>> bipartite.density(G, Y)
    1.0

    Notes
    -----
    The container of nodes passed as argument must contain all nodes
    in one of the two bipartite node sets to avoid ambiguity in the
    case of disconnected graphs.
    See :mod:`bipartite documentation <networkx.algorithms.bipartite>`
    for further details on how bipartite graphs are handled in NetworkX.

    See Also
    --------
    color
    """
    n = len(B)
    m = nx.number_of_edges(B)
    nb = len(nodes)
    nt = n - nb
    if m == 0:  # includes cases n==0 and n==1
        d = 0.0
    else:
        if B.is_directed():
            d = m / (2 * nb * nt)
        else:
            d = m / (nb * nt)
    return d


@nx._dispatchable(graphs="B", edge_attrs="weight")
def degrees(B, nodes, weight=None):
    """Returns the degrees of the two node sets in the bipartite graph B.

    Parameters
    ----------
    B : NetworkX graph

    nodes: list or container
      Nodes in one node set of the bipartite graph.

    weight : string or None, optional (default=None)
       The edge attribute that holds the numerical value used as a weight.
       If None, then each edge has weight 1.
       The degree is the sum of the edge weights adjacent to the node.

    Returns
    -------
    (degX,degY) : tuple of dictionaries
       The degrees of the two bipartite sets as dictionaries keyed by node.

    Examples
    --------
    >>> from networkx.algorithms import bipartite
    >>> G = nx.complete_bipartite_graph(3, 2)
    >>> Y = set([3, 4])
    >>> degX, degY = bipartite.degrees(G, Y)
    >>> dict(degX)
    {0: 2, 1: 2, 2: 2}

    Notes
    -----
    The container of nodes passed as argument must contain all nodes
    in one of the two bipartite node sets to avoid ambiguity in the
    case of disconnected graphs.
    See :mod:`bipartite documentation <networkx.algorithms.bipartite>`
    for further details on how bipartite graphs are handled in NetworkX.

    See Also
    --------
    color, density
    """
    bottom = set(nodes)
    top = set(B) - bottom
    return (B.degree(top, weight), B.degree(bottom, weight))
