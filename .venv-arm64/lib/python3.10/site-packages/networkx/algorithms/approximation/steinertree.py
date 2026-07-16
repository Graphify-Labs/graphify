from itertools import chain

import networkx as nx
from networkx.utils import not_implemented_for, pairwise

__all__ = ["metric_closure", "steiner_tree"]


@not_implemented_for("directed")
@nx._dispatchable(edge_attrs="weight", returns_graph=True)
def metric_closure(G, weight="weight"):
    """Return the metric closure of a graph.

    The metric closure of a graph *G* is the complete graph in which each edge
    is weighted by the shortest path distance between the nodes in *G* .

    Parameters
    ----------
    G : NetworkX graph

    Returns
    -------
    NetworkX graph
        Metric closure of the graph `G`.

    """
    M = nx.Graph()

    Gnodes = set(G)

    # check for connected graph while processing first node
    all_paths_iter = nx.all_pairs_dijkstra(G, weight=weight)
    u, (distance, path) = next(all_paths_iter)
    if Gnodes - set(distance):
        msg = "G is not a connected graph. metric_closure is not defined."
        raise nx.NetworkXError(msg)
    Gnodes.remove(u)
    for v in Gnodes:
        M.add_edge(u, v, distance=distance[v], path=path[v])

    # first node done -- now process the rest
    for u, (distance, path) in all_paths_iter:
        Gnodes.remove(u)
        for v in Gnodes:
            M.add_edge(u, v, distance=distance[v], path=path[v])

    return M


def _mehlhorn_steiner_tree(G, terminal_nodes, weight):
    paths = nx.multi_source_dijkstra_path(G, terminal_nodes)

    d_1 = {}
    s = {}
    for v in G.nodes():
        s[v] = paths[v][0]
        d_1[(v, s[v])] = len(paths[v]) - 1

    # G1-G4 names match those from the Mehlhorn 1988 paper.
    G_1_prime = nx.Graph()
    for u, v, data in G.edges(data=True):
        su, sv = s[u], s[v]
        weight_here = d_1[(u, su)] + data.get(weight, 1) + d_1[(v, sv)]
        if not G_1_prime.has_edge(su, sv):
            G_1_prime.add_edge(su, sv, weight=weight_here)
        else:
            new_weight = min(weight_here, G_1_prime[su][sv]["weight"])
            G_1_prime.add_edge(su, sv, weight=new_weight)

    G_2 = nx.minimum_spanning_edges(G_1_prime, data=True)

    G_3 = nx.Graph()
    for u, v, d in G_2:
        path = nx.shortest_path(G, u, v, weight)
        for n1, n2 in pairwise(path):
            G_3.add_edge(n1, n2)

    G_3_mst = list(nx.minimum_spanning_edges(G_3, data=False))
    if G.is_multigraph():
        G_3_mst = (
            (u, v, min(G[u][v], key=lambda k: G[u][v][k][weight])) for u, v in G_3_mst
        )
    G_4 = G.edge_subgraph(G_3_mst).copy()
    _remove_nonterminal_leaves(G_4, terminal_nodes)
    return G_4.edges()


def _kou_steiner_tree(G, terminal_nodes, weight):
    # H is the subgraph induced by terminal_nodes in the metric closure M of G.
    M = metric_closure(G, weight=weight)
    H = M.subgraph(terminal_nodes)

    # Use the 'distance' attribute of each edge provided by M.
    mst_edges = nx.minimum_spanning_edges(H, weight="distance", data=True)

    # Create an iterator over each edge in each shortest path; repeats are okay
    mst_all_edges = chain.from_iterable(pairwise(d["path"]) for u, v, d in mst_edges)
    if G.is_multigraph():
        mst_all_edges = (
            (u, v, min(G[u][v], key=lambda k: G[u][v][k][weight]))
            for u, v in mst_all_edges
        )

    # Find the MST again, over this new set of edges
    G_S = G.edge_subgraph(mst_all_edges)
    T_S = nx.minimum_spanning_edges(G_S, weight="weight", data=False)

    # Leaf nodes that are not terminal might still remain; remove them here
    T_H = G.edge_subgraph(T_S).copy()
    _remove_nonterminal_leaves(T_H, terminal_nodes)

    return T_H.edges()


