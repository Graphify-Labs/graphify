"""Generate graphs with a given degree sequence or expected degree sequence."""

import heapq
import math
from itertools import chain, combinations, zip_longest
from operator import itemgetter

import networkx as nx
from networkx.utils import py_random_state, random_weighted_sample

__all__ = [
    "configuration_model",
    "directed_configuration_model",
    "expected_degree_graph",
    "havel_hakimi_graph",
    "directed_havel_hakimi_graph",
    "degree_sequence_tree",
    "random_degree_sequence_graph",
]

chaini = chain.from_iterable


def _to_stublist(degree_sequence):
    """Returns a list of degree-repeated node numbers.

    ``degree_sequence`` is a list of nonnegative integers representing
    the degrees of nodes in a graph.

    This function returns a list of node numbers with multiplicities
    according to the given degree sequence. For example, if the first
    element of ``degree_sequence`` is ``3``, then the first node number,
    ``0``, will appear at the head of the returned list three times. The
    node numbers are assumed to be the numbers zero through
    ``len(degree_sequence) - 1``.

    Examples
    --------

    >>> degree_sequence = [1, 2, 3]
    >>> _to_stublist(degree_sequence)
    [0, 1, 1, 2, 2, 2]

    If a zero appears in the sequence, that means the node exists but
    has degree zero, so that number will be skipped in the returned
    list::

    >>> degree_sequence = [2, 0, 1]
    >>> _to_stublist(degree_sequence)
    [0, 0, 2]

    """
    return list(chaini([n] * d for n, d in enumerate(degree_sequence)))


def _configuration_model(
    deg_sequence, create_using, directed=False, in_deg_sequence=None, seed=None
):
    """Helper function for generating either undirected or directed
    configuration model graphs.

    ``deg_sequence`` is a list of nonnegative integers representing the
    degree of the node whose label is the index of the list element.

    ``create_using`` see :func:`~networkx.empty_graph`.

    ``directed`` and ``in_deg_sequence`` are required if you want the
    returned graph to be generated using the directed configuration
    model algorithm. If ``directed`` is ``False``, then ``deg_sequence``
    is interpreted as the degree sequence of an undirected graph and
    ``in_deg_sequence`` is ignored. Otherwise, if ``directed`` is
    ``True``, then ``deg_sequence`` is interpreted as the out-degree
    sequence and ``in_deg_sequence`` as the in-degree sequence of a
    directed graph.

    .. note::

       ``deg_sequence`` and ``in_deg_sequence`` need not be the same
       length.

    ``seed`` is a random.Random or numpy.random.RandomState instance

    This function returns a graph, directed if and only if ``directed``
    is ``True``, generated according to the configuration model
    algorithm. For more information on the algorithm, see the
    :func:`configuration_model` or :func:`directed_configuration_model`
    functions.

    """
    n = len(deg_sequence)
    G = nx.empty_graph(n, create_using)
    # If empty, return the null graph immediately.
    if n == 0:
        return G
    # Build a list of available degree-repeated nodes.  For example,
    # for degree sequence [3, 2, 1, 1, 1], the "stub list" is
    # initially [0, 0, 0, 1, 1, 2, 3, 4], that is, node 0 has degree
    # 3 and thus is repeated 3 times, etc.
    #
    # Also, shuffle the stub list in order to get a random sequence of
    # node pairs.
    if directed:
        pairs = zip_longest(deg_sequence, in_deg_sequence, fillvalue=0)
        # Unzip the list of pairs into a pair of lists.
        out_deg, in_deg = zip(*pairs)

        out_stublist = _to_stublist(out_deg)
        in_stublist = _to_stublist(in_deg)

        seed.shuffle(out_stublist)
        seed.shuffle(in_stublist)
    else:
        stublist = _to_stublist(deg_sequence)
        # Choose a random balanced bipartition of the stublist, which
        # gives a random pairing of nodes. In this implementation, we
        # shuffle the list and then split it in half.
        n = len(stublist)
        half = n // 2
        seed.shuffle(stublist)
        out_stublist, in_stublist = stublist[:half], stublist[half:]
    G.add_edges_from(zip(out_stublist, in_stublist))
    return G


