"""Functions for generating graphs based on the "duplication" method.

These graph generators start with a small initial graph then duplicate
nodes and (partially) duplicate their edges. These functions are
generally inspired by biological networks.

"""

import networkx as nx
from networkx.exception import NetworkXError
from networkx.utils import py_random_state
from networkx.utils.misc import check_create_using

__all__ = ["partial_duplication_graph", "duplication_divergence_graph"]


@py_random_state(4)
@nx._dispatchable(graphs=None, returns_graph=True)
def partial_duplication_graph(N, n, p, q, seed=None, *, create_using=None):
    """Returns a random graph using the partial duplication model.

    Parameters
    ----------
    N : int
        The total number of nodes in the final graph.

    n : int
        The number of nodes in the initial clique.

    p : float
        The probability of joining each neighbor of a node to the
        duplicate node. Must be a number in the between zero and one,
        inclusive.

    q : float
        The probability of joining the source node to the duplicate
        node. Must be a number in the between zero and one, inclusive.

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    create_using : Graph constructor, optional (default=nx.Graph)
        Graph type to create. If graph instance, then cleared before populated.
        Multigraph and directed types are not supported and raise a ``NetworkXError``.

    Notes
    -----
    A graph of nodes is grown by creating a fully connected graph
    of size `n`. The following procedure is then repeated until
    a total of `N` nodes have been reached.

    1. A random node, *u*, is picked and a new node, *v*, is created.
    2. For each neighbor of *u* an edge from the neighbor to *v* is created
       with probability `p`.
    3. An edge from *u* to *v* is created with probability `q`.

    This algorithm appears in [1].

    This implementation allows the possibility of generating
    disconnected graphs.

    References
    ----------
    .. [1] Knudsen Michael, and Carsten Wiuf. "A Markov chain approach to
           randomly grown graphs." Journal of Applied Mathematics 2008.
           <https://doi.org/10.1155/2008/190836>

    """
    create_using = check_create_using(create_using, directed=False, multigraph=False)
    if p < 0 or p > 1 or q < 0 or q > 1:
        msg = "partial duplication graph must have 0 <= p, q <= 1."
        raise NetworkXError(msg)
    if n > N:
        raise NetworkXError("partial duplication graph must have n <= N.")

    G = nx.complete_graph(n, create_using)
    for new_node in range(n, N):
        # Pick a random vertex, u, already in the graph.
        src_node = seed.randint(0, new_node - 1)

        # Add a new vertex, v, to the graph.
        G.add_node(new_node)

        # For each neighbor of u...
        for nbr_node in list(nx.all_neighbors(G, src_node)):
            # Add the neighbor to v with probability p.
            if seed.random() < p:
                G.add_edge(new_node, nbr_node)

        # Join v and u with probability q.
        if seed.random() < q:
            G.add_edge(new_node, src_node)
    return G


@py_random_state(2)
@nx._dispatchable(graphs=None, returns_graph=True)
def duplication_divergence_graph(n, p, seed=None, *, create_using=None):
    """Returns an undirected graph using the duplication-divergence model.

    A graph of `n` nodes is created by duplicating the initial nodes
    and retaining edges incident to the original nodes with a retention
    probability `p`.

    Parameters
    ----------
    n : int
        The desired number of nodes in the graph.
    p : float
        The probability for retaining the edge of the replicated node.
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.
    create_using : Graph constructor, optional (default=nx.Graph)
        Graph type to create. If graph instance, then cleared before populated.
        Multigraph and directed types are not supported and raise a ``NetworkXError``.

    Returns
    -------
    G : Graph

    Raises
    ------
    NetworkXError
        If `p` is not a valid probability.
        If `n` is less than 2.

    Notes
    -----
    This algorithm appears in [1].

    This implementation disallows the possibility of generating
    disconnected graphs.

    References
    ----------
    .. [1] I. Ispolatov, P. L. Krapivsky, A. Yuryev,
       "Duplication-divergence model of protein interaction network",
       Phys. Rev. E, 71, 061911, 2005.

    """
    if p > 1 or p < 0:
        msg = f"NetworkXError p={p} is not in [0,1]."
        raise nx.NetworkXError(msg)
    if n < 2:
        msg = "n must be greater than or equal to 2"
        raise nx.NetworkXError(msg)

    create_using = check_create_using(create_using, directed=False, multigraph=False)
    G = nx.empty_graph(create_using=create_using)

    # Initialize the graph with two connected nodes.
    G.add_edge(0, 1)
    i = 2
    while i < n:
        # Choose a random node from current graph to duplicate.
        random_node = seed.choice(list(G))
        # Make the replica.
        G.add_node(i)
        # flag indicates whether at least one edge is connected on the replica.
        flag = False
        for nbr in G.neighbors(random_node):
            if seed.random() < p:
                # Link retention step.
                G.add_edge(i, nbr)
                flag = True
        if not flag:
            # Delete replica if no edges retained.
            G.remove_node(i)
        else:
            # Successful duplication.
            i += 1
    return G
