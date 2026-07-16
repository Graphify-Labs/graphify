"""Routines to calculate the broadcast time of certain graphs.

Broadcasting is an information dissemination problem in which a node in a graph,
called the originator, must distribute a message to all other nodes by placing
a series of calls along the edges of the graph. Once informed, other nodes aid
the originator in distributing the message.

The broadcasting must be completed as quickly as possible subject to the
following constraints:
- Each call requires one unit of time.
- A node can only participate in one call per unit of time.
- Each call only involves two adjacent nodes: a sender and a receiver.
"""

import networkx as nx
from networkx import NetworkXError
from networkx.utils import not_implemented_for

__all__ = [
    "tree_broadcast_center",
    "tree_broadcast_time",
]


def _get_max_broadcast_value(G, U, v, values):
    adj = sorted(set(G.neighbors(v)) & U, key=values.get, reverse=True)
    return max(values[u] + i for i, u in enumerate(adj, start=1))


def _get_broadcast_centers(G, v, values, target):
    adj = sorted(G.neighbors(v), key=values.get, reverse=True)
    j = next(i for i, u in enumerate(adj, start=1) if values[u] + i == target)
    return set([v] + adj[:j])


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def tree_broadcast_center(G):
    """Return the Broadcast Center of the tree `G`.

    The broadcast center of a graph G denotes the set of nodes having
    minimum broadcast time [1]_. This is a linear algorithm for determining
    the broadcast center of a tree with ``N`` nodes, as a by-product it also
    determines the broadcast time from the broadcast center.

    Parameters
    ----------
    G : undirected graph
        The graph should be an undirected tree

    Returns
    -------
    BC : (int, set) tuple
        minimum broadcast number of the tree, set of broadcast centers

    Raises
    ------
    NetworkXNotImplemented
        If the graph is directed or is a multigraph.

    References
    ----------
    .. [1] Slater, P.J., Cockayne, E.J., Hedetniemi, S.T,
       Information dissemination in trees. SIAM J.Comput. 10(4), 692–701 (1981)
    """
    # Assert that the graph G is a tree
    if not nx.is_tree(G):
        NetworkXError("Input graph is not a tree")
    # step 0
    if G.number_of_nodes() == 2:
        return 1, set(G.nodes())
    if G.number_of_nodes() == 1:
        return 0, set(G.nodes())

    # step 1
    U = {node for node, deg in G.degree if deg == 1}
    values = {n: 0 for n in U}
    T = G.copy()
    T.remove_nodes_from(U)

    # step 2
    W = {node for node, deg in T.degree if deg == 1}
    values.update((w, G.degree[w] - 1) for w in W)

    # step 3
    while T.number_of_nodes() >= 2:
        # step 4
        w = min(W, key=lambda n: values[n])
        v = next(T.neighbors(w))

        # step 5
        U.add(w)
        W.remove(w)
        T.remove_node(w)

        # step 6
        if T.degree(v) == 1:
            # update t(v)
            values.update({v: _get_max_broadcast_value(G, U, v, values)})
            W.add(v)

    # step 7
    v = nx.utils.arbitrary_element(T)
    b_T = _get_max_broadcast_value(G, U, v, values)
    return b_T, _get_broadcast_centers(G, v, values, b_T)


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def tree_broadcast_time(G, node=None):
    """Return the Broadcast Time of the tree `G`.

    The minimum broadcast time of a node is defined as the minimum amount
    of time required to complete broadcasting starting from the
    originator. The broadcast time of a graph is the maximum over
    all nodes of the minimum broadcast time from that node [1]_.
    This function returns the minimum broadcast time of `node`.
    If `node` is None the broadcast time for the graph is returned.

    Parameters
    ----------
    G : undirected graph
        The graph should be an undirected tree
    node: int, optional
        index of starting node. If `None`, the algorithm returns the broadcast
        time of the tree.

    Returns
    -------
    BT : int
        Broadcast Time of a node in a tree

    Raises
    ------
    NetworkXNotImplemented
        If the graph is directed or is a multigraph.

    References
    ----------
    .. [1] Harutyunyan, H. A. and Li, Z.
        "A Simple Construction of Broadcast Graphs."
        In Computing and Combinatorics. COCOON 2019
        (Ed. D. Z. Du and C. Tian.) Springer, pp. 240-253, 2019.
    """
    b_T, b_C = tree_broadcast_center(G)
    if node is not None:
        return b_T + min(nx.shortest_path_length(G, node, u) for u in b_C)
    dist_from_center = dict.fromkeys(G, len(G))
    for u in b_C:
        for v, dist in nx.shortest_path_length(G, u).items():
            if dist < dist_from_center[v]:
                dist_from_center[v] = dist
    return b_T + max(dist_from_center.values())
