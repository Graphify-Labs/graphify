"""
Flow based cut algorithms
"""

import itertools

import networkx as nx

# Define the default maximum flow function to use in all flow based
# cut algorithms.
from networkx.algorithms.flow import build_residual_network, edmonds_karp

default_flow_func = edmonds_karp

from .utils import build_auxiliary_edge_connectivity, build_auxiliary_node_connectivity

__all__ = [
    "minimum_st_node_cut",
    "minimum_node_cut",
    "minimum_st_edge_cut",
    "minimum_edge_cut",
]


@nx._dispatchable(
    graphs={"G": 0, "auxiliary?": 4},
    preserve_edge_attrs={"auxiliary": {"capacity": float("inf")}},
    preserve_graph_attrs={"auxiliary"},
)
def minimum_st_edge_cut(G, s, t, flow_func=None, auxiliary=None, residual=None):
    """Returns the edges of the cut-set of a minimum (s, t)-cut.

    This function returns the set of edges of minimum cardinality that,
    if removed, would destroy all paths among source and target in G.
    Edge weights are not considered. See :meth:`minimum_cut` for
    computing minimum cuts considering edge weights.

    Parameters
    ----------
    G : NetworkX graph

    s : node
        Source node for the flow.

    t : node
        Sink node for the flow.

    auxiliary : NetworkX DiGraph
        Auxiliary digraph to compute flow based node connectivity. It has
        to have a graph attribute called mapping with a dictionary mapping
        node names in G and in the auxiliary digraph. If provided
        it will be reused instead of recreated. Default value: None.

    flow_func : function
        A function for computing the maximum flow among a pair of nodes.
        The function has to accept at least three parameters: a Digraph,
        a source node, and a target node. And return a residual network
        that follows NetworkX conventions (see :meth:`maximum_flow` for
        details). If flow_func is None, the default maximum flow function
        (:meth:`edmonds_karp`) is used. See :meth:`node_connectivity` for
        details. The choice of the default function may change from version
        to version and should not be relied on. Default value: None.

    residual : NetworkX DiGraph
        Residual network to compute maximum flow. If provided it will be
        reused instead of recreated. Default value: None.

    Returns
    -------
    cutset : set
        Set of edges that, if removed from the graph, will disconnect it.

    See also
    --------
    :meth:`minimum_cut`
    :meth:`minimum_node_cut`
    :meth:`minimum_edge_cut`
    :meth:`stoer_wagner`
    :meth:`node_connectivity`
    :meth:`edge_connectivity`
    :meth:`maximum_flow`
    :meth:`edmonds_karp`
    :meth:`preflow_push`
    :meth:`shortest_augmenting_path`

    Examples
    --------
    This function is not imported in the base NetworkX namespace, so you
    have to explicitly import it from the connectivity package:

    >>> from networkx.algorithms.connectivity import minimum_st_edge_cut

    We use in this example the platonic icosahedral graph, which has edge
    connectivity 5.

    >>> G = nx.icosahedral_graph()
    >>> len(minimum_st_edge_cut(G, 0, 6))
    5

    If you need to compute local edge cuts on several pairs of
    nodes in the same graph, it is recommended that you reuse the
    data structures that NetworkX uses in the computation: the
    auxiliary digraph for edge connectivity, and the residual
    network for the underlying maximum flow computation.

    Example of how to compute local edge cuts among all pairs of
    nodes of the platonic icosahedral graph reusing the data
    structures.

    >>> import itertools
    >>> # You also have to explicitly import the function for
    >>> # building the auxiliary digraph from the connectivity package
    >>> from networkx.algorithms.connectivity import build_auxiliary_edge_connectivity
    >>> H = build_auxiliary_edge_connectivity(G)
    >>> # And the function for building the residual network from the
    >>> # flow package
    >>> from networkx.algorithms.flow import build_residual_network
    >>> # Note that the auxiliary digraph has an edge attribute named capacity
    >>> R = build_residual_network(H, "capacity")
    >>> result = dict.fromkeys(G, dict())
    >>> # Reuse the auxiliary digraph and the residual network by passing them
    >>> # as parameters
    >>> for u, v in itertools.combinations(G, 2):
    ...     k = len(minimum_st_edge_cut(G, u, v, auxiliary=H, residual=R))
    ...     result[u][v] = k
    >>> all(result[u][v] == 5 for u, v in itertools.combinations(G, 2))
    True

    You can also use alternative flow algorithms for computing edge
    cuts. For instance, in dense networks the algorithm
    :meth:`shortest_augmenting_path` will usually perform better than
    the default :meth:`edmonds_karp` which is faster for sparse
    networks with highly skewed degree distributions. Alternative flow
    functions have to be explicitly imported from the flow package.

    >>> from networkx.algorithms.flow import shortest_augmenting_path
    >>> len(minimum_st_edge_cut(G, 0, 6, flow_func=shortest_augmenting_path))
    5

    """
    if flow_func is None:
        flow_func = default_flow_func

    if auxiliary is None:
        H = build_auxiliary_edge_connectivity(G)
    else:
        H = auxiliary

    kwargs = {"capacity": "capacity", "flow_func": flow_func, "residual": residual}

    cut_value, partition = nx.minimum_cut(H, s, t, **kwargs)
    reachable, non_reachable = partition
    # Any edge in the original graph linking the two sets in the
    # partition is part of the edge cutset
    cutset = set()
    for u, nbrs in ((n, G[n]) for n in reachable):
        cutset.update((u, v) for v in nbrs if v in non_reachable)

    return cutset


