# See https://github.com/networkx/networkx/pull/1474
# Copyright 2011 Reya Group <http://www.reyagroup.com>
# Copyright 2011 Alex Levenson <alex@isnotinvain.com>
# Copyright 2011 Diederik van Liere <diederik.vanliere@rotman.utoronto.ca>
"""Functions for analyzing triads of a graph."""

from collections import defaultdict
from itertools import combinations, permutations

import networkx as nx
from networkx.utils import not_implemented_for, py_random_state

__all__ = [
    "triadic_census",
    "is_triad",
    "all_triplets",
    "all_triads",
    "triads_by_type",
    "triad_type",
    "random_triad",
]

#: The integer codes representing each type of triad.
#:
#: Triads that are the same up to symmetry have the same code.
TRICODES = (
    1,
    2,
    2,
    3,
    2,
    4,
    6,
    8,
    2,
    6,
    5,
    7,
    3,
    8,
    7,
    11,
    2,
    6,
    4,
    8,
    5,
    9,
    9,
    13,
    6,
    10,
    9,
    14,
    7,
    14,
    12,
    15,
    2,
    5,
    6,
    7,
    6,
    9,
    10,
    14,
    4,
    9,
    9,
    12,
    8,
    13,
    14,
    15,
    3,
    7,
    8,
    11,
    7,
    12,
    14,
    15,
    8,
    14,
    13,
    15,
    11,
    15,
    15,
    16,
)

#: The names of each type of triad. The order of the elements is
#: important: it corresponds to the tricodes given in :data:`TRICODES`.
TRIAD_NAMES = (
    "003",
    "012",
    "102",
    "021D",
    "021U",
    "021C",
    "111D",
    "111U",
    "030T",
    "030C",
    "201",
    "120D",
    "120U",
    "120C",
    "210",
    "300",
)


#: A dictionary mapping triad code to triad name.
TRICODE_TO_NAME = {i: TRIAD_NAMES[code - 1] for i, code in enumerate(TRICODES)}


def _tricode(G, v, u, w):
    """Returns the integer code of the given triad.

    This is some fancy magic that comes from Batagelj and Mrvar's paper. It
    treats each edge joining a pair of `v`, `u`, and `w` as a bit in
    the binary representation of an integer.

    """
    combos = ((v, u, 1), (u, v, 2), (v, w, 4), (w, v, 8), (u, w, 16), (w, u, 32))
    return sum(x for u, v, x in combos if v in G[u])


