"""One-mode (unipartite) projections of bipartite graphs."""

import networkx as nx
from networkx.exception import NetworkXAlgorithmError
from networkx.utils import not_implemented_for

__all__ = [
    "projected_graph",
    "weighted_projected_graph",
    "collaboration_weighted_projected_graph",
    "overlap_weighted_projected_graph",
    "generic_weighted_projected_graph",
]


@nx._dispatchable(
    graphs="B", preserve_node_attrs=True, preserve_graph_attrs=True, returns_graph=True
)
def projected_graph(B, nodes, multigraph=False):
    r"""Returns the projection of B onto one of its node sets.

    Returns the graph G that is the projection of the bipartite graph B
    onto the specified nodes. They retain their attributes and are connected
    in G if they have a common neighbor in B.

    Parameters
    ----------
    B : NetworkX graph
      The input graph should be bipartite.

    nodes : list or iterable
      Nodes to project onto (the "bottom" nodes).

    multigraph: bool (default=False)
       If True return a multigraph where the multiple edges represent multiple
       shared neighbors.  They edge key in the multigraph is assigned to the
       label of the neighbor.

    Returns
    -------
    Graph : NetworkX graph or multigraph
       A graph that is the projection onto the given nodes.

    Examples
    --------
    >>> from networkx.algorithms import bipartite
    >>> B = nx.path_graph(4)
    >>> G = bipartite.projected_graph(B, [1, 3])
    >>> list(G)
    [1, 3]
    >>> list(G.edges())
    [(1, 3)]

    If nodes `a`, and `b` are connected through both nodes 1 and 2 then
    building a multigraph results in two edges in the projection onto
    [`a`, `b`]:

    >>> B = nx.Graph()
    >>> B.add_edges_from([("a", 1), ("b", 1), ("a", 2), ("b", 2)])
    >>> G = bipartite.projected_graph(B, ["a", "b"], multigraph=True)
    >>> print([sorted((u, v)) for u, v in G.edges()])
    [['a', 'b'], ['a', 'b']]

    Notes
    -----
    No attempt is made to verify that the input graph B is bipartite.
    Returns a simple graph that is the projection of the bipartite graph B
    onto the set of nodes given in list nodes.  If multigraph=True then
    a multigraph is returned with an edge for every shared neighbor.

    Directed graphs are allowed as input.  The output will also then
    be a directed graph with edges if there is a directed path between
    the nodes.

    The graph and node properties are (shallow) copied to the projected graph.

    See :mod:`bipartite documentation <networkx.algorithms.bipartite>`
    for further details on how bipartite graphs are handled in NetworkX.

    See Also
    --------
    is_bipartite,
    is_bipartite_node_set,
    sets,
    weighted_projected_graph,
    collaboration_weighted_projected_graph,
    overlap_weighted_projected_graph,
    generic_weighted_projected_graph
    """
    if B.is_multigraph():
        raise nx.NetworkXError("not defined for multigraphs")
    if B.is_directed():
        directed = True
        if multigraph:
            G = nx.MultiDiGraph()
        else:
            G = nx.DiGraph()
    else:
        directed = False
        if multigraph:
            G = nx.MultiGraph()
        else:
            G = nx.Graph()
    G.graph.update(B.graph)
    G.add_nodes_from((n, B.nodes[n]) for n in nodes)
    for u in nodes:
        nbrs2 = {v for nbr in B[u] for v in B[nbr] if v != u}
        if multigraph:
            for n in nbrs2:
                if directed:
                    links = set(B[u]) & set(B.pred[n])
                else:
                    links = set(B[u]) & set(B[n])
                for l in links:
                    if not G.has_edge(u, n, l):
                        G.add_edge(u, n, key=l)
        else:
            G.add_edges_from((u, n) for n in nbrs2)
    return G


