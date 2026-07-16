"""
Link prediction algorithms.
"""

from math import log

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = [
    "resource_allocation_index",
    "jaccard_coefficient",
    "adamic_adar_index",
    "preferential_attachment",
    "cn_soundarajan_hopcroft",
    "ra_index_soundarajan_hopcroft",
    "within_inter_cluster",
    "common_neighbor_centrality",
]


def _apply_prediction(G, func, ebunch=None):
    """Applies the given function to each edge in the specified iterable
    of edges.

    `G` is an instance of :class:`networkx.Graph`.

    `func` is a function on two inputs, each of which is a node in the
    graph. The function can return anything, but it should return a
    value representing a prediction of the likelihood of a "link"
    joining the two nodes.

    `ebunch` is an iterable of pairs of nodes. If not specified, all
    non-edges in the graph `G` will be used.

    """
    if ebunch is None:
        ebunch = nx.non_edges(G)
    else:
        for u, v in ebunch:
            if u not in G:
                raise nx.NodeNotFound(f"Node {u} not in G.")
            if v not in G:
                raise nx.NodeNotFound(f"Node {v} not in G.")
    return ((u, v, func(u, v)) for u, v in ebunch)


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def resource_allocation_index(G, ebunch=None):
    r"""Compute the resource allocation index of all node pairs in ebunch.

    Resource allocation index of `u` and `v` is defined as

    .. math::

        \sum_{w \in \Gamma(u) \cap \Gamma(v)} \frac{1}{|\Gamma(w)|}

    where $\Gamma(u)$ denotes the set of neighbors of $u$.

    Parameters
    ----------
    G : graph
        A NetworkX undirected graph.

    ebunch : iterable of node pairs, optional (default = None)
        Resource allocation index will be computed for each pair of
        nodes given in the iterable. The pairs must be given as
        2-tuples (u, v) where u and v are nodes in the graph. If ebunch
        is None then all nonexistent edges in the graph will be used.
        Default value: None.

    Returns
    -------
    piter : iterator
        An iterator of 3-tuples in the form (u, v, p) where (u, v) is a
        pair of nodes and p is their resource allocation index.

    Raises
    ------
    NetworkXNotImplemented
        If `G` is a `DiGraph`, a `Multigraph` or a `MultiDiGraph`.

    NodeNotFound
        If `ebunch` has a node that is not in `G`.

    Examples
    --------
    >>> G = nx.complete_graph(5)
    >>> preds = nx.resource_allocation_index(G, [(0, 1), (2, 3)])
    >>> for u, v, p in preds:
    ...     print(f"({u}, {v}) -> {p:.8f}")
    (0, 1) -> 0.75000000
    (2, 3) -> 0.75000000

    References
    ----------
    .. [1] T. Zhou, L. Lu, Y.-C. Zhang.
       Predicting missing links via local information.
       Eur. Phys. J. B 71 (2009) 623.
       https://arxiv.org/pdf/0901.0553.pdf
    """

    def predict(u, v):
        return sum(1 / G.degree(w) for w in nx.common_neighbors(G, u, v))

    return _apply_prediction(G, predict, ebunch)


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def jaccard_coefficient(G, ebunch=None):
    r"""Compute the Jaccard coefficient of all node pairs in ebunch.

    Jaccard coefficient of nodes `u` and `v` is defined as

    .. math::

        \frac{|\Gamma(u) \cap \Gamma(v)|}{|\Gamma(u) \cup \Gamma(v)|}

    where $\Gamma(u)$ denotes the set of neighbors of $u$.

    Parameters
    ----------
    G : graph
        A NetworkX undirected graph.

    ebunch : iterable of node pairs, optional (default = None)
        Jaccard coefficient will be computed for each pair of nodes
        given in the iterable. The pairs must be given as 2-tuples
        (u, v) where u and v are nodes in the graph. If ebunch is None
        then all nonexistent edges in the graph will be used.
        Default value: None.

    Returns
    -------
    piter : iterator
        An iterator of 3-tuples in the form (u, v, p) where (u, v) is a
        pair of nodes and p is their Jaccard coefficient.

    Raises
    ------
    NetworkXNotImplemented
        If `G` is a `DiGraph`, a `Multigraph` or a `MultiDiGraph`.

    NodeNotFound
        If `ebunch` has a node that is not in `G`.

    Examples
    --------
    >>> G = nx.complete_graph(5)
    >>> preds = nx.jaccard_coefficient(G, [(0, 1), (2, 3)])
    >>> for u, v, p in preds:
    ...     print(f"({u}, {v}) -> {p:.8f}")
    (0, 1) -> 0.60000000
    (2, 3) -> 0.60000000

    References
    ----------
    .. [1] D. Liben-Nowell, J. Kleinberg.
           The Link Prediction Problem for Social Networks (2004).
           http://www.cs.cornell.edu/home/kleinber/link-pred.pdf
    """

    def predict(u, v):
        union_size = len(set(G[u]) | set(G[v]))
        if union_size == 0:
            return 0
        return len(nx.common_neighbors(G, u, v)) / union_size

    return _apply_prediction(G, predict, ebunch)


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def adamic_adar_index(G, ebunch=None):
    r"""Compute the Adamic-Adar index of all node pairs in ebunch.

    Adamic-Adar index of `u` and `v` is defined as

    .. math::

        \sum_{w \in \Gamma(u) \cap \Gamma(v)} \frac{1}{\log |\Gamma(w)|}

    where $\Gamma(u)$ denotes the set of neighbors of $u$.
    This index leads to zero-division for nodes only connected via self-loops.
    It is intended to be used when no self-loops are present.

    Parameters
    ----------
    G : graph
        NetworkX undirected graph.

    ebunch : iterable of node pairs, optional (default = None)
        Adamic-Adar index will be computed for each pair of nodes given
        in the iterable. The pairs must be given as 2-tuples (u, v)
        where u and v are nodes in the graph. If ebunch is None then all
        nonexistent edges in the graph will be used.
        Default value: None.

    Returns
    -------
    piter : iterator
        An iterator of 3-tuples in the form (u, v, p) where (u, v) is a
        pair of nodes and p is their Adamic-Adar index.

    Raises
    ------
    NetworkXNotImplemented
        If `G` is a `DiGraph`, a `Multigraph` or a `MultiDiGraph`.

    NodeNotFound
        If `ebunch` has a node that is not in `G`.

    Examples
    --------
    >>> G = nx.complete_graph(5)
    >>> preds = nx.adamic_adar_index(G, [(0, 1), (2, 3)])
    >>> for u, v, p in preds:
    ...     print(f"({u}, {v}) -> {p:.8f}")
    (0, 1) -> 2.16404256
    (2, 3) -> 2.16404256

    References
    ----------
    .. [1] D. Liben-Nowell, J. Kleinberg.
           The Link Prediction Problem for Social Networks (2004).
           http://www.cs.cornell.edu/home/kleinber/link-pred.pdf
    """

    def predict(u, v):
        return sum(1 / log(G.degree(w)) for w in nx.common_neighbors(G, u, v))

    return _apply_prediction(G, predict, ebunch)


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def common_neighbor_centrality(G, ebunch=None, alpha=0.8):
    r"""Return the CCPA score for each pair of nodes.

    Compute the Common Neighbor and Centrality based Parameterized Algorithm(CCPA)
    score of all node pairs in ebunch.

    CCPA score of `u` and `v` is defined as

    .. math::

        \alpha \cdot (|\Gamma (u){\cap }^{}\Gamma (v)|)+(1-\alpha )\cdot \frac{N}{{d}_{uv}}

    where $\Gamma(u)$ denotes the set of neighbors of $u$, $\Gamma(v)$ denotes the
    set of neighbors of $v$, $\alpha$ is  parameter varies between [0,1], $N$ denotes
    total number of nodes in the Graph and ${d}_{uv}$ denotes shortest distance
    between $u$ and $v$.

    This algorithm is based on two vital properties of nodes, namely the number
    of common neighbors and their centrality. Common neighbor refers to the common
    nodes between two nodes. Centrality refers to the prestige that a node enjoys
    in a network.

    .. seealso::

        :func:`common_neighbors`

    Parameters
    ----------
    G : graph
        NetworkX undirected graph.

    ebunch : iterable of node pairs, optional (default = None)
        Preferential attachment score will be computed for each pair of
        nodes given in the iterable. The pairs must be given as
        2-tuples (u, v) where u and v are nodes in the graph. If ebunch
        is None then all nonexistent edges in the graph will be used.
        Default value: None.

    alpha : Parameter defined for participation of Common Neighbor
            and Centrality Algorithm share. Values for alpha should
            normally be between 0 and 1. Default value set to 0.8
            because author found better performance at 0.8 for all the
            dataset.
            Default value: 0.8


    Returns
    -------
    piter : iterator
        An iterator of 3-tuples in the form (u, v, p) where (u, v) is a
        pair of nodes and p is their Common Neighbor and Centrality based
        Parameterized Algorithm(CCPA) score.

    Raises
    ------
    NetworkXNotImplemented
        If `G` is a `DiGraph`, a `Multigraph` or a `MultiDiGraph`.

    NetworkXAlgorithmError
        If self loops exist in `ebunch` or in `G` (if `ebunch` is `None`).

    NodeNotFound
        If `ebunch` has a node that is not in `G`.

    Examples
    --------
    >>> G = nx.complete_graph(5)
    >>> preds = nx.common_neighbor_centrality(G, [(0, 1), (2, 3)])
    >>> for u, v, p in preds:
    ...     print(f"({u}, {v}) -> {p}")
    (0, 1) -> 3.4000000000000004
    (2, 3) -> 3.4000000000000004

    References
    ----------
    .. [1] Ahmad, I., Akhtar, M.U., Noor, S. et al.
           Missing Link Prediction using Common Neighbor and Centrality based Parameterized Algorithm.
           Sci Rep 10, 364 (2020).
           https://doi.org/10.1038/s41598-019-57304-y
    """

    # When alpha == 1, the CCPA score simplifies to the number of common neighbors.
    if alpha == 1:

        def predict(u, v):
            if u == v:
                raise nx.NetworkXAlgorithmError("Self loops are not supported")

            return len(nx.common_neighbors(G, u, v))

    else:
        spl = dict(nx.shortest_path_length(G))
        inf = float("inf")

        def predict(u, v):
            if u == v:
                raise nx.NetworkXAlgorithmError("Self loops are not supported")
            path_len = spl[u].get(v, inf)

            n_nbrs = len(nx.common_neighbors(G, u, v))
            return alpha * n_nbrs + (1 - alpha) * len(G) / path_len

    return _apply_prediction(G, predict, ebunch)


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def preferential_attachment(G, ebunch=None):
    r"""Compute the preferential attachment score of all node pairs in ebunch.

    Preferential attachment score of `u` and `v` is defined as

    .. math::

        |\Gamma(u)| |\Gamma(v)|

    where $\Gamma(u)$ denotes the set of neighbors of $u$.

    Parameters
    ----------
    G : graph
        NetworkX undirected graph.

    ebunch : iterable of node pairs, optional (default = None)
        Preferential attachment score will be computed for each pair of
        nodes given in the iterable. The pairs must be given as
        2-tuples (u, v) where u and v are nodes in the graph. If ebunch
        is None then all nonexistent edges in the graph will be used.
        Default value: None.

    Returns
    -------
    piter : iterator
        An iterator of 3-tuples in the form (u, v, p) where (u, v) is a
        pair of nodes and p is their preferential attachment score.

    Raises
    ------
    NetworkXNotImplemented
        If `G` is a `DiGraph`, a `Multigraph` or a `MultiDiGraph`.

    NodeNotFound
        If `ebunch` has a node that is not in `G`.

    Examples
    --------
    >>> G = nx.complete_graph(5)
    >>> preds = nx.preferential_attachment(G, [(0, 1), (2, 3)])
    >>> for u, v, p in preds:
    ...     print(f"({u}, {v}) -> {p}")
    (0, 1) -> 16
    (2, 3) -> 16

    References
    ----------
    .. [1] D. Liben-Nowell, J. Kleinberg.
           The Link Prediction Problem for Social Networks (2004).
           http://www.cs.cornell.edu/home/kleinber/link-pred.pdf
    """

    def predict(u, v):
        return G.degree(u) * G.degree(v)

    return _apply_prediction(G, predict, ebunch)


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable(node_attrs="community")
def cn_soundarajan_hopcroft(G, ebunch=None, community="community"):
    r"""Count the number of common neighbors of all node pairs in ebunch
        using community information.

    For two nodes $u$ and $v$, this function computes the number of
    common neighbors and bonus one for each common neighbor belonging to
    the same community as $u$ and $v$. Mathematically,

    .. math::

        |\Gamma(u) \cap \Gamma(v)| + \sum_{w \in \Gamma(u) \cap \Gamma(v)} f(w)

    where $f(w)$ equals 1 if $w$ belongs to the same community as $u$
    and $v$ or 0 otherwise and $\Gamma(u)$ denotes the set of
    neighbors of $u$.

    Parameters
    ----------
    G : graph
        A NetworkX undirected graph.

    ebunch : iterable of node pairs, optional (default = None)
        The score will be computed for each pair of nodes given in the
        iterable. The pairs must be given as 2-tuples (u, v) where u
        and v are nodes in the graph. If ebunch is None then all
        nonexistent edges in the graph will be used.
        Default value: None.

    community : string, optional (default = 'community')
        Nodes attribute name containing the community information.
        G[u][community] identifies which community u belongs to. Each
        node belongs to at most one community. Default value: 'community'.

    Returns
    -------
    piter : iterator
        An iterator of 3-tuples in the form (u, v, p) where (u, v) is a
        pair of nodes and p is their score.

    Raises
    ------
    NetworkXNotImplemented
        If `G` is a `DiGraph`, a `Multigraph` or a `MultiDiGraph`.

    NetworkXAlgorithmError
        If no community information is available for a node in `ebunch` or in `G` (if `ebunch` is `None`).

    NodeNotFound
        If `ebunch` has a node that is not in `G`.

    Examples
    --------
    >>> G = nx.path_graph(3)
    >>> G.nodes[0]["community"] = 0
    >>> G.nodes[1]["community"] = 0
    >>> G.nodes[2]["community"] = 0
    >>> preds = nx.cn_soundarajan_hopcroft(G, [(0, 2)])
    >>> for u, v, p in preds:
    ...     print(f"({u}, {v}) -> {p}")
    (0, 2) -> 2

    References
    ----------
    .. [1] Sucheta Soundarajan and John Hopcroft.
       Using community information to improve the precision of link
       prediction methods.
       In Proceedings of the 21st international conference companion on
       World Wide Web (WWW '12 Companion). ACM, New York, NY, USA, 607-608.
       http://doi.acm.org/10.1145/2187980.2188150
    """

    def predict(u, v):
        Cu = _community(G, u, community)
        Cv = _community(G, v, community)
        cnbors = nx.common_neighbors(G, u, v)
        neighbors = (
            sum(_community(G, w, community) == Cu for w in cnbors) if Cu == Cv else 0
        )
        return len(cnbors) + neighbors

    return _apply_prediction(G, predict, ebunch)


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable(node_attrs="community")
def ra_index_soundarajan_hopcroft(G, ebunch=None, community="community"):
    r"""Compute the resource allocation index of all node pairs in
    ebunch using community information.

    For two nodes $u$ and $v$, this function computes the resource
    allocation index considering only common neighbors belonging to the
    same community as $u$ and $v$. Mathematically,

    .. math::

        \sum_{w \in \Gamma(u) \cap \Gamma(v)} \frac{f(w)}{|\Gamma(w)|}

    where $f(w)$ equals 1 if $w$ belongs to the same community as $u$
    and $v$ or 0 otherwise and $\Gamma(u)$ denotes the set of
    neighbors of $u$.

    Parameters
    ----------
    G : graph
        A NetworkX undirected graph.

    ebunch : iterable of node pairs, optional (default = None)
        The score will be computed for each pair of nodes given in the
        iterable. The pairs must be given as 2-tuples (u, v) where u
        and v are nodes in the graph. If ebunch is None then all
        nonexistent edges in the graph will be used.
        Default value: None.

    community : string, optional (default = 'community')
        Nodes attribute name containing the community information.
        G[u][community] identifies which community u belongs to. Each
        node belongs to at most one community. Default value: 'community'.

    Returns
    -------
    piter : iterator
        An iterator of 3-tuples in the form (u, v, p) where (u, v) is a
        pair of nodes and p is their score.

    Raises
    ------
    NetworkXNotImplemented
        If `G` is a `DiGraph`, a `Multigraph` or a `MultiDiGraph`.

    NetworkXAlgorithmError
        If no community information is available for a node in `ebunch` or in `G` (if `ebunch` is `None`).

    NodeNotFound
        If `ebunch` has a node that is not in `G`.

    Examples
    --------
    >>> G = nx.Graph()
    >>> G.add_edges_from([(0, 1), (0, 2), (1, 3), (2, 3)])
    >>> G.nodes[0]["community"] = 0
    >>> G.nodes[1]["community"] = 0
    >>> G.nodes[2]["community"] = 1
    >>> G.nodes[3]["community"] = 0
    >>> preds = nx.ra_index_soundarajan_hopcroft(G, [(0, 3)])
    >>> for u, v, p in preds:
    ...     print(f"({u}, {v}) -> {p:.8f}")
    (0, 3) -> 0.50000000

    References
    ----------
    .. [1] Sucheta Soundarajan and John Hopcroft.
       Using community information to improve the precision of link
       prediction methods.
       In Proceedings of the 21st international conference companion on
       World Wide Web (WWW '12 Companion). ACM, New York, NY, USA, 607-608.
       http://doi.acm.org/10.1145/2187980.2188150
    """

    def predict(u, v):
        Cu = _community(G, u, community)
        Cv = _community(G, v, community)
        if Cu != Cv:
            return 0
        cnbors = nx.common_neighbors(G, u, v)
        return sum(1 / G.degree(w) for w in cnbors if _community(G, w, community) == Cu)

    return _apply_prediction(G, predict, ebunch)


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable(node_attrs="community")
def within_inter_cluster(G, ebunch=None, delta=0.001, community="community"):
    """Compute the ratio of within- and inter-cluster common neighbors
    of all node pairs in ebunch.

    For two nodes `u` and `v`, if a common neighbor `w` belongs to the
    same community as them, `w` is considered as within-cluster common
    neighbor of `u` and `v`. Otherwise, it is considered as
    inter-cluster common neighbor of `u` and `v`. The ratio between the
    size of the set of within- and inter-cluster common neighbors is
    defined as the WIC measure. [1]_

    Parameters
    ----------
    G : graph
        A NetworkX undirected graph.

    ebunch : iterable of node pairs, optional (default = None)
        The WIC measure will be computed for each pair of nodes given in
        the iterable. The pairs must be given as 2-tuples (u, v) where
        u and v are nodes in the graph. If ebunch is None then all
        nonexistent edges in the graph will be used.
        Default value: None.

    delta : float, optional (default = 0.001)
        Value to prevent division by zero in case there is no
        inter-cluster common neighbor between two nodes. See [1]_ for
        details. Default value: 0.001.

    community : string, optional (default = 'community')
        Nodes attribute name containing the community information.
        G[u][community] identifies which community u belongs to. Each
        node belongs to at most one community. Default value: 'community'.

    Returns
    -------
    piter : iterator
        An iterator of 3-tuples in the form (u, v, p) where (u, v) is a
        pair of nodes and p is their WIC measure.

    Raises
    ------
    NetworkXNotImplemented
        If `G` is a `DiGraph`, a `Multigraph` or a `MultiDiGraph`.

    NetworkXAlgorithmError
        - If `delta` is less than or equal to zero.
        - If no community information is available for a node in `ebunch` or in `G` (if `ebunch` is `None`).

    NodeNotFound
        If `ebunch` has a node that is not in `G`.

    Examples
    --------
    >>> G = nx.Graph()
    >>> G.add_edges_from([(0, 1), (0, 2), (0, 3), (1, 4), (2, 4), (3, 4)])
    >>> G.nodes[0]["community"] = 0
    >>> G.nodes[1]["community"] = 1
    >>> G.nodes[2]["community"] = 0
    >>> G.nodes[3]["community"] = 0
    >>> G.nodes[4]["community"] = 0
    >>> preds = nx.within_inter_cluster(G, [(0, 4)])
    >>> for u, v, p in preds:
    ...     print(f"({u}, {v}) -> {p:.8f}")
    (0, 4) -> 1.99800200
    >>> preds = nx.within_inter_cluster(G, [(0, 4)], delta=0.5)
    >>> for u, v, p in preds:
    ...     print(f"({u}, {v}) -> {p:.8f}")
    (0, 4) -> 1.33333333

    References
    ----------
    .. [1] Jorge Carlos Valverde-Rebaza and Alneu de Andrade Lopes.
       Link prediction in complex networks based on cluster information.
       In Proceedings of the 21st Brazilian conference on Advances in
       Artificial Intelligence (SBIA'12)
       https://doi.org/10.1007/978-3-642-34459-6_10
    """
    if delta <= 0:
        raise nx.NetworkXAlgorithmError("Delta must be greater than zero")

    def predict(u, v):
        Cu = _community(G, u, community)
        Cv = _community(G, v, community)
        if Cu != Cv:
            return 0
        cnbors = nx.common_neighbors(G, u, v)
        within = {w for w in cnbors if _community(G, w, community) == Cu}
        inter = cnbors - within
        return len(within) / (len(inter) + delta)

    return _apply_prediction(G, predict, ebunch)


def _community(G, u, community):
    """Get the community of the given node."""
    node_u = G.nodes[u]
    try:
        return node_u[community]
    except KeyError as err:
        raise nx.NetworkXAlgorithmError(
            f"No community information available for Node {u}"
        ) from err
