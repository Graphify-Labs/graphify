"""Functions measuring similarity using graph edit distance.

The graph edit distance is the number of edge/node changes needed
to make two graphs isomorphic.

The default algorithm/implementation is sub-optimal for some graphs.
The problem of finding the exact Graph Edit Distance (GED) is NP-hard
so it is often slow. If the simple interface `graph_edit_distance`
takes too long for your graph, try `optimize_graph_edit_distance`
and/or `optimize_edit_paths`.

At the same time, I encourage capable people to investigate
alternative GED algorithms, in order to improve the choices available.
"""

import math
import time
import warnings
from dataclasses import dataclass
from itertools import product

import networkx as nx
from networkx.utils import np_random_state

__all__ = [
    "graph_edit_distance",
    "optimal_edit_paths",
    "optimize_graph_edit_distance",
    "optimize_edit_paths",
    "simrank_similarity",
    "panther_similarity",
    "generate_random_paths",
]


def debug_print(*args, **kwargs):
    print(*args, **kwargs)


@nx._dispatchable(
    graphs={"G1": 0, "G2": 1}, preserve_edge_attrs=True, preserve_node_attrs=True
)
def graph_edit_distance(
    G1,
    G2,
    node_match=None,
    edge_match=None,
    node_subst_cost=None,
    node_del_cost=None,
    node_ins_cost=None,
    edge_subst_cost=None,
    edge_del_cost=None,
    edge_ins_cost=None,
    roots=None,
    upper_bound=None,
    timeout=None,
):
    """Returns GED (graph edit distance) between graphs G1 and G2.

    Graph edit distance is a graph similarity measure analogous to
    Levenshtein distance for strings.  It is defined as minimum cost
    of edit path (sequence of node and edge edit operations)
    transforming graph G1 to graph isomorphic to G2.

    Parameters
    ----------
    G1, G2: graphs
        The two graphs G1 and G2 must be of the same type.

    node_match : callable
        A function that returns True if node n1 in G1 and n2 in G2
        should be considered equal during matching.

        The function will be called like

           node_match(G1.nodes[n1], G2.nodes[n2]).

        That is, the function will receive the node attribute
        dictionaries for n1 and n2 as inputs.

        Ignored if node_subst_cost is specified.  If neither
        node_match nor node_subst_cost are specified then node
        attributes are not considered.

    edge_match : callable
        A function that returns True if the edge attribute dictionaries
        for the pair of nodes (u1, v1) in G1 and (u2, v2) in G2 should
        be considered equal during matching.

        The function will be called like

           edge_match(G1[u1][v1], G2[u2][v2]).

        That is, the function will receive the edge attribute
        dictionaries of the edges under consideration.

        Ignored if edge_subst_cost is specified.  If neither
        edge_match nor edge_subst_cost are specified then edge
        attributes are not considered.

    node_subst_cost, node_del_cost, node_ins_cost : callable
        Functions that return the costs of node substitution, node
        deletion, and node insertion, respectively.

        The functions will be called like

           node_subst_cost(G1.nodes[n1], G2.nodes[n2]),
           node_del_cost(G1.nodes[n1]),
           node_ins_cost(G2.nodes[n2]).

        That is, the functions will receive the node attribute
        dictionaries as inputs.  The functions are expected to return
        positive numeric values.

        Function node_subst_cost overrides node_match if specified.
        If neither node_match nor node_subst_cost are specified then
        default node substitution cost of 0 is used (node attributes
        are not considered during matching).

        If node_del_cost is not specified then default node deletion
        cost of 1 is used.  If node_ins_cost is not specified then
        default node insertion cost of 1 is used.

    edge_subst_cost, edge_del_cost, edge_ins_cost : callable
        Functions that return the costs of edge substitution, edge
        deletion, and edge insertion, respectively.

        The functions will be called like

           edge_subst_cost(G1[u1][v1], G2[u2][v2]),
           edge_del_cost(G1[u1][v1]),
           edge_ins_cost(G2[u2][v2]).

        That is, the functions will receive the edge attribute
        dictionaries as inputs.  The functions are expected to return
        positive numeric values.

        Function edge_subst_cost overrides edge_match if specified.
        If neither edge_match nor edge_subst_cost are specified then
        default edge substitution cost of 0 is used (edge attributes
        are not considered during matching).

        If edge_del_cost is not specified then default edge deletion
        cost of 1 is used.  If edge_ins_cost is not specified then
        default edge insertion cost of 1 is used.

    roots : 2-tuple
        Tuple where first element is a node in G1 and the second
        is a node in G2.
        These nodes are forced to be matched in the comparison to
        allow comparison between rooted graphs.

    upper_bound : numeric
        Maximum edit distance to consider.  Return None if no edit
        distance under or equal to upper_bound exists.

    timeout : numeric
        Maximum number of seconds to execute.
        After timeout is met, the current best GED is returned.

    Examples
    --------
    >>> G1 = nx.cycle_graph(6)
    >>> G2 = nx.wheel_graph(7)
    >>> nx.graph_edit_distance(G1, G2)
    7.0

    >>> G1 = nx.star_graph(5)
    >>> G2 = nx.star_graph(5)
    >>> nx.graph_edit_distance(G1, G2, roots=(0, 0))
    0.0
    >>> nx.graph_edit_distance(G1, G2, roots=(1, 0))
    8.0

    See Also
    --------
    optimal_edit_paths, optimize_graph_edit_distance,

    is_isomorphic: test for graph edit distance of 0

    References
    ----------
    .. [1] Zeina Abu-Aisheh, Romain Raveaux, Jean-Yves Ramel, Patrick
       Martineau. An Exact Graph Edit Distance Algorithm for Solving
       Pattern Recognition Problems. 4th International Conference on
       Pattern Recognition Applications and Methods 2015, Jan 2015,
       Lisbon, Portugal. 2015,
       <10.5220/0005209202710278>. <hal-01168816>
       https://hal.archives-ouvertes.fr/hal-01168816

    """
    bestcost = None
    for _, _, cost in optimize_edit_paths(
        G1,
        G2,
        node_match,
        edge_match,
        node_subst_cost,
        node_del_cost,
        node_ins_cost,
        edge_subst_cost,
        edge_del_cost,
        edge_ins_cost,
        upper_bound,
        True,
        roots,
        timeout,
    ):
        # assert bestcost is None or cost < bestcost
        bestcost = cost
    return bestcost


