"""Current-flow betweenness centrality measures."""

import networkx as nx
from networkx.algorithms.centrality.flow_matrix import (
    CGInverseLaplacian,
    FullInverseLaplacian,
    SuperLUInverseLaplacian,
    flow_matrix_row,
)
from networkx.utils import (
    not_implemented_for,
    py_random_state,
    reverse_cuthill_mckee_ordering,
)

__all__ = [
    "current_flow_betweenness_centrality",
    "approximate_current_flow_betweenness_centrality",
    "edge_current_flow_betweenness_centrality",
]


@not_implemented_for("directed")
@py_random_state(7)
@nx._dispatchable(edge_attrs="weight")
def approximate_current_flow_betweenness_centrality(
    G,
    normalized=True,
    weight=None,
    dtype=float,
    solver="full",
    epsilon=0.5,
    kmax=10000,
    seed=None,
):
    r"""Compute the approximate current-flow betweenness centrality for nodes.

    Approximates the current-flow betweenness centrality within absolute
    error of epsilon with high probability [1]_.


    Parameters
    ----------
    G : graph
      A NetworkX graph

    normalized : bool, optional (default=True)
      If True the betweenness values are normalized by 2/[(n-1)(n-2)] where
      n is the number of nodes in G.

    weight : string or None, optional (default=None)
      Key for edge data used as the edge weight.
      If None, then use 1 as each edge weight.
      The weight reflects the capacity or the strength of the
      edge.

    dtype : data type (float)
      Default data type for internal matrices.
      Set to np.float32 for lower memory consumption.

    solver : string (default='full')
       Type of linear solver to use for computing the flow matrix.
       Options are "full" (uses most memory), "lu" (recommended), and
       "cg" (uses least memory).

    epsilon: float
        Absolute error tolerance.

    kmax: int
       Maximum number of sample node pairs to use for approximation.

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    nodes : dictionary
       Dictionary of nodes with betweenness centrality as the value.

    See Also
    --------
    current_flow_betweenness_centrality

    Notes
    -----
    The running time is $O((1/\epsilon^2)m{\sqrt k} \log n)$
    and the space required is $O(m)$ for $n$ nodes and $m$ edges.

    If the edges have a 'weight' attribute they will be used as
    weights in this algorithm.  Unspecified weights are set to 1.

    References
    ----------
    .. [1] Ulrik Brandes and Daniel Fleischer:
       Centrality Measures Based on Current Flow.
       Proc. 22nd Symp. Theoretical Aspects of Computer Science (STACS '05).
       LNCS 3404, pp. 533-544. Springer-Verlag, 2005.
       https://doi.org/10.1007/978-3-540-31856-9_44
    """
    import numpy as np

    if not nx.is_connected(G):
        raise nx.NetworkXError("Graph not connected.")
    solvername = {
        "full": FullInverseLaplacian,
        "lu": SuperLUInverseLaplacian,
        "cg": CGInverseLaplacian,
    }
    n = G.number_of_nodes()
    ordering = list(reverse_cuthill_mckee_ordering(G))
    # make a copy with integer labels according to rcm ordering
    # this could be done without a copy if we really wanted to
    H = nx.relabel_nodes(G, dict(zip(ordering, range(n))))
    L = nx.laplacian_matrix(H, nodelist=range(n), weight=weight).asformat("csc")
    L = L.astype(dtype)
    C = solvername[solver](L, dtype=dtype)  # initialize solver
    betweenness = dict.fromkeys(H, 0.0)
    nb = (n - 1.0) * (n - 2.0)  # normalization factor
    cstar = n * (n - 1) / nb
    l = 1  # parameter in approximation, adjustable
    k = l * int(np.ceil((cstar / epsilon) ** 2 * np.log(n)))
    if k > kmax:
        msg = f"Number random pairs k>kmax ({k}>{kmax}) "
        raise nx.NetworkXError(msg, "Increase kmax or epsilon")
    cstar2k = cstar / (2 * k)
    for _ in range(k):
        s, t = pair = seed.sample(range(n), 2)
        b = np.zeros(n, dtype=dtype)
        b[s] = 1
        b[t] = -1
        p = C.solve(b)
        for v in H:
            if v in pair:
                continue
            for nbr in H[v]:
                w = H[v][nbr].get(weight, 1.0)
                betweenness[v] += float(w * np.abs(p[v] - p[nbr]) * cstar2k)
    if normalized:
        factor = 1.0
    else:
        factor = nb / 2.0
    # remap to original node names and "unnormalize" if required
    return {ordering[k]: v * factor for k, v in betweenness.items()}