@not_implemented_for("multigraph")
@nx._dispatchable(graphs="B", returns_graph=True)
def weighted_projected_graph(B, nodes, ratio=False):
    r"""Returns a weighted projection of B onto one of its node sets.

    The weighted projected graph is the projection of the bipartite
    network B onto the specified nodes with weights representing the
    number of shared neighbors or the ratio between actual shared
    neighbors and possible shared neighbors if ``ratio is True`` [1]_.
    The nodes retain their attributes and are connected in the resulting
    graph if they have an edge to a common node in the original graph.

    Parameters
    ----------
    B : NetworkX graph
        The input graph should be bipartite.

    nodes : list or iterable
        Distinct nodes to project onto (the "bottom" nodes).

    ratio: Bool (default=False)
        If True, edge weight is the ratio between actual shared neighbors
        and maximum possible shared neighbors (i.e., the size of the other
        node set). If False, edges weight is the number of shared neighbors.

    Returns
    -------
    Graph : NetworkX graph
       A graph that is the projection onto the given nodes.

    Examples
    --------
    >>> from networkx.algorithms import bipartite
    >>> B = nx.path_graph(4)
    >>> G = bipartite.weighted_projected_graph(B, [1, 3])
    >>> list(G)
    [1, 3]
    >>> list(G.edges(data=True))
    [(1, 3, {'weight': 1})]
    >>> G = bipartite.weighted_projected_graph(B, [1, 3], ratio=True)
    >>> list(G.edges(data=True))
    [(1, 3, {'weight': 0.5})]

    Notes
    -----
    No attempt is made to verify that the input graph B is bipartite, or that
    the input nodes are distinct. However, if the length of the input nodes is
    greater than or equal to the nodes in the graph B, an exception is raised.
    If the nodes are not distinct but don't raise this error, the output weights
    will be incorrect.
    The graph and node properties are (shallow) copied to the projected graph.

    See :mod:`bipartite documentation <networkx.algorithms.bipartite>`
    for further details on how bipartite graphs are handled in NetworkX.

    See Also
    --------
    is_bipartite,
    is_bipartite_node_set,
    sets,
    collaboration_weighted_projected_graph,
    overlap_weighted_projected_graph,
    generic_weighted_projected_graph
    projected_graph

    References
    ----------
    .. [1] Borgatti, S.P. and Halgin, D. In press. "Analyzing Affiliation
        Networks". In Carrington, P. and Scott, J. (eds) The Sage Handbook
        of Social Network Analysis. Sage Publications.
    """
    if B.is_directed():
        pred = B.pred
        G = nx.DiGraph()
    else:
        pred = B.adj
        G = nx.Graph()
    G.graph.update(B.graph)
    G.add_nodes_from((n, B.nodes[n]) for n in nodes)
    n_top = len(B) - len(nodes)

    if n_top < 1:
        raise NetworkXAlgorithmError(
            f"the size of the nodes to project onto ({len(nodes)}) is >= the graph size ({len(B)}).\n"
            "They are either not a valid bipartite partition or contain duplicates"
        )

    for u in nodes:
        unbrs = set(B[u])
        nbrs2 = {n for nbr in unbrs for n in B[nbr]} - {u}
        for v in nbrs2:
            vnbrs = set(pred[v])
            common = unbrs & vnbrs
            if not ratio:
                weight = len(common)
            else:
                weight = len(common) / n_top
            G.add_edge(u, v, weight=weight)
    return G


@not_implemented_for("multigraph")
@nx._dispatchable(graphs="B", returns_graph=True)
def collaboration_weighted_projected_graph(B, nodes):
    r"""Newman's weighted projection of B onto one of its node sets.

    The collaboration weighted projection is the projection of the
    bipartite network B onto the specified nodes with weights assigned
    using Newman's collaboration model [1]_:

    .. math::

        w_{u, v} = \sum_k \frac{\delta_{u}^{k} \delta_{v}^{k}}{d_k - 1}

    where `u` and `v` are nodes from the bottom bipartite node set,
    and `k` is a node of the top node set.
    The value `d_k` is the degree of node `k` in the bipartite
    network and `\delta_{u}^{k}` is 1 if node `u` is
    linked to node `k` in the original bipartite graph or 0 otherwise.

    The nodes retain their attributes and are connected in the resulting
    graph if have an edge to a common node in the original bipartite
    graph.

    Parameters
    ----------
    B : NetworkX graph
      The input graph should be bipartite.

    nodes : list or iterable
      Nodes to project onto (the "bottom" nodes).

    Returns
    -------
    Graph : NetworkX graph
       A graph that is the projection onto the given nodes.

    Examples
    --------
    >>> from networkx.algorithms import bipartite
    >>> B = nx.path_graph(5)
    >>> B.add_edge(1, 5)
    >>> G = bipartite.collaboration_weighted_projected_graph(B, [0, 2, 4, 5])
    >>> list(G)
    [0, 2, 4, 5]
    >>> for edge in sorted(G.edges(data=True)):
    ...     print(edge)
    (0, 2, {'weight': 0.5})
    (0, 5, {'weight': 0.5})
    (2, 4, {'weight': 1.0})
    (2, 5, {'weight': 0.5})

    Notes
    -----
    No attempt is made to verify that the input graph B is bipartite.
    The graph and node properties are (shallow) copied to the projected graph.

    See :mod:`bipartite documentation <networkx.algorithms.bipartite>`
    for further details on how bipartite graphs are handled in NetworkX.

    See Also
    --------
    is_bipartite,
    is_bipartite_node_set,
    sets,
    weighted_projected_graph,
    overlap_weighted_projected_graph,
    generic_weighted_projected_graph,
    projected_graph

    References
    ----------
    .. [1] Scientific collaboration networks: II.
        Shortest paths, weighted networks, and centrality,
        M. E. J. Newman, Phys. Rev. E 64, 016132 (2001).
    """
    if B.is_directed():
        pred = B.pred
        G = nx.DiGraph()
    else:
        pred = B.adj
        G = nx.Graph()
    G.graph.update(B.graph)
    G.add_nodes_from((n, B.nodes[n]) for n in nodes)
    for u in nodes:
        unbrs = set(B[u])
        nbrs2 = {n for nbr in unbrs for n in B[nbr] if n != u}
        for v in nbrs2:
            vnbrs = set(pred[v])
            common_degree = (len(B[n]) for n in unbrs & vnbrs)
            weight = sum(1.0 / (deg - 1) for deg in common_degree if deg > 1)
            G.add_edge(u, v, weight=weight)
    return G