@nx._dispatchable(graphs={"G1": 0, "G2": 1})
def optimal_edit_paths(
    G1,
    G2,
    node_match=None,
    edge_match=None,
    node_subst_cost=None,
    node_del_cost=None,
    node_ins_cost=None,
    edge_subst_cost=None,
    edge_del_cost=None,
    edge_ins_cost=None,
    upper_bound=None,
):
    """Returns all minimum-cost edit paths transforming G1 to G2.

    Graph edit path is a sequence of node and edge edit operations
    transforming graph G1 to graph isomorphic to G2.  Edit operations
    include substitutions, deletions, and insertions.

    Parameters
    ----------
    G1, G2: graphs
        The two graphs G1 and G2 must be of the same type.

    node_match : callable
        A function that returns True if node n1 in G1 and n2 in G2
        should be considered equal during matching.

        The function will be called like

           node_match(G1.nodes[n1], G2.nodes[n2]).

        That is, the function will receive the node attribute
        dictionaries for n1 and n2 as inputs.

        Ignored if node_subst_cost is specified.  If neither
        node_match nor node_subst_cost are specified then node
        attributes are not considered.

    edge_match : callable
        A function that returns True if the edge attribute dictionaries
        for the pair of nodes (u1, v1) in G1 and (u2, v2) in G2 should
        be considered equal during matching.

        The function will be called like

           edge_match(G1[u1][v1], G2[u2][v2]).

        That is, the function will receive the edge attribute
        dictionaries of the edges under consideration.

        Ignored if edge_subst_cost is specified.  If neither
        edge_match nor edge_subst_cost are specified then edge
        attributes are not considered.

    node_subst_cost, node_del_cost, node_ins_cost : callable
        Functions that return the costs of node substitution, node
        deletion, and node insertion, respectively.

        The functions will be called like

           node_subst_cost(G1.nodes[n1], G2.nodes[n2]),
           node_del_cost(G1.nodes[n1]),
           node_ins_cost(G2.nodes[n2]).

        That is, the functions will receive the node attribute
        dictionaries as inputs.  The functions are expected to return
        positive numeric values.

        Function node_subst_cost overrides node_match if specified.
        If neither node_match nor node_subst_cost are specified then
        default node substitution cost of 0 is used (node attributes
        are not considered during matching).

        If node_del_cost is not specified then default node deletion
        cost of 1 is used.  If node_ins_cost is not specified then
        default node insertion cost of 1 is used.

    edge_subst_cost, edge_del_cost, edge_ins_cost : callable
        Functions that return the costs of edge substitution, edge
        deletion, and edge insertion, respectively.

        The functions will be called like

           edge_subst_cost(G1[u1][v1], G2[u2][v2]),
           edge_del_cost(G1[u1][v1]),
           edge_ins_cost(G2[u2][v2]).

        That is, the functions will receive the edge attribute
        dictionaries as inputs.  The functions are expected to return
        positive numeric values.

        Function edge_subst_cost overrides edge_match if specified.
        If neither edge_match nor edge_subst_cost are specified then
        default edge substitution cost of 0 is used (edge attributes
        are not considered during matching).

        If edge_del_cost is not specified then default edge deletion
        cost of 1 is used.  If edge_ins_cost is not specified then
        default edge insertion cost of 1 is used.

    upper_bound : numeric
        Maximum edit distance to consider.

    Returns
    -------
    edit_paths : list of tuples (node_edit_path, edge_edit_path)
       - node_edit_path : list of tuples ``(u, v)`` indicating node transformations
         between `G1` and `G2`. ``u`` is `None` for insertion, ``v`` is `None`
         for deletion.
       - edge_edit_path : list of tuples ``((u1, v1), (u2, v2))`` indicating edge
         transformations between `G1` and `G2`. ``(None, (u2,v2))`` for insertion
         and ``((u1,v1), None)`` for deletion.

    cost : numeric
        Optimal edit path cost (graph edit distance). When the cost
        is zero, it indicates that `G1` and `G2` are isomorphic.

    Examples
    --------
    >>> G1 = nx.cycle_graph(4)
    >>> G2 = nx.wheel_graph(5)
    >>> paths, cost = nx.optimal_edit_paths(G1, G2)
    >>> len(paths)
    40
    >>> cost
    5.0

    Notes
    -----
    To transform `G1` into a graph isomorphic to `G2`, apply the node
    and edge edits in the returned ``edit_paths``.
    In the case of isomorphic graphs, the cost is zero, and the paths
    represent different isomorphic mappings (isomorphisms). That is, the
    edits involve renaming nodes and edges to match the structure of `G2`.

    See Also
    --------
    graph_edit_distance, optimize_edit_paths

    References
    ----------
    .. [1] Zeina Abu-Aisheh, Romain Raveaux, Jean-Yves Ramel, Patrick
       Martineau. An Exact Graph Edit Distance Algorithm for Solving
       Pattern Recognition Problems. 4th International Conference on
       Pattern Recognition Applications and Methods 2015, Jan 2015,
       Lisbon, Portugal. 2015,
       <10.5220/0005209202710278>. <hal-01168816>
       https://hal.archives-ouvertes.fr/hal-01168816

    """
    paths = []
    bestcost = None
    for vertex_path, edge_path, cost in optimize_edit_paths(
        G1,
        G2,
        node_match,
        edge_match,
        node_subst_cost,
        node_del_cost,
        node_ins_cost,
        edge_subst_cost,
        edge_del_cost,
        edge_ins_cost,
        upper_bound,
        False,
    ):
        # assert bestcost is None or cost <= bestcost
        if bestcost is not None and cost < bestcost:
            paths = []
        paths.append((vertex_path, edge_path))
        bestcost = cost
    return paths, bestcost


@nx._dispatchable(graphs={"G1": 0, "G2": 1})
def optimize_graph_edit_distance(
    G1,
    G2,
    node_match=None,
    edge_match=None,
    node_subst_cost=None,
    node_del_cost=None,
    node_ins_cost=None,
    edge_subst_cost=None,
    edge_del_cost=None,
    edge_ins_cost=None,
    upper_bound=None,
):
    """Returns consecutive approximations of GED (graph edit distance)
    between graphs G1 and G2.

    Graph edit distance is a graph similarity measure analogous to
    Levenshtein distance for strings.  It is defined as minimum cost
    of edit path (sequence of node and edge edit operations)
    transforming graph G1 to graph isomorphic to G2.

    Parameters
    ----------
    G1, G2: graphs
        The two graphs G1 and G2 must be of the same type.

    node_match : callable
        A function that returns True if node n1 in G1 and n2 in G2
        should be considered equal during matching.

        The function will be called like

           node_match(G1.nodes[n1], G2.nodes[n2]).

        That is, the function will receive the node attribute
        dictionaries for n1 and n2 as inputs.

        Ignored if node_subst_cost is specified.  If neither
        node_match nor node_subst_cost are specified then node
        attributes are not considered.

    edge_match : callable
        A function that returns True if the edge attribute dictionaries
        for the pair of nodes (u1, v1) in G1 and (u2, v2) in G2 should
        be considered equal during matching.

        The function will be called like

           edge_match(G1[u1][v1], G2[u2][v2]).

        That is, the function will receive the edge attribute
        dictionaries of the edges under consideration.

        Ignored if edge_subst_cost is specified.  If neither
        edge_match nor edge_subst_cost are specified then edge
        attributes are not considered.

    node_subst_cost, node_del_cost, node_ins_cost : callable
        Functions that return the costs of node substitution, node
        deletion, and node insertion, respectively.

        The functions will be called like

           node_subst_cost(G1.nodes[n1], G2.nodes[n2]),
           node_del_cost(G1.nodes[n1]),
           node_ins_cost(G2.nodes[n2]).

        That is, the functions will receive the node attribute
        dictionaries as inputs.  The functions are expected to return
        positive numeric values.

        Function node_subst_cost overrides node_match if specified.
        If neither node_match nor node_subst_cost are specified then
        default node substitution cost of 0 is used (node attributes
        are not considered during matching).

        If node_del_cost is not specified then default node deletion
        cost of 1 is used.  If node_ins_cost is not specified then
        default node insertion cost of 1 is used.

    edge_subst_cost, edge_del_cost, edge_ins_cost : callable
        Functions that return the costs of edge substitution, edge
        deletion, and edge insertion, respectively.

        The functions will be called like

           edge_subst_cost(G1[u1][v1], G2[u2][v2]),
           edge_del_cost(G1[u1][v1]),
           edge_ins_cost(G2[u2][v2]).

        That is, the functions will receive the edge attribute
        dictionaries as inputs.  The functions are expected to return
        positive numeric values.

        Function edge_subst_cost overrides edge_match if specified.
        If neither edge_match nor edge_subst_cost are specified then
        default edge substitution cost of 0 is used (edge attributes
        are not considered during matching).

        If edge_del_cost is not specified then default edge deletion
        cost of 1 is used.  If edge_ins_cost is not specified then
        default edge insertion cost of 1 is used.

    upper_bound : numeric
        Maximum edit distance to consider.

    Returns
    -------
    Generator of consecutive approximations of graph edit distance.

    Examples
    --------
    >>> G1 = nx.cycle_graph(6)
    >>> G2 = nx.wheel_graph(7)
    >>> for v in nx.optimize_graph_edit_distance(G1, G2):
    ...     minv = v
    >>> minv
    7.0

    See Also
    --------
    graph_edit_distance, optimize_edit_paths

    References
    ----------
    .. [1] Zeina Abu-Aisheh, Romain Raveaux, Jean-Yves Ramel, Patrick
       Martineau. An Exact Graph Edit Distance Algorithm for Solving
       Pattern Recognition Problems. 4th International Conference on
       Pattern Recognition Applications and Methods 2015, Jan 2015,
       Lisbon, Portugal. 2015,
       <10.5220/0005209202710278>. <hal-01168816>
       https://hal.archives-ouvertes.fr/hal-01168816
    """
    for _, _, cost in optimize_edit_paths(
        G1,
        G2,
        node_match,
        edge_match,
        node_subst_cost,
        node_del_cost,
        node_ins_cost,
        edge_subst_cost,
        edge_del_cost,
        edge_ins_cost,
        upper_bound,
        True,
    ):
        yield cost