def _remove_nonterminal_leaves(G, terminals):
    terminal_set = set(terminals)
    leaves = {n for n in G if len(set(G[n]) - {n}) == 1}
    nonterminal_leaves = leaves - terminal_set

    while nonterminal_leaves:
        # Removing a node may create new non-terminal leaves, so we limit
        # search for candidate non-terminal nodes to neighbors of current
        # non-terminal nodes
        candidate_leaves = set.union(*(set(G[n]) for n in nonterminal_leaves))
        candidate_leaves -= nonterminal_leaves | terminal_set
        # Remove current set of non-terminal nodes
        G.remove_nodes_from(nonterminal_leaves)
        # Find any new non-terminal nodes from the set of candidates
        leaves = {n for n in candidate_leaves if len(set(G[n]) - {n}) == 1}
        nonterminal_leaves = leaves - terminal_set


ALGORITHMS = {
    "kou": _kou_steiner_tree,
    "mehlhorn": _mehlhorn_steiner_tree,
}


@not_implemented_for("directed")
@nx._dispatchable(preserve_all_attrs=True, returns_graph=True)
def steiner_tree(G, terminal_nodes, weight="weight", method=None):
    r"""Return an approximation to the minimum Steiner tree of a graph.

    The minimum Steiner tree of `G` w.r.t a set of `terminal_nodes` (also *S*)
    is a tree within `G` that spans those nodes and has minimum size (sum of
    edge weights) among all such trees.

    The approximation algorithm is specified with the `method` keyword
    argument. All three available algorithms produce a tree whose weight is
    within a ``(2 - (2 / l))`` factor of the weight of the optimal Steiner tree,
    where ``l`` is the minimum number of leaf nodes across all possible Steiner
    trees.

    * ``"kou"`` [2]_ (runtime $O(|S| |V|^2)$) computes the minimum spanning tree of
      the subgraph of the metric closure of *G* induced by the terminal nodes,
      where the metric closure of *G* is the complete graph in which each edge is
      weighted by the shortest path distance between the nodes in *G*.

    * ``"mehlhorn"`` [3]_ (runtime $O(|E|+|V|\log|V|)$) modifies Kou et al.'s
      algorithm, beginning by finding the closest terminal node for each
      non-terminal. This data is used to create a complete graph containing only
      the terminal nodes, in which edge is weighted with the shortest path
      distance between them. The algorithm then proceeds in the same way as Kou
      et al..

    Parameters
    ----------
    G : NetworkX graph

    terminal_nodes : list
         A list of terminal nodes for which minimum steiner tree is
         to be found.

    weight : string (default = 'weight')
        Use the edge attribute specified by this string as the edge weight.
        Any edge attribute not present defaults to 1.

    method : string, optional (default = 'mehlhorn')
        The algorithm to use to approximate the Steiner tree.
        Supported options: 'kou', 'mehlhorn'.
        Other inputs produce a ValueError.

    Returns
    -------
    NetworkX graph
        Approximation to the minimum steiner tree of `G` induced by
        `terminal_nodes` .

    Raises
    ------
    NetworkXNotImplemented
        If `G` is directed.

    ValueError
        If the specified `method` is not supported.

    Notes
    -----
    For multigraphs, the edge between two nodes with minimum weight is the
    edge put into the Steiner tree.


    References
    ----------
    .. [1] Steiner_tree_problem on Wikipedia.
           https://en.wikipedia.org/wiki/Steiner_tree_problem
    .. [2] Kou, L., G. Markowsky, and L. Berman. 1981.
           ‘A Fast Algorithm for Steiner Trees’.
           Acta Informatica 15 (2): 141–45.
           https://doi.org/10.1007/BF00288961.
    .. [3] Mehlhorn, Kurt. 1988.
           ‘A Faster Approximation Algorithm for the Steiner Problem in Graphs’.
           Information Processing Letters 27 (3): 125–28.
           https://doi.org/10.1016/0020-0190(88)90066-X.
    """
    if method is None:
        method = "mehlhorn"

    try:
        algo = ALGORITHMS[method]
    except KeyError as e:
        raise ValueError(f"{method} is not a valid choice for an algorithm.") from e

    edges = algo(G, terminal_nodes, weight)
    # For multigraph we should add the minimal weight edge keys
    if G.is_multigraph():
        edges = (
            (u, v, min(G[u][v], key=lambda k: G[u][v][k][weight])) for u, v in edges
        )
    T = G.edge_subgraph(edges)
    return T
