"""Laplacian matrix of graphs.

All calculations here are done using the out-degree. For Laplacians using
in-degree, use `G.reverse(copy=False)` instead of `G` and take the transpose.

The `laplacian_matrix` function provides an unnormalized matrix,
while `normalized_laplacian_matrix`, `directed_laplacian_matrix`,
and `directed_combinatorial_laplacian_matrix` are all normalized.
"""

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = [
    "laplacian_matrix",
    "normalized_laplacian_matrix",
    "total_spanning_tree_weight",
    "directed_laplacian_matrix",
    "directed_combinatorial_laplacian_matrix",
]


@nx._dispatchable(edge_attrs="weight")
def laplacian_matrix(G, nodelist=None, weight="weight"):
    """Returns the Laplacian matrix of G.

    The graph Laplacian is the matrix L = D - A, where
    A is the adjacency matrix and D is the diagonal matrix of node degrees.

    Parameters
    ----------
    G : graph
       A NetworkX graph

    nodelist : list, optional
       The rows and columns are ordered according to the nodes in nodelist.
       If nodelist is None, then the ordering is produced by G.nodes().

    weight : string or None, optional (default='weight')
       The edge data key used to compute each value in the matrix.
       If None, then each edge has weight 1.

    Returns
    -------
    L : SciPy sparse array
      The Laplacian matrix of G.

    Notes
    -----
    For MultiGraph, the edges weights are summed.

    This returns an unnormalized matrix. For a normalized output,
    use `normalized_laplacian_matrix`, `directed_laplacian_matrix`,
    or `directed_combinatorial_laplacian_matrix`.

    This calculation uses the out-degree of the graph `G`. To use the
    in-degree for calculations instead, use `G.reverse(copy=False)` and
    take the transpose.

    See Also
    --------
    :func:`~networkx.convert_matrix.to_numpy_array`
    normalized_laplacian_matrix
    directed_laplacian_matrix
    directed_combinatorial_laplacian_matrix
    :func:`~networkx.linalg.spectrum.laplacian_spectrum`

    Examples
    --------
    For graphs with multiple connected components, L is permutation-similar
    to a block diagonal matrix where each block is the respective Laplacian
    matrix for each component.

    >>> G = nx.Graph([(1, 2), (2, 3), (4, 5)])
    >>> print(nx.laplacian_matrix(G).toarray())
    [[ 1 -1  0  0  0]
     [-1  2 -1  0  0]
     [ 0 -1  1  0  0]
     [ 0  0  0  1 -1]
     [ 0  0  0 -1  1]]

    >>> edges = [
    ...     (1, 2),
    ...     (2, 1),
    ...     (2, 4),
    ...     (4, 3),
    ...     (3, 4),
    ... ]
    >>> DiG = nx.DiGraph(edges)
    >>> print(nx.laplacian_matrix(DiG).toarray())
    [[ 1 -1  0  0]
     [-1  2 -1  0]
     [ 0  0  1 -1]
     [ 0  0 -1  1]]

    Notice that node 4 is represented by the third column and row. This is because
    by default the row/column order is the order of `G.nodes` (i.e. the node added
    order -- in the edgelist, 4 first appears in (2, 4), before node 3 in edge (4, 3).)
    To control the node order of the matrix, use the `nodelist` argument.

    >>> print(nx.laplacian_matrix(DiG, nodelist=[1, 2, 3, 4]).toarray())
    [[ 1 -1  0  0]
     [-1  2  0 -1]
     [ 0  0  1 -1]
     [ 0  0 -1  1]]

    This calculation uses the out-degree of the graph `G`. To use the
    in-degree for calculations instead, use `G.reverse(copy=False)` and
    take the transpose.

    >>> print(nx.laplacian_matrix(DiG.reverse(copy=False)).toarray().T)
    [[ 1 -1  0  0]
     [-1  1 -1  0]
     [ 0  0  2 -1]
     [ 0  0 -1  1]]

    References
    ----------
    .. [1] Langville, Amy N., and Carl D. Meyer. Google’s PageRank and Beyond:
       The Science of Search Engine Rankings. Princeton University Press, 2006.

    """
    import scipy as sp

    if nodelist is None:
        nodelist = list(G)
    A = nx.to_scipy_sparse_array(G, nodelist=nodelist, weight=weight, format="csr")
    n, m = A.shape
    # TODO: rm csr_array wrapper when spdiags can produce arrays
    D = sp.sparse.csr_array(sp.sparse.spdiags(A.sum(axis=1), 0, m, n, format="csr"))
    return D - A