@nx._dispatchable(
    graphs={"G1": 0, "G2": 1}, preserve_edge_attrs=True, preserve_node_attrs=True
)
def optimize_edit_paths(
    G1,
    G2,
    node_match=None,
    edge_match=None,
    node_subst_cost=None,
    node_del_cost=None,
    node_ins_cost=None,
    edge_subst_cost=None,
    edge_del_cost=None,
    edge_ins_cost=None,
    upper_bound=None,
    strictly_decreasing=True,
    roots=None,
    timeout=None,
):
    """GED (graph edit distance) calculation: advanced interface.

    Graph edit path is a sequence of node and edge edit operations
    transforming graph G1 to graph isomorphic to G2.  Edit operations
    include substitutions, deletions, and insertions.

    Graph edit distance is defined as minimum cost of edit path.

    Parameters
    ----------
    G1, G2: graphs
        The two graphs G1 and G2 must be of the same type.

    node_match : callable
        A function that returns True if node n1 in G1 and n2 in G2
        should be considered equal during matching.

        The function will be called like

           node_match(G1.nodes[n1], G2.nodes[n2]).

        That is, the function will receive the node attribute
        dictionaries for n1 and n2 as inputs.

        Ignored if node_subst_cost is specified.  If neither
        node_match nor node_subst_cost are specified then node
        attributes are not considered.

    edge_match : callable
        A function that returns True if the edge attribute dictionaries
        for the pair of nodes (u1, v1) in G1 and (u2, v2) in G2 should
        be considered equal during matching.

        The function will be called like

           edge_match(G1[u1][v1], G2[u2][v2]).

        That is, the function will receive the edge attribute
        dictionaries of the edges under consideration.

        Ignored if edge_subst_cost is specified.  If neither
        edge_match nor edge_subst_cost are specified then edge
        attributes are not considered.

    node_subst_cost, node_del_cost, node_ins_cost : callable
        Functions that return the costs of node substitution, node
        deletion, and node insertion, respectively.

        The functions will be called like

           node_subst_cost(G1.nodes[n1], G2.nodes[n2]),
           node_del_cost(G1.nodes[n1]),
           node_ins_cost(G2.nodes[n2]).

        That is, the functions will receive the node attribute
        dictionaries as inputs.  The functions are expected to return
        positive numeric values.

        Function node_subst_cost overrides node_match if specified.
        If neither node_match nor node_subst_cost are specified then
        default node substitution cost of 0 is used (node attributes
        are not considered during matching).

        If node_del_cost is not specified then default node deletion
        cost of 1 is used.  If node_ins_cost is not specified then
        default node insertion cost of 1 is used.

    edge_subst_cost, edge_del_cost, edge_ins_cost : callable
        Functions that return the costs of edge substitution, edge
        deletion, and edge insertion, respectively.

        The functions will be called like

           edge_subst_cost(G1[u1][v1], G2[u2][v2]),
           edge_del_cost(G1[u1][v1]),
           edge_ins_cost(G2[u2][v2]).

        That is, the functions will receive the edge attribute
        dictionaries as inputs.  The functions are expected to return
        positive numeric values.

        Function edge_subst_cost overrides edge_match if specified.
        If neither edge_match nor edge_subst_cost are specified then
        default edge substitution cost of 0 is used (edge attributes
        are not considered during matching).

        If edge_del_cost is not specified then default edge deletion
        cost of 1 is used.  If edge_ins_cost is not specified then
        default edge insertion cost of 1 is used.

    upper_bound : numeric
        Maximum edit distance to consider.

    strictly_decreasing : bool
        If True, return consecutive approximations of strictly
        decreasing cost.  Otherwise, return all edit paths of cost
        less than or equal to the previous minimum cost.

    roots : 2-tuple
        Tuple where first element is a node in G1 and the second
        is a node in G2.
        These nodes are forced to be matched in the comparison to
        allow comparison between rooted graphs.

    timeout : numeric
        Maximum number of seconds to execute.
        After timeout is met, the current best GED is returned.

    Returns
    -------
    Generator of tuples (node_edit_path, edge_edit_path, cost)
        node_edit_path : list of tuples (u, v)
        edge_edit_path : list of tuples ((u1, v1), (u2, v2))
        cost : numeric

    See Also
    --------
    graph_edit_distance, optimize_graph_edit_distance, optimal_edit_paths

    References
    ----------
    .. [1] Zeina Abu-Aisheh, Romain Raveaux, Jean-Yves Ramel, Patrick
       Martineau. An Exact Graph Edit Distance Algorithm for Solving
       Pattern Recognition Problems. 4th International Conference on
       Pattern Recognition Applications and Methods 2015, Jan 2015,
       Lisbon, Portugal. 2015,
       <10.5220/0005209202710278>. <hal-01168816>
       https://hal.archives-ouvertes.fr/hal-01168816

    """
    # TODO: support DiGraph

    import numpy as np
    import scipy as sp

    @dataclass
    class CostMatrix:
        C: ...
        lsa_row_ind: ...
        lsa_col_ind: ...
        ls: ...

    def make_CostMatrix(C, m, n):
        # assert(C.shape == (m + n, m + n))
        lsa_row_ind, lsa_col_ind = sp.optimize.linear_sum_assignment(C)

        # Fixup dummy assignments:
        # each substitution i<->j should have dummy assignment m+j<->n+i
        # NOTE: fast reduce of Cv relies on it
        # Create masks for substitution and dummy indices
        is_subst = (lsa_row_ind < m) & (lsa_col_ind < n)
        is_dummy = (lsa_row_ind >= m) & (lsa_col_ind >= n)

        # Map dummy assignments to the correct indices
        lsa_row_ind[is_dummy] = lsa_col_ind[is_subst] + m
        lsa_col_ind[is_dummy] = lsa_row_ind[is_subst] + n

        return CostMatrix(
            C, lsa_row_ind, lsa_col_ind, C[lsa_row_ind, lsa_col_ind].sum()
        )

    def extract_C(C, i, j, m, n):
        # assert(C.shape == (m + n, m + n))
        row_ind = [k in i or k - m in j for k in range(m + n)]
        col_ind = [k in j or k - n in i for k in range(m + n)]
        return C[row_ind, :][:, col_ind]

    def reduce_C(C, i, j, m, n):
        # assert(C.shape == (m + n, m + n))
        row_ind = [k not in i and k - m not in j for k in range(m + n)]
        col_ind = [k not in j and k - n not in i for k in range(m + n)]
        return C[row_ind, :][:, col_ind]

    def reduce_ind(ind, i):
        # assert set(ind) == set(range(len(ind)))
        rind = ind[[k not in i for k in ind]]
        for k in set(i):
            rind[rind >= k] -= 1
        return rind

    def match_edges(u, v, pending_g, pending_h, Ce, matched_uv=None):
        """
        Parameters:
            u, v: matched vertices, u=None or v=None for
               deletion/insertion
            pending_g, pending_h: lists of edges not yet mapped
            Ce: CostMatrix of pending edge mappings
            matched_uv: partial vertex edit path
                list of tuples (u, v) of previously matched vertex
                    mappings u<->v, u=None or v=None for
                    deletion/insertion

        Returns:
            list of (i, j): indices of edge mappings g<->h
            localCe: local CostMatrix of edge mappings
                (basically submatrix of Ce at cross of rows i, cols j)
        """
        M = len(pending_g)
        N = len(pending_h)
        # assert Ce.C.shape == (M + N, M + N)

        # only attempt to match edges after one node match has been made
        # this will stop self-edges on the first node being automatically deleted
        # even when a substitution is the better option
        if matched_uv is None or len(matched_uv) == 0:
            g_ind = []
            h_ind = []
        else:
            g_ind = [
                i
                for i in range(M)
                if pending_g[i][:2] == (u, u)
                or any(
                    pending_g[i][:2] in ((p, u), (u, p), (p, p)) for p, q in matched_uv
                )
            ]
            h_ind = [
                j
                for j in range(N)
                if pending_h[j][:2] == (v, v)
                or any(
                    pending_h[j][:2] in ((q, v), (v, q), (q, q)) for p, q in matched_uv
                )
            ]

        m = len(g_ind)
        n = len(h_ind)

        if m or n:
            C = extract_C(Ce.C, g_ind, h_ind, M, N)
            # assert C.shape == (m + n, m + n)

            # Forbid structurally invalid matches
            # NOTE: inf remembered from Ce construction
            for k, i in enumerate(g_ind):
                g = pending_g[i][:2]
                for l, j in enumerate(h_ind):
                    h = pending_h[j][:2]
                    if nx.is_directed(G1) or nx.is_directed(G2):
                        if any(
                            g == (p, u) and h == (q, v) or g == (u, p) and h == (v, q)
                            for p, q in matched_uv
                        ):
                            continue
                    else:
                        if any(
                            g in ((p, u), (u, p)) and h in ((q, v), (v, q))
                            for p, q in matched_uv
                        ):
                            continue
                    if g == (u, u) or any(g == (p, p) for p, q in matched_uv):
                        continue
                    if h == (v, v) or any(h == (q, q) for p, q in matched_uv):
                        continue
                    C[k, l] = inf

            localCe = make_CostMatrix(C, m, n)
            ij = [
                (
                    g_ind[k] if k < m else M + h_ind[l],
                    h_ind[l] if l < n else N + g_ind[k],
                )
                for k, l in zip(localCe.lsa_row_ind, localCe.lsa_col_ind)
                if k < m or l < n
            ]

        else:
            ij = []
            localCe = CostMatrix(np.empty((0, 0)), [], [], 0)

        return ij, localCe

    def reduce_Ce(Ce, ij, m, n):
        if len(ij):
            i, j = zip(*ij)
            m_i = m - sum(1 for t in i if t < m)
            n_j = n - sum(1 for t in j if t < n)
            return make_CostMatrix(reduce_C(Ce.C, i, j, m, n), m_i, n_j)
        return Ce

    def get_edit_ops(
        matched_uv, pending_u, pending_v, Cv, pending_g, pending_h, Ce, matched_cost
    ):
        """
        Parameters:
            matched_uv: partial vertex edit path
                list of tuples (u, v) of vertex mappings u<->v,
                u=None or v=None for deletion/insertion
            pending_u, pending_v: lists of vertices not yet mapped
            Cv: CostMatrix of pending vertex mappings
            pending_g, pending_h: lists of edges not yet mapped
            Ce: CostMatrix of pending edge mappings
            matched_cost: cost of partial edit path

        Returns:
            sequence of
                (i, j): indices of vertex mapping u<->v
                Cv_ij: reduced CostMatrix of pending vertex mappings
                    (basically Cv with row i, col j removed)
                list of (x, y): indices of edge mappings g<->h
                Ce_xy: reduced CostMatrix of pending edge mappings
                    (basically Ce with rows x, cols y removed)
                cost: total cost of edit operation
            NOTE: most promising ops first
        """
        m = len(pending_u)
        n = len(pending_v)
        # assert Cv.C.shape == (m + n, m + n)

        # 1) a vertex mapping from optimal linear sum assignment
        i, j = min(
            (k, l) for k, l in zip(Cv.lsa_row_ind, Cv.lsa_col_ind) if k < m or l < n
        )
        xy, localCe = match_edges(
            pending_u[i] if i < m else None,
            pending_v[j] if j < n else None,
            pending_g,
            pending_h,
            Ce,
            matched_uv,
        )
        Ce_xy = reduce_Ce(Ce, xy, len(pending_g), len(pending_h))
        # assert Ce.ls <= localCe.ls + Ce_xy.ls
        if prune(matched_cost + Cv.ls + localCe.ls + Ce_xy.ls):
            pass
        else:
            # get reduced Cv efficiently
            Cv_ij = CostMatrix(
                reduce_C(Cv.C, (i,), (j,), m, n),
                reduce_ind(Cv.lsa_row_ind, (i, m + j)),
                reduce_ind(Cv.lsa_col_ind, (j, n + i)),
                Cv.ls - Cv.C[i, j],
            )
            yield (i, j), Cv_ij, xy, Ce_xy, Cv.C[i, j] + localCe.ls

        # 2) other candidates, sorted by lower-bound cost estimate
        other = []
        fixed_i, fixed_j = i, j
        if m <= n:
            candidates = (
                (t, fixed_j)
                for t in range(m + n)
                if t != fixed_i and (t < m or t == m + fixed_j)
            )
        else:
            candidates = (
                (fixed_i, t)
                for t in range(m + n)
                if t != fixed_j and (t < n or t == n + fixed_i)
            )
        for i, j in candidates:
            if prune(matched_cost + Cv.C[i, j] + Ce.ls):
                continue
            Cv_ij = make_CostMatrix(
                reduce_C(Cv.C, (i,), (j,), m, n),
                m - 1 if i < m else m,
                n - 1 if j < n else n,
            )
            # assert Cv.ls <= Cv.C[i, j] + Cv_ij.ls
            if prune(matched_cost + Cv.C[i, j] + Cv_ij.ls + Ce.ls):
                continue
            xy, localCe = match_edges(
                pending_u[i] if i < m else None,
                pending_v[j] if j < n else None,
                pending_g,
                pending_h,
                Ce,
                matched_uv,
            )
            if prune(matched_cost + Cv.C[i, j] + Cv_ij.ls + localCe.ls):
                continue
            Ce_xy = reduce_Ce(Ce, xy, len(pending_g), len(pending_h))
            # assert Ce.ls <= localCe.ls + Ce_xy.ls
            if prune(matched_cost + Cv.C[i, j] + Cv_ij.ls + localCe.ls + Ce_xy.ls):
                continue
            other.append(((i, j), Cv_ij, xy, Ce_xy, Cv.C[i, j] + localCe.ls))

        yield from sorted(other, key=lambda t: t[4] + t[1].ls + t[3].ls)

    def get_edit_paths(
        matched_uv,
        pending_u,
        pending_v,
        Cv,
        matched_gh,
        pending_g,
        pending_h,
        Ce,
        matched_cost,
    ):
        """
        Parameters:
            matched_uv: partial vertex edit path
                list of tuples (u, v) of vertex mappings u<->v,
                u=None or v=None for deletion/insertion
            pending_u, pending_v: lists of vertices not yet mapped
            Cv: CostMatrix of pending vertex mappings
            matched_gh: partial edge edit path
                list of tuples (g, h) of edge mappings g<->h,
                g=None or h=None for deletion/insertion
            pending_g, pending_h: lists of edges not yet mapped
            Ce: CostMatrix of pending edge mappings
            matched_cost: cost of partial edit path

        Returns:
            sequence of (vertex_path, edge_path, cost)
                vertex_path: complete vertex edit path
                    list of tuples (u, v) of vertex mappings u<->v,
                    u=None or v=None for deletion/insertion
                edge_path: complete edge edit path
                    list of tuples (g, h) of edge mappings g<->h,
                    g=None or h=None for deletion/insertion
                cost: total cost of edit path
            NOTE: path costs are non-increasing
        """
        # debug_print('matched-uv:', matched_uv)
        # debug_print('matched-gh:', matched_gh)
        # debug_print('matched-cost:', matched_cost)
        # debug_print('pending-u:', pending_u)
        # debug_print('pending-v:', pending_v)
        # debug_print(Cv.C)
        # assert list(sorted(G1.nodes)) == list(sorted(list(u for u, v in matched_uv if u is not None) + pending_u))
        # assert list(sorted(G2.nodes)) == list(sorted(list(v for u, v in matched_uv if v is not None) + pending_v))
        # debug_print('pending-g:', pending_g)
        # debug_print('pending-h:', pending_h)
        # debug_print(Ce.C)
        # assert list(sorted(G1.edges)) == list(sorted(list(g for g, h in matched_gh if g is not None) + pending_g))
        # assert list(sorted(G2.edges)) == list(sorted(list(h for g, h in matched_gh if h is not None) + pending_h))
        # debug_print()

        if prune(matched_cost + Cv.ls + Ce.ls):
            return

        if not max(len(pending_u), len(pending_v)):
            # assert not len(pending_g)
            # assert not len(pending_h)
            # path completed!
            # assert matched_cost <= maxcost_value
            nonlocal maxcost_value
            maxcost_value = min(maxcost_value, matched_cost)
            yield matched_uv, matched_gh, matched_cost

        else:
            edit_ops = get_edit_ops(
                matched_uv,
                pending_u,
                pending_v,
                Cv,
                pending_g,
                pending_h,
                Ce,
                matched_cost,
            )
            for ij, Cv_ij, xy, Ce_xy, edit_cost in edit_ops:
                i, j = ij
                # assert Cv.C[i, j] + sum(Ce.C[t] for t in xy) == edit_cost
                if prune(matched_cost + edit_cost + Cv_ij.ls + Ce_xy.ls):
                    continue

                # dive deeper
                u = pending_u.pop(i) if i < len(pending_u) else None
                v = pending_v.pop(j) if j < len(pending_v) else None
                matched_uv.append((u, v))
                for x, y in xy:
                    len_g = len(pending_g)
                    len_h = len(pending_h)
                    matched_gh.append(
                        (
                            pending_g[x] if x < len_g else None,
                            pending_h[y] if y < len_h else None,
                        )
                    )
                sortedx = sorted(x for x, y in xy)
                sortedy = sorted(y for x, y in xy)
                G = [
                    (pending_g.pop(x) if x < len(pending_g) else None)
                    for x in reversed(sortedx)
                ]
                H = [
                    (pending_h.pop(y) if y < len(pending_h) else None)
                    for y in reversed(sortedy)
                ]

                yield from get_edit_paths(
                    matched_uv,
                    pending_u,
                    pending_v,
                    Cv_ij,
                    matched_gh,
                    pending_g,
                    pending_h,
                    Ce_xy,
                    matched_cost + edit_cost,
                )

                # backtrack
                if u is not None:
                    pending_u.insert(i, u)
                if v is not None:
                    pending_v.insert(j, v)
                matched_uv.pop()
                for x, g in zip(sortedx, reversed(G)):
                    if g is not None:
                        pending_g.insert(x, g)
                for y, h in zip(sortedy, reversed(H)):
                    if h is not None:
                        pending_h.insert(y, h)
                for _ in xy:
                    matched_gh.pop()

    # Initialization

    pending_u = list(G1.nodes)
    pending_v = list(G2.nodes)

    initial_cost = 0
    if roots:
        root_u, root_v = roots
        if root_u not in pending_u or root_v not in pending_v:
            raise nx.NodeNotFound("Root node not in graph.")

        # remove roots from pending
        pending_u.remove(root_u)
        pending_v.remove(root_v)

    # cost matrix of vertex mappings
    m = len(pending_u)
    n = len(pending_v)
    C = np.zeros((m + n, m + n))
    if node_subst_cost:
        C[0:m, 0:n] = np.array(
            [
                node_subst_cost(G1.nodes[u], G2.nodes[v])
                for u in pending_u
                for v in pending_v
            ]
        ).reshape(m, n)
        if roots:
            initial_cost = node_subst_cost(G1.nodes[root_u], G2.nodes[root_v])
    elif node_match:
        C[0:m, 0:n] = np.array(
            [
                1 - int(node_match(G1.nodes[u], G2.nodes[v]))
                for u in pending_u
                for v in pending_v
            ]
        ).reshape(m, n)
        if roots:
            initial_cost = 1 - node_match(G1.nodes[root_u], G2.nodes[root_v])
    else:
        # all zeroes
        pass
    # assert not min(m, n) or C[0:m, 0:n].min() >= 0
    if node_del_cost:
        del_costs = [node_del_cost(G1.nodes[u]) for u in pending_u]
    else:
        del_costs = [1] * len(pending_u)
    # assert not m or min(del_costs) >= 0
    if node_ins_cost:
        ins_costs = [node_ins_cost(G2.nodes[v]) for v in pending_v]
    else:
        ins_costs = [1] * len(pending_v)
    # assert not n or min(ins_costs) >= 0
    inf = C[0:m, 0:n].sum() + sum(del_costs) + sum(ins_costs) + 1
    C[0:m, n : n + m] = np.array(
        [del_costs[i] if i == j else inf for i in range(m) for j in range(m)]
    ).reshape(m, m)
    C[m : m + n, 0:n] = np.array(
        [ins_costs[i] if i == j else inf for i in range(n) for j in range(n)]
    ).reshape(n, n)
    Cv = make_CostMatrix(C, m, n)
    # debug_print(f"Cv: {m} x {n}")
    # debug_print(Cv.C)

    pending_g = list(G1.edges)
    pending_h = list(G2.edges)

    # cost matrix of edge mappings
    m = len(pending_g)
    n = len(pending_h)
    C = np.zeros((m + n, m + n))
    if edge_subst_cost:
        C[0:m, 0:n] = np.array(
            [
                edge_subst_cost(G1.edges[g], G2.edges[h])
                for g in pending_g
                for h in pending_h
            ]
        ).reshape(m, n)
    elif edge_match:
        C[0:m, 0:n] = np.array(
            [
                1 - int(edge_match(G1.edges[g], G2.edges[h]))
                for g in pending_g
                for h in pending_h
            ]
        ).reshape(m, n)
    else:
        # all zeroes
        pass
    # assert not min(m, n) or C[0:m, 0:n].min() >= 0
    if edge_del_cost:
        del_costs = [edge_del_cost(G1.edges[g]) for g in pending_g]
    else:
        del_costs = [1] * len(pending_g)
    # assert not m or min(del_costs) >= 0
    if edge_ins_cost:
        ins_costs = [edge_ins_cost(G2.edges[h]) for h in pending_h]
    else:
        ins_costs = [1] * len(pending_h)
    # assert not n or min(ins_costs) >= 0
    inf = C[0:m, 0:n].sum() + sum(del_costs) + sum(ins_costs) + 1
    C[0:m, n : n + m] = np.array(
        [del_costs[i] if i == j else inf for i in range(m) for j in range(m)]
    ).reshape(m, m)
    C[m : m + n, 0:n] = np.array(
        [ins_costs[i] if i == j else inf for i in range(n) for j in range(n)]
    ).reshape(n, n)
    Ce = make_CostMatrix(C, m, n)
    # debug_print(f'Ce: {m} x {n}')
    # debug_print(Ce.C)
    # debug_print()

    maxcost_value = Cv.C.sum() + Ce.C.sum() + 1

    if timeout is not None:
        if timeout <= 0:
            raise nx.NetworkXError("Timeout value must be greater than 0")
        start = time.perf_counter()

    def prune(cost):
        if timeout is not None:
            if time.perf_counter() - start > timeout:
                return True
        if upper_bound is not None:
            if cost > upper_bound:
                return True
        if cost > maxcost_value:
            return True
        if strictly_decreasing and cost >= maxcost_value:
            return True
        return False

    # Now go!

    done_uv = [] if roots is None else [roots]

    for vertex_path, edge_path, cost in get_edit_paths(
        done_uv, pending_u, pending_v, Cv, [], pending_g, pending_h, Ce, initial_cost
    ):
        # assert sorted(G1.nodes) == sorted(u for u, v in vertex_path if u is not None)
        # assert sorted(G2.nodes) == sorted(v for u, v in vertex_path if v is not None)
        # assert sorted(G1.edges) == sorted(g for g, h in edge_path if g is not None)
        # assert sorted(G2.edges) == sorted(h for g, h in edge_path if h is not None)
        # print(vertex_path, edge_path, cost, file = sys.stderr)
        # assert cost == maxcost_value
        yield list(vertex_path), list(edge_path), float(cost)


