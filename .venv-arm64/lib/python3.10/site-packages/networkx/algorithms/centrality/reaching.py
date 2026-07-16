"""Functions for computing reaching centrality of a node or a graph."""

import networkx as nx
from networkx.utils import pairwise

__all__ = ["global_reaching_centrality", "local_reaching_centrality"]


def _average_weight(G, path, weight=None):
    """Returns the average weight of an edge in a weighted path.

    Parameters
    ----------
    G : graph
      A networkx graph.

    path: list
      A list of vertices that define the path.

    weight : None or string, optional (default=None)
      If None, edge weights are ignored.  Then the average weight of an edge
      is assumed to be the multiplicative inverse of the length of the path.
      Otherwise holds the name of the edge attribute used as weight.
    """
    path_length = len(path) - 1
    if path_length <= 0:
        return 0
    if weight is None:
        return 1 / path_length
    total_weight = sum(G.edges[i, j][weight] for i, j in pairwise(path))
    return total_weight / path_length


@nx._dispatchable(edge_attrs="weight")
def global_reaching_centrality(G, weight=None, normalized=True):
    """Returns the global reaching centrality of a directed graph.

    The *global reaching centrality* of a weighted directed graph is the
    average over all nodes of the difference between the local reaching
    centrality of the node and the greatest local reaching centrality of
    any node in the graph [1]_. For more information on the local
    reaching centrality, see :func:`local_reaching_centrality`.
    Informally, the local reaching centrality is the proportion of the
    graph that is reachable from the neighbors of the node.

    Parameters
    ----------
    G : DiGraph
        A networkx DiGraph.

    weight : None or string, optional (default=None)
        Attribute to use for edge weights. If ``None``, each edge weight
        is assumed to be one. A higher weight implies a stronger
        connection between nodes and a *shorter* path length.

    normalized : bool, optional (default=True)
        Whether to normalize the edge weights by the total sum of edge
        weights.

    Returns
    -------
    h : float
        The global reaching centrality of the graph.

    Examples
    --------
    >>> G = nx.DiGraph()
    >>> G.add_edge(1, 2)
    >>> G.add_edge(1, 3)
    >>> nx.global_reaching_centrality(G)
    1.0
    >>> G.add_edge(3, 2)
    >>> nx.global_reaching_centrality(G)
    0.75

    See also
    --------
    local_reaching_centrality

    References
    ----------
    .. [1] Mones, Enys, Lilla Vicsek, and Tamás Vicsek.
           "Hierarchy Measure for Complex Networks."
           *PLoS ONE* 7.3 (2012): e33799.
           https://doi.org/10.1371/journal.pone.0033799
    """
    if nx.is_negatively_weighted(G, weight=weight):
        raise nx.NetworkXError("edge weights must be positive")
    total_weight = G.size(weight=weight)
    if total_weight <= 0:
        raise nx.NetworkXError("Size of G must be positive")
    # If provided, weights must be interpreted as connection strength
    # (so higher weights are more likely to be chosen). However, the
    # shortest path algorithms in NetworkX assume the provided "weight"
    # is actually a distance (so edges with higher weight are less
    # likely to be chosen). Therefore we need to invert the weights when
    # computing shortest paths.
    #
    # If weight is None, we leave it as-is so that the shortest path
    # algorithm can use a faster, unweighted algorithm.
    if weight is not None:

        def as_distance(u, v, d):
            return total_weight / d.get(weight, 1)

        shortest_paths = nx.shortest_path(G, weight=as_distance)
    else:
        shortest_paths = nx.shortest_path(G)

    centrality = local_reaching_centrality
    # TODO This can be trivially parallelized.
    lrc = [
        centrality(G, node, paths=paths, weight=weight, normalized=normalized)
        for node, paths in shortest_paths.items()
    ]

    max_lrc = max(lrc)
    return sum(max_lrc - c for c in lrc) / (len(G) - 1)


@nx._dispatchable(edge_attrs="weight")
def local_reaching_centrality(G, v, paths=None, weight=None, normalized=True):
    """Returns the local reaching centrality of a node in a directed
    graph.

    The *local reaching centrality* of a node in a directed graph is the
    proportion of other nodes reachable from that node [1]_.

    Parameters
    ----------
    G : DiGraph
        A NetworkX DiGraph.

    v : node
        A node in the directed graph `G`.

    paths : dictionary (default=None)
        If this is not `None` it must be a dictionary representation
        of single-source shortest paths, as computed by, for example,
        :func:`networkx.shortest_path` with source node `v`. Use this
        keyword argument if you intend to invoke this function many
        times but don't want the paths to be recomputed each time.

    weight : None or string, optional (default=None)
        Attribute to use for edge weights.  If `None`, each edge weight
        is assumed to be one. A higher weight implies a stronger
        connection between nodes and a *shorter* path length.

    normalized : bool, optional (default=True)
        Whether to normalize the edge weights by the total sum of edge
        weights.

    Returns
    -------
    h : float
        The local reaching centrality of the node ``v`` in the graph
        ``G``.

    Examples
    --------
    >>> G = nx.DiGraph()
    >>> G.add_edges_from([(1, 2), (1, 3)])
    >>> nx.local_reaching_centrality(G, 3)
    0.0
    >>> G.add_edge(3, 2)
    >>> nx.local_reaching_centrality(G, 3)
    0.5

    See also
    --------
    global_reaching_centrality

    References
    ----------
    .. [1] Mones, Enys, Lilla Vicsek, and Tamás Vicsek.
           "Hierarchy Measure for Complex Networks."
           *PLoS ONE* 7.3 (2012): e33799.
           https://doi.org/10.1371/journal.pone.0033799
    """
    # Corner case: graph with single node containing a self-loop
    if (total_weight := G.size(weight=weight)) > 0 and len(G) == 1:
        raise nx.NetworkXError(
            "local_reaching_centrality of a single node with self-loop not well-defined"
        )
    if paths is None:
        if nx.is_negatively_weighted(G, weight=weight):
            raise nx.NetworkXError("edge weights must be positive")
        if total_weight <= 0:
            raise nx.NetworkXError("Size of G must be positive")
        if weight is not None:
            # Interpret weights as lengths.
            def as_distance(u, v, d):
                return total_weight / d.get(weight, 1)

            paths = nx.shortest_path(G, source=v, weight=as_distance)
        else:
            paths = nx.shortest_path(G, source=v)
    # If the graph is unweighted, simply return the proportion of nodes
    # reachable from the source node ``v``.
    if weight is None and G.is_directed():
        return (len(paths) - 1) / (len(G) - 1)
    if normalized and weight is not None:
        norm = G.size(weight=weight) / G.size()
    else:
        norm = 1
    # TODO This can be trivially parallelized.
    avgw = (_average_weight(G, path, weight=weight) for path in paths.values())
    sum_avg_weight = sum(avgw) / norm
    return sum_avg_weight / (len(G) - 1)
