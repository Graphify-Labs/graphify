"""Bethe Hessian or deformed Laplacian matrix of graphs."""

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = ["bethe_hessian_matrix"]


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def bethe_hessian_matrix(G, r=None, nodelist=None):
    r"""Returns the Bethe Hessian matrix of G.

    The Bethe Hessian is a family of matrices parametrized by r, defined as
    H(r) = (r^2 - 1) I - r A + D where A is the adjacency matrix, D is the
    diagonal matrix of node degrees, and I is the identify matrix. It is equal
    to the graph laplacian when the regularizer r = 1.

    The default choice of regularizer should be the ratio [2]_

    .. math::
      r_m = \left(\sum k_i \right)^{-1}\left(\sum k_i^2 \right) - 1

    Parameters
    ----------
    G : Graph
       A NetworkX graph
    r : float
       Regularizer parameter
    nodelist : list, optional
       The rows and columns are ordered according to the nodes in nodelist.
       If nodelist is None, then the ordering is produced by ``G.nodes()``.

    Returns
    -------
    H : scipy.sparse.csr_array
      The Bethe Hessian matrix of `G`, with parameter `r`.

    Examples
    --------
    >>> k = [3, 2, 2, 1, 0]
    >>> G = nx.havel_hakimi_graph(k)
    >>> H = nx.bethe_hessian_matrix(G)
    >>> H.toarray()
    array([[ 3.5625, -1.25  , -1.25  , -1.25  ,  0.    ],
           [-1.25  ,  2.5625, -1.25  ,  0.    ,  0.    ],
           [-1.25  , -1.25  ,  2.5625,  0.    ,  0.    ],
           [-1.25  ,  0.    ,  0.    ,  1.5625,  0.    ],
           [ 0.    ,  0.    ,  0.    ,  0.    ,  0.5625]])

    See Also
    --------
    bethe_hessian_spectrum
    adjacency_matrix
    laplacian_matrix

    References
    ----------
    .. [1] A. Saade, F. Krzakala and L. Zdeborová
       "Spectral Clustering of Graphs with the Bethe Hessian",
       Advances in Neural Information Processing Systems, 2014.
    .. [2] C. M. Le, E. Levina
       "Estimating the number of communities in networks by spectral methods"
       arXiv:1507.00827, 2015.
    """
    import scipy as sp

    if nodelist is None:
        nodelist = list(G)
    if r is None:
        r = sum(d**2 for v, d in nx.degree(G)) / sum(d for v, d in nx.degree(G)) - 1
    A = nx.to_scipy_sparse_array(G, nodelist=nodelist, format="csr")
    n, m = A.shape
    # TODO: Rm csr_array wrapper when spdiags array creation becomes available
    D = sp.sparse.csr_array(sp.sparse.spdiags(A.sum(axis=1), 0, m, n, format="csr"))
    # TODO: Rm csr_array wrapper when eye array creation becomes available
    I = sp.sparse.csr_array(sp.sparse.eye(m, n, format="csr"))
    return (r**2 - 1) * I - r * A + D
