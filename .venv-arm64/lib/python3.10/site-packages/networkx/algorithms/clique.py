"""Functions for finding and manipulating cliques.

Finding the largest clique in a graph is NP-complete problem, so most of
these algorithms have an exponential running time; for more information,
see the Wikipedia article on the clique problem [1]_.

.. [1] clique problem:: https://en.wikipedia.org/wiki/Clique_problem

"""

from collections import defaultdict, deque
from itertools import chain, combinations, islice

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = [
    "find_cliques",
    "find_cliques_recursive",
    "make_max_clique_graph",
    "make_clique_bipartite",
    "node_clique_number",
    "number_of_cliques",
    "enumerate_all_cliques",
    "max_weight_clique",
]


@not_implemented_for("directed")
@nx._dispatchable
def enumerate_all_cliques(G):
    """Returns all cliques in an undirected graph.

    This function returns an iterator over cliques, each of which is a
    list of nodes. The iteration is ordered by cardinality of the
    cliques: first all cliques of size one, then all cliques of size
    two, etc.

    Parameters
    ----------
    G : NetworkX graph
        An undirected graph.

    Returns
    -------
    iterator
        An iterator over cliques, each of which is a list of nodes in
        `G`. The cliques are ordered according to size.

    Notes
    -----
    To obtain a list of all cliques, use
    `list(enumerate_all_cliques(G))`. However, be aware that in the
    worst-case, the length of this list can be exponential in the number
    of nodes in the graph (for example, when the graph is the complete
    graph). This function avoids storing all cliques in memory by only
    keeping current candidate node lists in memory during its search.

    The implementation is adapted from the algorithm by Zhang, et
    al. (2005) [1]_ to output all cliques discovered.

    This algorithm ignores self-loops and parallel edges, since cliques
    are not conventionally defined with such edges.

    References
    ----------
    .. [1] Yun Zhang, Abu-Khzam, F.N., Baldwin, N.E., Chesler, E.J.,
           Langston, M.A., Samatova, N.F.,
           "Genome-Scale Computational Approaches to Memory-Intensive
           Applications in Systems Biology".
           *Supercomputing*, 2005. Proceedings of the ACM/IEEE SC 2005
           Conference, pp. 12, 12--18 Nov. 2005.
           <https://doi.org/10.1109/SC.2005.29>.

    """
    index = {}
    nbrs = {}
    for u in G:
        index[u] = len(index)
        # Neighbors of u that appear after u in the iteration order of G.
        nbrs[u] = {v for v in G[u] if v not in index}

    queue = deque(([u], sorted(nbrs[u], key=index.__getitem__)) for u in G)
    # Loop invariants:
    # 1. len(base) is nondecreasing.
    # 2. (base + cnbrs) is sorted with respect to the iteration order of G.
    # 3. cnbrs is a set of common neighbors of nodes in base.
    while queue:
        base, cnbrs = map(list, queue.popleft())
        yield base
        for i, u in enumerate(cnbrs):
            # Use generators to reduce memory consumption.
            queue.append(
                (
                    chain(base, [u]),
                    filter(nbrs[u].__contains__, islice(cnbrs, i + 1, None)),
                )
            )


