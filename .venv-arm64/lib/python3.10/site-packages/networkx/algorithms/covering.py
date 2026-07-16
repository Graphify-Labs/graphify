"""Functions related to graph covers."""

from functools import partial
from itertools import chain

import networkx as nx
from networkx.utils import arbitrary_element, not_implemented_for

__all__ = ["min_edge_cover", "is_edge_cover"]


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def min_edge_cover(G, matching_algorithm=None):
    """Returns the min cardinality edge cover of the graph as a set of edges.

    A smallest edge cover can be found in polynomial time by finding
    a maximum matching and extending it greedily so that all nodes
    are covered. This function follows that process. A maximum matching
    algorithm can be specified for the first step of the algorithm.
    The resulting set may return a set with one 2-tuple for each edge,
    (the usual case) or with both 2-tuples `(u, v)` and `(v, u)` for
    each edge. The latter is only done when a bipartite matching algorithm
    is specified as `matching_algorithm`.

    Parameters
    ----------
    G : NetworkX graph
        An undirected graph.

    matching_algorithm : function
        A function that returns a maximum cardinality matching for `G`.
        The function must take one input, the graph `G`, and return
        either a set of edges (with only one direction for the pair of nodes)
        or a dictionary mapping each node to its mate. If not specified,
        :func:`~networkx.algorithms.matching.max_weight_matching` is used.
        Common bipartite matching functions include
        :func:`~networkx.algorithms.bipartite.matching.hopcroft_karp_matching`
        or
        :func:`~networkx.algorithms.bipartite.matching.eppstein_matching`.

    Returns
    -------
    min_cover : set

        A set of the edges in a minimum edge cover in the form of tuples.
        It contains only one of the equivalent 2-tuples `(u, v)` and `(v, u)`
        for each edge. If a bipartite method is used to compute the matching,
        the returned set contains both the 2-tuples `(u, v)` and `(v, u)`
        for each edge of a minimum edge cover.

    Examples
    --------
    >>> G = nx.Graph([(0, 1), (0, 2), (0, 3), (1, 2), (1, 3)])
    >>> sorted(nx.min_edge_cover(G))
    [(2, 1), (3, 0)]

    Notes
    -----
    An edge cover of a graph is a set of edges such that every node of
    the graph is incident to at least one edge of the set.
    The minimum edge cover is an edge covering of smallest cardinality.

    Due to its implementation, the worst-case running time of this algorithm
    is bounded by the worst-case running time of the function
    ``matching_algorithm``.

    Minimum edge cover for `G` can also be found using the `min_edge_covering`
    function in :mod:`networkx.algorithms.bipartite.covering` which is
    simply this function with a default matching algorithm of
    :func:`~networkx.algorithms.bipartite.matching.hopcraft_karp_matching`
    """
    if len(G) == 0:
        return set()
    if nx.number_of_isolates(G) > 0:
        # ``min_cover`` does not exist as there is an isolated node
        raise nx.NetworkXException(
            "Graph has a node with no edge incident on it, so no edge cover exists."
        )
    if matching_algorithm is None:
        matching_algorithm = partial(nx.max_weight_matching, maxcardinality=True)
    maximum_matching = matching_algorithm(G)
    # ``min_cover`` is superset of ``maximum_matching``
    try:
        # bipartite matching algs return dict so convert if needed
        min_cover = set(maximum_matching.items())
        bipartite_cover = True
    except AttributeError:
        min_cover = maximum_matching
        bipartite_cover = False
    # iterate for uncovered nodes
    uncovered_nodes = set(G) - {v for u, v in min_cover} - {u for u, v in min_cover}
    for v in uncovered_nodes:
        # Since `v` is uncovered, each edge incident to `v` will join it
        # with a covered node (otherwise, if there were an edge joining
        # uncovered nodes `u` and `v`, the maximum matching algorithm
        # would have found it), so we can choose an arbitrary edge
        # incident to `v`. (This applies only in a simple graph, not a
        # multigraph.)
        u = arbitrary_element(G[v])
        min_cover.add((u, v))
        if bipartite_cover:
            min_cover.add((v, u))
    return min_cover


@not_implemented_for("directed")
@nx._dispatchable
def is_edge_cover(G, cover):
    """Decides whether a set of edges is a valid edge cover of the graph.

    Given a set of edges, whether it is an edge covering can
    be decided if we just check whether all nodes of the graph
    has an edge from the set, incident on it.

    Parameters
    ----------
    G : NetworkX graph
        An undirected bipartite graph.

    cover : set
        Set of edges to be checked.

    Returns
    -------
    bool
        Whether the set of edges is a valid edge cover of the graph.

    Examples
    --------
    >>> G = nx.Graph([(0, 1), (0, 2), (0, 3), (1, 2), (1, 3)])
    >>> cover = {(2, 1), (3, 0)}
    >>> nx.is_edge_cover(G, cover)
    True

    Notes
    -----
    An edge cover of a graph is a set of edges such that every node of
    the graph is incident to at least one edge of the set.
    """
    return set(G) <= set(chain.from_iterable(cover))
