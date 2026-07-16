"""
Algorithms for chordal graphs.

A graph is chordal if every cycle of length at least 4 has a chord
(an edge joining two nodes not adjacent in the cycle).
https://en.wikipedia.org/wiki/Chordal_graph
"""

import sys

import networkx as nx
from networkx.algorithms.components import connected_components
from networkx.utils import arbitrary_element, not_implemented_for

__all__ = [
    "is_chordal",
    "find_induced_nodes",
    "chordal_graph_cliques",
    "chordal_graph_treewidth",
    "NetworkXTreewidthBoundExceeded",
    "complete_to_chordal_graph",
]


class NetworkXTreewidthBoundExceeded(nx.NetworkXException):
    """Exception raised when a treewidth bound has been provided and it has
    been exceeded"""


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def is_chordal(G):
    """Checks whether G is a chordal graph.

    A graph is chordal if every cycle of length at least 4 has a chord
    (an edge joining two nodes not adjacent in the cycle).

    Parameters
    ----------
    G : graph
      A NetworkX graph.

    Returns
    -------
    chordal : bool
      True if G is a chordal graph and False otherwise.

    Raises
    ------
    NetworkXNotImplemented
        The algorithm does not support DiGraph, MultiGraph and MultiDiGraph.

    Examples
    --------
    >>> e = [
    ...     (1, 2),
    ...     (1, 3),
    ...     (2, 3),
    ...     (2, 4),
    ...     (3, 4),
    ...     (3, 5),
    ...     (3, 6),
    ...     (4, 5),
    ...     (4, 6),
    ...     (5, 6),
    ... ]
    >>> G = nx.Graph(e)
    >>> nx.is_chordal(G)
    True

    Notes
    -----
    The routine tries to go through every node following maximum cardinality
    search. It returns False when it finds that the separator for any node
    is not a clique.  Based on the algorithms in [1]_.

    Self loops are ignored.

    References
    ----------
    .. [1] R. E. Tarjan and M. Yannakakis, Simple linear-time algorithms
       to test chordality of graphs, test acyclicity of hypergraphs, and
       selectively reduce acyclic hypergraphs, SIAM J. Comput., 13 (1984),
       pp. 566–579.
    """
    if len(G.nodes) <= 3:
        return True
    return len(_find_chordality_breaker(G)) == 0


@nx._dispatchable
def find_induced_nodes(G, s, t, treewidth_bound=sys.maxsize):
    """Returns the set of induced nodes in the path from s to t.

    Parameters
    ----------
    G : graph
      A chordal NetworkX graph
    s : node
        Source node to look for induced nodes
    t : node
        Destination node to look for induced nodes
    treewidth_bound: float
        Maximum treewidth acceptable for the graph H. The search
        for induced nodes will end as soon as the treewidth_bound is exceeded.

    Returns
    -------
    induced_nodes : Set of nodes
        The set of induced nodes in the path from s to t in G

    Raises
    ------
    NetworkXError
        The algorithm does not support DiGraph, MultiGraph and MultiDiGraph.
        If the input graph is an instance of one of these classes, a
        :exc:`NetworkXError` is raised.
        The algorithm can only be applied to chordal graphs. If the input
        graph is found to be non-chordal, a :exc:`NetworkXError` is raised.

    Examples
    --------
    >>> G = nx.Graph()
    >>> G = nx.generators.classic.path_graph(10)
    >>> induced_nodes = nx.find_induced_nodes(G, 1, 9, 2)
    >>> sorted(induced_nodes)
    [1, 2, 3, 4, 5, 6, 7, 8, 9]

    Notes
    -----
    G must be a chordal graph and (s,t) an edge that is not in G.

    If a treewidth_bound is provided, the search for induced nodes will end
    as soon as the treewidth_bound is exceeded.

    The algorithm is inspired by Algorithm 4 in [1]_.
    A formal definition of induced node can also be found on that reference.

    Self Loops are ignored

    References
    ----------
    .. [1] Learning Bounded Treewidth Bayesian Networks.
       Gal Elidan, Stephen Gould; JMLR, 9(Dec):2699--2731, 2008.
       http://jmlr.csail.mit.edu/papers/volume9/elidan08a/elidan08a.pdf
    """
    if not is_chordal(G):
        raise nx.NetworkXError("Input graph is not chordal.")

    H = nx.Graph(G)
    H.add_edge(s, t)
    induced_nodes = set()
    triplet = _find_chordality_breaker(H, s, treewidth_bound)
    while triplet:
        (u, v, w) = triplet
        induced_nodes.update(triplet)
        for n in triplet:
            if n != s:
                H.add_edge(s, n)
        triplet = _find_chordality_breaker(H, s, treewidth_bound)
    if induced_nodes:
        # Add t and the second node in the induced path from s to t.
        induced_nodes.add(t)
        for u in G[s]:
            if len(induced_nodes & set(G[u])) == 2:
                induced_nodes.add(u)
                break
    return induced_nodes


