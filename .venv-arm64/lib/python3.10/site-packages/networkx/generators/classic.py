"""Generators for some classic graphs.

The typical graph builder function is called as follows:

>>> G = nx.complete_graph(100)

returning the complete graph on n nodes labeled 0, .., 99
as a simple graph. Except for `empty_graph`, all the functions
in this module return a Graph class (i.e. a simple, undirected graph).

"""

import itertools
import numbers

import networkx as nx
from networkx.classes import Graph
from networkx.exception import NetworkXError
from networkx.utils import nodes_or_number, pairwise

__all__ = [
    "balanced_tree",
    "barbell_graph",
    "binomial_tree",
    "complete_graph",
    "complete_multipartite_graph",
    "circular_ladder_graph",
    "circulant_graph",
    "cycle_graph",
    "dorogovtsev_goltsev_mendes_graph",
    "empty_graph",
    "full_rary_tree",
    "kneser_graph",
    "ladder_graph",
    "lollipop_graph",
    "null_graph",
    "path_graph",
    "star_graph",
    "tadpole_graph",
    "trivial_graph",
    "turan_graph",
    "wheel_graph",
]


# -------------------------------------------------------------------
#   Some Classic Graphs
# -------------------------------------------------------------------


def _tree_edges(n, r):
    if n == 0:
        return
    # helper function for trees
    # yields edges in rooted tree at 0 with n nodes and branching ratio r
    nodes = iter(range(n))
    parents = [next(nodes)]  # stack of max length r
    while parents:
        source = parents.pop(0)
        for i in range(r):
            try:
                target = next(nodes)
                parents.append(target)
                yield source, target
            except StopIteration:
                break


@nx._dispatchable(graphs=None, returns_graph=True)
def full_rary_tree(r, n, create_using=None):
    """Creates a full r-ary tree of `n` nodes.

    Sometimes called a k-ary, n-ary, or m-ary tree.
    "... all non-leaf nodes have exactly r children and all levels
    are full except for some rightmost position of the bottom level
    (if a leaf at the bottom level is missing, then so are all of the
    leaves to its right." [1]_

    .. plot::

        >>> nx.draw(nx.full_rary_tree(2, 10))

    Parameters
    ----------
    r : int
        branching factor of the tree
    n : int
        Number of nodes in the tree
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        An r-ary tree with n nodes

    References
    ----------
    .. [1] An introduction to data structures and algorithms,
           James Andrew Storer,  Birkhauser Boston 2001, (page 225).
    """
    G = empty_graph(n, create_using)
    G.add_edges_from(_tree_edges(n, r))
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def kneser_graph(n, k):
    """Returns the Kneser Graph with parameters `n` and `k`.

    The Kneser Graph has nodes that are k-tuples (subsets) of the integers
    between 0 and ``n-1``. Nodes are adjacent if their corresponding sets are disjoint.

    Parameters
    ----------
    n: int
        Number of integers from which to make node subsets.
        Subsets are drawn from ``set(range(n))``.
    k: int
        Size of the subsets.

    Returns
    -------
    G : NetworkX Graph

    Examples
    --------
    >>> G = nx.kneser_graph(5, 2)
    >>> G.number_of_nodes()
    10
    >>> G.number_of_edges()
    15
    >>> nx.is_isomorphic(G, nx.petersen_graph())
    True
    """
    if n <= 0:
        raise NetworkXError("n should be greater than zero")
    if k <= 0 or k > n:
        raise NetworkXError("k should be greater than zero and smaller than n")

    G = nx.Graph()
    # Create all k-subsets of [0, 1, ..., n-1]
    subsets = list(itertools.combinations(range(n), k))

    if 2 * k > n:
        G.add_nodes_from(subsets)

    universe = set(range(n))
    comb = itertools.combinations  # only to make it all fit on one line
    G.add_edges_from((s, t) for s in subsets for t in comb(universe - set(s), k))
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def balanced_tree(r, h, create_using=None):
    """Returns the perfectly balanced `r`-ary tree of height `h`.

    .. plot::

        >>> nx.draw(nx.balanced_tree(2, 3))

    Parameters
    ----------
    r : int
        Branching factor of the tree; each node will have `r`
        children.

    h : int
        Height of the tree.

    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : NetworkX graph
        A balanced `r`-ary tree of height `h`.

    Notes
    -----
    This is the rooted tree where all leaves are at distance `h` from
    the root. The root has degree `r` and all other internal nodes
    have degree `r + 1`.

    Node labels are integers, starting from zero.

    A balanced tree is also known as a *complete r-ary tree*.

    """
    # The number of nodes in the balanced tree is `1 + r + ... + r^h`,
    # which is computed by using the closed-form formula for a geometric
    # sum with ratio `r`. In the special case that `r` is 1, the number
    # of nodes is simply `h + 1` (since the tree is actually a path
    # graph).
    if r == 1:
        n = h + 1
    else:
        # This must be an integer if both `r` and `h` are integers. If
        # they are not, we force integer division anyway.
        n = (1 - r ** (h + 1)) // (1 - r)
    return full_rary_tree(r, n, create_using=create_using)


