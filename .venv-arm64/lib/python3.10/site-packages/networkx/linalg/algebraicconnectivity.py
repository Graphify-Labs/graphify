"""
Algebraic connectivity and Fiedler vectors of undirected graphs.
"""

from functools import partial

import networkx as nx
from networkx.utils import (
    not_implemented_for,
    np_random_state,
    reverse_cuthill_mckee_ordering,
)

__all__ = [
    "algebraic_connectivity",
    "fiedler_vector",
    "spectral_ordering",
    "spectral_bisection",
]


class _PCGSolver:
    """Preconditioned conjugate gradient method.

    To solve Ax = b:
        M = A.diagonal() # or some other preconditioner
        solver = _PCGSolver(lambda x: A * x, lambda x: M * x)
        x = solver.solve(b)

    The inputs A and M are functions which compute
    matrix multiplication on the argument.
    A - multiply by the matrix A in Ax=b
    M - multiply by M, the preconditioner surrogate for A

    Warning: There is no limit on number of iterations.
    """

    def __init__(self, A, M):
        self._A = A
        self._M = M

    def solve(self, B, tol):
        import numpy as np

        # Densifying step - can this be kept sparse?
        B = np.asarray(B)
        X = np.ndarray(B.shape, order="F")
        for j in range(B.shape[1]):
            X[:, j] = self._solve(B[:, j], tol)
        return X

    def _solve(self, b, tol):
        import numpy as np
        import scipy as sp

        A = self._A
        M = self._M
        tol *= sp.linalg.blas.dasum(b)
        # Initialize.
        x = np.zeros(b.shape)
        r = b.copy()
        z = M(r)
        rz = sp.linalg.blas.ddot(r, z)
        p = z.copy()
        # Iterate.
        while True:
            Ap = A(p)
            alpha = rz / sp.linalg.blas.ddot(p, Ap)
            x = sp.linalg.blas.daxpy(p, x, a=alpha)
            r = sp.linalg.blas.daxpy(Ap, r, a=-alpha)
            if sp.linalg.blas.dasum(r) < tol:
                return x
            z = M(r)
            beta = sp.linalg.blas.ddot(r, z)
            beta, rz = beta / rz, beta
            p = sp.linalg.blas.daxpy(p, z, a=beta)


class _LUSolver:
    """LU factorization.

    To solve Ax = b:
        solver = _LUSolver(A)
        x = solver.solve(b)

    optional argument `tol` on solve method is ignored but included
    to match _PCGsolver API.
    """

    def __init__(self, A):
        import scipy as sp

        self._LU = sp.sparse.linalg.splu(
            A,
            permc_spec="MMD_AT_PLUS_A",
            diag_pivot_thresh=0.0,
            options={"Equil": True, "SymmetricMode": True},
        )

    def solve(self, B, tol=None):
        import numpy as np

        B = np.asarray(B)
        X = np.ndarray(B.shape, order="F")
        for j in range(B.shape[1]):
            X[:, j] = self._LU.solve(B[:, j])
        return X


def _preprocess_graph(G, weight):
    """Compute edge weights and eliminate zero-weight edges."""
    if G.is_directed():
        H = nx.MultiGraph()
        H.add_nodes_from(G)
        H.add_weighted_edges_from(
            ((u, v, e.get(weight, 1.0)) for u, v, e in G.edges(data=True) if u != v),
            weight=weight,
        )
        G = H
    if not G.is_multigraph():
        edges = (
            (u, v, abs(e.get(weight, 1.0))) for u, v, e in G.edges(data=True) if u != v
        )
    else:
        edges = (
            (u, v, sum(abs(e.get(weight, 1.0)) for e in G[u][v].values()))
            for u, v in G.edges()
            if u != v
        )
    H = nx.Graph()
    H.add_nodes_from(G)
    H.add_weighted_edges_from((u, v, e) for u, v, e in edges if e != 0)
    return H