@nx._dispatchable(edge_attrs="weight")
def normalized_laplacian_matrix(G, nodelist=None, weight="weight"):
    r"""Returns the normalized Laplacian matrix of G.

    The normalized graph Laplacian is the matrix

    .. math::

        N = D^{-1/2} L D^{-1/2}

    where `L` is the graph Laplacian and `D` is the diagonal matrix of
    node degrees [1]_.

    Parameters
    ----------
    G : graph
       A NetworkX graph

    nodelist : list, optional
       The rows and columns are ordered according to the nodes in nodelist.
       If nodelist is None, then the ordering is produced by G.nodes().

    weight : string or None, optional (default='weight')
       The edge data key used to compute each value in the matrix.
       If None, then each edge has weight 1.

    Returns
    -------
    N : SciPy sparse array
      The normalized Laplacian matrix of G.

    Notes
    -----
    For MultiGraph, the edges weights are summed.
    See :func:`to_numpy_array` for other options.

    If the Graph contains selfloops, D is defined as ``diag(sum(A, 1))``, where A is
    the adjacency matrix [2]_.

    This calculation uses the out-degree of the graph `G`. To use the
    in-degree for calculations instead, use `G.reverse(copy=False)` and
    take the transpose.

    For an unnormalized output, use `laplacian_matrix`.

    Examples
    --------

    >>> import numpy as np
    >>> edges = [
    ...     (1, 2),
    ...     (2, 1),
    ...     (2, 4),
    ...     (4, 3),
    ...     (3, 4),
    ... ]
    >>> DiG = nx.DiGraph(edges)
    >>> print(nx.normalized_laplacian_matrix(DiG).toarray())
    [[ 1.         -0.70710678  0.          0.        ]
     [-0.70710678  1.         -0.70710678  0.        ]
     [ 0.          0.          1.         -1.        ]
     [ 0.          0.         -1.          1.        ]]

    Notice that node 4 is represented by the third column and row. This is because
    by default the row/column order is the order of `G.nodes` (i.e. the node added
    order -- in the edgelist, 4 first appears in (2, 4), before node 3 in edge (4, 3).)
    To control the node order of the matrix, use the `nodelist` argument.

    >>> print(nx.normalized_laplacian_matrix(DiG, nodelist=[1, 2, 3, 4]).toarray())
    [[ 1.         -0.70710678  0.          0.        ]
     [-0.70710678  1.          0.         -0.70710678]
     [ 0.          0.          1.         -1.        ]
     [ 0.          0.         -1.          1.        ]]
    >>> G = nx.Graph(edges)
    >>> print(nx.normalized_laplacian_matrix(G).toarray())
    [[ 1.         -0.70710678  0.          0.        ]
     [-0.70710678  1.         -0.5         0.        ]
     [ 0.         -0.5         1.         -0.70710678]
     [ 0.          0.         -0.70710678  1.        ]]

    See Also
    --------
    laplacian_matrix
    normalized_laplacian_spectrum
    directed_laplacian_matrix
    directed_combinatorial_laplacian_matrix

    References
    ----------
    .. [1] Fan Chung-Graham, Spectral Graph Theory,
       CBMS Regional Conference Series in Mathematics, Number 92, 1997.
    .. [2] Steve Butler, Interlacing For Weighted Graphs Using The Normalized
       Laplacian, Electronic Journal of Linear Algebra, Volume 16, pp. 90-98,
       March 2007.
    .. [3] Langville, Amy N., and Carl D. Meyer. Google’s PageRank and Beyond:
       The Science of Search Engine Rankings. Princeton University Press, 2006.
    """
    import numpy as np
    import scipy as sp

    if nodelist is None:
        nodelist = list(G)
    A = nx.to_scipy_sparse_array(G, nodelist=nodelist, weight=weight, format="csr")
    n, _ = A.shape
    diags = A.sum(axis=1)
    # TODO: rm csr_array wrapper when spdiags can produce arrays
    D = sp.sparse.csr_array(sp.sparse.spdiags(diags, 0, n, n, format="csr"))
    L = D - A
    with np.errstate(divide="ignore"):
        diags_sqrt = 1.0 / np.sqrt(diags)
    diags_sqrt[np.isinf(diags_sqrt)] = 0
    # TODO: rm csr_array wrapper when spdiags can produce arrays
    DH = sp.sparse.csr_array(sp.sparse.spdiags(diags_sqrt, 0, n, n, format="csr"))
    return DH @ (L @ DH)


