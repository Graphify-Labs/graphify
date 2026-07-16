import networkx as nx

__all__ = ["average_neighbor_degree"]


@nx._dispatchable(edge_attrs="weight")
def average_neighbor_degree(G, source="out", target="out", nodes=None, weight=None):
    r"""Returns the average degree of the neighborhood of each node.

    In an undirected graph, the neighborhood `N(i)` of node `i` contains the
    nodes that are connected to `i` by an edge.

    For directed graphs, `N(i)` is defined according to the parameter `source`:

        - if source is 'in', then `N(i)` consists of predecessors of node `i`.
        - if source is 'out', then `N(i)` consists of successors of node `i`.
        - if source is 'in+out', then `N(i)` is both predecessors and successors.

    The average neighborhood degree of a node `i` is

    .. math::

        k_{nn,i} = \frac{1}{|N(i)|} \sum_{j \in N(i)} k_j

    where `N(i)` are the neighbors of node `i` and `k_j` is
    the degree of node `j` which belongs to `N(i)`. For weighted
    graphs, an analogous measure can be defined [1]_,

    .. math::

        k_{nn,i}^{w} = \frac{1}{s_i} \sum_{j \in N(i)} w_{ij} k_j

    where `s_i` is the weighted degree of node `i`, `w_{ij}`
    is the weight of the edge that links `i` and `j` and
    `N(i)` are the neighbors of node `i`.


    Parameters
    ----------
    G : NetworkX graph

    source : string ("in"|"out"|"in+out"), optional (default="out")
       Directed graphs only.
       Use "in"- or "out"-neighbors of source node.

    target : string ("in"|"out"|"in+out"), optional (default="out")
       Directed graphs only.
       Use "in"- or "out"-degree for target node.

    nodes : list or iterable, optional (default=G.nodes)
        Compute neighbor degree only for specified nodes.

    weight : string or None, optional (default=None)
       The edge attribute that holds the numerical value used as a weight.
       If None, then each edge has weight 1.

    Returns
    -------
    d: dict
       A dictionary keyed by node to the average degree of its neighbors.

    Raises
    ------
    NetworkXError
        If either `source` or `target` are not one of 'in', 'out', or 'in+out'.
        If either `source` or `target` is passed for an undirected graph.

    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> G.edges[0, 1]["weight"] = 5
    >>> G.edges[2, 3]["weight"] = 3

    >>> nx.average_neighbor_degree(G)
    {0: 2.0, 1: 1.5, 2: 1.5, 3: 2.0}
    >>> nx.average_neighbor_degree(G, weight="weight")
    {0: 2.0, 1: 1.1666666666666667, 2: 1.25, 3: 2.0}

    >>> G = nx.DiGraph()
    >>> nx.add_path(G, [0, 1, 2, 3])
    >>> nx.average_neighbor_degree(G, source="in", target="in")
    {0: 0.0, 1: 0.0, 2: 1.0, 3: 1.0}

    >>> nx.average_neighbor_degree(G, source="out", target="out")
    {0: 1.0, 1: 1.0, 2: 0.0, 3: 0.0}

    See Also
    --------
    average_degree_connectivity

    References
    ----------
    .. [1] A. Barrat, M. Barthélemy, R. Pastor-Satorras, and A. Vespignani,
       "The architecture of complex weighted networks".
       PNAS 101 (11): 3747–3752 (2004).
    """
    if G.is_directed():
        if source == "in":
            source_degree = G.in_degree
        elif source == "out":
            source_degree = G.out_degree
        elif source == "in+out":
            source_degree = G.degree
        else:
            raise nx.NetworkXError(
                f"source argument {source} must be 'in', 'out' or 'in+out'"
            )

        if target == "in":
            target_degree = G.in_degree
        elif target == "out":
            target_degree = G.out_degree
        elif target == "in+out":
            target_degree = G.degree
        else:
            raise nx.NetworkXError(
                f"target argument {target} must be 'in', 'out' or 'in+out'"
            )
    else:
        if source != "out" or target != "out":
            raise nx.NetworkXError(
                f"source and target arguments are only supported for directed graphs"
            )
        source_degree = target_degree = G.degree

    # precompute target degrees -- should *not* be weighted degree
    t_deg = dict(target_degree())

    # Set up both predecessor and successor neighbor dicts leaving empty if not needed
    G_P = G_S = {n: {} for n in G}
    if G.is_directed():
        # "in" or "in+out" cases: G_P contains predecessors
        if "in" in source:
            G_P = G.pred
        # "out" or "in+out" cases: G_S contains successors
        if "out" in source:
            G_S = G.succ
    else:
        # undirected leave G_P empty but G_S is the adjacency
        G_S = G.adj

    # Main loop: Compute average degree of neighbors
    avg = {}
    for n, deg in source_degree(nodes, weight=weight):
        # handle degree zero average
        if deg == 0:
            avg[n] = 0.0
            continue

        # we sum over both G_P and G_S, but one of the two is usually empty.
        if weight is None:
            avg[n] = (
                sum(t_deg[nbr] for nbr in G_S[n]) + sum(t_deg[nbr] for nbr in G_P[n])
            ) / deg
        else:
            avg[n] = (
                sum(dd.get(weight, 1) * t_deg[nbr] for nbr, dd in G_S[n].items())
                + sum(dd.get(weight, 1) * t_deg[nbr] for nbr, dd in G_P[n].items())
            ) / deg
    return avg