@nx._dispatchable
def chordal_graph_cliques(G):
    """Returns all maximal cliques of a chordal graph.

    The algorithm breaks the graph in connected components and performs a
    maximum cardinality search in each component to get the cliques.

    Parameters
    ----------
    G : graph
      A NetworkX graph

    Yields
    ------
    frozenset of nodes
        Maximal cliques, each of which is a frozenset of
        nodes in `G`. The order of cliques is arbitrary.

    Raises
    ------
    NetworkXError
        The algorithm does not support DiGraph, MultiGraph and MultiDiGraph.
        The algorithm can only be applied to chordal graphs. If the input
        graph is found to be non-chordal, a :exc:`NetworkXError` is raised.

    Examples
    --------
    >>> e = [
    ...     (1, 2),
    ...     (1, 3),
    ...     (2, 3),
    ...     (2, 4),
    ...     (3, 4),
    ...     (3, 5),
    ...     (3, 6),
    ...     (4, 5),
    ...     (4, 6),
    ...     (5, 6),
    ...     (7, 8),
    ... ]
    >>> G = nx.Graph(e)
    >>> G.add_node(9)
    >>> cliques = [c for c in chordal_graph_cliques(G)]
    >>> cliques[0]
    frozenset({1, 2, 3})
    """
    for C in (G.subgraph(c).copy() for c in connected_components(G)):
        if C.number_of_nodes() == 1:
            if nx.number_of_selfloops(C) > 0:
                raise nx.NetworkXError("Input graph is not chordal.")
            yield frozenset(C.nodes())
        else:
            unnumbered = set(C.nodes())
            v = arbitrary_element(C)
            unnumbered.remove(v)
            numbered = {v}
            clique_wanna_be = {v}
            while unnumbered:
                v = _max_cardinality_node(C, unnumbered, numbered)
                unnumbered.remove(v)
                numbered.add(v)
                new_clique_wanna_be = set(C.neighbors(v)) & numbered
                sg = C.subgraph(clique_wanna_be)
                if _is_complete_graph(sg):
                    new_clique_wanna_be.add(v)
                    if not new_clique_wanna_be >= clique_wanna_be:
                        yield frozenset(clique_wanna_be)
                    clique_wanna_be = new_clique_wanna_be
                else:
                    raise nx.NetworkXError("Input graph is not chordal.")
            yield frozenset(clique_wanna_be)


@nx._dispatchable
def chordal_graph_treewidth(G):
    """Returns the treewidth of the chordal graph G.

    Parameters
    ----------
    G : graph
      A NetworkX graph

    Returns
    -------
    treewidth : int
        The size of the largest clique in the graph minus one.

    Raises
    ------
    NetworkXError
        The algorithm does not support DiGraph, MultiGraph and MultiDiGraph.
        The algorithm can only be applied to chordal graphs. If the input
        graph is found to be non-chordal, a :exc:`NetworkXError` is raised.

    Examples
    --------
    >>> e = [
    ...     (1, 2),
    ...     (1, 3),
    ...     (2, 3),
    ...     (2, 4),
    ...     (3, 4),
    ...     (3, 5),
    ...     (3, 6),
    ...     (4, 5),
    ...     (4, 6),
    ...     (5, 6),
    ...     (7, 8),
    ... ]
    >>> G = nx.Graph(e)
    >>> G.add_node(9)
    >>> nx.chordal_graph_treewidth(G)
    3

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/Tree_decomposition#Treewidth
    """
    if not is_chordal(G):
        raise nx.NetworkXError("Input graph is not chordal.")

    max_clique = -1
    for clique in nx.chordal_graph_cliques(G):
        max_clique = max(max_clique, len(clique))
    return max_clique - 1


def _is_complete_graph(G):
    """Returns True if G is a complete graph."""
    if nx.number_of_selfloops(G) > 0:
        raise nx.NetworkXError("Self loop found in _is_complete_graph()")
    n = G.number_of_nodes()
    if n < 2:
        return True
    e = G.number_of_edges()
    max_edges = (n * (n - 1)) / 2
    return e == max_edges


