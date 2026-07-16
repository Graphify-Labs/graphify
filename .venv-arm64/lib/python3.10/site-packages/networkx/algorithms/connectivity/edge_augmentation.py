"""
Algorithms for finding k-edge-augmentations

A k-edge-augmentation is a set of edges, that once added to a graph, ensures
that the graph is k-edge-connected; i.e. the graph cannot be disconnected
unless k or more edges are removed.  Typically, the goal is to find the
augmentation with minimum weight.  In general, it is not guaranteed that a
k-edge-augmentation exists.

See Also
--------
:mod:`edge_kcomponents` : algorithms for finding k-edge-connected components
:mod:`connectivity` : algorithms for determining edge connectivity.
"""

import itertools as it
import math
from collections import defaultdict, namedtuple

import networkx as nx
from networkx.utils import not_implemented_for, py_random_state

__all__ = ["k_edge_augmentation", "is_k_edge_connected", "is_locally_k_edge_connected"]


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def is_k_edge_connected(G, k):
    """Tests to see if a graph is k-edge-connected.

    Is it impossible to disconnect the graph by removing fewer than k edges?
    If so, then G is k-edge-connected.

    Parameters
    ----------
    G : NetworkX graph
       An undirected graph.

    k : integer
        edge connectivity to test for

    Returns
    -------
    boolean
        True if G is k-edge-connected.

    See Also
    --------
    :func:`is_locally_k_edge_connected`

    Examples
    --------
    >>> G = nx.barbell_graph(10, 0)
    >>> nx.is_k_edge_connected(G, k=1)
    True
    >>> nx.is_k_edge_connected(G, k=2)
    False
    """
    if k < 1:
        raise ValueError(f"k must be positive, not {k}")
    # First try to quickly determine if G is not k-edge-connected
    if G.number_of_nodes() < k + 1:
        return False
    elif any(d < k for n, d in G.degree()):
        return False
    else:
        # Otherwise perform the full check
        if k == 1:
            return nx.is_connected(G)
        elif k == 2:
            return nx.is_connected(G) and not nx.has_bridges(G)
        else:
            return nx.edge_connectivity(G, cutoff=k) >= k


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def is_locally_k_edge_connected(G, s, t, k):
    """Tests to see if an edge in a graph is locally k-edge-connected.

    Is it impossible to disconnect s and t by removing fewer than k edges?
    If so, then s and t are locally k-edge-connected in G.

    Parameters
    ----------
    G : NetworkX graph
       An undirected graph.

    s : node
        Source node

    t : node
        Target node

    k : integer
        local edge connectivity for nodes s and t

    Returns
    -------
    boolean
        True if s and t are locally k-edge-connected in G.

    See Also
    --------
    :func:`is_k_edge_connected`

    Examples
    --------
    >>> from networkx.algorithms.connectivity import is_locally_k_edge_connected
    >>> G = nx.barbell_graph(10, 0)
    >>> is_locally_k_edge_connected(G, 5, 15, k=1)
    True
    >>> is_locally_k_edge_connected(G, 5, 15, k=2)
    False
    >>> is_locally_k_edge_connected(G, 1, 5, k=2)
    True
    """
    if k < 1:
        raise ValueError(f"k must be positive, not {k}")

    # First try to quickly determine s, t is not k-locally-edge-connected in G
    if G.degree(s) < k or G.degree(t) < k:
        return False
    else:
        # Otherwise perform the full check
        if k == 1:
            return nx.has_path(G, s, t)
        else:
            localk = nx.connectivity.local_edge_connectivity(G, s, t, cutoff=k)
            return localk >= k


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def k_edge_augmentation(G, k, avail=None, weight=None, partial=False):
    """Finds set of edges to k-edge-connect G.

    Adding edges from the augmentation to G make it impossible to disconnect G
    unless k or more edges are removed. This function uses the most efficient
    function available (depending on the value of k and if the problem is
    weighted or unweighted) to search for a minimum weight subset of available
    edges that k-edge-connects G. In general, finding a k-edge-augmentation is
    NP-hard, so solutions are not guaranteed to be minimal. Furthermore, a
    k-edge-augmentation may not exist.

    Parameters
    ----------
    G : NetworkX graph
       An undirected graph.

    k : integer
        Desired edge connectivity

    avail : dict or a set of 2 or 3 tuples
        The available edges that can be used in the augmentation.

        If unspecified, then all edges in the complement of G are available.
        Otherwise, each item is an available edge (with an optional weight).

        In the unweighted case, each item is an edge ``(u, v)``.

        In the weighted case, each item is a 3-tuple ``(u, v, d)`` or a dict
        with items ``(u, v): d``.  The third item, ``d``, can be a dictionary
        or a real number.  If ``d`` is a dictionary ``d[weight]``
        correspondings to the weight.

    weight : string
        key to use to find weights if ``avail`` is a set of 3-tuples where the
        third item in each tuple is a dictionary.

    partial : boolean
        If partial is True and no feasible k-edge-augmentation exists, then all
        a partial k-edge-augmentation is generated. Adding the edges in a
        partial augmentation to G, minimizes the number of k-edge-connected
        components and maximizes the edge connectivity between those
        components. For details, see :func:`partial_k_edge_augmentation`.

    Yields
    ------
    edge : tuple
        Edges that, once added to G, would cause G to become k-edge-connected.
        If partial is False, an error is raised if this is not possible.
        Otherwise, generated edges form a partial augmentation, which
        k-edge-connects any part of G where it is possible, and maximally
        connects the remaining parts.

    Raises
    ------
    NetworkXUnfeasible
        If partial is False and no k-edge-augmentation exists.

    NetworkXNotImplemented
        If the input graph is directed or a multigraph.

    ValueError:
        If k is less than 1

    Notes
    -----
    When k=1 this returns an optimal solution.

    When k=2 and ``avail`` is None, this returns an optimal solution.
    Otherwise when k=2, this returns a 2-approximation of the optimal solution.

    For k>3, this problem is NP-hard and this uses a randomized algorithm that
        produces a feasible solution, but provides no guarantees on the
        solution weight.

    Examples
    --------
    >>> # Unweighted cases
    >>> G = nx.path_graph((1, 2, 3, 4))
    >>> G.add_node(5)
    >>> sorted(nx.k_edge_augmentation(G, k=1))
    [(1, 5)]
    >>> sorted(nx.k_edge_augmentation(G, k=2))
    [(1, 5), (5, 4)]
    >>> sorted(nx.k_edge_augmentation(G, k=3))
    [(1, 4), (1, 5), (2, 5), (3, 5), (4, 5)]
    >>> complement = list(nx.k_edge_augmentation(G, k=5, partial=True))
    >>> G.add_edges_from(complement)
    >>> nx.edge_connectivity(G)
    4

    >>> # Weighted cases
    >>> G = nx.path_graph((1, 2, 3, 4))
    >>> G.add_node(5)
    >>> # avail can be a tuple with a dict
    >>> avail = [(1, 5, {"weight": 11}), (2, 5, {"weight": 10})]
    >>> sorted(nx.k_edge_augmentation(G, k=1, avail=avail, weight="weight"))
    [(2, 5)]
    >>> # or avail can be a 3-tuple with a real number
    >>> avail = [(1, 5, 11), (2, 5, 10), (4, 3, 1), (4, 5, 51)]
    >>> sorted(nx.k_edge_augmentation(G, k=2, avail=avail))
    [(1, 5), (2, 5), (4, 5)]
    >>> # or avail can be a dict
    >>> avail = {(1, 5): 11, (2, 5): 10, (4, 3): 1, (4, 5): 51}
    >>> sorted(nx.k_edge_augmentation(G, k=2, avail=avail))
    [(1, 5), (2, 5), (4, 5)]
    >>> # If augmentation is infeasible, then a partial solution can be found
    >>> avail = {(1, 5): 11}
    >>> sorted(nx.k_edge_augmentation(G, k=2, avail=avail, partial=True))
    [(1, 5)]
    """
    try:
        if k <= 0:
            raise ValueError(f"k must be a positive integer, not {k}")
        elif G.number_of_nodes() < k + 1:
            msg = f"impossible to {k} connect in graph with less than {k + 1} nodes"
            raise nx.NetworkXUnfeasible(msg)
        elif avail is not None and len(avail) == 0:
            if not nx.is_k_edge_connected(G, k):
                raise nx.NetworkXUnfeasible("no available edges")
            aug_edges = []
        elif k == 1:
            aug_edges = one_edge_augmentation(
                G, avail=avail, weight=weight, partial=partial
            )
        elif k == 2:
            aug_edges = bridge_augmentation(G, avail=avail, weight=weight)
        else:
            # raise NotImplementedError(f'not implemented for k>2. k={k}')
            aug_edges = greedy_k_edge_augmentation(
                G, k=k, avail=avail, weight=weight, seed=0
            )
        # Do eager evaluation so we can catch any exceptions
        # Before executing partial code.
        yield from list(aug_edges)
    except nx.NetworkXUnfeasible:
        if partial:
            # Return all available edges
            if avail is None:
                aug_edges = complement_edges(G)
            else:
                # If we can't k-edge-connect the entire graph, try to
                # k-edge-connect as much as possible
                aug_edges = partial_k_edge_augmentation(
                    G, k=k, avail=avail, weight=weight
                )
            yield from aug_edges
        else:
            raise


