"""Generators for classes of graphs used in studying social networks."""

import itertools
import math

import networkx as nx
from networkx.utils import py_random_state

__all__ = [
    "caveman_graph",
    "connected_caveman_graph",
    "relaxed_caveman_graph",
    "random_partition_graph",
    "planted_partition_graph",
    "gaussian_random_partition_graph",
    "ring_of_cliques",
    "windmill_graph",
    "stochastic_block_model",
    "LFR_benchmark_graph",
]


@nx._dispatchable(graphs=None, returns_graph=True)
def caveman_graph(l, k):
    """Returns a caveman graph of `l` cliques of size `k`.

    Parameters
    ----------
    l : int
      Number of cliques
    k : int
      Size of cliques

    Returns
    -------
    G : NetworkX Graph
      caveman graph

    Notes
    -----
    This returns an undirected graph, it can be converted to a directed
    graph using :func:`nx.to_directed`, or a multigraph using
    ``nx.MultiGraph(nx.caveman_graph(l, k))``. Only the undirected version is
    described in [1]_ and it is unclear which of the directed
    generalizations is most useful.

    Examples
    --------
    >>> G = nx.caveman_graph(3, 3)

    See also
    --------

    connected_caveman_graph

    References
    ----------
    .. [1] Watts, D. J. 'Networks, Dynamics, and the Small-World Phenomenon.'
       Amer. J. Soc. 105, 493-527, 1999.
    """
    # l disjoint cliques of size k
    G = nx.empty_graph(l * k)
    if k > 1:
        for start in range(0, l * k, k):
            edges = itertools.combinations(range(start, start + k), 2)
            G.add_edges_from(edges)
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def connected_caveman_graph(l, k):
    """Returns a connected caveman graph of `l` cliques of size `k`.

    The connected caveman graph is formed by creating `n` cliques of size
    `k`, then a single edge in each clique is rewired to a node in an
    adjacent clique.

    Parameters
    ----------
    l : int
      number of cliques
    k : int
      size of cliques (k at least 2 or NetworkXError is raised)

    Returns
    -------
    G : NetworkX Graph
      connected caveman graph

    Raises
    ------
    NetworkXError
        If the size of cliques `k` is smaller than 2.

    Notes
    -----
    This returns an undirected graph, it can be converted to a directed
    graph using :func:`nx.to_directed`, or a multigraph using
    ``nx.MultiGraph(nx.caveman_graph(l, k))``. Only the undirected version is
    described in [1]_ and it is unclear which of the directed
    generalizations is most useful.

    Examples
    --------
    >>> G = nx.connected_caveman_graph(3, 3)

    References
    ----------
    .. [1] Watts, D. J. 'Networks, Dynamics, and the Small-World Phenomenon.'
       Amer. J. Soc. 105, 493-527, 1999.
    """
    if k < 2:
        raise nx.NetworkXError(
            "The size of cliques in a connected caveman graph must be at least 2."
        )

    G = nx.caveman_graph(l, k)
    for start in range(0, l * k, k):
        G.remove_edge(start, start + 1)
        G.add_edge(start, (start - 1) % (l * k))
    return G


@py_random_state(3)
@nx._dispatchable(graphs=None, returns_graph=True)
def relaxed_caveman_graph(l, k, p, seed=None):
    """Returns a relaxed caveman graph.

    A relaxed caveman graph starts with `l` cliques of size `k`.  Edges are
    then randomly rewired with probability `p` to link different cliques.

    Parameters
    ----------
    l : int
      Number of groups
    k : int
      Size of cliques
    p : float
      Probability of rewiring each edge.
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    G : NetworkX Graph
      Relaxed Caveman Graph

    Raises
    ------
    NetworkXError
     If p is not in [0,1]

    Examples
    --------
    >>> G = nx.relaxed_caveman_graph(2, 3, 0.1, seed=42)

    References
    ----------
    .. [1] Santo Fortunato, Community Detection in Graphs,
       Physics Reports Volume 486, Issues 3-5, February 2010, Pages 75-174.
       https://arxiv.org/abs/0906.0612
    """
    G = nx.caveman_graph(l, k)
    nodes = list(G)
    for u, v in G.edges():
        if seed.random() < p:  # rewire the edge
            x = seed.choice(nodes)
            if G.has_edge(u, x):
                continue
            G.remove_edge(u, v)
            G.add_edge(u, x)
    return G