@nx._dispatchable(edge_attrs="weight")
def total_spanning_tree_weight(G, weight=None, root=None):
    """
    Returns the total weight of all spanning trees of `G`.

    Kirchoff's Tree Matrix Theorem [1]_, [2]_ states that the determinant of any
    cofactor of the Laplacian matrix of a graph is the number of spanning trees
    in the graph. For a weighted Laplacian matrix, it is the sum across all
    spanning trees of the multiplicative weight of each tree. That is, the
    weight of each tree is the product of its edge weights.

    For unweighted graphs, the total weight equals the number of spanning trees in `G`.

    For directed graphs, the total weight follows by summing over all directed
    spanning trees in `G` that start in the `root` node [3]_.

    .. deprecated:: 3.3

       ``total_spanning_tree_weight`` is deprecated and will be removed in v3.5.
       Use ``nx.number_of_spanning_trees(G)`` instead.

    Parameters
    ----------
    G : NetworkX Graph

    weight : string or None, optional (default=None)
        The key for the edge attribute holding the edge weight.
        If None, then each edge has weight 1.

    root : node (only required for directed graphs)
       A node in the directed graph `G`.

    Returns
    -------
    total_weight : float
        Undirected graphs:
            The sum of the total multiplicative weights for all spanning trees in `G`.
        Directed graphs:
            The sum of the total multiplicative weights for all spanning trees of `G`,
            rooted at node `root`.

    Raises
    ------
    NetworkXPointlessConcept
        If `G` does not contain any nodes.

    NetworkXError
        If the graph `G` is not (weakly) connected,
        or if `G` is directed and the root node is not specified or not in G.

    Examples
    --------
    >>> G = nx.complete_graph(5)
    >>> round(nx.total_spanning_tree_weight(G))
    125

    >>> G = nx.Graph()
    >>> G.add_edge(1, 2, weight=2)
    >>> G.add_edge(1, 3, weight=1)
    >>> G.add_edge(2, 3, weight=1)
    >>> round(nx.total_spanning_tree_weight(G, "weight"))
    5

    Notes
    -----
    Self-loops are excluded. Multi-edges are contracted in one edge
    equal to the sum of the weights.

    References
    ----------
    .. [1] Wikipedia
       "Kirchhoff's theorem."
       https://en.wikipedia.org/wiki/Kirchhoff%27s_theorem
    .. [2] Kirchhoff, G. R.
        Über die Auflösung der Gleichungen, auf welche man
        bei der Untersuchung der linearen Vertheilung
        Galvanischer Ströme geführt wird
        Annalen der Physik und Chemie, vol. 72, pp. 497-508, 1847.
    .. [3] Margoliash, J.
        "Matrix-Tree Theorem for Directed Graphs"
        https://www.math.uchicago.edu/~may/VIGRE/VIGRE2010/REUPapers/Margoliash.pdf
    """
    import warnings

    warnings.warn(
        (
            "\n\ntotal_spanning_tree_weight is deprecated and will be removed in v3.5.\n"
            "Use `nx.number_of_spanning_trees(G)` instead."
        ),
        category=DeprecationWarning,
        stacklevel=3,
    )

    return nx.number_of_spanning_trees(G, weight=weight, root=root)


###############################################################################
# Code based on work from https://github.com/bjedwards