@nx._dispatchable
def partial_k_edge_augmentation(G, k, avail, weight=None):
    """Finds augmentation that k-edge-connects as much of the graph as possible.

    When a k-edge-augmentation is not possible, we can still try to find a
    small set of edges that partially k-edge-connects as much of the graph as
    possible. All possible edges are generated between remaining parts.
    This minimizes the number of k-edge-connected subgraphs in the resulting
    graph and maximizes the edge connectivity between those subgraphs.

    Parameters
    ----------
    G : NetworkX graph
       An undirected graph.

    k : integer
        Desired edge connectivity

    avail : dict or a set of 2 or 3 tuples
        For more details, see :func:`k_edge_augmentation`.

    weight : string
        key to use to find weights if ``avail`` is a set of 3-tuples.
        For more details, see :func:`k_edge_augmentation`.

    Yields
    ------
    edge : tuple
        Edges in the partial augmentation of G. These edges k-edge-connect any
        part of G where it is possible, and maximally connects the remaining
        parts. In other words, all edges from avail are generated except for
        those within subgraphs that have already become k-edge-connected.

    Notes
    -----
    Construct H that augments G with all edges in avail.
    Find the k-edge-subgraphs of H.
    For each k-edge-subgraph, if the number of nodes is more than k, then find
    the k-edge-augmentation of that graph and add it to the solution. Then add
    all edges in avail between k-edge subgraphs to the solution.

    See Also
    --------
    :func:`k_edge_augmentation`

    Examples
    --------
    >>> G = nx.path_graph((1, 2, 3, 4, 5, 6, 7))
    >>> G.add_node(8)
    >>> avail = [(1, 3), (1, 4), (1, 5), (2, 4), (2, 5), (3, 5), (1, 8)]
    >>> sorted(partial_k_edge_augmentation(G, k=2, avail=avail))
    [(1, 5), (1, 8)]
    """

    def _edges_between_disjoint(H, only1, only2):
        """finds edges between disjoint nodes"""
        only1_adj = {u: set(H.adj[u]) for u in only1}
        for u, neighbs in only1_adj.items():
            # Find the neighbors of u in only1 that are also in only2
            neighbs12 = neighbs.intersection(only2)
            for v in neighbs12:
                yield (u, v)

    avail_uv, avail_w = _unpack_available_edges(avail, weight=weight, G=G)

    # Find which parts of the graph can be k-edge-connected
    H = G.copy()
    H.add_edges_from(
        (
            (u, v, {"weight": w, "generator": (u, v)})
            for (u, v), w in zip(avail, avail_w)
        )
    )
    k_edge_subgraphs = list(nx.k_edge_subgraphs(H, k=k))

    # Generate edges to k-edge-connect internal subgraphs
    for nodes in k_edge_subgraphs:
        if len(nodes) > 1:
            # Get the k-edge-connected subgraph
            C = H.subgraph(nodes).copy()
            # Find the internal edges that were available
            sub_avail = {
                d["generator"]: d["weight"]
                for (u, v, d) in C.edges(data=True)
                if "generator" in d
            }
            # Remove potential augmenting edges
            C.remove_edges_from(sub_avail.keys())
            # Find a subset of these edges that makes the component
            # k-edge-connected and ignore the rest
            yield from nx.k_edge_augmentation(C, k=k, avail=sub_avail)

    # Generate all edges between CCs that could not be k-edge-connected
    for cc1, cc2 in it.combinations(k_edge_subgraphs, 2):
        for u, v in _edges_between_disjoint(H, cc1, cc2):
            d = H.get_edge_data(u, v)
            edge = d.get("generator", None)
            if edge is not None:
                yield edge


