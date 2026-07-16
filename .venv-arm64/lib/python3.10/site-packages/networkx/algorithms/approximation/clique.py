"""Functions for computing large cliques and maximum independent sets."""

import networkx as nx
from networkx.algorithms.approximation import ramsey
from networkx.utils import not_implemented_for

__all__ = [
    "clique_removal",
    "max_clique",
    "large_clique_size",
    "maximum_independent_set",
]


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def maximum_independent_set(G):
    """Returns an approximate maximum independent set.

    Independent set or stable set is a set of vertices in a graph, no two of
    which are adjacent. That is, it is a set I of vertices such that for every
    two vertices in I, there is no edge connecting the two. Equivalently, each
    edge in the graph has at most one endpoint in I. The size of an independent
    set is the number of vertices it contains [1]_.

    A maximum independent set is a largest independent set for a given graph G
    and its size is denoted $\\alpha(G)$. The problem of finding such a set is called
    the maximum independent set problem and is an NP-hard optimization problem.
    As such, it is unlikely that there exists an efficient algorithm for finding
    a maximum independent set of a graph.

    The Independent Set algorithm is based on [2]_.

    Parameters
    ----------
    G : NetworkX graph
        Undirected graph

    Returns
    -------
    iset : Set
        The apx-maximum independent set

    Examples
    --------
    >>> G = nx.path_graph(10)
    >>> nx.approximation.maximum_independent_set(G)
    {0, 2, 4, 6, 9}

    Raises
    ------
    NetworkXNotImplemented
        If the graph is directed or is a multigraph.

    Notes
    -----
    Finds the $O(|V|/(log|V|)^2)$ apx of independent set in the worst case.

    References
    ----------
    .. [1] `Wikipedia: Independent set
        <https://en.wikipedia.org/wiki/Independent_set_(graph_theory)>`_
    .. [2] Boppana, R., & Halldórsson, M. M. (1992).
       Approximating maximum independent sets by excluding subgraphs.
       BIT Numerical Mathematics, 32(2), 180–196. Springer.
    """
    iset, _ = clique_removal(G)
    return iset


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def max_clique(G):
    r"""Find the Maximum Clique

    Finds the $O(|V|/(log|V|)^2)$ apx of maximum clique/independent set
    in the worst case.

    Parameters
    ----------
    G : NetworkX graph
        Undirected graph

    Returns
    -------
    clique : set
        The apx-maximum clique of the graph

    Examples
    --------
    >>> G = nx.path_graph(10)
    >>> nx.approximation.max_clique(G)
    {8, 9}

    Raises
    ------
    NetworkXNotImplemented
        If the graph is directed or is a multigraph.

    Notes
    -----
    A clique in an undirected graph G = (V, E) is a subset of the vertex set
    `C \subseteq V` such that for every two vertices in C there exists an edge
    connecting the two. This is equivalent to saying that the subgraph
    induced by C is complete (in some cases, the term clique may also refer
    to the subgraph).

    A maximum clique is a clique of the largest possible size in a given graph.
    The clique number `\omega(G)` of a graph G is the number of
    vertices in a maximum clique in G. The intersection number of
    G is the smallest number of cliques that together cover all edges of G.

    https://en.wikipedia.org/wiki/Maximum_clique

    References
    ----------
    .. [1] Boppana, R., & Halldórsson, M. M. (1992).
        Approximating maximum independent sets by excluding subgraphs.
        BIT Numerical Mathematics, 32(2), 180–196. Springer.
        doi:10.1007/BF01994876
    """
    # finding the maximum clique in a graph is equivalent to finding
    # the independent set in the complementary graph
    cgraph = nx.complement(G)
    iset, _ = clique_removal(cgraph)
    return iset


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def clique_removal(G):
    r"""Repeatedly remove cliques from the graph.

    Results in a $O(|V|/(\log |V|)^2)$ approximation of maximum clique
    and independent set. Returns the largest independent set found, along
    with found maximal cliques.

    Parameters
    ----------
    G : NetworkX graph
        Undirected graph

    Returns
    -------
    max_ind_cliques : (set, list) tuple
        2-tuple of Maximal Independent Set and list of maximal cliques (sets).

    Examples
    --------
    >>> G = nx.path_graph(10)
    >>> nx.approximation.clique_removal(G)
    ({0, 2, 4, 6, 9}, [{0, 1}, {2, 3}, {4, 5}, {6, 7}, {8, 9}])

    Raises
    ------
    NetworkXNotImplemented
        If the graph is directed or is a multigraph.

    References
    ----------
    .. [1] Boppana, R., & Halldórsson, M. M. (1992).
        Approximating maximum independent sets by excluding subgraphs.
        BIT Numerical Mathematics, 32(2), 180–196. Springer.
    """
    graph = G.copy()
    c_i, i_i = ramsey.ramsey_R2(graph)
    cliques = [c_i]
    isets = [i_i]
    while graph:
        graph.remove_nodes_from(c_i)
        c_i, i_i = ramsey.ramsey_R2(graph)
        if c_i:
            cliques.append(c_i)
        if i_i:
            isets.append(i_i)
    # Determine the largest independent set as measured by cardinality.
    maxiset = max(isets, key=len)
    return maxiset, cliques


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def large_clique_size(G):
    """Find the size of a large clique in a graph.

    A *clique* is a subset of nodes in which each pair of nodes is
    adjacent. This function is a heuristic for finding the size of a
    large clique in the graph.

    Parameters
    ----------
    G : NetworkX graph

    Returns
    -------
    k: integer
       The size of a large clique in the graph.

    Examples
    --------
    >>> G = nx.path_graph(10)
    >>> nx.approximation.large_clique_size(G)
    2

    Raises
    ------
    NetworkXNotImplemented
        If the graph is directed or is a multigraph.

    Notes
    -----
    This implementation is from [1]_. Its worst case time complexity is
    :math:`O(n d^2)`, where *n* is the number of nodes in the graph and
    *d* is the maximum degree.

    This function is a heuristic, which means it may work well in
    practice, but there is no rigorous mathematical guarantee on the
    ratio between the returned number and the actual largest clique size
    in the graph.

    References
    ----------
    .. [1] Pattabiraman, Bharath, et al.
       "Fast Algorithms for the Maximum Clique Problem on Massive Graphs
       with Applications to Overlapping Community Detection."
       *Internet Mathematics* 11.4-5 (2015): 421--448.
       <https://doi.org/10.1080/15427951.2014.986778>

    See also
    --------

    :func:`networkx.algorithms.approximation.clique.max_clique`
        A function that returns an approximate maximum clique with a
        guarantee on the approximation ratio.

    :mod:`networkx.algorithms.clique`
        Functions for finding the exact maximum clique in a graph.

    """
    degrees = G.degree

    def _clique_heuristic(G, U, size, best_size):
        if not U:
            return max(best_size, size)
        u = max(U, key=degrees)
        U.remove(u)
        N_prime = {v for v in G[u] if degrees[v] >= best_size}
        return _clique_heuristic(G, U & N_prime, size + 1, best_size)

    best_size = 0
    nodes = (u for u in G if degrees[u] >= best_size)
    for u in nodes:
        neighbors = {v for v in G[u] if degrees[v] >= best_size}
        best_size = _clique_heuristic(G, neighbors, 1, best_size)
    return best_size
