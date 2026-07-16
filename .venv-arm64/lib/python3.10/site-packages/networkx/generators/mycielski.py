"""Functions related to the Mycielski Operation and the Mycielskian family
of graphs.

"""

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = ["mycielskian", "mycielski_graph"]


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable(returns_graph=True)
def mycielskian(G, iterations=1):
    r"""Returns the Mycielskian of a simple, undirected graph G

    The Mycielskian of graph preserves a graph's triangle free
    property while increasing the chromatic number by 1.

    The Mycielski Operation on a graph, :math:`G=(V, E)`, constructs a new
    graph with :math:`2|V| + 1` nodes and :math:`3|E| + |V|` edges.

    The construction is as follows:

    Let :math:`V = {0, ..., n-1}`. Construct another vertex set
    :math:`U = {n, ..., 2n}` and a vertex, `w`.
    Construct a new graph, `M`, with vertices :math:`U \bigcup V \bigcup w`.
    For edges, :math:`(u, v) \in E` add edges :math:`(u, v), (u, v + n)`, and
    :math:`(u + n, v)` to M. Finally, for all vertices :math:`u \in U`, add
    edge :math:`(u, w)` to M.

    The Mycielski Operation can be done multiple times by repeating the above
    process iteratively.

    More information can be found at https://en.wikipedia.org/wiki/Mycielskian

    Parameters
    ----------
    G : graph
        A simple, undirected NetworkX graph
    iterations : int
        The number of iterations of the Mycielski operation to
        perform on G. Defaults to 1. Must be a non-negative integer.

    Returns
    -------
    M : graph
        The Mycielskian of G after the specified number of iterations.

    Notes
    -----
    Graph, node, and edge data are not necessarily propagated to the new graph.

    """

    M = nx.convert_node_labels_to_integers(G)

    for i in range(iterations):
        n = M.number_of_nodes()
        M.add_nodes_from(range(n, 2 * n))
        old_edges = list(M.edges())
        M.add_edges_from((u, v + n) for u, v in old_edges)
        M.add_edges_from((u + n, v) for u, v in old_edges)
        M.add_node(2 * n)
        M.add_edges_from((u + n, 2 * n) for u in range(n))

    return M


@nx._dispatchable(graphs=None, returns_graph=True)
def mycielski_graph(n):
    """Generator for the n_th Mycielski Graph.

    The Mycielski family of graphs is an infinite set of graphs.
    :math:`M_1` is the singleton graph, :math:`M_2` is two vertices with an
    edge, and, for :math:`i > 2`, :math:`M_i` is the Mycielskian of
    :math:`M_{i-1}`.

    More information can be found at
    http://mathworld.wolfram.com/MycielskiGraph.html

    Parameters
    ----------
    n : int
        The desired Mycielski Graph.

    Returns
    -------
    M : graph
        The n_th Mycielski Graph

    Notes
    -----
    The first graph in the Mycielski sequence is the singleton graph.
    The Mycielskian of this graph is not the :math:`P_2` graph, but rather the
    :math:`P_2` graph with an extra, isolated vertex. The second Mycielski
    graph is the :math:`P_2` graph, so the first two are hard coded.
    The remaining graphs are generated using the Mycielski operation.

    """

    if n < 1:
        raise nx.NetworkXError("must satisfy n >= 1")

    if n == 1:
        return nx.empty_graph(1)

    else:
        return mycielskian(nx.path_graph(2), n - 2)
