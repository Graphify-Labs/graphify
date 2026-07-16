"""Algorithms for directed acyclic graphs (DAGs).

Note that most of these functions are only guaranteed to work for DAGs.
In general, these functions do not check for acyclic-ness, so it is up
to the user to check for that.
"""

import heapq
from collections import deque
from functools import partial
from itertools import chain, combinations, product, starmap
from math import gcd

import networkx as nx
from networkx.utils import arbitrary_element, not_implemented_for, pairwise

__all__ = [
    "descendants",
    "ancestors",
    "topological_sort",
    "lexicographical_topological_sort",
    "all_topological_sorts",
    "topological_generations",
    "is_directed_acyclic_graph",
    "is_aperiodic",
    "transitive_closure",
    "transitive_closure_dag",
    "transitive_reduction",
    "antichains",
    "dag_longest_path",
    "dag_longest_path_length",
    "dag_to_branching",
    "compute_v_structures",
]

chaini = chain.from_iterable


@nx._dispatchable
def descendants(G, source):
    """Returns all nodes reachable from `source` in `G`.

    Parameters
    ----------
    G : NetworkX Graph
    source : node in `G`

    Returns
    -------
    set()
        The descendants of `source` in `G`

    Raises
    ------
    NetworkXError
        If node `source` is not in `G`.

    Examples
    --------
    >>> DG = nx.path_graph(5, create_using=nx.DiGraph)
    >>> sorted(nx.descendants(DG, 2))
    [3, 4]

    The `source` node is not a descendant of itself, but can be included manually:

    >>> sorted(nx.descendants(DG, 2) | {2})
    [2, 3, 4]

    See also
    --------
    ancestors
    """
    return {child for parent, child in nx.bfs_edges(G, source)}


@nx._dispatchable
def ancestors(G, source):
    """Returns all nodes having a path to `source` in `G`.

    Parameters
    ----------
    G : NetworkX Graph
    source : node in `G`

    Returns
    -------
    set()
        The ancestors of `source` in `G`

    Raises
    ------
    NetworkXError
        If node `source` is not in `G`.

    Examples
    --------
    >>> DG = nx.path_graph(5, create_using=nx.DiGraph)
    >>> sorted(nx.ancestors(DG, 2))
    [0, 1]

    The `source` node is not an ancestor of itself, but can be included manually:

    >>> sorted(nx.ancestors(DG, 2) | {2})
    [0, 1, 2]

    See also
    --------
    descendants
    """
    return {child for parent, child in nx.bfs_edges(G, source, reverse=True)}


@nx._dispatchable
def has_cycle(G):
    """Decides whether the directed graph has a cycle."""
    try:
        # Feed the entire iterator into a zero-length deque.
        deque(topological_sort(G), maxlen=0)
    except nx.NetworkXUnfeasible:
        return True
    else:
        return False


@nx._dispatchable
def is_directed_acyclic_graph(G):
    """Returns True if the graph `G` is a directed acyclic graph (DAG) or
    False if not.

    Parameters
    ----------
    G : NetworkX graph

    Returns
    -------
    bool
        True if `G` is a DAG, False otherwise

    Examples
    --------
    Undirected graph::

        >>> G = nx.Graph([(1, 2), (2, 3)])
        >>> nx.is_directed_acyclic_graph(G)
        False

    Directed graph with cycle::

        >>> G = nx.DiGraph([(1, 2), (2, 3), (3, 1)])
        >>> nx.is_directed_acyclic_graph(G)
        False

    Directed acyclic graph::

        >>> G = nx.DiGraph([(1, 2), (2, 3)])
        >>> nx.is_directed_acyclic_graph(G)
        True

    See also
    --------
    topological_sort
    """
    return G.is_directed() and not has_cycle(G)


@nx._dispatchable
def topological_generations(G):
    """Stratifies a DAG into generations.

    A topological generation is node collection in which ancestors of a node in each
    generation are guaranteed to be in a previous generation, and any descendants of
    a node are guaranteed to be in a following generation. Nodes are guaranteed to
    be in the earliest possible generation that they can belong to.

    Parameters
    ----------
    G : NetworkX digraph
        A directed acyclic graph (DAG)

    Yields
    ------
    sets of nodes
        Yields sets of nodes representing each generation.

    Raises
    ------
    NetworkXError
        Generations are defined for directed graphs only. If the graph
        `G` is undirected, a :exc:`NetworkXError` is raised.

    NetworkXUnfeasible
        If `G` is not a directed acyclic graph (DAG) no topological generations
        exist and a :exc:`NetworkXUnfeasible` exception is raised.  This can also
        be raised if `G` is changed while the returned iterator is being processed

    RuntimeError
        If `G` is changed while the returned iterator is being processed.

    Examples
    --------
    >>> DG = nx.DiGraph([(2, 1), (3, 1)])
    >>> [sorted(generation) for generation in nx.topological_generations(DG)]
    [[2, 3], [1]]

    Notes
    -----
    The generation in which a node resides can also be determined by taking the
    max-path-distance from the node to the farthest leaf node. That value can
    be obtained with this function using `enumerate(topological_generations(G))`.

    See also
    --------
    topological_sort
    """
    if not G.is_directed():
        raise nx.NetworkXError("Topological sort not defined on undirected graphs.")

    multigraph = G.is_multigraph()
    indegree_map = {v: d for v, d in G.in_degree() if d > 0}
    zero_indegree = [v for v, d in G.in_degree() if d == 0]

    while zero_indegree:
        this_generation = zero_indegree
        zero_indegree = []
        for node in this_generation:
            if node not in G:
                raise RuntimeError("Graph changed during iteration")
            for child in G.neighbors(node):
                try:
                    indegree_map[child] -= len(G[node][child]) if multigraph else 1
                except KeyError as err:
                    raise RuntimeError("Graph changed during iteration") from err
                if indegree_map[child] == 0:
                    zero_indegree.append(child)
                    del indegree_map[child]
        yield this_generation

    if indegree_map:
        raise nx.NetworkXUnfeasible(
            "Graph contains a cycle or graph changed during iteration"
        )


