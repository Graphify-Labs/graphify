"""
========================
Cycle finding algorithms
========================
"""

from collections import Counter, defaultdict
from itertools import combinations, product
from math import inf

import networkx as nx
from networkx.utils import not_implemented_for, pairwise

__all__ = [
    "cycle_basis",
    "simple_cycles",
    "recursive_simple_cycles",
    "find_cycle",
    "minimum_cycle_basis",
    "chordless_cycles",
    "girth",
]


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def cycle_basis(G, root=None):
    """Returns a list of cycles which form a basis for cycles of G.

    A basis for cycles of a network is a minimal collection of
    cycles such that any cycle in the network can be written
    as a sum of cycles in the basis.  Here summation of cycles
    is defined as "exclusive or" of the edges. Cycle bases are
    useful, e.g. when deriving equations for electric circuits
    using Kirchhoff's Laws.

    Parameters
    ----------
    G : NetworkX Graph
    root : node, optional
       Specify starting node for basis.

    Returns
    -------
    A list of cycle lists.  Each cycle list is a list of nodes
    which forms a cycle (loop) in G.

    Examples
    --------
    >>> G = nx.Graph()
    >>> nx.add_cycle(G, [0, 1, 2, 3])
    >>> nx.add_cycle(G, [0, 3, 4, 5])
    >>> nx.cycle_basis(G, 0)
    [[3, 4, 5, 0], [1, 2, 3, 0]]

    Notes
    -----
    This is adapted from algorithm CACM 491 [1]_.

    References
    ----------
    .. [1] Paton, K. An algorithm for finding a fundamental set of
       cycles of a graph. Comm. ACM 12, 9 (Sept 1969), 514-518.

    See Also
    --------
    simple_cycles
    minimum_cycle_basis
    """
    gnodes = dict.fromkeys(G)  # set-like object that maintains node order
    cycles = []
    while gnodes:  # loop over connected components
        if root is None:
            root = gnodes.popitem()[0]
        stack = [root]
        pred = {root: root}
        used = {root: set()}
        while stack:  # walk the spanning tree finding cycles
            z = stack.pop()  # use last-in so cycles easier to find
            zused = used[z]
            for nbr in G[z]:
                if nbr not in used:  # new node
                    pred[nbr] = z
                    stack.append(nbr)
                    used[nbr] = {z}
                elif nbr == z:  # self loops
                    cycles.append([z])
                elif nbr not in zused:  # found a cycle
                    pn = used[nbr]
                    cycle = [nbr, z]
                    p = pred[z]
                    while p not in pn:
                        cycle.append(p)
                        p = pred[p]
                    cycle.append(p)
                    cycles.append(cycle)
                    used[nbr].add(z)
        for node in pred:
            gnodes.pop(node, None)
        root = None
    return cycles


