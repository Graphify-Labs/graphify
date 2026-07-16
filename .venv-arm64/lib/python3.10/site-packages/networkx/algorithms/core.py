"""
Find the k-cores of a graph.

The k-core is found by recursively pruning nodes with degrees less than k.

See the following references for details:

An O(m) Algorithm for Cores Decomposition of Networks
Vladimir Batagelj and Matjaz Zaversnik, 2003.
https://arxiv.org/abs/cs.DS/0310049

Generalized Cores
Vladimir Batagelj and Matjaz Zaversnik, 2002.
https://arxiv.org/pdf/cs/0202039

For directed graphs a more general notion is that of D-cores which
looks at (k, l) restrictions on (in, out) degree. The (k, k) D-core
is the k-core.

D-cores: Measuring Collaboration of Directed Graphs Based on Degeneracy
Christos Giatsidis, Dimitrios M. Thilikos, Michalis Vazirgiannis, ICDM 2011.
http://www.graphdegeneracy.org/dcores_ICDM_2011.pdf

Multi-scale structure and topological anomaly detection via a new network \
statistic: The onion decomposition
L. Hébert-Dufresne, J. A. Grochow, and A. Allard
Scientific Reports 6, 31708 (2016)
http://doi.org/10.1038/srep31708

"""

import networkx as nx

__all__ = [
    "core_number",
    "k_core",
    "k_shell",
    "k_crust",
    "k_corona",
    "k_truss",
    "onion_layers",
]


@nx.utils.not_implemented_for("multigraph")
@nx._dispatchable
def core_number(G):
    """Returns the core number for each node.

    A k-core is a maximal subgraph that contains nodes of degree k or more.

    The core number of a node is the largest value k of a k-core containing
    that node.

    Parameters
    ----------
    G : NetworkX graph
       An undirected or directed graph

    Returns
    -------
    core_number : dictionary
       A dictionary keyed by node to the core number.

    Raises
    ------
    NetworkXNotImplemented
        If `G` is a multigraph or contains self loops.

    Notes
    -----
    For directed graphs the node degree is defined to be the
    in-degree + out-degree.

    Examples
    --------
    >>> degrees = [0, 1, 2, 2, 2, 2, 3]
    >>> H = nx.havel_hakimi_graph(degrees)
    >>> nx.core_number(H)
    {0: 1, 1: 2, 2: 2, 3: 2, 4: 1, 5: 2, 6: 0}
    >>> G = nx.DiGraph()
    >>> G.add_edges_from([(1, 2), (2, 1), (2, 3), (2, 4), (3, 4), (4, 3)])
    >>> nx.core_number(G)
    {1: 2, 2: 2, 3: 2, 4: 2}

    References
    ----------
    .. [1] An O(m) Algorithm for Cores Decomposition of Networks
       Vladimir Batagelj and Matjaz Zaversnik, 2003.
       https://arxiv.org/abs/cs.DS/0310049
    """
    if nx.number_of_selfloops(G) > 0:
        msg = (
            "Input graph has self loops which is not permitted; "
            "Consider using G.remove_edges_from(nx.selfloop_edges(G))."
        )
        raise nx.NetworkXNotImplemented(msg)
    degrees = dict(G.degree())
    # Sort nodes by degree.
    nodes = sorted(degrees, key=degrees.get)
    bin_boundaries = [0]
    curr_degree = 0
    for i, v in enumerate(nodes):
        if degrees[v] > curr_degree:
            bin_boundaries.extend([i] * (degrees[v] - curr_degree))
            curr_degree = degrees[v]
    node_pos = {v: pos for pos, v in enumerate(nodes)}
    # The initial guess for the core number of a node is its degree.
    core = degrees
    nbrs = {v: list(nx.all_neighbors(G, v)) for v in G}
    for v in nodes:
        for u in nbrs[v]:
            if core[u] > core[v]:
                nbrs[u].remove(v)
                pos = node_pos[u]
                bin_start = bin_boundaries[core[u]]
                node_pos[u] = bin_start
                node_pos[nodes[bin_start]] = pos
                nodes[bin_start], nodes[pos] = nodes[pos], nodes[bin_start]
                bin_boundaries[core[u]] += 1
                core[u] -= 1
    return core