@nx._dispatchable
def topological_sort(G):
    """Returns a generator of nodes in topologically sorted order.

    A topological sort is a nonunique permutation of the nodes of a
    directed graph such that an edge from u to v implies that u
    appears before v in the topological sort order. This ordering is
    valid only if the graph has no directed cycles.

    Parameters
    ----------
    G : NetworkX digraph
        A directed acyclic graph (DAG)

    Yields
    ------
    nodes
        Yields the nodes in topological sorted order.

    Raises
    ------
    NetworkXError
        Topological sort is defined for directed graphs only. If the graph `G`
        is undirected, a :exc:`NetworkXError` is raised.

    NetworkXUnfeasible
        If `G` is not a directed acyclic graph (DAG) no topological sort exists
        and a :exc:`NetworkXUnfeasible` exception is raised.  This can also be
        raised if `G` is changed while the returned iterator is being processed

    RuntimeError
        If `G` is changed while the returned iterator is being processed.

    Examples
    --------
    To get the reverse order of the topological sort:

    >>> DG = nx.DiGraph([(1, 2), (2, 3)])
    >>> list(reversed(list(nx.topological_sort(DG))))
    [3, 2, 1]

    If your DiGraph naturally has the edges representing tasks/inputs
    and nodes representing people/processes that initiate tasks, then
    topological_sort is not quite what you need. You will have to change
    the tasks to nodes with dependence reflected by edges. The result is
    a kind of topological sort of the edges. This can be done
    with :func:`networkx.line_graph` as follows:

    >>> list(nx.topological_sort(nx.line_graph(DG)))
    [(1, 2), (2, 3)]

    Notes
    -----
    This algorithm is based on a description and proof in
    "Introduction to Algorithms: A Creative Approach" [1]_ .

    See also
    --------
    is_directed_acyclic_graph, lexicographical_topological_sort

    References
    ----------
    .. [1] Manber, U. (1989).
       *Introduction to Algorithms - A Creative Approach.* Addison-Wesley.
    """
    for generation in nx.topological_generations(G):
        yield from generation


@nx._dispatchable
def lexicographical_topological_sort(G, key=None):
    """Generate the nodes in the unique lexicographical topological sort order.

    Generates a unique ordering of nodes by first sorting topologically (for which there are often
    multiple valid orderings) and then additionally by sorting lexicographically.

    A topological sort arranges the nodes of a directed graph so that the
    upstream node of each directed edge precedes the downstream node.
    It is always possible to find a solution for directed graphs that have no cycles.
    There may be more than one valid solution.

    Lexicographical sorting is just sorting alphabetically. It is used here to break ties in the
    topological sort and to determine a single, unique ordering.  This can be useful in comparing
    sort results.

    The lexicographical order can be customized by providing a function to the `key=` parameter.
    The definition of the key function is the same as used in python's built-in `sort()`.
    The function takes a single argument and returns a key to use for sorting purposes.

    Lexicographical sorting can fail if the node names are un-sortable. See the example below.
    The solution is to provide a function to the `key=` argument that returns sortable keys.


    Parameters
    ----------
    G : NetworkX digraph
        A directed acyclic graph (DAG)

    key : function, optional
        A function of one argument that converts a node name to a comparison key.
        It defines and resolves ambiguities in the sort order.  Defaults to the identity function.

    Yields
    ------
    nodes
        Yields the nodes of G in lexicographical topological sort order.

    Raises
    ------
    NetworkXError
        Topological sort is defined for directed graphs only. If the graph `G`
        is undirected, a :exc:`NetworkXError` is raised.

    NetworkXUnfeasible
        If `G` is not a directed acyclic graph (DAG) no topological sort exists
        and a :exc:`NetworkXUnfeasible` exception is raised.  This can also be
        raised if `G` is changed while the returned iterator is being processed

    RuntimeError
        If `G` is changed while the returned iterator is being processed.

    TypeError
        Results from un-sortable node names.
        Consider using `key=` parameter to resolve ambiguities in the sort order.

    Examples
    --------
    >>> DG = nx.DiGraph([(2, 1), (2, 5), (1, 3), (1, 4), (5, 4)])
    >>> list(nx.lexicographical_topological_sort(DG))
    [2, 1, 3, 5, 4]
    >>> list(nx.lexicographical_topological_sort(DG, key=lambda x: -x))
    [2, 5, 1, 4, 3]

    The sort will fail for any graph with integer and string nodes. Comparison of integer to strings
    is not defined in python.  Is 3 greater or less than 'red'?

    >>> DG = nx.DiGraph([(1, "red"), (3, "red"), (1, "green"), (2, "blue")])
    >>> list(nx.lexicographical_topological_sort(DG))
    Traceback (most recent call last):
    ...
    TypeError: '<' not supported between instances of 'str' and 'int'
    ...

    Incomparable nodes can be resolved using a `key` function. This example function
    allows comparison of integers and strings by returning a tuple where the first
    element is True for `str`, False otherwise. The second element is the node name.
    This groups the strings and integers separately so they can be compared only among themselves.

    >>> key = lambda node: (isinstance(node, str), node)
    >>> list(nx.lexicographical_topological_sort(DG, key=key))
    [1, 2, 3, 'blue', 'green', 'red']

    Notes
    -----
    This algorithm is based on a description and proof in
    "Introduction to Algorithms: A Creative Approach" [1]_ .

    See also
    --------
    topological_sort

    References
    ----------
    .. [1] Manber, U. (1989).
       *Introduction to Algorithms - A Creative Approach.* Addison-Wesley.
    """
    if not G.is_directed():
        msg = "Topological sort not defined on undirected graphs."
        raise nx.NetworkXError(msg)

    if key is None:

        def key(node):
            return node

    nodeid_map = {n: i for i, n in enumerate(G)}

    def create_tuple(node):
        return key(node), nodeid_map[node], node

    indegree_map = {v: d for v, d in G.in_degree() if d > 0}
    # These nodes have zero indegree and ready to be returned.
    zero_indegree = [create_tuple(v) for v, d in G.in_degree() if d == 0]
    heapq.heapify(zero_indegree)

    while zero_indegree:
        _, _, node = heapq.heappop(zero_indegree)

        if node not in G:
            raise RuntimeError("Graph changed during iteration")
        for _, child in G.edges(node):
            try:
                indegree_map[child] -= 1
            except KeyError as err:
                raise RuntimeError("Graph changed during iteration") from err
            if indegree_map[child] == 0:
                try:
                    heapq.heappush(zero_indegree, create_tuple(child))
                except TypeError as err:
                    raise TypeError(
                        f"{err}\nConsider using `key=` parameter to resolve ambiguities in the sort order."
                    )
                del indegree_map[child]

        yield node

    if indegree_map:
        msg = "Graph contains a cycle or graph changed during iteration"
        raise nx.NetworkXUnfeasible(msg)


