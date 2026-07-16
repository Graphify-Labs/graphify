"""Functions for computing eigenvector centrality."""

import math

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = ["eigenvector_centrality", "eigenvector_centrality_numpy"]


@not_implemented_for("multigraph")
@nx._dispatchable(edge_attrs="weight")
def eigenvector_centrality(G, max_iter=100, tol=1.0e-6, nstart=None, weight=None):
    r"""Compute the eigenvector centrality for the graph G.

    Eigenvector centrality computes the centrality for a node by adding
    the centrality of its predecessors. The centrality for node $i$ is the
    $i$-th element of a left eigenvector associated with the eigenvalue $\lambda$
    of maximum modulus that is positive. Such an eigenvector $x$ is
    defined up to a multiplicative constant by the equation

    .. math::

         \lambda x^T = x^T A,

    where $A$ is the adjacency matrix of the graph G. By definition of
    row-column product, the equation above is equivalent to

    .. math::

        \lambda x_i = \sum_{j\to i}x_j.

    That is, adding the eigenvector centralities of the predecessors of
    $i$ one obtains the eigenvector centrality of $i$ multiplied by
    $\lambda$. In the case of undirected graphs, $x$ also solves the familiar
    right-eigenvector equation $Ax = \lambda x$.

    By virtue of the Perron–Frobenius theorem [1]_, if G is strongly
    connected there is a unique eigenvector $x$, and all its entries
    are strictly positive.

    If G is not strongly connected there might be several left
    eigenvectors associated with $\lambda$, and some of their elements
    might be zero.

    Parameters
    ----------
    G : graph
      A networkx graph.

    max_iter : integer, optional (default=100)
      Maximum number of power iterations.

    tol : float, optional (default=1.0e-6)
      Error tolerance (in Euclidean norm) used to check convergence in
      power iteration.

    nstart : dictionary, optional (default=None)
      Starting value of power iteration for each node. Must have a nonzero
      projection on the desired eigenvector for the power method to converge.
      If None, this implementation uses an all-ones vector, which is a safe
      choice.

    weight : None or string, optional (default=None)
      If None, all edge weights are considered equal. Otherwise holds the
      name of the edge attribute used as weight. In this measure the
      weight is interpreted as the connection strength.

    Returns
    -------
    nodes : dictionary
       Dictionary of nodes with eigenvector centrality as the value. The
       associated vector has unit Euclidean norm and the values are
       nonegative.

    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> centrality = nx.eigenvector_centrality(G)
    >>> sorted((v, f"{c:0.2f}") for v, c in centrality.items())
    [(0, '0.37'), (1, '0.60'), (2, '0.60'), (3, '0.37')]

    Raises
    ------
    NetworkXPointlessConcept
        If the graph G is the null graph.

    NetworkXError
        If each value in `nstart` is zero.

    PowerIterationFailedConvergence
        If the algorithm fails to converge to the specified tolerance
        within the specified number of iterations of the power iteration
        method.

    See Also
    --------
    eigenvector_centrality_numpy
    :func:`~networkx.algorithms.link_analysis.pagerank_alg.pagerank`
    :func:`~networkx.algorithms.link_analysis.hits_alg.hits`

    Notes
    -----
    Eigenvector centrality was introduced by Landau [2]_ for chess
    tournaments. It was later rediscovered by Wei [3]_ and then
    popularized by Kendall [4]_ in the context of sport ranking. Berge
    introduced a general definition for graphs based on social connections
    [5]_. Bonacich [6]_ reintroduced again eigenvector centrality and made
    it popular in link analysis.

    This function computes the left dominant eigenvector, which corresponds
    to adding the centrality of predecessors: this is the usual approach.
    To add the centrality of successors first reverse the graph with
    ``G.reverse()``.

    The implementation uses power iteration [7]_ to compute a dominant
    eigenvector starting from the provided vector `nstart`. Convergence is
    guaranteed as long as `nstart` has a nonzero projection on a dominant
    eigenvector, which certainly happens using the default value.

    The method stops when the change in the computed vector between two
    iterations is smaller than an error tolerance of ``G.number_of_nodes()
    * tol`` or after ``max_iter`` iterations, but in the second case it
    raises an exception.

    This implementation uses $(A + I)$ rather than the adjacency matrix
    $A$ because the change preserves eigenvectors, but it shifts the
    spectrum, thus guaranteeing convergence even for networks with
    negative eigenvalues of maximum modulus.

    References
    ----------
    .. [1] Abraham Berman and Robert J. Plemmons.
       "Nonnegative Matrices in the Mathematical Sciences."
       Classics in Applied Mathematics. SIAM, 1994.

    .. [2] Edmund Landau.
       "Zur relativen Wertbemessung der Turnierresultate."
       Deutsches Wochenschach, 11:366–369, 1895.

    .. [3] Teh-Hsing Wei.
       "The Algebraic Foundations of Ranking Theory."
       PhD thesis, University of Cambridge, 1952.

    .. [4] Maurice G. Kendall.
       "Further contributions to the theory of paired comparisons."
       Biometrics, 11(1):43–62, 1955.
       https://www.jstor.org/stable/3001479

    .. [5] Claude Berge
       "Théorie des graphes et ses applications."
       Dunod, Paris, France, 1958.

    .. [6] Phillip Bonacich.
       "Technique for analyzing overlapping memberships."
       Sociological Methodology, 4:176–185, 1972.
       https://www.jstor.org/stable/270732

    .. [7] Power iteration:: https://en.wikipedia.org/wiki/Power_iteration

    """
    if len(G) == 0:
        raise nx.NetworkXPointlessConcept(
            "cannot compute centrality for the null graph"
        )
    # If no initial vector is provided, start with the all-ones vector.
    if nstart is None:
        nstart = {v: 1 for v in G}
    if all(v == 0 for v in nstart.values()):
        raise nx.NetworkXError("initial vector cannot have all zero values")
    # Normalize the initial vector so that each entry is in [0, 1]. This is
    # guaranteed to never have a divide-by-zero error by the previous line.
    nstart_sum = sum(nstart.values())
    x = {k: v / nstart_sum for k, v in nstart.items()}
    nnodes = G.number_of_nodes()
    # make up to max_iter iterations
    for _ in range(max_iter):
        xlast = x
        x = xlast.copy()  # Start with xlast times I to iterate with (A+I)
        # do the multiplication y^T = x^T A (left eigenvector)
        for n in x:
            for nbr in G[n]:
                w = G[n][nbr].get(weight, 1) if weight else 1
                x[nbr] += xlast[n] * w
        # Normalize the vector. The normalization denominator `norm`
        # should never be zero by the Perron--Frobenius
        # theorem. However, in case it is due to numerical error, we
        # assume the norm to be one instead.
        norm = math.hypot(*x.values()) or 1
        x = {k: v / norm for k, v in x.items()}
        # Check for convergence (in the L_1 norm).
        if sum(abs(x[n] - xlast[n]) for n in x) < nnodes * tol:
            return x
    raise nx.PowerIterationFailedConvergence(max_iter)