def _core_subgraph(G, k_filter, k=None, core=None):
    """Returns the subgraph induced by nodes passing filter `k_filter`.

    Parameters
    ----------
    G : NetworkX graph
       The graph or directed graph to process
    k_filter : filter function
       This function filters the nodes chosen. It takes three inputs:
       A node of G, the filter's cutoff, and the core dict of the graph.
       The function should return a Boolean value.
    k : int, optional
      The order of the core. If not specified use the max core number.
      This value is used as the cutoff for the filter.
    core : dict, optional
      Precomputed core numbers keyed by node for the graph `G`.
      If not specified, the core numbers will be computed from `G`.

    """
    if core is None:
        core = core_number(G)
    if k is None:
        k = max(core.values())
    nodes = (v for v in core if k_filter(v, k, core))
    return G.subgraph(nodes).copy()


@nx._dispatchable(preserve_all_attrs=True, returns_graph=True)
def k_core(G, k=None, core_number=None):
    """Returns the k-core of G.

    A k-core is a maximal subgraph that contains nodes of degree `k` or more.

    .. deprecated:: 3.3
       `k_core` will not accept `MultiGraph` objects in version 3.5.

    Parameters
    ----------
    G : NetworkX graph
      A graph or directed graph
    k : int, optional
      The order of the core. If not specified return the main core.
    core_number : dictionary, optional
      Precomputed core numbers for the graph G.

    Returns
    -------
    G : NetworkX graph
      The k-core subgraph

    Raises
    ------
    NetworkXNotImplemented
      The k-core is not defined for multigraphs or graphs with self loops.

    Notes
    -----
    The main core is the core with `k` as the largest core_number.

    For directed graphs the node degree is defined to be the
    in-degree + out-degree.

    Graph, node, and edge attributes are copied to the subgraph.

    Examples
    --------
    >>> degrees = [0, 1, 2, 2, 2, 2, 3]
    >>> H = nx.havel_hakimi_graph(degrees)
    >>> H.degree
    DegreeView({0: 1, 1: 2, 2: 2, 3: 2, 4: 2, 5: 3, 6: 0})
    >>> nx.k_core(H).nodes
    NodeView((1, 2, 3, 5))

    See Also
    --------
    core_number

    References
    ----------
    .. [1] An O(m) Algorithm for Cores Decomposition of Networks
       Vladimir Batagelj and Matjaz Zaversnik,  2003.
       https://arxiv.org/abs/cs.DS/0310049
    """

    import warnings

    if G.is_multigraph():
        warnings.warn(
            (
                "\n\n`k_core` will not accept `MultiGraph` objects in version 3.5.\n"
                "Convert it to an undirected graph instead, using::\n\n"
                "\tG = nx.Graph(G)\n"
            ),
            category=DeprecationWarning,
            stacklevel=5,
        )

    def k_filter(v, k, c):
        return c[v] >= k

    return _core_subgraph(G, k_filter, k, core_number)


