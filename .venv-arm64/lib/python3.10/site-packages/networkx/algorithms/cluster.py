"""Algorithms to characterize the number of triangles in a graph."""

from collections import Counter
from itertools import chain, combinations

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = [
    "triangles",
    "average_clustering",
    "clustering",
    "transitivity",
    "square_clustering",
    "generalized_degree",
]


@not_implemented_for("directed")
@nx._dispatchable
def triangles(G, nodes=None):
    """Compute the number of triangles.

    Finds the number of triangles that include a node as one vertex.

    Parameters
    ----------
    G : graph
       A networkx graph

    nodes : node, iterable of nodes, or None (default=None)
        If a singleton node, return the number of triangles for that node.
        If an iterable, compute the number of triangles for each of those nodes.
        If `None` (the default) compute the number of triangles for all nodes in `G`.

    Returns
    -------
    out : dict or int
       If `nodes` is a container of nodes, returns number of triangles keyed by node (dict).
       If `nodes` is a specific node, returns number of triangles for the node (int).

    Examples
    --------
    >>> G = nx.complete_graph(5)
    >>> print(nx.triangles(G, 0))
    6
    >>> print(nx.triangles(G))
    {0: 6, 1: 6, 2: 6, 3: 6, 4: 6}
    >>> print(list(nx.triangles(G, [0, 1]).values()))
    [6, 6]

    Notes
    -----
    Self loops are ignored.

    """
    if nodes is not None:
        # If `nodes` represents a single node, return only its number of triangles
        if nodes in G:
            return next(_triangles_and_degree_iter(G, nodes))[2] // 2

        # if `nodes` is a container of nodes, then return a
        # dictionary mapping node to number of triangles.
        return {v: t // 2 for v, d, t, _ in _triangles_and_degree_iter(G, nodes)}

    # if nodes is None, then compute triangles for the complete graph

    # dict used to avoid visiting the same nodes twice
    # this allows calculating/counting each triangle only once
    later_nbrs = {}

    # iterate over the nodes in a graph
    for node, neighbors in G.adjacency():
        later_nbrs[node] = {n for n in neighbors if n not in later_nbrs and n != node}

    # instantiate Counter for each node to include isolated nodes
    # add 1 to the count if a nodes neighbor's neighbor is also a neighbor
    triangle_counts = Counter(dict.fromkeys(G, 0))
    for node1, neighbors in later_nbrs.items():
        for node2 in neighbors:
            third_nodes = neighbors & later_nbrs[node2]
            m = len(third_nodes)
            triangle_counts[node1] += m
            triangle_counts[node2] += m
            triangle_counts.update(third_nodes)

    return dict(triangle_counts)


@not_implemented_for("multigraph")
def _triangles_and_degree_iter(G, nodes=None):
    """Return an iterator of (node, degree, triangles, generalized degree).

    This double counts triangles so you may want to divide by 2.
    See degree(), triangles() and generalized_degree() for definitions
    and details.

    """
    if nodes is None:
        nodes_nbrs = G.adj.items()
    else:
        nodes_nbrs = ((n, G[n]) for n in G.nbunch_iter(nodes))

    for v, v_nbrs in nodes_nbrs:
        vs = set(v_nbrs) - {v}
        gen_degree = Counter(len(vs & (set(G[w]) - {w})) for w in vs)
        ntriangles = sum(k * val for k, val in gen_degree.items())
        yield (v, len(vs), ntriangles, gen_degree)


@not_implemented_for("multigraph")
def _weighted_triangles_and_degree_iter(G, nodes=None, weight="weight"):
    """Return an iterator of (node, degree, weighted_triangles).

    Used for weighted clustering.
    Note: this returns the geometric average weight of edges in the triangle.
    Also, each triangle is counted twice (each direction).
    So you may want to divide by 2.

    """
    import numpy as np

    if weight is None or G.number_of_edges() == 0:
        max_weight = 1
    else:
        max_weight = max(d.get(weight, 1) for u, v, d in G.edges(data=True))
    if nodes is None:
        nodes_nbrs = G.adj.items()
    else:
        nodes_nbrs = ((n, G[n]) for n in G.nbunch_iter(nodes))

    def wt(u, v):
        return G[u][v].get(weight, 1) / max_weight

    for i, nbrs in nodes_nbrs:
        inbrs = set(nbrs) - {i}
        weighted_triangles = 0
        seen = set()
        for j in inbrs:
            seen.add(j)
            # This avoids counting twice -- we double at the end.
            jnbrs = set(G[j]) - seen
            # Only compute the edge weight once, before the inner inner
            # loop.
            wij = wt(i, j)
            weighted_triangles += np.cbrt(
                [(wij * wt(j, k) * wt(k, i)) for k in inbrs & jnbrs]
            ).sum()
        yield (i, len(inbrs), 2 * float(weighted_triangles))


@not_implemented_for("multigraph")
def _directed_triangles_and_degree_iter(G, nodes=None):
    """Return an iterator of
    (node, total_degree, reciprocal_degree, directed_triangles).

    Used for directed clustering.
    Note that unlike `_triangles_and_degree_iter()`, this function counts
    directed triangles so does not count triangles twice.

    """
    nodes_nbrs = ((n, G._pred[n], G._succ[n]) for n in G.nbunch_iter(nodes))

    for i, preds, succs in nodes_nbrs:
        ipreds = set(preds) - {i}
        isuccs = set(succs) - {i}

        directed_triangles = 0
        for j in chain(ipreds, isuccs):
            jpreds = set(G._pred[j]) - {j}
            jsuccs = set(G._succ[j]) - {j}
            directed_triangles += sum(
                1
                for k in chain(
                    (ipreds & jpreds),
                    (ipreds & jsuccs),
                    (isuccs & jpreds),
                    (isuccs & jsuccs),
                )
            )
        dtotal = len(ipreds) + len(isuccs)
        dbidirectional = len(ipreds & isuccs)
        yield (i, dtotal, dbidirectional, directed_triangles)


@not_implemented_for("multigraph")
def _directed_weighted_triangles_and_degree_iter(G, nodes=None, weight="weight"):
    """Return an iterator of
    (node, total_degree, reciprocal_degree, directed_weighted_triangles).

    Used for directed weighted clustering.
    Note that unlike `_weighted_triangles_and_degree_iter()`, this function counts
    directed triangles so does not count triangles twice.

    """
    import numpy as np

    if weight is None or G.number_of_edges() == 0:
        max_weight = 1
    else:
        max_weight = max(d.get(weight, 1) for u, v, d in G.edges(data=True))

    nodes_nbrs = ((n, G._pred[n], G._succ[n]) for n in G.nbunch_iter(nodes))

    def wt(u, v):
        return G[u][v].get(weight, 1) / max_weight

    for i, preds, succs in nodes_nbrs:
        ipreds = set(preds) - {i}
        isuccs = set(succs) - {i}

        directed_triangles = 0
        for j in ipreds:
            jpreds = set(G._pred[j]) - {j}
            jsuccs = set(G._succ[j]) - {j}
            directed_triangles += np.cbrt(
                [(wt(j, i) * wt(k, i) * wt(k, j)) for k in ipreds & jpreds]
            ).sum()
            directed_triangles += np.cbrt(
                [(wt(j, i) * wt(k, i) * wt(j, k)) for k in ipreds & jsuccs]
            ).sum()
            directed_triangles += np.cbrt(
                [(wt(j, i) * wt(i, k) * wt(k, j)) for k in isuccs & jpreds]
            ).sum()
            directed_triangles += np.cbrt(
                [(wt(j, i) * wt(i, k) * wt(j, k)) for k in isuccs & jsuccs]
            ).sum()

        for j in isuccs:
            jpreds = set(G._pred[j]) - {j}
            jsuccs = set(G._succ[j]) - {j}
            directed_triangles += np.cbrt(
                [(wt(i, j) * wt(k, i) * wt(k, j)) for k in ipreds & jpreds]
            ).sum()
            directed_triangles += np.cbrt(
                [(wt(i, j) * wt(k, i) * wt(j, k)) for k in ipreds & jsuccs]
            ).sum()
            directed_triangles += np.cbrt(
                [(wt(i, j) * wt(i, k) * wt(k, j)) for k in isuccs & jpreds]
            ).sum()
            directed_triangles += np.cbrt(
                [(wt(i, j) * wt(i, k) * wt(j, k)) for k in isuccs & jsuccs]
            ).sum()

        dtotal = len(ipreds) + len(isuccs)
        dbidirectional = len(ipreds & isuccs)
        yield (i, dtotal, dbidirectional, float(directed_triangles))


@nx._dispatchable(edge_attrs="weight")
def average_clustering(G, nodes=None, weight=None, count_zeros=True):
    r"""Compute the average clustering coefficient for the graph G.

    The clustering coefficient for the graph is the average,

    .. math::

       C = \frac{1}{n}\sum_{v \in G} c_v,

    where :math:`n` is the number of nodes in `G`.

    Parameters
    ----------
    G : graph

    nodes : container of nodes, optional (default=all nodes in G)
       Compute average clustering for nodes in this container.

    weight : string or None, optional (default=None)
       The edge attribute that holds the numerical value used as a weight.
       If None, then each edge has weight 1.

    count_zeros : bool
       If False include only the nodes with nonzero clustering in the average.

    Returns
    -------
    avg : float
       Average clustering

    Examples
    --------
    >>> G = nx.complete_graph(5)
    >>> print(nx.average_clustering(G))
    1.0

    Notes
    -----
    This is a space saving routine; it might be faster
    to use the clustering function to get a list and then take the average.

    Self loops are ignored.

    References
    ----------
    .. [1] Generalizations of the clustering coefficient to weighted
       complex networks by J. Saramäki, M. Kivelä, J.-P. Onnela,
       K. Kaski, and J. Kertész, Physical Review E, 75 027105 (2007).
       http://jponnela.com/web_documents/a9.pdf
    .. [2] Marcus Kaiser,  Mean clustering coefficients: the role of isolated
       nodes and leafs on clustering measures for small-world networks.
       https://arxiv.org/abs/0802.2512
    """
    c = clustering(G, nodes, weight=weight).values()
    if not count_zeros:
        c = [v for v in c if abs(v) > 0]
    return sum(c) / len(c)


@nx._dispatchable(edge_attrs="weight")
def clustering(G, nodes=None, weight=None):
    r"""Compute the clustering coefficient for nodes.

    For unweighted graphs, the clustering of a node :math:`u`
    is the fraction of possible triangles through that node that exist,

    .. math::

      c_u = \frac{2 T(u)}{deg(u)(deg(u)-1)},

    where :math:`T(u)` is the number of triangles through node :math:`u` and
    :math:`deg(u)` is the degree of :math:`u`.

    For weighted graphs, there are several ways to define clustering [1]_.
    the one used here is defined
    as the geometric average of the subgraph edge weights [2]_,

    .. math::

       c_u = \frac{1}{deg(u)(deg(u)-1))}
             \sum_{vw} (\hat{w}_{uv} \hat{w}_{uw} \hat{w}_{vw})^{1/3}.

    The edge weights :math:`\hat{w}_{uv}` are normalized by the maximum weight
    in the network :math:`\hat{w}_{uv} = w_{uv}/\max(w)`.

    The value of :math:`c_u` is assigned to 0 if :math:`deg(u) < 2`.

    Additionally, this weighted definition has been generalized to support negative edge weights [3]_.

    For directed graphs, the clustering is similarly defined as the fraction
    of all possible directed triangles or geometric average of the subgraph
    edge weights for unweighted and weighted directed graph respectively [4]_.

    .. math::

       c_u = \frac{T(u)}{2(deg^{tot}(u)(deg^{tot}(u)-1) - 2deg^{\leftrightarrow}(u))},

    where :math:`T(u)` is the number of directed triangles through node
    :math:`u`, :math:`deg^{tot}(u)` is the sum of in degree and out degree of
    :math:`u` and :math:`deg^{\leftrightarrow}(u)` is the reciprocal degree of
    :math:`u`.


    Parameters
    ----------
    G : graph

    nodes : node, iterable of nodes, or None (default=None)
        If a singleton node, return the number of triangles for that node.
        If an iterable, compute the number of triangles for each of those nodes.
        If `None` (the default) compute the number of triangles for all nodes in `G`.

    weight : string or None, optional (default=None)
       The edge attribute that holds the numerical value used as a weight.
       If None, then each edge has weight 1.

    Returns
    -------
    out : float, or dictionary
       Clustering coefficient at specified nodes

    Examples
    --------
    >>> G = nx.complete_graph(5)
    >>> print(nx.clustering(G, 0))
    1.0
    >>> print(nx.clustering(G))
    {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0}

    Notes
    -----
    Self loops are ignored.

    References
    ----------
    .. [1] Generalizations of the clustering coefficient to weighted
       complex networks by J. Saramäki, M. Kivelä, J.-P. Onnela,
       K. Kaski, and J. Kertész, Physical Review E, 75 027105 (2007).
       http://jponnela.com/web_documents/a9.pdf
    .. [2] Intensity and coherence of motifs in weighted complex
       networks by J. P. Onnela, J. Saramäki, J. Kertész, and K. Kaski,
       Physical Review E, 71(6), 065103 (2005).
    .. [3] Generalization of Clustering Coefficients to Signed Correlation Networks
       by G. Costantini and M. Perugini, PloS one, 9(2), e88669 (2014).
    .. [4] Clustering in complex directed networks by G. Fagiolo,
       Physical Review E, 76(2), 026107 (2007).
    """
    if G.is_directed():
        if weight is not None:
            td_iter = _directed_weighted_triangles_and_degree_iter(G, nodes, weight)
            clusterc = {
                v: 0 if t == 0 else t / ((dt * (dt - 1) - 2 * db) * 2)
                for v, dt, db, t in td_iter
            }
        else:
            td_iter = _directed_triangles_and_degree_iter(G, nodes)
            clusterc = {
                v: 0 if t == 0 else t / ((dt * (dt - 1) - 2 * db) * 2)
                for v, dt, db, t in td_iter
            }
    else:
        # The formula 2*T/(d*(d-1)) from docs is t/(d*(d-1)) here b/c t==2*T
        if weight is not None:
            td_iter = _weighted_triangles_and_degree_iter(G, nodes, weight)
            clusterc = {v: 0 if t == 0 else t / (d * (d - 1)) for v, d, t in td_iter}
        else:
            td_iter = _triangles_and_degree_iter(G, nodes)
            clusterc = {v: 0 if t == 0 else t / (d * (d - 1)) for v, d, t, _ in td_iter}
    if nodes in G:
        # Return the value of the sole entry in the dictionary.
        return clusterc[nodes]
    return clusterc


@nx._dispatchable
def transitivity(G):
    r"""Compute graph transitivity, the fraction of all possible triangles
    present in G.

    Possible triangles are identified by the number of "triads"
    (two edges with a shared vertex).

    The transitivity is

    .. math::

        T = 3\frac{\#triangles}{\#triads}.

    Parameters
    ----------
    G : graph

    Returns
    -------
    out : float
       Transitivity

    Notes
    -----
    Self loops are ignored.

    Examples
    --------
    >>> G = nx.complete_graph(5)
    >>> print(nx.transitivity(G))
    1.0
    """
    triangles_contri = [
        (t, d * (d - 1)) for v, d, t, _ in _triangles_and_degree_iter(G)
    ]
    # If the graph is empty
    if len(triangles_contri) == 0:
        return 0
    triangles, contri = map(sum, zip(*triangles_contri))
    return 0 if triangles == 0 else triangles / contri


@nx._dispatchable
def square_clustering(G, nodes=None):
    r"""Compute the squares clustering coefficient for nodes.

    For each node return the fraction of possible squares that exist at
    the node [1]_

    .. math::
       C_4(v) = \frac{ \sum_{u=1}^{k_v}
       \sum_{w=u+1}^{k_v} q_v(u,w) }{ \sum_{u=1}^{k_v}
       \sum_{w=u+1}^{k_v} [a_v(u,w) + q_v(u,w)]},

    where :math:`q_v(u,w)` are the number of common neighbors of :math:`u` and
    :math:`w` other than :math:`v` (ie squares), and :math:`a_v(u,w) = (k_u -
    (1+q_v(u,w)+\theta_{uv})) + (k_w - (1+q_v(u,w)+\theta_{uw}))`, where
    :math:`\theta_{uw} = 1` if :math:`u` and :math:`w` are connected and 0
    otherwise. [2]_

    Parameters
    ----------
    G : graph

    nodes : container of nodes, optional (default=all nodes in G)
       Compute clustering for nodes in this container.

    Returns
    -------
    c4 : dictionary
       A dictionary keyed by node with the square clustering coefficient value.

    Examples
    --------
    >>> G = nx.complete_graph(5)
    >>> print(nx.square_clustering(G, 0))
    1.0
    >>> print(nx.square_clustering(G))
    {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0}

    Notes
    -----
    While :math:`C_3(v)` (triangle clustering) gives the probability that
    two neighbors of node v are connected with each other, :math:`C_4(v)` is
    the probability that two neighbors of node v share a common
    neighbor different from v. This algorithm can be applied to both
    bipartite and unipartite networks.

    References
    ----------
    .. [1] Pedro G. Lind, Marta C. González, and Hans J. Herrmann. 2005
        Cycles and clustering in bipartite networks.
        Physical Review E (72) 056127.
    .. [2] Zhang, Peng et al. Clustering Coefficient and Community Structure of
        Bipartite Networks. Physica A: Statistical Mechanics and its Applications 387.27 (2008): 6869–6875.
        https://arxiv.org/abs/0710.0117v1
    """
    if nodes is None:
        node_iter = G
    else:
        node_iter = G.nbunch_iter(nodes)
    clustering = {}
    for v in node_iter:
        clustering[v] = 0
        potential = 0
        for u, w in combinations(G[v], 2):
            squares = len((set(G[u]) & set(G[w])) - {v})
            clustering[v] += squares
            degm = squares + 1
            if w in G[u]:
                degm += 1
            potential += (len(G[u]) - degm) + (len(G[w]) - degm) + squares
        if potential > 0:
            clustering[v] /= potential
    if nodes in G:
        # Return the value of the sole entry in the dictionary.
        return clustering[nodes]
    return clustering


@not_implemented_for("directed")
@nx._dispatchable
def generalized_degree(G, nodes=None):
    r"""Compute the generalized degree for nodes.

    For each node, the generalized degree shows how many edges of given
    triangle multiplicity the node is connected to. The triangle multiplicity
    of an edge is the number of triangles an edge participates in. The
    generalized degree of node :math:`i` can be written as a vector
    :math:`\mathbf{k}_i=(k_i^{(0)}, \dotsc, k_i^{(N-2)})` where
    :math:`k_i^{(j)}` is the number of edges attached to node :math:`i` that
    participate in :math:`j` triangles.

    Parameters
    ----------
    G : graph

    nodes : container of nodes, optional (default=all nodes in G)
       Compute the generalized degree for nodes in this container.

    Returns
    -------
    out : Counter, or dictionary of Counters
       Generalized degree of specified nodes. The Counter is keyed by edge
       triangle multiplicity.

    Examples
    --------
    >>> G = nx.complete_graph(5)
    >>> print(nx.generalized_degree(G, 0))
    Counter({3: 4})
    >>> print(nx.generalized_degree(G))
    {0: Counter({3: 4}), 1: Counter({3: 4}), 2: Counter({3: 4}), 3: Counter({3: 4}), 4: Counter({3: 4})}

    To recover the number of triangles attached to a node:

    >>> k1 = nx.generalized_degree(G, 0)
    >>> sum([k * v for k, v in k1.items()]) / 2 == nx.triangles(G, 0)
    True

    Notes
    -----
    Self loops are ignored.

    In a network of N nodes, the highest triangle multiplicity an edge can have
    is N-2.

    The return value does not include a `zero` entry if no edges of a
    particular triangle multiplicity are present.

    The number of triangles node :math:`i` is attached to can be recovered from
    the generalized degree :math:`\mathbf{k}_i=(k_i^{(0)}, \dotsc,
    k_i^{(N-2)})` by :math:`(k_i^{(1)}+2k_i^{(2)}+\dotsc +(N-2)k_i^{(N-2)})/2`.

    References
    ----------
    .. [1] Networks with arbitrary edge multiplicities by V. Zlatić,
        D. Garlaschelli and G. Caldarelli, EPL (Europhysics Letters),
        Volume 97, Number 2 (2012).
        https://iopscience.iop.org/article/10.1209/0295-5075/97/28005
    """
    if nodes in G:
        return next(_triangles_and_degree_iter(G, nodes))[3]
    return {v: gd for v, d, t, gd in _triangles_and_degree_iter(G, nodes)}