@not_implemented_for("directed")
@nx._dispatchable
def find_cliques(G, nodes=None):
    """Returns all maximal cliques in an undirected graph.

    For each node *n*, a *maximal clique for n* is a largest complete
    subgraph containing *n*. The largest maximal clique is sometimes
    called the *maximum clique*.

    This function returns an iterator over cliques, each of which is a
    list of nodes. It is an iterative implementation, so should not
    suffer from recursion depth issues.

    This function accepts a list of `nodes` and only the maximal cliques
    containing all of these `nodes` are returned. It can considerably speed up
    the running time if some specific cliques are desired.

    Parameters
    ----------
    G : NetworkX graph
        An undirected graph.

    nodes : list, optional (default=None)
        If provided, only yield *maximal cliques* containing all nodes in `nodes`.
        If `nodes` isn't a clique itself, a ValueError is raised.

    Returns
    -------
    iterator
        An iterator over maximal cliques, each of which is a list of
        nodes in `G`. If `nodes` is provided, only the maximal cliques
        containing all the nodes in `nodes` are returned. The order of
        cliques is arbitrary.

    Raises
    ------
    ValueError
        If `nodes` is not a clique.

    Examples
    --------
    >>> from pprint import pprint  # For nice dict formatting
    >>> G = nx.karate_club_graph()
    >>> sum(1 for c in nx.find_cliques(G))  # The number of maximal cliques in G
    36
    >>> max(nx.find_cliques(G), key=len)  # The largest maximal clique in G
    [0, 1, 2, 3, 13]

    The size of the largest maximal clique is known as the *clique number* of
    the graph, which can be found directly with:

    >>> max(len(c) for c in nx.find_cliques(G))
    5

    One can also compute the number of maximal cliques in `G` that contain a given
    node. The following produces a dictionary keyed by node whose
    values are the number of maximal cliques in `G` that contain the node:

    >>> pprint({n: sum(1 for c in nx.find_cliques(G) if n in c) for n in G})
    {0: 13,
     1: 6,
     2: 7,
     3: 3,
     4: 2,
     5: 3,
     6: 3,
     7: 1,
     8: 3,
     9: 2,
     10: 2,
     11: 1,
     12: 1,
     13: 2,
     14: 1,
     15: 1,
     16: 1,
     17: 1,
     18: 1,
     19: 2,
     20: 1,
     21: 1,
     22: 1,
     23: 3,
     24: 2,
     25: 2,
     26: 1,
     27: 3,
     28: 2,
     29: 2,
     30: 2,
     31: 4,
     32: 9,
     33: 14}

    Or, similarly, the maximal cliques in `G` that contain a given node.
    For example, the 4 maximal cliques that contain node 31:

    >>> [c for c in nx.find_cliques(G) if 31 in c]
    [[0, 31], [33, 32, 31], [33, 28, 31], [24, 25, 31]]

    See Also
    --------
    find_cliques_recursive
        A recursive version of the same algorithm.

    Notes
    -----
    To obtain a list of all maximal cliques, use
    `list(find_cliques(G))`. However, be aware that in the worst-case,
    the length of this list can be exponential in the number of nodes in
    the graph. This function avoids storing all cliques in memory by
    only keeping current candidate node lists in memory during its search.

    This implementation is based on the algorithm published by Bron and
    Kerbosch (1973) [1]_, as adapted by Tomita, Tanaka and Takahashi
    (2006) [2]_ and discussed in Cazals and Karande (2008) [3]_. It
    essentially unrolls the recursion used in the references to avoid
    issues of recursion stack depth (for a recursive implementation, see
    :func:`find_cliques_recursive`).

    This algorithm ignores self-loops and parallel edges, since cliques
    are not conventionally defined with such edges.

    References
    ----------
    .. [1] Bron, C. and Kerbosch, J.
       "Algorithm 457: finding all cliques of an undirected graph".
       *Communications of the ACM* 16, 9 (Sep. 1973), 575--577.
       <http://portal.acm.org/citation.cfm?doid=362342.362367>

    .. [2] Etsuji Tomita, Akira Tanaka, Haruhisa Takahashi,
       "The worst-case time complexity for generating all maximal
       cliques and computational experiments",
       *Theoretical Computer Science*, Volume 363, Issue 1,
       Computing and Combinatorics,
       10th Annual International Conference on
       Computing and Combinatorics (COCOON 2004), 25 October 2006, Pages 28--42
       <https://doi.org/10.1016/j.tcs.2006.06.015>

    .. [3] F. Cazals, C. Karande,
       "A note on the problem of reporting maximal cliques",
       *Theoretical Computer Science*,
       Volume 407, Issues 1--3, 6 November 2008, Pages 564--568,
       <https://doi.org/10.1016/j.tcs.2008.05.010>

    """
    if len(G) == 0:
        return

    adj = {u: {v for v in G[u] if v != u} for u in G}

    # Initialize Q with the given nodes and subg, cand with their nbrs
    Q = nodes[:] if nodes is not None else []
    cand = set(G)
    for node in Q:
        if node not in cand:
            raise ValueError(f"The given `nodes` {nodes} do not form a clique")
        cand &= adj[node]

    if not cand:
        yield Q[:]
        return

    subg = cand.copy()
    stack = []
    Q.append(None)

    u = max(subg, key=lambda u: len(cand & adj[u]))
    ext_u = cand - adj[u]

    try:
        while True:
            if ext_u:
                q = ext_u.pop()
                cand.remove(q)
                Q[-1] = q
                adj_q = adj[q]
                subg_q = subg & adj_q
                if not subg_q:
                    yield Q[:]
                else:
                    cand_q = cand & adj_q
                    if cand_q:
                        stack.append((subg, cand, ext_u))
                        Q.append(None)
                        subg = subg_q
                        cand = cand_q
                        u = max(subg, key=lambda u: len(cand & adj[u]))
                        ext_u = cand - adj[u]
            else:
                Q.pop()
                subg, cand, ext_u = stack.pop()
    except IndexError:
        pass