@not_implemented_for("undirected")
@not_implemented_for("multigraph")
@nx._dispatchable(edge_attrs="weight")
def directed_laplacian_matrix(
    G, nodelist=None, weight="weight", walk_type=None, alpha=0.95
):
    r"""Returns the directed Laplacian matrix of G.

    The graph directed Laplacian is the matrix

    .. math::

        L = I - \frac{1}{2} \left (\Phi^{1/2} P \Phi^{-1/2} + \Phi^{-1/2} P^T \Phi^{1/2} \right )

    where `I` is the identity matrix, `P` is the transition matrix of the
    graph, and `\Phi` a matrix with the Perron vector of `P` in the diagonal and
    zeros elsewhere [1]_.

    Depending on the value of walk_type, `P` can be the transition matrix
    induced by a random walk, a lazy random walk, or a random walk with
    teleportation (PageRank).

    Parameters
    ----------
    G : DiGraph
       A NetworkX graph

    nodelist : list, optional
       The rows and columns are ordered according to the nodes in nodelist.
       If nodelist is None, then the ordering is produced by G.nodes().

    weight : string or None, optional (default='weight')
       The edge data key used to compute each value in the matrix.
       If None, then each edge has weight 1.

    walk_type : string or None, optional (default=None)
       One of ``"random"``, ``"lazy"``, or ``"pagerank"``. If ``walk_type=None``
       (the default), then a value is selected according to the properties of `G`:
       - ``walk_type="random"`` if `G` is strongly connected and aperiodic
       - ``walk_type="lazy"`` if `G` is strongly connected but not aperiodic
       - ``walk_type="pagerank"`` for all other cases.

    alpha : real
       (1 - alpha) is the teleportation probability used with pagerank

    Returns
    -------
    L : NumPy matrix
      Normalized Laplacian of G.

    Notes
    -----
    Only implemented for DiGraphs

    The result is always a symmetric matrix.

    This calculation uses the out-degree of the graph `G`. To use the
    in-degree for calculations instead, use `G.reverse(copy=False)` and
    take the transpose.

    See Also
    --------
    laplacian_matrix
    normalized_laplacian_matrix
    directed_combinatorial_laplacian_matrix

    References
    ----------
    .. [1] Fan Chung (2005).
       Laplacians and the Cheeger inequality for directed graphs.
       Annals of Combinatorics, 9(1), 2005
    """
    import numpy as np
    import scipy as sp

    # NOTE: P has type ndarray if walk_type=="pagerank", else csr_array
    P = _transition_matrix(
        G, nodelist=nodelist, weight=weight, walk_type=walk_type, alpha=alpha
    )

    n, m = P.shape

    evals, evecs = sp.sparse.linalg.eigs(P.T, k=1)
    v = evecs.flatten().real
    p = v / v.sum()
    # p>=0 by Perron-Frobenius Thm. Use abs() to fix roundoff across zero gh-6865
    sqrtp = np.sqrt(np.abs(p))
    Q = (
        # TODO: rm csr_array wrapper when spdiags creates arrays
        sp.sparse.csr_array(sp.sparse.spdiags(sqrtp, 0, n, n))
        @ P
        # TODO: rm csr_array wrapper when spdiags creates arrays
        @ sp.sparse.csr_array(sp.sparse.spdiags(1.0 / sqrtp, 0, n, n))
    )
    # NOTE: This could be sparsified for the non-pagerank cases
    I = np.identity(len(G))

    return I - (Q + Q.T) / 2.0


@not_implemented_for("undirected")
@not_implemented_for("multigraph")
@nx._dispatchable(edge_attrs="weight")
def directed_combinatorial_laplacian_matrix(
    G, nodelist=None, weight="weight", walk_type=None, alpha=0.95
):
    r"""Return the directed combinatorial Laplacian matrix of G.

    The graph directed combinatorial Laplacian is the matrix

    .. math::

        L = \Phi - \frac{1}{2} \left (\Phi P + P^T \Phi \right)

    where `P` is the transition matrix of the graph and `\Phi` a matrix
    with the Perron vector of `P` in the diagonal and zeros elsewhere [1]_.

    Depending on the value of walk_type, `P` can be the transition matrix
    induced by a random walk, a lazy random walk, or a random walk with
    teleportation (PageRank).

    Parameters
    ----------
    G : DiGraph
       A NetworkX graph

    nodelist : list, optional
       The rows and columns are ordered according to the nodes in nodelist.
       If nodelist is None, then the ordering is produced by G.nodes().

    weight : string or None, optional (default='weight')
       The edge data key used to compute each value in the matrix.
       If None, then each edge has weight 1.

    walk_type : string or None, optional (default=None)
        One of ``"random"``, ``"lazy"``, or ``"pagerank"``. If ``walk_type=None``
        (the default), then a value is selected according to the properties of `G`:
        - ``walk_type="random"`` if `G` is strongly connected and aperiodic
        - ``walk_type="lazy"`` if `G` is strongly connected but not aperiodic
        - ``walk_type="pagerank"`` for all other cases.

    alpha : real
       (1 - alpha) is the teleportation probability used with pagerank

    Returns
    -------
    L : NumPy matrix
      Combinatorial Laplacian of G.

    Notes
    -----
    Only implemented for DiGraphs

    The result is always a symmetric matrix.

    This calculation uses the out-degree of the graph `G`. To use the
    in-degree for calculations instead, use `G.reverse(copy=False)` and
    take the transpose.

    See Also
    --------
    laplacian_matrix
    normalized_laplacian_matrix
    directed_laplacian_matrix

    References
    ----------
    .. [1] Fan Chung (2005).
       Laplacians and the Cheeger inequality for directed graphs.
       Annals of Combinatorics, 9(1), 2005
    """
    import scipy as sp

    P = _transition_matrix(
        G, nodelist=nodelist, weight=weight, walk_type=walk_type, alpha=alpha
    )

    n, m = P.shape

    evals, evecs = sp.sparse.linalg.eigs(P.T, k=1)
    v = evecs.flatten().real
    p = v / v.sum()
    # NOTE: could be improved by not densifying
    # TODO: Rm csr_array wrapper when spdiags array creation becomes available
    Phi = sp.sparse.csr_array(sp.sparse.spdiags(p, 0, n, n)).toarray()

    return Phi - (Phi @ P + P.T @ Phi) / 2.0


