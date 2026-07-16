import networkx as nx

__all__ = ["degree_centrality", "betweenness_centrality", "closeness_centrality"]


@nx._dispatchable(name="bipartite_degree_centrality")
def degree_centrality(G, nodes):
    r"""Compute the degree centrality for nodes in a bipartite network.

    The degree centrality for a node `v` is the fraction of nodes
    connected to it.

    Parameters
    ----------
    G : graph
       A bipartite network

    nodes : list or container
      Container with all nodes in one bipartite node set.

    Returns
    -------
    centrality : dictionary
       Dictionary keyed by node with bipartite degree centrality as the value.

    Examples
    --------
    >>> G = nx.wheel_graph(5)
    >>> top_nodes = {0, 1, 2}
    >>> nx.bipartite.degree_centrality(G, nodes=top_nodes)
    {0: 2.0, 1: 1.5, 2: 1.5, 3: 1.0, 4: 1.0}

    See Also
    --------
    betweenness_centrality
    closeness_centrality
    :func:`~networkx.algorithms.bipartite.basic.sets`
    :func:`~networkx.algorithms.bipartite.basic.is_bipartite`

    Notes
    -----
    The nodes input parameter must contain all nodes in one bipartite node set,
    but the dictionary returned contains all nodes from both bipartite node
    sets. See :mod:`bipartite documentation <networkx.algorithms.bipartite>`
    for further details on how bipartite graphs are handled in NetworkX.

    For unipartite networks, the degree centrality values are
    normalized by dividing by the maximum possible degree (which is
    `n-1` where `n` is the number of nodes in G).

    In the bipartite case, the maximum possible degree of a node in a
    bipartite node set is the number of nodes in the opposite node set
    [1]_.  The degree centrality for a node `v` in the bipartite
    sets `U` with `n` nodes and `V` with `m` nodes is

    .. math::

        d_{v} = \frac{deg(v)}{m}, \mbox{for} v \in U ,

        d_{v} = \frac{deg(v)}{n}, \mbox{for} v \in V ,


    where `deg(v)` is the degree of node `v`.

    References
    ----------
    .. [1] Borgatti, S.P. and Halgin, D. In press. "Analyzing Affiliation
        Networks". In Carrington, P. and Scott, J. (eds) The Sage Handbook
        of Social Network Analysis. Sage Publications.
        https://dx.doi.org/10.4135/9781446294413.n28
    """
    top = set(nodes)
    bottom = set(G) - top
    s = 1.0 / len(bottom)
    centrality = {n: d * s for n, d in G.degree(top)}
    s = 1.0 / len(top)
    centrality.update({n: d * s for n, d in G.degree(bottom)})
    return centrality


@nx._dispatchable(name="bipartite_betweenness_centrality")
def betweenness_centrality(G, nodes):
    r"""Compute betweenness centrality for nodes in a bipartite network.

    Betweenness centrality of a node `v` is the sum of the
    fraction of all-pairs shortest paths that pass through `v`.

    Values of betweenness are normalized by the maximum possible
    value which for bipartite graphs is limited by the relative size
    of the two node sets [1]_.

    Let `n` be the number of nodes in the node set `U` and
    `m` be the number of nodes in the node set `V`, then
    nodes in `U` are normalized by dividing by

    .. math::

       \frac{1}{2} [m^2 (s + 1)^2 + m (s + 1)(2t - s - 1) - t (2s - t + 3)] ,

    where

    .. math::

        s = (n - 1) \div m , t = (n - 1) \mod m ,

    and nodes in `V` are normalized by dividing by

    .. math::

        \frac{1}{2} [n^2 (p + 1)^2 + n (p + 1)(2r - p - 1) - r (2p - r + 3)] ,

    where,

    .. math::

        p = (m - 1) \div n , r = (m - 1) \mod n .

    Parameters
    ----------
    G : graph
        A bipartite graph

    nodes : list or container
        Container with all nodes in one bipartite node set.

    Returns
    -------
    betweenness : dictionary
        Dictionary keyed by node with bipartite betweenness centrality
        as the value.

    Examples
    --------
    >>> G = nx.cycle_graph(4)
    >>> top_nodes = {1, 2}
    >>> nx.bipartite.betweenness_centrality(G, nodes=top_nodes)
    {0: 0.25, 1: 0.25, 2: 0.25, 3: 0.25}

    See Also
    --------
    degree_centrality
    closeness_centrality
    :func:`~networkx.algorithms.bipartite.basic.sets`
    :func:`~networkx.algorithms.bipartite.basic.is_bipartite`

    Notes
    -----
    The nodes input parameter must contain all nodes in one bipartite node set,
    but the dictionary returned contains all nodes from both node sets.
    See :mod:`bipartite documentation <networkx.algorithms.bipartite>`
    for further details on how bipartite graphs are handled in NetworkX.


    References
    ----------
    .. [1] Borgatti, S.P. and Halgin, D. In press. "Analyzing Affiliation
        Networks". In Carrington, P. and Scott, J. (eds) The Sage Handbook
        of Social Network Analysis. Sage Publications.
        https://dx.doi.org/10.4135/9781446294413.n28
    """
    top = set(nodes)
    bottom = set(G) - top
    n = len(top)
    m = len(bottom)
    s, t = divmod(n - 1, m)
    bet_max_top = (
        ((m**2) * ((s + 1) ** 2))
        + (m * (s + 1) * (2 * t - s - 1))
        - (t * ((2 * s) - t + 3))
    ) / 2.0
    p, r = divmod(m - 1, n)
    bet_max_bot = (
        ((n**2) * ((p + 1) ** 2))
        + (n * (p + 1) * (2 * r - p - 1))
        - (r * ((2 * p) - r + 3))
    ) / 2.0
    betweenness = nx.betweenness_centrality(G, normalized=False, weight=None)
    for node in top:
        betweenness[node] /= bet_max_top
    for node in bottom:
        betweenness[node] /= bet_max_bot
    return betweenness


