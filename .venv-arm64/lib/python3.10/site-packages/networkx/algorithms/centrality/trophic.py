"""Trophic levels"""

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = ["trophic_levels", "trophic_differences", "trophic_incoherence_parameter"]


@not_implemented_for("undirected")
@nx._dispatchable(edge_attrs="weight")
def trophic_levels(G, weight="weight"):
    r"""Compute the trophic levels of nodes.

    The trophic level of a node $i$ is

    .. math::

        s_i = 1 + \frac{1}{k^{in}_i} \sum_{j} a_{ij} s_j

    where $k^{in}_i$ is the in-degree of i

    .. math::

        k^{in}_i = \sum_{j} a_{ij}

    and nodes with $k^{in}_i = 0$ have $s_i = 1$ by convention.

    These are calculated using the method outlined in Levine [1]_.

    Parameters
    ----------
    G : DiGraph
        A directed networkx graph

    Returns
    -------
    nodes : dict
        Dictionary of nodes with trophic level as the value.

    References
    ----------
    .. [1] Stephen Levine (1980) J. theor. Biol. 83, 195-207
    """
    import numpy as np

    # find adjacency matrix
    a = nx.adjacency_matrix(G, weight=weight).T.toarray()

    # drop rows/columns where in-degree is zero
    rowsum = np.sum(a, axis=1)
    p = a[rowsum != 0][:, rowsum != 0]
    # normalise so sum of in-degree weights is 1 along each row
    p = p / rowsum[rowsum != 0][:, np.newaxis]

    # calculate trophic levels
    nn = p.shape[0]
    i = np.eye(nn)
    try:
        n = np.linalg.inv(i - p)
    except np.linalg.LinAlgError as err:
        # LinAlgError is raised when there is a non-basal node
        msg = (
            "Trophic levels are only defined for graphs where every "
            + "node has a path from a basal node (basal nodes are nodes "
            + "with no incoming edges)."
        )
        raise nx.NetworkXError(msg) from err
    y = n.sum(axis=1) + 1

    levels = {}

    # all nodes with in-degree zero have trophic level == 1
    zero_node_ids = (node_id for node_id, degree in G.in_degree if degree == 0)
    for node_id in zero_node_ids:
        levels[node_id] = 1

    # all other nodes have levels as calculated
    nonzero_node_ids = (node_id for node_id, degree in G.in_degree if degree != 0)
    for i, node_id in enumerate(nonzero_node_ids):
        levels[node_id] = y.item(i)

    return levels


@not_implemented_for("undirected")
@nx._dispatchable(edge_attrs="weight")
def trophic_differences(G, weight="weight"):
    r"""Compute the trophic differences of the edges of a directed graph.

    The trophic difference $x_ij$ for each edge is defined in Johnson et al.
    [1]_ as:

    .. math::
        x_ij = s_j - s_i

    Where $s_i$ is the trophic level of node $i$.

    Parameters
    ----------
    G : DiGraph
        A directed networkx graph

    Returns
    -------
    diffs : dict
        Dictionary of edges with trophic differences as the value.

    References
    ----------
    .. [1] Samuel Johnson, Virginia Dominguez-Garcia, Luca Donetti, Miguel A.
        Munoz (2014) PNAS "Trophic coherence determines food-web stability"
    """
    levels = trophic_levels(G, weight=weight)
    diffs = {}
    for u, v in G.edges:
        diffs[(u, v)] = levels[v] - levels[u]
    return diffs


@not_implemented_for("undirected")
@nx._dispatchable(edge_attrs="weight")
def trophic_incoherence_parameter(G, weight="weight", cannibalism=False):
    r"""Compute the trophic incoherence parameter of a graph.

    Trophic coherence is defined as the homogeneity of the distribution of
    trophic distances: the more similar, the more coherent. This is measured by
    the standard deviation of the trophic differences and referred to as the
    trophic incoherence parameter $q$ by [1].

    Parameters
    ----------
    G : DiGraph
        A directed networkx graph

    cannibalism: Boolean
        If set to False, self edges are not considered in the calculation

    Returns
    -------
    trophic_incoherence_parameter : float
        The trophic coherence of a graph

    References
    ----------
    .. [1] Samuel Johnson, Virginia Dominguez-Garcia, Luca Donetti, Miguel A.
        Munoz (2014) PNAS "Trophic coherence determines food-web stability"
    """
    import numpy as np

    if cannibalism:
        diffs = trophic_differences(G, weight=weight)
    else:
        # If no cannibalism, remove self-edges
        self_loops = list(nx.selfloop_edges(G))
        if self_loops:
            # Make a copy so we do not change G's edges in memory
            G_2 = G.copy()
            G_2.remove_edges_from(self_loops)
        else:
            # Avoid copy otherwise
            G_2 = G
        diffs = trophic_differences(G_2, weight=weight)
    return float(np.std(list(diffs.values())))