@nx._dispatchable
def simple_cycles(G, length_bound=None):
    """Find simple cycles (elementary circuits) of a graph.

    A "simple cycle", or "elementary circuit", is a closed path where
    no node appears twice.  In a directed graph, two simple cycles are distinct
    if they are not cyclic permutations of each other.  In an undirected graph,
    two simple cycles are distinct if they are not cyclic permutations of each
    other nor of the other's reversal.

    Optionally, the cycles are bounded in length.  In the unbounded case, we use
    a nonrecursive, iterator/generator version of Johnson's algorithm [1]_.  In
    the bounded case, we use a version of the algorithm of Gupta and
    Suzumura [2]_. There may be better algorithms for some cases [3]_ [4]_ [5]_.

    The algorithms of Johnson, and Gupta and Suzumura, are enhanced by some
    well-known preprocessing techniques.  When `G` is directed, we restrict our
    attention to strongly connected components of `G`, generate all simple cycles
    containing a certain node, remove that node, and further decompose the
    remainder into strongly connected components.  When `G` is undirected, we
    restrict our attention to biconnected components, generate all simple cycles
    containing a particular edge, remove that edge, and further decompose the
    remainder into biconnected components.

    Note that multigraphs are supported by this function -- and in undirected
    multigraphs, a pair of parallel edges is considered a cycle of length 2.
    Likewise, self-loops are considered to be cycles of length 1.  We define
    cycles as sequences of nodes; so the presence of loops and parallel edges
    does not change the number of simple cycles in a graph.

    Parameters
    ----------
    G : NetworkX Graph
       A networkx graph. Undirected, directed, and multigraphs are all supported.

    length_bound : int or None, optional (default=None)
       If `length_bound` is an int, generate all simple cycles of `G` with length at
       most `length_bound`.  Otherwise, generate all simple cycles of `G`.

    Yields
    ------
    list of nodes
       Each cycle is represented by a list of nodes along the cycle.

    Examples
    --------
    >>> G = nx.DiGraph([(0, 0), (0, 1), (0, 2), (1, 2), (2, 0), (2, 1), (2, 2)])
    >>> sorted(nx.simple_cycles(G))
    [[0], [0, 1, 2], [0, 2], [1, 2], [2]]

    To filter the cycles so that they don't include certain nodes or edges,
    copy your graph and eliminate those nodes or edges before calling.
    For example, to exclude self-loops from the above example:

    >>> H = G.copy()
    >>> H.remove_edges_from(nx.selfloop_edges(G))
    >>> sorted(nx.simple_cycles(H))
    [[0, 1, 2], [0, 2], [1, 2]]

    Notes
    -----
    When `length_bound` is None, the time complexity is $O((n+e)(c+1))$ for $n$
    nodes, $e$ edges and $c$ simple circuits.  Otherwise, when ``length_bound > 1``,
    the time complexity is $O((c+n)(k-1)d^k)$ where $d$ is the average degree of
    the nodes of `G` and $k$ = `length_bound`.

    Raises
    ------
    ValueError
        when ``length_bound < 0``.

    References
    ----------
    .. [1] Finding all the elementary circuits of a directed graph.
       D. B. Johnson, SIAM Journal on Computing 4, no. 1, 77-84, 1975.
       https://doi.org/10.1137/0204007
    .. [2] Finding All Bounded-Length Simple Cycles in a Directed Graph
       A. Gupta and T. Suzumura https://arxiv.org/abs/2105.10094
    .. [3] Enumerating the cycles of a digraph: a new preprocessing strategy.
       G. Loizou and P. Thanish, Information Sciences, v. 27, 163-182, 1982.
    .. [4] A search strategy for the elementary cycles of a directed graph.
       J.L. Szwarcfiter and P.E. Lauer, BIT NUMERICAL MATHEMATICS,
       v. 16, no. 2, 192-204, 1976.
    .. [5] Optimal Listing of Cycles and st-Paths in Undirected Graphs
        R. Ferreira and R. Grossi and A. Marino and N. Pisanti and R. Rizzi and
        G. Sacomoto https://arxiv.org/abs/1205.2766

    See Also
    --------
    cycle_basis
    chordless_cycles
    """

    if length_bound is not None:
        if length_bound == 0:
            return
        elif length_bound < 0:
            raise ValueError("length bound must be non-negative")

    directed = G.is_directed()
    yield from ([v] for v, Gv in G.adj.items() if v in Gv)

    if length_bound is not None and length_bound == 1:
        return

    if G.is_multigraph() and not directed:
        visited = set()
        for u, Gu in G.adj.items():
            multiplicity = ((v, len(Guv)) for v, Guv in Gu.items() if v in visited)
            yield from ([u, v] for v, m in multiplicity if m > 1)
            visited.add(u)

    # explicitly filter out loops; implicitly filter out parallel edges
    if directed:
        G = nx.DiGraph((u, v) for u, Gu in G.adj.items() for v in Gu if v != u)
    else:
        G = nx.Graph((u, v) for u, Gu in G.adj.items() for v in Gu if v != u)

    # this case is not strictly necessary but improves performance
    if length_bound is not None and length_bound == 2:
        if directed:
            visited = set()
            for u, Gu in G.adj.items():
                yield from (
                    [v, u] for v in visited.intersection(Gu) if G.has_edge(v, u)
                )
                visited.add(u)
        return

    if directed:
        yield from _directed_cycle_search(G, length_bound)
    else:
        yield from _undirected_cycle_search(G, length_bound)


def _directed_cycle_search(G, length_bound):
    """A dispatch function for `simple_cycles` for directed graphs.

    We generate all cycles of G through binary partition.

        1. Pick a node v in G which belongs to at least one cycle
            a. Generate all cycles of G which contain the node v.
            b. Recursively generate all cycles of G \\ v.

    This is accomplished through the following:

        1. Compute the strongly connected components SCC of G.
        2. Select and remove a biconnected component C from BCC.  Select a
           non-tree edge (u, v) of a depth-first search of G[C].
        3. For each simple cycle P containing v in G[C], yield P.
        4. Add the biconnected components of G[C \\ v] to BCC.

    If the parameter length_bound is not None, then step 3 will be limited to
    simple cycles of length at most length_bound.

    Parameters
    ----------
    G : NetworkX DiGraph
       A directed graph

    length_bound : int or None
       If length_bound is an int, generate all simple cycles of G with length at most length_bound.
       Otherwise, generate all simple cycles of G.

    Yields
    ------
    list of nodes
       Each cycle is represented by a list of nodes along the cycle.
    """

    scc = nx.strongly_connected_components
    components = [c for c in scc(G) if len(c) >= 2]
    while components:
        c = components.pop()
        Gc = G.subgraph(c)
        v = next(iter(c))
        if length_bound is None:
            yield from _johnson_cycle_search(Gc, [v])
        else:
            yield from _bounded_cycle_search(Gc, [v], length_bound)
        # delete v after searching G, to make sure we can find v
        G.remove_node(v)
        components.extend(c for c in scc(Gc) if len(c) >= 2)


