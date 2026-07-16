"""
Eigenvalue spectrum of graphs.
"""

import networkx as nx

__all__ = [
    "laplacian_spectrum",
    "adjacency_spectrum",
    "modularity_spectrum",
    "normalized_laplacian_spectrum",
    "bethe_hessian_spectrum",
]


@nx._dispatchable(edge_attrs="weight")
def laplacian_spectrum(G, weight="weight"):
    """Returns eigenvalues of the Laplacian of G

    Parameters
    ----------
    G : graph
       A NetworkX graph

    weight : string or None, optional (default='weight')
       The edge data key used to compute each value in the matrix.
       If None, then each edge has weight 1.

    Returns
    -------
    evals : NumPy array
      Eigenvalues

    Notes
    -----
    For MultiGraph/MultiDiGraph, the edges weights are summed.
    See :func:`~networkx.convert_matrix.to_numpy_array` for other options.

    See Also
    --------
    laplacian_matrix

    Examples
    --------
    The multiplicity of 0 as an eigenvalue of the laplacian matrix is equal
    to the number of connected components of G.

    >>> G = nx.Graph()  # Create a graph with 5 nodes and 3 connected components
    >>> G.add_nodes_from(range(5))
    >>> G.add_edges_from([(0, 2), (3, 4)])
    >>> nx.laplacian_spectrum(G)
    array([0., 0., 0., 2., 2.])

    """
    import scipy as sp

    return sp.linalg.eigvalsh(nx.laplacian_matrix(G, weight=weight).todense())


@nx._dispatchable(edge_attrs="weight")
def normalized_laplacian_spectrum(G, weight="weight"):
    """Return eigenvalues of the normalized Laplacian of G

    Parameters
    ----------
    G : graph
       A NetworkX graph

    weight : string or None, optional (default='weight')
       The edge data key used to compute each value in the matrix.
       If None, then each edge has weight 1.

    Returns
    -------
    evals : NumPy array
      Eigenvalues

    Notes
    -----
    For MultiGraph/MultiDiGraph, the edges weights are summed.
    See to_numpy_array for other options.

    See Also
    --------
    normalized_laplacian_matrix
    """
    import scipy as sp

    return sp.linalg.eigvalsh(
        nx.normalized_laplacian_matrix(G, weight=weight).todense()
    )


@nx._dispatchable(edge_attrs="weight")
def adjacency_spectrum(G, weight="weight"):
    """Returns eigenvalues of the adjacency matrix of G.

    Parameters
    ----------
    G : graph
       A NetworkX graph

    weight : string or None, optional (default='weight')
       The edge data key used to compute each value in the matrix.
       If None, then each edge has weight 1.

    Returns
    -------
    evals : NumPy array
      Eigenvalues

    Notes
    -----
    For MultiGraph/MultiDiGraph, the edges weights are summed.
    See to_numpy_array for other options.

    See Also
    --------
    adjacency_matrix
    """
    import scipy as sp

    return sp.linalg.eigvals(nx.adjacency_matrix(G, weight=weight).todense())


@nx._dispatchable
def modularity_spectrum(G):
    """Returns eigenvalues of the modularity matrix of G.

    Parameters
    ----------
    G : Graph
       A NetworkX Graph or DiGraph

    Returns
    -------
    evals : NumPy array
      Eigenvalues

    See Also
    --------
    modularity_matrix

    References
    ----------
    .. [1] M. E. J. Newman, "Modularity and community structure in networks",
       Proc. Natl. Acad. Sci. USA, vol. 103, pp. 8577-8582, 2006.
    """
    import scipy as sp

    if G.is_directed():
        return sp.linalg.eigvals(nx.directed_modularity_matrix(G))
    else:
        return sp.linalg.eigvals(nx.modularity_matrix(G))


@nx._dispatchable
def bethe_hessian_spectrum(G, r=None):
    """Returns eigenvalues of the Bethe Hessian matrix of G.

    Parameters
    ----------
    G : Graph
       A NetworkX Graph or DiGraph

    r : float
       Regularizer parameter

    Returns
    -------
    evals : NumPy array
      Eigenvalues

    See Also
    --------
    bethe_hessian_matrix

    References
    ----------
    .. [1] A. Saade, F. Krzakala and L. Zdeborová
       "Spectral clustering of graphs with the bethe hessian",
       Advances in Neural Information Processing Systems. 2014.
    """
    import scipy as sp

    return sp.linalg.eigvalsh(nx.bethe_hessian_matrix(G, r).todense())
