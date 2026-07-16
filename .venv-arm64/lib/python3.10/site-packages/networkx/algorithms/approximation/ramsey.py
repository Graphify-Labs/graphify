"""
Ramsey numbers.
"""

import networkx as nx
from networkx.utils import not_implemented_for

from ...utils import arbitrary_element

__all__ = ["ramsey_R2"]


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def ramsey_R2(G):
    r"""Compute the largest clique and largest independent set in `G`.

    This can be used to estimate bounds for the 2-color
    Ramsey number `R(2;s,t)` for `G`.

    This is a recursive implementation which could run into trouble
    for large recursions. Note that self-loop edges are ignored.

    Parameters
    ----------
    G : NetworkX graph
        Undirected graph

    Returns
    -------
    max_pair : (set, set) tuple
        Maximum clique, Maximum independent set.

    Raises
    ------
    NetworkXNotImplemented
        If the graph is directed or is a multigraph.
    """
    if not G:
        return set(), set()

    node = arbitrary_element(G)
    nbrs = (nbr for nbr in nx.all_neighbors(G, node) if nbr != node)
    nnbrs = nx.non_neighbors(G, node)
    c_1, i_1 = ramsey_R2(G.subgraph(nbrs).copy())
    c_2, i_2 = ramsey_R2(G.subgraph(nnbrs).copy())

    c_1.add(node)
    i_2.add(node)
    # Choose the larger of the two cliques and the larger of the two
    # independent sets, according to cardinality.
    return max(c_1, c_2, key=len), max(i_1, i_2, key=len)