@nx._dispatchable(
    graphs={"G": 0, "auxiliary?": 4},
    preserve_node_attrs={"auxiliary": {"id": None}},
    preserve_graph_attrs={"auxiliary"},
)
def minimum_st_node_cut(G, s, t, flow_func=None, auxiliary=None, residual=None):
    r"""Returns a set of nodes of minimum cardinality that disconnect source
    from target in G.

    This function returns the set of nodes of minimum cardinality that,
    if removed, would destroy all paths among source and target in G.

    Parameters
    ----------
    G : NetworkX graph

    s : node
        Source node.

    t : node
        Target node.

    flow_func : function
        A function for computing the maximum flow among a pair of nodes.
        The function has to accept at least three parameters: a Digraph,
        a source node, and a target node. And return a residual network
        that follows NetworkX conventions (see :meth:`maximum_flow` for
        details). If flow_func is None, the default maximum flow function
        (:meth:`edmonds_karp`) is used. See below for details. The choice
        of the default function may change from version to version and
        should not be relied on. Default value: None.

    auxiliary : NetworkX DiGraph
        Auxiliary digraph to compute flow based node connectivity. It has
        to have a graph attribute called mapping with a dictionary mapping
        node names in G and in the auxiliary digraph. If provided
        it will be reused instead of recreated. Default value: None.

    residual : NetworkX DiGraph
        Residual network to compute maximum flow. If provided it will be
        reused instead of recreated. Default value: None.

    Returns
    -------
    cutset : set
        Set of nodes that, if removed, would destroy all paths between
        source and target in G.

    Examples
    --------
    This function is not imported in the base NetworkX namespace, so you
    have to explicitly import it from the connectivity package:

    >>> from networkx.algorithms.connectivity import minimum_st_node_cut

    We use in this example the platonic icosahedral graph, which has node
    connectivity 5.

    >>> G = nx.icosahedral_graph()
    >>> len(minimum_st_node_cut(G, 0, 6))
    5

    If you need to compute local st cuts between several pairs of
    nodes in the same graph, it is recommended that you reuse the
    data structures that NetworkX uses in the computation: the
    auxiliary digraph for node connectivity and node cuts, and the
    residual network for the underlying maximum flow computation.

    Example of how to compute local st node cuts reusing the data
    structures:

    >>> # You also have to explicitly import the function for
    >>> # building the auxiliary digraph from the connectivity package
    >>> from networkx.algorithms.connectivity import build_auxiliary_node_connectivity
    >>> H = build_auxiliary_node_connectivity(G)
    >>> # And the function for building the residual network from the
    >>> # flow package
    >>> from networkx.algorithms.flow import build_residual_network
    >>> # Note that the auxiliary digraph has an edge attribute named capacity
    >>> R = build_residual_network(H, "capacity")
    >>> # Reuse the auxiliary digraph and the residual network by passing them
    >>> # as parameters
    >>> len(minimum_st_node_cut(G, 0, 6, auxiliary=H, residual=R))
    5

    You can also use alternative flow algorithms for computing minimum st
    node cuts. For instance, in dense networks the algorithm
    :meth:`shortest_augmenting_path` will usually perform better than
    the default :meth:`edmonds_karp` which is faster for sparse
    networks with highly skewed degree distributions. Alternative flow
    functions have to be explicitly imported from the flow package.

    >>> from networkx.algorithms.flow import shortest_augmenting_path
    >>> len(minimum_st_node_cut(G, 0, 6, flow_func=shortest_augmenting_path))
    5

    Notes
    -----
    This is a flow based implementation of minimum node cut. The algorithm
    is based in solving a number of maximum flow computations to determine
    the capacity of the minimum cut on an auxiliary directed network that
    corresponds to the minimum node cut of G. It handles both directed
    and undirected graphs. This implementation is based on algorithm 11
    in [1]_.

    See also
    --------
    :meth:`minimum_node_cut`
    :meth:`minimum_edge_cut`
    :meth:`stoer_wagner`
    :meth:`node_connectivity`
    :meth:`edge_connectivity`
    :meth:`maximum_flow`
    :meth:`edmonds_karp`
    :meth:`preflow_push`
    :meth:`shortest_augmenting_path`

    References
    ----------
    .. [1] Abdol-Hossein Esfahanian. Connectivity Algorithms.
        http://www.cse.msu.edu/~cse835/Papers/Graph_connectivity_revised.pdf

    """
    if auxiliary is None:
        H = build_auxiliary_node_connectivity(G)
    else:
        H = auxiliary

    mapping = H.graph.get("mapping", None)
    if mapping is None:
        raise nx.NetworkXError("Invalid auxiliary digraph.")
    if G.has_edge(s, t) or G.has_edge(t, s):
        return {}
    kwargs = {"flow_func": flow_func, "residual": residual, "auxiliary": H}

    # The edge cut in the auxiliary digraph corresponds to the node cut in the
    # original graph.
    edge_cut = minimum_st_edge_cut(H, f"{mapping[s]}B", f"{mapping[t]}A", **kwargs)
    # Each node in the original graph maps to two nodes of the auxiliary graph
    node_cut = {H.nodes[node]["id"] for edge in edge_cut for node in edge}
    return node_cut - {s, t}