@not_implemented_for("multigraph")
@not_implemented_for("directed")
@nx._dispatchable
def one_edge_augmentation(G, avail=None, weight=None, partial=False):
    """Finds minimum weight set of edges to connect G.

    Equivalent to :func:`k_edge_augmentation` when k=1. Adding the resulting
    edges to G will make it 1-edge-connected. The solution is optimal for both
    weighted and non-weighted variants.

    Parameters
    ----------
    G : NetworkX graph
       An undirected graph.

    avail : dict or a set of 2 or 3 tuples
        For more details, see :func:`k_edge_augmentation`.

    weight : string
        key to use to find weights if ``avail`` is a set of 3-tuples.
        For more details, see :func:`k_edge_augmentation`.

    partial : boolean
        If partial is True and no feasible k-edge-augmentation exists, then the
        augmenting edges minimize the number of connected components.

    Yields
    ------
    edge : tuple
        Edges in the one-augmentation of G

    Raises
    ------
    NetworkXUnfeasible
        If partial is False and no one-edge-augmentation exists.

    Notes
    -----
    Uses either :func:`unconstrained_one_edge_augmentation` or
    :func:`weighted_one_edge_augmentation` depending on whether ``avail`` is
    specified. Both algorithms are based on finding a minimum spanning tree.
    As such both algorithms find optimal solutions and run in linear time.

    See Also
    --------
    :func:`k_edge_augmentation`
    """
    if avail is None:
        return unconstrained_one_edge_augmentation(G)
    else:
        return weighted_one_edge_augmentation(
            G, avail=avail, weight=weight, partial=partial
        )


@not_implemented_for("multigraph")
@not_implemented_for("directed")
@nx._dispatchable
def bridge_augmentation(G, avail=None, weight=None):
    """Finds the a set of edges that bridge connects G.

    Equivalent to :func:`k_edge_augmentation` when k=2, and partial=False.
    Adding the resulting edges to G will make it 2-edge-connected.  If no
    constraints are specified the returned set of edges is minimum an optimal,
    otherwise the solution is approximated.

    Parameters
    ----------
    G : NetworkX graph
       An undirected graph.

    avail : dict or a set of 2 or 3 tuples
        For more details, see :func:`k_edge_augmentation`.

    weight : string
        key to use to find weights if ``avail`` is a set of 3-tuples.
        For more details, see :func:`k_edge_augmentation`.

    Yields
    ------
    edge : tuple
        Edges in the bridge-augmentation of G

    Raises
    ------
    NetworkXUnfeasible
        If no bridge-augmentation exists.

    Notes
    -----
    If there are no constraints the solution can be computed in linear time
    using :func:`unconstrained_bridge_augmentation`. Otherwise, the problem
    becomes NP-hard and is the solution is approximated by
    :func:`weighted_bridge_augmentation`.

    See Also
    --------
    :func:`k_edge_augmentation`
    """
    if G.number_of_nodes() < 3:
        raise nx.NetworkXUnfeasible("impossible to bridge connect less than 3 nodes")
    if avail is None:
        return unconstrained_bridge_augmentation(G)
    else:
        return weighted_bridge_augmentation(G, avail, weight=weight)


# --- Algorithms and Helpers ---


def _ordered(u, v):
    """Returns the nodes in an undirected edge in lower-triangular order"""
    return (u, v) if u < v else (v, u)


def _unpack_available_edges(avail, weight=None, G=None):
    """Helper to separate avail into edges and corresponding weights"""
    if weight is None:
        weight = "weight"
    if isinstance(avail, dict):
        avail_uv = list(avail.keys())
        avail_w = list(avail.values())
    else:

        def _try_getitem(d):
            try:
                return d[weight]
            except TypeError:
                return d

        avail_uv = [tup[0:2] for tup in avail]
        avail_w = [1 if len(tup) == 2 else _try_getitem(tup[-1]) for tup in avail]

    if G is not None:
        # Edges already in the graph are filtered
        flags = [not G.has_edge(u, v) for u, v in avail_uv]
        avail_uv = list(it.compress(avail_uv, flags))
        avail_w = list(it.compress(avail_w, flags))
    return avail_uv, avail_w