@py_random_state(3)
@nx._dispatchable(graphs=None, returns_graph=True)
def random_partition_graph(sizes, p_in, p_out, seed=None, directed=False):
    """Returns the random partition graph with a partition of sizes.

    A partition graph is a graph of communities with sizes defined by
    s in sizes. Nodes in the same group are connected with probability
    p_in and nodes of different groups are connected with probability
    p_out.

    Parameters
    ----------
    sizes : list of ints
      Sizes of groups
    p_in : float
      probability of edges with in groups
    p_out : float
      probability of edges between groups
    directed : boolean optional, default=False
      Whether to create a directed graph
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    G : NetworkX Graph or DiGraph
      random partition graph of size sum(gs)

    Raises
    ------
    NetworkXError
      If p_in or p_out is not in [0,1]

    Examples
    --------
    >>> G = nx.random_partition_graph([10, 10, 10], 0.25, 0.01)
    >>> len(G)
    30
    >>> partition = G.graph["partition"]
    >>> len(partition)
    3

    Notes
    -----
    This is a generalization of the planted-l-partition described in
    [1]_.  It allows for the creation of groups of any size.

    The partition is store as a graph attribute 'partition'.

    References
    ----------
    .. [1] Santo Fortunato 'Community Detection in Graphs' Physical Reports
       Volume 486, Issue 3-5 p. 75-174. https://arxiv.org/abs/0906.0612
    """
    # Use geometric method for O(n+m) complexity algorithm
    # partition = nx.community_sets(nx.get_node_attributes(G, 'affiliation'))
    if not 0.0 <= p_in <= 1.0:
        raise nx.NetworkXError("p_in must be in [0,1]")
    if not 0.0 <= p_out <= 1.0:
        raise nx.NetworkXError("p_out must be in [0,1]")

    # create connection matrix
    num_blocks = len(sizes)
    p = [[p_out for s in range(num_blocks)] for r in range(num_blocks)]
    for r in range(num_blocks):
        p[r][r] = p_in

    return stochastic_block_model(
        sizes,
        p,
        nodelist=None,
        seed=seed,
        directed=directed,
        selfloops=False,
        sparse=True,
    )


@py_random_state(4)
@nx._dispatchable(graphs=None, returns_graph=True)
def planted_partition_graph(l, k, p_in, p_out, seed=None, directed=False):
    """Returns the planted l-partition graph.

    This model partitions a graph with n=l*k vertices in
    l groups with k vertices each. Vertices of the same
    group are linked with a probability p_in, and vertices
    of different groups are linked with probability p_out.

    Parameters
    ----------
    l : int
      Number of groups
    k : int
      Number of vertices in each group
    p_in : float
      probability of connecting vertices within a group
    p_out : float
      probability of connected vertices between groups
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.
    directed : bool,optional (default=False)
      If True return a directed graph

    Returns
    -------
    G : NetworkX Graph or DiGraph
      planted l-partition graph

    Raises
    ------
    NetworkXError
      If `p_in`, `p_out` are not in `[0, 1]`

    Examples
    --------
    >>> G = nx.planted_partition_graph(4, 3, 0.5, 0.1, seed=42)

    See Also
    --------
    random_partition_model

    References
    ----------
    .. [1] A. Condon, R.M. Karp, Algorithms for graph partitioning
        on the planted partition model,
        Random Struct. Algor. 18 (2001) 116-140.

    .. [2] Santo Fortunato 'Community Detection in Graphs' Physical Reports
       Volume 486, Issue 3-5 p. 75-174. https://arxiv.org/abs/0906.0612
    """
    return random_partition_graph([k] * l, p_in, p_out, seed=seed, directed=directed)