@not_implemented_for("undirected")
@nx._dispatchable
def all_topological_sorts(G):
    """Returns a generator of _all_ topological sorts of the directed graph G.

    A topological sort is a nonunique permutation of the nodes such that an
    edge from u to v implies that u appears before v in the topological sort
    order.

    Parameters
    ----------
    G : NetworkX DiGraph
        A directed graph

    Yields
    ------
    topological_sort_order : list
        a list of nodes in `G`, representing one of the topological sort orders

    Raises
    ------
    NetworkXNotImplemented
        If `G` is not directed
    NetworkXUnfeasible
        If `G` is not acyclic

    Examples
    --------
    To enumerate all topological sorts of directed graph:

    >>> DG = nx.DiGraph([(1, 2), (2, 3), (2, 4)])
    >>> list(nx.all_topological_sorts(DG))
    [[1, 2, 4, 3], [1, 2, 3, 4]]

    Notes
    -----
    Implements an iterative version of the algorithm given in [1].

    References
    ----------
    .. [1] Knuth, Donald E., Szwarcfiter, Jayme L. (1974).
       "A Structured Program to Generate All Topological Sorting Arrangements"
       Information Processing Letters, Volume 2, Issue 6, 1974, Pages 153-157,
       ISSN 0020-0190,
       https://doi.org/10.1016/0020-0190(74)90001-5.
       Elsevier (North-Holland), Amsterdam
    """
    if not G.is_directed():
        raise nx.NetworkXError("Topological sort not defined on undirected graphs.")

    # the names of count and D are chosen to match the global variables in [1]
    # number of edges originating in a vertex v
    count = dict(G.in_degree())
    # vertices with indegree 0
    D = deque([v for v, d in G.in_degree() if d == 0])
    # stack of first value chosen at a position k in the topological sort
    bases = []
    current_sort = []

    # do-while construct
    while True:
        assert all(count[v] == 0 for v in D)

        if len(current_sort) == len(G):
            yield list(current_sort)

            # clean-up stack
            while len(current_sort) > 0:
                assert len(bases) == len(current_sort)
                q = current_sort.pop()

                # "restores" all edges (q, x)
                # NOTE: it is important to iterate over edges instead
                # of successors, so count is updated correctly in multigraphs
                for _, j in G.out_edges(q):
                    count[j] += 1
                    assert count[j] >= 0
                # remove entries from D
                while len(D) > 0 and count[D[-1]] > 0:
                    D.pop()

                # corresponds to a circular shift of the values in D
                # if the first value chosen (the base) is in the first
                # position of D again, we are done and need to consider the
                # previous condition
                D.appendleft(q)
                if D[-1] == bases[-1]:
                    # all possible values have been chosen at current position
                    # remove corresponding marker
                    bases.pop()
                else:
                    # there are still elements that have not been fixed
                    # at the current position in the topological sort
                    # stop removing elements, escape inner loop
                    break

        else:
            if len(D) == 0:
                raise nx.NetworkXUnfeasible("Graph contains a cycle.")

            # choose next node
            q = D.pop()
            # "erase" all edges (q, x)
            # NOTE: it is important to iterate over edges instead
            # of successors, so count is updated correctly in multigraphs
            for _, j in G.out_edges(q):
                count[j] -= 1
                assert count[j] >= 0
                if count[j] == 0:
                    D.append(j)
            current_sort.append(q)

            # base for current position might _not_ be fixed yet
            if len(bases) < len(current_sort):
                bases.append(q)

        if len(bases) == 0:
            break