def _undirected_cycle_search(G, length_bound):
    """A dispatch function for `simple_cycles` for undirected graphs.

    We generate all cycles of G through binary partition.

        1. Pick an edge (u, v) in G which belongs to at least one cycle
            a. Generate all cycles of G which contain the edge (u, v)
            b. Recursively generate all cycles of G \\ (u, v)

    This is accomplished through the following:

        1. Compute the biconnected components BCC of G.
        2. Select and remove a biconnected component C from BCC.  Select a
           non-tree edge (u, v) of a depth-first search of G[C].
        3. For each (v -> u) path P remaining in G[C] \\ (u, v), yield P.
        4. Add the biconnected components of G[C] \\ (u, v) to BCC.

    If the parameter length_bound is not None, then step 3 will be limited to simple paths
    of length at most length_bound.

    Parameters
    ----------
    G : NetworkX Graph
       An undirected graph

    length_bound : int or None
       If length_bound is an int, generate all simple cycles of G with length at most length_bound.
       Otherwise, generate all simple cycles of G.

    Yields
    ------
    list of nodes
       Each cycle is represented by a list of nodes along the cycle.
    """

    bcc = nx.biconnected_components
    components = [c for c in bcc(G) if len(c) >= 3]
    while components:
        c = components.pop()
        Gc = G.subgraph(c)
        uv = list(next(iter(Gc.edges)))
        G.remove_edge(*uv)
        # delete (u, v) before searching G, to avoid fake 3-cycles [u, v, u]
        if length_bound is None:
            yield from _johnson_cycle_search(Gc, uv)
        else:
            yield from _bounded_cycle_search(Gc, uv, length_bound)
        components.extend(c for c in bcc(Gc) if len(c) >= 3)


class _NeighborhoodCache(dict):
    """Very lightweight graph wrapper which caches neighborhoods as list.

    This dict subclass uses the __missing__ functionality to query graphs for
    their neighborhoods, and store the result as a list.  This is used to avoid
    the performance penalty incurred by subgraph views.
    """

    def __init__(self, G):
        self.G = G

    def __missing__(self, v):
        Gv = self[v] = list(self.G[v])
        return Gv


def _johnson_cycle_search(G, path):
    """The main loop of the cycle-enumeration algorithm of Johnson.

    Parameters
    ----------
    G : NetworkX Graph or DiGraph
       A graph

    path : list
       A cycle prefix.  All cycles generated will begin with this prefix.

    Yields
    ------
    list of nodes
       Each cycle is represented by a list of nodes along the cycle.

    References
    ----------
        .. [1] Finding all the elementary circuits of a directed graph.
       D. B. Johnson, SIAM Journal on Computing 4, no. 1, 77-84, 1975.
       https://doi.org/10.1137/0204007

    """

    G = _NeighborhoodCache(G)
    blocked = set(path)
    B = defaultdict(set)  # graph portions that yield no elementary circuit
    start = path[0]
    stack = [iter(G[path[-1]])]
    closed = [False]
    while stack:
        nbrs = stack[-1]
        for w in nbrs:
            if w == start:
                yield path[:]
                closed[-1] = True
            elif w not in blocked:
                path.append(w)
                closed.append(False)
                stack.append(iter(G[w]))
                blocked.add(w)
                break
        else:  # no more nbrs
            stack.pop()
            v = path.pop()
            if closed.pop():
                if closed:
                    closed[-1] = True
                unblock_stack = {v}
                while unblock_stack:
                    u = unblock_stack.pop()
                    if u in blocked:
                        blocked.remove(u)
                        unblock_stack.update(B[u])
                        B[u].clear()
            else:
                for w in G[v]:
                    B[w].add(v)


def _bounded_cycle_search(G, path, length_bound):
    """The main loop of the cycle-enumeration algorithm of Gupta and Suzumura.

    Parameters
    ----------
    G : NetworkX Graph or DiGraph
       A graph

    path : list
       A cycle prefix.  All cycles generated will begin with this prefix.

    length_bound: int
        A length bound.  All cycles generated will have length at most length_bound.

    Yields
    ------
    list of nodes
       Each cycle is represented by a list of nodes along the cycle.

    References
    ----------
    .. [1] Finding All Bounded-Length Simple Cycles in a Directed Graph
       A. Gupta and T. Suzumura https://arxiv.org/abs/2105.10094

    """
    G = _NeighborhoodCache(G)
    lock = {v: 0 for v in path}
    B = defaultdict(set)
    start = path[0]
    stack = [iter(G[path[-1]])]
    blen = [length_bound]
    while stack:
        nbrs = stack[-1]
        for w in nbrs:
            if w == start:
                yield path[:]
                blen[-1] = 1
            elif len(path) < lock.get(w, length_bound):
                path.append(w)
                blen.append(length_bound)
                lock[w] = len(path)
                stack.append(iter(G[w]))
                break
        else:
            stack.pop()
            v = path.pop()
            bl = blen.pop()
            if blen:
                blen[-1] = min(blen[-1], bl)
            if bl < length_bound:
                relax_stack = [(bl, v)]
                while relax_stack:
                    bl, u = relax_stack.pop()
                    if lock.get(u, length_bound) < length_bound - bl + 1:
                        lock[u] = length_bound - bl + 1
                        relax_stack.extend((bl + 1, w) for w in B[u].difference(path))
            else:
                for w in G[v]:
                    B[w].add(v)


