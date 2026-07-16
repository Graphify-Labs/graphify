"""Modularity matrix of graphs."""

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = ["modularity_matrix", "directed_modularity_matrix"]


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable(edge_attrs="weight")
def modularity_matrix(G, nodelist=None, weight=None):
    r"""Returns the modularity matrix of G.

    The modularity matrix is the matrix B = A - <A>, where A is the adjacency
    matrix and <A> is the average adjacency matrix, assuming that the graph
    is described by the configuration model.

    More specifically, the element B_ij of B is defined as

    .. math::
        A_{ij} - {k_i k_j \over 2 m}

    where k_i is the degree of node i, and where m is the number of edges
    in the graph. When weight is set to a name of an attribute edge, Aij, k_i,
    k_j and m are computed using its value.

    Parameters
    ----------
    G : Graph
       A NetworkX graph

    nodelist : list, optional
       The rows and columns are ordered according to the nodes in nodelist.
       If nodelist is None, then the ordering is produced by G.nodes().

    weight : string or None, optional (default=None)
       The edge attribute that holds the numerical value used for
       the edge weight.  If None then all edge weights are 1.

    Returns
    -------
    B : Numpy array
      The modularity matrix of G.

    Examples
    --------
    >>> k = [3, 2, 2, 1, 0]
    >>> G = nx.havel_hakimi_graph(k)
    >>> B = nx.modularity_matrix(G)


    See Also
    --------
    to_numpy_array
    modularity_spectrum
    adjacency_matrix
    directed_modularity_matrix

    References
    ----------
    .. [1] M. E. J. Newman, "Modularity and community structure in networks",
           Proc. Natl. Acad. Sci. USA, vol. 103, pp. 8577-8582, 2006.
    """
    import numpy as np

    if nodelist is None:
        nodelist = list(G)
    A = nx.to_scipy_sparse_array(G, nodelist=nodelist, weight=weight, format="csr")
    k = A.sum(axis=1)
    m = k.sum() * 0.5
    # Expected adjacency matrix
    X = np.outer(k, k) / (2 * m)

    return A - X


@not_implemented_for("undirected")
@not_implemented_for("multigraph")
@nx._dispatchable(edge_attrs="weight")
def directed_modularity_matrix(G, nodelist=None, weight=None):
    """Returns the directed modularity matrix of G.

    The modularity matrix is the matrix B = A - <A>, where A is the adjacency
    matrix and <A> is the expected adjacency matrix, assuming that the graph
    is described by the configuration model.

    More specifically, the element B_ij of B is defined as

    .. math::
        B_{ij} = A_{ij} - k_i^{out} k_j^{in} / m

    where :math:`k_i^{in}` is the in degree of node i, and :math:`k_j^{out}` is the out degree
    of node j, with m the number of edges in the graph. When weight is set
    to a name of an attribute edge, Aij, k_i, k_j and m are computed using
    its value.

    Parameters
    ----------
    G : DiGraph
       A NetworkX DiGraph

    nodelist : list, optional
       The rows and columns are ordered according to the nodes in nodelist.
       If nodelist is None, then the ordering is produced by G.nodes().

    weight : string or None, optional (default=None)
       The edge attribute that holds the numerical value used for
       the edge weight.  If None then all edge weights are 1.

    Returns
    -------
    B : Numpy array
      The modularity matrix of G.

    Examples
    --------
    >>> G = nx.DiGraph()
    >>> G.add_edges_from(
    ...     (
    ...         (1, 2),
    ...         (1, 3),
    ...         (3, 1),
    ...         (3, 2),
    ...         (3, 5),
    ...         (4, 5),
    ...         (4, 6),
    ...         (5, 4),
    ...         (5, 6),
    ...         (6, 4),
    ...     )
    ... )
    >>> B = nx.directed_modularity_matrix(G)


    Notes
    -----
    NetworkX defines the element A_ij of the adjacency matrix as 1 if there
    is a link going from node i to node j. Leicht and Newman use the opposite
    definition. This explains the different expression for B_ij.

    See Also
    --------
    to_numpy_array
    modularity_spectrum
    adjacency_matrix
    modularity_matrix

    References
    ----------
    .. [1] E. A. Leicht, M. E. J. Newman,
        "Community structure in directed networks",
        Phys. Rev Lett., vol. 100, no. 11, p. 118703, 2008.
    """
    import numpy as np

    if nodelist is None:
        nodelist = list(G)
    A = nx.to_scipy_sparse_array(G, nodelist=nodelist, weight=weight, format="csr")
    k_in = A.sum(axis=0)
    k_out = A.sum(axis=1)
    m = k_in.sum()
    # Expected adjacency matrix
    X = np.outer(k_out, k_in) / m

    return A - X
