"""Functions for computing the Voronoi cells of a graph."""

import networkx as nx
from networkx.utils import groups

__all__ = ["voronoi_cells"]


@nx._dispatchable(edge_attrs="weight")
def voronoi_cells(G, center_nodes, weight="weight"):
    """Returns the Voronoi cells centered at `center_nodes` with respect
    to the shortest-path distance metric.

    If $C$ is a set of nodes in the graph and $c$ is an element of $C$,
    the *Voronoi cell* centered at a node $c$ is the set of all nodes
    $v$ that are closer to $c$ than to any other center node in $C$ with
    respect to the shortest-path distance metric. [1]_

    For directed graphs, this will compute the "outward" Voronoi cells,
    as defined in [1]_, in which distance is measured from the center
    nodes to the target node. For the "inward" Voronoi cells, use the
    :meth:`DiGraph.reverse` method to reverse the orientation of the
    edges before invoking this function on the directed graph.

    Parameters
    ----------
    G : NetworkX graph

    center_nodes : set
        A nonempty set of nodes in the graph `G` that represent the
        center of the Voronoi cells.

    weight : string or function
        The edge attribute (or an arbitrary function) representing the
        weight of an edge. This keyword argument is as described in the
        documentation for :func:`~networkx.multi_source_dijkstra_path`,
        for example.

    Returns
    -------
    dictionary
        A mapping from center node to set of all nodes in the graph
        closer to that center node than to any other center node. The
        keys of the dictionary are the element of `center_nodes`, and
        the values of the dictionary form a partition of the nodes of
        `G`.

    Examples
    --------
    To get only the partition of the graph induced by the Voronoi cells,
    take the collection of all values in the returned dictionary::

        >>> G = nx.path_graph(6)
        >>> center_nodes = {0, 3}
        >>> cells = nx.voronoi_cells(G, center_nodes)
        >>> partition = set(map(frozenset, cells.values()))
        >>> sorted(map(sorted, partition))
        [[0, 1], [2, 3, 4, 5]]

    Raises
    ------
    ValueError
        If `center_nodes` is empty.

    References
    ----------
    .. [1] Erwig, Martin. (2000),"The graph Voronoi diagram with applications."
        *Networks*, 36: 156--163.
        https://doi.org/10.1002/1097-0037(200010)36:3<156::AID-NET2>3.0.CO;2-L

    """
    # Determine the shortest paths from any one of the center nodes to
    # every node in the graph.
    #
    # This raises `ValueError` if `center_nodes` is an empty set.
    paths = nx.multi_source_dijkstra_path(G, center_nodes, weight=weight)
    # Determine the center node from which the shortest path originates.
    nearest = {v: p[0] for v, p in paths.items()}
    # Get the mapping from center node to all nodes closer to it than to
    # any other center node.
    cells = groups(nearest)
    # We collect all unreachable nodes under a special key, if there are any.
    unreachable = set(G) - set(nearest)
    if unreachable:
        cells["unreachable"] = unreachable
    return cells
