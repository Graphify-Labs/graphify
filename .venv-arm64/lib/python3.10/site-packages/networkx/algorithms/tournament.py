"""Functions concerning tournament graphs.

A `tournament graph`_ is a complete oriented graph. In other words, it
is a directed graph in which there is exactly one directed edge joining
each pair of distinct nodes. For each function in this module that
accepts a graph as input, you must provide a tournament graph. The
responsibility is on the caller to ensure that the graph is a tournament
graph:

    >>> G = nx.DiGraph([(0, 1), (1, 2), (2, 0)])
    >>> nx.is_tournament(G)
    True

To access the functions in this module, you must access them through the
:mod:`networkx.tournament` module::

    >>> nx.tournament.is_reachable(G, 0, 1)
    True

.. _tournament graph: https://en.wikipedia.org/wiki/Tournament_%28graph_theory%29

"""

from itertools import combinations

import networkx as nx
from networkx.algorithms.simple_paths import is_simple_path as is_path
from networkx.utils import arbitrary_element, not_implemented_for, py_random_state

__all__ = [
    "hamiltonian_path",
    "is_reachable",
    "is_strongly_connected",
    "is_tournament",
    "random_tournament",
    "score_sequence",
]


def index_satisfying(iterable, condition):
    """Returns the index of the first element in `iterable` that
    satisfies the given condition.

    If no such element is found (that is, when the iterable is
    exhausted), this returns the length of the iterable (that is, one
    greater than the last index of the iterable).

    `iterable` must not be empty. If `iterable` is empty, this
    function raises :exc:`ValueError`.

    """
    # Pre-condition: iterable must not be empty.
    for i, x in enumerate(iterable):
        if condition(x):
            return i
    # If we reach the end of the iterable without finding an element
    # that satisfies the condition, return the length of the iterable,
    # which is one greater than the index of its last element. If the
    # iterable was empty, `i` will not be defined, so we raise an
    # exception.
    try:
        return i + 1
    except NameError as err:
        raise ValueError("iterable must be non-empty") from err


@not_implemented_for("undirected")
@not_implemented_for("multigraph")
@nx._dispatchable
def is_tournament(G):
    """Returns True if and only if `G` is a tournament.

    A tournament is a directed graph, with neither self-loops nor
    multi-edges, in which there is exactly one directed edge joining
    each pair of distinct nodes.

    Parameters
    ----------
    G : NetworkX graph
        A directed graph representing a tournament.

    Returns
    -------
    bool
        Whether the given graph is a tournament graph.

    Examples
    --------
    >>> G = nx.DiGraph([(0, 1), (1, 2), (2, 0)])
    >>> nx.is_tournament(G)
    True

    Notes
    -----
    Some definitions require a self-loop on each node, but that is not
    the convention used here.

    """
    # In a tournament, there is exactly one directed edge joining each pair.
    return (
        all((v in G[u]) ^ (u in G[v]) for u, v in combinations(G, 2))
        and nx.number_of_selfloops(G) == 0
    )


@not_implemented_for("undirected")
@not_implemented_for("multigraph")
@nx._dispatchable
def hamiltonian_path(G):
    """Returns a Hamiltonian path in the given tournament graph.

    Each tournament has a Hamiltonian path. If furthermore, the
    tournament is strongly connected, then the returned Hamiltonian path
    is a Hamiltonian cycle (by joining the endpoints of the path).

    Parameters
    ----------
    G : NetworkX graph
        A directed graph representing a tournament.

    Returns
    -------
    path : list
        A list of nodes which form a Hamiltonian path in `G`.

    Examples
    --------
    >>> G = nx.DiGraph([(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)])
    >>> nx.is_tournament(G)
    True
    >>> nx.tournament.hamiltonian_path(G)
    [0, 1, 2, 3]

    Notes
    -----
    This is a recursive implementation with an asymptotic running time
    of $O(n^2)$, ignoring multiplicative polylogarithmic factors, where
    $n$ is the number of nodes in the graph.

    """
    if len(G) == 0:
        return []
    if len(G) == 1:
        return [arbitrary_element(G)]
    v = arbitrary_element(G)
    hampath = hamiltonian_path(G.subgraph(set(G) - {v}))
    # Get the index of the first node in the path that does *not* have
    # an edge to `v`, then insert `v` before that node.
    index = index_satisfying(hampath, lambda u: v not in G[u])
    hampath.insert(index, v)
    return hampath