# TODO Should this also be not implemented for directed graphs?
@nx._dispatchable
def find_cliques_recursive(G, nodes=None):
    """Returns all maximal cliques in a graph.

    For each node *v*, a *maximal clique for v* is a largest complete
    subgraph containing *v*. The largest maximal clique is sometimes
    called the *maximum clique*.

    This function returns an iterator over cliques, each of which is a
    list of nodes. It is a recursive implementation, so may suffer from
    recursion depth issues, but is included for pedagogical reasons.
    For a non-recursive implementation, see :func:`find_cliques`.

    This function accepts a list of `nodes` and only the maximal cliques
    containing all of these `nodes` are returned. It can considerably speed up
    the running time if some specific cliques are desired.

    Parameters
    ----------
    G : NetworkX graph

    nodes : list, optional (default=None)
        If provided, only yield *maximal cliques* containing all nodes in `nodes`.
        If `nodes` isn't a clique itself, a ValueError is raised.

    Returns
    -------
    iterator
        An iterator over maximal cliques, each of which is a list of
        nodes in `G`. If `nodes` is provided, only the maximal cliques
        containing all the nodes in `nodes` are yielded. The order of
        cliques is arbitrary.

    Raises
    ------
    ValueError
        If `nodes` is not a clique.

    See Also
    --------
    find_cliques
        An iterative version of the same algorithm. See docstring for examples.

    Notes
    -----
    To obtain a list of all maximal cliques, use
    `list(find_cliques_recursive(G))`. However, be aware that in the
    worst-case, the length of this list can be exponential in the number
    of nodes in the graph. This function avoids storing all cliques in memory
    by only keeping current candidate node lists in memory during its search.

    This implementation is based on the algorithm published by Bron and
    Kerbosch (1973) [1]_, as adapted by Tomita, Tanaka and Takahashi
    (2006) [2]_ and discussed in Cazals and Karande (2008) [3]_. For a
    non-recursive implementation, see :func:`find_cliques`.

    This algorithm ignores self-loops and parallel edges, since cliques
    are not conventionally defined with such edges.

    References
    ----------
    .. [1] Bron, C. and Kerbosch, J.
       "Algorithm 457: finding all cliques of an undirected graph".
       *Communications of the ACM* 16, 9 (Sep. 1973), 575--577.
       <http://portal.acm.org/citation.cfm?doid=362342.362367>

    .. [2] Etsuji Tomita, Akira Tanaka, Haruhisa Takahashi,
       "The worst-case time complexity for generating all maximal
       cliques and computational experiments",
       *Theoretical Computer Science*, Volume 363, Issue 1,
       Computing and Combinatorics,
       10th Annual International Conference on
       Computing and Combinatorics (COCOON 2004), 25 October 2006, Pages 28--42
       <https://doi.org/10.1016/j.tcs.2006.06.015>

    .. [3] F. Cazals, C. Karande,
       "A note on the problem of reporting maximal cliques",
       *Theoretical Computer Science*,
       Volume 407, Issues 1--3, 6 November 2008, Pages 564--568,
       <https://doi.org/10.1016/j.tcs.2008.05.010>

    """
    if len(G) == 0:
        return iter([])

    adj = {u: {v for v in G[u] if v != u} for u in G}

    # Initialize Q with the given nodes and subg, cand with their nbrs
    Q = nodes[:] if nodes is not None else []
    cand_init = set(G)
    for node in Q:
        if node not in cand_init:
            raise ValueError(f"The given `nodes` {nodes} do not form a clique")
        cand_init &= adj[node]

    if not cand_init:
        return iter([Q])

    subg_init = cand_init.copy()

    def expand(subg, cand):
        u = max(subg, key=lambda u: len(cand & adj[u]))
        for q in cand - adj[u]:
            cand.remove(q)
            Q.append(q)
            adj_q = adj[q]
            subg_q = subg & adj_q
            if not subg_q:
                yield Q[:]
            else:
                cand_q = cand & adj_q
                if cand_q:
                    yield from expand(subg_q, cand_q)
            Q.pop()

    return expand(subg_init, cand_init)


