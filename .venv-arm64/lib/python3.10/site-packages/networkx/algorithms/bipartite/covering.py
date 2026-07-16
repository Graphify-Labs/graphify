"""Functions related to graph covers."""

import networkx as nx
from networkx.algorithms.bipartite.matching import hopcroft_karp_matching
from networkx.algorithms.covering import min_edge_cover as _min_edge_cover
from networkx.utils import not_implemented_for

__all__ = ["min_edge_cover"]


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable(name="bipartite_min_edge_cover")
def min_edge_cover(G, matching_algorithm=None):
    """Returns a set of edges which constitutes
    the minimum edge cover of the graph.

    The smallest edge cover can be found in polynomial time by finding
    a maximum matching and extending it greedily so that all nodes
    are covered.

    Parameters
    ----------
    G : NetworkX graph
        An undirected bipartite graph.

    matching_algorithm : function
        A function that returns a maximum cardinality matching in a
        given bipartite graph. The function must take one input, the
        graph ``G``, and return a dictionary mapping each node to its
        mate. If not specified,
        :func:`~networkx.algorithms.bipartite.matching.hopcroft_karp_matching`
        will be used. Other possibilities include
        :func:`~networkx.algorithms.bipartite.matching.eppstein_matching`,

    Returns
    -------
    set
        A set of the edges in a minimum edge cover of the graph, given as
        pairs of nodes. It contains both the edges `(u, v)` and `(v, u)`
        for given nodes `u` and `v` among the edges of minimum edge cover.

    Notes
    -----
    An edge cover of a graph is a set of edges such that every node of
    the graph is incident to at least one edge of the set.
    A minimum edge cover is an edge covering of smallest cardinality.

    Due to its implementation, the worst-case running time of this algorithm
    is bounded by the worst-case running time of the function
    ``matching_algorithm``.
    """
    if G.order() == 0:  # Special case for the empty graph
        return set()
    if matching_algorithm is None:
        matching_algorithm = hopcroft_karp_matching
    return _min_edge_cover(G, matching_algorithm=matching_algorithm)
