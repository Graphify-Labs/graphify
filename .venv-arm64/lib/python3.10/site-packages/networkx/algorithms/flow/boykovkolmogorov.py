"""
Boykov-Kolmogorov algorithm for maximum flow problems.
"""

from collections import deque
from operator import itemgetter

import networkx as nx
from networkx.algorithms.flow.utils import build_residual_network

__all__ = ["boykov_kolmogorov"]


@nx._dispatchable(edge_attrs={"capacity": float("inf")}, returns_graph=True)
def boykov_kolmogorov(
    G, s, t, capacity="capacity", residual=None, value_only=False, cutoff=None
):
    r"""Find a maximum single-commodity flow using Boykov-Kolmogorov algorithm.

    This function returns the residual network resulting after computing
    the maximum flow. See below for details about the conventions
    NetworkX uses for defining residual networks.

    This algorithm has worse case complexity $O(n^2 m |C|)$ for $n$ nodes, $m$
    edges, and $|C|$ the cost of the minimum cut [1]_. This implementation
    uses the marking heuristic defined in [2]_ which improves its running
    time in many practical problems.

    Parameters
    ----------
    G : NetworkX graph
        Edges of the graph are expected to have an attribute called
        'capacity'. If this attribute is not present, the edge is
        considered to have infinite capacity.

    s : node
        Source node for the flow.

    t : node
        Sink node for the flow.

    capacity : string
        Edges of the graph G are expected to have an attribute capacity
        that indicates how much flow the edge can support. If this
        attribute is not present, the edge is considered to have
        infinite capacity. Default value: 'capacity'.

    residual : NetworkX graph
        Residual network on which the algorithm is to be executed. If None, a
        new residual network is created. Default value: None.

    value_only : bool
        If True compute only the value of the maximum flow. This parameter
        will be ignored by this algorithm because it is not applicable.

    cutoff : integer, float
        If specified, the algorithm will terminate when the flow value reaches
        or exceeds the cutoff. In this case, it may be unable to immediately
        determine a minimum cut. Default value: None.

    Returns
    -------
    R : NetworkX DiGraph
        Residual network after computing the maximum flow.

    Raises
    ------
    NetworkXError
        The algorithm does not support MultiGraph and MultiDiGraph. If
        the input graph is an instance of one of these two classes, a
        NetworkXError is raised.

    NetworkXUnbounded
        If the graph has a path of infinite capacity, the value of a
        feasible flow on the graph is unbounded above and the function
        raises a NetworkXUnbounded.

    See also
    --------
    :meth:`maximum_flow`
    :meth:`minimum_cut`
    :meth:`preflow_push`
    :meth:`shortest_augmenting_path`

    Notes
    -----
    The residual network :samp:`R` from an input graph :samp:`G` has the
    same nodes as :samp:`G`. :samp:`R` is a DiGraph that contains a pair
    of edges :samp:`(u, v)` and :samp:`(v, u)` iff :samp:`(u, v)` is not a
    self-loop, and at least one of :samp:`(u, v)` and :samp:`(v, u)` exists
    in :samp:`G`.

    For each edge :samp:`(u, v)` in :samp:`R`, :samp:`R[u][v]['capacity']`
    is equal to the capacity of :samp:`(u, v)` in :samp:`G` if it exists
    in :samp:`G` or zero otherwise. If the capacity is infinite,
    :samp:`R[u][v]['capacity']` will have a high arbitrary finite value
    that does not affect the solution of the problem. This value is stored in
    :samp:`R.graph['inf']`. For each edge :samp:`(u, v)` in :samp:`R`,
    :samp:`R[u][v]['flow']` represents the flow function of :samp:`(u, v)` and
    satisfies :samp:`R[u][v]['flow'] == -R[v][u]['flow']`.

    The flow value, defined as the total flow into :samp:`t`, the sink, is
    stored in :samp:`R.graph['flow_value']`. If :samp:`cutoff` is not
    specified, reachability to :samp:`t` using only edges :samp:`(u, v)` such
    that :samp:`R[u][v]['flow'] < R[u][v]['capacity']` induces a minimum
    :samp:`s`-:samp:`t` cut.

    Examples
    --------
    >>> from networkx.algorithms.flow import boykov_kolmogorov

    The functions that implement flow algorithms and output a residual
    network, such as this one, are not imported to the base NetworkX
    namespace, so you have to explicitly import them from the flow package.

    >>> G = nx.DiGraph()
    >>> G.add_edge("x", "a", capacity=3.0)
    >>> G.add_edge("x", "b", capacity=1.0)
    >>> G.add_edge("a", "c", capacity=3.0)
    >>> G.add_edge("b", "c", capacity=5.0)
    >>> G.add_edge("b", "d", capacity=4.0)
    >>> G.add_edge("d", "e", capacity=2.0)
    >>> G.add_edge("c", "y", capacity=2.0)
    >>> G.add_edge("e", "y", capacity=3.0)
    >>> R = boykov_kolmogorov(G, "x", "y")
    >>> flow_value = nx.maximum_flow_value(G, "x", "y")
    >>> flow_value
    3.0
    >>> flow_value == R.graph["flow_value"]
    True

    A nice feature of the Boykov-Kolmogorov algorithm is that a partition
    of the nodes that defines a minimum cut can be easily computed based
    on the search trees used during the algorithm. These trees are stored
    in the graph attribute `trees` of the residual network.

    >>> source_tree, target_tree = R.graph["trees"]
    >>> partition = (set(source_tree), set(G) - set(source_tree))

    Or equivalently:

    >>> partition = (set(G) - set(target_tree), set(target_tree))

    References
    ----------
    .. [1] Boykov, Y., & Kolmogorov, V. (2004). An experimental comparison
           of min-cut/max-flow algorithms for energy minimization in vision.
           Pattern Analysis and Machine Intelligence, IEEE Transactions on,
           26(9), 1124-1137.
           https://doi.org/10.1109/TPAMI.2004.60

    .. [2] Vladimir Kolmogorov. Graph-based Algorithms for Multi-camera
           Reconstruction Problem. PhD thesis, Cornell University, CS Department,
           2003. pp. 109-114.
           https://web.archive.org/web/20170809091249/https://pub.ist.ac.at/~vnk/papers/thesis.pdf

    """
    R = boykov_kolmogorov_impl(G, s, t, capacity, residual, cutoff)
    R.graph["algorithm"] = "boykov_kolmogorov"
    nx._clear_cache(R)
    return R