@py_random_state(2)
@nx._dispatchable(graphs=None, returns_graph=True)
def configuration_model(deg_sequence, create_using=None, seed=None):
    """Returns a random graph with the given degree sequence.

    The configuration model generates a random pseudograph (graph with
    parallel edges and self loops) by randomly assigning edges to
    match the given degree sequence.

    Parameters
    ----------
    deg_sequence :  list of nonnegative integers
        Each list entry corresponds to the degree of a node.
    create_using : NetworkX graph constructor, optional (default MultiGraph)
        Graph type to create. If graph instance, then cleared before populated.
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    G : MultiGraph
        A graph with the specified degree sequence.
        Nodes are labeled starting at 0 with an index
        corresponding to the position in deg_sequence.

    Raises
    ------
    NetworkXError
        If the degree sequence does not have an even sum.

    See Also
    --------
    is_graphical

    Notes
    -----
    As described by Newman [1]_.

    A non-graphical degree sequence (not realizable by some simple
    graph) is allowed since this function returns graphs with self
    loops and parallel edges.  An exception is raised if the degree
    sequence does not have an even sum.

    This configuration model construction process can lead to
    duplicate edges and loops.  You can remove the self-loops and
    parallel edges (see below) which will likely result in a graph
    that doesn't have the exact degree sequence specified.

    The density of self-loops and parallel edges tends to decrease as
    the number of nodes increases. However, typically the number of
    self-loops will approach a Poisson distribution with a nonzero mean,
    and similarly for the number of parallel edges.  Consider a node
    with *k* stubs. The probability of being joined to another stub of
    the same node is basically (*k* - *1*) / *N*, where *k* is the
    degree and *N* is the number of nodes. So the probability of a
    self-loop scales like *c* / *N* for some constant *c*. As *N* grows,
    this means we expect *c* self-loops. Similarly for parallel edges.

    References
    ----------
    .. [1] M.E.J. Newman, "The structure and function of complex networks",
       SIAM REVIEW 45-2, pp 167-256, 2003.

    Examples
    --------
    You can create a degree sequence following a particular distribution
    by using the one of the distribution functions in
    :mod:`~networkx.utils.random_sequence` (or one of your own). For
    example, to create an undirected multigraph on one hundred nodes
    with degree sequence chosen from the power law distribution:

    >>> sequence = nx.random_powerlaw_tree_sequence(100, tries=5000)
    >>> G = nx.configuration_model(sequence)
    >>> len(G)
    100
    >>> actual_degrees = [d for v, d in G.degree()]
    >>> actual_degrees == sequence
    True

    The returned graph is a multigraph, which may have parallel
    edges. To remove any parallel edges from the returned graph:

    >>> G = nx.Graph(G)

    Similarly, to remove self-loops:

    >>> G.remove_edges_from(nx.selfloop_edges(G))

    """
    if sum(deg_sequence) % 2 != 0:
        msg = "Invalid degree sequence: sum of degrees must be even, not odd"
        raise nx.NetworkXError(msg)

    G = nx.empty_graph(0, create_using, default=nx.MultiGraph)
    if G.is_directed():
        raise nx.NetworkXNotImplemented("not implemented for directed graphs")

    G = _configuration_model(deg_sequence, G, seed=seed)

    return G


