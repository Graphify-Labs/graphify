"""Betweenness centrality measures for subsets of nodes."""

import networkx as nx
from networkx.algorithms.centrality.betweenness import (
    _add_edge_keys,
)
from networkx.algorithms.centrality.betweenness import (
    _single_source_dijkstra_path_basic as dijkstra,
)
from networkx.algorithms.centrality.betweenness import (
    _single_source_shortest_path_basic as shortest_path,
)

__all__ = [
    "betweenness_centrality_subset",
    "edge_betweenness_centrality_subset",
]


@nx._dispatchable(edge_attrs="weight")
def betweenness_centrality_subset(G, sources, targets, normalized=False, weight=None):
    r"""Compute betweenness centrality for a subset of nodes.

    .. math::

       c_B(v) =\sum_{s\in S, t \in T} \frac{\sigma(s, t|v)}{\sigma(s, t)}

    where $S$ is the set of sources, $T$ is the set of targets,
    $\sigma(s, t)$ is the number of shortest $(s, t)$-paths,
    and $\sigma(s, t|v)$ is the number of those paths
    passing through some  node $v$ other than $s, t$.
    If $s = t$, $\sigma(s, t) = 1$,
    and if $v \in {s, t}$, $\sigma(s, t|v) = 0$ [2]_.


    Parameters
    ----------
    G : graph
      A NetworkX graph.

    sources: list of nodes
      Nodes to use as sources for shortest paths in betweenness

    targets: list of nodes
      Nodes to use as targets for shortest paths in betweenness

    normalized : bool, optional
      If True the betweenness values are normalized by $2/((n-1)(n-2))$
      for graphs, and $1/((n-1)(n-2))$ for directed graphs where $n$
      is the number of nodes in G.

    weight : None or string, optional (default=None)
      If None, all edge weights are considered equal.
      Otherwise holds the name of the edge attribute used as weight.
      Weights are used to calculate weighted shortest paths, so they are
      interpreted as distances.

    Returns
    -------
    nodes : dictionary
       Dictionary of nodes with betweenness centrality as the value.

    See Also
    --------
    edge_betweenness_centrality
    load_centrality

    Notes
    -----
    The basic algorithm is from [1]_.

    For weighted graphs the edge weights must be greater than zero.
    Zero edge weights can produce an infinite number of equal length
    paths between pairs of nodes.

    The normalization might seem a little strange but it is
    designed to make betweenness_centrality(G) be the same as
    betweenness_centrality_subset(G,sources=G.nodes(),targets=G.nodes()).

    The total number of paths between source and target is counted
    differently for directed and undirected graphs. Directed paths
    are easy to count. Undirected paths are tricky: should a path
    from "u" to "v" count as 1 undirected path or as 2 directed paths?

    For betweenness_centrality we report the number of undirected
    paths when G is undirected.

    For betweenness_centrality_subset the reporting is different.
    If the source and target subsets are the same, then we want
    to count undirected paths. But if the source and target subsets
    differ -- for example, if sources is {0} and targets is {1},
    then we are only counting the paths in one direction. They are
    undirected paths but we are counting them in a directed way.
    To count them as undirected paths, each should count as half a path.

    References
    ----------
    .. [1] Ulrik Brandes, A Faster Algorithm for Betweenness Centrality.
       Journal of Mathematical Sociology 25(2):163-177, 2001.
       https://doi.org/10.1080/0022250X.2001.9990249
    .. [2] Ulrik Brandes: On Variants of Shortest-Path Betweenness
       Centrality and their Generic Computation.
       Social Networks 30(2):136-145, 2008.
       https://doi.org/10.1016/j.socnet.2007.11.001
    """
    b = dict.fromkeys(G, 0.0)  # b[v]=0 for v in G
    for s in sources:
        # single source shortest paths
        if weight is None:  # use BFS
            S, P, sigma, _ = shortest_path(G, s)
        else:  # use Dijkstra's algorithm
            S, P, sigma, _ = dijkstra(G, s, weight)
        b = _accumulate_subset(b, S, P, sigma, s, targets)
    b = _rescale(b, len(G), normalized=normalized, directed=G.is_directed())
    return b


