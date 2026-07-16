"""Functions for computing rich-club coefficients."""

from itertools import accumulate

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = ["rich_club_coefficient"]


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def rich_club_coefficient(G, normalized=True, Q=100, seed=None):
    r"""Returns the rich-club coefficient of the graph `G`.

    For each degree *k*, the *rich-club coefficient* is the ratio of the
    number of actual to the number of potential edges for nodes with
    degree greater than *k*:

    .. math::

        \phi(k) = \frac{2 E_k}{N_k (N_k - 1)}

    where `N_k` is the number of nodes with degree larger than *k*, and
    `E_k` is the number of edges among those nodes.

    Parameters
    ----------
    G : NetworkX graph
        Undirected graph with neither parallel edges nor self-loops.
    normalized : bool (optional)
        Normalize using randomized network as in [1]_
    Q : float (optional, default=100)
        If `normalized` is True, perform `Q * m` double-edge
        swaps, where `m` is the number of edges in `G`, to use as a
        null-model for normalization.
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    rc : dictionary
       A dictionary, keyed by degree, with rich-club coefficient values.

    Raises
    ------
    NetworkXError
        If `G` has fewer than four nodes and ``normalized=True``.
        A randomly sampled graph for normalization cannot be generated in this case.

    Examples
    --------
    >>> G = nx.Graph([(0, 1), (0, 2), (1, 2), (1, 3), (1, 4), (4, 5)])
    >>> rc = nx.rich_club_coefficient(G, normalized=False, seed=42)
    >>> rc[0]
    0.4

    Notes
    -----
    The rich club definition and algorithm are found in [1]_.  This
    algorithm ignores any edge weights and is not defined for directed
    graphs or graphs with parallel edges or self loops.

    Normalization is done by computing the rich club coefficient for a randomly
    sampled graph with the same degree distribution as `G` by
    repeatedly swapping the endpoints of existing edges. For graphs with fewer than 4
    nodes, it is not possible to generate a random graph with a prescribed
    degree distribution, as the degree distribution fully determines the graph
    (hence making the coefficients trivially normalized to 1).
    This function raises an exception in this case.

    Estimates for appropriate values of `Q` are found in [2]_.

    References
    ----------
    .. [1] Julian J. McAuley, Luciano da Fontoura Costa,
       and Tibério S. Caetano,
       "The rich-club phenomenon across complex network hierarchies",
       Applied Physics Letters Vol 91 Issue 8, August 2007.
       https://arxiv.org/abs/physics/0701290
    .. [2] R. Milo, N. Kashtan, S. Itzkovitz, M. E. J. Newman, U. Alon,
       "Uniform generation of random graphs with arbitrary degree
       sequences", 2006. https://arxiv.org/abs/cond-mat/0312028
    """
    if nx.number_of_selfloops(G) > 0:
        raise Exception(
            "rich_club_coefficient is not implemented for graphs with self loops."
        )
    rc = _compute_rc(G)
    if normalized:
        # make R a copy of G, randomize with Q*|E| double edge swaps
        # and use rich_club coefficient of R to normalize
        R = G.copy()
        E = R.number_of_edges()
        nx.double_edge_swap(R, Q * E, max_tries=Q * E * 10, seed=seed)
        rcran = _compute_rc(R)
        rc = {k: v / rcran[k] for k, v in rc.items()}
    return rc


def _compute_rc(G):
    """Returns the rich-club coefficient for each degree in the graph
    `G`.

    `G` is an undirected graph without multiedges.

    Returns a dictionary mapping degree to rich-club coefficient for
    that degree.

    """
    deghist = nx.degree_histogram(G)
    total = sum(deghist)
    # Compute the number of nodes with degree greater than `k`, for each
    # degree `k` (omitting the last entry, which is zero).
    nks = (total - cs for cs in accumulate(deghist) if total - cs > 1)
    # Create a sorted list of pairs of edge endpoint degrees.
    #
    # The list is sorted in reverse order so that we can pop from the
    # right side of the list later, instead of popping from the left
    # side of the list, which would have a linear time cost.
    edge_degrees = sorted((sorted(map(G.degree, e)) for e in G.edges()), reverse=True)
    ek = G.number_of_edges()
    if ek == 0:
        return {}

    k1, k2 = edge_degrees.pop()
    rc = {}
    for d, nk in enumerate(nks):
        while k1 <= d:
            if len(edge_degrees) == 0:
                ek = 0
                break
            k1, k2 = edge_degrees.pop()
            ek -= 1
        rc[d] = 2 * ek / (nk * (nk - 1))
    return rc
