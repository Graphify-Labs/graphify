"""Provides functions for computing minors of a graph."""

from itertools import chain, combinations, permutations, product

import networkx as nx
from networkx import density
from networkx.exception import NetworkXException
from networkx.utils import arbitrary_element

__all__ = [
    "contracted_edge",
    "contracted_nodes",
    "equivalence_classes",
    "identified_nodes",
    "quotient_graph",
]

chaini = chain.from_iterable


def equivalence_classes(iterable, relation):
    """Returns equivalence classes of `relation` when applied to `iterable`.

    The equivalence classes, or blocks, consist of objects from `iterable`
    which are all equivalent. They are defined to be equivalent if the
    `relation` function returns `True` when passed any two objects from that
    class, and `False` otherwise. To define an equivalence relation the
    function must be reflexive, symmetric and transitive.

    Parameters
    ----------
    iterable : list, tuple, or set
        An iterable of elements/nodes.

    relation : function
        A Boolean-valued function that implements an equivalence relation
        (reflexive, symmetric, transitive binary relation) on the elements
        of `iterable` - it must take two elements and return `True` if
        they are related, or `False` if not.

    Returns
    -------
    set of frozensets
        A set of frozensets representing the partition induced by the equivalence
        relation function `relation` on the elements of `iterable`. Each
        member set in the return set represents an equivalence class, or
        block, of the partition.

        Duplicate elements will be ignored so it makes the most sense for
        `iterable` to be a :class:`set`.

    Notes
    -----
    This function does not check that `relation` represents an equivalence
    relation. You can check that your equivalence classes provide a partition
    using `is_partition`.

    Examples
    --------
    Let `X` be the set of integers from `0` to `9`, and consider an equivalence
    relation `R` on `X` of congruence modulo `3`: this means that two integers
    `x` and `y` in `X` are equivalent under `R` if they leave the same
    remainder when divided by `3`, i.e. `(x - y) mod 3 = 0`.

    The equivalence classes of this relation are `{0, 3, 6, 9}`, `{1, 4, 7}`,
    `{2, 5, 8}`: `0`, `3`, `6`, `9` are all divisible by `3` and leave zero
    remainder; `1`, `4`, `7` leave remainder `1`; while `2`, `5` and `8` leave
    remainder `2`. We can see this by calling `equivalence_classes` with
    `X` and a function implementation of `R`.

    >>> X = set(range(10))
    >>> def mod3(x, y):
    ...     return (x - y) % 3 == 0
    >>> equivalence_classes(X, mod3)  # doctest: +SKIP
    {frozenset({1, 4, 7}), frozenset({8, 2, 5}), frozenset({0, 9, 3, 6})}
    """
    # For simplicity of implementation, we initialize the return value as a
    # list of lists, then convert it to a set of sets at the end of the
    # function.
    blocks = []
    # Determine the equivalence class for each element of the iterable.
    for y in iterable:
        # Each element y must be in *exactly one* equivalence class.
        #
        # Each block is guaranteed to be non-empty
        for block in blocks:
            x = arbitrary_element(block)
            if relation(x, y):
                block.append(y)
                break
        else:
            # If the element y is not part of any known equivalence class, it
            # must be in its own, so we create a new singleton equivalence
            # class for it.
            blocks.append([y])
    return {frozenset(block) for block in blocks}