def _rcm_estimate(G, nodelist):
    """Estimate the Fiedler vector using the reverse Cuthill-McKee ordering."""
    import numpy as np

    G = G.subgraph(nodelist)
    order = reverse_cuthill_mckee_ordering(G)
    n = len(nodelist)
    index = dict(zip(nodelist, range(n)))
    x = np.ndarray(n, dtype=float)
    for i, u in enumerate(order):
        x[index[u]] = i
    x -= (n - 1) / 2.0
    return x


def _tracemin_fiedler(L, X, normalized, tol, method):
    """Compute the Fiedler vector of L using the TraceMIN-Fiedler algorithm.

    The Fiedler vector of a connected undirected graph is the eigenvector
    corresponding to the second smallest eigenvalue of the Laplacian matrix
    of the graph. This function starts with the Laplacian L, not the Graph.

    Parameters
    ----------
    L : Laplacian of a possibly weighted or normalized, but undirected graph

    X : Initial guess for a solution. Usually a matrix of random numbers.
        This function allows more than one column in X to identify more than
        one eigenvector if desired.

    normalized : bool
        Whether the normalized Laplacian matrix is used.

    tol : float
        Tolerance of relative residual in eigenvalue computation.
        Warning: There is no limit on number of iterations.

    method : string
        Should be 'tracemin_pcg' or 'tracemin_lu'.
        Otherwise exception is raised.

    Returns
    -------
    sigma, X : Two NumPy arrays of floats.
        The lowest eigenvalues and corresponding eigenvectors of L.
        The size of input X determines the size of these outputs.
        As this is for Fiedler vectors, the zero eigenvalue (and
        constant eigenvector) are avoided.
    """
    import numpy as np
    import scipy as sp

    n = X.shape[0]

    if normalized:
        # Form the normalized Laplacian matrix and determine the eigenvector of
        # its nullspace.
        e = np.sqrt(L.diagonal())
        # TODO: rm csr_array wrapper when spdiags array creation becomes available
        D = sp.sparse.csr_array(sp.sparse.spdiags(1 / e, 0, n, n, format="csr"))
        L = D @ L @ D
        e *= 1.0 / np.linalg.norm(e, 2)

    if normalized:

        def project(X):
            """Make X orthogonal to the nullspace of L."""
            X = np.asarray(X)
            for j in range(X.shape[1]):
                X[:, j] -= (X[:, j] @ e) * e

    else:

        def project(X):
            """Make X orthogonal to the nullspace of L."""
            X = np.asarray(X)
            for j in range(X.shape[1]):
                X[:, j] -= X[:, j].sum() / n

    if method == "tracemin_pcg":
        D = L.diagonal().astype(float)
        solver = _PCGSolver(lambda x: L @ x, lambda x: D * x)
    elif method == "tracemin_lu":
        # Convert A to CSC to suppress SparseEfficiencyWarning.
        A = sp.sparse.csc_array(L, dtype=float, copy=True)
        # Force A to be nonsingular. Since A is the Laplacian matrix of a
        # connected graph, its rank deficiency is one, and thus one diagonal
        # element needs to modified. Changing to infinity forces a zero in the
        # corresponding element in the solution.
        i = (A.indptr[1:] - A.indptr[:-1]).argmax()
        A[i, i] = np.inf
        solver = _LUSolver(A)
    else:
        raise nx.NetworkXError(f"Unknown linear system solver: {method}")

    # Initialize.
    Lnorm = abs(L).sum(axis=1).flatten().max()
    project(X)
    W = np.ndarray(X.shape, order="F")

    while True:
        # Orthonormalize X.
        X = np.linalg.qr(X)[0]
        # Compute iteration matrix H.
        W[:, :] = L @ X
        H = X.T @ W
        sigma, Y = sp.linalg.eigh(H, overwrite_a=True)
        # Compute the Ritz vectors.
        X = X @ Y
        # Test for convergence exploiting the fact that L * X == W * Y.
        res = sp.linalg.blas.dasum(W @ Y[:, 0] - sigma[0] * X[:, 0]) / Lnorm
        if res < tol:
            break
        # Compute X = L \ X / (X' * (L \ X)).
        # L \ X can have an arbitrary projection on the nullspace of L,
        # which will be eliminated.
        W[:, :] = solver.solve(X, tol)
        X = (sp.linalg.inv(W.T @ X) @ W.T).T  # Preserves Fortran storage order.
        project(X)

    return sigma, np.asarray(X)


