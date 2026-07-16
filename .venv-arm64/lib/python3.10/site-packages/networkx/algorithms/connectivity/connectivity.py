"""
Flow based connectivity algorithms
"""

import itertools
from operator import itemgetter

import networkx as nx

# Define the default maximum flow function to use in all flow based
# connectivity algorithms.
from networkx.algorithms.flow import (
    boykov_kolmogorov,
    build_residual_network,
    dinitz,
    edmonds_karp,
    preflow_push,
    shortest_augmenting_path,
)

default_flow_func = edmonds_karp

from .utils import build_auxiliary_edge_connectivity, build_auxiliary_node_connectivity

__all__ = [
    "average_node_connectivity",
    "local_node_connectivity",
    "node_connectivity",
    "local_edge_connectivity",
    "edge_connectivity",
    "all_pairs_node_connectivity",
]


@nx._dispatchable(graphs={"G": 0, "auxiliary?": 4}, preserve_graph_attrs={"auxiliary"})
def local_node_connectivity(
    G, s, t, flow_func=None, auxiliary=None, residual=None, cutoff=None
):
    r"""Computes local node connectivity for nodes s and t.

    Local node connectivity for two non adjacent nodes s and t is the
    minimum number of nodes that must be removed (along with their incident
    edges) to disconnect them.

    This is a flow based implementation of node connectivity. We compute the
    maximum flow on an auxiliary digraph build from the original input
    graph (see below for details).

    Parameters
    ----------
    G : NetworkX graph
        Undirected graph

    s : node
        Source node

    t : node
        Target node

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

    cutoff : integer, float, or None (default: None)
        If specified, the maximum flow algorithm will terminate when the
        flow value reaches or exceeds the cutoff. This only works for flows
        that support the cutoff parameter (most do) and is ignored otherwise.

    Returns
    -------
    K : integer
        local node connectivity for nodes s and t

    Examples
    --------
    This function is not imported in the base NetworkX namespace, so you
    have to explicitly import it from the connectivity package:

    >>> from networkx.algorithms.connectivity import local_node_connectivity

    We use in this example the platonic icosahedral graph, which has node
    connectivity 5.

    >>> G = nx.icosahedral_graph()
    >>> local_node_connectivity(G, 0, 6)
    5

    If you need to compute local connectivity on several pairs of
    nodes in the same graph, it is recommended that you reuse the
    data structures that NetworkX uses in the computation: the
    auxiliary digraph for node connectivity, and the residual
    network for the underlying maximum flow computation.

    Example of how to compute local node connectivity among
    all pairs of nodes of the platonic icosahedral graph reusing
    the data structures.

    >>> import itertools
    >>> # You also have to explicitly import the function for
    >>> # building the auxiliary digraph from the connectivity package
    >>> from networkx.algorithms.connectivity import build_auxiliary_node_connectivity
    >>> H = build_auxiliary_node_connectivity(G)
    >>> # And the function for building the residual network from the
    >>> # flow package
    >>> from networkx.algorithms.flow import build_residual_network
    >>> # Note that the auxiliary digraph has an edge attribute named capacity
    >>> R = build_residual_network(H, "capacity")
    >>> result = dict.fromkeys(G, dict())
    >>> # Reuse the auxiliary digraph and the residual network by passing them
    >>> # as parameters
    >>> for u, v in itertools.combinations(G, 2):
    ...     k = local_node_connectivity(G, u, v, auxiliary=H, residual=R)
    ...     result[u][v] = k
    >>> all(result[u][v] == 5 for u, v in itertools.combinations(G, 2))
    True

    You can also use alternative flow algorithms for computing node
    connectivity. For instance, in dense networks the algorithm
    :meth:`shortest_augmenting_path` will usually perform better than
    the default :meth:`edmonds_karp` which is faster for sparse
    networks with highly skewed degree distributions. Alternative flow
    functions have to be explicitly imported from the flow package.

    >>> from networkx.algorithms.flow import shortest_augmenting_path
    >>> local_node_connectivity(G, 0, 6, flow_func=shortest_augmenting_path)
    5

    Notes
    -----
    This is a flow based implementation of node connectivity. We compute the
    maximum flow using, by default, the :meth:`edmonds_karp` algorithm (see:
    :meth:`maximum_flow`) on an auxiliary digraph build from the original
    input graph:

    For an undirected graph G having `n` nodes and `m` edges we derive a
    directed graph H with `2n` nodes and `2m+n` arcs by replacing each
    original node `v` with two nodes `v_A`, `v_B` linked by an (internal)
    arc in H. Then for each edge (`u`, `v`) in G we add two arcs
    (`u_B`, `v_A`) and (`v_B`, `u_A`) in H. Finally we set the attribute
    capacity = 1 for each arc in H [1]_ .

    For a directed graph G having `n` nodes and `m` arcs we derive a
    directed graph H with `2n` nodes and `m+n` arcs by replacing each
    original node `v` with two nodes `v_A`, `v_B` linked by an (internal)
    arc (`v_A`, `v_B`) in H. Then for each arc (`u`, `v`) in G we add one arc
    (`u_B`, `v_A`) in H. Finally we set the attribute capacity = 1 for
    each arc in H.

    This is equal to the local node connectivity because the value of
    a maximum s-t-flow is equal to the capacity of a minimum s-t-cut.

    See also
    --------
    :meth:`local_edge_connectivity`
    :meth:`node_connectivity`
    :meth:`minimum_node_cut`
    :meth:`maximum_flow`
    :meth:`edmonds_karp`
    :meth:`preflow_push`
    :meth:`shortest_augmenting_path`

    References
    ----------
    .. [1] Kammer, Frank and Hanjo Taubig. Graph Connectivity. in Brandes and
        Erlebach, 'Network Analysis: Methodological Foundations', Lecture
        Notes in Computer Science, Volume 3418, Springer-Verlag, 2005.
        http://www.informatik.uni-augsburg.de/thi/personen/kammer/Graph_Connectivity.pdf

    """
    if flow_func is None:
        flow_func = default_flow_func

    if auxiliary is None:
        H = build_auxiliary_node_connectivity(G)
    else:
        H = auxiliary

    mapping = H.graph.get("mapping", None)
    if mapping is None:
        raise nx.NetworkXError("Invalid auxiliary digraph.")

    kwargs = {"flow_func": flow_func, "residual": residual}

    if flow_func is not preflow_push:
        kwargs["cutoff"] = cutoff

    if flow_func is shortest_augmenting_path:
        kwargs["two_phase"] = True

    return nx.maximum_flow_value(H, f"{mapping[s]}B", f"{mapping[t]}A", **kwargs)


