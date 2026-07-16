"""
Minimum cost flow algorithms on directed connected graphs.
"""

__all__ = ["min_cost_flow_cost", "min_cost_flow", "cost_of_flow", "max_flow_min_cost"]

import networkx as nx


@nx._dispatchable(
    node_attrs="demand", edge_attrs={"capacity": float("inf"), "weight": 0}
)
def min_cost_flow_cost(G, demand="demand", capacity="capacity", weight="weight"):
    r"""Find the cost of a minimum cost flow satisfying all demands in digraph G.

    G is a digraph with edge costs and capacities and in which nodes
    have demand, i.e., they want to send or receive some amount of
    flow. A negative demand means that the node wants to send flow, a
    positive demand means that the node want to receive flow. A flow on
    the digraph G satisfies all demand if the net flow into each node
    is equal to the demand of that node.

    Parameters
    ----------
    G : NetworkX graph
        DiGraph on which a minimum cost flow satisfying all demands is
        to be found.

    demand : string
        Nodes of the graph G are expected to have an attribute demand
        that indicates how much flow a node wants to send (negative
        demand) or receive (positive demand). Note that the sum of the
        demands should be 0 otherwise the problem in not feasible. If
        this attribute is not present, a node is considered to have 0
        demand. Default value: 'demand'.

    capacity : string
        Edges of the graph G are expected to have an attribute capacity
        that indicates how much flow the edge can support. If this
        attribute is not present, the edge is considered to have
        infinite capacity. Default value: 'capacity'.

    weight : string
        Edges of the graph G are expected to have an attribute weight
        that indicates the cost incurred by sending one unit of flow on
        that edge. If not present, the weight is considered to be 0.
        Default value: 'weight'.

    Returns
    -------
    flowCost : integer, float
        Cost of a minimum cost flow satisfying all demands.

    Raises
    ------
    NetworkXError
        This exception is raised if the input graph is not directed or
        not connected.

    NetworkXUnfeasible
        This exception is raised in the following situations:

            * The sum of the demands is not zero. Then, there is no
              flow satisfying all demands.
            * There is no flow satisfying all demand.

    NetworkXUnbounded
        This exception is raised if the digraph G has a cycle of
        negative cost and infinite capacity. Then, the cost of a flow
        satisfying all demands is unbounded below.

    See also
    --------
    cost_of_flow, max_flow_min_cost, min_cost_flow, network_simplex

    Notes
    -----
    This algorithm is not guaranteed to work if edge weights or demands
    are floating point numbers (overflows and roundoff errors can
    cause problems). As a workaround you can use integer numbers by
    multiplying the relevant edge attributes by a convenient
    constant factor (eg 100).

    Examples
    --------
    A simple example of a min cost flow problem.

    >>> G = nx.DiGraph()
    >>> G.add_node("a", demand=-5)
    >>> G.add_node("d", demand=5)
    >>> G.add_edge("a", "b", weight=3, capacity=4)
    >>> G.add_edge("a", "c", weight=6, capacity=10)
    >>> G.add_edge("b", "d", weight=1, capacity=9)
    >>> G.add_edge("c", "d", weight=2, capacity=5)
    >>> flowCost = nx.min_cost_flow_cost(G)
    >>> flowCost
    24
    """
    return nx.network_simplex(G, demand=demand, capacity=capacity, weight=weight)[0]