@nx._dispatchable
def chordless_cycles(G, length_bound=None):
    """Find simple chordless cycles of a graph.

    A `simple cycle` is a closed path where no node appears twice.  In a simple
    cycle, a `chord` is an additional edge between two nodes in the cycle.  A
    `chordless cycle` is a simple cycle without chords.  Said differently, a
    chordless cycle is a cycle C in a graph G where the number of edges in the
    induced graph G[C] is equal to the length of `C`.

    Note that some care must be taken in the case that G is not a simple graph
    nor a simple digraph.  Some authors limit the definition of chordless cycles
    to have a prescribed minimum length; we do not.

        1. We interpret self-loops to be chordless cycles, except in multigraphs
           with multiple loops in parallel.  Likewise, in a chordless cycle of
           length greater than 1, there can be no nodes with self-loops.

        2. We interpret directed two-cycles to be chordless cycles, except in
           multi-digraphs when any edge in a two-cycle has a parallel copy.

        3. We interpret parallel pairs of undirected edges as two-cycles, except
           when a third (or more) parallel edge exists between the two nodes.

        4. Generalizing the above, edges with parallel clones may not occur in
           chordless cycles.

    In a directed graph, two chordless cycles are distinct if they are not
    cyclic permutations of each other.  In an undirected graph, two chordless
    cycles are distinct if they are not cyclic permutations of each other nor of
    the other's reversal.

    Optionally, the cycles are bounded in length.

    We use an algorithm strongly inspired by that of Dias et al [1]_.  It has
    been modified in the following ways:

        1. Recursion is avoided, per Python's limitations

        2. The labeling function is not necessary, because the starting paths
            are chosen (and deleted from the host graph) to prevent multiple
            occurrences of the same path

        3. The search is optionally bounded at a specified length

        4. Support for directed graphs is provided by extending cycles along
            forward edges, and blocking nodes along forward and reverse edges

        5. Support for multigraphs is provided by omitting digons from the set
            of forward edges

    Parameters
    ----------
    G : NetworkX DiGraph
       A directed graph

    length_bound : int or None, optional (default=None)
       If length_bound is an int, generate all simple cycles of G with length at
       most length_bound.  Otherwise, generate all simple cycles of G.

    Yields
    ------
    list of nodes
       Each cycle is represented by a list of nodes along the cycle.

    Examples
    --------
    >>> sorted(list(nx.chordless_cycles(nx.complete_graph(4))))
    [[1, 0, 2], [1, 0, 3], [2, 0, 3], [2, 1, 3]]

    Notes
    -----
    When length_bound is None, and the graph is simple, the time complexity is
    $O((n+e)(c+1))$ for $n$ nodes, $e$ edges and $c$ chordless cycles.

    Raises
    ------
    ValueError
        when length_bound < 0.

    References
    ----------
    .. [1] Efficient enumeration of chordless cycles
       E. Dias and D. Castonguay and H. Longo and W.A.R. Jradi
       https://arxiv.org/abs/1309.1051

    See Also
    --------
    simple_cycles
    """

    if length_bound is not None:
        if length_bound == 0:
            return
        elif length_bound < 0:
            raise ValueError("length bound must be non-negative")

    directed = G.is_directed()
    multigraph = G.is_multigraph()

    if multigraph:
        yield from ([v] for v, Gv in G.adj.items() if len(Gv.get(v, ())) == 1)
    else:
        yield from ([v] for v, Gv in G.adj.items() if v in Gv)

    if length_bound is not None and length_bound == 1:
        return

    # Nodes with loops cannot belong to longer cycles.  Let's delete them here.
    # also, we implicitly reduce the multiplicity of edges down to 1 in the case
    # of multiedges.
    if directed:
        F = nx.DiGraph((u, v) for u, Gu in G.adj.items() if u not in Gu for v in Gu)
        B = F.to_undirected(as_view=False)
    else:
        F = nx.Graph((u, v) for u, Gu in G.adj.items() if u not in Gu for v in Gu)
        B = None

    # If we're given a multigraph, we have a few cases to consider with parallel
    # edges.
    #
    # 1. If we have 2 or more edges in parallel between the nodes (u, v), we
    #    must not construct longer cycles along (u, v).
    # 2. If G is not directed, then a pair of parallel edges between (u, v) is a
    #    chordless cycle unless there exists a third (or more) parallel edge.
    # 3. If G is directed, then parallel edges do not form cycles, but do
    #    preclude back-edges from forming cycles (handled in the next section),
    #    Thus, if an edge (u, v) is duplicated and the reverse (v, u) is also
    #    present, then we remove both from F.
    #
    # In directed graphs, we need to consider both directions that edges can
    # take, so iterate over all edges (u, v) and possibly (v, u).  In undirected
    # graphs, we need to be a little careful to only consider every edge once,
    # so we use a "visited" set to emulate node-order comparisons.

    if multigraph:
        if not directed:
            B = F.copy()
            visited = set()
        for u, Gu in G.adj.items():
            if directed:
                multiplicity = ((v, len(Guv)) for v, Guv in Gu.items())
                for v, m in multiplicity:
                    if m > 1:
                        F.remove_edges_from(((u, v), (v, u)))
            else:
                multiplicity = ((v, len(Guv)) for v, Guv in Gu.items() if v in visited)
                for v, m in multiplicity:
                    if m == 2:
                        yield [u, v]
                    if m > 1:
                        F.remove_edge(u, v)
                visited.add(u)

    # If we're given a directed graphs, we need to think about digons.  If we
    # have two edges (u, v) and (v, u), then that's a two-cycle.  If either edge
    # was duplicated above, then we removed both from F.  So, any digons we find
    # here are chordless.  After finding digons, we remove their edges from F
    # to avoid traversing them in the search for chordless cycles.
    if directed:
        for u, Fu in F.adj.items():
            digons = [[u, v] for v in Fu if F.has_edge(v, u)]
            yield from digons
            F.remove_edges_from(digons)
            F.remove_edges_from(e[::-1] for e in digons)

    if length_bound is not None and length_bound == 2:
        return

    # Now, we prepare to search for cycles.  We have removed all cycles of
    # lengths 1 and 2, so F is a simple graph or simple digraph.  We repeatedly
    # separate digraphs into their strongly connected components, and undirected
    # graphs into their biconnected components.  For each component, we pick a
    # node v, search for chordless cycles based at each "stem" (u, v, w), and
    # then remove v from that component before separating the graph again.
    if directed:
        separate = nx.strongly_connected_components

        # Directed stems look like (u -> v -> w), so we use the product of
        # predecessors of v with successors of v.
        def stems(C, v):
            for u, w in product(C.pred[v], C.succ[v]):
                if not G.has_edge(u, w):  # omit stems with acyclic chords
                    yield [u, v, w], F.has_edge(w, u)

    else:
        separate = nx.biconnected_components

        # Undirected stems look like (u ~ v ~ w), but we must not also search
        # (w ~ v ~ u), so we use combinations of v's neighbors of length 2.
        def stems(C, v):
            yield from (([u, v, w], F.has_edge(w, u)) for u, w in combinations(C[v], 2))

    components = [c for c in separate(F) if len(c) > 2]
    while components:
        c = components.pop()
        v = next(iter(c))
        Fc = F.subgraph(c)
        Fcc = Bcc = None
        for S, is_triangle in stems(Fc, v):
            if is_triangle:
                yield S
            else:
                if Fcc is None:
                    Fcc = _NeighborhoodCache(Fc)
                    Bcc = Fcc if B is None else _NeighborhoodCache(B.subgraph(c))
                yield from _chordless_cycle_search(Fcc, Bcc, S, length_bound)

        components.extend(c for c in separate(F.subgraph(c - {v})) if len(c) > 2)