@nx._dispatchable(name="bipartite_closeness_centrality")
def closeness_centrality(G, nodes, normalized=True):
    r"""Compute the closeness centrality for nodes in a bipartite network.

    The closeness of a node is the distance to all other nodes in the
    graph or in the case that the graph is not connected to all other nodes
    in the connected component containing that node.

    Parameters
    ----------
    G : graph
        A bipartite network

    nodes : list or container
        Container with all nodes in one bipartite node set.

    normalized : bool, optional
      If True (default) normalize by connected component size.

    Returns
    -------
    closeness : dictionary
        Dictionary keyed by node with bipartite closeness centrality
        as the value.

    Examples
    --------
    >>> G = nx.wheel_graph(5)
    >>> top_nodes = {0, 1, 2}
    >>> nx.bipartite.closeness_centrality(G, nodes=top_nodes)
    {0: 1.5, 1: 1.2, 2: 1.2, 3: 1.0, 4: 1.0}

    See Also
    --------
    betweenness_centrality
    degree_centrality
    :func:`~networkx.algorithms.bipartite.basic.sets`
    :func:`~networkx.algorithms.bipartite.basic.is_bipartite`

    Notes
    -----
    The nodes input parameter must contain all nodes in one bipartite node set,
    but the dictionary returned contains all nodes from both node sets.
    See :mod:`bipartite documentation <networkx.algorithms.bipartite>`
    for further details on how bipartite graphs are handled in NetworkX.


    Closeness centrality is normalized by the minimum distance possible.
    In the bipartite case the minimum distance for a node in one bipartite
    node set is 1 from all nodes in the other node set and 2 from all
    other nodes in its own set [1]_. Thus the closeness centrality
    for node `v`  in the two bipartite sets `U` with
    `n` nodes and `V` with `m` nodes is

    .. math::

        c_{v} = \frac{m + 2(n - 1)}{d}, \mbox{for} v \in U,

        c_{v} = \frac{n + 2(m - 1)}{d}, \mbox{for} v \in V,

    where `d` is the sum of the distances from `v` to all
    other nodes.

    Higher values of closeness  indicate higher centrality.

    As in the unipartite case, setting normalized=True causes the
    values to normalized further to n-1 / size(G)-1 where n is the
    number of nodes in the connected part of graph containing the
    node.  If the graph is not completely connected, this algorithm
    computes the closeness centrality for each connected part
    separately.

    References
    ----------
    .. [1] Borgatti, S.P. and Halgin, D. In press. "Analyzing Affiliation
        Networks". In Carrington, P. and Scott, J. (eds) The Sage Handbook
        of Social Network Analysis. Sage Publications.
        https://dx.doi.org/10.4135/9781446294413.n28
    """
    closeness = {}
    path_length = nx.single_source_shortest_path_length
    top = set(nodes)
    bottom = set(G) - top
    n = len(top)
    m = len(bottom)
    for node in top:
        sp = dict(path_length(G, node))
        totsp = sum(sp.values())
        if totsp > 0.0 and len(G) > 1:
            closeness[node] = (m + 2 * (n - 1)) / totsp
            if normalized:
                s = (len(sp) - 1) / (len(G) - 1)
                closeness[node] *= s
        else:
            closeness[node] = 0.0
    for node in bottom:
        sp = dict(path_length(G, node))
        totsp = sum(sp.values())
        if totsp > 0.0 and len(G) > 1:
            closeness[node] = (n + 2 * (m - 1)) / totsp
            if normalized:
                s = (len(sp) - 1) / (len(G) - 1)
                closeness[node] *= s
        else:
            closeness[node] = 0.0
    return closeness