@nx._dispatchable(edge_attrs="weight")
def edge_betweenness_centrality_subset(
    G, sources, targets, normalized=False, weight=None
):
    r"""Compute betweenness centrality for edges for a subset of nodes.

    .. math::

       c_B(v) =\sum_{s\in S,t \in T} \frac{\sigma(s, t|e)}{\sigma(s, t)}

    where $S$ is the set of sources, $T$ is the set of targets,
    $\sigma(s, t)$ is the number of shortest $(s, t)$-paths,
    and $\sigma(s, t|e)$ is the number of those paths
    passing through edge $e$ [2]_.

    Parameters
    ----------
    G : graph
      A networkx graph.

    sources: list of nodes
      Nodes to use as sources for shortest paths in betweenness

    targets: list of nodes
      Nodes to use as targets for shortest paths in betweenness

    normalized : bool, optional
      If True the betweenness values are normalized by `2/(n(n-1))`
      for graphs, and `1/(n(n-1))` for directed graphs where `n`
      is the number of nodes in G.

    weight : None or string, optional (default=None)
      If None, all edge weights are considered equal.
      Otherwise holds the name of the edge attribute used as weight.
      Weights are used to calculate weighted shortest paths, so they are
      interpreted as distances.

    Returns
    -------
    edges : dictionary
       Dictionary of edges with Betweenness centrality as the value.

    See Also
    --------
    betweenness_centrality
    edge_load

    Notes
    -----
    The basic algorithm is from [1]_.

    For weighted graphs the edge weights must be greater than zero.
    Zero edge weights can produce an infinite number of equal length
    paths between pairs of nodes.

    The normalization might seem a little strange but it is the same
    as in edge_betweenness_centrality() and is designed to make
    edge_betweenness_centrality(G) be the same as
    edge_betweenness_centrality_subset(G,sources=G.nodes(),targets=G.nodes()).

    References
    ----------
    .. [1] Ulrik Brandes, A Faster Algorithm for Betweenness Centrality.
       Journal of Mathematical Sociology 25(2):163-177, 2001.
       https://doi.org/10.1080/0022250X.2001.9990249
    .. [2] Ulrik Brandes: On Variants of Shortest-Path Betweenness
       Centrality and their Generic Computation.
       Social Networks 30(2):136-145, 2008.
       https://doi.org/10.1016/j.socnet.2007.11.001
    """
    b = dict.fromkeys(G, 0.0)  # b[v]=0 for v in G
    b.update(dict.fromkeys(G.edges(), 0.0))  # b[e] for e in G.edges()
    for s in sources:
        # single source shortest paths
        if weight is None:  # use BFS
            S, P, sigma, _ = shortest_path(G, s)
        else:  # use Dijkstra's algorithm
            S, P, sigma, _ = dijkstra(G, s, weight)
        b = _accumulate_edges_subset(b, S, P, sigma, s, targets)
    for n in G:  # remove nodes to only return edges
        del b[n]
    b = _rescale_e(b, len(G), normalized=normalized, directed=G.is_directed())
    if G.is_multigraph():
        b = _add_edge_keys(G, b, weight=weight)
    return b


def _accumulate_subset(betweenness, S, P, sigma, s, targets):
    delta = dict.fromkeys(S, 0.0)
    target_set = set(targets) - {s}
    while S:
        w = S.pop()
        if w in target_set:
            coeff = (delta[w] + 1.0) / sigma[w]
        else:
            coeff = delta[w] / sigma[w]
        for v in P[w]:
            delta[v] += sigma[v] * coeff
        if w != s:
            betweenness[w] += delta[w]
    return betweenness


def _accumulate_edges_subset(betweenness, S, P, sigma, s, targets):
    """edge_betweenness_centrality_subset helper."""
    delta = dict.fromkeys(S, 0)
    target_set = set(targets)
    while S:
        w = S.pop()
        for v in P[w]:
            if w in target_set:
                c = (sigma[v] / sigma[w]) * (1.0 + delta[w])
            else:
                c = delta[w] / len(P[w])
            if (v, w) not in betweenness:
                betweenness[(w, v)] += c
            else:
                betweenness[(v, w)] += c
            delta[v] += c
        if w != s:
            betweenness[w] += delta[w]
    return betweenness


def _rescale(betweenness, n, normalized, directed=False):
    """betweenness_centrality_subset helper."""
    if normalized:
        if n <= 2:
            scale = None  # no normalization b=0 for all nodes
        else:
            scale = 1.0 / ((n - 1) * (n - 2))
    else:  # rescale by 2 for undirected graphs
        if not directed:
            scale = 0.5
        else:
            scale = None
    if scale is not None:
        for v in betweenness:
            betweenness[v] *= scale
    return betweenness


def _rescale_e(betweenness, n, normalized, directed=False):
    """edge_betweenness_centrality_subset helper."""
    if normalized:
        if n <= 1:
            scale = None  # no normalization b=0 for all nodes
        else:
            scale = 1.0 / (n * (n - 1))
    else:  # rescale by 2 for undirected graphs
        if not directed:
            scale = 0.5
        else:
            scale = None
    if scale is not None:
        for v in betweenness:
            betweenness[v] *= scale
    return betweenness