@py_random_state(6)
@nx._dispatchable(graphs=None, returns_graph=True)
def gaussian_random_partition_graph(n, s, v, p_in, p_out, directed=False, seed=None):
    """Generate a Gaussian random partition graph.

    A Gaussian random partition graph is created by creating k partitions
    each with a size drawn from a normal distribution with mean s and variance
    s/v. Nodes are connected within clusters with probability p_in and
    between clusters with probability p_out[1]

    Parameters
    ----------
    n : int
      Number of nodes in the graph
    s : float
      Mean cluster size
    v : float
      Shape parameter. The variance of cluster size distribution is s/v.
    p_in : float
      Probability of intra cluster connection.
    p_out : float
      Probability of inter cluster connection.
    directed : boolean, optional default=False
      Whether to create a directed graph or not
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    G : NetworkX Graph or DiGraph
      gaussian random partition graph

    Raises
    ------
    NetworkXError
      If s is > n
      If p_in or p_out is not in [0,1]

    Notes
    -----
    Note the number of partitions is dependent on s,v and n, and that the
    last partition may be considerably smaller, as it is sized to simply
    fill out the nodes [1]

    See Also
    --------
    random_partition_graph

    Examples
    --------
    >>> G = nx.gaussian_random_partition_graph(100, 10, 10, 0.25, 0.1)
    >>> len(G)
    100

    References
    ----------
    .. [1] Ulrik Brandes, Marco Gaertler, Dorothea Wagner,
       Experiments on Graph Clustering Algorithms,
       In the proceedings of the 11th Europ. Symp. Algorithms, 2003.
    """
    if s > n:
        raise nx.NetworkXError("s must be <= n")
    assigned = 0
    sizes = []
    while True:
        size = int(seed.gauss(s, s / v + 0.5))
        if size < 1:  # how to handle 0 or negative sizes?
            continue
        if assigned + size >= n:
            sizes.append(n - assigned)
            break
        assigned += size
        sizes.append(size)
    return random_partition_graph(sizes, p_in, p_out, seed=seed, directed=directed)


@nx._dispatchable(graphs=None, returns_graph=True)
def ring_of_cliques(num_cliques, clique_size):
    """Defines a "ring of cliques" graph.

    A ring of cliques graph is consisting of cliques, connected through single
    links. Each clique is a complete graph.

    Parameters
    ----------
    num_cliques : int
        Number of cliques
    clique_size : int
        Size of cliques

    Returns
    -------
    G : NetworkX Graph
        ring of cliques graph

    Raises
    ------
    NetworkXError
        If the number of cliques is lower than 2 or
        if the size of cliques is smaller than 2.

    Examples
    --------
    >>> G = nx.ring_of_cliques(8, 4)

    See Also
    --------
    connected_caveman_graph

    Notes
    -----
    The `connected_caveman_graph` graph removes a link from each clique to
    connect it with the next clique. Instead, the `ring_of_cliques` graph
    simply adds the link without removing any link from the cliques.
    """
    if num_cliques < 2:
        raise nx.NetworkXError("A ring of cliques must have at least two cliques")
    if clique_size < 2:
        raise nx.NetworkXError("The cliques must have at least two nodes")

    G = nx.Graph()
    for i in range(num_cliques):
        edges = itertools.combinations(
            range(i * clique_size, i * clique_size + clique_size), 2
        )
        G.add_edges_from(edges)
        G.add_edge(
            i * clique_size + 1, (i + 1) * clique_size % (num_cliques * clique_size)
        )
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def windmill_graph(n, k):
    """Generate a windmill graph.
    A windmill graph is a graph of `n` cliques each of size `k` that are all
    joined at one node.
    It can be thought of as taking a disjoint union of `n` cliques of size `k`,
    selecting one point from each, and contracting all of the selected points.
    Alternatively, one could generate `n` cliques of size `k-1` and one node
    that is connected to all other nodes in the graph.

    Parameters
    ----------
    n : int
        Number of cliques
    k : int
        Size of cliques

    Returns
    -------
    G : NetworkX Graph
        windmill graph with n cliques of size k

    Raises
    ------
    NetworkXError
        If the number of cliques is less than two
        If the size of the cliques are less than two

    Examples
    --------
    >>> G = nx.windmill_graph(4, 5)

    Notes
    -----
    The node labeled `0` will be the node connected to all other nodes.
    Note that windmill graphs are usually denoted `Wd(k,n)`, so the parameters
    are in the opposite order as the parameters of this method.
    """
    if n < 2:
        msg = "A windmill graph must have at least two cliques"
        raise nx.NetworkXError(msg)
    if k < 2:
        raise nx.NetworkXError("The cliques must have at least two nodes")

    G = nx.disjoint_union_all(
        itertools.chain(
            [nx.complete_graph(k)], (nx.complete_graph(k - 1) for _ in range(n - 1))
        )
    )
    G.add_edges_from((0, i) for i in range(k, G.number_of_nodes()))
    return G


