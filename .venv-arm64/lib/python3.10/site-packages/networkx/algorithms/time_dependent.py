"""Time dependent algorithms."""

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = ["cd_index"]


@not_implemented_for("undirected")
@not_implemented_for("multigraph")
@nx._dispatchable(node_attrs={"time": None, "weight": 1})
def cd_index(G, node, time_delta, *, time="time", weight=None):
    r"""Compute the CD index for `node` within the graph `G`.

    Calculates the CD index for the given node of the graph,
    considering only its predecessors who have the `time` attribute
    smaller than or equal to the `time` attribute of the `node`
    plus `time_delta`.

    Parameters
    ----------
    G : graph
       A directed networkx graph whose nodes have `time` attributes and optionally
       `weight` attributes (if a weight is not given, it is considered 1).
    node : node
       The node for which the CD index is calculated.
    time_delta : numeric or timedelta
       Amount of time after the `time` attribute of the `node`. The value of
       `time_delta` must support comparison with the `time` node attribute. For
       example, if the `time` attribute of the nodes are `datetime.datetime`
       objects, then `time_delta` should be a `datetime.timedelta` object.
    time : string (Optional, default is "time")
        The name of the node attribute that will be used for the calculations.
    weight : string (Optional, default is None)
        The name of the node attribute used as weight.

    Returns
    -------
    float
       The CD index calculated for the node `node` within the graph `G`.

    Raises
    ------
    NetworkXError
       If not all nodes have a `time` attribute or
       `time_delta` and `time` attribute types are not compatible or
       `n` equals 0.

    NetworkXNotImplemented
        If `G` is a non-directed graph or a multigraph.

    Examples
    --------
    >>> from datetime import datetime, timedelta
    >>> G = nx.DiGraph()
    >>> nodes = {
    ...     1: {"time": datetime(2015, 1, 1)},
    ...     2: {"time": datetime(2012, 1, 1), "weight": 4},
    ...     3: {"time": datetime(2010, 1, 1)},
    ...     4: {"time": datetime(2008, 1, 1)},
    ...     5: {"time": datetime(2014, 1, 1)},
    ... }
    >>> G.add_nodes_from([(n, nodes[n]) for n in nodes])
    >>> edges = [(1, 3), (1, 4), (2, 3), (3, 4), (3, 5)]
    >>> G.add_edges_from(edges)
    >>> delta = timedelta(days=5 * 365)
    >>> nx.cd_index(G, 3, time_delta=delta, time="time")
    0.5
    >>> nx.cd_index(G, 3, time_delta=delta, time="time", weight="weight")
    0.12

    Integers can also be used for the time values:
    >>> node_times = {1: 2015, 2: 2012, 3: 2010, 4: 2008, 5: 2014}
    >>> nx.set_node_attributes(G, node_times, "new_time")
    >>> nx.cd_index(G, 3, time_delta=4, time="new_time")
    0.5
    >>> nx.cd_index(G, 3, time_delta=4, time="new_time", weight="weight")
    0.12

    Notes
    -----
    This method implements the algorithm for calculating the CD index,
    as described in the paper by Funk and Owen-Smith [1]_. The CD index
    is used in order to check how consolidating or destabilizing a patent
    is, hence the nodes of the graph represent patents and the edges show
    the citations between these patents. The mathematical model is given
    below:

    .. math::
        CD_{t}=\frac{1}{n_{t}}\sum_{i=1}^{n}\frac{-2f_{it}b_{it}+f_{it}}{w_{it}},

    where `f_{it}` equals 1 if `i` cites the focal patent else 0, `b_{it}` equals
    1 if `i` cites any of the focal patents successors else 0, `n_{t}` is the number
    of forward citations in `i` and `w_{it}` is a matrix of weight for patent `i`
    at time `t`.

    The `datetime.timedelta` package can lead to off-by-one issues when converting
    from years to days. In the example above `timedelta(days=5 * 365)` looks like
    5 years, but it isn't because of leap year days. So it gives the same result
    as `timedelta(days=4 * 365)`. But using `timedelta(days=5 * 365 + 1)` gives
    a 5 year delta **for this choice of years** but may not if the 5 year gap has
    more than 1 leap year. To avoid these issues, use integers to represent years,
    or be very careful when you convert units of time.

    References
    ----------
    .. [1] Funk, Russell J., and Jason Owen-Smith.
           "A dynamic network measure of technological change."
           Management science 63, no. 3 (2017): 791-817.
           http://russellfunk.org/cdindex/static/papers/funk_ms_2017.pdf

    """
    if not all(time in G.nodes[n] for n in G):
        raise nx.NetworkXError("Not all nodes have a 'time' attribute.")

    try:
        # get target_date
        target_date = G.nodes[node][time] + time_delta
        # keep the predecessors that existed before the target date
        pred = {i for i in G.pred[node] if G.nodes[i][time] <= target_date}
    except:
        raise nx.NetworkXError(
            "Addition and comparison are not supported between 'time_delta' "
            "and 'time' types."
        )

    # -1 if any edge between node's predecessors and node's successors, else 1
    b = [-1 if any(j in G[i] for j in G[node]) else 1 for i in pred]

    # n is size of the union of the focal node's predecessors and its successors' predecessors
    n = len(pred.union(*(G.pred[s].keys() - {node} for s in G[node])))
    if n == 0:
        raise nx.NetworkXError("The cd index cannot be defined.")

    # calculate cd index
    if weight is None:
        return round(sum(bi for bi in b) / n, 2)
    else:
        # If a node has the specified weight attribute, its weight is used in the calculation
        # otherwise, a weight of 1 is assumed for that node
        weights = [G.nodes[i].get(weight, 1) for i in pred]
        return round(sum(bi / wt for bi, wt in zip(b, weights)) / n, 2)