@nx._dispatchable(preserve_all_attrs=True, returns_graph=True)
def k_shell(G, k=None, core_number=None):
    """Returns the k-shell of G.

    The k-shell is the subgraph induced by nodes with core number k.
    That is, nodes in the k-core that are not in the (k+1)-core.

    .. deprecated:: 3.3
       `k_shell` will not accept `MultiGraph` objects in version 3.5.

    Parameters
    ----------
    G : NetworkX graph
      A graph or directed graph.
    k : int, optional
      The order of the shell. If not specified return the outer shell.
    core_number : dictionary, optional
      Precomputed core numbers for the graph G.


    Returns
    -------
    G : NetworkX graph
       The k-shell subgraph

    Raises
    ------
    NetworkXNotImplemented
        The k-shell is not implemented for multigraphs or graphs with self loops.

    Notes
    -----
    This is similar to k_corona but in that case only neighbors in the
    k-core are considered.

    For directed graphs the node degree is defined to be the
    in-degree + out-degree.

    Graph, node, and edge attributes are copied to the subgraph.

    Examples
    --------
    >>> degrees = [0, 1, 2, 2, 2, 2, 3]
    >>> H = nx.havel_hakimi_graph(degrees)
    >>> H.degree
    DegreeView({0: 1, 1: 2, 2: 2, 3: 2, 4: 2, 5: 3, 6: 0})
    >>> nx.k_shell(H, k=1).nodes
    NodeView((0, 4))

    See Also
    --------
    core_number
    k_corona


    References
    ----------
    .. [1] A model of Internet topology using k-shell decomposition
       Shai Carmi, Shlomo Havlin, Scott Kirkpatrick, Yuval Shavitt,
       and Eran Shir, PNAS  July 3, 2007   vol. 104  no. 27  11150-11154
       http://www.pnas.org/content/104/27/11150.full
    """

    import warnings

    if G.is_multigraph():
        warnings.warn(
            (
                "\n\n`k_shell` will not accept `MultiGraph` objects in version 3.5.\n"
                "Convert it to an undirected graph instead, using::\n\n"
                "\tG = nx.Graph(G)\n"
            ),
            category=DeprecationWarning,
            stacklevel=5,
        )

    def k_filter(v, k, c):
        return c[v] == k

    return _core_subgraph(G, k_filter, k, core_number)


@nx._dispatchable(preserve_all_attrs=True, returns_graph=True)
def k_crust(G, k=None, core_number=None):
    """Returns the k-crust of G.

    The k-crust is the graph G with the edges of the k-core removed
    and isolated nodes found after the removal of edges are also removed.

    .. deprecated:: 3.3
       `k_crust` will not accept `MultiGraph` objects in version 3.5.

    Parameters
    ----------
    G : NetworkX graph
       A graph or directed graph.
    k : int, optional
      The order of the shell. If not specified return the main crust.
    core_number : dictionary, optional
      Precomputed core numbers for the graph G.

    Returns
    -------
    G : NetworkX graph
       The k-crust subgraph

    Raises
    ------
    NetworkXNotImplemented
        The k-crust is not implemented for multigraphs or graphs with self loops.

    Notes
    -----
    This definition of k-crust is different than the definition in [1]_.
    The k-crust in [1]_ is equivalent to the k+1 crust of this algorithm.

    For directed graphs the node degree is defined to be the
    in-degree + out-degree.

    Graph, node, and edge attributes are copied to the subgraph.

    Examples
    --------
    >>> degrees = [0, 1, 2, 2, 2, 2, 3]
    >>> H = nx.havel_hakimi_graph(degrees)
    >>> H.degree
    DegreeView({0: 1, 1: 2, 2: 2, 3: 2, 4: 2, 5: 3, 6: 0})
    >>> nx.k_crust(H, k=1).nodes
    NodeView((0, 4, 6))

    See Also
    --------
    core_number

    References
    ----------
    .. [1] A model of Internet topology using k-shell decomposition
       Shai Carmi, Shlomo Havlin, Scott Kirkpatrick, Yuval Shavitt,
       and Eran Shir, PNAS  July 3, 2007   vol. 104  no. 27  11150-11154
       http://www.pnas.org/content/104/27/11150.full
    """

    import warnings

    if G.is_multigraph():
        warnings.warn(
            (
                "\n\n`k_crust` will not accept `MultiGraph` objects in version 3.5.\n"
                "Convert it to an undirected graph instead, using::\n\n"
                "\tG = nx.Graph(G)\n"
            ),
            category=DeprecationWarning,
            stacklevel=5,
        )

    # Default for k is one less than in _core_subgraph, so just inline.
    #    Filter is c[v] <= k
    if core_number is None:
        core_number = nx.core_number(G)
    if k is None:
        k = max(core_number.values()) - 1
    nodes = (v for v in core_number if core_number[v] <= k)
    return G.subgraph(nodes).copy()