@py_random_state(3)
@nx._dispatchable(graphs=None, returns_graph=True)
def stochastic_block_model(
    sizes, p, nodelist=None, seed=None, directed=False, selfloops=False, sparse=True
):
    """Returns a stochastic block model graph.

    This model partitions the nodes in blocks of arbitrary sizes, and places
    edges between pairs of nodes independently, with a probability that depends
    on the blocks.

    Parameters
    ----------
    sizes : list of ints
        Sizes of blocks
    p : list of list of floats
        Element (r,s) gives the density of edges going from the nodes
        of group r to nodes of group s.
        p must match the number of groups (len(sizes) == len(p)),
        and it must be symmetric if the graph is undirected.
    nodelist : list, optional
        The block tags are assigned according to the node identifiers
        in nodelist. If nodelist is None, then the ordering is the
        range [0,sum(sizes)-1].
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.
    directed : boolean optional, default=False
        Whether to create a directed graph or not.
    selfloops : boolean optional, default=False
        Whether to include self-loops or not.
    sparse: boolean optional, default=True
        Use the sparse heuristic to speed up the generator.

    Returns
    -------
    g : NetworkX Graph or DiGraph
        Stochastic block model graph of size sum(sizes)

    Raises
    ------
    NetworkXError
      If probabilities are not in [0,1].
      If the probability matrix is not square (directed case).
      If the probability matrix is not symmetric (undirected case).
      If the sizes list does not match nodelist or the probability matrix.
      If nodelist contains duplicate.

    Examples
    --------
    >>> sizes = [75, 75, 300]
    >>> probs = [[0.25, 0.05, 0.02], [0.05, 0.35, 0.07], [0.02, 0.07, 0.40]]
    >>> g = nx.stochastic_block_model(sizes, probs, seed=0)
    >>> len(g)
    450
    >>> H = nx.quotient_graph(g, g.graph["partition"], relabel=True)
    >>> for v in H.nodes(data=True):
    ...     print(round(v[1]["density"], 3))
    0.245
    0.348
    0.405
    >>> for v in H.edges(data=True):
    ...     print(round(1.0 * v[2]["weight"] / (sizes[v[0]] * sizes[v[1]]), 3))
    0.051
    0.022
    0.07

    See Also
    --------
    random_partition_graph
    planted_partition_graph
    gaussian_random_partition_graph
    gnp_random_graph

    References
    ----------
    .. [1] Holland, P. W., Laskey, K. B., & Leinhardt, S.,
           "Stochastic blockmodels: First steps",
           Social networks, 5(2), 109-137, 1983.
    """
    # Check if dimensions match
    if len(sizes) != len(p):
        raise nx.NetworkXException("'sizes' and 'p' do not match.")
    # Check for probability symmetry (undirected) and shape (directed)
    for row in p:
        if len(p) != len(row):
            raise nx.NetworkXException("'p' must be a square matrix.")
    if not directed:
        p_transpose = [list(i) for i in zip(*p)]
        for i in zip(p, p_transpose):
            for j in zip(i[0], i[1]):
                if abs(j[0] - j[1]) > 1e-08:
                    raise nx.NetworkXException("'p' must be symmetric.")
    # Check for probability range
    for row in p:
        for prob in row:
            if prob < 0 or prob > 1:
                raise nx.NetworkXException("Entries of 'p' not in [0,1].")
    # Check for nodelist consistency
    if nodelist is not None:
        if len(nodelist) != sum(sizes):
            raise nx.NetworkXException("'nodelist' and 'sizes' do not match.")
        if len(nodelist) != len(set(nodelist)):
            raise nx.NetworkXException("nodelist contains duplicate.")
    else:
        nodelist = range(sum(sizes))

    # Setup the graph conditionally to the directed switch.
    block_range = range(len(sizes))
    if directed:
        g = nx.DiGraph()
        block_iter = itertools.product(block_range, block_range)
    else:
        g = nx.Graph()
        block_iter = itertools.combinations_with_replacement(block_range, 2)
    # Split nodelist in a partition (list of sets).
    size_cumsum = [sum(sizes[0:x]) for x in range(len(sizes) + 1)]
    g.graph["partition"] = [
        set(nodelist[size_cumsum[x] : size_cumsum[x + 1]])
        for x in range(len(size_cumsum) - 1)
    ]
    # Setup nodes and graph name
    for block_id, nodes in enumerate(g.graph["partition"]):
        for node in nodes:
            g.add_node(node, block=block_id)

    g.name = "stochastic_block_model"

    # Test for edge existence
    parts = g.graph["partition"]
    for i, j in block_iter:
        if i == j:
            if directed:
                if selfloops:
                    edges = itertools.product(parts[i], parts[i])
                else:
                    edges = itertools.permutations(parts[i], 2)
            else:
                edges = itertools.combinations(parts[i], 2)
                if selfloops:
                    edges = itertools.chain(edges, zip(parts[i], parts[i]))
            for e in edges:
                if seed.random() < p[i][j]:
                    g.add_edge(*e)
        else:
            edges = itertools.product(parts[i], parts[j])
        if sparse:
            if p[i][j] == 1:  # Test edges cases p_ij = 0 or 1
                for e in edges:
                    g.add_edge(*e)
            elif p[i][j] > 0:
                while True:
                    try:
                        logrand = math.log(seed.random())
                        skip = math.floor(logrand / math.log(1 - p[i][j]))
                        # consume "skip" edges
                        next(itertools.islice(edges, skip, skip), None)
                        e = next(edges)
                        g.add_edge(*e)  # __safe
                    except StopIteration:
                        break
        else:
            for e in edges:
                if seed.random() < p[i][j]:
                    g.add_edge(*e)  # __safe
    return g


