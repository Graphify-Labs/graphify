"""Generate graphs with a given joint degree and directed joint degree"""

import networkx as nx
from networkx.utils import py_random_state

__all__ = [
    "is_valid_joint_degree",
    "is_valid_directed_joint_degree",
    "joint_degree_graph",
    "directed_joint_degree_graph",
]


@nx._dispatchable(graphs=None)
def is_valid_joint_degree(joint_degrees):
    """Checks whether the given joint degree dictionary is realizable.

    A *joint degree dictionary* is a dictionary of dictionaries, in
    which entry ``joint_degrees[k][l]`` is an integer representing the
    number of edges joining nodes of degree *k* with nodes of degree
    *l*. Such a dictionary is realizable as a simple graph if and only
    if the following conditions are satisfied.

    - each entry must be an integer,
    - the total number of nodes of degree *k*, computed by
      ``sum(joint_degrees[k].values()) / k``, must be an integer,
    - the total number of edges joining nodes of degree *k* with
      nodes of degree *l* cannot exceed the total number of possible edges,
    - each diagonal entry ``joint_degrees[k][k]`` must be even (this is
      a convention assumed by the :func:`joint_degree_graph` function).


    Parameters
    ----------
    joint_degrees :  dictionary of dictionary of integers
        A joint degree dictionary in which entry ``joint_degrees[k][l]``
        is the number of edges joining nodes of degree *k* with nodes of
        degree *l*.

    Returns
    -------
    bool
        Whether the given joint degree dictionary is realizable as a
        simple graph.

    References
    ----------
    .. [1] M. Gjoka, M. Kurant, A. Markopoulou, "2.5K Graphs: from Sampling
       to Generation", IEEE Infocom, 2013.
    .. [2] I. Stanton, A. Pinar, "Constructing and sampling graphs with a
       prescribed joint degree distribution", Journal of Experimental
       Algorithmics, 2012.
    """

    degree_count = {}
    for k in joint_degrees:
        if k > 0:
            k_size = sum(joint_degrees[k].values()) / k
            if not k_size.is_integer():
                return False
            degree_count[k] = k_size

    for k in joint_degrees:
        for l in joint_degrees[k]:
            if not float(joint_degrees[k][l]).is_integer():
                return False

            if (k != l) and (joint_degrees[k][l] > degree_count[k] * degree_count[l]):
                return False
            elif k == l:
                if joint_degrees[k][k] > degree_count[k] * (degree_count[k] - 1):
                    return False
                if joint_degrees[k][k] % 2 != 0:
                    return False

    # if all above conditions have been satisfied then the input
    # joint degree is realizable as a simple graph.
    return True


def _neighbor_switch(G, w, unsat, h_node_residual, avoid_node_id=None):
    """Releases one free stub for ``w``, while preserving joint degree in G.

    Parameters
    ----------
    G : NetworkX graph
        Graph in which the neighbor switch will take place.
    w : integer
        Node id for which we will execute this neighbor switch.
    unsat : set of integers
        Set of unsaturated node ids that have the same degree as w.
    h_node_residual: dictionary of integers
        Keeps track of the remaining stubs  for a given node.
    avoid_node_id: integer
        Node id to avoid when selecting w_prime.

    Notes
    -----
    First, it selects *w_prime*, an  unsaturated node that has the same degree
    as ``w``. Second, it selects *switch_node*, a neighbor node of ``w`` that
    is not  connected to *w_prime*. Then it executes an edge swap i.e. removes
    (``w``,*switch_node*) and adds (*w_prime*,*switch_node*). Gjoka et. al. [1]
    prove that such an edge swap is always possible.

    References
    ----------
    .. [1] M. Gjoka, B. Tillman, A. Markopoulou, "Construction of Simple
       Graphs with a Target Joint Degree Matrix and Beyond", IEEE Infocom, '15
    """

    if (avoid_node_id is None) or (h_node_residual[avoid_node_id] > 1):
        # select unsaturated node w_prime that has the same degree as w
        w_prime = next(iter(unsat))
    else:
        # assume that the node pair (v,w) has been selected for connection. if
        # - neighbor_switch is called for node w,
        # - nodes v and w have the same degree,
        # - node v=avoid_node_id has only one stub left,
        # then prevent v=avoid_node_id from being selected as w_prime.

        iter_var = iter(unsat)
        while True:
            w_prime = next(iter_var)
            if w_prime != avoid_node_id:
                break

    # select switch_node, a neighbor of w, that is not connected to w_prime
    w_prime_neighbs = G[w_prime]  # slightly faster declaring this variable
    for v in G[w]:
        if (v not in w_prime_neighbs) and (v != w_prime):
            switch_node = v
            break

    # remove edge (w,switch_node), add edge (w_prime,switch_node) and update
    # data structures
    G.remove_edge(w, switch_node)
    G.add_edge(w_prime, switch_node)
    h_node_residual[w] += 1
    h_node_residual[w_prime] -= 1
    if h_node_residual[w_prime] == 0:
        unsat.remove(w_prime)


