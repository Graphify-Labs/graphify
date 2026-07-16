"""Katz centrality."""

import math

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = ["katz_centrality", "katz_centrality_numpy"]


@not_implemented_for("multigraph")
@nx._dispatchable(edge_attrs="weight")
def katz_centrality(
    G,
    alpha=0.1,
    beta=1.0,
    max_iter=1000,
    tol=1.0e-6,
    nstart=None,
    normalized=True,
    weight=None,
):
    r"""Compute the Katz centrality for the nodes of the graph G.

    Katz centrality computes the centrality for a node based on the centrality
    of its neighbors. It is a generalization of the eigenvector centrality. The
    Katz centrality for node $i$ is

    .. math::

        x_i = \alpha \sum_{j} A_{ij} x_j + \beta,

    where $A$ is the adjacency matrix of graph G with eigenvalues $\lambda$.

    The parameter $\beta$ controls the initial centrality and

    .. math::

        \alpha < \frac{1}{\lambda_{\max}}.

    Katz centrality computes the relative influence of a node within a
    network by measuring the number of the immediate neighbors (first
    degree nodes) and also all other nodes in the network that connect
    to the node under consideration through these immediate neighbors.

    Extra weight can be provided to immediate neighbors through the
    parameter $\beta$.  Connections made with distant neighbors
    are, however, penalized by an attenuation factor $\alpha$ which
    should be strictly less than the inverse largest eigenvalue of the
    adjacency matrix in order for the Katz centrality to be computed
    correctly. More information is provided in [1]_.

    Parameters
    ----------
    G : graph
      A NetworkX graph.

    alpha : float, optional (default=0.1)
      Attenuation factor

    beta : scalar or dictionary, optional (default=1.0)
      Weight attributed to the immediate neighborhood. If not a scalar, the
      dictionary must have a value for every node.

    max_iter : integer, optional (default=1000)
      Maximum number of iterations in power method.

    tol : float, optional (default=1.0e-6)
      Error tolerance used to check convergence in power method iteration.

    nstart : dictionary, optional
      Starting value of Katz iteration for each node.

    normalized : bool, optional (default=True)
      If True normalize the resulting values.

    weight : None or string, optional (default=None)
      If None, all edge weights are considered equal.
      Otherwise holds the name of the edge attribute used as weight.
      In this measure the weight is interpreted as the connection strength.

    Returns
    -------
    nodes : dictionary
       Dictionary of nodes with Katz centrality as the value.

    Raises
    ------
    NetworkXError
       If the parameter `beta` is not a scalar but lacks a value for at least
       one node

    PowerIterationFailedConvergence
        If the algorithm fails to converge to the specified tolerance
        within the specified number of iterations of the power iteration
        method.

    Examples
    --------
    >>> import math
    >>> G = nx.path_graph(4)
    >>> phi = (1 + math.sqrt(5)) / 2.0  # largest eigenvalue of adj matrix
    >>> centrality = nx.katz_centrality(G, 1 / phi - 0.01)
    >>> for n, c in sorted(centrality.items()):
    ...     print(f"{n} {c:.2f}")
    0 0.37
    1 0.60
    2 0.60
    3 0.37

    See Also
    --------
    katz_centrality_numpy
    eigenvector_centrality
    eigenvector_centrality_numpy
    :func:`~networkx.algorithms.link_analysis.pagerank_alg.pagerank`
    :func:`~networkx.algorithms.link_analysis.hits_alg.hits`

    Notes
    -----
    Katz centrality was introduced by [2]_.

    This algorithm it uses the power method to find the eigenvector
    corresponding to the largest eigenvalue of the adjacency matrix of ``G``.
    The parameter ``alpha`` should be strictly less than the inverse of largest
    eigenvalue of the adjacency matrix for the algorithm to converge.
    You can use ``max(nx.adjacency_spectrum(G))`` to get $\lambda_{\max}$ the largest
    eigenvalue of the adjacency matrix.
    The iteration will stop after ``max_iter`` iterations or an error tolerance of
    ``number_of_nodes(G) * tol`` has been reached.

    For strongly connected graphs, as $\alpha \to 1/\lambda_{\max}$, and $\beta > 0$,
    Katz centrality approaches the results for eigenvector centrality.

    For directed graphs this finds "left" eigenvectors which corresponds
    to the in-edges in the graph. For out-edges Katz centrality,
    first reverse the graph with ``G.reverse()``.

    References
    ----------
    .. [1] Mark E. J. Newman:
       Networks: An Introduction.
       Oxford University Press, USA, 2010, p. 720.
    .. [2] Leo Katz:
       A New Status Index Derived from Sociometric Index.
       Psychometrika 18(1):39–43, 1953
       https://link.springer.com/content/pdf/10.1007/BF02289026.pdf
    """
    if len(G) == 0:
        return {}

    nnodes = G.number_of_nodes()

    if nstart is None:
        # choose starting vector with entries of 0
        x = {n: 0 for n in G}
    else:
        x = nstart

    try:
        b = dict.fromkeys(G, float(beta))
    except (TypeError, ValueError, AttributeError) as err:
        b = beta
        if set(beta) != set(G):
            raise nx.NetworkXError(
                "beta dictionary must have a value for every node"
            ) from err

    # make up to max_iter iterations
    for _ in range(max_iter):
        xlast = x
        x = dict.fromkeys(xlast, 0)
        # do the multiplication y^T = Alpha * x^T A + Beta
        for n in x:
            for nbr in G[n]:
                x[nbr] += xlast[n] * G[n][nbr].get(weight, 1)
        for n in x:
            x[n] = alpha * x[n] + b[n]

        # check convergence
        error = sum(abs(x[n] - xlast[n]) for n in x)
        if error < nnodes * tol:
            if normalized:
                # normalize vector
                try:
                    s = 1.0 / math.hypot(*x.values())
                except ZeroDivisionError:
                    s = 1.0
            else:
                s = 1
            for n in x:
                x[n] *= s
            return x
    raise nx.PowerIterationFailedConvergence(max_iter)