@nx._dispatchable(
    node_attrs="demand", edge_attrs={"capacity": float("inf"), "weight": 0}
)
def min_cost_flow(G, demand="demand", capacity="capacity", weight="weight"):
    r"""Returns a minimum cost flow satisfying all demands in digraph G.

    G is a digraph with edge costs and capacities and in which nodes
    have demand, i.e., they want to send or receive some amount of
    flow. A negative demand means that the node wants to send flow, a
    positive demand means that the node want to receive flow. A flow on
    the digraph G satisfies all demand if the net flow into each node
    is equal to the demand of that node.

    Parameters
    ----------
    G : NetworkX graph
        DiGraph on which a minimum cost flow satisfying all demands is
        to be found.

    demand : string
        Nodes of the graph G are expected to have an attribute demand
        that indicates how much flow a node wants to send (negative
        demand) or receive (positive demand). Note that the sum of the
        demands should be 0 otherwise the problem in not feasible. If
        this attribute is not present, a node is considered to have 0
        demand. Default value: 'demand'.

    capacity : string
        Edges of the graph G are expected to have an attribute capacity
        that indicates how much flow the edge can support. If this
        attribute is not present, the edge is considered to have
        infinite capacity. Default value: 'capacity'.

    weight : string
        Edges of the graph G are expected to have an attribute weight
        that indicates the cost incurred by sending one unit of flow on
        that edge. If not present, the weight is considered to be 0.
        Default value: 'weight'.

    Returns
    -------
    flowDict : dictionary
        Dictionary of dictionaries keyed by nodes such that
        flowDict[u][v] is the flow edge (u, v).

    Raises
    ------
    NetworkXError
        This exception is raised if the input graph is not directed or
        not connected.

    NetworkXUnfeasible
        This exception is raised in the following situations:

            * The sum of the demands is not zero. Then, there is no
              flow satisfying all demands.
            * There is no flow satisfying all demand.

    NetworkXUnbounded
        This exception is raised if the digraph G has a cycle of
        negative cost and infinite capacity. Then, the cost of a flow
        satisfying all demands is unbounded below.

    See also
    --------
    cost_of_flow, max_flow_min_cost, min_cost_flow_cost, network_simplex

    Notes
    -----
    This algorithm is not guaranteed to work if edge weights or demands
    are floating point numbers (overflows and roundoff errors can
    cause problems). As a workaround you can use integer numbers by
    multiplying the relevant edge attributes by a convenient
    constant factor (eg 100).

    Examples
    --------
    A simple example of a min cost flow problem.

    >>> G = nx.DiGraph()
    >>> G.add_node("a", demand=-5)
    >>> G.add_node("d", demand=5)
    >>> G.add_edge("a", "b", weight=3, capacity=4)
    >>> G.add_edge("a", "c", weight=6, capacity=10)
    >>> G.add_edge("b", "d", weight=1, capacity=9)
    >>> G.add_edge("c", "d", weight=2, capacity=5)
    >>> flowDict = nx.min_cost_flow(G)
    >>> flowDict
    {'a': {'b': 4, 'c': 1}, 'd': {}, 'b': {'d': 4}, 'c': {'d': 1}}
    """
    return nx.network_simplex(G, demand=demand, capacity=capacity, weight=weight)[1]


@nx._dispatchable(edge_attrs={"weight": 0})
def cost_of_flow(G, flowDict, weight="weight"):
    """Compute the cost of the flow given by flowDict on graph G.

    Note that this function does not check for the validity of the
    flow flowDict. This function will fail if the graph G and the
    flow don't have the same edge set.

    Parameters
    ----------
    G : NetworkX graph
        DiGraph on which a minimum cost flow satisfying all demands is
        to be found.

    weight : string
        Edges of the graph G are expected to have an attribute weight
        that indicates the cost incurred by sending one unit of flow on
        that edge. If not present, the weight is considered to be 0.
        Default value: 'weight'.

    flowDict : dictionary
        Dictionary of dictionaries keyed by nodes such that
        flowDict[u][v] is the flow edge (u, v).

    Returns
    -------
    cost : Integer, float
        The total cost of the flow. This is given by the sum over all
        edges of the product of the edge's flow and the edge's weight.

    See also
    --------
    max_flow_min_cost, min_cost_flow, min_cost_flow_cost, network_simplex

    Notes
    -----
    This algorithm is not guaranteed to work if edge weights or demands
    are floating point numbers (overflows and roundoff errors can
    cause problems). As a workaround you can use integer numbers by
    multiplying the relevant edge attributes by a convenient
    constant factor (eg 100).

    Examples
    --------
    >>> G = nx.DiGraph()
    >>> G.add_node("a", demand=-5)
    >>> G.add_node("d", demand=5)
    >>> G.add_edge("a", "b", weight=3, capacity=4)
    >>> G.add_edge("a", "c", weight=6, capacity=10)
    >>> G.add_edge("b", "d", weight=1, capacity=9)
    >>> G.add_edge("c", "d", weight=2, capacity=5)
    >>> flowDict = nx.min_cost_flow(G)
    >>> flowDict
    {'a': {'b': 4, 'c': 1}, 'd': {}, 'b': {'d': 4}, 'c': {'d': 1}}
    >>> nx.cost_of_flow(G, flowDict)
    24
    """
    return sum((flowDict[u][v] * d.get(weight, 0) for u, v, d in G.edges(data=True)))