def _zipf_rv_below(gamma, xmin, threshold, seed):
    """Returns a random value chosen from the bounded Zipf distribution.

    Repeatedly draws values from the Zipf distribution until the
    threshold is met, then returns that value.
    """
    result = nx.utils.zipf_rv(gamma, xmin, seed)
    while result > threshold:
        result = nx.utils.zipf_rv(gamma, xmin, seed)
    return result


def _powerlaw_sequence(gamma, low, high, condition, length, max_iters, seed):
    """Returns a list of numbers obeying a constrained power law distribution.

    ``gamma`` and ``low`` are the parameters for the Zipf distribution.

    ``high`` is the maximum allowed value for values draw from the Zipf
    distribution. For more information, see :func:`_zipf_rv_below`.

    ``condition`` and ``length`` are Boolean-valued functions on
    lists. While generating the list, random values are drawn and
    appended to the list until ``length`` is satisfied by the created
    list. Once ``condition`` is satisfied, the sequence generated in
    this way is returned.

    ``max_iters`` indicates the number of times to generate a list
    satisfying ``length``. If the number of iterations exceeds this
    value, :exc:`~networkx.exception.ExceededMaxIterations` is raised.

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.
    """
    for i in range(max_iters):
        seq = []
        while not length(seq):
            seq.append(_zipf_rv_below(gamma, low, high, seed))
        if condition(seq):
            return seq
    raise nx.ExceededMaxIterations("Could not create power law sequence")