def _chordless_cycle_search(F, B, path, length_bound):
    """The main loop for chordless cycle enumeration.

    This algorithm is strongly inspired by that of Dias et al [1]_.  It has been
    modified in the following ways:

        1. Recursion is avoided, per Python's limitations

        2. The labeling function is not necessary, because the starting paths
            are chosen (and deleted from the host graph) to prevent multiple
            occurrences of the same path

        3. The search is optionally bounded at a specified length

        4. Support for directed graphs is provided by extending cycles along
            forward edges, and blocking nodes along forward and reverse edges

        5. Support for multigraphs is provided by omitting digons from the set
            of forward edges

    Parameters
    ----------
    F : _NeighborhoodCache
       A graph of forward edges to follow in constructing cycles

    B : _NeighborhoodCache
       A graph of blocking edges to prevent the production of chordless cycles

    path : list
       A cycle prefix.  All cycles generated will begin with this prefix.

    length_bound : int
       A length bound.  All cycles generated will have length at most length_bound.


    Yields
    ------
    list of nodes
       Each cycle is represented by a list of nodes along the cycle.

    References
    ----------
    .. [1] Efficient enumeration of chordless cycles
       E. Dias and D. Castonguay and H. Longo and W.A.R. Jradi
       https://arxiv.org/abs/1309.1051

    """
    blocked = defaultdict(int)
    target = path[0]
    blocked[path[1]] = 1
    for w in path[1:]:
        for v in B[w]:
            blocked[v] += 1

    stack = [iter(F[path[2]])]
    while stack:
        nbrs = stack[-1]
        for w in nbrs:
            if blocked[w] == 1 and (length_bound is None or len(path) < length_bound):
                Fw = F[w]
                if target in Fw:
                    yield path + [w]
                else:
                    Bw = B[w]
                    if target in Bw:
                        continue
                    for v in Bw:
                        blocked[v] += 1
                    path.append(w)
                    stack.append(iter(Fw))
                    break
        else:
            stack.pop()
            for v in B[path.pop()]:
                blocked[v] -= 1