@nx._dispatchable
def simrank_similarity(
    G,
    source=None,
    target=None,
    importance_factor=0.9,
    max_iterations=1000,
    tolerance=1e-4,
):
    """Returns the SimRank similarity of nodes in the graph ``G``.

    SimRank is a similarity metric that says "two objects are considered
    to be similar if they are referenced by similar objects." [1]_.

    The pseudo-code definition from the paper is::

        def simrank(G, u, v):
            in_neighbors_u = G.predecessors(u)
            in_neighbors_v = G.predecessors(v)
            scale = C / (len(in_neighbors_u) * len(in_neighbors_v))
            return scale * sum(
                simrank(G, w, x) for w, x in product(in_neighbors_u, in_neighbors_v)
            )

    where ``G`` is the graph, ``u`` is the source, ``v`` is the target,
    and ``C`` is a float decay or importance factor between 0 and 1.

    The SimRank algorithm for determining node similarity is defined in
    [2]_.

    Parameters
    ----------
    G : NetworkX graph
        A NetworkX graph

    source : node
        If this is specified, the returned dictionary maps each node
        ``v`` in the graph to the similarity between ``source`` and
        ``v``.

    target : node
        If both ``source`` and ``target`` are specified, the similarity
        value between ``source`` and ``target`` is returned. If
        ``target`` is specified but ``source`` is not, this argument is
        ignored.

    importance_factor : float
        The relative importance of indirect neighbors with respect to
        direct neighbors.

    max_iterations : integer
        Maximum number of iterations.

    tolerance : float
        Error tolerance used to check convergence. When an iteration of
        the algorithm finds that no similarity value changes more than
        this amount, the algorithm halts.

    Returns
    -------
    similarity : dictionary or float
        If ``source`` and ``target`` are both ``None``, this returns a
        dictionary of dictionaries, where keys are node pairs and value
        are similarity of the pair of nodes.

        If ``source`` is not ``None`` but ``target`` is, this returns a
        dictionary mapping node to the similarity of ``source`` and that
        node.

        If neither ``source`` nor ``target`` is ``None``, this returns
        the similarity value for the given pair of nodes.

    Raises
    ------
    ExceededMaxIterations
        If the algorithm does not converge within ``max_iterations``.

    NodeNotFound
        If either ``source`` or ``target`` is not in `G`.

    Examples
    --------
    >>> G = nx.cycle_graph(2)
    >>> nx.simrank_similarity(G)
    {0: {0: 1.0, 1: 0.0}, 1: {0: 0.0, 1: 1.0}}
    >>> nx.simrank_similarity(G, source=0)
    {0: 1.0, 1: 0.0}
    >>> nx.simrank_similarity(G, source=0, target=0)
    1.0

    The result of this function can be converted to a numpy array
    representing the SimRank matrix by using the node order of the
    graph to determine which row and column represent each node.
    Other ordering of nodes is also possible.

    >>> import numpy as np
    >>> sim = nx.simrank_similarity(G)
    >>> np.array([[sim[u][v] for v in G] for u in G])
    array([[1., 0.],
           [0., 1.]])
    >>> sim_1d = nx.simrank_similarity(G, source=0)
    >>> np.array([sim[0][v] for v in G])
    array([1., 0.])

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/SimRank
    .. [2] G. Jeh and J. Widom.
           "SimRank: a measure of structural-context similarity",
           In KDD'02: Proceedings of the Eighth ACM SIGKDD
           International Conference on Knowledge Discovery and Data Mining,
           pp. 538--543. ACM Press, 2002.
    """
    import numpy as np

    nodelist = list(G)
    if source is not None:
        if source not in nodelist:
            raise nx.NodeNotFound(f"Source node {source} not in G")
        else:
            s_indx = nodelist.index(source)
    else:
        s_indx = None

    if target is not None:
        if target not in nodelist:
            raise nx.NodeNotFound(f"Target node {target} not in G")
        else:
            t_indx = nodelist.index(target)
    else:
        t_indx = None

    x = _simrank_similarity_numpy(
        G, s_indx, t_indx, importance_factor, max_iterations, tolerance
    )

    if isinstance(x, np.ndarray):
        if x.ndim == 1:
            return dict(zip(G, x.tolist()))
        # else x.ndim == 2
        return {u: dict(zip(G, row)) for u, row in zip(G, x.tolist())}
    return float(x)