def _hurwitz_zeta(x, q, tolerance):
    """The Hurwitz zeta function, or the Riemann zeta function of two arguments.

    ``x`` must be greater than one and ``q`` must be positive.

    This function repeatedly computes subsequent partial sums until
    convergence, as decided by ``tolerance``.
    """
    z = 0
    z_prev = -float("inf")
    k = 0
    while abs(z - z_prev) > tolerance:
        z_prev = z
        z += 1 / ((k + q) ** x)
        k += 1
    return z


def _generate_min_degree(gamma, average_degree, max_degree, tolerance, max_iters):
    """Returns a minimum degree from the given average degree."""
    # Defines zeta function whether or not Scipy is available
    try:
        from scipy.special import zeta
    except ImportError:

        def zeta(x, q):
            return _hurwitz_zeta(x, q, tolerance)

    min_deg_top = max_degree
    min_deg_bot = 1
    min_deg_mid = (min_deg_top - min_deg_bot) / 2 + min_deg_bot
    itrs = 0
    mid_avg_deg = 0
    while abs(mid_avg_deg - average_degree) > tolerance:
        if itrs > max_iters:
            raise nx.ExceededMaxIterations("Could not match average_degree")
        mid_avg_deg = 0
        for x in range(int(min_deg_mid), max_degree + 1):
            mid_avg_deg += (x ** (-gamma + 1)) / zeta(gamma, min_deg_mid)
        if mid_avg_deg > average_degree:
            min_deg_top = min_deg_mid
            min_deg_mid = (min_deg_top - min_deg_bot) / 2 + min_deg_bot
        else:
            min_deg_bot = min_deg_mid
            min_deg_mid = (min_deg_top - min_deg_bot) / 2 + min_deg_bot
        itrs += 1
    # return int(min_deg_mid + 0.5)
    return round(min_deg_mid)


def _generate_communities(degree_seq, community_sizes, mu, max_iters, seed):
    """Returns a list of sets, each of which represents a community.

    ``degree_seq`` is the degree sequence that must be met by the
    graph.

    ``community_sizes`` is the community size distribution that must be
    met by the generated list of sets.

    ``mu`` is a float in the interval [0, 1] indicating the fraction of
    intra-community edges incident to each node.

    ``max_iters`` is the number of times to try to add a node to a
    community. This must be greater than the length of
    ``degree_seq``, otherwise this function will always fail. If
    the number of iterations exceeds this value,
    :exc:`~networkx.exception.ExceededMaxIterations` is raised.

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    The communities returned by this are sets of integers in the set {0,
    ..., *n* - 1}, where *n* is the length of ``degree_seq``.

    """
    # This assumes the nodes in the graph will be natural numbers.
    result = [set() for _ in community_sizes]
    n = len(degree_seq)
    free = list(range(n))
    for i in range(max_iters):
        v = free.pop()
        c = seed.choice(range(len(community_sizes)))
        # s = int(degree_seq[v] * (1 - mu) + 0.5)
        s = round(degree_seq[v] * (1 - mu))
        # If the community is large enough, add the node to the chosen
        # community. Otherwise, return it to the list of unaffiliated
        # nodes.
        if s < community_sizes[c]:
            result[c].add(v)
        else:
            free.append(v)
        # If the community is too big, remove a node from it.
        if len(result[c]) > community_sizes[c]:
            free.append(result[c].pop())
        if not free:
            return result
    msg = "Could not assign communities; try increasing min_community"
    raise nx.ExceededMaxIterations(msg)