def _find_missing_edge(G):
    """Given a non-complete graph G, returns a missing edge."""
    nodes = set(G)
    for u in G:
        missing = nodes - set(list(G[u].keys()) + [u])
        if missing:
            return (u, missing.pop())


def _max_cardinality_node(G, choices, wanna_connect):
    """Returns a the node in choices that has more connections in G
    to nodes in wanna_connect.
    """
    max_number = -1
    for x in choices:
        number = len([y for y in G[x] if y in wanna_connect])
        if number > max_number:
            max_number = number
            max_cardinality_node = x
    return max_cardinality_node


def _find_chordality_breaker(G, s=None, treewidth_bound=sys.maxsize):
    """Given a graph G, starts a max cardinality search
    (starting from s if s is given and from an arbitrary node otherwise)
    trying to find a non-chordal cycle.

    If it does find one, it returns (u,v,w) where u,v,w are the three
    nodes that together with s are involved in the cycle.

    It ignores any self loops.
    """
    if len(G) == 0:
        raise nx.NetworkXPointlessConcept("Graph has no nodes.")
    unnumbered = set(G)
    if s is None:
        s = arbitrary_element(G)
    unnumbered.remove(s)
    numbered = {s}
    current_treewidth = -1
    while unnumbered:  # and current_treewidth <= treewidth_bound:
        v = _max_cardinality_node(G, unnumbered, numbered)
        unnumbered.remove(v)
        numbered.add(v)
        clique_wanna_be = set(G[v]) & numbered
        sg = G.subgraph(clique_wanna_be)
        if _is_complete_graph(sg):
            # The graph seems to be chordal by now. We update the treewidth
            current_treewidth = max(current_treewidth, len(clique_wanna_be))
            if current_treewidth > treewidth_bound:
                raise nx.NetworkXTreewidthBoundExceeded(
                    f"treewidth_bound exceeded: {current_treewidth}"
                )
        else:
            # sg is not a clique,
            # look for an edge that is not included in sg
            (u, w) = _find_missing_edge(sg)
            return (u, v, w)
    return ()


@not_implemented_for("directed")
@nx._dispatchable(returns_graph=True)
def complete_to_chordal_graph(G):
    """Return a copy of G completed to a chordal graph

    Adds edges to a copy of G to create a chordal graph. A graph G=(V,E) is
    called chordal if for each cycle with length bigger than 3, there exist
    two non-adjacent nodes connected by an edge (called a chord).

    Parameters
    ----------
    G : NetworkX graph
        Undirected graph

    Returns
    -------
    H : NetworkX graph
        The chordal enhancement of G
    alpha : Dictionary
            The elimination ordering of nodes of G

    Notes
    -----
    There are different approaches to calculate the chordal
    enhancement of a graph. The algorithm used here is called
    MCS-M and gives at least minimal (local) triangulation of graph. Note
    that this triangulation is not necessarily a global minimum.

    https://en.wikipedia.org/wiki/Chordal_graph

    References
    ----------
    .. [1] Berry, Anne & Blair, Jean & Heggernes, Pinar & Peyton, Barry. (2004)
           Maximum Cardinality Search for Computing Minimal Triangulations of
           Graphs.  Algorithmica. 39. 287-298. 10.1007/s00453-004-1084-3.

    Examples
    --------
    >>> from networkx.algorithms.chordal import complete_to_chordal_graph
    >>> G = nx.wheel_graph(10)
    >>> H, alpha = complete_to_chordal_graph(G)
    """
    H = G.copy()
    alpha = {node: 0 for node in H}
    if nx.is_chordal(H):
        return H, alpha
    chords = set()
    weight = {node: 0 for node in H.nodes()}
    unnumbered_nodes = list(H.nodes())
    for i in range(len(H.nodes()), 0, -1):
        # get the node in unnumbered_nodes with the maximum weight
        z = max(unnumbered_nodes, key=lambda node: weight[node])
        unnumbered_nodes.remove(z)
        alpha[z] = i
        update_nodes = []
        for y in unnumbered_nodes:
            if G.has_edge(y, z):
                update_nodes.append(y)
            else:
                # y_weight will be bigger than node weights between y and z
                y_weight = weight[y]
                lower_nodes = [
                    node for node in unnumbered_nodes if weight[node] < y_weight
                ]
                if nx.has_path(H.subgraph(lower_nodes + [z, y]), y, z):
                    update_nodes.append(y)
                    chords.add((z, y))
        # during calculation of paths the weights should not be updated
        for node in update_nodes:
            weight[node] += 1
    H.add_edges_from(chords)
    return H, alpha