MetaEdge = namedtuple("MetaEdge", ("meta_uv", "uv", "w"))


def _lightest_meta_edges(mapping, avail_uv, avail_w):
    """Maps available edges in the original graph to edges in the metagraph.

    Parameters
    ----------
    mapping : dict
        mapping produced by :func:`collapse`, that maps each node in the
        original graph to a node in the meta graph

    avail_uv : list
        list of edges

    avail_w : list
        list of edge weights

    Notes
    -----
    Each node in the metagraph is a k-edge-connected component in the original
    graph.  We don't care about any edge within the same k-edge-connected
    component, so we ignore self edges.  We also are only interested in the
    minimum weight edge bridging each k-edge-connected component so, we group
    the edges by meta-edge and take the lightest in each group.

    Examples
    --------
    >>> # Each group represents a meta-node
    >>> groups = ([1, 2, 3], [4, 5], [6])
    >>> mapping = {n: meta_n for meta_n, ns in enumerate(groups) for n in ns}
    >>> avail_uv = [(1, 2), (3, 6), (1, 4), (5, 2), (6, 1), (2, 6), (3, 1)]
    >>> avail_w = [20, 99, 20, 15, 50, 99, 20]
    >>> sorted(_lightest_meta_edges(mapping, avail_uv, avail_w))
    [MetaEdge(meta_uv=(0, 1), uv=(5, 2), w=15), MetaEdge(meta_uv=(0, 2), uv=(6, 1), w=50)]
    """
    grouped_wuv = defaultdict(list)
    for w, (u, v) in zip(avail_w, avail_uv):
        # Order the meta-edge so it can be used as a dict key
        meta_uv = _ordered(mapping[u], mapping[v])
        # Group each available edge using the meta-edge as a key
        grouped_wuv[meta_uv].append((w, u, v))

    # Now that all available edges are grouped, choose one per group
    for (mu, mv), choices_wuv in grouped_wuv.items():
        # Ignore available edges within the same meta-node
        if mu != mv:
            # Choose the lightest available edge belonging to each meta-edge
            w, u, v = min(choices_wuv)
            yield MetaEdge((mu, mv), (u, v), w)


@nx._dispatchable
def unconstrained_one_edge_augmentation(G):
    """Finds the smallest set of edges to connect G.

    This is a variant of the unweighted MST problem.
    If G is not empty, a feasible solution always exists.

    Parameters
    ----------
    G : NetworkX graph
       An undirected graph.

    Yields
    ------
    edge : tuple
        Edges in the one-edge-augmentation of G

    See Also
    --------
    :func:`one_edge_augmentation`
    :func:`k_edge_augmentation`

    Examples
    --------
    >>> G = nx.Graph([(1, 2), (2, 3), (4, 5)])
    >>> G.add_nodes_from([6, 7, 8])
    >>> sorted(unconstrained_one_edge_augmentation(G))
    [(1, 4), (4, 6), (6, 7), (7, 8)]
    """
    ccs1 = list(nx.connected_components(G))
    C = collapse(G, ccs1)
    # When we are not constrained, we can just make a meta graph tree.
    meta_nodes = list(C.nodes())
    # build a path in the metagraph
    meta_aug = list(zip(meta_nodes, meta_nodes[1:]))
    # map that path to the original graph
    inverse = defaultdict(list)
    for k, v in C.graph["mapping"].items():
        inverse[v].append(k)
    for mu, mv in meta_aug:
        yield (inverse[mu][0], inverse[mv][0])


@nx._dispatchable
def weighted_one_edge_augmentation(G, avail, weight=None, partial=False):
    """Finds the minimum weight set of edges to connect G if one exists.

    This is a variant of the weighted MST problem.

    Parameters
    ----------
    G : NetworkX graph
       An undirected graph.

    avail : dict or a set of 2 or 3 tuples
        For more details, see :func:`k_edge_augmentation`.

    weight : string
        key to use to find weights if ``avail`` is a set of 3-tuples.
        For more details, see :func:`k_edge_augmentation`.

    partial : boolean
        If partial is True and no feasible k-edge-augmentation exists, then the
        augmenting edges minimize the number of connected components.

    Yields
    ------
    edge : tuple
        Edges in the subset of avail chosen to connect G.

    See Also
    --------
    :func:`one_edge_augmentation`
    :func:`k_edge_augmentation`

    Examples
    --------
    >>> G = nx.Graph([(1, 2), (2, 3), (4, 5)])
    >>> G.add_nodes_from([6, 7, 8])
    >>> # any edge not in avail has an implicit weight of infinity
    >>> avail = [(1, 3), (1, 5), (4, 7), (4, 8), (6, 1), (8, 1), (8, 2)]
    >>> sorted(weighted_one_edge_augmentation(G, avail))
    [(1, 5), (4, 7), (6, 1), (8, 1)]
    >>> # find another solution by giving large weights to edges in the
    >>> # previous solution (note some of the old edges must be used)
    >>> avail = [(1, 3), (1, 5, 99), (4, 7, 9), (6, 1, 99), (8, 1, 99), (8, 2)]
    >>> sorted(weighted_one_edge_augmentation(G, avail))
    [(1, 5), (4, 7), (6, 1), (8, 2)]
    """
    avail_uv, avail_w = _unpack_available_edges(avail, weight=weight, G=G)
    # Collapse CCs in the original graph into nodes in a metagraph
    # Then find an MST of the metagraph instead of the original graph
    C = collapse(G, nx.connected_components(G))
    mapping = C.graph["mapping"]
    # Assign each available edge to an edge in the metagraph
    candidate_mapping = _lightest_meta_edges(mapping, avail_uv, avail_w)
    # nx.set_edge_attributes(C, name='weight', values=0)
    C.add_edges_from(
        (mu, mv, {"weight": w, "generator": uv})
        for (mu, mv), uv, w in candidate_mapping
    )
    # Find MST of the meta graph
    meta_mst = nx.minimum_spanning_tree(C)
    if not partial and not nx.is_connected(meta_mst):
        raise nx.NetworkXUnfeasible("Not possible to connect G with available edges")
    # Yield the edge that generated the meta-edge
    for mu, mv, d in meta_mst.edges(data=True):
        if "generator" in d:
            edge = d["generator"]
            yield edge


