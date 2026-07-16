"""Functions for generating stochastic graphs from a given weighted directed
graph.

"""

import networkx as nx
from networkx.classes import DiGraph, MultiDiGraph
from networkx.utils import not_implemented_for

__all__ = ["stochastic_graph"]


@not_implemented_for("undirected")
@nx._dispatchable(
    edge_attrs="weight", mutates_input={"not copy": 1}, returns_graph=True
)
def stochastic_graph(G, copy=True, weight="weight"):
    """Returns a right-stochastic representation of directed graph `G`.

    A right-stochastic graph is a weighted digraph in which for each
    node, the sum of the weights of all the out-edges of that node is
    1. If the graph is already weighted (for example, via a 'weight'
    edge attribute), the reweighting takes that into account.

    Parameters
    ----------
    G : directed graph
        A :class:`~networkx.DiGraph` or :class:`~networkx.MultiDiGraph`.

    copy : boolean, optional
        If this is True, then this function returns a new graph with
        the stochastic reweighting. Otherwise, the original graph is
        modified in-place (and also returned, for convenience).

    weight : edge attribute key (optional, default='weight')
        Edge attribute key used for reading the existing weight and
        setting the new weight.  If no attribute with this key is found
        for an edge, then the edge weight is assumed to be 1. If an edge
        has a weight, it must be a positive number.

    """
    if copy:
        G = MultiDiGraph(G) if G.is_multigraph() else DiGraph(G)
    # There is a tradeoff here: the dictionary of node degrees may
    # require a lot of memory, whereas making a call to `G.out_degree`
    # inside the loop may be costly in computation time.
    degree = dict(G.out_degree(weight=weight))
    for u, v, d in G.edges(data=True):
        if degree[u] == 0:
            d[weight] = 0
        else:
            d[weight] = d.get(weight, 1) / degree[u]
    nx._clear_cache(G)
    return G