@not_implemented_for("undirected")
@nx._dispatchable(mutates_input=True)
def recursive_simple_cycles(G):
    """Find simple cycles (elementary circuits) of a directed graph.

    A `simple cycle`, or `elementary circuit`, is a closed path where
    no node appears twice. Two elementary circuits are distinct if they
    are not cyclic permutations of each other.

    This version uses a recursive algorithm to build a list of cycles.
    You should probably use the iterator version called simple_cycles().
    Warning: This recursive version uses lots of RAM!
    It appears in NetworkX for pedagogical value.

    Parameters
    ----------
    G : NetworkX DiGraph
       A directed graph

    Returns
    -------
    A list of cycles, where each cycle is represented by a list of nodes
    along the cycle.

    Example:

    >>> edges = [(0, 0), (0, 1), (0, 2), (1, 2), (2, 0), (2, 1), (2, 2)]
    >>> G = nx.DiGraph(edges)
    >>> nx.recursive_simple_cycles(G)
    [[0], [2], [0, 1, 2], [0, 2], [1, 2]]

    Notes
    -----
    The implementation follows pp. 79-80 in [1]_.

    The time complexity is $O((n+e)(c+1))$ for $n$ nodes, $e$ edges and $c$
    elementary circuits.

    References
    ----------
    .. [1] Finding all the elementary circuits of a directed graph.
       D. B. Johnson, SIAM Journal on Computing 4, no. 1, 77-84, 1975.
       https://doi.org/10.1137/0204007

    See Also
    --------
    simple_cycles, cycle_basis
    """

    # Jon Olav Vik, 2010-08-09
    def _unblock(thisnode):
        """Recursively unblock and remove nodes from B[thisnode]."""
        if blocked[thisnode]:
            blocked[thisnode] = False
            while B[thisnode]:
                _unblock(B[thisnode].pop())

    def circuit(thisnode, startnode, component):
        closed = False  # set to True if elementary path is closed
        path.append(thisnode)
        blocked[thisnode] = True
        for nextnode in component[thisnode]:  # direct successors of thisnode
            if nextnode == startnode:
                result.append(path[:])
                closed = True
            elif not blocked[nextnode]:
                if circuit(nextnode, startnode, component):
                    closed = True
        if closed:
            _unblock(thisnode)
        else:
            for nextnode in component[thisnode]:
                if thisnode not in B[nextnode]:  # TODO: use set for speedup?
                    B[nextnode].append(thisnode)
        path.pop()  # remove thisnode from path
        return closed

    path = []  # stack of nodes in current path
    blocked = defaultdict(bool)  # vertex: blocked from search?
    B = defaultdict(list)  # graph portions that yield no elementary circuit
    result = []  # list to accumulate the circuits found

    # Johnson's algorithm exclude self cycle edges like (v, v)
    # To be backward compatible, we record those cycles in advance
    # and then remove from subG
    for v in G:
        if G.has_edge(v, v):
            result.append([v])
            G.remove_edge(v, v)

    # Johnson's algorithm requires some ordering of the nodes.
    # They might not be sortable so we assign an arbitrary ordering.
    ordering = dict(zip(G, range(len(G))))
    for s in ordering:
        # Build the subgraph induced by s and following nodes in the ordering
        subgraph = G.subgraph(node for node in G if ordering[node] >= ordering[s])
        # Find the strongly connected component in the subgraph
        # that contains the least node according to the ordering
        strongcomp = nx.strongly_connected_components(subgraph)
        mincomp = min(strongcomp, key=lambda ns: min(ordering[n] for n in ns))
        component = G.subgraph(mincomp)
        if len(component) > 1:
            # smallest node in the component according to the ordering
            startnode = min(component, key=ordering.__getitem__)
            for node in component:
                blocked[node] = False
                B[node][:] = []
            dummy = circuit(startnode, startnode, component)
    return result