@nx._dispatchable
def unconstrained_bridge_augmentation(G):
    """Finds an optimal 2-edge-augmentation of G using the fewest edges.

    This is an implementation of the algorithm detailed in [1]_.
    The basic idea is to construct a meta-graph of bridge-ccs, connect leaf
    nodes of the trees to connect the entire graph, and finally connect the
    leafs of the tree in dfs-preorder to bridge connect the entire graph.

    Parameters
    ----------
    G : NetworkX graph
       An undirected graph.

    Yields
    ------
    edge : tuple
        Edges in the bridge augmentation of G

    Notes
    -----
    Input: a graph G.
    First find the bridge components of G and collapse each bridge-cc into a
    node of a metagraph graph C, which is guaranteed to be a forest of trees.

    C contains p "leafs" --- nodes with exactly one incident edge.
    C contains q "isolated nodes" --- nodes with no incident edges.

    Theorem: If p + q > 1, then at least :math:`ceil(p / 2) + q` edges are
        needed to bridge connect C. This algorithm achieves this min number.

    The method first adds enough edges to make G into a tree and then pairs
    leafs in a simple fashion.

    Let n be the number of trees in C. Let v(i) be an isolated vertex in the
    i-th tree if one exists, otherwise it is a pair of distinct leafs nodes
    in the i-th tree. Alternating edges from these sets (i.e.  adding edges
    A1 = [(v(i)[0], v(i + 1)[1]), v(i + 1)[0], v(i + 2)[1])...]) connects C
    into a tree T. This tree has p' = p + 2q - 2(n -1) leafs and no isolated
    vertices. A1 has n - 1 edges. The next step finds ceil(p' / 2) edges to
    biconnect any tree with p' leafs.

    Convert T into an arborescence T' by picking an arbitrary root node with
    degree >= 2 and directing all edges away from the root. Note the
    implementation implicitly constructs T'.

    The leafs of T are the nodes with no existing edges in T'.
    Order the leafs of T' by DFS preorder. Then break this list in half
    and add the zipped pairs to A2.

    The set A = A1 + A2 is the minimum augmentation in the metagraph.

    To convert this to edges in the original graph

    References
    ----------
    .. [1] Eswaran, Kapali P., and R. Endre Tarjan. (1975) Augmentation problems.
        http://epubs.siam.org/doi/abs/10.1137/0205044

    See Also
    --------
    :func:`bridge_augmentation`
    :func:`k_edge_augmentation`

    Examples
    --------
    >>> G = nx.path_graph((1, 2, 3, 4, 5, 6, 7))
    >>> sorted(unconstrained_bridge_augmentation(G))
    [(1, 7)]
    >>> G = nx.path_graph((1, 2, 3, 2, 4, 5, 6, 7))
    >>> sorted(unconstrained_bridge_augmentation(G))
    [(1, 3), (3, 7)]
    >>> G = nx.Graph([(0, 1), (0, 2), (1, 2)])
    >>> G.add_node(4)
    >>> sorted(unconstrained_bridge_augmentation(G))
    [(1, 4), (4, 0)]
    """
    # -----
    # Mapping of terms from (Eswaran and Tarjan):
    #     G = G_0 - the input graph
    #     C = G_0' - the bridge condensation of G. (This is a forest of trees)
    #     A1 = A_1 - the edges to connect the forest into a tree
    #         leaf = pendant - a node with degree of 1

    #     alpha(v) = maps the node v in G to its meta-node in C
    #     beta(x) = maps the meta-node x in C to any node in the bridge
    #         component of G corresponding to x.

    # find the 2-edge-connected components of G
    bridge_ccs = list(nx.connectivity.bridge_components(G))
    # condense G into an forest C
    C = collapse(G, bridge_ccs)

    # Choose pairs of distinct leaf nodes in each tree. If this is not
    # possible then make a pair using the single isolated node in the tree.
    vset1 = [
        tuple(cc) * 2  # case1: an isolated node
        if len(cc) == 1
        else sorted(cc, key=C.degree)[0:2]  # case2: pair of leaf nodes
        for cc in nx.connected_components(C)
    ]
    if len(vset1) > 1:
        # Use this set to construct edges that connect C into a tree.
        nodes1 = [vs[0] for vs in vset1]
        nodes2 = [vs[1] for vs in vset1]
        A1 = list(zip(nodes1[1:], nodes2))
    else:
        A1 = []
    # Connect each tree in the forest to construct an arborescence
    T = C.copy()
    T.add_edges_from(A1)

    # If there are only two leaf nodes, we simply connect them.
    leafs = [n for n, d in T.degree() if d == 1]
    if len(leafs) == 1:
        A2 = []
    if len(leafs) == 2:
        A2 = [tuple(leafs)]
    else:
        # Choose an arbitrary non-leaf root
        try:
            root = next(n for n, d in T.degree() if d > 1)
        except StopIteration:  # no nodes found with degree > 1
            return
        # order the leaves of C by (induced directed) preorder
        v2 = [n for n in nx.dfs_preorder_nodes(T, root) if T.degree(n) == 1]
        # connecting first half of the leafs in pre-order to the second
        # half will bridge connect the tree with the fewest edges.
        half = math.ceil(len(v2) / 2)
        A2 = list(zip(v2[:half], v2[-half:]))

    # collect the edges used to augment the original forest
    aug_tree_edges = A1 + A2

    # Construct the mapping (beta) from meta-nodes to regular nodes
    inverse = defaultdict(list)
    for k, v in C.graph["mapping"].items():
        inverse[v].append(k)
    # sort so we choose minimum degree nodes first
    inverse = {
        mu: sorted(mapped, key=lambda u: (G.degree(u), u))
        for mu, mapped in inverse.items()
    }

    # For each meta-edge, map back to an arbitrary pair in the original graph
    G2 = G.copy()
    for mu, mv in aug_tree_edges:
        # Find the first available edge that doesn't exist and return it
        for u, v in it.product(inverse[mu], inverse[mv]):
            if not G2.has_edge(u, v):
                G2.add_edge(u, v)
                yield u, v
                break