@py_random_state(1)
@nx._dispatchable(graphs=None, returns_graph=True)
def joint_degree_graph(joint_degrees, seed=None):
    """Generates a random simple graph with the given joint degree dictionary.

    Parameters
    ----------
    joint_degrees :  dictionary of dictionary of integers
        A joint degree dictionary in which entry ``joint_degrees[k][l]`` is the
        number of edges joining nodes of degree *k* with nodes of degree *l*.
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    G : Graph
        A graph with the specified joint degree dictionary.

    Raises
    ------
    NetworkXError
        If *joint_degrees* dictionary is not realizable.

    Notes
    -----
    In each iteration of the "while loop" the algorithm picks two disconnected
    nodes *v* and *w*, of degree *k* and *l* correspondingly,  for which
    ``joint_degrees[k][l]`` has not reached its target yet. It then adds
    edge (*v*, *w*) and increases the number of edges in graph G by one.

    The intelligence of the algorithm lies in the fact that  it is always
    possible to add an edge between such disconnected nodes *v* and *w*,
    even if one or both nodes do not have free stubs. That is made possible by
    executing a "neighbor switch", an edge rewiring move that releases
    a free stub while keeping the joint degree of G the same.

    The algorithm continues for E (number of edges) iterations of
    the "while loop", at the which point all entries of the given
    ``joint_degrees[k][l]`` have reached their target values and the
    construction is complete.

    References
    ----------
    ..  [1] M. Gjoka, B. Tillman, A. Markopoulou, "Construction of Simple
        Graphs with a Target Joint Degree Matrix and Beyond", IEEE Infocom, '15

    Examples
    --------
    >>> joint_degrees = {
    ...     1: {4: 1},
    ...     2: {2: 2, 3: 2, 4: 2},
    ...     3: {2: 2, 4: 1},
    ...     4: {1: 1, 2: 2, 3: 1},
    ... }
    >>> G = nx.joint_degree_graph(joint_degrees)
    >>>
    """

    if not is_valid_joint_degree(joint_degrees):
        msg = "Input joint degree dict not realizable as a simple graph"
        raise nx.NetworkXError(msg)

    # compute degree count from joint_degrees
    degree_count = {k: sum(l.values()) // k for k, l in joint_degrees.items() if k > 0}

    # start with empty N-node graph
    N = sum(degree_count.values())
    G = nx.empty_graph(N)

    # for a given degree group, keep the list of all node ids
    h_degree_nodelist = {}

    # for a given node, keep track of the remaining stubs
    h_node_residual = {}

    # populate h_degree_nodelist and h_node_residual
    nodeid = 0
    for degree, num_nodes in degree_count.items():
        h_degree_nodelist[degree] = range(nodeid, nodeid + num_nodes)
        for v in h_degree_nodelist[degree]:
            h_node_residual[v] = degree
        nodeid += int(num_nodes)

    # iterate over every degree pair (k,l) and add the number of edges given
    # for each pair
    for k in joint_degrees:
        for l in joint_degrees[k]:
            # n_edges_add is the number of edges to add for the
            # degree pair (k,l)
            n_edges_add = joint_degrees[k][l]

            if (n_edges_add > 0) and (k >= l):
                # number of nodes with degree k and l
                k_size = degree_count[k]
                l_size = degree_count[l]

                # k_nodes and l_nodes consist of all nodes of degree k and l
                k_nodes = h_degree_nodelist[k]
                l_nodes = h_degree_nodelist[l]

                # k_unsat and l_unsat consist of nodes of degree k and l that
                # are unsaturated (nodes that have at least 1 available stub)
                k_unsat = {v for v in k_nodes if h_node_residual[v] > 0}

                if k != l:
                    l_unsat = {w for w in l_nodes if h_node_residual[w] > 0}
                else:
                    l_unsat = k_unsat
                    n_edges_add = joint_degrees[k][l] // 2

                while n_edges_add > 0:
                    # randomly pick nodes v and w that have degrees k and l
                    v = k_nodes[seed.randrange(k_size)]
                    w = l_nodes[seed.randrange(l_size)]

                    # if nodes v and w are disconnected then attempt to connect
                    if not G.has_edge(v, w) and (v != w):
                        # if node v has no free stubs then do neighbor switch
                        if h_node_residual[v] == 0:
                            _neighbor_switch(G, v, k_unsat, h_node_residual)

                        # if node w has no free stubs then do neighbor switch
                        if h_node_residual[w] == 0:
                            if k != l:
                                _neighbor_switch(G, w, l_unsat, h_node_residual)
                            else:
                                _neighbor_switch(
                                    G, w, l_unsat, h_node_residual, avoid_node_id=v
                                )

                        # add edge (v, w) and update data structures
                        G.add_edge(v, w)
                        h_node_residual[v] -= 1
                        h_node_residual[w] -= 1
                        n_edges_add -= 1

                        if h_node_residual[v] == 0:
                            k_unsat.discard(v)
                        if h_node_residual[w] == 0:
                            l_unsat.discard(w)
    return G


@nx._dispatchable(graphs=None)
def is_valid_directed_joint_degree(in_degrees, out_degrees, nkk):
    """Checks whether the given directed joint degree input is realizable

    Parameters
    ----------
    in_degrees :  list of integers
        in degree sequence contains the in degrees of nodes.
    out_degrees : list of integers
        out degree sequence contains the out degrees of nodes.
    nkk  :  dictionary of dictionary of integers
        directed joint degree dictionary. for nodes of out degree k (first
        level of dict) and nodes of in degree l (second level of dict)
        describes the number of edges.

    Returns
    -------
    boolean
        returns true if given input is realizable, else returns false.

    Notes
    -----
    Here is the list of conditions that the inputs (in/out degree sequences,
    nkk) need to satisfy for simple directed graph realizability:

    - Condition 0: in_degrees and out_degrees have the same length
    - Condition 1: nkk[k][l]  is integer for all k,l
    - Condition 2: sum(nkk[k])/k = number of nodes with partition id k, is an
                   integer and matching degree sequence
    - Condition 3: number of edges and non-chords between k and l cannot exceed
                   maximum possible number of edges


    References
    ----------
    [1] B. Tillman, A. Markopoulou, C. T. Butts & M. Gjoka,
        "Construction of Directed 2K Graphs". In Proc. of KDD 2017.
    """
    V = {}  # number of nodes with in/out degree.
    forbidden = {}
    if len(in_degrees) != len(out_degrees):
        return False

    for idx in range(len(in_degrees)):
        i = in_degrees[idx]
        o = out_degrees[idx]
        V[(i, 0)] = V.get((i, 0), 0) + 1
        V[(o, 1)] = V.get((o, 1), 0) + 1

        forbidden[(o, i)] = forbidden.get((o, i), 0) + 1

    S = {}  # number of edges going from in/out degree nodes.
    for k in nkk:
        for l in nkk[k]:
            val = nkk[k][l]
            if not float(val).is_integer():  # condition 1
                return False

            if val > 0:
                S[(k, 1)] = S.get((k, 1), 0) + val
                S[(l, 0)] = S.get((l, 0), 0) + val
                # condition 3
                if val + forbidden.get((k, l), 0) > V[(k, 1)] * V[(l, 0)]:
                    return False

    return all(S[s] / s[0] == V[s] for s in S)


def _directed_neighbor_switch(
    G, w, unsat, h_node_residual_out, chords, h_partition_in, partition
):
    """Releases one free stub for node w, while preserving joint degree in G.

    Parameters
    ----------
    G : networkx directed graph
        graph within which the edge swap will take place.
    w : integer
        node id for which we need to perform a neighbor switch.
    unsat: set of integers
        set of node ids that have the same degree as w and are unsaturated.
    h_node_residual_out: dict of integers
        for a given node, keeps track of the remaining stubs to be added.
    chords: set of tuples
        keeps track of available positions to add edges.
    h_partition_in: dict of integers
        for a given node, keeps track of its partition id (in degree).
    partition: integer
        partition id to check if chords have to be updated.

    Notes
    -----
    First, it selects node w_prime that (1) has the same degree as w and
    (2) is unsaturated. Then, it selects node v, a neighbor of w, that is
    not connected to w_prime and does an edge swap i.e. removes (w,v) and
    adds (w_prime,v). If neighbor switch is not possible for w using
    w_prime and v, then return w_prime; in [1] it's proven that
    such unsaturated nodes can be used.

    References
    ----------
    [1] B. Tillman, A. Markopoulou, C. T. Butts & M. Gjoka,
        "Construction of Directed 2K Graphs". In Proc. of KDD 2017.
    """
    w_prime = unsat.pop()
    unsat.add(w_prime)
    # select node t, a neighbor of w, that is not connected to w_prime
    w_neighbs = list(G.successors(w))
    # slightly faster declaring this variable
    w_prime_neighbs = list(G.successors(w_prime))

    for v in w_neighbs:
        if (v not in w_prime_neighbs) and w_prime != v:
            # removes (w,v), add (w_prime,v)  and update data structures
            G.remove_edge(w, v)
            G.add_edge(w_prime, v)

            if h_partition_in[v] == partition:
                chords.add((w, v))
                chords.discard((w_prime, v))

            h_node_residual_out[w] += 1
            h_node_residual_out[w_prime] -= 1
            if h_node_residual_out[w_prime] == 0:
                unsat.remove(w_prime)
            return None

    # If neighbor switch didn't work, use unsaturated node
    return w_prime


def _directed_neighbor_switch_rev(
    G, w, unsat, h_node_residual_in, chords, h_partition_out, partition
):
    """The reverse of directed_neighbor_switch.

    Parameters
    ----------
    G : networkx directed graph
        graph within which the edge swap will take place.
    w : integer
        node id for which we need to perform a neighbor switch.
    unsat: set of integers
        set of node ids that have the same degree as w and are unsaturated.
    h_node_residual_in: dict of integers
        for a given node, keeps track of the remaining stubs to be added.
    chords: set of tuples
        keeps track of available positions to add edges.
    h_partition_out: dict of integers
        for a given node, keeps track of its partition id (out degree).
    partition: integer
        partition id to check if chords have to be updated.

    Notes
    -----
    Same operation as directed_neighbor_switch except it handles this operation
    for incoming edges instead of outgoing.
    """
    w_prime = unsat.pop()
    unsat.add(w_prime)
    # slightly faster declaring these as variables.
    w_neighbs = list(G.predecessors(w))
    w_prime_neighbs = list(G.predecessors(w_prime))
    # select node v, a neighbor of w, that is not connected to w_prime.
    for v in w_neighbs:
        if (v not in w_prime_neighbs) and w_prime != v:
            # removes (v,w), add (v,w_prime) and update data structures.
            G.remove_edge(v, w)
            G.add_edge(v, w_prime)
            if h_partition_out[v] == partition:
                chords.add((v, w))
                chords.discard((v, w_prime))

            h_node_residual_in[w] += 1
            h_node_residual_in[w_prime] -= 1
            if h_node_residual_in[w_prime] == 0:
                unsat.remove(w_prime)
            return None

    # If neighbor switch didn't work, use the unsaturated node.
    return w_prime


@py_random_state(3)
@nx._dispatchable(graphs=None, returns_graph=True)
def directed_joint_degree_graph(in_degrees, out_degrees, nkk, seed=None):
    """Generates a random simple directed graph with the joint degree.

    Parameters
    ----------
    degree_seq :  list of tuples (of size 3)
        degree sequence contains tuples of nodes with node id, in degree and
        out degree.
    nkk  :  dictionary of dictionary of integers
        directed joint degree dictionary, for nodes of out degree k (first
        level of dict) and nodes of in degree l (second level of dict)
        describes the number of edges.
    seed : hashable object, optional
        Seed for random number generator.

    Returns
    -------
    G : Graph
        A directed graph with the specified inputs.

    Raises
    ------
    NetworkXError
        If degree_seq and nkk are not realizable as a simple directed graph.


    Notes
    -----
    Similarly to the undirected version:
    In each iteration of the "while loop" the algorithm picks two disconnected
    nodes v and w, of degree k and l correspondingly,  for which nkk[k][l] has
    not reached its target yet i.e. (for given k,l): n_edges_add < nkk[k][l].
    It then adds edge (v,w) and always increases the number of edges in graph G
    by one.

    The intelligence of the algorithm lies in the fact that  it is always
    possible to add an edge between disconnected nodes v and w, for which
    nkk[degree(v)][degree(w)] has not reached its target, even if one or both
    nodes do not have free stubs. If either node v or w does not have a free
    stub, we perform a "neighbor switch", an edge rewiring move that releases a
    free stub while keeping nkk the same.

    The difference for the directed version lies in the fact that neighbor
    switches might not be able to rewire, but in these cases unsaturated nodes
    can be reassigned to use instead, see [1] for detailed description and
    proofs.

    The algorithm continues for E (number of edges in the graph) iterations of
    the "while loop", at which point all entries of the given nkk[k][l] have
    reached their target values and the construction is complete.

    References
    ----------
    [1] B. Tillman, A. Markopoulou, C. T. Butts & M. Gjoka,
        "Construction of Directed 2K Graphs". In Proc. of KDD 2017.

    Examples
    --------
    >>> in_degrees = [0, 1, 1, 2]
    >>> out_degrees = [1, 1, 1, 1]
    >>> nkk = {1: {1: 2, 2: 2}}
    >>> G = nx.directed_joint_degree_graph(in_degrees, out_degrees, nkk)
    >>>
    """
    if not is_valid_directed_joint_degree(in_degrees, out_degrees, nkk):
        msg = "Input is not realizable as a simple graph"
        raise nx.NetworkXError(msg)

    # start with an empty directed graph.
    G = nx.DiGraph()

    # for a given group, keep the list of all node ids.
    h_degree_nodelist_in = {}
    h_degree_nodelist_out = {}
    # for a given group, keep the list of all unsaturated node ids.
    h_degree_nodelist_in_unsat = {}
    h_degree_nodelist_out_unsat = {}
    # for a given node, keep track of the remaining stubs to be added.
    h_node_residual_out = {}
    h_node_residual_in = {}
    # for a given node, keep track of the partition id.
    h_partition_out = {}
    h_partition_in = {}
    # keep track of non-chords between pairs of partition ids.
    non_chords = {}

    # populate data structures
    for idx, i in enumerate(in_degrees):
        idx = int(idx)
        if i > 0:
            h_degree_nodelist_in.setdefault(i, [])
            h_degree_nodelist_in_unsat.setdefault(i, set())
            h_degree_nodelist_in[i].append(idx)
            h_degree_nodelist_in_unsat[i].add(idx)
            h_node_residual_in[idx] = i
            h_partition_in[idx] = i

    for idx, o in enumerate(out_degrees):
        o = out_degrees[idx]
        non_chords[(o, in_degrees[idx])] = non_chords.get((o, in_degrees[idx]), 0) + 1
        idx = int(idx)
        if o > 0:
            h_degree_nodelist_out.setdefault(o, [])
            h_degree_nodelist_out_unsat.setdefault(o, set())
            h_degree_nodelist_out[o].append(idx)
            h_degree_nodelist_out_unsat[o].add(idx)
            h_node_residual_out[idx] = o
            h_partition_out[idx] = o

        G.add_node(idx)

    nk_in = {}
    nk_out = {}
    for p in h_degree_nodelist_in:
        nk_in[p] = len(h_degree_nodelist_in[p])
    for p in h_degree_nodelist_out:
        nk_out[p] = len(h_degree_nodelist_out[p])

    # iterate over every degree pair (k,l) and add the number of edges given
    # for each pair.
    for k in nkk:
        for l in nkk[k]:
            n_edges_add = nkk[k][l]

            if n_edges_add > 0:
                # chords contains a random set of potential edges.
                chords = set()

                k_len = nk_out[k]
                l_len = nk_in[l]
                chords_sample = seed.sample(
                    range(k_len * l_len), n_edges_add + non_chords.get((k, l), 0)
                )

                num = 0
                while len(chords) < n_edges_add:
                    i = h_degree_nodelist_out[k][chords_sample[num] % k_len]
                    j = h_degree_nodelist_in[l][chords_sample[num] // k_len]
                    num += 1
                    if i != j:
                        chords.add((i, j))

                # k_unsat and l_unsat consist of nodes of in/out degree k and l
                # that are unsaturated i.e. those nodes that have at least one
                # available stub
                k_unsat = h_degree_nodelist_out_unsat[k]
                l_unsat = h_degree_nodelist_in_unsat[l]

                while n_edges_add > 0:
                    v, w = chords.pop()
                    chords.add((v, w))

                    # if node v has no free stubs then do neighbor switch.
                    if h_node_residual_out[v] == 0:
                        _v = _directed_neighbor_switch(
                            G,
                            v,
                            k_unsat,
                            h_node_residual_out,
                            chords,
                            h_partition_in,
                            l,
                        )
                        if _v is not None:
                            v = _v

                    # if node w has no free stubs then do neighbor switch.
                    if h_node_residual_in[w] == 0:
                        _w = _directed_neighbor_switch_rev(
                            G,
                            w,
                            l_unsat,
                            h_node_residual_in,
                            chords,
                            h_partition_out,
                            k,
                        )
                        if _w is not None:
                            w = _w

                    # add edge (v,w) and update data structures.
                    G.add_edge(v, w)
                    h_node_residual_out[v] -= 1
                    h_node_residual_in[w] -= 1
                    n_edges_add -= 1
                    chords.discard((v, w))

                    if h_node_residual_out[v] == 0:
                        k_unsat.discard(v)
                    if h_node_residual_in[w] == 0:
                        l_unsat.discard(w)
    return G