@nx._dispatchable
def is_aperiodic(G):
    """Returns True if `G` is aperiodic.

    A directed graph is aperiodic if there is no integer k > 1 that
    divides the length of every cycle in the graph.

    Parameters
    ----------
    G : NetworkX DiGraph
        A directed graph

    Returns
    -------
    bool
        True if the graph is aperiodic False otherwise

    Raises
    ------
    NetworkXError
        If `G` is not directed

    Examples
    --------
    A graph consisting of one cycle, the length of which is 2. Therefore ``k = 2``
    divides the length of every cycle in the graph and thus the graph
    is *not aperiodic*::

        >>> DG = nx.DiGraph([(1, 2), (2, 1)])
        >>> nx.is_aperiodic(DG)
        False

    A graph consisting of two cycles: one of length 2 and the other of length 3.
    The cycle lengths are coprime, so there is no single value of k where ``k > 1``
    that divides each cycle length and therefore the graph is *aperiodic*::

        >>> DG = nx.DiGraph([(1, 2), (2, 3), (3, 1), (1, 4), (4, 1)])
        >>> nx.is_aperiodic(DG)
        True

    A graph consisting of two cycles: one of length 2 and the other of length 4.
    The lengths of the cycles share a common factor ``k = 2``, and therefore
    the graph is *not aperiodic*::

        >>> DG = nx.DiGraph([(1, 2), (2, 1), (3, 4), (4, 5), (5, 6), (6, 3)])
        >>> nx.is_aperiodic(DG)
        False

    An acyclic graph, therefore the graph is *not aperiodic*::

        >>> DG = nx.DiGraph([(1, 2), (2, 3)])
        >>> nx.is_aperiodic(DG)
        False

    Notes
    -----
    This uses the method outlined in [1]_, which runs in $O(m)$ time
    given $m$ edges in `G`. Note that a graph is not aperiodic if it is
    acyclic as every integer trivial divides length 0 cycles.

    References
    ----------
    .. [1] Jarvis, J. P.; Shier, D. R. (1996),
       "Graph-theoretic analysis of finite Markov chains,"
       in Shier, D. R.; Wallenius, K. T., Applied Mathematical Modeling:
       A Multidisciplinary Approach, CRC Press.
    """
    if not G.is_directed():
        raise nx.NetworkXError("is_aperiodic not defined for undirected graphs")
    if len(G) == 0:
        raise nx.NetworkXPointlessConcept("Graph has no nodes.")
    s = arbitrary_element(G)
    levels = {s: 0}
    this_level = [s]
    g = 0
    lev = 1
    while this_level:
        next_level = []
        for u in this_level:
            for v in G[u]:
                if v in levels:  # Non-Tree Edge
                    g = gcd(g, levels[u] - levels[v] + 1)
                else:  # Tree Edge
                    next_level.append(v)
                    levels[v] = lev
        this_level = next_level
        lev += 1
    if len(levels) == len(G):  # All nodes in tree
        return g == 1
    else:
        return g == 1 and nx.is_aperiodic(G.subgraph(set(G) - set(levels)))


@nx._dispatchable(preserve_all_attrs=True, returns_graph=True)
def transitive_closure(G, reflexive=False):
    """Returns transitive closure of a graph

    The transitive closure of G = (V,E) is a graph G+ = (V,E+) such that
    for all v, w in V there is an edge (v, w) in E+ if and only if there
    is a path from v to w in G.

    Handling of paths from v to v has some flexibility within this definition.
    A reflexive transitive closure creates a self-loop for the path
    from v to v of length 0. The usual transitive closure creates a
    self-loop only if a cycle exists (a path from v to v with length > 0).
    We also allow an option for no self-loops.

    Parameters
    ----------
    G : NetworkX Graph
        A directed/undirected graph/multigraph.
    reflexive : Bool or None, optional (default: False)
        Determines when cycles create self-loops in the Transitive Closure.
        If True, trivial cycles (length 0) create self-loops. The result
        is a reflexive transitive closure of G.
        If False (the default) non-trivial cycles create self-loops.
        If None, self-loops are not created.

    Returns
    -------
    NetworkX graph
        The transitive closure of `G`

    Raises
    ------
    NetworkXError
        If `reflexive` not in `{None, True, False}`

    Examples
    --------
    The treatment of trivial (i.e. length 0) cycles is controlled by the
    `reflexive` parameter.

    Trivial (i.e. length 0) cycles do not create self-loops when
    ``reflexive=False`` (the default)::

        >>> DG = nx.DiGraph([(1, 2), (2, 3)])
        >>> TC = nx.transitive_closure(DG, reflexive=False)
        >>> TC.edges()
        OutEdgeView([(1, 2), (1, 3), (2, 3)])

    However, nontrivial (i.e. length greater than 0) cycles create self-loops
    when ``reflexive=False`` (the default)::

        >>> DG = nx.DiGraph([(1, 2), (2, 3), (3, 1)])
        >>> TC = nx.transitive_closure(DG, reflexive=False)
        >>> TC.edges()
        OutEdgeView([(1, 2), (1, 3), (1, 1), (2, 3), (2, 1), (2, 2), (3, 1), (3, 2), (3, 3)])

    Trivial cycles (length 0) create self-loops when ``reflexive=True``::

        >>> DG = nx.DiGraph([(1, 2), (2, 3)])
        >>> TC = nx.transitive_closure(DG, reflexive=True)
        >>> TC.edges()
        OutEdgeView([(1, 2), (1, 1), (1, 3), (2, 3), (2, 2), (3, 3)])

    And the third option is not to create self-loops at all when ``reflexive=None``::

        >>> DG = nx.DiGraph([(1, 2), (2, 3), (3, 1)])
        >>> TC = nx.transitive_closure(DG, reflexive=None)
        >>> TC.edges()
        OutEdgeView([(1, 2), (1, 3), (2, 3), (2, 1), (3, 1), (3, 2)])

    References
    ----------
    .. [1] https://www.ics.uci.edu/~eppstein/PADS/PartialOrder.py
    """
    TC = G.copy()

    if reflexive not in {None, True, False}:
        raise nx.NetworkXError("Incorrect value for the parameter `reflexive`")

    for v in G:
        if reflexive is None:
            TC.add_edges_from((v, u) for u in nx.descendants(G, v) if u not in TC[v])
        elif reflexive is True:
            TC.add_edges_from(
                (v, u) for u in nx.descendants(G, v) | {v} if u not in TC[v]
            )
        elif reflexive is False:
            TC.add_edges_from((v, e[1]) for e in nx.edge_bfs(G, v) if e[1] not in TC[v])

    return TC