@nx._dispatchable
def weighted_bridge_augmentation(G, avail, weight=None):
    """Finds an approximate min-weight 2-edge-augmentation of G.

    This is an implementation of the approximation algorithm detailed in [1]_.
    It chooses a set of edges from avail to add to G that renders it
    2-edge-connected if such a subset exists.  This is done by finding a
    minimum spanning arborescence of a specially constructed metagraph.

    Parameters
    ----------
    G : NetworkX graph
       An undirected graph.

    avail : set of 2 or 3 tuples.
        candidate edges (with optional weights) to choose from

    weight : string
        key to use to find weights if avail is a set of 3-tuples where the
        third item in each tuple is a dictionary.

    Yields
    ------
    edge : tuple
        Edges in the subset of avail chosen to bridge augment G.

    Notes
    -----
    Finding a weighted 2-edge-augmentation is NP-hard.
    Any edge not in ``avail`` is considered to have a weight of infinity.
    The approximation factor is 2 if ``G`` is connected and 3 if it is not.
    Runs in :math:`O(m + n log(n))` time

    References
    ----------
    .. [1] Khuller, Samir, and Ramakrishna Thurimella. (1993) Approximation
        algorithms for graph augmentation.
        http://www.sciencedirect.com/science/article/pii/S0196677483710102

    See Also
    --------
    :func:`bridge_augmentation`
    :func:`k_edge_augmentation`

    Examples
    --------
    >>> G = nx.path_graph((1, 2, 3, 4))
    >>> # When the weights are equal, (1, 4) is the best
    >>> avail = [(1, 4, 1), (1, 3, 1), (2, 4, 1)]
    >>> sorted(weighted_bridge_augmentation(G, avail))
    [(1, 4)]
    >>> # Giving (1, 4) a high weight makes the two edge solution the best.
    >>> avail = [(1, 4, 1000), (1, 3, 1), (2, 4, 1)]
    >>> sorted(weighted_bridge_augmentation(G, avail))
    [(1, 3), (2, 4)]
    >>> # ------
    >>> G = nx.path_graph((1, 2, 3, 4))
    >>> G.add_node(5)
    >>> avail = [(1, 5, 11), (2, 5, 10), (4, 3, 1), (4, 5, 1)]
    >>> sorted(weighted_bridge_augmentation(G, avail=avail))
    [(1, 5), (4, 5)]
    >>> avail = [(1, 5, 11), (2, 5, 10), (4, 3, 1), (4, 5, 51)]
    >>> sorted(weighted_bridge_augmentation(G, avail=avail))
    [(1, 5), (2, 5), (4, 5)]
    """

    if weight is None:
        weight = "weight"

    # If input G is not connected the approximation factor increases to 3
    if not nx.is_connected(G):
        H = G.copy()
        connectors = list(one_edge_augmentation(H, avail=avail, weight=weight))
        H.add_edges_from(connectors)

        yield from connectors
    else:
        connectors = []
        H = G

    if len(avail) == 0:
        if nx.has_bridges(H):
            raise nx.NetworkXUnfeasible("no augmentation possible")

    avail_uv, avail_w = _unpack_available_edges(avail, weight=weight, G=H)

    # Collapse input into a metagraph. Meta nodes are bridge-ccs
    bridge_ccs = nx.connectivity.bridge_components(H)
    C = collapse(H, bridge_ccs)

    # Use the meta graph to shrink avail to a small feasible subset
    mapping = C.graph["mapping"]
    # Choose the minimum weight feasible edge in each group
    meta_to_wuv = {
        (mu, mv): (w, uv)
        for (mu, mv), uv, w in _lightest_meta_edges(mapping, avail_uv, avail_w)
    }

    # Mapping of terms from (Khuller and Thurimella):
    #     C         : G_0 = (V, E^0)
    #        This is the metagraph where each node is a 2-edge-cc in G.
    #        The edges in C represent bridges in the original graph.
    #     (mu, mv)  : E - E^0  # they group both avail and given edges in E
    #     T         : \Gamma
    #     D         : G^D = (V, E_D)

    #     The paper uses ancestor because children point to parents, which is
    #     contrary to networkx standards.  So, we actually need to run
    #     nx.least_common_ancestor on the reversed Tree.

    # Pick an arbitrary leaf from C as the root
    try:
        root = next(n for n, d in C.degree() if d == 1)
    except StopIteration:  # no nodes found with degree == 1
        return
    # Root C into a tree TR by directing all edges away from the root
    # Note in their paper T directs edges towards the root
    TR = nx.dfs_tree(C, root)

    # Add to D the directed edges of T and set their weight to zero
    # This indicates that it costs nothing to use edges that were given.
    D = nx.reverse(TR).copy()

    nx.set_edge_attributes(D, name="weight", values=0)

    # The LCA of mu and mv in T is the shared ancestor of mu and mv that is
    # located farthest from the root.
    lca_gen = nx.tree_all_pairs_lowest_common_ancestor(
        TR, root=root, pairs=meta_to_wuv.keys()
    )

    for (mu, mv), lca in lca_gen:
        w, uv = meta_to_wuv[(mu, mv)]
        if lca == mu:
            # If u is an ancestor of v in TR, then add edge u->v to D
            D.add_edge(lca, mv, weight=w, generator=uv)
        elif lca == mv:
            # If v is an ancestor of u in TR, then add edge v->u to D
            D.add_edge(lca, mu, weight=w, generator=uv)
        else:
            # If neither u nor v is a ancestor of the other in TR
            # let t = lca(TR, u, v) and add edges t->u and t->v
            # Track the original edge that GENERATED these edges.
            D.add_edge(lca, mu, weight=w, generator=uv)
            D.add_edge(lca, mv, weight=w, generator=uv)

    # Then compute a minimum rooted branching
    try:
        # Note the original edges must be directed towards to root for the
        # branching to give us a bridge-augmentation.
        A = _minimum_rooted_branching(D, root)
    except nx.NetworkXException as err:
        # If there is no branching then augmentation is not possible
        raise nx.NetworkXUnfeasible("no 2-edge-augmentation possible") from err

    # For each edge e, in the branching that did not belong to the directed
    # tree T, add the corresponding edge that **GENERATED** it (this is not
    # necessarily e itself!)

    # ensure the third case does not generate edges twice
    bridge_connectors = set()
    for mu, mv in A.edges():
        data = D.get_edge_data(mu, mv)
        if "generator" in data:
            # Add the avail edge that generated the branching edge.
            edge = data["generator"]
            bridge_connectors.add(edge)

    yield from bridge_connectors