def _get_fiedler_func(method):
    """Returns a function that solves the Fiedler eigenvalue problem."""
    import numpy as np

    if method == "tracemin":  # old style keyword <v2.1
        method = "tracemin_pcg"
    if method in ("tracemin_pcg", "tracemin_lu"):

        def find_fiedler(L, x, normalized, tol, seed):
            q = 1 if method == "tracemin_pcg" else min(4, L.shape[0] - 1)
            X = np.asarray(seed.normal(size=(q, L.shape[0]))).T
            sigma, X = _tracemin_fiedler(L, X, normalized, tol, method)
            return sigma[0], X[:, 0]

    elif method == "lanczos" or method == "lobpcg":

        def find_fiedler(L, x, normalized, tol, seed):
            import scipy as sp

            L = sp.sparse.csc_array(L, dtype=float)
            n = L.shape[0]
            if normalized:
                # TODO: rm csc_array wrapping when spdiags array becomes available
                D = sp.sparse.csc_array(
                    sp.sparse.spdiags(
                        1.0 / np.sqrt(L.diagonal()), [0], n, n, format="csc"
                    )
                )
                L = D @ L @ D
            if method == "lanczos" or n < 10:
                # Avoid LOBPCG when n < 10 due to
                # https://github.com/scipy/scipy/issues/3592
                # https://github.com/scipy/scipy/pull/3594
                sigma, X = sp.sparse.linalg.eigsh(
                    L, 2, which="SM", tol=tol, return_eigenvectors=True
                )
                return sigma[1], X[:, 1]
            else:
                X = np.asarray(np.atleast_2d(x).T)
                # TODO: rm csr_array wrapping when spdiags array becomes available
                M = sp.sparse.csr_array(sp.sparse.spdiags(1.0 / L.diagonal(), 0, n, n))
                Y = np.ones(n)
                if normalized:
                    Y /= D.diagonal()
                sigma, X = sp.sparse.linalg.lobpcg(
                    L, X, M=M, Y=np.atleast_2d(Y).T, tol=tol, maxiter=n, largest=False
                )
                return sigma[0], X[:, 0]

    else:
        raise nx.NetworkXError(f"unknown method {method!r}.")

    return find_fiedler


@not_implemented_for("directed")
@np_random_state(5)
@nx._dispatchable(edge_attrs="weight")
def algebraic_connectivity(
    G, weight="weight", normalized=False, tol=1e-8, method="tracemin_pcg", seed=None
):
    r"""Returns the algebraic connectivity of an undirected graph.

    The algebraic connectivity of a connected undirected graph is the second
    smallest eigenvalue of its Laplacian matrix.

    Parameters
    ----------
    G : NetworkX graph
        An undirected graph.

    weight : object, optional (default: None)
        The data key used to determine the weight of each edge. If None, then
        each edge has unit weight.

    normalized : bool, optional (default: False)
        Whether the normalized Laplacian matrix is used.

    tol : float, optional (default: 1e-8)
        Tolerance of relative residual in eigenvalue computation.

    method : string, optional (default: 'tracemin_pcg')
        Method of eigenvalue computation. It must be one of the tracemin
        options shown below (TraceMIN), 'lanczos' (Lanczos iteration)
        or 'lobpcg' (LOBPCG).

        The TraceMIN algorithm uses a linear system solver. The following
        values allow specifying the solver to be used.

        =============== ========================================
        Value           Solver
        =============== ========================================
        'tracemin_pcg'  Preconditioned conjugate gradient method
        'tracemin_lu'   LU factorization
        =============== ========================================

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    algebraic_connectivity : float
        Algebraic connectivity.

    Raises
    ------
    NetworkXNotImplemented
        If G is directed.

    NetworkXError
        If G has less than two nodes.

    Notes
    -----
    Edge weights are interpreted by their absolute values. For MultiGraph's,
    weights of parallel edges are summed. Zero-weighted edges are ignored.

    See Also
    --------
    laplacian_matrix

    Examples
    --------
    For undirected graphs algebraic connectivity can tell us if a graph is connected or not
    `G` is connected iff  ``algebraic_connectivity(G) > 0``:

    >>> G = nx.complete_graph(5)
    >>> nx.algebraic_connectivity(G) > 0
    True
    >>> G.add_node(10)  # G is no longer connected
    >>> nx.algebraic_connectivity(G) > 0
    False

    """
    if len(G) < 2:
        raise nx.NetworkXError("graph has less than two nodes.")
    G = _preprocess_graph(G, weight)
    if not nx.is_connected(G):
        return 0.0

    L = nx.laplacian_matrix(G)
    if L.shape[0] == 2:
        return 2.0 * float(L[0, 0]) if not normalized else 2.0

    find_fiedler = _get_fiedler_func(method)
    x = None if method != "lobpcg" else _rcm_estimate(G, G)
    sigma, fiedler = find_fiedler(L, x, normalized, tol, seed)
    return float(sigma)


