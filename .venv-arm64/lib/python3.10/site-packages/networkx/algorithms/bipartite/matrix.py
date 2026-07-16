"""
====================
Biadjacency matrices
====================
"""

import itertools

import networkx as nx
from networkx.convert_matrix import _generate_weighted_edges

__all__ = ["biadjacency_matrix", "from_biadjacency_matrix"]


@nx._dispatchable(edge_attrs="weight")
def biadjacency_matrix(
    G, row_order, column_order=None, dtype=None, weight="weight", format="csr"
):
    r"""Returns the biadjacency matrix of the bipartite graph G.

    Let `G = (U, V, E)` be a bipartite graph with node sets
    `U = u_{1},...,u_{r}` and `V = v_{1},...,v_{s}`. The biadjacency
    matrix [1]_ is the `r` x `s` matrix `B` in which `b_{i,j} = 1`
    if, and only if, `(u_i, v_j) \in E`. If the parameter `weight` is
    not `None` and matches the name of an edge attribute, its value is
    used instead of 1.

    Parameters
    ----------
    G : graph
       A NetworkX graph

    row_order : list of nodes
       The rows of the matrix are ordered according to the list of nodes.

    column_order : list, optional
       The columns of the matrix are ordered according to the list of nodes.
       If column_order is None, then the ordering of columns is arbitrary.

    dtype : NumPy data-type, optional
        A valid NumPy dtype used to initialize the array. If None, then the
        NumPy default is used.

    weight : string or None, optional (default='weight')
       The edge data key used to provide each value in the matrix.
       If None, then each edge has weight 1.

    format : str in {'bsr', 'csr', 'csc', 'coo', 'lil', 'dia', 'dok'}
        The type of the matrix to be returned (default 'csr').  For
        some algorithms different implementations of sparse matrices
        can perform better.  See [2]_ for details.

    Returns
    -------
    M : SciPy sparse array
        Biadjacency matrix representation of the bipartite graph G.

    Notes
    -----
    No attempt is made to check that the input graph is bipartite.

    For directed bipartite graphs only successors are considered as neighbors.
    To obtain an adjacency matrix with ones (or weight values) for both
    predecessors and successors you have to generate two biadjacency matrices
    where the rows of one of them are the columns of the other, and then add
    one to the transpose of the other.

    See Also
    --------
    adjacency_matrix
    from_biadjacency_matrix

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/Adjacency_matrix#Adjacency_matrix_of_a_bipartite_graph
    .. [2] Scipy Dev. References, "Sparse Matrices",
       https://docs.scipy.org/doc/scipy/reference/sparse.html
    """
    import scipy as sp

    nlen = len(row_order)
    if nlen == 0:
        raise nx.NetworkXError("row_order is empty list")
    if len(row_order) != len(set(row_order)):
        msg = "Ambiguous ordering: `row_order` contained duplicates."
        raise nx.NetworkXError(msg)
    if column_order is None:
        column_order = list(set(G) - set(row_order))
    mlen = len(column_order)
    if len(column_order) != len(set(column_order)):
        msg = "Ambiguous ordering: `column_order` contained duplicates."
        raise nx.NetworkXError(msg)

    row_index = dict(zip(row_order, itertools.count()))
    col_index = dict(zip(column_order, itertools.count()))

    if G.number_of_edges() == 0:
        row, col, data = [], [], []
    else:
        row, col, data = zip(
            *(
                (row_index[u], col_index[v], d.get(weight, 1))
                for u, v, d in G.edges(row_order, data=True)
                if u in row_index and v in col_index
            )
        )
    A = sp.sparse.coo_array((data, (row, col)), shape=(nlen, mlen), dtype=dtype)
    try:
        return A.asformat(format)
    except ValueError as err:
        raise nx.NetworkXError(f"Unknown sparse array format: {format}") from err


@nx._dispatchable(graphs=None, returns_graph=True)
def from_biadjacency_matrix(A, create_using=None, edge_attribute="weight"):
    r"""Creates a new bipartite graph from a biadjacency matrix given as a
    SciPy sparse array.

    Parameters
    ----------
    A: scipy sparse array
      A biadjacency matrix representation of a graph

    create_using: NetworkX graph
       Use specified graph for result.  The default is Graph()

    edge_attribute: string
       Name of edge attribute to store matrix numeric value. The data will
       have the same type as the matrix entry (int, float, (real,imag)).

    Notes
    -----
    The nodes are labeled with the attribute `bipartite` set to an integer
    0 or 1 representing membership in part 0 or part 1 of the bipartite graph.

    If `create_using` is an instance of :class:`networkx.MultiGraph` or
    :class:`networkx.MultiDiGraph` and the entries of `A` are of
    type :class:`int`, then this function returns a multigraph (of the same
    type as `create_using`) with parallel edges. In this case, `edge_attribute`
    will be ignored.

    See Also
    --------
    biadjacency_matrix
    from_numpy_array

    References
    ----------
    [1] https://en.wikipedia.org/wiki/Adjacency_matrix#Adjacency_matrix_of_a_bipartite_graph
    """
    G = nx.empty_graph(0, create_using)
    n, m = A.shape
    # Make sure we get even the isolated nodes of the graph.
    G.add_nodes_from(range(n), bipartite=0)
    G.add_nodes_from(range(n, n + m), bipartite=1)
    # Create an iterable over (u, v, w) triples and for each triple, add an
    # edge from u to v with weight w.
    triples = ((u, n + v, d) for (u, v, d) in _generate_weighted_edges(A))
    # If the entries in the adjacency matrix are integers and the graph is a
    # multigraph, then create parallel edges, each with weight 1, for each
    # entry in the adjacency matrix. Otherwise, create one edge for each
    # positive entry in the adjacency matrix and set the weight of that edge to
    # be the entry in the matrix.
    if A.dtype.kind in ("i", "u") and G.is_multigraph():
        chain = itertools.chain.from_iterable
        triples = chain(((u, v, 1) for d in range(w)) for (u, v, w) in triples)
    G.add_weighted_edges_from(triples, weight=edge_attribute)
    return G