@not_implemented_for("multigraph")
@nx._dispatchable(graphs="B", returns_graph=True)
def overlap_weighted_projected_graph(B, nodes, jaccard=True):
    r"""Overlap weighted projection of B onto one of its node sets.

    The overlap weighted projection is the projection of the bipartite
    network B onto the specified nodes with weights representing
    the Jaccard index between the neighborhoods of the two nodes in the
    original bipartite network [1]_:

    .. math::

        w_{v, u} = \frac{|N(u) \cap N(v)|}{|N(u) \cup N(v)|}

    or if the parameter 'jaccard' is False, the fraction of common
    neighbors by minimum of both nodes degree in the original
    bipartite graph [1]_:

    .. math::

        w_{v, u} = \frac{|N(u) \cap N(v)|}{min(|N(u)|, |N(v)|)}

    The nodes retain their attributes and are connected in the resulting
    graph if have an edge to a common node in the original bipartite graph.

    Parameters
    ----------
    B : NetworkX graph
        The input graph should be bipartite.

    nodes : list or iterable
        Nodes to project onto (the "bottom" nodes).

    jaccard: Bool (default=True)

    Returns
    -------
    Graph : NetworkX graph
       A graph that is the projection onto the given nodes.

    Examples
    --------
    >>> from networkx.algorithms import bipartite
    >>> B = nx.path_graph(5)
    >>> nodes = [0, 2, 4]
    >>> G = bipartite.overlap_weighted_projected_graph(B, nodes)
    >>> list(G)
    [0, 2, 4]
    >>> list(G.edges(data=True))
    [(0, 2, {'weight': 0.5}), (2, 4, {'weight': 0.5})]
    >>> G = bipartite.overlap_weighted_projected_graph(B, nodes, jaccard=False)
    >>> list(G.edges(data=True))
    [(0, 2, {'weight': 1.0}), (2, 4, {'weight': 1.0})]

    Notes
    -----
    No attempt is made to verify that the input graph B is bipartite.
    The graph and node properties are (shallow) copied to the projected graph.

    See :mod:`bipartite documentation <networkx.algorithms.bipartite>`
    for further details on how bipartite graphs are handled in NetworkX.

    See Also
    --------
    is_bipartite,
    is_bipartite_node_set,
    sets,
    weighted_projected_graph,
    collaboration_weighted_projected_graph,
    generic_weighted_projected_graph,
    projected_graph

    References
    ----------
    .. [1] Borgatti, S.P. and Halgin, D. In press. Analyzing Affiliation
        Networks. In Carrington, P. and Scott, J. (eds) The Sage Handbook
        of Social Network Analysis. Sage Publications.

    """
    if B.is_directed():
        pred = B.pred
        G = nx.DiGraph()
    else:
        pred = B.adj
        G = nx.Graph()
    G.graph.update(B.graph)
    G.add_nodes_from((n, B.nodes[n]) for n in nodes)
    for u in nodes:
        unbrs = set(B[u])
        nbrs2 = {n for nbr in unbrs for n in B[nbr]} - {u}
        for v in nbrs2:
            vnbrs = set(pred[v])
            if jaccard:
                wt = len(unbrs & vnbrs) / len(unbrs | vnbrs)
            else:
                wt = len(unbrs & vnbrs) / min(len(unbrs), len(vnbrs))
            G.add_edge(u, v, weight=wt)
    return G


