"""Functions for computing measures of structural holes."""

import networkx as nx

__all__ = ["constraint", "local_constraint", "effective_size"]


@nx._dispatchable(edge_attrs="weight")
def mutual_weight(G, u, v, weight=None):
    """Returns the sum of the weights of the edge from `u` to `v` and
    the edge from `v` to `u` in `G`.

    `weight` is the edge data key that represents the edge weight. If
    the specified key is `None` or is not in the edge data for an edge,
    that edge is assumed to have weight 1.

    Pre-conditions: `u` and `v` must both be in `G`.

    """
    try:
        a_uv = G[u][v].get(weight, 1)
    except KeyError:
        a_uv = 0
    try:
        a_vu = G[v][u].get(weight, 1)
    except KeyError:
        a_vu = 0
    return a_uv + a_vu


@nx._dispatchable(edge_attrs="weight")
def normalized_mutual_weight(G, u, v, norm=sum, weight=None):
    """Returns normalized mutual weight of the edges from `u` to `v`
    with respect to the mutual weights of the neighbors of `u` in `G`.

    `norm` specifies how the normalization factor is computed. It must
    be a function that takes a single argument and returns a number.
    The argument will be an iterable of mutual weights
    of pairs ``(u, w)``, where ``w`` ranges over each (in- and
    out-)neighbor of ``u``. Commons values for `normalization` are
    ``sum`` and ``max``.

    `weight` can be ``None`` or a string, if None, all edge weights
    are considered equal. Otherwise holds the name of the edge
    attribute used as weight.

    """
    scale = norm(mutual_weight(G, u, w, weight) for w in set(nx.all_neighbors(G, u)))
    return 0 if scale == 0 else mutual_weight(G, u, v, weight) / scale


@nx._dispatchable(edge_attrs="weight")
def effective_size(G, nodes=None, weight=None):
    r"""Returns the effective size of all nodes in the graph ``G``.

    The *effective size* of a node's ego network is based on the concept
    of redundancy. A person's ego network has redundancy to the extent
    that her contacts are connected to each other as well. The
    nonredundant part of a person's relationships is the effective
    size of her ego network [1]_.  Formally, the effective size of a
    node $u$, denoted $e(u)$, is defined by

    .. math::

       e(u) = \sum_{v \in N(u) \setminus \{u\}}
       \left(1 - \sum_{w \in N(v)} p_{uw} m_{vw}\right)

    where $N(u)$ is the set of neighbors of $u$ and $p_{uw}$ is the
    normalized mutual weight of the (directed or undirected) edges
    joining $u$ and $v$, for each vertex $u$ and $v$ [1]_. And $m_{vw}$
    is the mutual weight of $v$ and $w$ divided by $v$ highest mutual
    weight with any of its neighbors. The *mutual weight* of $u$ and $v$
    is the sum of the weights of edges joining them (edge weights are
    assumed to be one if the graph is unweighted).

    For the case of unweighted and undirected graphs, Borgatti proposed
    a simplified formula to compute effective size [2]_

    .. math::

       e(u) = n - \frac{2t}{n}

    where `t` is the number of ties in the ego network (not including
    ties to ego) and `n` is the number of nodes (excluding ego).

    Parameters
    ----------
    G : NetworkX graph
        The graph containing ``v``. Directed graphs are treated like
        undirected graphs when computing neighbors of ``v``.

    nodes : container, optional
        Container of nodes in the graph ``G`` to compute the effective size.
        If None, the effective size of every node is computed.

    weight : None or string, optional
      If None, all edge weights are considered equal.
      Otherwise holds the name of the edge attribute used as weight.

    Returns
    -------
    dict
        Dictionary with nodes as keys and the effective size of the node as values.

    Notes
    -----
    Burt also defined the related concept of *efficiency* of a node's ego
    network, which is its effective size divided by the degree of that
    node [1]_. So you can easily compute efficiency:

    >>> G = nx.DiGraph()
    >>> G.add_edges_from([(0, 1), (0, 2), (1, 0), (2, 1)])
    >>> esize = nx.effective_size(G)
    >>> efficiency = {n: v / G.degree(n) for n, v in esize.items()}

    See also
    --------
    constraint

    References
    ----------
    .. [1] Burt, Ronald S.
           *Structural Holes: The Social Structure of Competition.*
           Cambridge: Harvard University Press, 1995.

    .. [2] Borgatti, S.
           "Structural Holes: Unpacking Burt's Redundancy Measures"
           CONNECTIONS 20(1):35-38.
           http://www.analytictech.com/connections/v20(1)/holes.htm

    """

    def redundancy(G, u, v, weight=None):
        nmw = normalized_mutual_weight
        r = sum(
            nmw(G, u, w, weight=weight) * nmw(G, v, w, norm=max, weight=weight)
            for w in set(nx.all_neighbors(G, u))
        )
        return 1 - r

    effective_size = {}
    if nodes is None:
        nodes = G
    # Use Borgatti's simplified formula for unweighted and undirected graphs
    if not G.is_directed() and weight is None:
        for v in nodes:
            # Effective size is not defined for isolated nodes
            if len(G[v]) == 0:
                effective_size[v] = float("nan")
                continue
            E = nx.ego_graph(G, v, center=False, undirected=True)
            effective_size[v] = len(E) - (2 * E.size()) / len(E)
    else:
        for v in nodes:
            # Effective size is not defined for isolated nodes
            if len(G[v]) == 0:
                effective_size[v] = float("nan")
                continue
            effective_size[v] = sum(
                redundancy(G, v, u, weight) for u in set(nx.all_neighbors(G, v))
            )
    return effective_size


