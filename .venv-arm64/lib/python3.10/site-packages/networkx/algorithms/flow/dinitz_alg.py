"""
Dinitz' algorithm for maximum flow problems.
"""

from collections import deque

import networkx as nx
from networkx.algorithms.flow.utils import build_residual_network
from networkx.utils import pairwise

__all__ = ["dinitz"]


@nx._dispatchable(edge_attrs={"capacity": float("inf")}, returns_graph=True)
def dinitz(G, s, t, capacity="capacity", residual=None, value_only=False, cutoff=None):
    """Find a maximum single-commodity flow using Dinitz' algorithm.

    This function returns the residual network resulting after computing
    the maximum flow. See below for details about the conventions
    NetworkX uses for defining residual networks.

    This algorithm has a running time of $O(n^2 m)$ for $n$ nodes and $m$
    edges [1]_.


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
    >>> from networkx.algorithms.flow import dinitz

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
    >>> R = dinitz(G, "x", "y")
    >>> flow_value = nx.maximum_flow_value(G, "x", "y")
    >>> flow_value
    3.0
    >>> flow_value == R.graph["flow_value"]
    True

    References
    ----------
    .. [1] Dinitz' Algorithm: The Original Version and Even's Version.
           2006. Yefim Dinitz. In Theoretical Computer Science. Lecture
           Notes in Computer Science. Volume 3895. pp 218-240.
           https://doi.org/10.1007/11685654_10

    """
    R = dinitz_impl(G, s, t, capacity, residual, cutoff)
    R.graph["algorithm"] = "dinitz"
    nx._clear_cache(R)
    return R


def dinitz_impl(G, s, t, capacity, residual, cutoff):
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

    def breath_first_search():
        parents = {}
        vertex_dist = {s: 0}
        queue = deque([(s, 0)])
        # Record all the potential edges of shortest augmenting paths
        while queue:
            if t in parents:
                break
            u, dist = queue.popleft()
            for v, attr in R_succ[u].items():
                if attr["capacity"] - attr["flow"] > 0:
                    if v in parents:
                        if vertex_dist[v] == dist + 1:
                            parents[v].append(u)
                    else:
                        parents[v] = deque([u])
                        vertex_dist[v] = dist + 1
                        queue.append((v, dist + 1))
        return parents

    def depth_first_search(parents):
        # DFS to find all the shortest augmenting paths
        """Build a path using DFS starting from the sink"""
        total_flow = 0
        u = t
        # path also functions as a stack
        path = [u]
        # The loop ends with no augmenting path left in the layered graph
        while True:
            if len(parents[u]) > 0:
                v = parents[u][0]
                path.append(v)
            else:
                path.pop()
                if len(path) == 0:
                    break
                v = path[-1]
                parents[v].popleft()
            # Augment the flow along the path found
            if v == s:
                flow = INF
                for u, v in pairwise(path):
                    flow = min(flow, R_pred[u][v]["capacity"] - R_pred[u][v]["flow"])
                for u, v in pairwise(reversed(path)):
                    R_pred[v][u]["flow"] += flow
                    R_pred[u][v]["flow"] -= flow
                    # Find the proper node to continue the search
                    if R_pred[v][u]["capacity"] - R_pred[v][u]["flow"] == 0:
                        parents[v].popleft()
                        while path[-1] != v:
                            path.pop()
                total_flow += flow
                v = path[-1]
            u = v
        return total_flow

    flow_value = 0
    while flow_value < cutoff:
        parents = breath_first_search()
        if t not in parents:
            break
        this_flow = depth_first_search(parents)
        if this_flow * 2 > INF:
            raise nx.NetworkXUnbounded("Infinite capacity path, flow unbounded above.")
        flow_value += this_flow

    R.graph["flow_value"] = flow_value
    return R