@not_implemented_for("multigraph")
@nx._dispatchable(graphs="B", preserve_all_attrs=True, returns_graph=True)
def generic_weighted_projected_graph(B, nodes, weight_function=None):
    r"""Weighted projection of B with a user-specified weight function.

    The bipartite network B is projected on to the specified nodes
    with weights computed by a user-specified function.  This function
    must accept as a parameter the neighborhood sets of two nodes and
    return an integer or a float.

    The nodes retain their attributes and are connected in the resulting graph
    if they have an edge to a common node in the original graph.

    Parameters
    ----------
    B : NetworkX graph
        The input graph should be bipartite.

    nodes : list or iterable
        Nodes to project onto (the "bottom" nodes).

    weight_function : function
        This function must accept as parameters the same input graph
        that this function, and two nodes; and return an integer or a float.
        The default function computes the number of shared neighbors.

    Returns
    -------
    Graph : NetworkX graph
       A graph that is the projection onto the given nodes.

    Examples
    --------
    >>> from networkx.algorithms import bipartite
    >>> # Define some custom weight functions
    >>> def jaccard(G, u, v):
    ...     unbrs = set(G[u])
    ...     vnbrs = set(G[v])
    ...     return float(len(unbrs & vnbrs)) / len(unbrs | vnbrs)
    >>> def my_weight(G, u, v, weight="weight"):
    ...     w = 0
    ...     for nbr in set(G[u]) & set(G[v]):
    ...         w += G[u][nbr].get(weight, 1) + G[v][nbr].get(weight, 1)
    ...     return w
    >>> # A complete bipartite graph with 4 nodes and 4 edges
    >>> B = nx.complete_bipartite_graph(2, 2)
    >>> # Add some arbitrary weight to the edges
    >>> for i, (u, v) in enumerate(B.edges()):
    ...     B.edges[u, v]["weight"] = i + 1
    >>> for edge in B.edges(data=True):
    ...     print(edge)
    (0, 2, {'weight': 1})
    (0, 3, {'weight': 2})
    (1, 2, {'weight': 3})
    (1, 3, {'weight': 4})
    >>> # By default, the weight is the number of shared neighbors
    >>> G = bipartite.generic_weighted_projected_graph(B, [0, 1])
    >>> print(list(G.edges(data=True)))
    [(0, 1, {'weight': 2})]
    >>> # To specify a custom weight function use the weight_function parameter
    >>> G = bipartite.generic_weighted_projected_graph(
    ...     B, [0, 1], weight_function=jaccard
    ... )
    >>> print(list(G.edges(data=True)))
    [(0, 1, {'weight': 1.0})]
    >>> G = bipartite.generic_weighted_projected_graph(
    ...     B, [0, 1], weight_function=my_weight
    ... )
    >>> print(list(G.edges(data=True)))
    [(0, 1, {'weight': 10})]

    Notes
    -----
    No attempt is made to verify that the input graph B is bipartite.
    The graph and node properties are (shallow) copied to the projected graph.

    See :mod:`bipartite documentation <networkx.algorithms.bipartite>`
    for further details on how bipartite graphs are handled in NetworkX.

    See Also
    --------
    is_bipartite,
    is_bipartite_node_set,
    sets,
    weighted_projected_graph,
    collaboration_weighted_projected_graph,
    overlap_weighted_projected_graph,
    projected_graph

    """
    if B.is_directed():
        pred = B.pred
        G = nx.DiGraph()
    else:
        pred = B.adj
        G = nx.Graph()
    if weight_function is None:

        def weight_function(G, u, v):
            # Notice that we use set(pred[v]) for handling the directed case.
            return len(set(G[u]) & set(pred[v]))

    G.graph.update(B.graph)
    G.add_nodes_from((n, B.nodes[n]) for n in nodes)
    for u in nodes:
        nbrs2 = {n for nbr in set(B[u]) for n in B[nbr]} - {u}
        for v in nbrs2:
            weight = weight_function(B, u, v)
            G.add_edge(u, v, weight=weight)
    return G