@nx._dispatchable
def minimum_node_cut(G, s=None, t=None, flow_func=None):
    r"""Returns a set of nodes of minimum cardinality that disconnects G.

    If source and target nodes are provided, this function returns the
    set of nodes of minimum cardinality that, if removed, would destroy
    all paths among source and target in G. If not, it returns a set
    of nodes of minimum cardinality that disconnects G.

    Parameters
    ----------
    G : NetworkX graph

    s : node
        Source node. Optional. Default value: None.

    t : node
        Target node. Optional. Default value: None.

    flow_func : function
        A function for computing the maximum flow among a pair of nodes.
        The function has to accept at least three parameters: a Digraph,
        a source node, and a target node. And return a residual network
        that follows NetworkX conventions (see :meth:`maximum_flow` for
        details). If flow_func is None, the default maximum flow function
        (:meth:`edmonds_karp`) is used. See below for details. The
        choice of the default function may change from version
        to version and should not be relied on. Default value: None.

    Returns
    -------
    cutset : set
        Set of nodes that, if removed, would disconnect G. If source
        and target nodes are provided, the set contains the nodes that
        if removed, would destroy all paths between source and target.

    Examples
    --------
    >>> # Platonic icosahedral graph has node connectivity 5
    >>> G = nx.icosahedral_graph()
    >>> node_cut = nx.minimum_node_cut(G)
    >>> len(node_cut)
    5

    You can use alternative flow algorithms for the underlying maximum
    flow computation. In dense networks the algorithm
    :meth:`shortest_augmenting_path` will usually perform better
    than the default :meth:`edmonds_karp`, which is faster for
    sparse networks with highly skewed degree distributions. Alternative
    flow functions have to be explicitly imported from the flow package.

    >>> from networkx.algorithms.flow import shortest_augmenting_path
    >>> node_cut == nx.minimum_node_cut(G, flow_func=shortest_augmenting_path)
    True

    If you specify a pair of nodes (source and target) as parameters,
    this function returns a local st node cut.

    >>> len(nx.minimum_node_cut(G, 3, 7))
    5

    If you need to perform several local st cuts among different
    pairs of nodes on the same graph, it is recommended that you reuse
    the data structures used in the maximum flow computations. See
    :meth:`minimum_st_node_cut` for details.

    Notes
    -----
    This is a flow based implementation of minimum node cut. The algorithm
    is based in solving a number of maximum flow computations to determine
    the capacity of the minimum cut on an auxiliary directed network that
    corresponds to the minimum node cut of G. It handles both directed
    and undirected graphs. This implementation is based on algorithm 11
    in [1]_.

    See also
    --------
    :meth:`minimum_st_node_cut`
    :meth:`minimum_cut`
    :meth:`minimum_edge_cut`
    :meth:`stoer_wagner`
    :meth:`node_connectivity`
    :meth:`edge_connectivity`
    :meth:`maximum_flow`
    :meth:`edmonds_karp`
    :meth:`preflow_push`
    :meth:`shortest_augmenting_path`

    References
    ----------
    .. [1] Abdol-Hossein Esfahanian. Connectivity Algorithms.
        http://www.cse.msu.edu/~cse835/Papers/Graph_connectivity_revised.pdf

    """
    if (s is not None and t is None) or (s is None and t is not None):
        raise nx.NetworkXError("Both source and target must be specified.")

    # Local minimum node cut.
    if s is not None and t is not None:
        if s not in G:
            raise nx.NetworkXError(f"node {s} not in graph")
        if t not in G:
            raise nx.NetworkXError(f"node {t} not in graph")
        return minimum_st_node_cut(G, s, t, flow_func=flow_func)

    # Global minimum node cut.
    # Analog to the algorithm 11 for global node connectivity in [1].
    if G.is_directed():
        if not nx.is_weakly_connected(G):
            raise nx.NetworkXError("Input graph is not connected")
        iter_func = itertools.permutations

        def neighbors(v):
            return itertools.chain.from_iterable([G.predecessors(v), G.successors(v)])

    else:
        if not nx.is_connected(G):
            raise nx.NetworkXError("Input graph is not connected")
        iter_func = itertools.combinations
        neighbors = G.neighbors

    # Reuse the auxiliary digraph and the residual network.
    H = build_auxiliary_node_connectivity(G)
    R = build_residual_network(H, "capacity")
    kwargs = {"flow_func": flow_func, "auxiliary": H, "residual": R}

    # Choose a node with minimum degree.
    v = min(G, key=G.degree)
    # Initial node cutset is all neighbors of the node with minimum degree.
    min_cut = set(G[v])
    # Compute st node cuts between v and all its non-neighbors nodes in G.
    for w in set(G) - set(neighbors(v)) - {v}:
        this_cut = minimum_st_node_cut(G, v, w, **kwargs)
        if len(min_cut) >= len(this_cut):
            min_cut = this_cut
    # Also for non adjacent pairs of neighbors of v.
    for x, y in iter_func(neighbors(v), 2):
        if y in G[x]:
            continue
        this_cut = minimum_st_node_cut(G, x, y, **kwargs)
        if len(min_cut) >= len(this_cut):
            min_cut = this_cut

    return min_cut


