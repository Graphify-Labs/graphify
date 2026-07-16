"""
Generators and functions for bipartite graphs.
"""

import math
import numbers
from functools import reduce

import networkx as nx
from networkx.utils import nodes_or_number, py_random_state

__all__ = [
    "configuration_model",
    "havel_hakimi_graph",
    "reverse_havel_hakimi_graph",
    "alternating_havel_hakimi_graph",
    "preferential_attachment_graph",
    "random_graph",
    "gnmk_random_graph",
    "complete_bipartite_graph",
]


@nx._dispatchable(graphs=None, returns_graph=True)
@nodes_or_number([0, 1])
def complete_bipartite_graph(n1, n2, create_using=None):
    """Returns the complete bipartite graph `K_{n_1,n_2}`.

    The graph is composed of two partitions with nodes 0 to (n1 - 1)
    in the first and nodes n1 to (n1 + n2 - 1) in the second.
    Each node in the first is connected to each node in the second.

    Parameters
    ----------
    n1, n2 : integer or iterable container of nodes
        If integers, nodes are from `range(n1)` and `range(n1, n1 + n2)`.
        If a container, the elements are the nodes.
    create_using : NetworkX graph instance, (default: nx.Graph)
       Return graph of this type.

    Notes
    -----
    Nodes are the integers 0 to `n1 + n2 - 1` unless either n1 or n2 are
    containers of nodes. If only one of n1 or n2 are integers, that
    integer is replaced by `range` of that integer.

    The nodes are assigned the attribute 'bipartite' with the value 0 or 1
    to indicate which bipartite set the node belongs to.

    This function is not imported in the main namespace.
    To use it use nx.bipartite.complete_bipartite_graph
    """
    G = nx.empty_graph(0, create_using)
    if G.is_directed():
        raise nx.NetworkXError("Directed Graph not supported")

    n1, top = n1
    n2, bottom = n2
    if isinstance(n1, numbers.Integral) and isinstance(n2, numbers.Integral):
        bottom = [n1 + i for i in bottom]
    G.add_nodes_from(top, bipartite=0)
    G.add_nodes_from(bottom, bipartite=1)
    if len(G) != len(top) + len(bottom):
        raise nx.NetworkXError("Inputs n1 and n2 must contain distinct nodes")
    G.add_edges_from((u, v) for u in top for v in bottom)
    G.graph["name"] = f"complete_bipartite_graph({len(top)}, {len(bottom)})"
    return G


@py_random_state(3)
@nx._dispatchable(name="bipartite_configuration_model", graphs=None, returns_graph=True)
def configuration_model(aseq, bseq, create_using=None, seed=None):
    """Returns a random bipartite graph from two given degree sequences.

    Parameters
    ----------
    aseq : list
       Degree sequence for node set A.
    bseq : list
       Degree sequence for node set B.
    create_using : NetworkX graph instance, optional
       Return graph of this type.
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    The graph is composed of two partitions. Set A has nodes 0 to
    (len(aseq) - 1) and set B has nodes len(aseq) to (len(bseq) - 1).
    Nodes from set A are connected to nodes in set B by choosing
    randomly from the possible free stubs, one in A and one in B.

    Notes
    -----
    The sum of the two sequences must be equal: sum(aseq)=sum(bseq)
    If no graph type is specified use MultiGraph with parallel edges.
    If you want a graph with no parallel edges use create_using=Graph()
    but then the resulting degree sequences might not be exact.

    The nodes are assigned the attribute 'bipartite' with the value 0 or 1
    to indicate which bipartite set the node belongs to.

    This function is not imported in the main namespace.
    To use it use nx.bipartite.configuration_model
    """
    G = nx.empty_graph(0, create_using, default=nx.MultiGraph)
    if G.is_directed():
        raise nx.NetworkXError("Directed Graph not supported")

    # length and sum of each sequence
    lena = len(aseq)
    lenb = len(bseq)
    suma = sum(aseq)
    sumb = sum(bseq)

    if not suma == sumb:
        raise nx.NetworkXError(
            f"invalid degree sequences, sum(aseq)!=sum(bseq),{suma},{sumb}"
        )

    G = _add_nodes_with_bipartite_label(G, lena, lenb)

    if len(aseq) == 0 or max(aseq) == 0:
        return G  # done if no edges

    # build lists of degree-repeated vertex numbers
    stubs = [[v] * aseq[v] for v in range(lena)]
    astubs = [x for subseq in stubs for x in subseq]

    stubs = [[v] * bseq[v - lena] for v in range(lena, lena + lenb)]
    bstubs = [x for subseq in stubs for x in subseq]

    # shuffle lists
    seed.shuffle(astubs)
    seed.shuffle(bstubs)

    G.add_edges_from([astubs[i], bstubs[i]] for i in range(suma))

    G.name = "bipartite_configuration_model"
    return G


