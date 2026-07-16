"""
Time Series Graphs
"""

import itertools

import networkx as nx

__all__ = ["visibility_graph"]


@nx._dispatchable(graphs=None, returns_graph=True)
def visibility_graph(series):
    """
    Return a Visibility Graph of an input Time Series.

    A visibility graph converts a time series into a graph. The constructed graph
    uses integer nodes to indicate which event in the series the node represents.
    Edges are formed as follows: consider a bar plot of the series and view that
    as a side view of a landscape with a node at the top of each bar. An edge
    means that the nodes can be connected by a straight "line-of-sight" without
    being obscured by any bars between the nodes.

    The resulting graph inherits several properties of the series in its structure.
    Thereby, periodic series convert into regular graphs, random series convert
    into random graphs, and fractal series convert into scale-free networks [1]_.

    Parameters
    ----------
    series : Sequence[Number]
       A Time Series sequence (iterable and sliceable) of numeric values
       representing times.

    Returns
    -------
    NetworkX Graph
        The Visibility Graph of the input series

    Examples
    --------
    >>> series_list = [range(10), [2, 1, 3, 2, 1, 3, 2, 1, 3, 2, 1, 3]]
    >>> for s in series_list:
    ...     g = nx.visibility_graph(s)
    ...     print(g)
    Graph with 10 nodes and 9 edges
    Graph with 12 nodes and 18 edges

    References
    ----------
    .. [1] Lacasa, Lucas, Bartolo Luque, Fernando Ballesteros, Jordi Luque, and Juan Carlos Nuno.
           "From time series to complex networks: The visibility graph." Proceedings of the
           National Academy of Sciences 105, no. 13 (2008): 4972-4975.
           https://www.pnas.org/doi/10.1073/pnas.0709247105
    """

    # Sequential values are always connected
    G = nx.path_graph(len(series))
    nx.set_node_attributes(G, dict(enumerate(series)), "value")

    # Check all combinations of nodes n series
    for (n1, t1), (n2, t2) in itertools.combinations(enumerate(series), 2):
        # check if any value between obstructs line of sight
        slope = (t2 - t1) / (n2 - n1)
        offset = t2 - slope * n2

        obstructed = any(
            t >= slope * n + offset
            for n, t in enumerate(series[n1 + 1 : n2], start=n1 + 1)
        )

        if not obstructed:
            G.add_edge(n1, n2)

    return G