@not_implemented_for("undirected")
@nx._dispatchable(preserve_all_attrs=True, returns_graph=True)
def transitive_closure_dag(G, topo_order=None):
    """Returns the transitive closure of a directed acyclic graph.

    This function is faster than the function `transitive_closure`, but fails
    if the graph has a cycle.

    The transitive closure of G = (V,E) is a graph G+ = (V,E+) such that
    for all v, w in V there is an edge (v, w) in E+ if and only if there
    is a non-null path from v to w in G.

    Parameters
    ----------
    G : NetworkX DiGraph
        A directed acyclic graph (DAG)

    topo_order: list or tuple, optional
        A topological order for G (if None, the function will compute one)

    Returns
    -------
    NetworkX DiGraph
        The transitive closure of `G`

    Raises
    ------
    NetworkXNotImplemented
        If `G` is not directed
    NetworkXUnfeasible
        If `G` has a cycle

    Examples
    --------
    >>> DG = nx.DiGraph([(1, 2), (2, 3)])
    >>> TC = nx.transitive_closure_dag(DG)
    >>> TC.edges()
    OutEdgeView([(1, 2), (1, 3), (2, 3)])

    Notes
    -----
    This algorithm is probably simple enough to be well-known but I didn't find
    a mention in the literature.
    """
    if topo_order is None:
        topo_order = list(topological_sort(G))

    TC = G.copy()

    # idea: traverse vertices following a reverse topological order, connecting
    # each vertex to its descendants at distance 2 as we go
    for v in reversed(topo_order):
        TC.add_edges_from((v, u) for u in nx.descendants_at_distance(TC, v, 2))

    return TC


@not_implemented_for("undirected")
@nx._dispatchable(returns_graph=True)
def transitive_reduction(G):
    """Returns transitive reduction of a directed graph

    The transitive reduction of G = (V,E) is a graph G- = (V,E-) such that
    for all v,w in V there is an edge (v,w) in E- if and only if (v,w) is
    in E and there is no path from v to w in G with length greater than 1.

    Parameters
    ----------
    G : NetworkX DiGraph
        A directed acyclic graph (DAG)

    Returns
    -------
    NetworkX DiGraph
        The transitive reduction of `G`

    Raises
    ------
    NetworkXError
        If `G` is not a directed acyclic graph (DAG) transitive reduction is
        not uniquely defined and a :exc:`NetworkXError` exception is raised.

    Examples
    --------
    To perform transitive reduction on a DiGraph:

    >>> DG = nx.DiGraph([(1, 2), (2, 3), (1, 3)])
    >>> TR = nx.transitive_reduction(DG)
    >>> list(TR.edges)
    [(1, 2), (2, 3)]

    To avoid unnecessary data copies, this implementation does not return a
    DiGraph with node/edge data.
    To perform transitive reduction on a DiGraph and transfer node/edge data:

    >>> DG = nx.DiGraph()
    >>> DG.add_edges_from([(1, 2), (2, 3), (1, 3)], color="red")
    >>> TR = nx.transitive_reduction(DG)
    >>> TR.add_nodes_from(DG.nodes(data=True))
    >>> TR.add_edges_from((u, v, DG.edges[u, v]) for u, v in TR.edges)
    >>> list(TR.edges(data=True))
    [(1, 2, {'color': 'red'}), (2, 3, {'color': 'red'})]

    References
    ----------
    https://en.wikipedia.org/wiki/Transitive_reduction

    """
    if not is_directed_acyclic_graph(G):
        msg = "Directed Acyclic Graph required for transitive_reduction"
        raise nx.NetworkXError(msg)
    TR = nx.DiGraph()
    TR.add_nodes_from(G.nodes())
    descendants = {}
    # count before removing set stored in descendants
    check_count = dict(G.in_degree)
    for u in G:
        u_nbrs = set(G[u])
        for v in G[u]:
            if v in u_nbrs:
                if v not in descendants:
                    descendants[v] = {y for x, y in nx.dfs_edges(G, v)}
                u_nbrs -= descendants[v]
            check_count[v] -= 1
            if check_count[v] == 0:
                del descendants[v]
        TR.add_edges_from((u, v) for v in u_nbrs)
    return TR