def _simrank_similarity_python(
    G,
    source=None,
    target=None,
    importance_factor=0.9,
    max_iterations=1000,
    tolerance=1e-4,
):
    """Returns the SimRank similarity of nodes in the graph ``G``.

    This pure Python version is provided for pedagogical purposes.

    Examples
    --------
    >>> G = nx.cycle_graph(2)
    >>> nx.similarity._simrank_similarity_python(G)
    {0: {0: 1, 1: 0.0}, 1: {0: 0.0, 1: 1}}
    >>> nx.similarity._simrank_similarity_python(G, source=0)
    {0: 1, 1: 0.0}
    >>> nx.similarity._simrank_similarity_python(G, source=0, target=0)
    1
    """
    # build up our similarity adjacency dictionary output
    newsim = {u: {v: 1 if u == v else 0 for v in G} for u in G}

    # These functions compute the update to the similarity value of the nodes
    # `u` and `v` with respect to the previous similarity values.
    def avg_sim(s):
        return sum(newsim[w][x] for (w, x) in s) / len(s) if s else 0.0

    Gadj = G.pred if G.is_directed() else G.adj

    def sim(u, v):
        return importance_factor * avg_sim(list(product(Gadj[u], Gadj[v])))

    for its in range(max_iterations):
        oldsim = newsim
        newsim = {u: {v: sim(u, v) if u != v else 1 for v in G} for u in G}
        is_close = all(
            all(
                abs(newsim[u][v] - old) <= tolerance * (1 + abs(old))
                for v, old in nbrs.items()
            )
            for u, nbrs in oldsim.items()
        )
        if is_close:
            break

    if its + 1 == max_iterations:
        raise nx.ExceededMaxIterations(
            f"simrank did not converge after {max_iterations} iterations."
        )

    if source is not None and target is not None:
        return newsim[source][target]
    if source is not None:
        return newsim[source]
    return newsim