@not_implemented_for("undirected")
@nx._dispatchable
def triadic_census(G, nodelist=None):
    """Determines the triadic census of a directed graph.

    The triadic census is a count of how many of the 16 possible types of
    triads are present in a directed graph. If a list of nodes is passed, then
    only those triads are taken into account which have elements of nodelist in them.

    Parameters
    ----------
    G : digraph
       A NetworkX DiGraph
    nodelist : list
        List of nodes for which you want to calculate triadic census

    Returns
    -------
    census : dict
       Dictionary with triad type as keys and number of occurrences as values.

    Examples
    --------
    >>> G = nx.DiGraph([(1, 2), (2, 3), (3, 1), (3, 4), (4, 1), (4, 2)])
    >>> triadic_census = nx.triadic_census(G)
    >>> for key, value in triadic_census.items():
    ...     print(f"{key}: {value}")
    003: 0
    012: 0
    102: 0
    021D: 0
    021U: 0
    021C: 0
    111D: 0
    111U: 0
    030T: 2
    030C: 2
    201: 0
    120D: 0
    120U: 0
    120C: 0
    210: 0
    300: 0

    Notes
    -----
    This algorithm has complexity $O(m)$ where $m$ is the number of edges in
    the graph.

    For undirected graphs, the triadic census can be computed by first converting
    the graph into a directed graph using the ``G.to_directed()`` method.
    After this conversion, only the triad types 003, 102, 201 and 300 will be
    present in the undirected scenario.

    Raises
    ------
    ValueError
        If `nodelist` contains duplicate nodes or nodes not in `G`.
        If you want to ignore this you can preprocess with `set(nodelist) & G.nodes`

    See also
    --------
    triad_graph

    References
    ----------
    .. [1] Vladimir Batagelj and Andrej Mrvar, A subquadratic triad census
        algorithm for large sparse networks with small maximum degree,
        University of Ljubljana,
        http://vlado.fmf.uni-lj.si/pub/networks/doc/triads/triads.pdf

    """
    nodeset = set(G.nbunch_iter(nodelist))
    if nodelist is not None and len(nodelist) != len(nodeset):
        raise ValueError("nodelist includes duplicate nodes or nodes not in G")

    N = len(G)
    Nnot = N - len(nodeset)  # can signal special counting for subset of nodes

    # create an ordering of nodes with nodeset nodes first
    m = {n: i for i, n in enumerate(nodeset)}
    if Nnot:
        # add non-nodeset nodes later in the ordering
        not_nodeset = G.nodes - nodeset
        m.update((n, i + N) for i, n in enumerate(not_nodeset))

    # build all_neighbor dicts for easy counting
    # After Python 3.8 can leave off these keys(). Speedup also using G._pred
    # nbrs = {n: G._pred[n].keys() | G._succ[n].keys() for n in G}
    nbrs = {n: G.pred[n].keys() | G.succ[n].keys() for n in G}
    dbl_nbrs = {n: G.pred[n].keys() & G.succ[n].keys() for n in G}

    if Nnot:
        sgl_nbrs = {n: G.pred[n].keys() ^ G.succ[n].keys() for n in not_nodeset}
        # find number of edges not incident to nodes in nodeset
        sgl = sum(1 for n in not_nodeset for nbr in sgl_nbrs[n] if nbr not in nodeset)
        sgl_edges_outside = sgl // 2
        dbl = sum(1 for n in not_nodeset for nbr in dbl_nbrs[n] if nbr not in nodeset)
        dbl_edges_outside = dbl // 2

    # Initialize the count for each triad to be zero.
    census = {name: 0 for name in TRIAD_NAMES}
    # Main loop over nodes
    for v in nodeset:
        vnbrs = nbrs[v]
        dbl_vnbrs = dbl_nbrs[v]
        if Nnot:
            # set up counts of edges attached to v.
            sgl_unbrs_bdy = sgl_unbrs_out = dbl_unbrs_bdy = dbl_unbrs_out = 0
        for u in vnbrs:
            if m[u] <= m[v]:
                continue
            unbrs = nbrs[u]
            neighbors = (vnbrs | unbrs) - {u, v}
            # Count connected triads.
            for w in neighbors:
                if m[u] < m[w] or (m[v] < m[w] < m[u] and v not in nbrs[w]):
                    code = _tricode(G, v, u, w)
                    census[TRICODE_TO_NAME[code]] += 1

            # Use a formula for dyadic triads with edge incident to v
            if u in dbl_vnbrs:
                census["102"] += N - len(neighbors) - 2
            else:
                census["012"] += N - len(neighbors) - 2

            # Count edges attached to v. Subtract later to get triads with v isolated
            # _out are (u,unbr) for unbrs outside boundary of nodeset
            # _bdy are (u,unbr) for unbrs on boundary of nodeset (get double counted)
            if Nnot and u not in nodeset:
                sgl_unbrs = sgl_nbrs[u]
                sgl_unbrs_bdy += len(sgl_unbrs & vnbrs - nodeset)
                sgl_unbrs_out += len(sgl_unbrs - vnbrs - nodeset)
                dbl_unbrs = dbl_nbrs[u]
                dbl_unbrs_bdy += len(dbl_unbrs & vnbrs - nodeset)
                dbl_unbrs_out += len(dbl_unbrs - vnbrs - nodeset)
        # if nodeset == G.nodes, skip this b/c we will find the edge later.
        if Nnot:
            # Count edges outside nodeset not connected with v (v isolated triads)
            census["012"] += sgl_edges_outside - (sgl_unbrs_out + sgl_unbrs_bdy // 2)
            census["102"] += dbl_edges_outside - (dbl_unbrs_out + dbl_unbrs_bdy // 2)

    # calculate null triads: "003"
    # null triads = total number of possible triads - all found triads
    total_triangles = (N * (N - 1) * (N - 2)) // 6
    triangles_without_nodeset = (Nnot * (Nnot - 1) * (Nnot - 2)) // 6
    total_census = total_triangles - triangles_without_nodeset
    census["003"] = total_census - sum(census.values())

    return census


@nx._dispatchable
def is_triad(G):
    """Returns True if the graph G is a triad, else False.

    Parameters
    ----------
    G : graph
       A NetworkX Graph

    Returns
    -------
    istriad : boolean
       Whether G is a valid triad

    Examples
    --------
    >>> G = nx.DiGraph([(1, 2), (2, 3), (3, 1)])
    >>> nx.is_triad(G)
    True
    >>> G.add_edge(0, 1)
    >>> nx.is_triad(G)
    False
    """
    if isinstance(G, nx.Graph):
        if G.order() == 3 and nx.is_directed(G):
            if not any((n, n) in G.edges() for n in G.nodes()):
                return True
    return False


@not_implemented_for("undirected")
@nx._dispatchable
def all_triplets(G):
    """Returns a generator of all possible sets of 3 nodes in a DiGraph.

    .. deprecated:: 3.3

       all_triplets is deprecated and will be removed in NetworkX version 3.5.
       Use `itertools.combinations` instead::

          all_triplets = itertools.combinations(G, 3)

    Parameters
    ----------
    G : digraph
       A NetworkX DiGraph

    Returns
    -------
    triplets : generator of 3-tuples
       Generator of tuples of 3 nodes

    Examples
    --------
    >>> G = nx.DiGraph([(1, 2), (2, 3), (3, 4)])
    >>> list(nx.all_triplets(G))
    [(1, 2, 3), (1, 2, 4), (1, 3, 4), (2, 3, 4)]

    """
    import warnings

    warnings.warn(
        (
            "\n\nall_triplets is deprecated and will be removed in v3.5.\n"
            "Use `itertools.combinations(G, 3)` instead."
        ),
        category=DeprecationWarning,
        stacklevel=4,
    )
    triplets = combinations(G.nodes(), 3)
    return triplets


@not_implemented_for("undirected")
@nx._dispatchable(returns_graph=True)
def all_triads(G):
    """A generator of all possible triads in G.

    Parameters
    ----------
    G : digraph
       A NetworkX DiGraph

    Returns
    -------
    all_triads : generator of DiGraphs
       Generator of triads (order-3 DiGraphs)

    Examples
    --------
    >>> G = nx.DiGraph([(1, 2), (2, 3), (3, 1), (3, 4), (4, 1), (4, 2)])
    >>> for triad in nx.all_triads(G):
    ...     print(triad.edges)
    [(1, 2), (2, 3), (3, 1)]
    [(1, 2), (4, 1), (4, 2)]
    [(3, 1), (3, 4), (4, 1)]
    [(2, 3), (3, 4), (4, 2)]

    """
    triplets = combinations(G.nodes(), 3)
    for triplet in triplets:
        yield G.subgraph(triplet).copy()


@not_implemented_for("undirected")
@nx._dispatchable
def triads_by_type(G):
    """Returns a list of all triads for each triad type in a directed graph.
    There are exactly 16 different types of triads possible. Suppose 1, 2, 3 are three
    nodes, they will be classified as a particular triad type if their connections
    are as follows:

    - 003: 1, 2, 3
    - 012: 1 -> 2, 3
    - 102: 1 <-> 2, 3
    - 021D: 1 <- 2 -> 3
    - 021U: 1 -> 2 <- 3
    - 021C: 1 -> 2 -> 3
    - 111D: 1 <-> 2 <- 3
    - 111U: 1 <-> 2 -> 3
    - 030T: 1 -> 2 -> 3, 1 -> 3
    - 030C: 1 <- 2 <- 3, 1 -> 3
    - 201: 1 <-> 2 <-> 3
    - 120D: 1 <- 2 -> 3, 1 <-> 3
    - 120U: 1 -> 2 <- 3, 1 <-> 3
    - 120C: 1 -> 2 -> 3, 1 <-> 3
    - 210: 1 -> 2 <-> 3, 1 <-> 3
    - 300: 1 <-> 2 <-> 3, 1 <-> 3

    Refer to the :doc:`example gallery </auto_examples/graph/plot_triad_types>`
    for visual examples of the triad types.

    Parameters
    ----------
    G : digraph
       A NetworkX DiGraph

    Returns
    -------
    tri_by_type : dict
       Dictionary with triad types as keys and lists of triads as values.

    Examples
    --------
    >>> G = nx.DiGraph([(1, 2), (1, 3), (2, 3), (3, 1), (5, 6), (5, 4), (6, 7)])
    >>> dict = nx.triads_by_type(G)
    >>> dict["120C"][0].edges()
    OutEdgeView([(1, 2), (1, 3), (2, 3), (3, 1)])
    >>> dict["012"][0].edges()
    OutEdgeView([(1, 2)])

    References
    ----------
    .. [1] Snijders, T. (2012). "Transitivity and triads." University of
        Oxford.
        https://web.archive.org/web/20170830032057/http://www.stats.ox.ac.uk/~snijders/Trans_Triads_ha.pdf
    """
    # num_triads = o * (o - 1) * (o - 2) // 6
    # if num_triads > TRIAD_LIMIT: print(WARNING)
    all_tri = all_triads(G)
    tri_by_type = defaultdict(list)
    for triad in all_tri:
        name = triad_type(triad)
        tri_by_type[name].append(triad)
    return tri_by_type


@not_implemented_for("undirected")
@nx._dispatchable
def triad_type(G):
    """Returns the sociological triad type for a triad.

    Parameters
    ----------
    G : digraph
       A NetworkX DiGraph with 3 nodes

    Returns
    -------
    triad_type : str
       A string identifying the triad type

    Examples
    --------
    >>> G = nx.DiGraph([(1, 2), (2, 3), (3, 1)])
    >>> nx.triad_type(G)
    '030C'
    >>> G.add_edge(1, 3)
    >>> nx.triad_type(G)
    '120C'

    Notes
    -----
    There can be 6 unique edges in a triad (order-3 DiGraph) (so 2^^6=64 unique
    triads given 3 nodes). These 64 triads each display exactly 1 of 16
    topologies of triads (topologies can be permuted). These topologies are
    identified by the following notation:

    {m}{a}{n}{type} (for example: 111D, 210, 102)

    Here:

    {m}     = number of mutual ties (takes 0, 1, 2, 3); a mutual tie is (0,1)
              AND (1,0)
    {a}     = number of asymmetric ties (takes 0, 1, 2, 3); an asymmetric tie
              is (0,1) BUT NOT (1,0) or vice versa
    {n}     = number of null ties (takes 0, 1, 2, 3); a null tie is NEITHER
              (0,1) NOR (1,0)
    {type}  = a letter (takes U, D, C, T) corresponding to up, down, cyclical
              and transitive. This is only used for topologies that can have
              more than one form (eg: 021D and 021U).

    References
    ----------
    .. [1] Snijders, T. (2012). "Transitivity and triads." University of
        Oxford.
        https://web.archive.org/web/20170830032057/http://www.stats.ox.ac.uk/~snijders/Trans_Triads_ha.pdf
    """
    if not is_triad(G):
        raise nx.NetworkXAlgorithmError("G is not a triad (order-3 DiGraph)")
    num_edges = len(G.edges())
    if num_edges == 0:
        return "003"
    elif num_edges == 1:
        return "012"
    elif num_edges == 2:
        e1, e2 = G.edges()
        if set(e1) == set(e2):
            return "102"
        elif e1[0] == e2[0]:
            return "021D"
        elif e1[1] == e2[1]:
            return "021U"
        elif e1[1] == e2[0] or e2[1] == e1[0]:
            return "021C"
    elif num_edges == 3:
        for e1, e2, e3 in permutations(G.edges(), 3):
            if set(e1) == set(e2):
                if e3[0] in e1:
                    return "111U"
                # e3[1] in e1:
                return "111D"
            elif set(e1).symmetric_difference(set(e2)) == set(e3):
                if {e1[0], e2[0], e3[0]} == {e1[0], e2[0], e3[0]} == set(G.nodes()):
                    return "030C"
                # e3 == (e1[0], e2[1]) and e2 == (e1[1], e3[1]):
                return "030T"
    elif num_edges == 4:
        for e1, e2, e3, e4 in permutations(G.edges(), 4):
            if set(e1) == set(e2):
                # identify pair of symmetric edges (which necessarily exists)
                if set(e3) == set(e4):
                    return "201"
                if {e3[0]} == {e4[0]} == set(e3).intersection(set(e4)):
                    return "120D"
                if {e3[1]} == {e4[1]} == set(e3).intersection(set(e4)):
                    return "120U"
                if e3[1] == e4[0]:
                    return "120C"
    elif num_edges == 5:
        return "210"
    elif num_edges == 6:
        return "300"


@not_implemented_for("undirected")
@py_random_state(1)
@nx._dispatchable(preserve_all_attrs=True, returns_graph=True)
def random_triad(G, seed=None):
    """Returns a random triad from a directed graph.

    .. deprecated:: 3.3

       random_triad is deprecated and will be removed in version 3.5.
       Use random sampling directly instead::

          G.subgraph(random.sample(list(G), 3))

    Parameters
    ----------
    G : digraph
       A NetworkX DiGraph
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    G2 : subgraph
       A randomly selected triad (order-3 NetworkX DiGraph)

    Raises
    ------
    NetworkXError
        If the input Graph has less than 3 nodes.

    Examples
    --------
    >>> G = nx.DiGraph([(1, 2), (1, 3), (2, 3), (3, 1), (5, 6), (5, 4), (6, 7)])
    >>> triad = nx.random_triad(G, seed=1)
    >>> triad.edges
    OutEdgeView([(1, 2)])

    """
    import warnings

    warnings.warn(
        (
            "\n\nrandom_triad is deprecated and will be removed in NetworkX v3.5.\n"
            "Use random.sample instead, e.g.::\n\n"
            "\tG.subgraph(random.sample(list(G), 3))\n"
        ),
        category=DeprecationWarning,
        stacklevel=5,
    )
    if len(G) < 3:
        raise nx.NetworkXError(
            f"G needs at least 3 nodes to form a triad; (it has {len(G)} nodes)"
        )
    nodes = seed.sample(list(G.nodes()), 3)
    G2 = G.subgraph(nodes)
    return G2