@not_implemented_for("undirected")
@nx._dispatchable
def antichains(G, topo_order=None):
    """Generates antichains from a directed acyclic graph (DAG).

    An antichain is a subset of a partially ordered set such that any
    two elements in the subset are incomparable.

    Parameters
    ----------
    G : NetworkX DiGraph
        A directed acyclic graph (DAG)

    topo_order: list or tuple, optional
        A topological order for G (if None, the function will compute one)

    Yields
    ------
    antichain : list
        a list of nodes in `G` representing an antichain

    Raises
    ------
    NetworkXNotImplemented
        If `G` is not directed

    NetworkXUnfeasible
        If `G` contains a cycle

    Examples
    --------
    >>> DG = nx.DiGraph([(1, 2), (1, 3)])
    >>> list(nx.antichains(DG))
    [[], [3], [2], [2, 3], [1]]

    Notes
    -----
    This function was originally developed by Peter Jipsen and Franco Saliola
    for the SAGE project. It's included in NetworkX with permission from the
    authors. Original SAGE code at:

    https://github.com/sagemath/sage/blob/master/src/sage/combinat/posets/hasse_diagram.py

    References
    ----------
    .. [1] Free Lattices, by R. Freese, J. Jezek and J. B. Nation,
       AMS, Vol 42, 1995, p. 226.
    """
    if topo_order is None:
        topo_order = list(nx.topological_sort(G))

    TC = nx.transitive_closure_dag(G, topo_order)
    antichains_stacks = [([], list(reversed(topo_order)))]

    while antichains_stacks:
        (antichain, stack) = antichains_stacks.pop()
        # Invariant:
        #  - the elements of antichain are independent
        #  - the elements of stack are independent from those of antichain
        yield antichain
        while stack:
            x = stack.pop()
            new_antichain = antichain + [x]
            new_stack = [t for t in stack if not ((t in TC[x]) or (x in TC[t]))]
            antichains_stacks.append((new_antichain, new_stack))


@not_implemented_for("undirected")
@nx._dispatchable(edge_attrs={"weight": "default_weight"})
def dag_longest_path(G, weight="weight", default_weight=1, topo_order=None):
    """Returns the longest path in a directed acyclic graph (DAG).

    If `G` has edges with `weight` attribute the edge data are used as
    weight values.

    Parameters
    ----------
    G : NetworkX DiGraph
        A directed acyclic graph (DAG)

    weight : str, optional
        Edge data key to use for weight

    default_weight : int, optional
        The weight of edges that do not have a weight attribute

    topo_order: list or tuple, optional
        A topological order for `G` (if None, the function will compute one)

    Returns
    -------
    list
        Longest path

    Raises
    ------
    NetworkXNotImplemented
        If `G` is not directed

    Examples
    --------
    >>> DG = nx.DiGraph(
    ...     [(0, 1, {"cost": 1}), (1, 2, {"cost": 1}), (0, 2, {"cost": 42})]
    ... )
    >>> list(nx.all_simple_paths(DG, 0, 2))
    [[0, 1, 2], [0, 2]]
    >>> nx.dag_longest_path(DG)
    [0, 1, 2]
    >>> nx.dag_longest_path(DG, weight="cost")
    [0, 2]

    In the case where multiple valid topological orderings exist, `topo_order`
    can be used to specify a specific ordering:

    >>> DG = nx.DiGraph([(0, 1), (0, 2)])
    >>> sorted(nx.all_topological_sorts(DG))  # Valid topological orderings
    [[0, 1, 2], [0, 2, 1]]
    >>> nx.dag_longest_path(DG, topo_order=[0, 1, 2])
    [0, 1]
    >>> nx.dag_longest_path(DG, topo_order=[0, 2, 1])
    [0, 2]

    See also
    --------
    dag_longest_path_length

    """
    if not G:
        return []

    if topo_order is None:
        topo_order = nx.topological_sort(G)

    dist = {}  # stores {v : (length, u)}
    for v in topo_order:
        us = [
            (
                dist[u][0]
                + (
                    max(data.values(), key=lambda x: x.get(weight, default_weight))
                    if G.is_multigraph()
                    else data
                ).get(weight, default_weight),
                u,
            )
            for u, data in G.pred[v].items()
        ]

        # Use the best predecessor if there is one and its distance is
        # non-negative, otherwise terminate.
        maxu = max(us, key=lambda x: x[0]) if us else (0, v)
        dist[v] = maxu if maxu[0] >= 0 else (0, v)

    u = None
    v = max(dist, key=lambda x: dist[x][0])
    path = []
    while u != v:
        path.append(v)
        u = v
        v = dist[v][1]

    path.reverse()
    return path


@not_implemented_for("undirected")
@nx._dispatchable(edge_attrs={"weight": "default_weight"})
def dag_longest_path_length(G, weight="weight", default_weight=1):
    """Returns the longest path length in a DAG

    Parameters
    ----------
    G : NetworkX DiGraph
        A directed acyclic graph (DAG)

    weight : string, optional
        Edge data key to use for weight

    default_weight : int, optional
        The weight of edges that do not have a weight attribute

    Returns
    -------
    int
        Longest path length

    Raises
    ------
    NetworkXNotImplemented
        If `G` is not directed

    Examples
    --------
    >>> DG = nx.DiGraph(
    ...     [(0, 1, {"cost": 1}), (1, 2, {"cost": 1}), (0, 2, {"cost": 42})]
    ... )
    >>> list(nx.all_simple_paths(DG, 0, 2))
    [[0, 1, 2], [0, 2]]
    >>> nx.dag_longest_path_length(DG)
    2
    >>> nx.dag_longest_path_length(DG, weight="cost")
    42

    See also
    --------
    dag_longest_path
    """
    path = nx.dag_longest_path(G, weight, default_weight)
    path_length = 0
    if G.is_multigraph():
        for u, v in pairwise(path):
            i = max(G[u][v], key=lambda x: G[u][v][x].get(weight, default_weight))
            path_length += G[u][v][i].get(weight, default_weight)
    else:
        for u, v in pairwise(path):
            path_length += G[u][v].get(weight, default_weight)

    return path_length