def _minimum_rooted_branching(D, root):
    """Helper function to compute a minimum rooted branching (aka rooted
    arborescence)

    Before the branching can be computed, the directed graph must be rooted by
    removing the predecessors of root.

    A branching / arborescence of rooted graph G is a subgraph that contains a
    directed path from the root to every other vertex. It is the directed
    analog of the minimum spanning tree problem.

    References
    ----------
    [1] Khuller, Samir (2002) Advanced Algorithms Lecture 24 Notes.
    https://web.archive.org/web/20121030033722/https://www.cs.umd.edu/class/spring2011/cmsc651/lec07.pdf
    """
    rooted = D.copy()
    # root the graph by removing all predecessors to `root`.
    rooted.remove_edges_from([(u, root) for u in D.predecessors(root)])
    # Then compute the branching / arborescence.
    A = nx.minimum_spanning_arborescence(rooted)
    return A


@nx._dispatchable(returns_graph=True)
def collapse(G, grouped_nodes):
    """Collapses each group of nodes into a single node.

    This is similar to condensation, but works on undirected graphs.

    Parameters
    ----------
    G : NetworkX Graph

    grouped_nodes:  list or generator
       Grouping of nodes to collapse. The grouping must be disjoint.
       If grouped_nodes are strongly_connected_components then this is
       equivalent to :func:`condensation`.

    Returns
    -------
    C : NetworkX Graph
       The collapsed graph C of G with respect to the node grouping.  The node
       labels are integers corresponding to the index of the component in the
       list of grouped_nodes.  C has a graph attribute named 'mapping' with a
       dictionary mapping the original nodes to the nodes in C to which they
       belong.  Each node in C also has a node attribute 'members' with the set
       of original nodes in G that form the group that the node in C
       represents.

    Examples
    --------
    >>> # Collapses a graph using disjoint groups, but not necessarily connected
    >>> G = nx.Graph([(1, 0), (2, 3), (3, 1), (3, 4), (4, 5), (5, 6), (5, 7)])
    >>> G.add_node("A")
    >>> grouped_nodes = [{0, 1, 2, 3}, {5, 6, 7}]
    >>> C = collapse(G, grouped_nodes)
    >>> members = nx.get_node_attributes(C, "members")
    >>> sorted(members.keys())
    [0, 1, 2, 3]
    >>> member_values = set(map(frozenset, members.values()))
    >>> assert {0, 1, 2, 3} in member_values
    >>> assert {4} in member_values
    >>> assert {5, 6, 7} in member_values
    >>> assert {"A"} in member_values
    """
    mapping = {}
    members = {}
    C = G.__class__()
    i = 0  # required if G is empty
    remaining = set(G.nodes())
    for i, group in enumerate(grouped_nodes):
        group = set(group)
        assert remaining.issuperset(
            group
        ), "grouped nodes must exist in G and be disjoint"
        remaining.difference_update(group)
        members[i] = group
        mapping.update((n, i) for n in group)
    # remaining nodes are in their own group
    for i, node in enumerate(remaining, start=i + 1):
        group = {node}
        members[i] = group
        mapping.update((n, i) for n in group)
    number_of_groups = i + 1
    C.add_nodes_from(range(number_of_groups))
    C.add_edges_from(
        (mapping[u], mapping[v]) for u, v in G.edges() if mapping[u] != mapping[v]
    )
    # Add a list of members (ie original nodes) to each node (ie scc) in C.
    nx.set_node_attributes(C, name="members", values=members)
    # Add mapping dict as graph attribute
    C.graph["mapping"] = mapping
    return C