@py_random_state(11)
@nx._dispatchable(graphs=None, returns_graph=True)
def LFR_benchmark_graph(
    n,
    tau1,
    tau2,
    mu,
    average_degree=None,
    min_degree=None,
    max_degree=None,
    min_community=None,
    max_community=None,
    tol=1.0e-7,
    max_iters=500,
    seed=None,
):
    r"""Returns the LFR benchmark graph.

    This algorithm proceeds as follows:

    1) Find a degree sequence with a power law distribution, and minimum
       value ``min_degree``, which has approximate average degree
       ``average_degree``. This is accomplished by either

       a) specifying ``min_degree`` and not ``average_degree``,
       b) specifying ``average_degree`` and not ``min_degree``, in which
          case a suitable minimum degree will be found.

       ``max_degree`` can also be specified, otherwise it will be set to
       ``n``. Each node *u* will have $\mu \mathrm{deg}(u)$ edges
       joining it to nodes in communities other than its own and $(1 -
       \mu) \mathrm{deg}(u)$ edges joining it to nodes in its own
       community.
    2) Generate community sizes according to a power law distribution
       with exponent ``tau2``. If ``min_community`` and
       ``max_community`` are not specified they will be selected to be
       ``min_degree`` and ``max_degree``, respectively.  Community sizes
       are generated until the sum of their sizes equals ``n``.
    3) Each node will be randomly assigned a community with the
       condition that the community is large enough for the node's
       intra-community degree, $(1 - \mu) \mathrm{deg}(u)$ as
       described in step 2. If a community grows too large, a random node
       will be selected for reassignment to a new community, until all
       nodes have been assigned a community.
    4) Each node *u* then adds $(1 - \mu) \mathrm{deg}(u)$
       intra-community edges and $\mu \mathrm{deg}(u)$ inter-community
       edges.

    Parameters
    ----------
    n : int
        Number of nodes in the created graph.

    tau1 : float
        Power law exponent for the degree distribution of the created
        graph. This value must be strictly greater than one.

    tau2 : float
        Power law exponent for the community size distribution in the
        created graph. This value must be strictly greater than one.

    mu : float
        Fraction of inter-community edges incident to each node. This
        value must be in the interval [0, 1].

    average_degree : float
        Desired average degree of nodes in the created graph. This value
        must be in the interval [0, *n*]. Exactly one of this and
        ``min_degree`` must be specified, otherwise a
        :exc:`NetworkXError` is raised.

    min_degree : int
        Minimum degree of nodes in the created graph. This value must be
        in the interval [0, *n*]. Exactly one of this and
        ``average_degree`` must be specified, otherwise a
        :exc:`NetworkXError` is raised.

    max_degree : int
        Maximum degree of nodes in the created graph. If not specified,
        this is set to ``n``, the total number of nodes in the graph.

    min_community : int
        Minimum size of communities in the graph. If not specified, this
        is set to ``min_degree``.

    max_community : int
        Maximum size of communities in the graph. If not specified, this
        is set to ``n``, the total number of nodes in the graph.

    tol : float
        Tolerance when comparing floats, specifically when comparing
        average degree values.

    max_iters : int
        Maximum number of iterations to try to create the community sizes,
        degree distribution, and community affiliations.

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    G : NetworkX graph
        The LFR benchmark graph generated according to the specified
        parameters.

        Each node in the graph has a node attribute ``'community'`` that
        stores the community (that is, the set of nodes) that includes
        it.

    Raises
    ------
    NetworkXError
        If any of the parameters do not meet their upper and lower bounds:

        - ``tau1`` and ``tau2`` must be strictly greater than 1.
        - ``mu`` must be in [0, 1].
        - ``max_degree`` must be in {1, ..., *n*}.
        - ``min_community`` and ``max_community`` must be in {0, ...,
          *n*}.

        If not exactly one of ``average_degree`` and ``min_degree`` is
        specified.

        If ``min_degree`` is not specified and a suitable ``min_degree``
        cannot be found.

    ExceededMaxIterations
        If a valid degree sequence cannot be created within
        ``max_iters`` number of iterations.

        If a valid set of community sizes cannot be created within
        ``max_iters`` number of iterations.

        If a valid community assignment cannot be created within ``10 *
        n * max_iters`` number of iterations.

    Examples
    --------
    Basic usage::

        >>> from networkx.generators.community import LFR_benchmark_graph
        >>> n = 250
        >>> tau1 = 3
        >>> tau2 = 1.5
        >>> mu = 0.1
        >>> G = LFR_benchmark_graph(
        ...     n, tau1, tau2, mu, average_degree=5, min_community=20, seed=10
        ... )

    Continuing the example above, you can get the communities from the
    node attributes of the graph::

        >>> communities = {frozenset(G.nodes[v]["community"]) for v in G}

    Notes
    -----
    This algorithm differs slightly from the original way it was
    presented in [1].

    1) Rather than connecting the graph via a configuration model then
       rewiring to match the intra-community and inter-community
       degrees, we do this wiring explicitly at the end, which should be
       equivalent.
    2) The code posted on the author's website [2] calculates the random
       power law distributed variables and their average using
       continuous approximations, whereas we use the discrete
       distributions here as both degree and community size are
       discrete.

    Though the authors describe the algorithm as quite robust, testing
    during development indicates that a somewhat narrower parameter set
    is likely to successfully produce a graph. Some suggestions have
    been provided in the event of exceptions.

    References
    ----------
    .. [1] "Benchmark graphs for testing community detection algorithms",
           Andrea Lancichinetti, Santo Fortunato, and Filippo Radicchi,
           Phys. Rev. E 78, 046110 2008
    .. [2] https://www.santofortunato.net/resources

    """
    # Perform some basic parameter validation.
    if not tau1 > 1:
        raise nx.NetworkXError("tau1 must be greater than one")
    if not tau2 > 1:
        raise nx.NetworkXError("tau2 must be greater than one")
    if not 0 <= mu <= 1:
        raise nx.NetworkXError("mu must be in the interval [0, 1]")

    # Validate parameters for generating the degree sequence.
    if max_degree is None:
        max_degree = n
    elif not 0 < max_degree <= n:
        raise nx.NetworkXError("max_degree must be in the interval (0, n]")
    if not ((min_degree is None) ^ (average_degree is None)):
        raise nx.NetworkXError(
            "Must assign exactly one of min_degree and average_degree"
        )
    if min_degree is None:
        min_degree = _generate_min_degree(
            tau1, average_degree, max_degree, tol, max_iters
        )

    # Generate a degree sequence with a power law distribution.
    low, high = min_degree, max_degree

    def condition(seq):
        return sum(seq) % 2 == 0

    def length(seq):
        return len(seq) >= n

    deg_seq = _powerlaw_sequence(tau1, low, high, condition, length, max_iters, seed)

    # Validate parameters for generating the community size sequence.
    if min_community is None:
        min_community = min(deg_seq)
    if max_community is None:
        max_community = max(deg_seq)

    # Generate a community size sequence with a power law distribution.
    #
    # TODO The original code incremented the number of iterations each
    # time a new Zipf random value was drawn from the distribution. This
    # differed from the way the number of iterations was incremented in
    # `_powerlaw_degree_sequence`, so this code was changed to match
    # that one. As a result, this code is allowed many more chances to
    # generate a valid community size sequence.
    low, high = min_community, max_community

    def condition(seq):
        return sum(seq) == n

    def length(seq):
        return sum(seq) >= n

    comms = _powerlaw_sequence(tau2, low, high, condition, length, max_iters, seed)

    # Generate the communities based on the given degree sequence and
    # community sizes.
    max_iters *= 10 * n
    communities = _generate_communities(deg_seq, comms, mu, max_iters, seed)

    # Finally, generate the benchmark graph based on the given
    # communities, joining nodes according to the intra- and
    # inter-community degrees.
    G = nx.Graph()
    G.add_nodes_from(range(n))
    for c in communities:
        for u in c:
            while G.degree(u) < round(deg_seq[u] * (1 - mu)):
                v = seed.choice(list(c))
                G.add_edge(u, v)
            while G.degree(u) < deg_seq[u]:
                v = seed.choice(range(n))
                if v not in c:
                    G.add_edge(u, v)
            G.nodes[u]["community"] = c
    return G