@py_random_state(3)
@nx._dispatchable(graphs=None, returns_graph=True)
def directed_configuration_model(
    in_degree_sequence, out_degree_sequence, create_using=None, seed=None
):
    """Returns a directed_random graph with the given degree sequences.

    The configuration model generates a random directed pseudograph
    (graph with parallel edges and self loops) by randomly assigning
    edges to match the given degree sequences.

    Parameters
    ----------
    in_degree_sequence :  list of nonnegative integers
       Each list entry corresponds to the in-degree of a node.
    out_degree_sequence :  list of nonnegative integers
       Each list entry corresponds to the out-degree of a node.
    create_using : NetworkX graph constructor, optional (default MultiDiGraph)
        Graph type to create. If graph instance, then cleared before populated.
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    G : MultiDiGraph
        A graph with the specified degree sequences.
        Nodes are labeled starting at 0 with an index
        corresponding to the position in deg_sequence.

    Raises
    ------
    NetworkXError
        If the degree sequences do not have the same sum.

    See Also
    --------
    configuration_model

    Notes
    -----
    Algorithm as described by Newman [1]_.

    A non-graphical degree sequence (not realizable by some simple
    graph) is allowed since this function returns graphs with self
    loops and parallel edges.  An exception is raised if the degree
    sequences does not have the same sum.

    This configuration model construction process can lead to
    duplicate edges and loops.  You can remove the self-loops and
    parallel edges (see below) which will likely result in a graph
    that doesn't have the exact degree sequence specified.  This
    "finite-size effect" decreases as the size of the graph increases.

    References
    ----------
    .. [1] Newman, M. E. J. and Strogatz, S. H. and Watts, D. J.
       Random graphs with arbitrary degree distributions and their applications
       Phys. Rev. E, 64, 026118 (2001)

    Examples
    --------
    One can modify the in- and out-degree sequences from an existing
    directed graph in order to create a new directed graph. For example,
    here we modify the directed path graph:

    >>> D = nx.DiGraph([(0, 1), (1, 2), (2, 3)])
    >>> din = list(d for n, d in D.in_degree())
    >>> dout = list(d for n, d in D.out_degree())
    >>> din.append(1)
    >>> dout[0] = 2
    >>> # We now expect an edge from node 0 to a new node, node 3.
    ... D = nx.directed_configuration_model(din, dout)

    The returned graph is a directed multigraph, which may have parallel
    edges. To remove any parallel edges from the returned graph:

    >>> D = nx.DiGraph(D)

    Similarly, to remove self-loops:

    >>> D.remove_edges_from(nx.selfloop_edges(D))

    """
    if sum(in_degree_sequence) != sum(out_degree_sequence):
        msg = "Invalid degree sequences: sequences must have equal sums"
        raise nx.NetworkXError(msg)

    if create_using is None:
        create_using = nx.MultiDiGraph

    G = _configuration_model(
        out_degree_sequence,
        create_using,
        directed=True,
        in_deg_sequence=in_degree_sequence,
        seed=seed,
    )

    name = "directed configuration_model {} nodes {} edges"
    return G