@not_implemented_for("directed")
@np_random_state(5)
@nx._dispatchable(edge_attrs="weight")
def fiedler_vector(
    G, weight="weight", normalized=False, tol=1e-8, method="tracemin_pcg", seed=None
):
    """Returns the Fiedler vector of a connected undirected graph.

    The Fiedler vector of a connected undirected graph is the eigenvector
    corresponding to the second smallest eigenvalue of the Laplacian matrix
    of the graph.

    Parameters
    ----------
    G : NetworkX graph
        An undirected graph.

    weight : object, optional (default: None)
        The data key used to determine the weight of each edge. If None, then
        each edge has unit weight.

    normalized : bool, optional (default: False)
        Whether the normalized Laplacian matrix is used.

    tol : float, optional (default: 1e-8)
        Tolerance of relative residual in eigenvalue computation.

    method : string, optional (default: 'tracemin_pcg')
        Method of eigenvalue computation. It must be one of the tracemin
        options shown below (TraceMIN), 'lanczos' (Lanczos iteration)
        or 'lobpcg' (LOBPCG).

        The TraceMIN algorithm uses a linear system solver. The following
        values allow specifying the solver to be used.

        =============== ========================================
        Value           Solver
        =============== ========================================
        'tracemin_pcg'  Preconditioned conjugate gradient method
        'tracemin_lu'   LU factorization
        =============== ========================================

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    fiedler_vector : NumPy array of floats.
        Fiedler vector.

    Raises
    ------
    NetworkXNotImplemented
        If G is directed.

    NetworkXError
        If G has less than two nodes or is not connected.

    Notes
    -----
    Edge weights are interpreted by their absolute values. For MultiGraph's,
    weights of parallel edges are summed. Zero-weighted edges are ignored.

    See Also
    --------
    laplacian_matrix

    Examples
    --------
    Given a connected graph the signs of the values in the Fiedler vector can be
    used to partition the graph into two components.

    >>> G = nx.barbell_graph(5, 0)
    >>> nx.fiedler_vector(G, normalized=True, seed=1)
    array([-0.32864129, -0.32864129, -0.32864129, -0.32864129, -0.26072899,
            0.26072899,  0.32864129,  0.32864129,  0.32864129,  0.32864129])

    The connected components are the two 5-node cliques of the barbell graph.
    """
    import numpy as np

    if len(G) < 2:
        raise nx.NetworkXError("graph has less than two nodes.")
    G = _preprocess_graph(G, weight)
    if not nx.is_connected(G):
        raise nx.NetworkXError("graph is not connected.")

    if len(G) == 2:
        return np.array([1.0, -1.0])

    find_fiedler = _get_fiedler_func(method)
    L = nx.laplacian_matrix(G)
    x = None if method != "lobpcg" else _rcm_estimate(G, G)
    sigma, fiedler = find_fiedler(L, x, normalized, tol, seed)
    return fiedler


