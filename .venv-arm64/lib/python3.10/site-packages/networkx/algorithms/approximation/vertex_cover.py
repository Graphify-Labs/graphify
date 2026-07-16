"""Functions for computing an approximate minimum weight vertex cover.

A |vertex cover|_ is a subset of nodes such that each edge in the graph
is incident to at least one node in the subset.

.. _vertex cover: https://en.wikipedia.org/wiki/Vertex_cover
.. |vertex cover| replace:: *vertex cover*

"""

import networkx as nx

__all__ = ["min_weighted_vertex_cover"]


@nx._dispatchable(node_attrs="weight")
def min_weighted_vertex_cover(G, weight=None):
    r"""Returns an approximate minimum weighted vertex cover.

    The set of nodes returned by this function is guaranteed to be a
    vertex cover, and the total weight of the set is guaranteed to be at
    most twice the total weight of the minimum weight vertex cover. In
    other words,

    .. math::

       w(S) \leq 2 * w(S^*),

    where $S$ is the vertex cover returned by this function,
    $S^*$ is the vertex cover of minimum weight out of all vertex
    covers of the graph, and $w$ is the function that computes the
    sum of the weights of each node in that given set.

    Parameters
    ----------
    G : NetworkX graph

    weight : string, optional (default = None)
        If None, every node has weight 1. If a string, use this node
        attribute as the node weight. A node without this attribute is
        assumed to have weight 1.

    Returns
    -------
    min_weighted_cover : set
        Returns a set of nodes whose weight sum is no more than twice
        the weight sum of the minimum weight vertex cover.

    Notes
    -----
    For a directed graph, a vertex cover has the same definition: a set
    of nodes such that each edge in the graph is incident to at least
    one node in the set. Whether the node is the head or tail of the
    directed edge is ignored.

    This is the local-ratio algorithm for computing an approximate
    vertex cover. The algorithm greedily reduces the costs over edges,
    iteratively building a cover. The worst-case runtime of this
    implementation is $O(m \log n)$, where $n$ is the number
    of nodes and $m$ the number of edges in the graph.

    References
    ----------
    .. [1] Bar-Yehuda, R., and Even, S. (1985). "A local-ratio theorem for
       approximating the weighted vertex cover problem."
       *Annals of Discrete Mathematics*, 25, 27–46
       <http://www.cs.technion.ac.il/~reuven/PDF/vc_lr.pdf>

    """
    cost = dict(G.nodes(data=weight, default=1))
    # While there are uncovered edges, choose an uncovered and update
    # the cost of the remaining edges.
    cover = set()
    for u, v in G.edges():
        if u in cover or v in cover:
            continue
        if cost[u] <= cost[v]:
            cover.add(u)
            cost[v] -= cost[u]
        else:
            cover.add(v)
            cost[u] -= cost[v]
    return cover