@nx._dispatchable
def find_cycle(G, source=None, orientation=None):
    """Returns a cycle found via depth-first traversal.

    The cycle is a list of edges indicating the cyclic path.
    Orientation of directed edges is controlled by `orientation`.

    Parameters
    ----------
    G : graph
        A directed/undirected graph/multigraph.

    source : node, list of nodes
        The node from which the traversal begins. If None, then a source
        is chosen arbitrarily and repeatedly until all edges from each node in
        the graph are searched.

    orientation : None | 'original' | 'reverse' | 'ignore' (default: None)
        For directed graphs and directed multigraphs, edge traversals need not
        respect the original orientation of the edges.
        When set to 'reverse' every edge is traversed in the reverse direction.
        When set to 'ignore', every edge is treated as undirected.
        When set to 'original', every edge is treated as directed.
        In all three cases, the yielded edge tuples add a last entry to
        indicate the direction in which that edge was traversed.
        If orientation is None, the yielded edge has no direction indicated.
        The direction is respected, but not reported.

    Returns
    -------
    edges : directed edges
        A list of directed edges indicating the path taken for the loop.
        If no cycle is found, then an exception is raised.
        For graphs, an edge is of the form `(u, v)` where `u` and `v`
        are the tail and head of the edge as determined by the traversal.
        For multigraphs, an edge is of the form `(u, v, key)`, where `key` is
        the key of the edge. When the graph is directed, then `u` and `v`
        are always in the order of the actual directed edge.
        If orientation is not None then the edge tuple is extended to include
        the direction of traversal ('forward' or 'reverse') on that edge.

    Raises
    ------
    NetworkXNoCycle
        If no cycle was found.

    Examples
    --------
    In this example, we construct a DAG and find, in the first call, that there
    are no directed cycles, and so an exception is raised. In the second call,
    we ignore edge orientations and find that there is an undirected cycle.
    Note that the second call finds a directed cycle while effectively
    traversing an undirected graph, and so, we found an "undirected cycle".
    This means that this DAG structure does not form a directed tree (which
    is also known as a polytree).

    >>> G = nx.DiGraph([(0, 1), (0, 2), (1, 2)])
    >>> nx.find_cycle(G, orientation="original")
    Traceback (most recent call last):
        ...
    networkx.exception.NetworkXNoCycle: No cycle found.
    >>> list(nx.find_cycle(G, orientation="ignore"))
    [(0, 1, 'forward'), (1, 2, 'forward'), (0, 2, 'reverse')]

    See Also
    --------
    simple_cycles
    """
    if not G.is_directed() or orientation in (None, "original"):

        def tailhead(edge):
            return edge[:2]

    elif orientation == "reverse":

        def tailhead(edge):
            return edge[1], edge[0]

    elif orientation == "ignore":

        def tailhead(edge):
            if edge[-1] == "reverse":
                return edge[1], edge[0]
            return edge[:2]

    explored = set()
    cycle = []
    final_node = None
    for start_node in G.nbunch_iter(source):
        if start_node in explored:
            # No loop is possible.
            continue

        edges = []
        # All nodes seen in this iteration of edge_dfs
        seen = {start_node}
        # Nodes in active path.
        active_nodes = {start_node}
        previous_head = None

        for edge in nx.edge_dfs(G, start_node, orientation):
            # Determine if this edge is a continuation of the active path.
            tail, head = tailhead(edge)
            if head in explored:
                # Then we've already explored it. No loop is possible.
                continue
            if previous_head is not None and tail != previous_head:
                # This edge results from backtracking.
                # Pop until we get a node whose head equals the current tail.
                # So for example, we might have:
                #  (0, 1), (1, 2), (2, 3), (1, 4)
                # which must become:
                #  (0, 1), (1, 4)
                while True:
                    try:
                        popped_edge = edges.pop()
                    except IndexError:
                        edges = []
                        active_nodes = {tail}
                        break
                    else:
                        popped_head = tailhead(popped_edge)[1]
                        active_nodes.remove(popped_head)

                    if edges:
                        last_head = tailhead(edges[-1])[1]
                        if tail == last_head:
                            break
            edges.append(edge)

            if head in active_nodes:
                # We have a loop!
                cycle.extend(edges)
                final_node = head
                break
            else:
                seen.add(head)
                active_nodes.add(head)
                previous_head = head

        if cycle:
            break
        else:
            explored.update(seen)

    else:
        assert len(cycle) == 0
        raise nx.exception.NetworkXNoCycle("No cycle found.")

    # We now have a list of edges which ends on a cycle.
    # So we need to remove from the beginning edges that are not relevant.

    for i, edge in enumerate(cycle):
        tail, head = tailhead(edge)
        if tail == final_node:
            break

    return cycle[i:]


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable(edge_attrs="weight")
def minimum_cycle_basis(G, weight=None):
    """Returns a minimum weight cycle basis for G

    Minimum weight means a cycle basis for which the total weight
    (length for unweighted graphs) of all the cycles is minimum.

    Parameters
    ----------
    G : NetworkX Graph
    weight: string
        name of the edge attribute to use for edge weights

    Returns
    -------
    A list of cycle lists.  Each cycle list is a list of nodes
    which forms a cycle (loop) in G. Note that the nodes are not
    necessarily returned in a order by which they appear in the cycle

    Examples
    --------
    >>> G = nx.Graph()
    >>> nx.add_cycle(G, [0, 1, 2, 3])
    >>> nx.add_cycle(G, [0, 3, 4, 5])
    >>> nx.minimum_cycle_basis(G)
    [[5, 4, 3, 0], [3, 2, 1, 0]]

    References:
        [1] Kavitha, Telikepalli, et al. "An O(m^2n) Algorithm for
        Minimum Cycle Basis of Graphs."
        http://link.springer.com/article/10.1007/s00453-007-9064-z
        [2] de Pina, J. 1995. Applications of shortest path methods.
        Ph.D. thesis, University of Amsterdam, Netherlands

    See Also
    --------
    simple_cycles, cycle_basis
    """
    # We first split the graph in connected subgraphs
    return sum(
        (_min_cycle_basis(G.subgraph(c), weight) for c in nx.connected_components(G)),
        [],
    )