@nx._dispatchable(preserve_all_attrs=True, returns_graph=True)
def k_corona(G, k, core_number=None):
    """Returns the k-corona of G.

    The k-corona is the subgraph of nodes in the k-core which have
    exactly k neighbors in the k-core.

    .. deprecated:: 3.3
       `k_corona` will not accept `MultiGraph` objects in version 3.5.

    Parameters
    ----------
    G : NetworkX graph
       A graph or directed graph
    k : int
       The order of the corona.
    core_number : dictionary, optional
       Precomputed core numbers for the graph G.

    Returns
    -------
    G : NetworkX graph
       The k-corona subgraph

    Raises
    ------
    NetworkXNotImplemented
        The k-corona is not defined for multigraphs or graphs with self loops.

    Notes
    -----
    For directed graphs the node degree is defined to be the
    in-degree + out-degree.

    Graph, node, and edge attributes are copied to the subgraph.

    Examples
    --------
    >>> degrees = [0, 1, 2, 2, 2, 2, 3]
    >>> H = nx.havel_hakimi_graph(degrees)
    >>> H.degree
    DegreeView({0: 1, 1: 2, 2: 2, 3: 2, 4: 2, 5: 3, 6: 0})
    >>> nx.k_corona(H, k=2).nodes
    NodeView((1, 2, 3, 5))

    See Also
    --------
    core_number

    References
    ----------
    .. [1]  k -core (bootstrap) percolation on complex networks:
       Critical phenomena and nonlocal effects,
       A. V. Goltsev, S. N. Dorogovtsev, and J. F. F. Mendes,
       Phys. Rev. E 73, 056101 (2006)
       http://link.aps.org/doi/10.1103/PhysRevE.73.056101
    """

    import warnings

    if G.is_multigraph():
        warnings.warn(
            (
                "\n\n`k_corona` will not accept `MultiGraph` objects in version 3.5.\n"
                "Convert it to an undirected graph instead, using::\n\n"
                "\tG = nx.Graph(G)\n"
            ),
            category=DeprecationWarning,
            stacklevel=5,
        )

    def func(v, k, c):
        return c[v] == k and k == sum(1 for w in G[v] if c[w] >= k)

    return _core_subgraph(G, func, k, core_number)


@nx.utils.not_implemented_for("directed")
@nx.utils.not_implemented_for("multigraph")
@nx._dispatchable(preserve_all_attrs=True, returns_graph=True)
def k_truss(G, k):
    """Returns the k-truss of `G`.

    The k-truss is the maximal induced subgraph of `G` which contains at least
    three vertices where every edge is incident to at least `k-2` triangles.

    Parameters
    ----------
    G : NetworkX graph
      An undirected graph
    k : int
      The order of the truss

    Returns
    -------
    H : NetworkX graph
      The k-truss subgraph

    Raises
    ------
    NetworkXNotImplemented
      If `G` is a multigraph or directed graph or if it contains self loops.

    Notes
    -----
    A k-clique is a (k-2)-truss and a k-truss is a (k+1)-core.

    Graph, node, and edge attributes are copied to the subgraph.

    K-trusses were originally defined in [2] which states that the k-truss
    is the maximal induced subgraph where each edge belongs to at least
    `k-2` triangles. A more recent paper, [1], uses a slightly different
    definition requiring that each edge belong to at least `k` triangles.
    This implementation uses the original definition of `k-2` triangles.

    Examples
    --------
    >>> degrees = [0, 1, 2, 2, 2, 2, 3]
    >>> H = nx.havel_hakimi_graph(degrees)
    >>> H.degree
    DegreeView({0: 1, 1: 2, 2: 2, 3: 2, 4: 2, 5: 3, 6: 0})
    >>> nx.k_truss(H, k=2).nodes
    NodeView((0, 1, 2, 3, 4, 5))

    References
    ----------
    .. [1] Bounds and Algorithms for k-truss. Paul Burkhardt, Vance Faber,
       David G. Harris, 2018. https://arxiv.org/abs/1806.05523v2
    .. [2] Trusses: Cohesive Subgraphs for Social Network Analysis. Jonathan
       Cohen, 2005.
    """
    if nx.number_of_selfloops(G) > 0:
        msg = (
            "Input graph has self loops which is not permitted; "
            "Consider using G.remove_edges_from(nx.selfloop_edges(G))."
        )
        raise nx.NetworkXNotImplemented(msg)

    H = G.copy()

    n_dropped = 1
    while n_dropped > 0:
        n_dropped = 0
        to_drop = []
        seen = set()
        for u in H:
            nbrs_u = set(H[u])
            seen.add(u)
            new_nbrs = [v for v in nbrs_u if v not in seen]
            for v in new_nbrs:
                if len(nbrs_u & set(H[v])) < (k - 2):
                    to_drop.append((u, v))
        H.remove_edges_from(to_drop)
        n_dropped = len(to_drop)
        H.remove_nodes_from(list(nx.isolates(H)))

    return H