def _transition_matrix(G, nodelist=None, weight="weight", walk_type=None, alpha=0.95):
    """Returns the transition matrix of G.

    This is a row stochastic giving the transition probabilities while
    performing a random walk on the graph. Depending on the value of walk_type,
    P can be the transition matrix induced by a random walk, a lazy random walk,
    or a random walk with teleportation (PageRank).

    Parameters
    ----------
    G : DiGraph
       A NetworkX graph

    nodelist : list, optional
       The rows and columns are ordered according to the nodes in nodelist.
       If nodelist is None, then the ordering is produced by G.nodes().

    weight : string or None, optional (default='weight')
       The edge data key used to compute each value in the matrix.
       If None, then each edge has weight 1.

    walk_type : string or None, optional (default=None)
       One of ``"random"``, ``"lazy"``, or ``"pagerank"``. If ``walk_type=None``
       (the default), then a value is selected according to the properties of `G`:
        - ``walk_type="random"`` if `G` is strongly connected and aperiodic
        - ``walk_type="lazy"`` if `G` is strongly connected but not aperiodic
        - ``walk_type="pagerank"`` for all other cases.

    alpha : real
       (1 - alpha) is the teleportation probability used with pagerank

    Returns
    -------
    P : numpy.ndarray
      transition matrix of G.

    Raises
    ------
    NetworkXError
        If walk_type not specified or alpha not in valid range
    """
    import numpy as np
    import scipy as sp

    if walk_type is None:
        if nx.is_strongly_connected(G):
            if nx.is_aperiodic(G):
                walk_type = "random"
            else:
                walk_type = "lazy"
        else:
            walk_type = "pagerank"

    A = nx.to_scipy_sparse_array(G, nodelist=nodelist, weight=weight, dtype=float)
    n, m = A.shape
    if walk_type in ["random", "lazy"]:
        # TODO: Rm csr_array wrapper when spdiags array creation becomes available
        DI = sp.sparse.csr_array(sp.sparse.spdiags(1.0 / A.sum(axis=1), 0, n, n))
        if walk_type == "random":
            P = DI @ A
        else:
            # TODO: Rm csr_array wrapper when identity array creation becomes available
            I = sp.sparse.csr_array(sp.sparse.identity(n))
            P = (I + DI @ A) / 2.0

    elif walk_type == "pagerank":
        if not (0 < alpha < 1):
            raise nx.NetworkXError("alpha must be between 0 and 1")
        # this is using a dense representation. NOTE: This should be sparsified!
        A = A.toarray()
        # add constant to dangling nodes' row
        A[A.sum(axis=1) == 0, :] = 1 / n
        # normalize
        A = A / A.sum(axis=1)[np.newaxis, :].T
        P = alpha * A + (1 - alpha) / n
    else:
        raise nx.NetworkXError("walk_type must be random, lazy, or pagerank")

    return P
