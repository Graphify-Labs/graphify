"""Load centrality."""

from operator import itemgetter

import networkx as nx

__all__ = ["load_centrality", "edge_load_centrality"]


@nx._dispatchable(edge_attrs="weight")
def newman_betweenness_centrality(G, v=None, cutoff=None, normalized=True, weight=None):
    """Compute load centrality for nodes.

    The load centrality of a node is the fraction of all shortest
    paths that pass through that node.

    Parameters
    ----------
    G : graph
      A networkx graph.

    normalized : bool, optional (default=True)
      If True the betweenness values are normalized by b=b/(n-1)(n-2) where
      n is the number of nodes in G.

    weight : None or string, optional (default=None)
      If None, edge weights are ignored.
      Otherwise holds the name of the edge attribute used as weight.
      The weight of an edge is treated as the length or distance between the two sides.

    cutoff : bool, optional (default=None)
      If specified, only consider paths of length <= cutoff.

    Returns
    -------
    nodes : dictionary
       Dictionary of nodes with centrality as the value.

    See Also
    --------
    betweenness_centrality

    Notes
    -----
    Load centrality is slightly different than betweenness. It was originally
    introduced by [2]_. For this load algorithm see [1]_.

    References
    ----------
    .. [1] Mark E. J. Newman:
       Scientific collaboration networks. II.
       Shortest paths, weighted networks, and centrality.
       Physical Review E 64, 016132, 2001.
       http://journals.aps.org/pre/abstract/10.1103/PhysRevE.64.016132
    .. [2] Kwang-Il Goh, Byungnam Kahng and Doochul Kim
       Universal behavior of Load Distribution in Scale-Free Networks.
       Physical Review Letters 87(27):1–4, 2001.
       https://doi.org/10.1103/PhysRevLett.87.278701
    """
    if v is not None:  # only one node
        betweenness = 0.0
        for source in G:
            ubetween = _node_betweenness(G, source, cutoff, False, weight)
            betweenness += ubetween[v] if v in ubetween else 0
        if normalized:
            order = G.order()
            if order <= 2:
                return betweenness  # no normalization b=0 for all nodes
            betweenness *= 1.0 / ((order - 1) * (order - 2))
    else:
        betweenness = {}.fromkeys(G, 0.0)
        for source in betweenness:
            ubetween = _node_betweenness(G, source, cutoff, False, weight)
            for vk in ubetween:
                betweenness[vk] += ubetween[vk]
        if normalized:
            order = G.order()
            if order <= 2:
                return betweenness  # no normalization b=0 for all nodes
            scale = 1.0 / ((order - 1) * (order - 2))
            for v in betweenness:
                betweenness[v] *= scale
    return betweenness  # all nodes


def _node_betweenness(G, source, cutoff=False, normalized=True, weight=None):
    """Node betweenness_centrality helper:

    See betweenness_centrality for what you probably want.
    This actually computes "load" and not betweenness.
    See https://networkx.lanl.gov/ticket/103

    This calculates the load of each node for paths from a single source.
    (The fraction of number of shortests paths from source that go
    through each node.)

    To get the load for a node you need to do all-pairs shortest paths.

    If weight is not None then use Dijkstra for finding shortest paths.
    """
    # get the predecessor and path length data
    if weight is None:
        (pred, length) = nx.predecessor(G, source, cutoff=cutoff, return_seen=True)
    else:
        (pred, length) = nx.dijkstra_predecessor_and_distance(G, source, cutoff, weight)

    # order the nodes by path length
    onodes = [(l, vert) for (vert, l) in length.items()]
    onodes.sort()
    onodes[:] = [vert for (l, vert) in onodes if l > 0]

    # initialize betweenness
    between = {}.fromkeys(length, 1.0)

    while onodes:
        v = onodes.pop()
        if v in pred:
            num_paths = len(pred[v])  # Discount betweenness if more than
            for x in pred[v]:  # one shortest path.
                if x == source:  # stop if hit source because all remaining v
                    break  # also have pred[v]==[source]
                between[x] += between[v] / num_paths
    #  remove source
    for v in between:
        between[v] -= 1
    # rescale to be between 0 and 1
    if normalized:
        l = len(between)
        if l > 2:
            # scale by 1/the number of possible paths
            scale = 1 / ((l - 1) * (l - 2))
            for v in between:
                between[v] *= scale
    return between


load_centrality = newman_betweenness_centrality


@nx._dispatchable
def edge_load_centrality(G, cutoff=False):
    """Compute edge load.

    WARNING: This concept of edge load has not been analysed
    or discussed outside of NetworkX that we know of.
    It is based loosely on load_centrality in the sense that
    it counts the number of shortest paths which cross each edge.
    This function is for demonstration and testing purposes.

    Parameters
    ----------
    G : graph
        A networkx graph

    cutoff : bool, optional (default=False)
        If specified, only consider paths of length <= cutoff.

    Returns
    -------
    A dict keyed by edge 2-tuple to the number of shortest paths
    which use that edge. Where more than one path is shortest
    the count is divided equally among paths.
    """
    betweenness = {}
    for u, v in G.edges():
        betweenness[(u, v)] = 0.0
        betweenness[(v, u)] = 0.0

    for source in G:
        ubetween = _edge_betweenness(G, source, cutoff=cutoff)
        for e, ubetweenv in ubetween.items():
            betweenness[e] += ubetweenv  # cumulative total
    return betweenness


def _edge_betweenness(G, source, nodes=None, cutoff=False):
    """Edge betweenness helper."""
    # get the predecessor data
    (pred, length) = nx.predecessor(G, source, cutoff=cutoff, return_seen=True)
    # order the nodes by path length
    onodes = [n for n, d in sorted(length.items(), key=itemgetter(1))]
    # initialize betweenness, doesn't account for any edge weights
    between = {}
    for u, v in G.edges(nodes):
        between[(u, v)] = 1.0
        between[(v, u)] = 1.0

    while onodes:  # work through all paths
        v = onodes.pop()
        if v in pred:
            # Discount betweenness if more than one shortest path.
            num_paths = len(pred[v])
            for w in pred[v]:
                if w in pred:
                    # Discount betweenness, mult path
                    num_paths = len(pred[w])
                    for x in pred[w]:
                        between[(w, x)] += between[(v, w)] / num_paths
                        between[(x, w)] += between[(w, v)] / num_paths
    return between
