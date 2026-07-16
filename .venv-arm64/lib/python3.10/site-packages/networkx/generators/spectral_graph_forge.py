"""Generates graphs with a given eigenvector structure"""

import networkx as nx
from networkx.utils import np_random_state

__all__ = ["spectral_graph_forge"]


@np_random_state(3)
@nx._dispatchable(returns_graph=True)
def spectral_graph_forge(G, alpha, transformation="identity", seed=None):
    """Returns a random simple graph with spectrum resembling that of `G`

    This algorithm, called Spectral Graph Forge (SGF), computes the
    eigenvectors of a given graph adjacency matrix, filters them and
    builds a random graph with a similar eigenstructure.
    SGF has been proved to be particularly useful for synthesizing
    realistic social networks and it can also be used to anonymize
    graph sensitive data.

    Parameters
    ----------
    G : Graph
    alpha :  float
        Ratio representing the percentage of eigenvectors of G to consider,
        values in [0,1].
    transformation : string, optional
        Represents the intended matrix linear transformation, possible values
        are 'identity' and 'modularity'
    seed : integer, random_state, or None (default)
        Indicator of numpy random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    H : Graph
        A graph with a similar eigenvector structure of the input one.

    Raises
    ------
    NetworkXError
        If transformation has a value different from 'identity' or 'modularity'

    Notes
    -----
    Spectral Graph Forge (SGF) generates a random simple graph resembling the
    global properties of the given one.
    It leverages the low-rank approximation of the associated adjacency matrix
    driven by the *alpha* precision parameter.
    SGF preserves the number of nodes of the input graph and their ordering.
    This way, nodes of output graphs resemble the properties of the input one
    and attributes can be directly mapped.

    It considers the graph adjacency matrices which can optionally be
    transformed to other symmetric real matrices (currently transformation
    options include *identity* and *modularity*).
    The *modularity* transformation, in the sense of Newman's modularity matrix
    allows the focusing on community structure related properties of the graph.

    SGF applies a low-rank approximation whose fixed rank is computed from the
    ratio *alpha* of the input graph adjacency matrix dimension.
    This step performs a filtering on the input eigenvectors similar to the low
    pass filtering common in telecommunications.

    The filtered values (after truncation) are used as input to a Bernoulli
    sampling for constructing a random adjacency matrix.

    References
    ----------
    ..  [1] L. Baldesi, C. T. Butts, A. Markopoulou, "Spectral Graph Forge:
        Graph Generation Targeting Modularity", IEEE Infocom, '18.
        https://arxiv.org/abs/1801.01715
    ..  [2] M. Newman, "Networks: an introduction", Oxford university press,
        2010

    Examples
    --------
    >>> G = nx.karate_club_graph()
    >>> H = nx.spectral_graph_forge(G, 0.3)
    >>>
    """
    import numpy as np
    import scipy as sp

    available_transformations = ["identity", "modularity"]
    alpha = np.clip(alpha, 0, 1)
    A = nx.to_numpy_array(G)
    n = A.shape[1]
    level = round(n * alpha)

    if transformation not in available_transformations:
        msg = f"{transformation!r} is not a valid transformation. "
        msg += f"Transformations: {available_transformations}"
        raise nx.NetworkXError(msg)

    K = np.ones((1, n)) @ A

    B = A
    if transformation == "modularity":
        B -= K.T @ K / K.sum()

    # Compute low-rank approximation of B
    evals, evecs = np.linalg.eigh(B)
    k = np.argsort(np.abs(evals))[::-1]  # indices of evals in descending order
    evecs[:, k[np.arange(level, n)]] = 0  # set smallest eigenvectors to 0
    B = evecs @ np.diag(evals) @ evecs.T

    if transformation == "modularity":
        B += K.T @ K / K.sum()

    B = np.clip(B, 0, 1)
    np.fill_diagonal(B, 0)

    for i in range(n - 1):
        B[i, i + 1 :] = sp.stats.bernoulli.rvs(B[i, i + 1 :], random_state=seed)
        B[i + 1 :, i] = np.transpose(B[i, i + 1 :])

    H = nx.from_numpy_array(B)

    return H