@nx._dispatchable
def minimum_edge_cut(G, s=None, t=None, flow_func=None):
    r"""Returns a set of edges of minimum cardinality that disconnects G.

    If source and target nodes are provided, this function returns the
    set of edges of minimum cardinality that, if removed, would break
    all paths among source and target in G. If not, it returns a set of
    edges of minimum cardinality that disconnects G.

    Parameters
    ----------
    G : NetworkX graph

    s : node
        Source node. Optional. Default value: None.

    t : node
        Target node. Optional. Default value: None.

    flow_func : function
        A function for computing the maximum flow among a pair of nodes.
        The function has to accept at least three parameters: a Digraph,
        a source node, and a target node. And return a residual network
        that follows NetworkX conventions (see :meth:`maximum_flow` for
        details). If flow_func is None, the default maximum flow function
        (:meth:`edmonds_karp`) is used. See below for details. The
        choice of the default function may change from version
        to version and should not be relied on. Default value: None.

    Returns
    -------
    cutset : set
        Set of edges that, if removed, would disconnect G. If source
        and target nodes are provided, the set contains the edges that
        if removed, would destroy all paths between source and target.

    Examples
    --------
    >>> # Platonic icosahedral graph has edge connectivity 5
    >>> G = nx.icosahedral_graph()
    >>> len(nx.minimum_edge_cut(G))
    5

    You can use alternative flow algorithms for the underlying
    maximum flow computation. In dense networks the algorithm
    :meth:`shortest_augmenting_path` will usually perform better
    than the default :meth:`edmonds_karp`, which is faster for
    sparse networks with highly skewed degree distributions.
    Alternative flow functions have to be explicitly imported
    from the flow package.

    >>> from networkx.algorithms.flow import shortest_augmenting_path
    >>> len(nx.minimum_edge_cut(G, flow_func=shortest_augmenting_path))
    5

    If you specify a pair of nodes (source and target) as parameters,
    this function returns the value of local edge connectivity.

    >>> nx.edge_connectivity(G, 3, 7)
    5

    If you need to perform several local computations among different
    pairs of nodes on the same graph, it is recommended that you reuse
    the data structures used in the maximum flow computations. See
    :meth:`local_edge_connectivity` for details.

    Notes
    -----
    This is a flow based implementation of minimum edge cut. For
    undirected graphs the algorithm works by finding a 'small' dominating
    set of nodes of G (see algorithm 7 in [1]_) and computing the maximum
    flow between an arbitrary node in the dominating set and the rest of
    nodes in it. This is an implementation of algorithm 6 in [1]_. For
    directed graphs, the algorithm does n calls to the max flow function.
    The function raises an error if the directed graph is not weakly
    connected and returns an empty set if it is weakly connected.
    It is an implementation of algorithm 8 in [1]_.

    See also
    --------
    :meth:`minimum_st_edge_cut`
    :meth:`minimum_node_cut`
    :meth:`stoer_wagner`
    :meth:`node_connectivity`
    :meth:`edge_connectivity`
    :meth:`maximum_flow`
    :meth:`edmonds_karp`
    :meth:`preflow_push`
    :meth:`shortest_augmenting_path`

    References
    ----------
    .. [1] Abdol-Hossein Esfahanian. Connectivity Algorithms.
        http://www.cse.msu.edu/~cse835/Papers/Graph_connectivity_revised.pdf

    """
    if (s is not None and t is None) or (s is None and t is not None):
        raise nx.NetworkXError("Both source and target must be specified.")

    # reuse auxiliary digraph and residual network
    H = build_auxiliary_edge_connectivity(G)
    R = build_residual_network(H, "capacity")
    kwargs = {"flow_func": flow_func, "residual": R, "auxiliary": H}

    # Local minimum edge cut if s and t are not None
    if s is not None and t is not None:
        if s not in G:
            raise nx.NetworkXError(f"node {s} not in graph")
        if t not in G:
            raise nx.NetworkXError(f"node {t} not in graph")
        return minimum_st_edge_cut(H, s, t, **kwargs)

    # Global minimum edge cut
    # Analog to the algorithm for global edge connectivity
    if G.is_directed():
        # Based on algorithm 8 in [1]
        if not nx.is_weakly_connected(G):
            raise nx.NetworkXError("Input graph is not connected")

        # Initial cutset is all edges of a node with minimum degree
        node = min(G, key=G.degree)
        min_cut = set(G.edges(node))
        nodes = list(G)
        n = len(nodes)
        for i in range(n):
            try:
                this_cut = minimum_st_edge_cut(H, nodes[i], nodes[i + 1], **kwargs)
                if len(this_cut) <= len(min_cut):
                    min_cut = this_cut
            except IndexError:  # Last node!
                this_cut = minimum_st_edge_cut(H, nodes[i], nodes[0], **kwargs)
                if len(this_cut) <= len(min_cut):
                    min_cut = this_cut

        return min_cut

    else:  # undirected
        # Based on algorithm 6 in [1]
        if not nx.is_connected(G):
            raise nx.NetworkXError("Input graph is not connected")

        # Initial cutset is all edges of a node with minimum degree
        node = min(G, key=G.degree)
        min_cut = set(G.edges(node))
        # A dominating set is \lambda-covering
        # We need a dominating set with at least two nodes
        for node in G:
            D = nx.dominating_set(G, start_with=node)
            v = D.pop()
            if D:
                break
        else:
            # in complete graphs the dominating set will always be of one node
            # thus we return min_cut, which now contains the edges of a node
            # with minimum degree
            return min_cut
        for w in D:
            this_cut = minimum_st_edge_cut(H, v, w, **kwargs)
            if len(this_cut) <= len(min_cut):
                min_cut = this_cut

        return min_cut