@nx._dispatchable
def complement_edges(G):
    """Returns only the edges in the complement of G

    Parameters
    ----------
    G : NetworkX Graph

    Yields
    ------
    edge : tuple
        Edges in the complement of G

    Examples
    --------
    >>> G = nx.path_graph((1, 2, 3, 4))
    >>> sorted(complement_edges(G))
    [(1, 3), (1, 4), (2, 4)]
    >>> G = nx.path_graph((1, 2, 3, 4), nx.DiGraph())
    >>> sorted(complement_edges(G))
    [(1, 3), (1, 4), (2, 1), (2, 4), (3, 1), (3, 2), (4, 1), (4, 2), (4, 3)]
    >>> G = nx.complete_graph(1000)
    >>> sorted(complement_edges(G))
    []
    """
    G_adj = G._adj  # Store as a variable to eliminate attribute lookup
    if G.is_directed():
        for u, v in it.combinations(G.nodes(), 2):
            if v not in G_adj[u]:
                yield (u, v)
            if u not in G_adj[v]:
                yield (v, u)
    else:
        for u, v in it.combinations(G.nodes(), 2):
            if v not in G_adj[u]:
                yield (u, v)


def _compat_shuffle(rng, input):
    """wrapper around rng.shuffle for python 2 compatibility reasons"""
    rng.shuffle(input)


@not_implemented_for("multigraph")
@not_implemented_for("directed")
@py_random_state(4)
@nx._dispatchable
def greedy_k_edge_augmentation(G, k, avail=None, weight=None, seed=None):
    """Greedy algorithm for finding a k-edge-augmentation

    Parameters
    ----------
    G : NetworkX graph
       An undirected graph.

    k : integer
        Desired edge connectivity

    avail : dict or a set of 2 or 3 tuples
        For more details, see :func:`k_edge_augmentation`.

    weight : string
        key to use to find weights if ``avail`` is a set of 3-tuples.
        For more details, see :func:`k_edge_augmentation`.

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Yields
    ------
    edge : tuple
        Edges in the greedy augmentation of G

    Notes
    -----
    The algorithm is simple. Edges are incrementally added between parts of the
    graph that are not yet locally k-edge-connected. Then edges are from the
    augmenting set are pruned as long as local-edge-connectivity is not broken.

    This algorithm is greedy and does not provide optimality guarantees. It
    exists only to provide :func:`k_edge_augmentation` with the ability to
    generate a feasible solution for arbitrary k.

    See Also
    --------
    :func:`k_edge_augmentation`

    Examples
    --------
    >>> G = nx.path_graph((1, 2, 3, 4, 5, 6, 7))
    >>> sorted(greedy_k_edge_augmentation(G, k=2))
    [(1, 7)]
    >>> sorted(greedy_k_edge_augmentation(G, k=1, avail=[]))
    []
    >>> G = nx.path_graph((1, 2, 3, 4, 5, 6, 7))
    >>> avail = {(u, v): 1 for (u, v) in complement_edges(G)}
    >>> # randomized pruning process can produce different solutions
    >>> sorted(greedy_k_edge_augmentation(G, k=4, avail=avail, seed=2))
    [(1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (2, 4), (2, 6), (3, 7), (5, 7)]
    >>> sorted(greedy_k_edge_augmentation(G, k=4, avail=avail, seed=3))
    [(1, 3), (1, 5), (1, 6), (2, 4), (2, 6), (3, 7), (4, 7), (5, 7)]
    """
    # Result set
    aug_edges = []

    done = is_k_edge_connected(G, k)
    if done:
        return
    if avail is None:
        # all edges are available
        avail_uv = list(complement_edges(G))
        avail_w = [1] * len(avail_uv)
    else:
        # Get the unique set of unweighted edges
        avail_uv, avail_w = _unpack_available_edges(avail, weight=weight, G=G)

    # Greedy: order lightest edges. Use degree sum to tie-break
    tiebreaker = [sum(map(G.degree, uv)) for uv in avail_uv]
    avail_wduv = sorted(zip(avail_w, tiebreaker, avail_uv))
    avail_uv = [uv for w, d, uv in avail_wduv]

    # Incrementally add edges in until we are k-connected
    H = G.copy()
    for u, v in avail_uv:
        done = False
        if not is_locally_k_edge_connected(H, u, v, k=k):
            # Only add edges in parts that are not yet locally k-edge-connected
            aug_edges.append((u, v))
            H.add_edge(u, v)
            # Did adding this edge help?
            if H.degree(u) >= k and H.degree(v) >= k:
                done = is_k_edge_connected(H, k)
        if done:
            break

    # Check for feasibility
    if not done:
        raise nx.NetworkXUnfeasible("not able to k-edge-connect with available edges")

    # Randomized attempt to reduce the size of the solution
    _compat_shuffle(seed, aug_edges)
    for u, v in list(aug_edges):
        # Don't remove if we know it would break connectivity
        if H.degree(u) <= k or H.degree(v) <= k:
            continue
        H.remove_edge(u, v)
        aug_edges.remove((u, v))
        if not is_k_edge_connected(H, k=k):
            # If removing this edge breaks feasibility, undo
            H.add_edge(u, v)
            aug_edges.append((u, v))

    # Generate results
    yield from aug_edges