@nx._dispatchable(returns_graph=True)
def make_max_clique_graph(G, create_using=None):
    """Returns the maximal clique graph of the given graph.

    The nodes of the maximal clique graph of `G` are the cliques of
    `G` and an edge joins two cliques if the cliques are not disjoint.

    Parameters
    ----------
    G : NetworkX graph

    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    NetworkX graph
        A graph whose nodes are the cliques of `G` and whose edges
        join two cliques if they are not disjoint.

    Notes
    -----
    This function behaves like the following code::

        import networkx as nx

        G = nx.make_clique_bipartite(G)
        cliques = [v for v in G.nodes() if G.nodes[v]["bipartite"] == 0]
        G = nx.bipartite.projected_graph(G, cliques)
        G = nx.relabel_nodes(G, {-v: v - 1 for v in G})

    It should be faster, though, since it skips all the intermediate
    steps.

    """
    if create_using is None:
        B = G.__class__()
    else:
        B = nx.empty_graph(0, create_using)
    cliques = list(enumerate(set(c) for c in find_cliques(G)))
    # Add a numbered node for each clique.
    B.add_nodes_from(i for i, c in cliques)
    # Join cliques by an edge if they share a node.
    clique_pairs = combinations(cliques, 2)
    B.add_edges_from((i, j) for (i, c1), (j, c2) in clique_pairs if c1 & c2)
    return B


@nx._dispatchable(returns_graph=True)
def make_clique_bipartite(G, fpos=None, create_using=None, name=None):
    """Returns the bipartite clique graph corresponding to `G`.

    In the returned bipartite graph, the "bottom" nodes are the nodes of
    `G` and the "top" nodes represent the maximal cliques of `G`.
    There is an edge from node *v* to clique *C* in the returned graph
    if and only if *v* is an element of *C*.

    Parameters
    ----------
    G : NetworkX graph
        An undirected graph.

    fpos : bool
        If True or not None, the returned graph will have an
        additional attribute, `pos`, a dictionary mapping node to
        position in the Euclidean plane.

    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    NetworkX graph
        A bipartite graph whose "bottom" set is the nodes of the graph
        `G`, whose "top" set is the cliques of `G`, and whose edges
        join nodes of `G` to the cliques that contain them.

        The nodes of the graph `G` have the node attribute
        'bipartite' set to 1 and the nodes representing cliques
        have the node attribute 'bipartite' set to 0, as is the
        convention for bipartite graphs in NetworkX.

    """
    B = nx.empty_graph(0, create_using)
    B.clear()
    # The "bottom" nodes in the bipartite graph are the nodes of the
    # original graph, G.
    B.add_nodes_from(G, bipartite=1)
    for i, cl in enumerate(find_cliques(G)):
        # The "top" nodes in the bipartite graph are the cliques. These
        # nodes get negative numbers as labels.
        name = -i - 1
        B.add_node(name, bipartite=0)
        B.add_edges_from((v, name) for v in cl)
    return B