def boykov_kolmogorov_impl(G, s, t, capacity, residual, cutoff):
    if s not in G:
        raise nx.NetworkXError(f"node {str(s)} not in graph")
    if t not in G:
        raise nx.NetworkXError(f"node {str(t)} not in graph")
    if s == t:
        raise nx.NetworkXError("source and sink are the same node")

    if residual is None:
        R = build_residual_network(G, capacity)
    else:
        R = residual

    # Initialize/reset the residual network.
    # This is way too slow
    # nx.set_edge_attributes(R, 0, 'flow')
    for u in R:
        for e in R[u].values():
            e["flow"] = 0

    # Use an arbitrary high value as infinite. It is computed
    # when building the residual network.
    INF = R.graph["inf"]

    if cutoff is None:
        cutoff = INF

    R_succ = R.succ
    R_pred = R.pred

    def grow():
        """Bidirectional breadth-first search for the growth stage.

        Returns a connecting edge, that is and edge that connects
        a node from the source search tree with a node from the
        target search tree.
        The first node in the connecting edge is always from the
        source tree and the last node from the target tree.
        """
        while active:
            u = active[0]
            if u in source_tree:
                this_tree = source_tree
                other_tree = target_tree
                neighbors = R_succ
            else:
                this_tree = target_tree
                other_tree = source_tree
                neighbors = R_pred
            for v, attr in neighbors[u].items():
                if attr["capacity"] - attr["flow"] > 0:
                    if v not in this_tree:
                        if v in other_tree:
                            return (u, v) if this_tree is source_tree else (v, u)
                        this_tree[v] = u
                        dist[v] = dist[u] + 1
                        timestamp[v] = timestamp[u]
                        active.append(v)
                    elif v in this_tree and _is_closer(u, v):
                        this_tree[v] = u
                        dist[v] = dist[u] + 1
                        timestamp[v] = timestamp[u]
            _ = active.popleft()
        return None, None

    def augment(u, v):
        """Augmentation stage.

        Reconstruct path and determine its residual capacity.
        We start from a connecting edge, which links a node
        from the source tree to a node from the target tree.
        The connecting edge is the output of the grow function
        and the input of this function.
        """
        attr = R_succ[u][v]
        flow = min(INF, attr["capacity"] - attr["flow"])
        path = [u]
        # Trace a path from u to s in source_tree.
        w = u
        while w != s:
            n = w
            w = source_tree[n]
            attr = R_pred[n][w]
            flow = min(flow, attr["capacity"] - attr["flow"])
            path.append(w)
        path.reverse()
        # Trace a path from v to t in target_tree.
        path.append(v)
        w = v
        while w != t:
            n = w
            w = target_tree[n]
            attr = R_succ[n][w]
            flow = min(flow, attr["capacity"] - attr["flow"])
            path.append(w)
        # Augment flow along the path and check for saturated edges.
        it = iter(path)
        u = next(it)
        these_orphans = []
        for v in it:
            R_succ[u][v]["flow"] += flow
            R_succ[v][u]["flow"] -= flow
            if R_succ[u][v]["flow"] == R_succ[u][v]["capacity"]:
                if v in source_tree:
                    source_tree[v] = None
                    these_orphans.append(v)
                if u in target_tree:
                    target_tree[u] = None
                    these_orphans.append(u)
            u = v
        orphans.extend(sorted(these_orphans, key=dist.get))
        return flow

    def adopt():
        """Adoption stage.

        Reconstruct search trees by adopting or discarding orphans.
        During augmentation stage some edges got saturated and thus
        the source and target search trees broke down to forests, with
        orphans as roots of some of its trees. We have to reconstruct
        the search trees rooted to source and target before we can grow
        them again.
        """
        while orphans:
            u = orphans.popleft()
            if u in source_tree:
                tree = source_tree
                neighbors = R_pred
            else:
                tree = target_tree
                neighbors = R_succ
            nbrs = ((n, attr, dist[n]) for n, attr in neighbors[u].items() if n in tree)
            for v, attr, d in sorted(nbrs, key=itemgetter(2)):
                if attr["capacity"] - attr["flow"] > 0:
                    if _has_valid_root(v, tree):
                        tree[u] = v
                        dist[u] = dist[v] + 1
                        timestamp[u] = time
                        break
            else:
                nbrs = (
                    (n, attr, dist[n]) for n, attr in neighbors[u].items() if n in tree
                )
                for v, attr, d in sorted(nbrs, key=itemgetter(2)):
                    if attr["capacity"] - attr["flow"] > 0:
                        if v not in active:
                            active.append(v)
                    if tree[v] == u:
                        tree[v] = None
                        orphans.appendleft(v)
                if u in active:
                    active.remove(u)
                del tree[u]

    def _has_valid_root(n, tree):
        path = []
        v = n
        while v is not None:
            path.append(v)
            if v in (s, t):
                base_dist = 0
                break
            elif timestamp[v] == time:
                base_dist = dist[v]
                break
            v = tree[v]
        else:
            return False
        length = len(path)
        for i, u in enumerate(path, 1):
            dist[u] = base_dist + length - i
            timestamp[u] = time
        return True

    def _is_closer(u, v):
        return timestamp[v] <= timestamp[u] and dist[v] > dist[u] + 1

    source_tree = {s: None}
    target_tree = {t: None}
    active = deque([s, t])
    orphans = deque()
    flow_value = 0
    # data structures for the marking heuristic
    time = 1
    timestamp = {s: time, t: time}
    dist = {s: 0, t: 0}
    while flow_value < cutoff:
        # Growth stage
        u, v = grow()
        if u is None:
            break
        time += 1
        # Augmentation stage
        flow_value += augment(u, v)
        # Adoption stage
        adopt()

    if flow_value * 2 > INF:
        raise nx.NetworkXUnbounded("Infinite capacity path, flow unbounded above.")

    # Add source and target tree in a graph attribute.
    # A partition that defines a minimum cut can be directly
    # computed from the search trees as explained in the docstrings.
    R.graph["trees"] = (source_tree, target_tree)
    # Add the standard flow_value graph attribute.
    R.graph["flow_value"] = flow_value
    return R