@nx._dispatchable(edge_attrs="weight", returns_graph=True)
def quotient_graph(
    G,
    partition,
    edge_relation=None,
    node_data=None,
    edge_data=None,
    weight="weight",
    relabel=False,
    create_using=None,
):
    """Returns the quotient graph of `G` under the specified equivalence
    relation on nodes.

    Parameters
    ----------
    G : NetworkX graph
        The graph for which to return the quotient graph with the
        specified node relation.

    partition : function, or dict or list of lists, tuples or sets
        If a function, this function must represent an equivalence
        relation on the nodes of `G`. It must take two arguments *u*
        and *v* and return True exactly when *u* and *v* are in the
        same equivalence class. The equivalence classes form the nodes
        in the returned graph.

        If a dict of lists/tuples/sets, the keys can be any meaningful
        block labels, but the values must be the block lists/tuples/sets
        (one list/tuple/set per block), and the blocks must form a valid
        partition of the nodes of the graph. That is, each node must be
        in exactly one block of the partition.

        If a list of sets, the list must form a valid partition of
        the nodes of the graph. That is, each node must be in exactly
        one block of the partition.

    edge_relation : Boolean function with two arguments
        This function must represent an edge relation on the *blocks* of
        the `partition` of `G`. It must take two arguments, *B* and *C*,
        each one a set of nodes, and return True exactly when there should be
        an edge joining block *B* to block *C* in the returned graph.

        If `edge_relation` is not specified, it is assumed to be the
        following relation. Block *B* is related to block *C* if and
        only if some node in *B* is adjacent to some node in *C*,
        according to the edge set of `G`.

    node_data : function
        This function takes one argument, *B*, a set of nodes in `G`,
        and must return a dictionary representing the node data
        attributes to set on the node representing *B* in the quotient graph.
        If None, the following node attributes will be set:

        * 'graph', the subgraph of the graph `G` that this block
          represents,
        * 'nnodes', the number of nodes in this block,
        * 'nedges', the number of edges within this block,
        * 'density', the density of the subgraph of `G` that this
          block represents.

    edge_data : function
        This function takes two arguments, *B* and *C*, each one a set
        of nodes, and must return a dictionary representing the edge
        data attributes to set on the edge joining *B* and *C*, should
        there be an edge joining *B* and *C* in the quotient graph (if
        no such edge occurs in the quotient graph as determined by
        `edge_relation`, then the output of this function is ignored).

        If the quotient graph would be a multigraph, this function is
        not applied, since the edge data from each edge in the graph
        `G` appears in the edges of the quotient graph.

    weight : string or None, optional (default="weight")
        The name of an edge attribute that holds the numerical value
        used as a weight. If None then each edge has weight 1.

    relabel : bool
        If True, relabel the nodes of the quotient graph to be
        nonnegative integers. Otherwise, the nodes are identified with
        :class:`frozenset` instances representing the blocks given in
        `partition`.

    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    NetworkX graph
        The quotient graph of `G` under the equivalence relation
        specified by `partition`. If the partition were given as a
        list of :class:`set` instances and `relabel` is False,
        each node will be a :class:`frozenset` corresponding to the same
        :class:`set`.

    Raises
    ------
    NetworkXException
        If the given partition is not a valid partition of the nodes of
        `G`.

    Examples
    --------
    The quotient graph of the complete bipartite graph under the "same
    neighbors" equivalence relation is `K_2`. Under this relation, two nodes
    are equivalent if they are not adjacent but have the same neighbor set.

    >>> G = nx.complete_bipartite_graph(2, 3)
    >>> same_neighbors = lambda u, v: (u not in G[v] and v not in G[u] and G[u] == G[v])
    >>> Q = nx.quotient_graph(G, same_neighbors)
    >>> K2 = nx.complete_graph(2)
    >>> nx.is_isomorphic(Q, K2)
    True

    The quotient graph of a directed graph under the "same strongly connected
    component" equivalence relation is the condensation of the graph (see
    :func:`condensation`). This example comes from the Wikipedia article
    *`Strongly connected component`_*.

    >>> G = nx.DiGraph()
    >>> edges = [
    ...     "ab",
    ...     "be",
    ...     "bf",
    ...     "bc",
    ...     "cg",
    ...     "cd",
    ...     "dc",
    ...     "dh",
    ...     "ea",
    ...     "ef",
    ...     "fg",
    ...     "gf",
    ...     "hd",
    ...     "hf",
    ... ]
    >>> G.add_edges_from(tuple(x) for x in edges)
    >>> components = list(nx.strongly_connected_components(G))
    >>> sorted(sorted(component) for component in components)
    [['a', 'b', 'e'], ['c', 'd', 'h'], ['f', 'g']]
    >>>
    >>> C = nx.condensation(G, components)
    >>> component_of = C.graph["mapping"]
    >>> same_component = lambda u, v: component_of[u] == component_of[v]
    >>> Q = nx.quotient_graph(G, same_component)
    >>> nx.is_isomorphic(C, Q)
    True

    Node identification can be represented as the quotient of a graph under the
    equivalence relation that places the two nodes in one block and each other
    node in its own singleton block.

    >>> K24 = nx.complete_bipartite_graph(2, 4)
    >>> K34 = nx.complete_bipartite_graph(3, 4)
    >>> C = nx.contracted_nodes(K34, 1, 2)
    >>> nodes = {1, 2}
    >>> is_contracted = lambda u, v: u in nodes and v in nodes
    >>> Q = nx.quotient_graph(K34, is_contracted)
    >>> nx.is_isomorphic(Q, C)
    True
    >>> nx.is_isomorphic(Q, K24)
    True

    The blockmodeling technique described in [1]_ can be implemented as a
    quotient graph.

    >>> G = nx.path_graph(6)
    >>> partition = [{0, 1}, {2, 3}, {4, 5}]
    >>> M = nx.quotient_graph(G, partition, relabel=True)
    >>> list(M.edges())
    [(0, 1), (1, 2)]

    Here is the sample example but using partition as a dict of block sets.

    >>> G = nx.path_graph(6)
    >>> partition = {0: {0, 1}, 2: {2, 3}, 4: {4, 5}}
    >>> M = nx.quotient_graph(G, partition, relabel=True)
    >>> list(M.edges())
    [(0, 1), (1, 2)]

    Partitions can be represented in various ways:

    0. a list/tuple/set of block lists/tuples/sets
    1. a dict with block labels as keys and blocks lists/tuples/sets as values
    2. a dict with block lists/tuples/sets as keys and block labels as values
    3. a function from nodes in the original iterable to block labels
    4. an equivalence relation function on the target iterable

    As `quotient_graph` is designed to accept partitions represented as (0), (1) or
    (4) only, the `equivalence_classes` function can be used to get the partitions
    in the right form, in order to call `quotient_graph`.

    .. _Strongly connected component: https://en.wikipedia.org/wiki/Strongly_connected_component

    References
    ----------
    .. [1] Patrick Doreian, Vladimir Batagelj, and Anuska Ferligoj.
           *Generalized Blockmodeling*.
           Cambridge University Press, 2004.

    """
    # If the user provided an equivalence relation as a function to compute
    # the blocks of the partition on the nodes of G induced by the
    # equivalence relation.
    if callable(partition):
        # equivalence_classes always return partition of whole G.
        partition = equivalence_classes(G, partition)
        if not nx.community.is_partition(G, partition):
            raise nx.NetworkXException(
                "Input `partition` is not an equivalence relation for nodes of G"
            )
        return _quotient_graph(
            G,
            partition,
            edge_relation,
            node_data,
            edge_data,
            weight,
            relabel,
            create_using,
        )

    # If the partition is a dict, it is assumed to be one where the keys are
    # user-defined block labels, and values are block lists, tuples or sets.
    if isinstance(partition, dict):
        partition = list(partition.values())

    # If the user provided partition as a collection of sets. Then we
    # need to check if partition covers all of G nodes. If the answer
    # is 'No' then we need to prepare suitable subgraph view.
    partition_nodes = set().union(*partition)
    if len(partition_nodes) != len(G):
        G = G.subgraph(partition_nodes)
    # Each node in the graph/subgraph must be in exactly one block.
    if not nx.community.is_partition(G, partition):
        raise NetworkXException("each node must be in exactly one part of `partition`")
    return _quotient_graph(
        G,
        partition,
        edge_relation,
        node_data,
        edge_data,
        weight,
        relabel,
        create_using,
    )


