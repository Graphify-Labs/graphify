"""
Shortest augmenting path algorithm for maximum flow problems.
"""

from collections import deque

import networkx as nx

from .edmondskarp import edmonds_karp_core
from .utils import CurrentEdge, build_residual_network

__all__ = ["shortest_augmenting_path"]


def shortest_augmenting_path_impl(G, s, t, capacity, residual, two_phase, cutoff):
    """Implementation of the shortest augmenting path algorithm."""
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

    R_nodes = R.nodes
    R_pred = R.pred
    R_succ = R.succ

    # Initialize/reset the residual network.
    for u in R:
        for e in R_succ[u].values():
            e["flow"] = 0

    # Initialize heights of the nodes.
    heights = {t: 0}
    q = deque([(t, 0)])
    while q:
        u, height = q.popleft()
        height += 1
        for v, attr in R_pred[u].items():
            if v not in heights and attr["flow"] < attr["capacity"]:
                heights[v] = height
                q.append((v, height))

    if s not in heights:
        # t is not reachable from s in the residual network. The maximum flow
        # must be zero.
        R.graph["flow_value"] = 0
        return R

    n = len(G)
    m = R.size() / 2

    # Initialize heights and 'current edge' data structures of the nodes.
    for u in R:
        R_nodes[u]["height"] = heights[u] if u in heights else n
        R_nodes[u]["curr_edge"] = CurrentEdge(R_succ[u])

    # Initialize counts of nodes in each level.
    counts = [0] * (2 * n - 1)
    for u in R:
        counts[R_nodes[u]["height"]] += 1

    inf = R.graph["inf"]

    def augment(path):
        """Augment flow along a path from s to t."""
        # Determine the path residual capacity.
        flow = inf
        it = iter(path)
        u = next(it)
        for v in it:
            attr = R_succ[u][v]
            flow = min(flow, attr["capacity"] - attr["flow"])
            u = v
        if flow * 2 > inf:
            raise nx.NetworkXUnbounded("Infinite capacity path, flow unbounded above.")
        # Augment flow along the path.
        it = iter(path)
        u = next(it)
        for v in it:
            R_succ[u][v]["flow"] += flow
            R_succ[v][u]["flow"] -= flow
            u = v
        return flow

    def relabel(u):
        """Relabel a node to create an admissible edge."""
        height = n - 1
        for v, attr in R_succ[u].items():
            if attr["flow"] < attr["capacity"]:
                height = min(height, R_nodes[v]["height"])
        return height + 1

    if cutoff is None:
        cutoff = float("inf")

    # Phase 1: Look for shortest augmenting paths using depth-first search.

    flow_value = 0
    path = [s]
    u = s
    d = n if not two_phase else int(min(m**0.5, 2 * n ** (2.0 / 3)))
    done = R_nodes[s]["height"] >= d
    while not done:
        height = R_nodes[u]["height"]
        curr_edge = R_nodes[u]["curr_edge"]
        # Depth-first search for the next node on the path to t.
        while True:
            v, attr = curr_edge.get()
            if height == R_nodes[v]["height"] + 1 and attr["flow"] < attr["capacity"]:
                # Advance to the next node following an admissible edge.
                path.append(v)
                u = v
                break
            try:
                curr_edge.move_to_next()
            except StopIteration:
                counts[height] -= 1
                if counts[height] == 0:
                    # Gap heuristic: If relabeling causes a level to become
                    # empty, a minimum cut has been identified. The algorithm
                    # can now be terminated.
                    R.graph["flow_value"] = flow_value
                    return R
                height = relabel(u)
                if u == s and height >= d:
                    if not two_phase:
                        # t is disconnected from s in the residual network. No
                        # more augmenting paths exist.
                        R.graph["flow_value"] = flow_value
                        return R
                    else:
                        # t is at least d steps away from s. End of phase 1.
                        done = True
                        break
                counts[height] += 1
                R_nodes[u]["height"] = height
                if u != s:
                    # After relabeling, the last edge on the path is no longer
                    # admissible. Retreat one step to look for an alternative.
                    path.pop()
                    u = path[-1]
                    break
        if u == t:
            # t is reached. Augment flow along the path and reset it for a new
            # depth-first search.
            flow_value += augment(path)
            if flow_value >= cutoff:
                R.graph["flow_value"] = flow_value
                return R
            path = [s]
            u = s

    # Phase 2: Look for shortest augmenting paths using breadth-first search.
    flow_value += edmonds_karp_core(R, s, t, cutoff - flow_value)

    R.graph["flow_value"] = flow_value
    return R


@nx._dispatchable(edge_attrs={"capacity": float("inf")}, returns_graph=True)
def shortest_augmenting_path(
    G,
    s,
    t,
    capacity="capacity",
    residual=None,
    value_only=False,
    two_phase=False,
    cutoff=None,
):
    r"""Find a maximum single-commodity flow using the shortest augmenting path
    algorithm.

    This function returns the residual network resulting after computing
    the maximum flow. See below for details about the conventions
    NetworkX uses for defining residual networks.

    This algorithm has a running time of $O(n^2 m)$ for $n$ nodes and $m$
    edges.


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

    two_phase : bool
        If True, a two-phase variant is used. The two-phase variant improves
        the running time on unit-capacity networks from $O(nm)$ to
        $O(\min(n^{2/3}, m^{1/2}) m)$. Default value: False.

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
    :meth:`edmonds_karp`
    :meth:`preflow_push`

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
    >>> from networkx.algorithms.flow import shortest_augmenting_path

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
    >>> R = shortest_augmenting_path(G, "x", "y")
    >>> flow_value = nx.maximum_flow_value(G, "x", "y")
    >>> flow_value
    3.0
    >>> flow_value == R.graph["flow_value"]
    True

    """
    R = shortest_augmenting_path_impl(G, s, t, capacity, residual, two_phase, cutoff)
    R.graph["algorithm"] = "shortest_augmenting_path"
    nx._clear_cache(R)
    return R
