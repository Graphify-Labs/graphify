"""Percolation centrality measures."""

import networkx as nx
from networkx.algorithms.centrality.betweenness import (
    _single_source_dijkstra_path_basic as dijkstra,
)
from networkx.algorithms.centrality.betweenness import (
    _single_source_shortest_path_basic as shortest_path,
)

__all__ = ["percolation_centrality"]


@nx._dispatchable(node_attrs="attribute", edge_attrs="weight")
def percolation_centrality(G, attribute="percolation", states=None, weight=None):
    r"""Compute the percolation centrality for nodes.

    Percolation centrality of a node $v$, at a given time, is defined
    as the proportion of ‘percolated paths’ that go through that node.

    This measure quantifies relative impact of nodes based on their
    topological connectivity, as well as their percolation states.

    Percolation states of nodes are used to depict network percolation
    scenarios (such as during infection transmission in a social network
    of individuals, spreading of computer viruses on computer networks, or
    transmission of disease over a network of towns) over time. In this
    measure usually the percolation state is expressed as a decimal
    between 0.0 and 1.0.

    When all nodes are in the same percolated state this measure is
    equivalent to betweenness centrality.

    Parameters
    ----------
    G : graph
      A NetworkX graph.

    attribute : None or string, optional (default='percolation')
      Name of the node attribute to use for percolation state, used
      if `states` is None. If a node does not set the attribute the
      state of that node will be set to the default value of 1.
      If all nodes do not have the attribute all nodes will be set to
      1 and the centrality measure will be equivalent to betweenness centrality.

    states : None or dict, optional (default=None)
      Specify percolation states for the nodes, nodes as keys states
      as values.

    weight : None or string, optional (default=None)
      If None, all edge weights are considered equal.
      Otherwise holds the name of the edge attribute used as weight.
      The weight of an edge is treated as the length or distance between the two sides.


    Returns
    -------
    nodes : dictionary
       Dictionary of nodes with percolation centrality as the value.

    See Also
    --------
    betweenness_centrality

    Notes
    -----
    The algorithm is from Mahendra Piraveenan, Mikhail Prokopenko, and
    Liaquat Hossain [1]_
    Pair dependencies are calculated and accumulated using [2]_

    For weighted graphs the edge weights must be greater than zero.
    Zero edge weights can produce an infinite number of equal length
    paths between pairs of nodes.

    References
    ----------
    .. [1] Mahendra Piraveenan, Mikhail Prokopenko, Liaquat Hossain
       Percolation Centrality: Quantifying Graph-Theoretic Impact of Nodes
       during Percolation in Networks
       http://journals.plos.org/plosone/article?id=10.1371/journal.pone.0053095
    .. [2] Ulrik Brandes:
       A Faster Algorithm for Betweenness Centrality.
       Journal of Mathematical Sociology 25(2):163-177, 2001.
       https://doi.org/10.1080/0022250X.2001.9990249
    """
    percolation = dict.fromkeys(G, 0.0)  # b[v]=0 for v in G

    nodes = G

    if states is None:
        states = nx.get_node_attributes(nodes, attribute, default=1)

    # sum of all percolation states
    p_sigma_x_t = 0.0
    for v in states.values():
        p_sigma_x_t += v

    for s in nodes:
        # single source shortest paths
        if weight is None:  # use BFS
            S, P, sigma, _ = shortest_path(G, s)
        else:  # use Dijkstra's algorithm
            S, P, sigma, _ = dijkstra(G, s, weight)
        # accumulation
        percolation = _accumulate_percolation(
            percolation, S, P, sigma, s, states, p_sigma_x_t
        )

    n = len(G)

    for v in percolation:
        percolation[v] *= 1 / (n - 2)

    return percolation


def _accumulate_percolation(percolation, S, P, sigma, s, states, p_sigma_x_t):
    delta = dict.fromkeys(S, 0)
    while S:
        w = S.pop()
        coeff = (1 + delta[w]) / sigma[w]
        for v in P[w]:
            delta[v] += sigma[v] * coeff
        if w != s:
            # percolation weight
            pw_s_w = states[s] / (p_sigma_x_t - states[w])
            percolation[w] += delta[w] * pw_s_w
    return percolation