def _quotient_graph(
    G, partition, edge_relation, node_data, edge_data, weight, relabel, create_using
):
    """Construct the quotient graph assuming input has been checked"""
    if create_using is None:
        H = G.__class__()
    else:
        H = nx.empty_graph(0, create_using)
    # By default set some basic information about the subgraph that each block
    # represents on the nodes in the quotient graph.
    if node_data is None:

        def node_data(b):
            S = G.subgraph(b)
            return {
                "graph": S,
                "nnodes": len(S),
                "nedges": S.number_of_edges(),
                "density": density(S),
            }

    # Each block of the partition becomes a node in the quotient graph.
    partition = [frozenset(b) for b in partition]
    H.add_nodes_from((b, node_data(b)) for b in partition)
    # By default, the edge relation is the relation defined as follows. B is
    # adjacent to C if a node in B is adjacent to a node in C, according to the
    # edge set of G.
    #
    # This is not a particularly efficient implementation of this relation:
    # there are O(n^2) pairs to check and each check may require O(log n) time
    # (to check set membership). This can certainly be parallelized.
    if edge_relation is None:

        def edge_relation(b, c):
            return any(v in G[u] for u, v in product(b, c))

    # By default, sum the weights of the edges joining pairs of nodes across
    # blocks to get the weight of the edge joining those two blocks.
    if edge_data is None:

        def edge_data(b, c):
            edgedata = (
                d
                for u, v, d in G.edges(b | c, data=True)
                if (u in b and v in c) or (u in c and v in b)
            )
            return {"weight": sum(d.get(weight, 1) for d in edgedata)}

    block_pairs = permutations(H, 2) if H.is_directed() else combinations(H, 2)
    # In a multigraph, add one edge in the quotient graph for each edge
    # in the original graph.
    if H.is_multigraph():
        edges = chaini(
            (
                (b, c, G.get_edge_data(u, v, default={}))
                for u, v in product(b, c)
                if v in G[u]
            )
            for b, c in block_pairs
            if edge_relation(b, c)
        )
    # In a simple graph, apply the edge data function to each pair of
    # blocks to determine the edge data attributes to apply to each edge
    # in the quotient graph.
    else:
        edges = (
            (b, c, edge_data(b, c)) for (b, c) in block_pairs if edge_relation(b, c)
        )
    H.add_edges_from(edges)
    # If requested by the user, relabel the nodes to be integers,
    # numbered in increasing order from zero in the same order as the
    # iteration order of `partition`.
    if relabel:
        # Can't use nx.convert_node_labels_to_integers() here since we
        # want the order of iteration to be the same for backward
        # compatibility with the nx.blockmodel() function.
        labels = {b: i for i, b in enumerate(partition)}
        H = nx.relabel_nodes(H, labels)
    return H