@py_random_state(1)
@nx._dispatchable(graphs=None, returns_graph=True)
def expected_degree_graph(w, seed=None, selfloops=True):
    r"""Returns a random graph with given expected degrees.

    Given a sequence of expected degrees $W=(w_0,w_1,\ldots,w_{n-1})$
    of length $n$ this algorithm assigns an edge between node $u$ and
    node $v$ with probability

    .. math::

       p_{uv} = \frac{w_u w_v}{\sum_k w_k} .

    Parameters
    ----------
    w : list
        The list of expected degrees.
    selfloops: bool (default=True)
        Set to False to remove the possibility of self-loop edges.
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    Graph

    Examples
    --------
    >>> z = [10 for i in range(100)]
    >>> G = nx.expected_degree_graph(z)

    Notes
    -----
    The nodes have integer labels corresponding to index of expected degrees
    input sequence.

    The complexity of this algorithm is $\mathcal{O}(n+m)$ where $n$ is the
    number of nodes and $m$ is the expected number of edges.

    The model in [1]_ includes the possibility of self-loop edges.
    Set selfloops=False to produce a graph without self loops.

    For finite graphs this model doesn't produce exactly the given
    expected degree sequence.  Instead the expected degrees are as
    follows.

    For the case without self loops (selfloops=False),

    .. math::

       E[deg(u)] = \sum_{v \ne u} p_{uv}
                = w_u \left( 1 - \frac{w_u}{\sum_k w_k} \right) .


    NetworkX uses the standard convention that a self-loop edge counts 2
    in the degree of a node, so with self loops (selfloops=True),

    .. math::

       E[deg(u)] =  \sum_{v \ne u} p_{uv}  + 2 p_{uu}
                = w_u \left( 1 + \frac{w_u}{\sum_k w_k} \right) .

    References
    ----------
    .. [1] Fan Chung and L. Lu, Connected components in random graphs with
       given expected degree sequences, Ann. Combinatorics, 6,
       pp. 125-145, 2002.
    .. [2] Joel Miller and Aric Hagberg,
       Efficient generation of networks with given expected degrees,
       in Algorithms and Models for the Web-Graph (WAW 2011),
       Alan Frieze, Paul Horn, and Paweł Prałat (Eds), LNCS 6732,
       pp. 115-126, 2011.
    """
    n = len(w)
    G = nx.empty_graph(n)

    # If there are no nodes are no edges in the graph, return the empty graph.
    if n == 0 or max(w) == 0:
        return G

    rho = 1 / sum(w)
    # Sort the weights in decreasing order. The original order of the
    # weights dictates the order of the (integer) node labels, so we
    # need to remember the permutation applied in the sorting.
    order = sorted(enumerate(w), key=itemgetter(1), reverse=True)
    mapping = {c: u for c, (u, v) in enumerate(order)}
    seq = [v for u, v in order]
    last = n
    if not selfloops:
        last -= 1
    for u in range(last):
        v = u
        if not selfloops:
            v += 1
        factor = seq[u] * rho
        p = min(seq[v] * factor, 1)
        while v < n and p > 0:
            if p != 1:
                r = seed.random()
                v += math.floor(math.log(r, 1 - p))
            if v < n:
                q = min(seq[v] * factor, 1)
                if seed.random() < q / p:
                    G.add_edge(mapping[u], mapping[v])
                v += 1
                p = q
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def havel_hakimi_graph(deg_sequence, create_using=None):
    """Returns a simple graph with given degree sequence constructed
    using the Havel-Hakimi algorithm.

    Parameters
    ----------
    deg_sequence: list of integers
        Each integer corresponds to the degree of a node (need not be sorted).
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
        Graph type to create. If graph instance, then cleared before populated.
        Directed graphs are not allowed.

    Raises
    ------
    NetworkXException
        For a non-graphical degree sequence (i.e. one
        not realizable by some simple graph).

    Notes
    -----
    The Havel-Hakimi algorithm constructs a simple graph by
    successively connecting the node of highest degree to other nodes
    of highest degree, resorting remaining nodes by degree, and
    repeating the process. The resulting graph has a high
    degree-associativity.  Nodes are labeled 1,.., len(deg_sequence),
    corresponding to their position in deg_sequence.

    The basic algorithm is from Hakimi [1]_ and was generalized by
    Kleitman and Wang [2]_.

    References
    ----------
    .. [1] Hakimi S., On Realizability of a Set of Integers as
       Degrees of the Vertices of a Linear Graph. I,
       Journal of SIAM, 10(3), pp. 496-506 (1962)
    .. [2] Kleitman D.J. and Wang D.L.
       Algorithms for Constructing Graphs and Digraphs with Given Valences
       and Factors  Discrete Mathematics, 6(1), pp. 79-88 (1973)
    """
    if not nx.is_graphical(deg_sequence):
        raise nx.NetworkXError("Invalid degree sequence")

    p = len(deg_sequence)
    G = nx.empty_graph(p, create_using)
    if G.is_directed():
        raise nx.NetworkXError("Directed graphs are not supported")
    num_degs = [[] for i in range(p)]
    dmax, dsum, n = 0, 0, 0
    for d in deg_sequence:
        # Process only the non-zero integers
        if d > 0:
            num_degs[d].append(n)
            dmax, dsum, n = max(dmax, d), dsum + d, n + 1
    # Return graph if no edges
    if n == 0:
        return G

    modstubs = [(0, 0)] * (dmax + 1)
    # Successively reduce degree sequence by removing the maximum degree
    while n > 0:
        # Retrieve the maximum degree in the sequence
        while len(num_degs[dmax]) == 0:
            dmax -= 1
        # If there are not enough stubs to connect to, then the sequence is
        # not graphical
        if dmax > n - 1:
            raise nx.NetworkXError("Non-graphical integer sequence")

        # Remove largest stub in list
        source = num_degs[dmax].pop()
        n -= 1
        # Reduce the next dmax largest stubs
        mslen = 0
        k = dmax
        for i in range(dmax):
            while len(num_degs[k]) == 0:
                k -= 1
            target = num_degs[k].pop()
            G.add_edge(source, target)
            n -= 1
            if k > 1:
                modstubs[mslen] = (k - 1, target)
                mslen += 1
        # Add back to the list any nonzero stubs that were removed
        for i in range(mslen):
            (stubval, stubtarget) = modstubs[i]
            num_degs[stubval].append(stubtarget)
            n += 1

    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def directed_havel_hakimi_graph(in_deg_sequence, out_deg_sequence, create_using=None):
    """Returns a directed graph with the given degree sequences.

    Parameters
    ----------
    in_deg_sequence :  list of integers
        Each list entry corresponds to the in-degree of a node.
    out_deg_sequence : list of integers
        Each list entry corresponds to the out-degree of a node.
    create_using : NetworkX graph constructor, optional (default DiGraph)
        Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : DiGraph
        A graph with the specified degree sequences.
        Nodes are labeled starting at 0 with an index
        corresponding to the position in deg_sequence

    Raises
    ------
    NetworkXError
        If the degree sequences are not digraphical.

    See Also
    --------
    configuration_model

    Notes
    -----
    Algorithm as described by Kleitman and Wang [1]_.

    References
    ----------
    .. [1] D.J. Kleitman and D.L. Wang
       Algorithms for Constructing Graphs and Digraphs with Given Valences
       and Factors Discrete Mathematics, 6(1), pp. 79-88 (1973)
    """
    in_deg_sequence = nx.utils.make_list_of_ints(in_deg_sequence)
    out_deg_sequence = nx.utils.make_list_of_ints(out_deg_sequence)

    # Process the sequences and form two heaps to store degree pairs with
    # either zero or nonzero out degrees
    sumin, sumout = 0, 0
    nin, nout = len(in_deg_sequence), len(out_deg_sequence)
    maxn = max(nin, nout)
    G = nx.empty_graph(maxn, create_using, default=nx.DiGraph)
    if maxn == 0:
        return G
    maxin = 0
    stubheap, zeroheap = [], []
    for n in range(maxn):
        in_deg, out_deg = 0, 0
        if n < nout:
            out_deg = out_deg_sequence[n]
        if n < nin:
            in_deg = in_deg_sequence[n]
        if in_deg < 0 or out_deg < 0:
            raise nx.NetworkXError(
                "Invalid degree sequences. Sequence values must be positive."
            )
        sumin, sumout, maxin = sumin + in_deg, sumout + out_deg, max(maxin, in_deg)
        if in_deg > 0:
            stubheap.append((-1 * out_deg, -1 * in_deg, n))
        elif out_deg > 0:
            zeroheap.append((-1 * out_deg, n))
    if sumin != sumout:
        raise nx.NetworkXError(
            "Invalid degree sequences. Sequences must have equal sums."
        )
    heapq.heapify(stubheap)
    heapq.heapify(zeroheap)

    modstubs = [(0, 0, 0)] * (maxin + 1)
    # Successively reduce degree sequence by removing the maximum
    while stubheap:
        # Remove first value in the sequence with a non-zero in degree
        (freeout, freein, target) = heapq.heappop(stubheap)
        freein *= -1
        if freein > len(stubheap) + len(zeroheap):
            raise nx.NetworkXError("Non-digraphical integer sequence")

        # Attach arcs from the nodes with the most stubs
        mslen = 0
        for i in range(freein):
            if zeroheap and (not stubheap or stubheap[0][0] > zeroheap[0][0]):
                (stubout, stubsource) = heapq.heappop(zeroheap)
                stubin = 0
            else:
                (stubout, stubin, stubsource) = heapq.heappop(stubheap)
            if stubout == 0:
                raise nx.NetworkXError("Non-digraphical integer sequence")
            G.add_edge(stubsource, target)
            # Check if source is now totally connected
            if stubout + 1 < 0 or stubin < 0:
                modstubs[mslen] = (stubout + 1, stubin, stubsource)
                mslen += 1

        # Add the nodes back to the heaps that still have available stubs
        for i in range(mslen):
            stub = modstubs[i]
            if stub[1] < 0:
                heapq.heappush(stubheap, stub)
            else:
                heapq.heappush(zeroheap, (stub[0], stub[2]))
        if freeout < 0:
            heapq.heappush(zeroheap, (freeout, target))

    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def degree_sequence_tree(deg_sequence, create_using=None):
    """Make a tree for the given degree sequence.

    A tree has #nodes-#edges=1 so
    the degree sequence must have
    len(deg_sequence)-sum(deg_sequence)/2=1
    """
    # The sum of the degree sequence must be even (for any undirected graph).
    degree_sum = sum(deg_sequence)
    if degree_sum % 2 != 0:
        msg = "Invalid degree sequence: sum of degrees must be even, not odd"
        raise nx.NetworkXError(msg)
    if len(deg_sequence) - degree_sum // 2 != 1:
        msg = (
            "Invalid degree sequence: tree must have number of nodes equal"
            " to one less than the number of edges"
        )
        raise nx.NetworkXError(msg)
    G = nx.empty_graph(0, create_using)
    if G.is_directed():
        raise nx.NetworkXError("Directed Graph not supported")

    # Sort all degrees greater than 1 in decreasing order.
    #
    # TODO Does this need to be sorted in reverse order?
    deg = sorted((s for s in deg_sequence if s > 1), reverse=True)

    # make path graph as backbone
    n = len(deg) + 2
    nx.add_path(G, range(n))
    last = n

    # add the leaves
    for source in range(1, n - 1):
        nedges = deg.pop() - 2
        for target in range(last, last + nedges):
            G.add_edge(source, target)
        last += nedges

    # in case we added one too many
    if len(G) > len(deg_sequence):
        G.remove_node(0)
    return G