def _simrank_similarity_numpy(
    G,
    source=None,
    target=None,
    importance_factor=0.9,
    max_iterations=1000,
    tolerance=1e-4,
):
    """Calculate SimRank of nodes in ``G`` using matrices with ``numpy``.

    The SimRank algorithm for determining node similarity is defined in
    [1]_.

    Parameters
    ----------
    G : NetworkX graph
        A NetworkX graph

    source : node
        If this is specified, the returned dictionary maps each node
        ``v`` in the graph to the similarity between ``source`` and
        ``v``.

    target : node
        If both ``source`` and ``target`` are specified, the similarity
        value between ``source`` and ``target`` is returned. If
        ``target`` is specified but ``source`` is not, this argument is
        ignored.

    importance_factor : float
        The relative importance of indirect neighbors with respect to
        direct neighbors.

    max_iterations : integer
        Maximum number of iterations.

    tolerance : float
        Error tolerance used to check convergence. When an iteration of
        the algorithm finds that no similarity value changes more than
        this amount, the algorithm halts.

    Returns
    -------
    similarity : numpy array or float
        If ``source`` and ``target`` are both ``None``, this returns a
        2D array containing SimRank scores of the nodes.

        If ``source`` is not ``None`` but ``target`` is, this returns an
        1D array containing SimRank scores of ``source`` and that
        node.

        If neither ``source`` nor ``target`` is ``None``, this returns
        the similarity value for the given pair of nodes.

    Examples
    --------
    >>> G = nx.cycle_graph(2)
    >>> nx.similarity._simrank_similarity_numpy(G)
    array([[1., 0.],
           [0., 1.]])
    >>> nx.similarity._simrank_similarity_numpy(G, source=0)
    array([1., 0.])
    >>> nx.similarity._simrank_similarity_numpy(G, source=0, target=0)
    1.0

    References
    ----------
    .. [1] G. Jeh and J. Widom.
           "SimRank: a measure of structural-context similarity",
           In KDD'02: Proceedings of the Eighth ACM SIGKDD
           International Conference on Knowledge Discovery and Data Mining,
           pp. 538--543. ACM Press, 2002.
    """
    # This algorithm follows roughly
    #
    #     S = max{C * (A.T * S * A), I}
    #
    # where C is the importance factor, A is the column normalized
    # adjacency matrix, and I is the identity matrix.
    import numpy as np

    adjacency_matrix = nx.to_numpy_array(G)

    # column-normalize the ``adjacency_matrix``
    s = np.array(adjacency_matrix.sum(axis=0))
    s[s == 0] = 1
    adjacency_matrix /= s  # adjacency_matrix.sum(axis=0)

    newsim = np.eye(len(G), dtype=np.float64)
    for its in range(max_iterations):
        prevsim = newsim.copy()
        newsim = importance_factor * ((adjacency_matrix.T @ prevsim) @ adjacency_matrix)
        np.fill_diagonal(newsim, 1.0)

        if np.allclose(prevsim, newsim, atol=tolerance):
            break

    if its + 1 == max_iterations:
        raise nx.ExceededMaxIterations(
            f"simrank did not converge after {max_iterations} iterations."
        )

    if source is not None and target is not None:
        return float(newsim[source, target])
    if source is not None:
        return newsim[source]
    return newsim