@nx._dispatchable
def node_clique_number(G, nodes=None, cliques=None, separate_nodes=False):
    """Returns the size of the largest maximal clique containing each given node.

    Returns a single or list depending on input nodes.
    An optional list of cliques can be input if already computed.

    Parameters
    ----------
    G : NetworkX graph
        An undirected graph.

    cliques : list, optional (default=None)
        A list of cliques, each of which is itself a list of nodes.
        If not specified, the list of all cliques will be computed
        using :func:`find_cliques`.

    Returns
    -------
    int or dict
        If `nodes` is a single node, returns the size of the
        largest maximal clique in `G` containing that node.
        Otherwise return a dict keyed by node to the size
        of the largest maximal clique containing that node.

    See Also
    --------
    find_cliques
        find_cliques yields the maximal cliques of G.
        It accepts a `nodes` argument which restricts consideration to
        maximal cliques containing all the given `nodes`.
        The search for the cliques is optimized for `nodes`.
    """
    if cliques is None:
        if nodes is not None:
            # Use ego_graph to decrease size of graph
            # check for single node
            if nodes in G:
                return max(len(c) for c in find_cliques(nx.ego_graph(G, nodes)))
            # handle multiple nodes
            return {
                n: max(len(c) for c in find_cliques(nx.ego_graph(G, n))) for n in nodes
            }

        # nodes is None--find all cliques
        cliques = list(find_cliques(G))

    # single node requested
    if nodes in G:
        return max(len(c) for c in cliques if nodes in c)

    # multiple nodes requested
    # preprocess all nodes (faster than one at a time for even 2 nodes)
    size_for_n = defaultdict(int)
    for c in cliques:
        size_of_c = len(c)
        for n in c:
            if size_for_n[n] < size_of_c:
                size_for_n[n] = size_of_c
    if nodes is None:
        return size_for_n
    return {n: size_for_n[n] for n in nodes}


def number_of_cliques(G, nodes=None, cliques=None):
    """Returns the number of maximal cliques for each node.

    Returns a single or list depending on input nodes.
    Optional list of cliques can be input if already computed.
    """
    if cliques is None:
        cliques = list(find_cliques(G))

    if nodes is None:
        nodes = list(G.nodes())  # none, get entire graph

    if not isinstance(nodes, list):  # check for a list
        v = nodes
        # assume it is a single value
        numcliq = len([1 for c in cliques if v in c])
    else:
        numcliq = {}
        for v in nodes:
            numcliq[v] = len([1 for c in cliques if v in c])
    return numcliq