@nx._dispatchable(
    preserve_all_attrs=True, mutates_input={"not copy": 4}, returns_graph=True
)
def contracted_nodes(G, u, v, self_loops=True, copy=True):
    """Returns the graph that results from contracting `u` and `v`.

    Node contraction identifies the two nodes as a single node incident to any
    edge that was incident to the original two nodes.

    Parameters
    ----------
    G : NetworkX graph
        The graph whose nodes will be contracted.

    u, v : nodes
        Must be nodes in `G`.

    self_loops : Boolean
        If this is True, any edges joining `u` and `v` in `G` become
        self-loops on the new node in the returned graph.

    copy : Boolean
        If this is True (default True), make a copy of
        `G` and return that instead of directly changing `G`.


    Returns
    -------
    Networkx graph
        If Copy is True,
        A new graph object of the same type as `G` (leaving `G` unmodified)
        with `u` and `v` identified in a single node. The right node `v`
        will be merged into the node `u`, so only `u` will appear in the
        returned graph.
        If copy is False,
        Modifies `G` with `u` and `v` identified in a single node.
        The right node `v` will be merged into the node `u`, so
        only `u` will appear in the returned graph.

    Notes
    -----
    For multigraphs, the edge keys for the realigned edges may
    not be the same as the edge keys for the old edges. This is
    natural because edge keys are unique only within each pair of nodes.

    For non-multigraphs where `u` and `v` are adjacent to a third node
    `w`, the edge (`v`, `w`) will be contracted into the edge (`u`,
    `w`) with its attributes stored into a "contraction" attribute.

    This function is also available as `identified_nodes`.

    Examples
    --------
    Contracting two nonadjacent nodes of the cycle graph on four nodes `C_4`
    yields the path graph (ignoring parallel edges):

    >>> G = nx.cycle_graph(4)
    >>> M = nx.contracted_nodes(G, 1, 3)
    >>> P3 = nx.path_graph(3)
    >>> nx.is_isomorphic(M, P3)
    True

    >>> G = nx.MultiGraph(P3)
    >>> M = nx.contracted_nodes(G, 0, 2)
    >>> M.edges
    MultiEdgeView([(0, 1, 0), (0, 1, 1)])

    >>> G = nx.Graph([(1, 2), (2, 2)])
    >>> H = nx.contracted_nodes(G, 1, 2, self_loops=False)
    >>> list(H.nodes())
    [1]
    >>> list(H.edges())
    [(1, 1)]

    In a ``MultiDiGraph`` with a self loop, the in and out edges will
    be treated separately as edges, so while contracting a node which
    has a self loop the contraction will add multiple edges:

    >>> G = nx.MultiDiGraph([(1, 2), (2, 2)])
    >>> H = nx.contracted_nodes(G, 1, 2)
    >>> list(H.edges())  # edge 1->2, 2->2, 2<-2 from the original Graph G
    [(1, 1), (1, 1), (1, 1)]
    >>> H = nx.contracted_nodes(G, 1, 2, self_loops=False)
    >>> list(H.edges())  # edge 2->2, 2<-2 from the original Graph G
    [(1, 1), (1, 1)]

    See Also
    --------
    contracted_edge
    quotient_graph

    """
    # Copying has significant overhead and can be disabled if needed
    if copy:
        H = G.copy()
    else:
        H = G

    # edge code uses G.edges(v) instead of G.adj[v] to handle multiedges
    if H.is_directed():
        edges_to_remap = chain(G.in_edges(v, data=True), G.out_edges(v, data=True))
    else:
        edges_to_remap = G.edges(v, data=True)

    # If the H=G, the generators change as H changes
    # This makes the edges_to_remap independent of H
    if not copy:
        edges_to_remap = list(edges_to_remap)

    v_data = H.nodes[v]
    H.remove_node(v)

    for prev_w, prev_x, d in edges_to_remap:
        w = prev_w if prev_w != v else u
        x = prev_x if prev_x != v else u

        if ({prev_w, prev_x} == {u, v}) and not self_loops:
            continue

        if not H.has_edge(w, x) or G.is_multigraph():
            H.add_edge(w, x, **d)
        else:
            if "contraction" in H.edges[(w, x)]:
                H.edges[(w, x)]["contraction"][(prev_w, prev_x)] = d
            else:
                H.edges[(w, x)]["contraction"] = {(prev_w, prev_x): d}

    if "contraction" in H.nodes[u]:
        H.nodes[u]["contraction"][v] = v_data
    else:
        H.nodes[u]["contraction"] = {v: v_data}
    return H