@nx._dispatchable(edge_attrs="weight")
def panther_similarity(
    G, source, k=5, path_length=5, c=0.5, delta=0.1, eps=None, weight="weight"
):
    r"""Returns the Panther similarity of nodes in the graph `G` to node ``v``.

    Panther is a similarity metric that says "two objects are considered
    to be similar if they frequently appear on the same paths." [1]_.

    Parameters
    ----------
    G : NetworkX graph
        A NetworkX graph
    source : node
        Source node for which to find the top `k` similar other nodes
    k : int (default = 5)
        The number of most similar nodes to return.
    path_length : int (default = 5)
        How long the randomly generated paths should be (``T`` in [1]_)
    c : float (default = 0.5)
        A universal positive constant used to scale the number
        of sample random paths to generate.
    delta : float (default = 0.1)
        The probability that the similarity $S$ is not an epsilon-approximation to (R, phi),
        where $R$ is the number of random paths and $\phi$ is the probability
        that an element sampled from a set $A \subseteq D$, where $D$ is the domain.
    eps : float or None (default = None)
        The error bound. Per [1]_, a good value is ``sqrt(1/|E|)``. Therefore,
        if no value is provided, the recommended computed value will be used.
    weight : string or None, optional (default="weight")
        The name of an edge attribute that holds the numerical value
        used as a weight. If None then each edge has weight 1.

    Returns
    -------
    similarity : dictionary
        Dictionary of nodes to similarity scores (as floats). Note:
        the self-similarity (i.e., ``v``) will not be included in
        the returned dictionary. So, for ``k = 5``, a dictionary of
        top 4 nodes and their similarity scores will be returned.

    Raises
    ------
    NetworkXUnfeasible
        If `source` is an isolated node.

    NodeNotFound
        If `source` is not in `G`.

    Notes
    -----
        The isolated nodes in `G` are ignored.

    Examples
    --------
    >>> G = nx.star_graph(10)
    >>> sim = nx.panther_similarity(G, 0)

    References
    ----------
    .. [1] Zhang, J., Tang, J., Ma, C., Tong, H., Jing, Y., & Li, J.
           Panther: Fast top-k similarity search on large networks.
           In Proceedings of the ACM SIGKDD International Conference
           on Knowledge Discovery and Data Mining (Vol. 2015-August, pp. 1445–1454).
           Association for Computing Machinery. https://doi.org/10.1145/2783258.2783267.
    """
    import numpy as np

    if source not in G:
        raise nx.NodeNotFound(f"Source node {source} not in G")

    isolates = set(nx.isolates(G))

    if source in isolates:
        raise nx.NetworkXUnfeasible(
            f"Panther similarity is not defined for the isolated source node {source}."
        )

    G = G.subgraph([node for node in G.nodes if node not in isolates]).copy()

    num_nodes = G.number_of_nodes()
    if num_nodes < k:
        warnings.warn(
            f"Number of nodes is {num_nodes}, but requested k is {k}. "
            "Setting k to number of nodes."
        )
        k = num_nodes
    # According to [1], they empirically determined
    # a good value for ``eps`` to be sqrt( 1 / |E| )
    if eps is None:
        eps = np.sqrt(1.0 / G.number_of_edges())

    inv_node_map = {name: index for index, name in enumerate(G.nodes)}
    node_map = np.array(G)

    # Calculate the sample size ``R`` for how many paths
    # to randomly generate
    t_choose_2 = math.comb(path_length, 2)
    sample_size = int((c / eps**2) * (np.log2(t_choose_2) + 1 + np.log(1 / delta)))
    index_map = {}
    _ = list(
        generate_random_paths(
            G, sample_size, path_length=path_length, index_map=index_map, weight=weight
        )
    )
    S = np.zeros(num_nodes)

    inv_sample_size = 1 / sample_size

    source_paths = set(index_map[source])

    # Calculate the path similarities
    # between ``source`` (v) and ``node`` (v_j)
    # using our inverted index mapping of
    # vertices to paths
    for node, paths in index_map.items():
        # Only consider paths where both
        # ``node`` and ``source`` are present
        common_paths = source_paths.intersection(paths)
        S[inv_node_map[node]] = len(common_paths) * inv_sample_size

    # Retrieve top ``k`` similar
    # Note: the below performed anywhere from 4-10x faster
    # (depending on input sizes) vs the equivalent ``np.argsort(S)[::-1]``
    top_k_unsorted = np.argpartition(S, -k)[-k:]
    top_k_sorted = top_k_unsorted[np.argsort(S[top_k_unsorted])][::-1]

    # Add back the similarity scores
    top_k_with_val = dict(
        zip(node_map[top_k_sorted].tolist(), S[top_k_sorted].tolist())
    )

    # Remove the self-similarity
    top_k_with_val.pop(source, None)
    return top_k_with_val