@nx._dispatchable(graphs=None, returns_graph=True)
def barbell_graph(m1, m2, create_using=None):
    """Returns the Barbell Graph: two complete graphs connected by a path.

    .. plot::

        >>> nx.draw(nx.barbell_graph(4, 2))

    Parameters
    ----------
    m1 : int
        Size of the left and right barbells, must be greater than 2.

    m2 : int
        Length of the path connecting the barbells.

    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.
       Only undirected Graphs are supported.

    Returns
    -------
    G : NetworkX graph
        A barbell graph.

    Notes
    -----


    Two identical complete graphs $K_{m1}$ form the left and right bells,
    and are connected by a path $P_{m2}$.

    The `2*m1+m2`  nodes are numbered
        `0, ..., m1-1` for the left barbell,
        `m1, ..., m1+m2-1` for the path,
        and `m1+m2, ..., 2*m1+m2-1` for the right barbell.

    The 3 subgraphs are joined via the edges `(m1-1, m1)` and
    `(m1+m2-1, m1+m2)`. If `m2=0`, this is merely two complete
    graphs joined together.

    This graph is an extremal example in David Aldous
    and Jim Fill's e-text on Random Walks on Graphs.

    """
    if m1 < 2:
        raise NetworkXError("Invalid graph description, m1 should be >=2")
    if m2 < 0:
        raise NetworkXError("Invalid graph description, m2 should be >=0")

    # left barbell
    G = complete_graph(m1, create_using)
    if G.is_directed():
        raise NetworkXError("Directed Graph not supported")

    # connecting path
    G.add_nodes_from(range(m1, m1 + m2 - 1))
    if m2 > 1:
        G.add_edges_from(pairwise(range(m1, m1 + m2)))

    # right barbell
    G.add_edges_from(
        (u, v) for u in range(m1 + m2, 2 * m1 + m2) for v in range(u + 1, 2 * m1 + m2)
    )

    # connect it up
    G.add_edge(m1 - 1, m1)
    if m2 > 0:
        G.add_edge(m1 + m2 - 1, m1 + m2)

    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def binomial_tree(n, create_using=None):
    """Returns the Binomial Tree of order n.

    The binomial tree of order 0 consists of a single node. A binomial tree of order k
    is defined recursively by linking two binomial trees of order k-1: the root of one is
    the leftmost child of the root of the other.

    .. plot::

        >>> nx.draw(nx.binomial_tree(3))

    Parameters
    ----------
    n : int
        Order of the binomial tree.

    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : NetworkX graph
        A binomial tree of $2^n$ nodes and $2^n - 1$ edges.

    """
    G = nx.empty_graph(1, create_using)

    N = 1
    for i in range(n):
        # Use G.edges() to ensure 2-tuples. G.edges is 3-tuple for MultiGraph
        edges = [(u + N, v + N) for (u, v) in G.edges()]
        G.add_edges_from(edges)
        G.add_edge(0, N)
        N *= 2
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
@nodes_or_number(0)
def complete_graph(n, create_using=None):
    """Return the complete graph `K_n` with n nodes.

    A complete graph on `n` nodes means that all pairs
    of distinct nodes have an edge connecting them.

    .. plot::

        >>> nx.draw(nx.complete_graph(5))

    Parameters
    ----------
    n : int or iterable container of nodes
        If n is an integer, nodes are from range(n).
        If n is a container of nodes, those nodes appear in the graph.
        Warning: n is not checked for duplicates and if present the
        resulting graph may not be as desired. Make sure you have no duplicates.
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Examples
    --------
    >>> G = nx.complete_graph(9)
    >>> len(G)
    9
    >>> G.size()
    36
    >>> G = nx.complete_graph(range(11, 14))
    >>> list(G.nodes())
    [11, 12, 13]
    >>> G = nx.complete_graph(4, nx.DiGraph())
    >>> G.is_directed()
    True

    """
    _, nodes = n
    G = empty_graph(nodes, create_using)
    if len(nodes) > 1:
        if G.is_directed():
            edges = itertools.permutations(nodes, 2)
        else:
            edges = itertools.combinations(nodes, 2)
        G.add_edges_from(edges)
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def circular_ladder_graph(n, create_using=None):
    """Returns the circular ladder graph $CL_n$ of length n.

    $CL_n$ consists of two concentric n-cycles in which
    each of the n pairs of concentric nodes are joined by an edge.

    Node labels are the integers 0 to n-1

    .. plot::

        >>> nx.draw(nx.circular_ladder_graph(5))

    """
    G = ladder_graph(n, create_using)
    G.add_edge(0, n - 1)
    G.add_edge(n, 2 * n - 1)
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def circulant_graph(n, offsets, create_using=None):
    r"""Returns the circulant graph $Ci_n(x_1, x_2, ..., x_m)$ with $n$ nodes.

    The circulant graph $Ci_n(x_1, ..., x_m)$ consists of $n$ nodes $0, ..., n-1$
    such that node $i$ is connected to nodes $(i + x) \mod n$ and $(i - x) \mod n$
    for all $x$ in $x_1, ..., x_m$. Thus $Ci_n(1)$ is a cycle graph.

    .. plot::

        >>> nx.draw(nx.circulant_graph(10, [1]))

    Parameters
    ----------
    n : integer
        The number of nodes in the graph.
    offsets : list of integers
        A list of node offsets, $x_1$ up to $x_m$, as described above.
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    NetworkX Graph of type create_using

    Examples
    --------
    Many well-known graph families are subfamilies of the circulant graphs;
    for example, to create the cycle graph on n points, we connect every
    node to nodes on either side (with offset plus or minus one). For n = 10,

    >>> G = nx.circulant_graph(10, [1])
    >>> edges = [
    ...     (0, 9),
    ...     (0, 1),
    ...     (1, 2),
    ...     (2, 3),
    ...     (3, 4),
    ...     (4, 5),
    ...     (5, 6),
    ...     (6, 7),
    ...     (7, 8),
    ...     (8, 9),
    ... ]
    >>> sorted(edges) == sorted(G.edges())
    True

    Similarly, we can create the complete graph
    on 5 points with the set of offsets [1, 2]:

    >>> G = nx.circulant_graph(5, [1, 2])
    >>> edges = [
    ...     (0, 1),
    ...     (0, 2),
    ...     (0, 3),
    ...     (0, 4),
    ...     (1, 2),
    ...     (1, 3),
    ...     (1, 4),
    ...     (2, 3),
    ...     (2, 4),
    ...     (3, 4),
    ... ]
    >>> sorted(edges) == sorted(G.edges())
    True

    """
    G = empty_graph(n, create_using)
    for i in range(n):
        for j in offsets:
            G.add_edge(i, (i - j) % n)
            G.add_edge(i, (i + j) % n)
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
@nodes_or_number(0)
def cycle_graph(n, create_using=None):
    """Returns the cycle graph $C_n$ of cyclically connected nodes.

    $C_n$ is a path with its two end-nodes connected.

    .. plot::

        >>> nx.draw(nx.cycle_graph(5))

    Parameters
    ----------
    n : int or iterable container of nodes
        If n is an integer, nodes are from `range(n)`.
        If n is a container of nodes, those nodes appear in the graph.
        Warning: n is not checked for duplicates and if present the
        resulting graph may not be as desired. Make sure you have no duplicates.
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Notes
    -----
    If create_using is directed, the direction is in increasing order.

    """
    _, nodes = n
    G = empty_graph(nodes, create_using)
    G.add_edges_from(pairwise(nodes, cyclic=True))
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def dorogovtsev_goltsev_mendes_graph(n, create_using=None):
    """Returns the hierarchically constructed Dorogovtsev--Goltsev--Mendes graph.

    The Dorogovtsev--Goltsev--Mendes [1]_ procedure deterministically produces a
    scale-free graph with ``3/2 * (3**(n-1) + 1)`` nodes
    and ``3**n`` edges for a given `n`.

    Note that `n` denotes the number of times the state transition is applied,
    starting from the base graph with ``n = 0`` (no transitions), as in [2]_.
    This is different from the parameter ``t = n - 1`` in [1]_.

    .. plot::

        >>> nx.draw(nx.dorogovtsev_goltsev_mendes_graph(3))

    Parameters
    ----------
    n : integer
        The generation number.

    create_using : NetworkX graph constructor, optional (default=nx.Graph)
        Graph type to create. Directed graphs and multigraphs are not supported.

    Returns
    -------
    G : NetworkX `Graph`

    Raises
    ------
    NetworkXError
        If `n` is less than zero.

        If `create_using` is a directed graph or multigraph.

    Examples
    --------
    >>> G = nx.dorogovtsev_goltsev_mendes_graph(3)
    >>> G.number_of_nodes()
    15
    >>> G.number_of_edges()
    27
    >>> nx.is_planar(G)
    True

    References
    ----------
    .. [1] S. N. Dorogovtsev, A. V. Goltsev and J. F. F. Mendes,
        "Pseudofractal scale-free web", Physical Review E 65, 066122, 2002.
        https://arxiv.org/pdf/cond-mat/0112143.pdf
    .. [2] Weisstein, Eric W. "Dorogovtsev--Goltsev--Mendes Graph".
        From MathWorld--A Wolfram Web Resource.
        https://mathworld.wolfram.com/Dorogovtsev-Goltsev-MendesGraph.html
    """
    if n < 0:
        raise NetworkXError("n must be greater than or equal to 0")

    G = empty_graph(0, create_using)
    if G.is_directed():
        raise NetworkXError("directed graph not supported")
    if G.is_multigraph():
        raise NetworkXError("multigraph not supported")

    G.add_edge(0, 1)
    new_node = 2  # next node to be added
    for _ in range(n):  # iterate over number of generations.
        new_edges = []
        for u, v in G.edges():
            new_edges.append((u, new_node))
            new_edges.append((v, new_node))
            new_node += 1

        G.add_edges_from(new_edges)
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
@nodes_or_number(0)
def empty_graph(n=0, create_using=None, default=Graph):
    """Returns the empty graph with n nodes and zero edges.

    .. plot::

        >>> nx.draw(nx.empty_graph(5))

    Parameters
    ----------
    n : int or iterable container of nodes (default = 0)
        If n is an integer, nodes are from `range(n)`.
        If n is a container of nodes, those nodes appear in the graph.
    create_using : Graph Instance, Constructor or None
        Indicator of type of graph to return.
        If a Graph-type instance, then clear and use it.
        If None, use the `default` constructor.
        If a constructor, call it to create an empty graph.
    default : Graph constructor (optional, default = nx.Graph)
        The constructor to use if create_using is None.
        If None, then nx.Graph is used.
        This is used when passing an unknown `create_using` value
        through your home-grown function to `empty_graph` and
        you want a default constructor other than nx.Graph.

    Examples
    --------
    >>> G = nx.empty_graph(10)
    >>> G.number_of_nodes()
    10
    >>> G.number_of_edges()
    0
    >>> G = nx.empty_graph("ABC")
    >>> G.number_of_nodes()
    3
    >>> sorted(G)
    ['A', 'B', 'C']

    Notes
    -----
    The variable create_using should be a Graph Constructor or a
    "graph"-like object. Constructors, e.g. `nx.Graph` or `nx.MultiGraph`
    will be used to create the returned graph. "graph"-like objects
    will be cleared (nodes and edges will be removed) and refitted as
    an empty "graph" with nodes specified in n. This capability
    is useful for specifying the class-nature of the resulting empty
    "graph" (i.e. Graph, DiGraph, MyWeirdGraphClass, etc.).

    The variable create_using has three main uses:
    Firstly, the variable create_using can be used to create an
    empty digraph, multigraph, etc.  For example,

    >>> n = 10
    >>> G = nx.empty_graph(n, create_using=nx.DiGraph)

    will create an empty digraph on n nodes.

    Secondly, one can pass an existing graph (digraph, multigraph,
    etc.) via create_using. For example, if G is an existing graph
    (resp. digraph, multigraph, etc.), then empty_graph(n, create_using=G)
    will empty G (i.e. delete all nodes and edges using G.clear())
    and then add n nodes and zero edges, and return the modified graph.

    Thirdly, when constructing your home-grown graph creation function
    you can use empty_graph to construct the graph by passing a user
    defined create_using to empty_graph. In this case, if you want the
    default constructor to be other than nx.Graph, specify `default`.

    >>> def mygraph(n, create_using=None):
    ...     G = nx.empty_graph(n, create_using, nx.MultiGraph)
    ...     G.add_edges_from([(0, 1), (0, 1)])
    ...     return G
    >>> G = mygraph(3)
    >>> G.is_multigraph()
    True
    >>> G = mygraph(3, nx.Graph)
    >>> G.is_multigraph()
    False

    See also create_empty_copy(G).

    """
    if create_using is None:
        G = default()
    elif isinstance(create_using, type):
        G = create_using()
    elif not hasattr(create_using, "adj"):
        raise TypeError("create_using is not a valid NetworkX graph type or instance")
    else:
        # create_using is a NetworkX style Graph
        create_using.clear()
        G = create_using

    _, nodes = n
    G.add_nodes_from(nodes)
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def ladder_graph(n, create_using=None):
    """Returns the Ladder graph of length n.

    This is two paths of n nodes, with
    each pair connected by a single edge.

    Node labels are the integers 0 to 2*n - 1.

    .. plot::

        >>> nx.draw(nx.ladder_graph(5))

    """
    G = empty_graph(2 * n, create_using)
    if G.is_directed():
        raise NetworkXError("Directed Graph not supported")
    G.add_edges_from(pairwise(range(n)))
    G.add_edges_from(pairwise(range(n, 2 * n)))
    G.add_edges_from((v, v + n) for v in range(n))
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
@nodes_or_number([0, 1])
def lollipop_graph(m, n, create_using=None):
    """Returns the Lollipop Graph; ``K_m`` connected to ``P_n``.

    This is the Barbell Graph without the right barbell.

    .. plot::

        >>> nx.draw(nx.lollipop_graph(3, 4))

    Parameters
    ----------
    m, n : int or iterable container of nodes
        If an integer, nodes are from ``range(m)`` and ``range(m, m+n)``.
        If a container of nodes, those nodes appear in the graph.
        Warning: `m` and `n` are not checked for duplicates and if present the
        resulting graph may not be as desired. Make sure you have no duplicates.

        The nodes for `m` appear in the complete graph $K_m$ and the nodes
        for `n` appear in the path $P_n$
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    Networkx graph
       A complete graph with `m` nodes connected to a path of length `n`.

    Notes
    -----
    The 2 subgraphs are joined via an edge ``(m-1, m)``.
    If ``n=0``, this is merely a complete graph.

    (This graph is an extremal example in David Aldous and Jim
    Fill's etext on Random Walks on Graphs.)

    """
    m, m_nodes = m
    M = len(m_nodes)
    if M < 2:
        raise NetworkXError("Invalid description: m should indicate at least 2 nodes")

    n, n_nodes = n
    if isinstance(m, numbers.Integral) and isinstance(n, numbers.Integral):
        n_nodes = list(range(M, M + n))
    N = len(n_nodes)

    # the ball
    G = complete_graph(m_nodes, create_using)
    if G.is_directed():
        raise NetworkXError("Directed Graph not supported")

    # the stick
    G.add_nodes_from(n_nodes)
    if N > 1:
        G.add_edges_from(pairwise(n_nodes))

    if len(G) != M + N:
        raise NetworkXError("Nodes must be distinct in containers m and n")

    # connect ball to stick
    if M > 0 and N > 0:
        G.add_edge(m_nodes[-1], n_nodes[0])
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def null_graph(create_using=None):
    """Returns the Null graph with no nodes or edges.

    See empty_graph for the use of create_using.

    """
    G = empty_graph(0, create_using)
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
@nodes_or_number(0)
def path_graph(n, create_using=None):
    """Returns the Path graph `P_n` of linearly connected nodes.

    .. plot::

        >>> nx.draw(nx.path_graph(5))

    Parameters
    ----------
    n : int or iterable
        If an integer, nodes are 0 to n - 1.
        If an iterable of nodes, in the order they appear in the path.
        Warning: n is not checked for duplicates and if present the
        resulting graph may not be as desired. Make sure you have no duplicates.
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    """
    _, nodes = n
    G = empty_graph(nodes, create_using)
    G.add_edges_from(pairwise(nodes))
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
@nodes_or_number(0)
def star_graph(n, create_using=None):
    """Return the star graph

    The star graph consists of one center node connected to n outer nodes.

    .. plot::

        >>> nx.draw(nx.star_graph(6))

    Parameters
    ----------
    n : int or iterable
        If an integer, node labels are 0 to n with center 0.
        If an iterable of nodes, the center is the first.
        Warning: n is not checked for duplicates and if present the
        resulting graph may not be as desired. Make sure you have no duplicates.
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Notes
    -----
    The graph has n+1 nodes for integer n.
    So star_graph(3) is the same as star_graph(range(4)).
    """
    n, nodes = n
    if isinstance(n, numbers.Integral):
        nodes.append(int(n))  # there should be n+1 nodes
    G = empty_graph(nodes, create_using)
    if G.is_directed():
        raise NetworkXError("Directed Graph not supported")

    if len(nodes) > 1:
        hub, *spokes = nodes
        G.add_edges_from((hub, node) for node in spokes)
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
@nodes_or_number([0, 1])
def tadpole_graph(m, n, create_using=None):
    """Returns the (m,n)-tadpole graph; ``C_m`` connected to ``P_n``.

    This graph on m+n nodes connects a cycle of size `m` to a path of length `n`.
    It looks like a tadpole. It is also called a kite graph or a dragon graph.

    .. plot::

        >>> nx.draw(nx.tadpole_graph(3, 5))

    Parameters
    ----------
    m, n : int or iterable container of nodes
        If an integer, nodes are from ``range(m)`` and ``range(m,m+n)``.
        If a container of nodes, those nodes appear in the graph.
        Warning: `m` and `n` are not checked for duplicates and if present the
        resulting graph may not be as desired.

        The nodes for `m` appear in the cycle graph $C_m$ and the nodes
        for `n` appear in the path $P_n$.
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    Networkx graph
       A cycle of size `m` connected to a path of length `n`.

    Raises
    ------
    NetworkXError
        If ``m < 2``. The tadpole graph is undefined for ``m<2``.

    Notes
    -----
    The 2 subgraphs are joined via an edge ``(m-1, m)``.
    If ``n=0``, this is a cycle graph.
    `m` and/or `n` can be a container of nodes instead of an integer.

    """
    m, m_nodes = m
    M = len(m_nodes)
    if M < 2:
        raise NetworkXError("Invalid description: m should indicate at least 2 nodes")

    n, n_nodes = n
    if isinstance(m, numbers.Integral) and isinstance(n, numbers.Integral):
        n_nodes = list(range(M, M + n))

    # the circle
    G = cycle_graph(m_nodes, create_using)
    if G.is_directed():
        raise NetworkXError("Directed Graph not supported")

    # the stick
    nx.add_path(G, [m_nodes[-1]] + list(n_nodes))

    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def trivial_graph(create_using=None):
    """Return the Trivial graph with one node (with label 0) and no edges.

    .. plot::

        >>> nx.draw(nx.trivial_graph(), with_labels=True)

    """
    G = empty_graph(1, create_using)
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def turan_graph(n, r):
    r"""Return the Turan Graph

    The Turan Graph is a complete multipartite graph on $n$ nodes
    with $r$ disjoint subsets. That is, edges connect each node to
    every node not in its subset.

    Given $n$ and $r$, we create a complete multipartite graph with
    $r-(n \mod r)$ partitions of size $n/r$, rounded down, and
    $n \mod r$ partitions of size $n/r+1$, rounded down.

    .. plot::

        >>> nx.draw(nx.turan_graph(6, 2))

    Parameters
    ----------
    n : int
        The number of nodes.
    r : int
        The number of partitions.
        Must be less than or equal to n.

    Notes
    -----
    Must satisfy $1 <= r <= n$.
    The graph has $(r-1)(n^2)/(2r)$ edges, rounded down.
    """

    if not 1 <= r <= n:
        raise NetworkXError("Must satisfy 1 <= r <= n")

    partitions = [n // r] * (r - (n % r)) + [n // r + 1] * (n % r)
    G = complete_multipartite_graph(*partitions)
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
@nodes_or_number(0)
def wheel_graph(n, create_using=None):
    """Return the wheel graph

    The wheel graph consists of a hub node connected to a cycle of (n-1) nodes.

    .. plot::

        >>> nx.draw(nx.wheel_graph(5))

    Parameters
    ----------
    n : int or iterable
        If an integer, node labels are 0 to n with center 0.
        If an iterable of nodes, the center is the first.
        Warning: n is not checked for duplicates and if present the
        resulting graph may not be as desired. Make sure you have no duplicates.
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Node labels are the integers 0 to n - 1.
    """
    _, nodes = n
    G = empty_graph(nodes, create_using)
    if G.is_directed():
        raise NetworkXError("Directed Graph not supported")

    if len(nodes) > 1:
        hub, *rim = nodes
        G.add_edges_from((hub, node) for node in rim)
        if len(rim) > 1:
            G.add_edges_from(pairwise(rim, cyclic=True))
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def complete_multipartite_graph(*subset_sizes):
    """Returns the complete multipartite graph with the specified subset sizes.

    .. plot::

        >>> nx.draw(nx.complete_multipartite_graph(1, 2, 3))

    Parameters
    ----------
    subset_sizes : tuple of integers or tuple of node iterables
       The arguments can either all be integer number of nodes or they
       can all be iterables of nodes. If integers, they represent the
       number of nodes in each subset of the multipartite graph.
       If iterables, each is used to create the nodes for that subset.
       The length of subset_sizes is the number of subsets.

    Returns
    -------
    G : NetworkX Graph
       Returns the complete multipartite graph with the specified subsets.

       For each node, the node attribute 'subset' is an integer
       indicating which subset contains the node.

    Examples
    --------
    Creating a complete tripartite graph, with subsets of one, two, and three
    nodes, respectively.

        >>> G = nx.complete_multipartite_graph(1, 2, 3)
        >>> [G.nodes[u]["subset"] for u in G]
        [0, 1, 1, 2, 2, 2]
        >>> list(G.edges(0))
        [(0, 1), (0, 2), (0, 3), (0, 4), (0, 5)]
        >>> list(G.edges(2))
        [(2, 0), (2, 3), (2, 4), (2, 5)]
        >>> list(G.edges(4))
        [(4, 0), (4, 1), (4, 2)]

        >>> G = nx.complete_multipartite_graph("a", "bc", "def")
        >>> [G.nodes[u]["subset"] for u in sorted(G)]
        [0, 1, 1, 2, 2, 2]

    Notes
    -----
    This function generalizes several other graph builder functions.

    - If no subset sizes are given, this returns the null graph.
    - If a single subset size `n` is given, this returns the empty graph on
      `n` nodes.
    - If two subset sizes `m` and `n` are given, this returns the complete
      bipartite graph on `m + n` nodes.
    - If subset sizes `1` and `n` are given, this returns the star graph on
      `n + 1` nodes.

    See also
    --------
    complete_bipartite_graph
    """
    # The complete multipartite graph is an undirected simple graph.
    G = Graph()

    if len(subset_sizes) == 0:
        return G

    # set up subsets of nodes
    try:
        extents = pairwise(itertools.accumulate((0,) + subset_sizes))
        subsets = [range(start, end) for start, end in extents]
    except TypeError:
        subsets = subset_sizes
    else:
        if any(size < 0 for size in subset_sizes):
            raise NetworkXError(f"Negative number of nodes not valid: {subset_sizes}")

    # add nodes with subset attribute
    # while checking that ints are not mixed with iterables
    try:
        for i, subset in enumerate(subsets):
            G.add_nodes_from(subset, subset=i)
    except TypeError as err:
        raise NetworkXError("Arguments must be all ints or all iterables") from err

    # Across subsets, all nodes should be adjacent.
    # We can use itertools.combinations() because undirected.
    for subset1, subset2 in itertools.combinations(subsets, 2):
        G.add_edges_from(itertools.product(subset1, subset2))
    return G