@nx._dispatchable(edge_attrs="weight")
def eigenvector_centrality_numpy(G, weight=None, max_iter=50, tol=0):
    r"""Compute the eigenvector centrality for the graph `G`.

    Eigenvector centrality computes the centrality for a node by adding
    the centrality of its predecessors. The centrality for node $i$ is the
    $i$-th element of a left eigenvector associated with the eigenvalue $\lambda$
    of maximum modulus that is positive. Such an eigenvector $x$ is
    defined up to a multiplicative constant by the equation

    .. math::

         \lambda x^T = x^T A,

    where $A$ is the adjacency matrix of the graph `G`. By definition of
    row-column product, the equation above is equivalent to

    .. math::

        \lambda x_i = \sum_{j\to i}x_j.

    That is, adding the eigenvector centralities of the predecessors of
    $i$ one obtains the eigenvector centrality of $i$ multiplied by
    $\lambda$. In the case of undirected graphs, $x$ also solves the familiar
    right-eigenvector equation $Ax = \lambda x$.

    By virtue of the Perron--Frobenius theorem [1]_, if `G` is (strongly)
    connected, there is a unique eigenvector $x$, and all its entries
    are strictly positive.

    However, if `G` is not (strongly) connected, there might be several left
    eigenvectors associated with $\lambda$, and some of their elements
    might be zero.
    Depending on the method used to choose eigenvectors, round-off error can affect
    which of the infinitely many eigenvectors is reported.
    This can lead to inconsistent results for the same graph,
    which the underlying implementation is not robust to.
    For this reason, only (strongly) connected graphs are accepted.

    Parameters
    ----------
    G : graph
        A connected NetworkX graph.

    weight : None or string, optional (default=None)
        If ``None``, all edge weights are considered equal. Otherwise holds the
        name of the edge attribute used as weight. In this measure the
        weight is interpreted as the connection strength.

    max_iter : integer, optional (default=50)
        Maximum number of Arnoldi update iterations allowed.

    tol : float, optional (default=0)
        Relative accuracy for eigenvalues (stopping criterion).
        The default value of 0 implies machine precision.

    Returns
    -------
    nodes : dict of nodes
        Dictionary of nodes with eigenvector centrality as the value. The
        associated vector has unit Euclidean norm and the values are
        nonnegative.

    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> centrality = nx.eigenvector_centrality_numpy(G)
    >>> print([f"{node} {centrality[node]:0.2f}" for node in centrality])
    ['0 0.37', '1 0.60', '2 0.60', '3 0.37']

    Raises
    ------
    NetworkXPointlessConcept
        If the graph `G` is the null graph.

    ArpackNoConvergence
        When the requested convergence is not obtained. The currently
        converged eigenvalues and eigenvectors can be found as
        eigenvalues and eigenvectors attributes of the exception object.

    AmbiguousSolution
        If `G` is not connected.

    See Also
    --------
    :func:`scipy.sparse.linalg.eigs`
    eigenvector_centrality
    :func:`~networkx.algorithms.link_analysis.pagerank_alg.pagerank`
    :func:`~networkx.algorithms.link_analysis.hits_alg.hits`

    Notes
    -----
    Eigenvector centrality was introduced by Landau [2]_ for chess
    tournaments. It was later rediscovered by Wei [3]_ and then
    popularized by Kendall [4]_ in the context of sport ranking. Berge
    introduced a general definition for graphs based on social connections
    [5]_. Bonacich [6]_ reintroduced again eigenvector centrality and made
    it popular in link analysis.

    This function computes the left dominant eigenvector, which corresponds
    to adding the centrality of predecessors: this is the usual approach.
    To add the centrality of successors first reverse the graph with
    ``G.reverse()``.

    This implementation uses the
    :func:`SciPy sparse eigenvalue solver<scipy.sparse.linalg.eigs>` (ARPACK)
    to find the largest eigenvalue/eigenvector pair using Arnoldi iterations
    [7]_.

    References
    ----------
    .. [1] Abraham Berman and Robert J. Plemmons.
       "Nonnegative Matrices in the Mathematical Sciences".
       Classics in Applied Mathematics. SIAM, 1994.

    .. [2] Edmund Landau.
       "Zur relativen Wertbemessung der Turnierresultate".
       Deutsches Wochenschach, 11:366--369, 1895.

    .. [3] Teh-Hsing Wei.
       "The Algebraic Foundations of Ranking Theory".
       PhD thesis, University of Cambridge, 1952.

    .. [4] Maurice G. Kendall.
       "Further contributions to the theory of paired comparisons".
       Biometrics, 11(1):43--62, 1955.
       https://www.jstor.org/stable/3001479

    .. [5] Claude Berge.
       "Théorie des graphes et ses applications".
       Dunod, Paris, France, 1958.

    .. [6] Phillip Bonacich.
       "Technique for analyzing overlapping memberships".
       Sociological Methodology, 4:176--185, 1972.
       https://www.jstor.org/stable/270732

    .. [7] Arnoldi, W. E. (1951).
       "The principle of minimized iterations in the solution of the matrix eigenvalue problem".
       Quarterly of Applied Mathematics. 9 (1): 17--29.
       https://doi.org/10.1090/qam/42792
    """
    import numpy as np
    import scipy as sp

    if len(G) == 0:
        raise nx.NetworkXPointlessConcept(
            "cannot compute centrality for the null graph"
        )
    connected = nx.is_strongly_connected(G) if G.is_directed() else nx.is_connected(G)
    if not connected:  # See gh-6888.
        raise nx.AmbiguousSolution(
            "`eigenvector_centrality_numpy` does not give consistent results for disconnected graphs"
        )
    M = nx.to_scipy_sparse_array(G, nodelist=list(G), weight=weight, dtype=float)
    _, eigenvector = sp.sparse.linalg.eigs(
        M.T, k=1, which="LR", maxiter=max_iter, tol=tol
    )
    largest = eigenvector.flatten().real
    norm = np.sign(largest.sum()) * sp.linalg.norm(largest)
    return dict(zip(G, (largest / norm).tolist()))