@nx.utils.not_implemented_for("multigraph")
@nx.utils.not_implemented_for("directed")
@nx._dispatchable
def onion_layers(G):
    """Returns the layer of each vertex in an onion decomposition of the graph.

    The onion decomposition refines the k-core decomposition by providing
    information on the internal organization of each k-shell. It is usually
    used alongside the `core numbers`.

    Parameters
    ----------
    G : NetworkX graph
        An undirected graph without self loops.

    Returns
    -------
    od_layers : dictionary
        A dictionary keyed by node to the onion layer. The layers are
        contiguous integers starting at 1.

    Raises
    ------
    NetworkXNotImplemented
        If `G` is a multigraph or directed graph or if it contains self loops.

    Examples
    --------
    >>> degrees = [0, 1, 2, 2, 2, 2, 3]
    >>> H = nx.havel_hakimi_graph(degrees)
    >>> H.degree
    DegreeView({0: 1, 1: 2, 2: 2, 3: 2, 4: 2, 5: 3, 6: 0})
    >>> nx.onion_layers(H)
    {6: 1, 0: 2, 4: 3, 1: 4, 2: 4, 3: 4, 5: 4}

    See Also
    --------
    core_number

    References
    ----------
    .. [1] Multi-scale structure and topological anomaly detection via a new
       network statistic: The onion decomposition
       L. Hébert-Dufresne, J. A. Grochow, and A. Allard
       Scientific Reports 6, 31708 (2016)
       http://doi.org/10.1038/srep31708
    .. [2] Percolation and the effective structure of complex networks
       A. Allard and L. Hébert-Dufresne
       Physical Review X 9, 011023 (2019)
       http://doi.org/10.1103/PhysRevX.9.011023
    """
    if nx.number_of_selfloops(G) > 0:
        msg = (
            "Input graph contains self loops which is not permitted; "
            "Consider using G.remove_edges_from(nx.selfloop_edges(G))."
        )
        raise nx.NetworkXNotImplemented(msg)
    # Dictionaries to register the k-core/onion decompositions.
    od_layers = {}
    # Adjacency list
    neighbors = {v: list(nx.all_neighbors(G, v)) for v in G}
    # Effective degree of nodes.
    degrees = dict(G.degree())
    # Performs the onion decomposition.
    current_core = 1
    current_layer = 1
    # Sets vertices of degree 0 to layer 1, if any.
    isolated_nodes = list(nx.isolates(G))
    if len(isolated_nodes) > 0:
        for v in isolated_nodes:
            od_layers[v] = current_layer
            degrees.pop(v)
        current_layer = 2
    # Finds the layer for the remaining nodes.
    while len(degrees) > 0:
        # Sets the order for looking at nodes.
        nodes = sorted(degrees, key=degrees.get)
        # Sets properly the current core.
        min_degree = degrees[nodes[0]]
        if min_degree > current_core:
            current_core = min_degree
        # Identifies vertices in the current layer.
        this_layer = []
        for n in nodes:
            if degrees[n] > current_core:
                break
            this_layer.append(n)
        # Identifies the core/layer of the vertices in the current layer.
        for v in this_layer:
            od_layers[v] = current_layer
            for n in neighbors[v]:
                neighbors[n].remove(v)
                degrees[n] = degrees[n] - 1
            degrees.pop(v)
        # Updates the layer count.
        current_layer = current_layer + 1
    # Returns the dictionaries containing the onion layer of each vertices.
    return od_layers
