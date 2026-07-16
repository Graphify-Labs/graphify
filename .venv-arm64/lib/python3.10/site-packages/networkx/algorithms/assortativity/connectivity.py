from collections import defaultdict

import networkx as nx

__all__ = ["average_degree_connectivity"]


@nx._dispatchable(edge_attrs="weight")
def average_degree_connectivity(
    G, source="in+out", target="in+out", nodes=None, weight=None
):
    r"""Compute the average degree connectivity of graph.

    The average degree connectivity is the average nearest neighbor degree of
    nodes with degree k. For weighted graphs, an analogous measure can
    be computed using the weighted average neighbors degree defined in
    [1]_, for a node `i`, as

    .. math::

        k_{nn,i}^{w} = \frac{1}{s_i} \sum_{j \in N(i)} w_{ij} k_j

    where `s_i` is the weighted degree of node `i`,
    `w_{ij}` is the weight of the edge that links `i` and `j`,
    and `N(i)` are the neighbors of node `i`.

    Parameters
    ----------
    G : NetworkX graph

    source :  "in"|"out"|"in+out" (default:"in+out")
       Directed graphs only. Use "in"- or "out"-degree for source node.

    target : "in"|"out"|"in+out" (default:"in+out"
       Directed graphs only. Use "in"- or "out"-degree for target node.

    nodes : list or iterable (optional)
        Compute neighbor connectivity for these nodes. The default is all
        nodes.

    weight : string or None, optional (default=None)
       The edge attribute that holds the numerical value used as a weight.
       If None, then each edge has weight 1.

    Returns
    -------
    d : dict
       A dictionary keyed by degree k with the value of average connectivity.

    Raises
    ------
    NetworkXError
        If either `source` or `target` are not one of 'in',
        'out', or 'in+out'.
        If either `source` or `target` is passed for an undirected graph.

    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> G.edges[1, 2]["weight"] = 3
    >>> nx.average_degree_connectivity(G)
    {1: 2.0, 2: 1.5}
    >>> nx.average_degree_connectivity(G, weight="weight")
    {1: 2.0, 2: 1.75}

    See Also
    --------
    average_neighbor_degree

    References
    ----------
    .. [1] A. Barrat, M. Barthélemy, R. Pastor-Satorras, and A. Vespignani,
       "The architecture of complex weighted networks".
       PNAS 101 (11): 3747–3752 (2004).
    """
    # First, determine the type of neighbors and the type of degree to use.
    if G.is_directed():
        if source not in ("in", "out", "in+out"):
            raise nx.NetworkXError('source must be one of "in", "out", or "in+out"')
        if target not in ("in", "out", "in+out"):
            raise nx.NetworkXError('target must be one of "in", "out", or "in+out"')
        direction = {"out": G.out_degree, "in": G.in_degree, "in+out": G.degree}
        neighbor_funcs = {
            "out": G.successors,
            "in": G.predecessors,
            "in+out": G.neighbors,
        }
        source_degree = direction[source]
        target_degree = direction[target]
        neighbors = neighbor_funcs[source]
        # `reverse` indicates whether to look at the in-edge when
        # computing the weight of an edge.
        reverse = source == "in"
    else:
        if source != "in+out" or target != "in+out":
            raise nx.NetworkXError(
                f"source and target arguments are only supported for directed graphs"
            )
        source_degree = G.degree
        target_degree = G.degree
        neighbors = G.neighbors
        reverse = False
    dsum = defaultdict(int)
    dnorm = defaultdict(int)
    # Check if `source_nodes` is actually a single node in the graph.
    source_nodes = source_degree(nodes)
    if nodes in G:
        source_nodes = [(nodes, source_degree(nodes))]
    for n, k in source_nodes:
        nbrdeg = target_degree(neighbors(n))
        if weight is None:
            s = sum(d for n, d in nbrdeg)
        else:  # weight nbr degree by weight of (n,nbr) edge
            if reverse:
                s = sum(G[nbr][n].get(weight, 1) * d for nbr, d in nbrdeg)
            else:
                s = sum(G[n][nbr].get(weight, 1) * d for nbr, d in nbrdeg)
        dnorm[k] += source_degree(n, weight=weight)
        dsum[k] += s

    # normalize
    return {k: avg if dnorm[k] == 0 else avg / dnorm[k] for k, avg in dsum.items()}