@not_implemented_for("multigraph")
@nx._dispatchable(edge_attrs="weight")
def katz_centrality_numpy(G, alpha=0.1, beta=1.0, normalized=True, weight=None):
    r"""Compute the Katz centrality for the graph G.

    Katz centrality computes the centrality for a node based on the centrality
    of its neighbors. It is a generalization of the eigenvector centrality. The
    Katz centrality for node $i$ is

    .. math::

        x_i = \alpha \sum_{j} A_{ij} x_j + \beta,

    where $A$ is the adjacency matrix of graph G with eigenvalues $\lambda$.

    The parameter $\beta$ controls the initial centrality and

    .. math::

        \alpha < \frac{1}{\lambda_{\max}}.

    Katz centrality computes the relative influence of a node within a
    network by measuring the number of the immediate neighbors (first
    degree nodes) and also all other nodes in the network that connect
    to the node under consideration through these immediate neighbors.

    Extra weight can be provided to immediate neighbors through the
    parameter $\beta$.  Connections made with distant neighbors
    are, however, penalized by an attenuation factor $\alpha$ which
    should be strictly less than the inverse largest eigenvalue of the
    adjacency matrix in order for the Katz centrality to be computed
    correctly. More information is provided in [1]_.

    Parameters
    ----------
    G : graph
      A NetworkX graph

    alpha : float
      Attenuation factor

    beta : scalar or dictionary, optional (default=1.0)
      Weight attributed to the immediate neighborhood. If not a scalar the
      dictionary must have an value for every node.

    normalized : bool
      If True normalize the resulting values.

    weight : None or string, optional
      If None, all edge weights are considered equal.
      Otherwise holds the name of the edge attribute used as weight.
      In this measure the weight is interpreted as the connection strength.

    Returns
    -------
    nodes : dictionary
       Dictionary of nodes with Katz centrality as the value.

    Raises
    ------
    NetworkXError
       If the parameter `beta` is not a scalar but lacks a value for at least
       one node

    Examples
    --------
    >>> import math
    >>> G = nx.path_graph(4)
    >>> phi = (1 + math.sqrt(5)) / 2.0  # largest eigenvalue of adj matrix
    >>> centrality = nx.katz_centrality_numpy(G, 1 / phi)
    >>> for n, c in sorted(centrality.items()):
    ...     print(f"{n} {c:.2f}")
    0 0.37
    1 0.60
    2 0.60
    3 0.37

    See Also
    --------
    katz_centrality
    eigenvector_centrality_numpy
    eigenvector_centrality
    :func:`~networkx.algorithms.link_analysis.pagerank_alg.pagerank`
    :func:`~networkx.algorithms.link_analysis.hits_alg.hits`

    Notes
    -----
    Katz centrality was introduced by [2]_.

    This algorithm uses a direct linear solver to solve the above equation.
    The parameter ``alpha`` should be strictly less than the inverse of largest
    eigenvalue of the adjacency matrix for there to be a solution.
    You can use ``max(nx.adjacency_spectrum(G))`` to get $\lambda_{\max}$ the largest
    eigenvalue of the adjacency matrix.

    For strongly connected graphs, as $\alpha \to 1/\lambda_{\max}$, and $\beta > 0$,
    Katz centrality approaches the results for eigenvector centrality.

    For directed graphs this finds "left" eigenvectors which corresponds
    to the in-edges in the graph. For out-edges Katz centrality,
    first reverse the graph with ``G.reverse()``.

    References
    ----------
    .. [1] Mark E. J. Newman:
       Networks: An Introduction.
       Oxford University Press, USA, 2010, p. 173.
    .. [2] Leo Katz:
       A New Status Index Derived from Sociometric Index.
       Psychometrika 18(1):39–43, 1953
       https://link.springer.com/content/pdf/10.1007/BF02289026.pdf
    """
    import numpy as np

    if len(G) == 0:
        return {}
    try:
        nodelist = beta.keys()
        if set(nodelist) != set(G):
            raise nx.NetworkXError("beta dictionary must have a value for every node")
        b = np.array(list(beta.values()), dtype=float)
    except AttributeError:
        nodelist = list(G)
        try:
            b = np.ones((len(nodelist), 1)) * beta
        except (TypeError, ValueError, AttributeError) as err:
            raise nx.NetworkXError("beta must be a number") from err

    A = nx.adjacency_matrix(G, nodelist=nodelist, weight=weight).todense().T
    n = A.shape[0]
    centrality = np.linalg.solve(np.eye(n, n) - (alpha * A), b).squeeze()

    # Normalize: rely on truediv to cast to float, then tolist to make Python numbers
    norm = np.sign(sum(centrality)) * np.linalg.norm(centrality) if normalized else 1
    return dict(zip(nodelist, (centrality / norm).tolist()))
