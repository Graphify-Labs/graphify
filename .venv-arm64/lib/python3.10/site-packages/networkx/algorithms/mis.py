"""
Algorithm to find a maximal (not maximum) independent set.

"""

import networkx as nx
from networkx.utils import not_implemented_for, py_random_state

__all__ = ["maximal_independent_set"]


@not_implemented_for("directed")
@py_random_state(2)
@nx._dispatchable
def maximal_independent_set(G, nodes=None, seed=None):
    """Returns a random maximal independent set guaranteed to contain
    a given set of nodes.

    An independent set is a set of nodes such that the subgraph
    of G induced by these nodes contains no edges. A maximal
    independent set is an independent set such that it is not possible
    to add a new node and still get an independent set.

    Parameters
    ----------
    G : NetworkX graph

    nodes : list or iterable
       Nodes that must be part of the independent set. This set of nodes
       must be independent.

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    indep_nodes : list
       List of nodes that are part of a maximal independent set.

    Raises
    ------
    NetworkXUnfeasible
       If the nodes in the provided list are not part of the graph or
       do not form an independent set, an exception is raised.

    NetworkXNotImplemented
        If `G` is directed.

    Examples
    --------
    >>> G = nx.path_graph(5)
    >>> nx.maximal_independent_set(G)  # doctest: +SKIP
    [4, 0, 2]
    >>> nx.maximal_independent_set(G, [1])  # doctest: +SKIP
    [1, 3]

    Notes
    -----
    This algorithm does not solve the maximum independent set problem.

    """
    if not nodes:
        nodes = {seed.choice(list(G))}
    else:
        nodes = set(nodes)
    if not nodes.issubset(G):
        raise nx.NetworkXUnfeasible(f"{nodes} is not a subset of the nodes of G")
    neighbors = set.union(*[set(G.adj[v]) for v in nodes])
    if set.intersection(neighbors, nodes):
        raise nx.NetworkXUnfeasible(f"{nodes} is not an independent set of G")
    indep_nodes = list(nodes)
    available_nodes = set(G.nodes()).difference(neighbors.union(nodes))
    while available_nodes:
        node = seed.choice(list(available_nodes))
        indep_nodes.append(node)
        available_nodes.difference_update(list(G.adj[node]) + [node])
    return indep_nodes