@nx._dispatchable
def node_connectivity(G, s=None, t=None, flow_func=None):
    r"""Returns node connectivity for a graph or digraph G.

    Node connectivity is equal to the minimum number of nodes that
    must be removed to disconnect G or render it trivial. If source
    and target nodes are provided, this function returns the local node
    connectivity: the minimum number of nodes that must be removed to break
    all paths from source to target in G.

    Parameters
    ----------
    G : NetworkX graph
        Undirected graph

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
    K : integer
        Node connectivity of G, or local node connectivity if source
        and target are provided.

    Examples
    --------
    >>> # Platonic icosahedral graph is 5-node-connected
    >>> G = nx.icosahedral_graph()
    >>> nx.node_connectivity(G)
    5

    You can use alternative flow algorithms for the underlying maximum
    flow computation. In dense networks the algorithm
    :meth:`shortest_augmenting_path` will usually perform better
    than the default :meth:`edmonds_karp`, which is faster for
    sparse networks with highly skewed degree distributions. Alternative
    flow functions have to be explicitly imported from the flow package.

    >>> from networkx.algorithms.flow import shortest_augmenting_path
    >>> nx.node_connectivity(G, flow_func=shortest_augmenting_path)
    5

    If you specify a pair of nodes (source and target) as parameters,
    this function returns the value of local node connectivity.

    >>> nx.node_connectivity(G, 3, 7)
    5

    If you need to perform several local computations among different
    pairs of nodes on the same graph, it is recommended that you reuse
    the data structures used in the maximum flow computations. See
    :meth:`local_node_connectivity` for details.

    Notes
    -----
    This is a flow based implementation of node connectivity. The
    algorithm works by solving $O((n-\delta-1+\delta(\delta-1)/2))$
    maximum flow problems on an auxiliary digraph. Where $\delta$
    is the minimum degree of G. For details about the auxiliary
    digraph and the computation of local node connectivity see
    :meth:`local_node_connectivity`. This implementation is based
    on algorithm 11 in [1]_.

    See also
    --------
    :meth:`local_node_connectivity`
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

    # Local node connectivity
    if s is not None and t is not None:
        if s not in G:
            raise nx.NetworkXError(f"node {s} not in graph")
        if t not in G:
            raise nx.NetworkXError(f"node {t} not in graph")
        return local_node_connectivity(G, s, t, flow_func=flow_func)

    # Global node connectivity
    if G.is_directed():
        if not nx.is_weakly_connected(G):
            return 0
        iter_func = itertools.permutations
        # It is necessary to consider both predecessors
        # and successors for directed graphs

        def neighbors(v):
            return itertools.chain.from_iterable([G.predecessors(v), G.successors(v)])

    else:
        if not nx.is_connected(G):
            return 0
        iter_func = itertools.combinations
        neighbors = G.neighbors

    # Reuse the auxiliary digraph and the residual network
    H = build_auxiliary_node_connectivity(G)
    R = build_residual_network(H, "capacity")
    kwargs = {"flow_func": flow_func, "auxiliary": H, "residual": R}

    # Pick a node with minimum degree
    # Node connectivity is bounded by degree.
    v, K = min(G.degree(), key=itemgetter(1))
    # compute local node connectivity with all its non-neighbors nodes
    for w in set(G) - set(neighbors(v)) - {v}:
        kwargs["cutoff"] = K
        K = min(K, local_node_connectivity(G, v, w, **kwargs))
    # Also for non adjacent pairs of neighbors of v
    for x, y in iter_func(neighbors(v), 2):
        if y in G[x]:
            continue
        kwargs["cutoff"] = K
        K = min(K, local_node_connectivity(G, x, y, **kwargs))

    return K


@nx._dispatchable
def average_node_connectivity(G, flow_func=None):
    r"""Returns the average connectivity of a graph G.

    The average connectivity `\bar{\kappa}` of a graph G is the average
    of local node connectivity over all pairs of nodes of G [1]_ .

    .. math::

        \bar{\kappa}(G) = \frac{\sum_{u,v} \kappa_{G}(u,v)}{{n \choose 2}}

    Parameters
    ----------

    G : NetworkX graph
        Undirected graph

    flow_func : function
        A function for computing the maximum flow among a pair of nodes.
        The function has to accept at least three parameters: a Digraph,
        a source node, and a target node. And return a residual network
        that follows NetworkX conventions (see :meth:`maximum_flow` for
        details). If flow_func is None, the default maximum flow function
        (:meth:`edmonds_karp`) is used. See :meth:`local_node_connectivity`
        for details. The choice of the default function may change from
        version to version and should not be relied on. Default value: None.

    Returns
    -------
    K : float
        Average node connectivity

    See also
    --------
    :meth:`local_node_connectivity`
    :meth:`node_connectivity`
    :meth:`edge_connectivity`
    :meth:`maximum_flow`
    :meth:`edmonds_karp`
    :meth:`preflow_push`
    :meth:`shortest_augmenting_path`

    References
    ----------
    .. [1]  Beineke, L., O. Oellermann, and R. Pippert (2002). The average
            connectivity of a graph. Discrete mathematics 252(1-3), 31-45.
            http://www.sciencedirect.com/science/article/pii/S0012365X01001807

    """
    if G.is_directed():
        iter_func = itertools.permutations
    else:
        iter_func = itertools.combinations

    # Reuse the auxiliary digraph and the residual network
    H = build_auxiliary_node_connectivity(G)
    R = build_residual_network(H, "capacity")
    kwargs = {"flow_func": flow_func, "auxiliary": H, "residual": R}

    num, den = 0, 0
    for u, v in iter_func(G, 2):
        num += local_node_connectivity(G, u, v, **kwargs)
        den += 1

    if den == 0:  # Null Graph
        return 0
    return num / den


@nx._dispatchable
def all_pairs_node_connectivity(G, nbunch=None, flow_func=None):
    """Compute node connectivity between all pairs of nodes of G.

    Parameters
    ----------
    G : NetworkX graph
        Undirected graph

    nbunch: container
        Container of nodes. If provided node connectivity will be computed
        only over pairs of nodes in nbunch.

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
    all_pairs : dict
        A dictionary with node connectivity between all pairs of nodes
        in G, or in nbunch if provided.

    See also
    --------
    :meth:`local_node_connectivity`
    :meth:`edge_connectivity`
    :meth:`local_edge_connectivity`
    :meth:`maximum_flow`
    :meth:`edmonds_karp`
    :meth:`preflow_push`
    :meth:`shortest_augmenting_path`

    """
    if nbunch is None:
        nbunch = G
    else:
        nbunch = set(nbunch)

    directed = G.is_directed()
    if directed:
        iter_func = itertools.permutations
    else:
        iter_func = itertools.combinations

    all_pairs = {n: {} for n in nbunch}

    # Reuse auxiliary digraph and residual network
    H = build_auxiliary_node_connectivity(G)
    mapping = H.graph["mapping"]
    R = build_residual_network(H, "capacity")
    kwargs = {"flow_func": flow_func, "auxiliary": H, "residual": R}

    for u, v in iter_func(nbunch, 2):
        K = local_node_connectivity(G, u, v, **kwargs)
        all_pairs[u][v] = K
        if not directed:
            all_pairs[v][u] = K

    return all_pairs


@nx._dispatchable(graphs={"G": 0, "auxiliary?": 4})
def local_edge_connectivity(
    G, s, t, flow_func=None, auxiliary=None, residual=None, cutoff=None
):
    r"""Returns local edge connectivity for nodes s and t in G.

    Local edge connectivity for two nodes s and t is the minimum number
    of edges that must be removed to disconnect them.

    This is a flow based implementation of edge connectivity. We compute the
    maximum flow on an auxiliary digraph build from the original
    network (see below for details). This is equal to the local edge
    connectivity because the value of a maximum s-t-flow is equal to the
    capacity of a minimum s-t-cut (Ford and Fulkerson theorem) [1]_ .

    Parameters
    ----------
    G : NetworkX graph
        Undirected or directed graph

    s : node
        Source node

    t : node
        Target node

    flow_func : function
        A function for computing the maximum flow among a pair of nodes.
        The function has to accept at least three parameters: a Digraph,
        a source node, and a target node. And return a residual network
        that follows NetworkX conventions (see :meth:`maximum_flow` for
        details). If flow_func is None, the default maximum flow function
        (:meth:`edmonds_karp`) is used. See below for details. The
        choice of the default function may change from version
        to version and should not be relied on. Default value: None.

    auxiliary : NetworkX DiGraph
        Auxiliary digraph for computing flow based edge connectivity. If
        provided it will be reused instead of recreated. Default value: None.

    residual : NetworkX DiGraph
        Residual network to compute maximum flow. If provided it will be
        reused instead of recreated. Default value: None.

    cutoff : integer, float, or None (default: None)
        If specified, the maximum flow algorithm will terminate when the
        flow value reaches or exceeds the cutoff. This only works for flows
        that support the cutoff parameter (most do) and is ignored otherwise.

    Returns
    -------
    K : integer
        local edge connectivity for nodes s and t.

    Examples
    --------
    This function is not imported in the base NetworkX namespace, so you
    have to explicitly import it from the connectivity package:

    >>> from networkx.algorithms.connectivity import local_edge_connectivity

    We use in this example the platonic icosahedral graph, which has edge
    connectivity 5.

    >>> G = nx.icosahedral_graph()
    >>> local_edge_connectivity(G, 0, 6)
    5

    If you need to compute local connectivity on several pairs of
    nodes in the same graph, it is recommended that you reuse the
    data structures that NetworkX uses in the computation: the
    auxiliary digraph for edge connectivity, and the residual
    network for the underlying maximum flow computation.

    Example of how to compute local edge connectivity among
    all pairs of nodes of the platonic icosahedral graph reusing
    the data structures.

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
    ...     k = local_edge_connectivity(G, u, v, auxiliary=H, residual=R)
    ...     result[u][v] = k
    >>> all(result[u][v] == 5 for u, v in itertools.combinations(G, 2))
    True

    You can also use alternative flow algorithms for computing edge
    connectivity. For instance, in dense networks the algorithm
    :meth:`shortest_augmenting_path` will usually perform better than
    the default :meth:`edmonds_karp` which is faster for sparse
    networks with highly skewed degree distributions. Alternative flow
    functions have to be explicitly imported from the flow package.

    >>> from networkx.algorithms.flow import shortest_augmenting_path
    >>> local_edge_connectivity(G, 0, 6, flow_func=shortest_augmenting_path)
    5

    Notes
    -----
    This is a flow based implementation of edge connectivity. We compute the
    maximum flow using, by default, the :meth:`edmonds_karp` algorithm on an
    auxiliary digraph build from the original input graph:

    If the input graph is undirected, we replace each edge (`u`,`v`) with
    two reciprocal arcs (`u`, `v`) and (`v`, `u`) and then we set the attribute
    'capacity' for each arc to 1. If the input graph is directed we simply
    add the 'capacity' attribute. This is an implementation of algorithm 1
    in [1]_.

    The maximum flow in the auxiliary network is equal to the local edge
    connectivity because the value of a maximum s-t-flow is equal to the
    capacity of a minimum s-t-cut (Ford and Fulkerson theorem).

    See also
    --------
    :meth:`edge_connectivity`
    :meth:`local_node_connectivity`
    :meth:`node_connectivity`
    :meth:`maximum_flow`
    :meth:`edmonds_karp`
    :meth:`preflow_push`
    :meth:`shortest_augmenting_path`

    References
    ----------
    .. [1] Abdol-Hossein Esfahanian. Connectivity Algorithms.
        http://www.cse.msu.edu/~cse835/Papers/Graph_connectivity_revised.pdf

    """
    if flow_func is None:
        flow_func = default_flow_func

    if auxiliary is None:
        H = build_auxiliary_edge_connectivity(G)
    else:
        H = auxiliary

    kwargs = {"flow_func": flow_func, "residual": residual}

    if flow_func is not preflow_push:
        kwargs["cutoff"] = cutoff

    if flow_func is shortest_augmenting_path:
        kwargs["two_phase"] = True

    return nx.maximum_flow_value(H, s, t, **kwargs)


@nx._dispatchable
def edge_connectivity(G, s=None, t=None, flow_func=None, cutoff=None):
    r"""Returns the edge connectivity of the graph or digraph G.

    The edge connectivity is equal to the minimum number of edges that
    must be removed to disconnect G or render it trivial. If source
    and target nodes are provided, this function returns the local edge
    connectivity: the minimum number of edges that must be removed to
    break all paths from source to target in G.

    Parameters
    ----------
    G : NetworkX graph
        Undirected or directed graph

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

    cutoff : integer, float, or None (default: None)
        If specified, the maximum flow algorithm will terminate when the
        flow value reaches or exceeds the cutoff. This only works for flows
        that support the cutoff parameter (most do) and is ignored otherwise.

    Returns
    -------
    K : integer
        Edge connectivity for G, or local edge connectivity if source
        and target were provided

    Examples
    --------
    >>> # Platonic icosahedral graph is 5-edge-connected
    >>> G = nx.icosahedral_graph()
    >>> nx.edge_connectivity(G)
    5

    You can use alternative flow algorithms for the underlying
    maximum flow computation. In dense networks the algorithm
    :meth:`shortest_augmenting_path` will usually perform better
    than the default :meth:`edmonds_karp`, which is faster for
    sparse networks with highly skewed degree distributions.
    Alternative flow functions have to be explicitly imported
    from the flow package.

    >>> from networkx.algorithms.flow import shortest_augmenting_path
    >>> nx.edge_connectivity(G, flow_func=shortest_augmenting_path)
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
    This is a flow based implementation of global edge connectivity.
    For undirected graphs the algorithm works by finding a 'small'
    dominating set of nodes of G (see algorithm 7 in [1]_ ) and
    computing local maximum flow (see :meth:`local_edge_connectivity`)
    between an arbitrary node in the dominating set and the rest of
    nodes in it. This is an implementation of algorithm 6 in [1]_ .
    For directed graphs, the algorithm does n calls to the maximum
    flow function. This is an implementation of algorithm 8 in [1]_ .

    See also
    --------
    :meth:`local_edge_connectivity`
    :meth:`local_node_connectivity`
    :meth:`node_connectivity`
    :meth:`maximum_flow`
    :meth:`edmonds_karp`
    :meth:`preflow_push`
    :meth:`shortest_augmenting_path`
    :meth:`k_edge_components`
    :meth:`k_edge_subgraphs`

    References
    ----------
    .. [1] Abdol-Hossein Esfahanian. Connectivity Algorithms.
        http://www.cse.msu.edu/~cse835/Papers/Graph_connectivity_revised.pdf

    """
    if (s is not None and t is None) or (s is None and t is not None):
        raise nx.NetworkXError("Both source and target must be specified.")

    # Local edge connectivity
    if s is not None and t is not None:
        if s not in G:
            raise nx.NetworkXError(f"node {s} not in graph")
        if t not in G:
            raise nx.NetworkXError(f"node {t} not in graph")
        return local_edge_connectivity(G, s, t, flow_func=flow_func, cutoff=cutoff)

    # Global edge connectivity
    # reuse auxiliary digraph and residual network
    H = build_auxiliary_edge_connectivity(G)
    R = build_residual_network(H, "capacity")
    kwargs = {"flow_func": flow_func, "auxiliary": H, "residual": R}

    if G.is_directed():
        # Algorithm 8 in [1]
        if not nx.is_weakly_connected(G):
            return 0

        # initial value for \lambda is minimum degree
        L = min(d for n, d in G.degree())
        nodes = list(G)
        n = len(nodes)

        if cutoff is not None:
            L = min(cutoff, L)

        for i in range(n):
            kwargs["cutoff"] = L
            try:
                L = min(L, local_edge_connectivity(G, nodes[i], nodes[i + 1], **kwargs))
            except IndexError:  # last node!
                L = min(L, local_edge_connectivity(G, nodes[i], nodes[0], **kwargs))
        return L
    else:  # undirected
        # Algorithm 6 in [1]
        if not nx.is_connected(G):
            return 0

        # initial value for \lambda is minimum degree
        L = min(d for n, d in G.degree())

        if cutoff is not None:
            L = min(cutoff, L)

        # A dominating set is \lambda-covering
        # We need a dominating set with at least two nodes
        for node in G:
            D = nx.dominating_set(G, start_with=node)
            v = D.pop()
            if D:
                break
        else:
            # in complete graphs the dominating sets will always be of one node
            # thus we return min degree
            return L

        for w in D:
            kwargs["cutoff"] = L
            L = min(L, local_edge_connectivity(G, v, w, **kwargs))

        return L
