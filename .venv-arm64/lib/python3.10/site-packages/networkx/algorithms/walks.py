"""Function for computing walks in a graph."""

import networkx as nx

__all__ = ["number_of_walks"]


@nx._dispatchable
def number_of_walks(G, walk_length):
    """Returns the number of walks connecting each pair of nodes in `G`

    A *walk* is a sequence of nodes in which each adjacent pair of nodes
    in the sequence is adjacent in the graph. A walk can repeat the same
    edge and go in the opposite direction just as people can walk on a
    set of paths, but standing still is not counted as part of the walk.

    This function only counts the walks with `walk_length` edges. Note that
    the number of nodes in the walk sequence is one more than `walk_length`.
    The number of walks can grow very quickly on a larger graph
    and with a larger walk length.

    Parameters
    ----------
    G : NetworkX graph

    walk_length : int
        A nonnegative integer representing the length of a walk.

    Returns
    -------
    dict
        A dictionary of dictionaries in which outer keys are source
        nodes, inner keys are target nodes, and inner values are the
        number of walks of length `walk_length` connecting those nodes.

    Raises
    ------
    ValueError
        If `walk_length` is negative

    Examples
    --------

    >>> G = nx.Graph([(0, 1), (1, 2)])
    >>> walks = nx.number_of_walks(G, 2)
    >>> walks
    {0: {0: 1, 1: 0, 2: 1}, 1: {0: 0, 1: 2, 2: 0}, 2: {0: 1, 1: 0, 2: 1}}
    >>> total_walks = sum(sum(tgts.values()) for _, tgts in walks.items())

    You can also get the number of walks from a specific source node using the
    returned dictionary. For example, number of walks of length 1 from node 0
    can be found as follows:

    >>> walks = nx.number_of_walks(G, 1)
    >>> walks[0]
    {0: 0, 1: 1, 2: 0}
    >>> sum(walks[0].values())  # walks from 0 of length 1
    1

    Similarly, a target node can also be specified:

    >>> walks[0][1]
    1

    """
    import numpy as np

    if walk_length < 0:
        raise ValueError(f"`walk_length` cannot be negative: {walk_length}")

    A = nx.adjacency_matrix(G, weight=None)
    # TODO: Use matrix_power from scipy.sparse when available
    # power = sp.sparse.linalg.matrix_power(A, walk_length)
    power = np.linalg.matrix_power(A.toarray(), walk_length)
    result = {
        u: {v: power.item(u_idx, v_idx) for v_idx, v in enumerate(G)}
        for u_idx, u in enumerate(G)
    }
    return result