@py_random_state(1)
@nx._dispatchable(graphs=None, returns_graph=True)
def random_degree_sequence_graph(sequence, seed=None, tries=10):
    r"""Returns a simple random graph with the given degree sequence.

    If the maximum degree $d_m$ in the sequence is $O(m^{1/4})$ then the
    algorithm produces almost uniform random graphs in $O(m d_m)$ time
    where $m$ is the number of edges.

    Parameters
    ----------
    sequence :  list of integers
        Sequence of degrees
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.
    tries : int, optional
        Maximum number of tries to create a graph

    Returns
    -------
    G : Graph
        A graph with the specified degree sequence.
        Nodes are labeled starting at 0 with an index
        corresponding to the position in the sequence.

    Raises
    ------
    NetworkXUnfeasible
        If the degree sequence is not graphical.
    NetworkXError
        If a graph is not produced in specified number of tries

    See Also
    --------
    is_graphical, configuration_model

    Notes
    -----
    The generator algorithm [1]_ is not guaranteed to produce a graph.

    References
    ----------
    .. [1] Moshen Bayati, Jeong Han Kim, and Amin Saberi,
       A sequential algorithm for generating random graphs.
       Algorithmica, Volume 58, Number 4, 860-910,
       DOI: 10.1007/s00453-009-9340-1

    Examples
    --------
    >>> sequence = [1, 2, 2, 3]
    >>> G = nx.random_degree_sequence_graph(sequence, seed=42)
    >>> sorted(d for n, d in G.degree())
    [1, 2, 2, 3]
    """
    DSRG = DegreeSequenceRandomGraph(sequence, seed)
    for try_n in range(tries):
        try:
            return DSRG.generate()
        except nx.NetworkXUnfeasible:
            pass
    raise nx.NetworkXError(f"failed to generate graph in {tries} tries")