@nx._dispatchable(edge_attrs="weight")
def constraint(G, nodes=None, weight=None):
    r"""Returns the constraint on all nodes in the graph ``G``.

    The *constraint* is a measure of the extent to which a node *v* is
    invested in those nodes that are themselves invested in the
    neighbors of *v*. Formally, the *constraint on v*, denoted `c(v)`,
    is defined by

    .. math::

       c(v) = \sum_{w \in N(v) \setminus \{v\}} \ell(v, w)

    where $N(v)$ is the subset of the neighbors of `v` that are either
    predecessors or successors of `v` and $\ell(v, w)$ is the local
    constraint on `v` with respect to `w` [1]_. For the definition of local
    constraint, see :func:`local_constraint`.

    Parameters
    ----------
    G : NetworkX graph
        The graph containing ``v``. This can be either directed or undirected.

    nodes : container, optional
        Container of nodes in the graph ``G`` to compute the constraint. If
        None, the constraint of every node is computed.

    weight : None or string, optional
      If None, all edge weights are considered equal.
      Otherwise holds the name of the edge attribute used as weight.

    Returns
    -------
    dict
        Dictionary with nodes as keys and the constraint on the node as values.

    See also
    --------
    local_constraint

    References
    ----------
    .. [1] Burt, Ronald S.
           "Structural holes and good ideas".
           American Journal of Sociology (110): 349–399.

    """
    if nodes is None:
        nodes = G
    constraint = {}
    for v in nodes:
        # Constraint is not defined for isolated nodes
        if len(G[v]) == 0:
            constraint[v] = float("nan")
            continue
        constraint[v] = sum(
            local_constraint(G, v, n, weight) for n in set(nx.all_neighbors(G, v))
        )
    return constraint


@nx._dispatchable(edge_attrs="weight")
def local_constraint(G, u, v, weight=None):
    r"""Returns the local constraint on the node ``u`` with respect to
    the node ``v`` in the graph ``G``.

    Formally, the *local constraint on u with respect to v*, denoted
    $\ell(u, v)$, is defined by

    .. math::

       \ell(u, v) = \left(p_{uv} + \sum_{w \in N(v)} p_{uw} p_{wv}\right)^2,

    where $N(v)$ is the set of neighbors of $v$ and $p_{uv}$ is the
    normalized mutual weight of the (directed or undirected) edges
    joining $u$ and $v$, for each vertex $u$ and $v$ [1]_. The *mutual
    weight* of $u$ and $v$ is the sum of the weights of edges joining
    them (edge weights are assumed to be one if the graph is
    unweighted).

    Parameters
    ----------
    G : NetworkX graph
        The graph containing ``u`` and ``v``. This can be either
        directed or undirected.

    u : node
        A node in the graph ``G``.

    v : node
        A node in the graph ``G``.

    weight : None or string, optional
      If None, all edge weights are considered equal.
      Otherwise holds the name of the edge attribute used as weight.

    Returns
    -------
    float
        The constraint of the node ``v`` in the graph ``G``.

    See also
    --------
    constraint

    References
    ----------
    .. [1] Burt, Ronald S.
           "Structural holes and good ideas".
           American Journal of Sociology (110): 349–399.

    """
    nmw = normalized_mutual_weight
    direct = nmw(G, u, v, weight=weight)
    indirect = sum(
        nmw(G, u, w, weight=weight) * nmw(G, w, v, weight=weight)
        for w in set(nx.all_neighbors(G, u))
    )
    return (direct + indirect) ** 2