@np_random_state(5)
@nx._dispatchable(edge_attrs="weight")
def spectral_ordering(
    G, weight="weight", normalized=False, tol=1e-8, method="tracemin_pcg", seed=None
):
    """Compute the spectral_ordering of a graph.

    The spectral ordering of a graph is an ordering of its nodes where nodes
    in the same weakly connected components appear contiguous and ordered by
    their corresponding elements in the Fiedler vector of the component.

    Parameters
    ----------
    G : NetworkX graph
        A graph.

    weight : object, optional (default: None)
        The data key used to determine the weight of each edge. If None, then
        each edge has unit weight.

    normalized : bool, optional (default: False)
        Whether the normalized Laplacian matrix is used.

    tol : float, optional (default: 1e-8)
        Tolerance of relative residual in eigenvalue computation.

    method : string, optional (default: 'tracemin_pcg')
        Method of eigenvalue computation. It must be one of the tracemin
        options shown below (TraceMIN), 'lanczos' (Lanczos iteration)
        or 'lobpcg' (LOBPCG).

        The TraceMIN algorithm uses a linear system solver. The following
        values allow specifying the solver to be used.

        =============== ========================================
        Value           Solver
        =============== ========================================
        'tracemin_pcg'  Preconditioned conjugate gradient method
        'tracemin_lu'   LU factorization
        =============== ========================================

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    spectral_ordering : NumPy array of floats.
        Spectral ordering of nodes.

    Raises
    ------
    NetworkXError
        If G is empty.

    Notes
    -----
    Edge weights are interpreted by their absolute values. For MultiGraph's,
    weights of parallel edges are summed. Zero-weighted edges are ignored.

    See Also
    --------
    laplacian_matrix
    """
    if len(G) == 0:
        raise nx.NetworkXError("graph is empty.")
    G = _preprocess_graph(G, weight)

    find_fiedler = _get_fiedler_func(method)
    order = []
    for component in nx.connected_components(G):
        size = len(component)
        if size > 2:
            L = nx.laplacian_matrix(G, component)
            x = None if method != "lobpcg" else _rcm_estimate(G, component)
            sigma, fiedler = find_fiedler(L, x, normalized, tol, seed)
            sort_info = zip(fiedler, range(size), component)
            order.extend(u for x, c, u in sorted(sort_info))
        else:
            order.extend(component)

    return order


@nx._dispatchable(edge_attrs="weight")
def spectral_bisection(
    G, weight="weight", normalized=False, tol=1e-8, method="tracemin_pcg", seed=None
):
    """Bisect the graph using the Fiedler vector.

    This method uses the Fiedler vector to bisect a graph.
    The partition is defined by the nodes which are associated with
    either positive or negative values in the vector.

    Parameters
    ----------
    G : NetworkX Graph

    weight : str, optional (default: weight)
        The data key used to determine the weight of each edge. If None, then
        each edge has unit weight.

    normalized : bool, optional (default: False)
        Whether the normalized Laplacian matrix is used.

    tol : float, optional (default: 1e-8)
        Tolerance of relative residual in eigenvalue computation.

    method : string, optional (default: 'tracemin_pcg')
        Method of eigenvalue computation. It must be one of the tracemin
        options shown below (TraceMIN), 'lanczos' (Lanczos iteration)
        or 'lobpcg' (LOBPCG).

        The TraceMIN algorithm uses a linear system solver. The following
        values allow specifying the solver to be used.

        =============== ========================================
        Value           Solver
        =============== ========================================
        'tracemin_pcg'  Preconditioned conjugate gradient method
        'tracemin_lu'   LU factorization
        =============== ========================================

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    bisection : tuple of sets
        Sets with the bisection of nodes

    Examples
    --------
    >>> G = nx.barbell_graph(3, 0)
    >>> nx.spectral_bisection(G)
    ({0, 1, 2}, {3, 4, 5})

    References
    ----------
    .. [1] M. E. J Newman 'Networks: An Introduction', pages 364-370
       Oxford University Press 2011.
    """
    import numpy as np

    v = nx.fiedler_vector(G, weight, normalized, tol, method, seed)
    nodes = np.array(list(G))
    pos_vals = v >= 0

    return set(nodes[~pos_vals].tolist()), set(nodes[pos_vals].tolist())
