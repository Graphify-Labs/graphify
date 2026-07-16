"""Provides functions for computing the efficiency of nodes and graphs."""

import networkx as nx
from networkx.exception import NetworkXNoPath

from ..utils import not_implemented_for

__all__ = ["efficiency", "local_efficiency", "global_efficiency"]


@not_implemented_for("directed")
@nx._dispatchable
def efficiency(G, u, v):
    """Returns the efficiency of a pair of nodes in a graph.

    The *efficiency* of a pair of nodes is the multiplicative inverse of the
    shortest path distance between the nodes [1]_. Returns 0 if no path
    between nodes.

    Parameters
    ----------
    G : :class:`networkx.Graph`
        An undirected graph for which to compute the average local efficiency.
    u, v : node
        Nodes in the graph ``G``.

    Returns
    -------
    float
        Multiplicative inverse of the shortest path distance between the nodes.

    Examples
    --------
    >>> G = nx.Graph([(0, 1), (0, 2), (0, 3), (1, 2), (1, 3)])
    >>> nx.efficiency(G, 2, 3)  # this gives efficiency for node 2 and 3
    0.5

    Notes
    -----
    Edge weights are ignored when computing the shortest path distances.

    See also
    --------
    local_efficiency
    global_efficiency

    References
    ----------
    .. [1] Latora, Vito, and Massimo Marchiori.
           "Efficient behavior of small-world networks."
           *Physical Review Letters* 87.19 (2001): 198701.
           <https://doi.org/10.1103/PhysRevLett.87.198701>

    """
    try:
        eff = 1 / nx.shortest_path_length(G, u, v)
    except NetworkXNoPath:
        eff = 0
    return eff


@not_implemented_for("directed")
@nx._dispatchable
def global_efficiency(G):
    """Returns the average global efficiency of the graph.

    The *efficiency* of a pair of nodes in a graph is the multiplicative
    inverse of the shortest path distance between the nodes. The *average
    global efficiency* of a graph is the average efficiency of all pairs of
    nodes [1]_.

    Parameters
    ----------
    G : :class:`networkx.Graph`
        An undirected graph for which to compute the average global efficiency.

    Returns
    -------
    float
        The average global efficiency of the graph.

    Examples
    --------
    >>> G = nx.Graph([(0, 1), (0, 2), (0, 3), (1, 2), (1, 3)])
    >>> round(nx.global_efficiency(G), 12)
    0.916666666667

    Notes
    -----
    Edge weights are ignored when computing the shortest path distances.

    See also
    --------
    local_efficiency

    References
    ----------
    .. [1] Latora, Vito, and Massimo Marchiori.
           "Efficient behavior of small-world networks."
           *Physical Review Letters* 87.19 (2001): 198701.
           <https://doi.org/10.1103/PhysRevLett.87.198701>

    """
    n = len(G)
    denom = n * (n - 1)
    if denom != 0:
        lengths = nx.all_pairs_shortest_path_length(G)
        g_eff = 0
        for source, targets in lengths:
            for target, distance in targets.items():
                if distance > 0:
                    g_eff += 1 / distance
        g_eff /= denom
        # g_eff = sum(1 / d for s, tgts in lengths
        #                   for t, d in tgts.items() if d > 0) / denom
    else:
        g_eff = 0
    # TODO This can be made more efficient by computing all pairs shortest
    # path lengths in parallel.
    return g_eff


@not_implemented_for("directed")
@nx._dispatchable
def local_efficiency(G):
    """Returns the average local efficiency of the graph.

    The *efficiency* of a pair of nodes in a graph is the multiplicative
    inverse of the shortest path distance between the nodes. The *local
    efficiency* of a node in the graph is the average global efficiency of the
    subgraph induced by the neighbors of the node. The *average local
    efficiency* is the average of the local efficiencies of each node [1]_.

    Parameters
    ----------
    G : :class:`networkx.Graph`
        An undirected graph for which to compute the average local efficiency.

    Returns
    -------
    float
        The average local efficiency of the graph.

    Examples
    --------
    >>> G = nx.Graph([(0, 1), (0, 2), (0, 3), (1, 2), (1, 3)])
    >>> nx.local_efficiency(G)
    0.9166666666666667

    Notes
    -----
    Edge weights are ignored when computing the shortest path distances.

    See also
    --------
    global_efficiency

    References
    ----------
    .. [1] Latora, Vito, and Massimo Marchiori.
           "Efficient behavior of small-world networks."
           *Physical Review Letters* 87.19 (2001): 198701.
           <https://doi.org/10.1103/PhysRevLett.87.198701>

    """
    efficiency_list = (global_efficiency(G.subgraph(G[v])) for v in G)
    return sum(efficiency_list) / len(G)
