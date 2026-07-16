r"""Function for computing the moral graph of a directed graph."""

import itertools

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = ["moral_graph"]


@not_implemented_for("undirected")
@nx._dispatchable(returns_graph=True)
def moral_graph(G):
    r"""Return the Moral Graph

    Returns the moralized graph of a given directed graph.

    Parameters
    ----------
    G : NetworkX graph
        Directed graph

    Returns
    -------
    H : NetworkX graph
        The undirected moralized graph of G

    Raises
    ------
    NetworkXNotImplemented
        If `G` is undirected.

    Examples
    --------
    >>> G = nx.DiGraph([(1, 2), (2, 3), (2, 5), (3, 4), (4, 3)])
    >>> G_moral = nx.moral_graph(G)
    >>> G_moral.edges()
    EdgeView([(1, 2), (2, 3), (2, 5), (2, 4), (3, 4)])

    Notes
    -----
    A moral graph is an undirected graph H = (V, E) generated from a
    directed Graph, where if a node has more than one parent node, edges
    between these parent nodes are inserted and all directed edges become
    undirected.

    https://en.wikipedia.org/wiki/Moral_graph

    References
    ----------
    .. [1] Wray L. Buntine. 1995. Chain graphs for learning.
           In Proceedings of the Eleventh conference on Uncertainty
           in artificial intelligence (UAI'95)
    """
    H = G.to_undirected()
    for preds in G.pred.values():
        predecessors_combinations = itertools.combinations(preds, r=2)
        H.add_edges_from(predecessors_combinations)
    return H