@py_random_state(1)
@nx._dispatchable(graphs=None, returns_graph=True)
def random_tournament(n, seed=None):
    r"""Returns a random tournament graph on `n` nodes.

    Parameters
    ----------
    n : int
        The number of nodes in the returned graph.
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    G : DiGraph
        A tournament on `n` nodes, with exactly one directed edge joining
        each pair of distinct nodes.

    Notes
    -----
    This algorithm adds, for each pair of distinct nodes, an edge with
    uniformly random orientation. In other words, `\binom{n}{2}` flips
    of an unbiased coin decide the orientations of the edges in the
    graph.

    """
    # Flip an unbiased coin for each pair of distinct nodes.
    coins = (seed.random() for i in range((n * (n - 1)) // 2))
    pairs = combinations(range(n), 2)
    edges = ((u, v) if r < 0.5 else (v, u) for (u, v), r in zip(pairs, coins))
    return nx.DiGraph(edges)


@not_implemented_for("undirected")
@not_implemented_for("multigraph")
@nx._dispatchable
def score_sequence(G):
    """Returns the score sequence for the given tournament graph.

    The score sequence is the sorted list of the out-degrees of the
    nodes of the graph.

    Parameters
    ----------
    G : NetworkX graph
        A directed graph representing a tournament.

    Returns
    -------
    list
        A sorted list of the out-degrees of the nodes of `G`.

    Examples
    --------
    >>> G = nx.DiGraph([(1, 0), (1, 3), (0, 2), (0, 3), (2, 1), (3, 2)])
    >>> nx.is_tournament(G)
    True
    >>> nx.tournament.score_sequence(G)
    [1, 1, 2, 2]

    """
    return sorted(d for v, d in G.out_degree())


@not_implemented_for("undirected")
@not_implemented_for("multigraph")
@nx._dispatchable(preserve_edge_attrs={"G": {"weight": 1}})
def tournament_matrix(G):
    r"""Returns the tournament matrix for the given tournament graph.

    This function requires SciPy.

    The *tournament matrix* of a tournament graph with edge set *E* is
    the matrix *T* defined by

    .. math::

       T_{i j} =
       \begin{cases}
       +1 & \text{if } (i, j) \in E \\
       -1 & \text{if } (j, i) \in E \\
       0 & \text{if } i == j.
       \end{cases}

    An equivalent definition is `T = A - A^T`, where *A* is the
    adjacency matrix of the graph `G`.

    Parameters
    ----------
    G : NetworkX graph
        A directed graph representing a tournament.

    Returns
    -------
    SciPy sparse array
        The tournament matrix of the tournament graph `G`.

    Raises
    ------
    ImportError
        If SciPy is not available.

    """
    A = nx.adjacency_matrix(G)
    return A - A.T


@not_implemented_for("undirected")
@not_implemented_for("multigraph")
@nx._dispatchable
def is_reachable(G, s, t):
    """Decides whether there is a path from `s` to `t` in the
    tournament.

    This function is more theoretically efficient than the reachability
    checks than the shortest path algorithms in
    :mod:`networkx.algorithms.shortest_paths`.

    The given graph **must** be a tournament, otherwise this function's
    behavior is undefined.

    Parameters
    ----------
    G : NetworkX graph
        A directed graph representing a tournament.

    s : node
        A node in the graph.

    t : node
        A node in the graph.

    Returns
    -------
    bool
        Whether there is a path from `s` to `t` in `G`.

    Examples
    --------
    >>> G = nx.DiGraph([(1, 0), (1, 3), (1, 2), (2, 3), (2, 0), (3, 0)])
    >>> nx.is_tournament(G)
    True
    >>> nx.tournament.is_reachable(G, 1, 3)
    True
    >>> nx.tournament.is_reachable(G, 3, 2)
    False

    Notes
    -----
    Although this function is more theoretically efficient than the
    generic shortest path functions, a speedup requires the use of
    parallelism. Though it may in the future, the current implementation
    does not use parallelism, thus you may not see much of a speedup.

    This algorithm comes from [1].

    References
    ----------
    .. [1] Tantau, Till.
           "A note on the complexity of the reachability problem for
           tournaments."
           *Electronic Colloquium on Computational Complexity*. 2001.
           <http://eccc.hpi-web.de/report/2001/092/>
    """

    def two_neighborhood(G, v):
        """Returns the set of nodes at distance at most two from `v`.

        `G` must be a graph and `v` a node in that graph.

        The returned set includes the nodes at distance zero (that is,
        the node `v` itself), the nodes at distance one (that is, the
        out-neighbors of `v`), and the nodes at distance two.

        """
        return {
            x for x in G if x == v or x in G[v] or any(is_path(G, [v, z, x]) for z in G)
        }

    def is_closed(G, nodes):
        """Decides whether the given set of nodes is closed.

        A set *S* of nodes is *closed* if for each node *u* in the graph
        not in *S* and for each node *v* in *S*, there is an edge from
        *u* to *v*.

        """
        return all(v in G[u] for u in set(G) - nodes for v in nodes)

    neighborhoods = [two_neighborhood(G, v) for v in G]
    return all(not (is_closed(G, S) and s in S and t not in S) for S in neighborhoods)


@not_implemented_for("undirected")
@not_implemented_for("multigraph")
@nx._dispatchable(name="tournament_is_strongly_connected")
def is_strongly_connected(G):
    """Decides whether the given tournament is strongly connected.

    This function is more theoretically efficient than the
    :func:`~networkx.algorithms.components.is_strongly_connected`
    function.

    The given graph **must** be a tournament, otherwise this function's
    behavior is undefined.

    Parameters
    ----------
    G : NetworkX graph
        A directed graph representing a tournament.

    Returns
    -------
    bool
        Whether the tournament is strongly connected.

    Examples
    --------
    >>> G = nx.DiGraph([(0, 1), (0, 2), (1, 2), (1, 3), (2, 3), (3, 0)])
    >>> nx.is_tournament(G)
    True
    >>> nx.tournament.is_strongly_connected(G)
    True
    >>> G.remove_edge(3, 0)
    >>> G.add_edge(0, 3)
    >>> nx.is_tournament(G)
    True
    >>> nx.tournament.is_strongly_connected(G)
    False

    Notes
    -----
    Although this function is more theoretically efficient than the
    generic strong connectivity function, a speedup requires the use of
    parallelism. Though it may in the future, the current implementation
    does not use parallelism, thus you may not see much of a speedup.

    This algorithm comes from [1].

    References
    ----------
    .. [1] Tantau, Till.
           "A note on the complexity of the reachability problem for
           tournaments."
           *Electronic Colloquium on Computational Complexity*. 2001.
           <http://eccc.hpi-web.de/report/2001/092/>

    """
    return all(is_reachable(G, u, v) for u in G for v in G)