class MaxWeightClique:
    """A class for the maximum weight clique algorithm.

    This class is a helper for the `max_weight_clique` function.  The class
    should not normally be used directly.

    Parameters
    ----------
    G : NetworkX graph
        The undirected graph for which a maximum weight clique is sought
    weight : string or None, optional (default='weight')
        The node attribute that holds the integer value used as a weight.
        If None, then each node has weight 1.

    Attributes
    ----------
    G : NetworkX graph
        The undirected graph for which a maximum weight clique is sought
    node_weights: dict
        The weight of each node
    incumbent_nodes : list
        The nodes of the incumbent clique (the best clique found so far)
    incumbent_weight: int
        The weight of the incumbent clique
    """

    def __init__(self, G, weight):
        self.G = G
        self.incumbent_nodes = []
        self.incumbent_weight = 0

        if weight is None:
            self.node_weights = {v: 1 for v in G.nodes()}
        else:
            for v in G.nodes():
                if weight not in G.nodes[v]:
                    errmsg = f"Node {v!r} does not have the requested weight field."
                    raise KeyError(errmsg)
                if not isinstance(G.nodes[v][weight], int):
                    errmsg = f"The {weight!r} field of node {v!r} is not an integer."
                    raise ValueError(errmsg)
            self.node_weights = {v: G.nodes[v][weight] for v in G.nodes()}

    def update_incumbent_if_improved(self, C, C_weight):
        """Update the incumbent if the node set C has greater weight.

        C is assumed to be a clique.
        """
        if C_weight > self.incumbent_weight:
            self.incumbent_nodes = C[:]
            self.incumbent_weight = C_weight

    def greedily_find_independent_set(self, P):
        """Greedily find an independent set of nodes from a set of
        nodes P."""
        independent_set = []
        P = P[:]
        while P:
            v = P[0]
            independent_set.append(v)
            P = [w for w in P if v != w and not self.G.has_edge(v, w)]
        return independent_set

    def find_branching_nodes(self, P, target):
        """Find a set of nodes to branch on."""
        residual_wt = {v: self.node_weights[v] for v in P}
        total_wt = 0
        P = P[:]
        while P:
            independent_set = self.greedily_find_independent_set(P)
            min_wt_in_class = min(residual_wt[v] for v in independent_set)
            total_wt += min_wt_in_class
            if total_wt > target:
                break
            for v in independent_set:
                residual_wt[v] -= min_wt_in_class
            P = [v for v in P if residual_wt[v] != 0]
        return P

    def expand(self, C, C_weight, P):
        """Look for the best clique that contains all the nodes in C and zero or
        more of the nodes in P, backtracking if it can be shown that no such
        clique has greater weight than the incumbent.
        """
        self.update_incumbent_if_improved(C, C_weight)
        branching_nodes = self.find_branching_nodes(P, self.incumbent_weight - C_weight)
        while branching_nodes:
            v = branching_nodes.pop()
            P.remove(v)
            new_C = C + [v]
            new_C_weight = C_weight + self.node_weights[v]
            new_P = [w for w in P if self.G.has_edge(v, w)]
            self.expand(new_C, new_C_weight, new_P)

    def find_max_weight_clique(self):
        """Find a maximum weight clique."""
        # Sort nodes in reverse order of degree for speed
        nodes = sorted(self.G.nodes(), key=lambda v: self.G.degree(v), reverse=True)
        nodes = [v for v in nodes if self.node_weights[v] > 0]
        self.expand([], 0, nodes)


@not_implemented_for("directed")
@nx._dispatchable(node_attrs="weight")
def max_weight_clique(G, weight="weight"):
    """Find a maximum weight clique in G.

    A *clique* in a graph is a set of nodes such that every two distinct nodes
    are adjacent.  The *weight* of a clique is the sum of the weights of its
    nodes.  A *maximum weight clique* of graph G is a clique C in G such that
    no clique in G has weight greater than the weight of C.

    Parameters
    ----------
    G : NetworkX graph
        Undirected graph
    weight : string or None, optional (default='weight')
        The node attribute that holds the integer value used as a weight.
        If None, then each node has weight 1.

    Returns
    -------
    clique : list
        the nodes of a maximum weight clique
    weight : int
        the weight of a maximum weight clique

    Notes
    -----
    The implementation is recursive, and therefore it may run into recursion
    depth issues if G contains a clique whose number of nodes is close to the
    recursion depth limit.

    At each search node, the algorithm greedily constructs a weighted
    independent set cover of part of the graph in order to find a small set of
    nodes on which to branch.  The algorithm is very similar to the algorithm
    of Tavares et al. [1]_, other than the fact that the NetworkX version does
    not use bitsets.  This style of algorithm for maximum weight clique (and
    maximum weight independent set, which is the same problem but on the
    complement graph) has a decades-long history.  See Algorithm B of Warren
    and Hicks [2]_ and the references in that paper.

    References
    ----------
    .. [1] Tavares, W.A., Neto, M.B.C., Rodrigues, C.D., Michelon, P.: Um
           algoritmo de branch and bound para o problema da clique máxima
           ponderada.  Proceedings of XLVII SBPO 1 (2015).

    .. [2] Warren, Jeffrey S, Hicks, Illya V.: Combinatorial Branch-and-Bound
           for the Maximum Weight Independent Set Problem.  Technical Report,
           Texas A&M University (2016).
    """

    mwc = MaxWeightClique(G, weight)
    mwc.find_max_weight_clique()
    return mwc.incumbent_nodes, mwc.incumbent_weight