@nx._dispatchable
def root_to_leaf_paths(G):
    """Yields root-to-leaf paths in a directed acyclic graph.

    `G` must be a directed acyclic graph. If not, the behavior of this
    function is undefined. A "root" in this graph is a node of in-degree
    zero and a "leaf" a node of out-degree zero.

    When invoked, this function iterates over each path from any root to
    any leaf. A path is a list of nodes.

    """
    roots = (v for v, d in G.in_degree() if d == 0)
    leaves = (v for v, d in G.out_degree() if d == 0)
    all_paths = partial(nx.all_simple_paths, G)
    # TODO In Python 3, this would be better as `yield from ...`.
    return chaini(starmap(all_paths, product(roots, leaves)))


@not_implemented_for("multigraph")
@not_implemented_for("undirected")
@nx._dispatchable(returns_graph=True)
def dag_to_branching(G):
    """Returns a branching representing all (overlapping) paths from
    root nodes to leaf nodes in the given directed acyclic graph.

    As described in :mod:`networkx.algorithms.tree.recognition`, a
    *branching* is a directed forest in which each node has at most one
    parent. In other words, a branching is a disjoint union of
    *arborescences*. For this function, each node of in-degree zero in
    `G` becomes a root of one of the arborescences, and there will be
    one leaf node for each distinct path from that root to a leaf node
    in `G`.

    Each node `v` in `G` with *k* parents becomes *k* distinct nodes in
    the returned branching, one for each parent, and the sub-DAG rooted
    at `v` is duplicated for each copy. The algorithm then recurses on
    the children of each copy of `v`.

    Parameters
    ----------
    G : NetworkX graph
        A directed acyclic graph.

    Returns
    -------
    DiGraph
        The branching in which there is a bijection between root-to-leaf
        paths in `G` (in which multiple paths may share the same leaf)
        and root-to-leaf paths in the branching (in which there is a
        unique path from a root to a leaf).

        Each node has an attribute 'source' whose value is the original
        node to which this node corresponds. No other graph, node, or
        edge attributes are copied into this new graph.

    Raises
    ------
    NetworkXNotImplemented
        If `G` is not directed, or if `G` is a multigraph.

    HasACycle
        If `G` is not acyclic.

    Examples
    --------
    To examine which nodes in the returned branching were produced by
    which original node in the directed acyclic graph, we can collect
    the mapping from source node to new nodes into a dictionary. For
    example, consider the directed diamond graph::

        >>> from collections import defaultdict
        >>> from operator import itemgetter
        >>>
        >>> G = nx.DiGraph(nx.utils.pairwise("abd"))
        >>> G.add_edges_from(nx.utils.pairwise("acd"))
        >>> B = nx.dag_to_branching(G)
        >>>
        >>> sources = defaultdict(set)
        >>> for v, source in B.nodes(data="source"):
        ...     sources[source].add(v)
        >>> len(sources["a"])
        1
        >>> len(sources["d"])
        2

    To copy node attributes from the original graph to the new graph,
    you can use a dictionary like the one constructed in the above
    example::

        >>> for source, nodes in sources.items():
        ...     for v in nodes:
        ...         B.nodes[v].update(G.nodes[source])

    Notes
    -----
    This function is not idempotent in the sense that the node labels in
    the returned branching may be uniquely generated each time the
    function is invoked. In fact, the node labels may not be integers;
    in order to relabel the nodes to be more readable, you can use the
    :func:`networkx.convert_node_labels_to_integers` function.

    The current implementation of this function uses
    :func:`networkx.prefix_tree`, so it is subject to the limitations of
    that function.

    """
    if has_cycle(G):
        msg = "dag_to_branching is only defined for acyclic graphs"
        raise nx.HasACycle(msg)
    paths = root_to_leaf_paths(G)
    B = nx.prefix_tree(paths)
    # Remove the synthetic `root`(0) and `NIL`(-1) nodes from the tree
    B.remove_node(0)
    B.remove_node(-1)
    return B


@not_implemented_for("undirected")
@nx._dispatchable
def compute_v_structures(G):
    """Yields 3-node tuples that represent the v-structures in `G`.

    .. deprecated:: 3.4

       `compute_v_structures` actually yields colliders. It will be removed in
       version 3.6. Use `nx.dag.v_structures` or `nx.dag.colliders` instead.

    Colliders are triples in the directed acyclic graph (DAG) where two parent nodes
    point to the same child node. V-structures are colliders where the two parent
    nodes are not adjacent. In a causal graph setting, the parents do not directly
    depend on each other, but conditioning on the child node provides an association.

    Parameters
    ----------
    G : graph
        A networkx `~networkx.DiGraph`.

    Yields
    ------
    A 3-tuple representation of a v-structure
        Each v-structure is a 3-tuple with the parent, collider, and other parent.

    Raises
    ------
    NetworkXNotImplemented
        If `G` is an undirected graph.

    Examples
    --------
    >>> G = nx.DiGraph([(1, 2), (0, 4), (3, 1), (2, 4), (0, 5), (4, 5), (1, 5)])
    >>> nx.is_directed_acyclic_graph(G)
    True
    >>> list(nx.compute_v_structures(G))
    [(0, 4, 2), (0, 5, 4), (0, 5, 1), (4, 5, 1)]

    See Also
    --------
    v_structures
    colliders

    Notes
    -----
    This function was written to be used on DAGs, however it works on cyclic graphs
    too. Since colliders are referred to in the cyclic causal graph literature
    [2]_ we allow cyclic graphs in this function. It is suggested that you test if
    your input graph is acyclic as in the example if you want that property.

    References
    ----------
    .. [1]  `Pearl's PRIMER <https://bayes.cs.ucla.edu/PRIMER/primer-ch2.pdf>`_
            Ch-2 page 50: v-structures def.
    .. [2] A Hyttinen, P.O. Hoyer, F. Eberhardt, M J ̈arvisalo, (2013)
           "Discovering cyclic causal models with latent variables:
           a general SAT-based procedure", UAI'13: Proceedings of the Twenty-Ninth
           Conference on Uncertainty in Artificial Intelligence, pg 301–310,
           `doi:10.5555/3023638.3023669 <https://dl.acm.org/doi/10.5555/3023638.3023669>`_
    """
    import warnings

    warnings.warn(
        (
            "\n\n`compute_v_structures` actually yields colliders. It will be\n"
            "removed in version 3.6. Use `nx.dag.v_structures` or `nx.dag.colliders`\n"
            "instead.\n"
        ),
        category=DeprecationWarning,
        stacklevel=5,
    )

    return colliders(G)