class DegreeSequenceRandomGraph:
    # class to generate random graphs with a given degree sequence
    # use random_degree_sequence_graph()
    def __init__(self, degree, rng):
        if not nx.is_graphical(degree):
            raise nx.NetworkXUnfeasible("degree sequence is not graphical")
        self.rng = rng
        self.degree = list(degree)
        # node labels are integers 0,...,n-1
        self.m = sum(self.degree) / 2.0  # number of edges
        try:
            self.dmax = max(self.degree)  # maximum degree
        except ValueError:
            self.dmax = 0

    def generate(self):
        # remaining_degree is mapping from int->remaining degree
        self.remaining_degree = dict(enumerate(self.degree))
        # add all nodes to make sure we get isolated nodes
        self.graph = nx.Graph()
        self.graph.add_nodes_from(self.remaining_degree)
        # remove zero degree nodes
        for n, d in list(self.remaining_degree.items()):
            if d == 0:
                del self.remaining_degree[n]
        if len(self.remaining_degree) > 0:
            # build graph in three phases according to how many unmatched edges
            self.phase1()
            self.phase2()
            self.phase3()
        return self.graph

    def update_remaining(self, u, v, aux_graph=None):
        # decrement remaining nodes, modify auxiliary graph if in phase3
        if aux_graph is not None:
            # remove edges from auxiliary graph
            aux_graph.remove_edge(u, v)
        if self.remaining_degree[u] == 1:
            del self.remaining_degree[u]
            if aux_graph is not None:
                aux_graph.remove_node(u)
        else:
            self.remaining_degree[u] -= 1
        if self.remaining_degree[v] == 1:
            del self.remaining_degree[v]
            if aux_graph is not None:
                aux_graph.remove_node(v)
        else:
            self.remaining_degree[v] -= 1

    def p(self, u, v):
        # degree probability
        return 1 - self.degree[u] * self.degree[v] / (4.0 * self.m)

    def q(self, u, v):
        # remaining degree probability
        norm = max(self.remaining_degree.values()) ** 2
        return self.remaining_degree[u] * self.remaining_degree[v] / norm

    def suitable_edge(self):
        """Returns True if and only if an arbitrary remaining node can
        potentially be joined with some other remaining node.

        """
        nodes = iter(self.remaining_degree)
        u = next(nodes)
        return any(v not in self.graph[u] for v in nodes)

    def phase1(self):
        # choose node pairs from (degree) weighted distribution
        rem_deg = self.remaining_degree
        while sum(rem_deg.values()) >= 2 * self.dmax**2:
            u, v = sorted(random_weighted_sample(rem_deg, 2, self.rng))
            if self.graph.has_edge(u, v):
                continue
            if self.rng.random() < self.p(u, v):  # accept edge
                self.graph.add_edge(u, v)
                self.update_remaining(u, v)

    def phase2(self):
        # choose remaining nodes uniformly at random and use rejection sampling
        remaining_deg = self.remaining_degree
        rng = self.rng
        while len(remaining_deg) >= 2 * self.dmax:
            while True:
                u, v = sorted(rng.sample(list(remaining_deg.keys()), 2))
                if self.graph.has_edge(u, v):
                    continue
                if rng.random() < self.q(u, v):
                    break
            if rng.random() < self.p(u, v):  # accept edge
                self.graph.add_edge(u, v)
                self.update_remaining(u, v)

    def phase3(self):
        # build potential remaining edges and choose with rejection sampling
        potential_edges = combinations(self.remaining_degree, 2)
        # build auxiliary graph of potential edges not already in graph
        H = nx.Graph(
            [(u, v) for (u, v) in potential_edges if not self.graph.has_edge(u, v)]
        )
        rng = self.rng
        while self.remaining_degree:
            if not self.suitable_edge():
                raise nx.NetworkXUnfeasible("no suitable edges left")
            while True:
                u, v = sorted(rng.choice(list(H.edges())))
                if rng.random() < self.q(u, v):
                    break
            if rng.random() < self.p(u, v):  # accept edge
                self.graph.add_edge(u, v)
                self.update_remaining(u, v, aux_graph=H)