identified_nodes = contracted_nodes


@nx._dispatchable(
    preserve_edge_attrs=True, mutates_input={"not copy": 3}, returns_graph=True
)
def contracted_edge(G, edge, self_loops=True, copy=True):
    """Returns the graph that results from contracting the specified edge.

    Edge contraction identifies the two endpoints of the edge as a single node
    incident to any edge that was incident to the original two nodes. A graph
    that results from edge contraction is called a *minor* of the original
    graph.

    Parameters
    ----------
    G : NetworkX graph
       The graph whose edge will be contracted.

    edge : tuple
       Must be a pair of nodes in `G`.

    self_loops : Boolean
       If this is True, any edges (including `edge`) joining the
       endpoints of `edge` in `G` become self-loops on the new node in the
       returned graph.

    copy : Boolean (default True)
        If this is True, a the contraction will be performed on a copy of `G`,
        otherwise the contraction will happen in place.

    Returns
    -------
    Networkx graph
       A new graph object of the same type as `G` (leaving `G` unmodified)
       with endpoints of `edge` identified in a single node. The right node
       of `edge` will be merged into the left one, so only the left one will
       appear in the returned graph.

    Raises
    ------
    ValueError
       If `edge` is not an edge in `G`.

    Examples
    --------
    Attempting to contract two nonadjacent nodes yields an error:

    >>> G = nx.cycle_graph(4)
    >>> nx.contracted_edge(G, (1, 3))
    Traceback (most recent call last):
      ...
    ValueError: Edge (1, 3) does not exist in graph G; cannot contract it

    Contracting two adjacent nodes in the cycle graph on *n* nodes yields the
    cycle graph on *n - 1* nodes:

    >>> C5 = nx.cycle_graph(5)
    >>> C4 = nx.cycle_graph(4)
    >>> M = nx.contracted_edge(C5, (0, 1), self_loops=False)
    >>> nx.is_isomorphic(M, C4)
    True

    See also
    --------
    contracted_nodes
    quotient_graph

    """
    u, v = edge[:2]
    if not G.has_edge(u, v):
        raise ValueError(f"Edge {edge} does not exist in graph G; cannot contract it")
    return contracted_nodes(G, u, v, self_loops=self_loops, copy=copy)