@nx._dispatchable(edge_attrs={"capacity": float("inf"), "weight": 0})
def max_flow_min_cost(G, s, t, capacity="capacity", weight="weight"):
    """Returns a maximum (s, t)-flow of minimum cost.

    G is a digraph with edge costs and capacities. There is a source
    node s and a sink node t. This function finds a maximum flow from
    s to t whose total cost is minimized.

    Parameters
    ----------
    G : NetworkX graph
        DiGraph on which a minimum cost flow satisfying all demands is
        to be found.

    s: node label
        Source of the flow.

    t: node label
        Destination of the flow.

    capacity: string
        Edges of the graph G are expected to have an attribute capacity
        that indicates how much flow the edge can support. If this
        attribute is not present, the edge is considered to have
        infinite capacity. Default value: 'capacity'.

    weight: string
        Edges of the graph G are expected to have an attribute weight
        that indicates the cost incurred by sending one unit of flow on
        that edge. If not present, the weight is considered to be 0.
        Default value: 'weight'.

    Returns
    -------
    flowDict: dictionary
        Dictionary of dictionaries keyed by nodes such that
        flowDict[u][v] is the flow edge (u, v).

    Raises
    ------
    NetworkXError
        This exception is raised if the input graph is not directed or
        not connected.

    NetworkXUnbounded
        This exception is raised if there is an infinite capacity path
        from s to t in G. In this case there is no maximum flow. This
        exception is also raised if the digraph G has a cycle of
        negative cost and infinite capacity. Then, the cost of a flow
        is unbounded below.

    See also
    --------
    cost_of_flow, min_cost_flow, min_cost_flow_cost, network_simplex

    Notes
    -----
    This algorithm is not guaranteed to work if edge weights or demands
    are floating point numbers (overflows and roundoff errors can
    cause problems). As a workaround you can use integer numbers by
    multiplying the relevant edge attributes by a convenient
    constant factor (eg 100).

    Examples
    --------
    >>> G = nx.DiGraph()
    >>> G.add_edges_from(
    ...     [
    ...         (1, 2, {"capacity": 12, "weight": 4}),
    ...         (1, 3, {"capacity": 20, "weight": 6}),
    ...         (2, 3, {"capacity": 6, "weight": -3}),
    ...         (2, 6, {"capacity": 14, "weight": 1}),
    ...         (3, 4, {"weight": 9}),
    ...         (3, 5, {"capacity": 10, "weight": 5}),
    ...         (4, 2, {"capacity": 19, "weight": 13}),
    ...         (4, 5, {"capacity": 4, "weight": 0}),
    ...         (5, 7, {"capacity": 28, "weight": 2}),
    ...         (6, 5, {"capacity": 11, "weight": 1}),
    ...         (6, 7, {"weight": 8}),
    ...         (7, 4, {"capacity": 6, "weight": 6}),
    ...     ]
    ... )
    >>> mincostFlow = nx.max_flow_min_cost(G, 1, 7)
    >>> mincost = nx.cost_of_flow(G, mincostFlow)
    >>> mincost
    373
    >>> from networkx.algorithms.flow import maximum_flow
    >>> maxFlow = maximum_flow(G, 1, 7)[1]
    >>> nx.cost_of_flow(G, maxFlow) >= mincost
    True
    >>> mincostFlowValue = sum((mincostFlow[u][7] for u in G.predecessors(7))) - sum(
    ...     (mincostFlow[7][v] for v in G.successors(7))
    ... )
    >>> mincostFlowValue == nx.maximum_flow_value(G, 1, 7)
    True

    """
    maxFlow = nx.maximum_flow_value(G, s, t, capacity=capacity)
    H = nx.DiGraph(G)
    H.add_node(s, demand=-maxFlow)
    H.add_node(t, demand=maxFlow)
    return min_cost_flow(H, capacity=capacity, weight=weight)