@not_implemented_for("undirected")
@nx._dispatchable
def v_structures(G):
    """Yields 3-node tuples that represent the v-structures in `G`.

    Colliders are triples in the directed acyclic graph (DAG) where two parent nodes
    point to the same child node. V-structures are colliders where the two parent
    nodes are not adjacent. In a causal graph setting, the parents do not directly
    depend on each other, but conditioning on the child node provides an association.

    Parameters
    ----------
    G : graph
        A networkx `~networkx.DiGraph`.

    Yields
    ------
    A 3-tuple representation of a v-structure
        Each v-structure is a 3-tuple with the parent, collider, and other parent.

    Raises
    ------
    NetworkXNotImplemented
        If `G` is an undirected graph.

    Examples
    --------
    >>> G = nx.DiGraph([(1, 2), (0, 4), (3, 1), (2, 4), (0, 5), (4, 5), (1, 5)])
    >>> nx.is_directed_acyclic_graph(G)
    True
    >>> list(nx.dag.v_structures(G))
    [(0, 4, 2), (0, 5, 1), (4, 5, 1)]

    See Also
    --------
    colliders

    Notes
    -----
    This function was written to be used on DAGs, however it works on cyclic graphs
    too. Since colliders are referred to in the cyclic causal graph literature
    [2]_ we allow cyclic graphs in this function. It is suggested that you test if
    your input graph is acyclic as in the example if you want that property.

    References
    ----------
    .. [1]  `Pearl's PRIMER <https://bayes.cs.ucla.edu/PRIMER/primer-ch2.pdf>`_
            Ch-2 page 50: v-structures def.
    .. [2] A Hyttinen, P.O. Hoyer, F. Eberhardt, M J ̈arvisalo, (2013)
           "Discovering cyclic causal models with latent variables:
           a general SAT-based procedure", UAI'13: Proceedings of the Twenty-Ninth
           Conference on Uncertainty in Artificial Intelligence, pg 301–310,
           `doi:10.5555/3023638.3023669 <https://dl.acm.org/doi/10.5555/3023638.3023669>`_
    """
    for p1, c, p2 in colliders(G):
        if not (G.has_edge(p1, p2) or G.has_edge(p2, p1)):
            yield (p1, c, p2)


@not_implemented_for("undirected")
@nx._dispatchable
def colliders(G):
    """Yields 3-node tuples that represent the colliders in `G`.

    In a Directed Acyclic Graph (DAG), if you have three nodes A, B, and C, and
    there are edges from A to C and from B to C, then C is a collider [1]_ . In
    a causal graph setting, this means that both events A and B are "causing" C,
    and conditioning on C provide an association between A and B even if
    no direct causal relationship exists between A and B.

    Parameters
    ----------
    G : graph
        A networkx `~networkx.DiGraph`.

    Yields
    ------
    A 3-tuple representation of a collider
        Each collider is a 3-tuple with the parent, collider, and other parent.

    Raises
    ------
    NetworkXNotImplemented
        If `G` is an undirected graph.

    Examples
    --------
    >>> G = nx.DiGraph([(1, 2), (0, 4), (3, 1), (2, 4), (0, 5), (4, 5), (1, 5)])
    >>> nx.is_directed_acyclic_graph(G)
    True
    >>> list(nx.dag.colliders(G))
    [(0, 4, 2), (0, 5, 4), (0, 5, 1), (4, 5, 1)]

    See Also
    --------
    v_structures

    Notes
    -----
    This function was written to be used on DAGs, however it works on cyclic graphs
    too. Since colliders are referred to in the cyclic causal graph literature
    [2]_ we allow cyclic graphs in this function. It is suggested that you test if
    your input graph is acyclic as in the example if you want that property.

    References
    ----------
    .. [1] `Wikipedia: Collider in causal graphs <https://en.wikipedia.org/wiki/Collider_(statistics)>`_
    .. [2] A Hyttinen, P.O. Hoyer, F. Eberhardt, M J ̈arvisalo, (2013)
           "Discovering cyclic causal models with latent variables:
           a general SAT-based procedure", UAI'13: Proceedings of the Twenty-Ninth
           Conference on Uncertainty in Artificial Intelligence, pg 301–310,
           `doi:10.5555/3023638.3023669 <https://dl.acm.org/doi/10.5555/3023638.3023669>`_
    """
    for node in G.nodes:
        for p1, p2 in combinations(G.predecessors(node), 2):
            yield (p1, node, p2)