@np_random_state(5)
@nx._dispatchable(edge_attrs="weight")
def generate_random_paths(
    G, sample_size, path_length=5, index_map=None, weight="weight", seed=None
):
    """Randomly generate `sample_size` paths of length `path_length`.

    Parameters
    ----------
    G : NetworkX graph
        A NetworkX graph
    sample_size : integer
        The number of paths to generate. This is ``R`` in [1]_.
    path_length : integer (default = 5)
        The maximum size of the path to randomly generate.
        This is ``T`` in [1]_. According to the paper, ``T >= 5`` is
        recommended.
    index_map : dictionary, optional
        If provided, this will be populated with the inverted
        index of nodes mapped to the set of generated random path
        indices within ``paths``.
    weight : string or None, optional (default="weight")
        The name of an edge attribute that holds the numerical value
        used as a weight. If None then each edge has weight 1.
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    paths : generator of lists
        Generator of `sample_size` paths each with length `path_length`.

    Examples
    --------
    Note that the return value is the list of paths:

    >>> G = nx.star_graph(3)
    >>> random_path = nx.generate_random_paths(G, 2)

    By passing a dictionary into `index_map`, it will build an
    inverted index mapping of nodes to the paths in which that node is present:

    >>> G = nx.star_graph(3)
    >>> index_map = {}
    >>> random_path = nx.generate_random_paths(G, 3, index_map=index_map)
    >>> paths_containing_node_0 = [
    ...     random_path[path_idx] for path_idx in index_map.get(0, [])
    ... ]

    References
    ----------
    .. [1] Zhang, J., Tang, J., Ma, C., Tong, H., Jing, Y., & Li, J.
           Panther: Fast top-k similarity search on large networks.
           In Proceedings of the ACM SIGKDD International Conference
           on Knowledge Discovery and Data Mining (Vol. 2015-August, pp. 1445–1454).
           Association for Computing Machinery. https://doi.org/10.1145/2783258.2783267.
    """
    import numpy as np

    randint_fn = (
        seed.integers if isinstance(seed, np.random.Generator) else seed.randint
    )

    # Calculate transition probabilities between
    # every pair of vertices according to Eq. (3)
    adj_mat = nx.to_numpy_array(G, weight=weight)
    inv_row_sums = np.reciprocal(adj_mat.sum(axis=1)).reshape(-1, 1)
    transition_probabilities = adj_mat * inv_row_sums

    node_map = list(G)
    num_nodes = G.number_of_nodes()

    for path_index in range(sample_size):
        # Sample current vertex v = v_i uniformly at random
        node_index = randint_fn(num_nodes)
        node = node_map[node_index]

        # Add v into p_r and add p_r into the path set
        # of v, i.e., P_v
        path = [node]

        # Build the inverted index (P_v) of vertices to paths
        if index_map is not None:
            if node in index_map:
                index_map[node].add(path_index)
            else:
                index_map[node] = {path_index}

        starting_index = node_index
        for _ in range(path_length):
            # Randomly sample a neighbor (v_j) according
            # to transition probabilities from ``node`` (v) to its neighbors
            nbr_index = seed.choice(
                num_nodes, p=transition_probabilities[starting_index]
            )

            # Set current vertex (v = v_j)
            starting_index = nbr_index

            # Add v into p_r
            nbr_node = node_map[nbr_index]
            path.append(nbr_node)

            # Add p_r into P_v
            if index_map is not None:
                if nbr_node in index_map:
                    index_map[nbr_node].add(path_index)
                else:
                    index_map[nbr_node] = {path_index}

        yield path