@not_implemented_for("directed")
@nx._dispatchable(edge_attrs="weight")
def current_flow_betweenness_centrality(
    G, normalized=True, weight=None, dtype=float, solver="full"
):
    r"""Compute current-flow betweenness centrality for nodes.

    Current-flow betweenness centrality uses an electrical current
    model for information spreading in contrast to betweenness
    centrality which uses shortest paths.

    Current-flow betweenness centrality is also known as
    random-walk betweenness centrality [2]_.

    Parameters
    ----------
    G : graph
      A NetworkX graph

    normalized : bool, optional (default=True)
      If True the betweenness values are normalized by 2/[(n-1)(n-2)] where
      n is the number of nodes in G.

    weight : string or None, optional (default=None)
      Key for edge data used as the edge weight.
      If None, then use 1 as each edge weight.
      The weight reflects the capacity or the strength of the
      edge.

    dtype : data type (float)
      Default data type for internal matrices.
      Set to np.float32 for lower memory consumption.

    solver : string (default='full')
       Type of linear solver to use for computing the flow matrix.
       Options are "full" (uses most memory), "lu" (recommended), and
       "cg" (uses least memory).

    Returns
    -------
    nodes : dictionary
       Dictionary of nodes with betweenness centrality as the value.

    See Also
    --------
    approximate_current_flow_betweenness_centrality
    betweenness_centrality
    edge_betweenness_centrality
    edge_current_flow_betweenness_centrality

    Notes
    -----
    Current-flow betweenness can be computed in  $O(I(n-1)+mn \log n)$
    time [1]_, where $I(n-1)$ is the time needed to compute the
    inverse Laplacian.  For a full matrix this is $O(n^3)$ but using
    sparse methods you can achieve $O(nm{\sqrt k})$ where $k$ is the
    Laplacian matrix condition number.

    The space required is $O(nw)$ where $w$ is the width of the sparse
    Laplacian matrix.  Worse case is $w=n$ for $O(n^2)$.

    If the edges have a 'weight' attribute they will be used as
    weights in this algorithm.  Unspecified weights are set to 1.

    References
    ----------
    .. [1] Centrality Measures Based on Current Flow.
       Ulrik Brandes and Daniel Fleischer,
       Proc. 22nd Symp. Theoretical Aspects of Computer Science (STACS '05).
       LNCS 3404, pp. 533-544. Springer-Verlag, 2005.
       https://doi.org/10.1007/978-3-540-31856-9_44

    .. [2] A measure of betweenness centrality based on random walks,
       M. E. J. Newman, Social Networks 27, 39-54 (2005).
    """
    if not nx.is_connected(G):
        raise nx.NetworkXError("Graph not connected.")
    N = G.number_of_nodes()
    ordering = list(reverse_cuthill_mckee_ordering(G))
    # make a copy with integer labels according to rcm ordering
    # this could be done without a copy if we really wanted to
    H = nx.relabel_nodes(G, dict(zip(ordering, range(N))))
    betweenness = dict.fromkeys(H, 0.0)  # b[n]=0 for n in H
    for row, (s, t) in flow_matrix_row(H, weight=weight, dtype=dtype, solver=solver):
        pos = dict(zip(row.argsort()[::-1], range(N)))
        for i in range(N):
            betweenness[s] += (i - pos[i]) * row.item(i)
            betweenness[t] += (N - i - 1 - pos[i]) * row.item(i)
    if normalized:
        nb = (N - 1.0) * (N - 2.0)  # normalization factor
    else:
        nb = 2.0
    return {ordering[n]: (b - n) * 2.0 / nb for n, b in betweenness.items()}


