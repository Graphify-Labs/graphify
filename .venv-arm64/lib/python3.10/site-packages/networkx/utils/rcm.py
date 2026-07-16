"""
Cuthill-McKee ordering of graph nodes to produce sparse matrices
"""

from collections import deque
from operator import itemgetter

import networkx as nx

from ..utils import arbitrary_element

__all__ = ["cuthill_mckee_ordering", "reverse_cuthill_mckee_ordering"]


def cuthill_mckee_ordering(G, heuristic=None):
    """Generate an ordering (permutation) of the graph nodes to make
    a sparse matrix.

    Uses the Cuthill-McKee heuristic (based on breadth-first search) [1]_.

    Parameters
    ----------
    G : graph
      A NetworkX graph

    heuristic : function, optional
      Function to choose starting node for RCM algorithm.  If None
      a node from a pseudo-peripheral pair is used.  A user-defined function
      can be supplied that takes a graph object and returns a single node.

    Returns
    -------
    nodes : generator
       Generator of nodes in Cuthill-McKee ordering.

    Examples
    --------
    >>> from networkx.utils import cuthill_mckee_ordering
    >>> G = nx.path_graph(4)
    >>> rcm = list(cuthill_mckee_ordering(G))
    >>> A = nx.adjacency_matrix(G, nodelist=rcm)

    Smallest degree node as heuristic function:

    >>> def smallest_degree(G):
    ...     return min(G, key=G.degree)
    >>> rcm = list(cuthill_mckee_ordering(G, heuristic=smallest_degree))


    See Also
    --------
    reverse_cuthill_mckee_ordering

    Notes
    -----
    The optimal solution the bandwidth reduction is NP-complete [2]_.


    References
    ----------
    .. [1] E. Cuthill and J. McKee.
       Reducing the bandwidth of sparse symmetric matrices,
       In Proc. 24th Nat. Conf. ACM, pages 157-172, 1969.
       http://doi.acm.org/10.1145/800195.805928
    .. [2]  Steven S. Skiena. 1997. The Algorithm Design Manual.
       Springer-Verlag New York, Inc., New York, NY, USA.
    """
    for c in nx.connected_components(G):
        yield from connected_cuthill_mckee_ordering(G.subgraph(c), heuristic)


def reverse_cuthill_mckee_ordering(G, heuristic=None):
    """Generate an ordering (permutation) of the graph nodes to make
    a sparse matrix.

    Uses the reverse Cuthill-McKee heuristic (based on breadth-first search)
    [1]_.

    Parameters
    ----------
    G : graph
      A NetworkX graph

    heuristic : function, optional
      Function to choose starting node for RCM algorithm.  If None
      a node from a pseudo-peripheral pair is used.  A user-defined function
      can be supplied that takes a graph object and returns a single node.

    Returns
    -------
    nodes : generator
       Generator of nodes in reverse Cuthill-McKee ordering.

    Examples
    --------
    >>> from networkx.utils import reverse_cuthill_mckee_ordering
    >>> G = nx.path_graph(4)
    >>> rcm = list(reverse_cuthill_mckee_ordering(G))
    >>> A = nx.adjacency_matrix(G, nodelist=rcm)

    Smallest degree node as heuristic function:

    >>> def smallest_degree(G):
    ...     return min(G, key=G.degree)
    >>> rcm = list(reverse_cuthill_mckee_ordering(G, heuristic=smallest_degree))


    See Also
    --------
    cuthill_mckee_ordering

    Notes
    -----
    The optimal solution the bandwidth reduction is NP-complete [2]_.

    References
    ----------
    .. [1] E. Cuthill and J. McKee.
       Reducing the bandwidth of sparse symmetric matrices,
       In Proc. 24th Nat. Conf. ACM, pages 157-72, 1969.
       http://doi.acm.org/10.1145/800195.805928
    .. [2]  Steven S. Skiena. 1997. The Algorithm Design Manual.
       Springer-Verlag New York, Inc., New York, NY, USA.
    """
    return reversed(list(cuthill_mckee_ordering(G, heuristic=heuristic)))


def connected_cuthill_mckee_ordering(G, heuristic=None):
    # the cuthill mckee algorithm for connected graphs
    if heuristic is None:
        start = pseudo_peripheral_node(G)
    else:
        start = heuristic(G)
    visited = {start}
    queue = deque([start])
    while queue:
        parent = queue.popleft()
        yield parent
        nd = sorted(G.degree(set(G[parent]) - visited), key=itemgetter(1))
        children = [n for n, d in nd]
        visited.update(children)
        queue.extend(children)


def pseudo_peripheral_node(G):
    # helper for cuthill-mckee to find a node in a "pseudo peripheral pair"
    # to use as good starting node
    u = arbitrary_element(G)
    lp = 0
    v = u
    while True:
        spl = dict(nx.shortest_path_length(G, v))
        l = max(spl.values())
        if l <= lp:
            break
        lp = l
        farthest = (n for n, dist in spl.items() if dist == l)
        v, deg = min(G.degree(farthest), key=itemgetter(1))
    return v