def _min_cycle_basis(G, weight):
    cb = []
    # We  extract the edges not in a spanning tree. We do not really need a
    # *minimum* spanning tree. That is why we call the next function with
    # weight=None. Depending on implementation, it may be faster as well
    tree_edges = list(nx.minimum_spanning_edges(G, weight=None, data=False))
    chords = G.edges - tree_edges - {(v, u) for u, v in tree_edges}

    # We maintain a set of vectors orthogonal to sofar found cycles
    set_orth = [{edge} for edge in chords]
    while set_orth:
        base = set_orth.pop()
        # kth cycle is "parallel" to kth vector in set_orth
        cycle_edges = _min_cycle(G, base, weight)
        cb.append([v for u, v in cycle_edges])

        # now update set_orth so that k+1,k+2... th elements are
        # orthogonal to the newly found cycle, as per [p. 336, 1]
        set_orth = [
            (
                {e for e in orth if e not in base if e[::-1] not in base}
                | {e for e in base if e not in orth if e[::-1] not in orth}
            )
            if sum((e in orth or e[::-1] in orth) for e in cycle_edges) % 2
            else orth
            for orth in set_orth
        ]
    return cb


def _min_cycle(G, orth, weight):
    """
    Computes the minimum weight cycle in G,
    orthogonal to the vector orth as per [p. 338, 1]
    Use (u, 1) to indicate the lifted copy of u (denoted u' in paper).
    """
    Gi = nx.Graph()

    # Add 2 copies of each edge in G to Gi.
    # If edge is in orth, add cross edge; otherwise in-plane edge
    for u, v, wt in G.edges(data=weight, default=1):
        if (u, v) in orth or (v, u) in orth:
            Gi.add_edges_from([(u, (v, 1)), ((u, 1), v)], Gi_weight=wt)
        else:
            Gi.add_edges_from([(u, v), ((u, 1), (v, 1))], Gi_weight=wt)

    # find the shortest length in Gi between n and (n, 1) for each n
    # Note: Use "Gi_weight" for name of weight attribute
    spl = nx.shortest_path_length
    lift = {n: spl(Gi, source=n, target=(n, 1), weight="Gi_weight") for n in G}

    # Now compute that short path in Gi, which translates to a cycle in G
    start = min(lift, key=lift.get)
    end = (start, 1)
    min_path_i = nx.shortest_path(Gi, source=start, target=end, weight="Gi_weight")

    # Now we obtain the actual path, re-map nodes in Gi to those in G
    min_path = [n if n in G else n[0] for n in min_path_i]

    # Now remove the edges that occur two times
    # two passes: flag which edges get kept, then build it
    edgelist = list(pairwise(min_path))
    edgeset = set()
    for e in edgelist:
        if e in edgeset:
            edgeset.remove(e)
        elif e[::-1] in edgeset:
            edgeset.remove(e[::-1])
        else:
            edgeset.add(e)

    min_edgelist = []
    for e in edgelist:
        if e in edgeset:
            min_edgelist.append(e)
            edgeset.remove(e)
        elif e[::-1] in edgeset:
            min_edgelist.append(e[::-1])
            edgeset.remove(e[::-1])

    return min_edgelist


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def girth(G):
    """Returns the girth of the graph.

    The girth of a graph is the length of its shortest cycle, or infinity if
    the graph is acyclic. The algorithm follows the description given on the
    Wikipedia page [1]_, and runs in time O(mn) on a graph with m edges and n
    nodes.

    Parameters
    ----------
    G : NetworkX Graph

    Returns
    -------
    int or math.inf

    Examples
    --------
    All examples below (except P_5) can easily be checked using Wikipedia,
    which has a page for each of these famous graphs.

    >>> nx.girth(nx.chvatal_graph())
    4
    >>> nx.girth(nx.tutte_graph())
    4
    >>> nx.girth(nx.petersen_graph())
    5
    >>> nx.girth(nx.heawood_graph())
    6
    >>> nx.girth(nx.pappus_graph())
    6
    >>> nx.girth(nx.path_graph(5))
    inf

    References
    ----------
    .. [1] `Wikipedia: Girth <https://en.wikipedia.org/wiki/Girth_(graph_theory)>`_

    """
    girth = depth_limit = inf
    tree_edge = nx.algorithms.traversal.breadth_first_search.TREE_EDGE
    level_edge = nx.algorithms.traversal.breadth_first_search.LEVEL_EDGE
    for n in G:
        # run a BFS from source n, keeping track of distances; since we want
        # the shortest cycle, no need to explore beyond the current minimum length
        depth = {n: 0}
        for u, v, label in nx.bfs_labeled_edges(G, n):
            du = depth[u]
            if du > depth_limit:
                break
            if label is tree_edge:
                depth[v] = du + 1
            else:
                # if (u, v) is a level edge, the length is du + du + 1 (odd)
                # otherwise, it's a forward edge; length is du + (du + 1) + 1 (even)
                delta = label is level_edge
                length = du + du + 2 - delta
                if length < girth:
                    girth = length
                    depth_limit = du - delta

    return girth