@nx._dispatchable(name="bipartite_havel_hakimi_graph", graphs=None, returns_graph=True)
def havel_hakimi_graph(aseq, bseq, create_using=None):
    """Returns a bipartite graph from two given degree sequences using a
    Havel-Hakimi style construction.

    The graph is composed of two partitions. Set A has nodes 0 to
    (len(aseq) - 1) and set B has nodes len(aseq) to (len(bseq) - 1).
    Nodes from the set A are connected to nodes in the set B by
    connecting the highest degree nodes in set A to the highest degree
    nodes in set B until all stubs are connected.

    Parameters
    ----------
    aseq : list
       Degree sequence for node set A.
    bseq : list
       Degree sequence for node set B.
    create_using : NetworkX graph instance, optional
       Return graph of this type.

    Notes
    -----
    The sum of the two sequences must be equal: sum(aseq)=sum(bseq)
    If no graph type is specified use MultiGraph with parallel edges.
    If you want a graph with no parallel edges use create_using=Graph()
    but then the resulting degree sequences might not be exact.

    The nodes are assigned the attribute 'bipartite' with the value 0 or 1
    to indicate which bipartite set the node belongs to.

    This function is not imported in the main namespace.
    To use it use nx.bipartite.havel_hakimi_graph
    """
    G = nx.empty_graph(0, create_using, default=nx.MultiGraph)
    if G.is_directed():
        raise nx.NetworkXError("Directed Graph not supported")

    # length of the each sequence
    naseq = len(aseq)
    nbseq = len(bseq)

    suma = sum(aseq)
    sumb = sum(bseq)

    if not suma == sumb:
        raise nx.NetworkXError(
            f"invalid degree sequences, sum(aseq)!=sum(bseq),{suma},{sumb}"
        )

    G = _add_nodes_with_bipartite_label(G, naseq, nbseq)

    if len(aseq) == 0 or max(aseq) == 0:
        return G  # done if no edges

    # build list of degree-repeated vertex numbers
    astubs = [[aseq[v], v] for v in range(naseq)]
    bstubs = [[bseq[v - naseq], v] for v in range(naseq, naseq + nbseq)]
    astubs.sort()
    while astubs:
        (degree, u) = astubs.pop()  # take of largest degree node in the a set
        if degree == 0:
            break  # done, all are zero
        # connect the source to largest degree nodes in the b set
        bstubs.sort()
        for target in bstubs[-degree:]:
            v = target[1]
            G.add_edge(u, v)
            target[0] -= 1  # note this updates bstubs too.
            if target[0] == 0:
                bstubs.remove(target)

    G.name = "bipartite_havel_hakimi_graph"
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def reverse_havel_hakimi_graph(aseq, bseq, create_using=None):
    """Returns a bipartite graph from two given degree sequences using a
    Havel-Hakimi style construction.

    The graph is composed of two partitions. Set A has nodes 0 to
    (len(aseq) - 1) and set B has nodes len(aseq) to (len(bseq) - 1).
    Nodes from set A are connected to nodes in the set B by connecting
    the highest degree nodes in set A to the lowest degree nodes in
    set B until all stubs are connected.

    Parameters
    ----------
    aseq : list
       Degree sequence for node set A.
    bseq : list
       Degree sequence for node set B.
    create_using : NetworkX graph instance, optional
       Return graph of this type.

    Notes
    -----
    The sum of the two sequences must be equal: sum(aseq)=sum(bseq)
    If no graph type is specified use MultiGraph with parallel edges.
    If you want a graph with no parallel edges use create_using=Graph()
    but then the resulting degree sequences might not be exact.

    The nodes are assigned the attribute 'bipartite' with the value 0 or 1
    to indicate which bipartite set the node belongs to.

    This function is not imported in the main namespace.
    To use it use nx.bipartite.reverse_havel_hakimi_graph
    """
    G = nx.empty_graph(0, create_using, default=nx.MultiGraph)
    if G.is_directed():
        raise nx.NetworkXError("Directed Graph not supported")

    # length of the each sequence
    lena = len(aseq)
    lenb = len(bseq)
    suma = sum(aseq)
    sumb = sum(bseq)

    if not suma == sumb:
        raise nx.NetworkXError(
            f"invalid degree sequences, sum(aseq)!=sum(bseq),{suma},{sumb}"
        )

    G = _add_nodes_with_bipartite_label(G, lena, lenb)

    if len(aseq) == 0 or max(aseq) == 0:
        return G  # done if no edges

    # build list of degree-repeated vertex numbers
    astubs = [[aseq[v], v] for v in range(lena)]
    bstubs = [[bseq[v - lena], v] for v in range(lena, lena + lenb)]
    astubs.sort()
    bstubs.sort()
    while astubs:
        (degree, u) = astubs.pop()  # take of largest degree node in the a set
        if degree == 0:
            break  # done, all are zero
        # connect the source to the smallest degree nodes in the b set
        for target in bstubs[0:degree]:
            v = target[1]
            G.add_edge(u, v)
            target[0] -= 1  # note this updates bstubs too.
            if target[0] == 0:
                bstubs.remove(target)

    G.name = "bipartite_reverse_havel_hakimi_graph"
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def alternating_havel_hakimi_graph(aseq, bseq, create_using=None):
    """Returns a bipartite graph from two given degree sequences using
    an alternating Havel-Hakimi style construction.

    The graph is composed of two partitions. Set A has nodes 0 to
    (len(aseq) - 1) and set B has nodes len(aseq) to (len(bseq) - 1).
    Nodes from the set A are connected to nodes in the set B by
    connecting the highest degree nodes in set A to alternatively the
    highest and the lowest degree nodes in set B until all stubs are
    connected.

    Parameters
    ----------
    aseq : list
       Degree sequence for node set A.
    bseq : list
       Degree sequence for node set B.
    create_using : NetworkX graph instance, optional
       Return graph of this type.

    Notes
    -----
    The sum of the two sequences must be equal: sum(aseq)=sum(bseq)
    If no graph type is specified use MultiGraph with parallel edges.
    If you want a graph with no parallel edges use create_using=Graph()
    but then the resulting degree sequences might not be exact.

    The nodes are assigned the attribute 'bipartite' with the value 0 or 1
    to indicate which bipartite set the node belongs to.

    This function is not imported in the main namespace.
    To use it use nx.bipartite.alternating_havel_hakimi_graph
    """
    G = nx.empty_graph(0, create_using, default=nx.MultiGraph)
    if G.is_directed():
        raise nx.NetworkXError("Directed Graph not supported")

    # length of the each sequence
    naseq = len(aseq)
    nbseq = len(bseq)
    suma = sum(aseq)
    sumb = sum(bseq)

    if not suma == sumb:
        raise nx.NetworkXError(
            f"invalid degree sequences, sum(aseq)!=sum(bseq),{suma},{sumb}"
        )

    G = _add_nodes_with_bipartite_label(G, naseq, nbseq)

    if len(aseq) == 0 or max(aseq) == 0:
        return G  # done if no edges
    # build list of degree-repeated vertex numbers
    astubs = [[aseq[v], v] for v in range(naseq)]
    bstubs = [[bseq[v - naseq], v] for v in range(naseq, naseq + nbseq)]
    while astubs:
        astubs.sort()
        (degree, u) = astubs.pop()  # take of largest degree node in the a set
        if degree == 0:
            break  # done, all are zero
        bstubs.sort()
        small = bstubs[0 : degree // 2]  # add these low degree targets
        large = bstubs[(-degree + degree // 2) :]  # now high degree targets
        stubs = [x for z in zip(large, small) for x in z]  # combine, sorry
        if len(stubs) < len(small) + len(large):  # check for zip truncation
            stubs.append(large.pop())
        for target in stubs:
            v = target[1]
            G.add_edge(u, v)
            target[0] -= 1  # note this updates bstubs too.
            if target[0] == 0:
                bstubs.remove(target)

    G.name = "bipartite_alternating_havel_hakimi_graph"
    return G


@py_random_state(3)
@nx._dispatchable(graphs=None, returns_graph=True)
def preferential_attachment_graph(aseq, p, create_using=None, seed=None):
    """Create a bipartite graph with a preferential attachment model from
    a given single degree sequence.

    The graph is composed of two partitions. Set A has nodes 0 to
    (len(aseq) - 1) and set B has nodes starting with node len(aseq).
    The number of nodes in set B is random.

    Parameters
    ----------
    aseq : list
       Degree sequence for node set A.
    p :  float
       Probability that a new bottom node is added.
    create_using : NetworkX graph instance, optional
       Return graph of this type.
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    References
    ----------
    .. [1] Guillaume, J.L. and Latapy, M.,
       Bipartite graphs as models of complex networks.
       Physica A: Statistical Mechanics and its Applications,
       2006, 371(2), pp.795-813.
    .. [2] Jean-Loup Guillaume and Matthieu Latapy,
       Bipartite structure of all complex networks,
       Inf. Process. Lett. 90, 2004, pg. 215-221
       https://doi.org/10.1016/j.ipl.2004.03.007

    Notes
    -----
    The nodes are assigned the attribute 'bipartite' with the value 0 or 1
    to indicate which bipartite set the node belongs to.

    This function is not imported in the main namespace.
    To use it use nx.bipartite.preferential_attachment_graph
    """
    G = nx.empty_graph(0, create_using, default=nx.MultiGraph)
    if G.is_directed():
        raise nx.NetworkXError("Directed Graph not supported")

    if p > 1:
        raise nx.NetworkXError(f"probability {p} > 1")

    naseq = len(aseq)
    G = _add_nodes_with_bipartite_label(G, naseq, 0)
    vv = [[v] * aseq[v] for v in range(naseq)]
    while vv:
        while vv[0]:
            source = vv[0][0]
            vv[0].remove(source)
            if seed.random() < p or len(G) == naseq:
                target = len(G)
                G.add_node(target, bipartite=1)
                G.add_edge(source, target)
            else:
                bb = [[b] * G.degree(b) for b in range(naseq, len(G))]
                # flatten the list of lists into a list.
                bbstubs = reduce(lambda x, y: x + y, bb)
                # choose preferentially a bottom node.
                target = seed.choice(bbstubs)
                G.add_node(target, bipartite=1)
                G.add_edge(source, target)
        vv.remove(vv[0])
    G.name = "bipartite_preferential_attachment_model"
    return G


@py_random_state(3)
@nx._dispatchable(graphs=None, returns_graph=True)
def random_graph(n, m, p, seed=None, directed=False):
    """Returns a bipartite random graph.

    This is a bipartite version of the binomial (Erdős-Rényi) graph.
    The graph is composed of two partitions. Set A has nodes 0 to
    (n - 1) and set B has nodes n to (n + m - 1).

    Parameters
    ----------
    n : int
        The number of nodes in the first bipartite set.
    m : int
        The number of nodes in the second bipartite set.
    p : float
        Probability for edge creation.
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.
    directed : bool, optional (default=False)
        If True return a directed graph

    Notes
    -----
    The bipartite random graph algorithm chooses each of the n*m (undirected)
    or 2*nm (directed) possible edges with probability p.

    This algorithm is $O(n+m)$ where $m$ is the expected number of edges.

    The nodes are assigned the attribute 'bipartite' with the value 0 or 1
    to indicate which bipartite set the node belongs to.

    This function is not imported in the main namespace.
    To use it use nx.bipartite.random_graph

    See Also
    --------
    gnp_random_graph, configuration_model

    References
    ----------
    .. [1] Vladimir Batagelj and Ulrik Brandes,
       "Efficient generation of large random networks",
       Phys. Rev. E, 71, 036113, 2005.
    """
    G = nx.Graph()
    G = _add_nodes_with_bipartite_label(G, n, m)
    if directed:
        G = nx.DiGraph(G)
    G.name = f"fast_gnp_random_graph({n},{m},{p})"

    if p <= 0:
        return G
    if p >= 1:
        return nx.complete_bipartite_graph(n, m)

    lp = math.log(1.0 - p)

    v = 0
    w = -1
    while v < n:
        lr = math.log(1.0 - seed.random())
        w = w + 1 + int(lr / lp)
        while w >= m and v < n:
            w = w - m
            v = v + 1
        if v < n:
            G.add_edge(v, n + w)

    if directed:
        # use the same algorithm to
        # add edges from the "m" to "n" set
        v = 0
        w = -1
        while v < n:
            lr = math.log(1.0 - seed.random())
            w = w + 1 + int(lr / lp)
            while w >= m and v < n:
                w = w - m
                v = v + 1
            if v < n:
                G.add_edge(n + w, v)

    return G


@py_random_state(3)
@nx._dispatchable(graphs=None, returns_graph=True)
def gnmk_random_graph(n, m, k, seed=None, directed=False):
    """Returns a random bipartite graph G_{n,m,k}.

    Produces a bipartite graph chosen randomly out of the set of all graphs
    with n top nodes, m bottom nodes, and k edges.
    The graph is composed of two sets of nodes.
    Set A has nodes 0 to (n - 1) and set B has nodes n to (n + m - 1).

    Parameters
    ----------
    n : int
        The number of nodes in the first bipartite set.
    m : int
        The number of nodes in the second bipartite set.
    k : int
        The number of edges
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.
    directed : bool, optional (default=False)
        If True return a directed graph

    Examples
    --------
    from nx.algorithms import bipartite
    G = bipartite.gnmk_random_graph(10,20,50)

    See Also
    --------
    gnm_random_graph

    Notes
    -----
    If k > m * n then a complete bipartite graph is returned.

    This graph is a bipartite version of the `G_{nm}` random graph model.

    The nodes are assigned the attribute 'bipartite' with the value 0 or 1
    to indicate which bipartite set the node belongs to.

    This function is not imported in the main namespace.
    To use it use nx.bipartite.gnmk_random_graph
    """
    G = nx.Graph()
    G = _add_nodes_with_bipartite_label(G, n, m)
    if directed:
        G = nx.DiGraph(G)
    G.name = f"bipartite_gnm_random_graph({n},{m},{k})"
    if n == 1 or m == 1:
        return G
    max_edges = n * m  # max_edges for bipartite networks
    if k >= max_edges:  # Maybe we should raise an exception here
        return nx.complete_bipartite_graph(n, m, create_using=G)

    top = [n for n, d in G.nodes(data=True) if d["bipartite"] == 0]
    bottom = list(set(G) - set(top))
    edge_count = 0
    while edge_count < k:
        # generate random edge,u,v
        u = seed.choice(top)
        v = seed.choice(bottom)
        if v in G[u]:
            continue
        else:
            G.add_edge(u, v)
            edge_count += 1
    return G


def _add_nodes_with_bipartite_label(G, lena, lenb):
    G.add_nodes_from(range(lena + lenb))
    b = dict(zip(range(lena), [0] * lena))
    b.update(dict(zip(range(lena, lena + lenb), [1] * lenb)))
    nx.set_node_attributes(G, b, "bipartite")
    return G