@not_implemented_for("directed")
@nx._dispatchable(edge_attrs="weight")
def edge_current_flow_betweenness_centrality(
    G, normalized=True, weight=None, dtype=float, solver="full"
):
    r"""Compute current-flow betweenness centrality for edges.

    Current-flow betweenness centrality uses an electrical current
    model for information spreading in contrast to betweenness
    centrality which uses shortest paths.

    Current-flow betweenness centrality is also known as
    random-walk betweenness centrality [2]_.

    Parameters
    ----------
    G : graph
      A NetworkX graph

    normalized : bool, optional (default=True)
      If True the betweenness values are normalized by 2/[(n-1)(n-2)] where
      n is the number of nodes in G.

    weight : string or None, optional (default=None)
      Key for edge data used as the edge weight.
      If None, then use 1 as each edge weight.
      The weight reflects the capacity or the strength of the
      edge.

    dtype : data type (default=float)
      Default data type for internal matrices.
      Set to np.float32 for lower memory consumption.

    solver : string (default='full')
       Type of linear solver to use for computing the flow matrix.
       Options are "full" (uses most memory), "lu" (recommended), and
       "cg" (uses least memory).

    Returns
    -------
    nodes : dictionary
       Dictionary of edge tuples with betweenness centrality as the value.

    Raises
    ------
    NetworkXError
        The algorithm does not support DiGraphs.
        If the input graph is an instance of DiGraph class, NetworkXError
        is raised.

    See Also
    --------
    betweenness_centrality
    edge_betweenness_centrality
    current_flow_betweenness_centrality

    Notes
    -----
    Current-flow betweenness can be computed in $O(I(n-1)+mn \log n)$
    time [1]_, where $I(n-1)$ is the time needed to compute the
    inverse Laplacian.  For a full matrix this is $O(n^3)$ but using
    sparse methods you can achieve $O(nm{\sqrt k})$ where $k$ is the
    Laplacian matrix condition number.

    The space required is $O(nw)$ where $w$ is the width of the sparse
    Laplacian matrix.  Worse case is $w=n$ for $O(n^2)$.

    If the edges have a 'weight' attribute they will be used as
    weights in this algorithm.  Unspecified weights are set to 1.

    References
    ----------
    .. [1] Centrality Measures Based on Current Flow.
       Ulrik Brandes and Daniel Fleischer,
       Proc. 22nd Symp. Theoretical Aspects of Computer Science (STACS '05).
       LNCS 3404, pp. 533-544. Springer-Verlag, 2005.
       https://doi.org/10.1007/978-3-540-31856-9_44

    .. [2] A measure of betweenness centrality based on random walks,
       M. E. J. Newman, Social Networks 27, 39-54 (2005).
    """
    if not nx.is_connected(G):
        raise nx.NetworkXError("Graph not connected.")
    N = G.number_of_nodes()
    ordering = list(reverse_cuthill_mckee_ordering(G))
    # make a copy with integer labels according to rcm ordering
    # this could be done without a copy if we really wanted to
    H = nx.relabel_nodes(G, dict(zip(ordering, range(N))))
    edges = (tuple(sorted((u, v))) for u, v in H.edges())
    betweenness = dict.fromkeys(edges, 0.0)
    if normalized:
        nb = (N - 1.0) * (N - 2.0)  # normalization factor
    else:
        nb = 2.0
    for row, (e) in flow_matrix_row(H, weight=weight, dtype=dtype, solver=solver):
        pos = dict(zip(row.argsort()[::-1], range(1, N + 1)))
        for i in range(N):
            betweenness[e] += (i + 1 - pos[i]) * row.item(i)
            betweenness[e] += (N - i - pos[i]) * row.item(i)
        betweenness[e] /= nb
    return {(ordering[s], ordering[t]): b for (s, t), b in betweenness.items()}
