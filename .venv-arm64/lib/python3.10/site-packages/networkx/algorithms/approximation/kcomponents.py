"""Fast approximation for k-component structure"""

import itertools
from collections import defaultdict
from collections.abc import Mapping
from functools import cached_property

import networkx as nx
from networkx.algorithms.approximation import local_node_connectivity
from networkx.exception import NetworkXError
from networkx.utils import not_implemented_for

__all__ = ["k_components"]


@not_implemented_for("directed")
@nx._dispatchable(name="approximate_k_components")
def k_components(G, min_density=0.95):
    r"""Returns the approximate k-component structure of a graph G.

    A `k`-component is a maximal subgraph of a graph G that has, at least,
    node connectivity `k`: we need to remove at least `k` nodes to break it
    into more components. `k`-components have an inherent hierarchical
    structure because they are nested in terms of connectivity: a connected
    graph can contain several 2-components, each of which can contain
    one or more 3-components, and so forth.

    This implementation is based on the fast heuristics to approximate
    the `k`-component structure of a graph [1]_. Which, in turn, it is based on
    a fast approximation algorithm for finding good lower bounds of the number
    of node independent paths between two nodes [2]_.

    Parameters
    ----------
    G : NetworkX graph
        Undirected graph

    min_density : Float
        Density relaxation threshold. Default value 0.95

    Returns
    -------
    k_components : dict
        Dictionary with connectivity level `k` as key and a list of
        sets of nodes that form a k-component of level `k` as values.

    Raises
    ------
    NetworkXNotImplemented
        If G is directed.

    Examples
    --------
    >>> # Petersen graph has 10 nodes and it is triconnected, thus all
    >>> # nodes are in a single component on all three connectivity levels
    >>> from networkx.algorithms import approximation as apxa
    >>> G = nx.petersen_graph()
    >>> k_components = apxa.k_components(G)

    Notes
    -----
    The logic of the approximation algorithm for computing the `k`-component
    structure [1]_ is based on repeatedly applying simple and fast algorithms
    for `k`-cores and biconnected components in order to narrow down the
    number of pairs of nodes over which we have to compute White and Newman's
    approximation algorithm for finding node independent paths [2]_. More
    formally, this algorithm is based on Whitney's theorem, which states
    an inclusion relation among node connectivity, edge connectivity, and
    minimum degree for any graph G. This theorem implies that every
    `k`-component is nested inside a `k`-edge-component, which in turn,
    is contained in a `k`-core. Thus, this algorithm computes node independent
    paths among pairs of nodes in each biconnected part of each `k`-core,
    and repeats this procedure for each `k` from 3 to the maximal core number
    of a node in the input graph.

    Because, in practice, many nodes of the core of level `k` inside a
    bicomponent actually are part of a component of level k, the auxiliary
    graph needed for the algorithm is likely to be very dense. Thus, we use
    a complement graph data structure (see `AntiGraph`) to save memory.
    AntiGraph only stores information of the edges that are *not* present
    in the actual auxiliary graph. When applying algorithms to this
    complement graph data structure, it behaves as if it were the dense
    version.

    See also
    --------
    k_components

    References
    ----------
    .. [1]  Torrents, J. and F. Ferraro (2015) Structural Cohesion:
            Visualization and Heuristics for Fast Computation.
            https://arxiv.org/pdf/1503.04476v1

    .. [2]  White, Douglas R., and Mark Newman (2001) A Fast Algorithm for
            Node-Independent Paths. Santa Fe Institute Working Paper #01-07-035
            https://www.santafe.edu/research/results/working-papers/fast-approximation-algorithms-for-finding-node-ind

    .. [3]  Moody, J. and D. White (2003). Social cohesion and embeddedness:
            A hierarchical conception of social groups.
            American Sociological Review 68(1), 103--28.
            https://doi.org/10.2307/3088904

    """
    # Dictionary with connectivity level (k) as keys and a list of
    # sets of nodes that form a k-component as values
    k_components = defaultdict(list)
    # make a few functions local for speed
    node_connectivity = local_node_connectivity
    k_core = nx.k_core
    core_number = nx.core_number
    biconnected_components = nx.biconnected_components
    combinations = itertools.combinations
    # Exact solution for k = {1,2}
    # There is a linear time algorithm for triconnectivity, if we had an
    # implementation available we could start from k = 4.
    for component in nx.connected_components(G):
        # isolated nodes have connectivity 0
        comp = set(component)
        if len(comp) > 1:
            k_components[1].append(comp)
    for bicomponent in nx.biconnected_components(G):
        # avoid considering dyads as bicomponents
        bicomp = set(bicomponent)
        if len(bicomp) > 2:
            k_components[2].append(bicomp)
    # There is no k-component of k > maximum core number
    # \kappa(G) <= \lambda(G) <= \delta(G)
    g_cnumber = core_number(G)
    max_core = max(g_cnumber.values())
    for k in range(3, max_core + 1):
        C = k_core(G, k, core_number=g_cnumber)
        for nodes in biconnected_components(C):
            # Build a subgraph SG induced by the nodes that are part of
            # each biconnected component of the k-core subgraph C.
            if len(nodes) < k:
                continue
            SG = G.subgraph(nodes)
            # Build auxiliary graph
            H = _AntiGraph()
            H.add_nodes_from(SG.nodes())
            for u, v in combinations(SG, 2):
                K = node_connectivity(SG, u, v, cutoff=k)
                if k > K:
                    H.add_edge(u, v)
            for h_nodes in biconnected_components(H):
                if len(h_nodes) <= k:
                    continue
                SH = H.subgraph(h_nodes)
                for Gc in _cliques_heuristic(SG, SH, k, min_density):
                    for k_nodes in biconnected_components(Gc):
                        Gk = nx.k_core(SG.subgraph(k_nodes), k)
                        if len(Gk) <= k:
                            continue
                        k_components[k].append(set(Gk))
    return k_components


def _cliques_heuristic(G, H, k, min_density):
    h_cnumber = nx.core_number(H)
    for i, c_value in enumerate(sorted(set(h_cnumber.values()), reverse=True)):
        cands = {n for n, c in h_cnumber.items() if c == c_value}
        # Skip checking for overlap for the highest core value
        if i == 0:
            overlap = False
        else:
            overlap = set.intersection(
                *[{x for x in H[n] if x not in cands} for n in cands]
            )
        if overlap and len(overlap) < k:
            SH = H.subgraph(cands | overlap)
        else:
            SH = H.subgraph(cands)
        sh_cnumber = nx.core_number(SH)
        SG = nx.k_core(G.subgraph(SH), k)
        while not (_same(sh_cnumber) and nx.density(SH) >= min_density):
            # This subgraph must be writable => .copy()
            SH = H.subgraph(SG).copy()
            if len(SH) <= k:
                break
            sh_cnumber = nx.core_number(SH)
            sh_deg = dict(SH.degree())
            min_deg = min(sh_deg.values())
            SH.remove_nodes_from(n for n, d in sh_deg.items() if d == min_deg)
            SG = nx.k_core(G.subgraph(SH), k)
        else:
            yield SG


def _same(measure, tol=0):
    vals = set(measure.values())
    if (max(vals) - min(vals)) <= tol:
        return True
    return False


class _AntiGraph(nx.Graph):
    """
    Class for complement graphs.

    The main goal is to be able to work with big and dense graphs with
    a low memory footprint.

    In this class you add the edges that *do not exist* in the dense graph,
    the report methods of the class return the neighbors, the edges and
    the degree as if it was the dense graph. Thus it's possible to use
    an instance of this class with some of NetworkX functions. In this
    case we only use k-core, connected_components, and biconnected_components.
    """

    all_edge_dict = {"weight": 1}

    def single_edge_dict(self):
        return self.all_edge_dict

    edge_attr_dict_factory = single_edge_dict  # type: ignore[assignment]

    def __getitem__(self, n):
        """Returns a dict of neighbors of node n in the dense graph.

        Parameters
        ----------
        n : node
           A node in the graph.

        Returns
        -------
        adj_dict : dictionary
           The adjacency dictionary for nodes connected to n.

        """
        all_edge_dict = self.all_edge_dict
        return {
            node: all_edge_dict for node in set(self._adj) - set(self._adj[n]) - {n}
        }

    def neighbors(self, n):
        """Returns an iterator over all neighbors of node n in the
        dense graph.
        """
        try:
            return iter(set(self._adj) - set(self._adj[n]) - {n})
        except KeyError as err:
            raise NetworkXError(f"The node {n} is not in the graph.") from err

    class AntiAtlasView(Mapping):
        """An adjacency inner dict for AntiGraph"""

        def __init__(self, graph, node):
            self._graph = graph
            self._atlas = graph._adj[node]
            self._node = node

        def __len__(self):
            return len(self._graph) - len(self._atlas) - 1

        def __iter__(self):
            return (n for n in self._graph if n not in self._atlas and n != self._node)

        def __getitem__(self, nbr):
            nbrs = set(self._graph._adj) - set(self._atlas) - {self._node}
            if nbr in nbrs:
                return self._graph.all_edge_dict
            raise KeyError(nbr)

    class AntiAdjacencyView(AntiAtlasView):
        """An adjacency outer dict for AntiGraph"""

        def __init__(self, graph):
            self._graph = graph
            self._atlas = graph._adj

        def __len__(self):
            return len(self._atlas)

        def __iter__(self):
            return iter(self._graph)

        def __getitem__(self, node):
            if node not in self._graph:
                raise KeyError(node)
            return self._graph.AntiAtlasView(self._graph, node)

    @cached_property
    def adj(self):
        return self.AntiAdjacencyView(self)

    def subgraph(self, nodes):
        """This subgraph method returns a full AntiGraph. Not a View"""
        nodes = set(nodes)
        G = _AntiGraph()
        G.add_nodes_from(nodes)
        for n in G:
            Gnbrs = G.adjlist_inner_dict_factory()
            G._adj[n] = Gnbrs
            for nbr, d in self._adj[n].items():
                if nbr in G._adj:
                    Gnbrs[nbr] = d
                    G._adj[nbr][n] = d
        G.graph = self.graph
        return G

    class AntiDegreeView(nx.reportviews.DegreeView):
        def __iter__(self):
            all_nodes = set(self._succ)
            for n in self._nodes:
                nbrs = all_nodes - set(self._succ[n]) - {n}
                yield (n, len(nbrs))

        def __getitem__(self, n):
            nbrs = set(self._succ) - set(self._succ[n]) - {n}
            # AntiGraph is a ThinGraph so all edges have weight 1
            return len(nbrs) + (n in nbrs)

    @cached_property
    def degree(self):
        """Returns an iterator for (node, degree) and degree for single node.

        The node degree is the number of edges adjacent to the node.

        Parameters
        ----------
        nbunch : iterable container, optional (default=all nodes)
            A container of nodes.  The container will be iterated
            through once.

        weight : string or None, optional (default=None)
           The edge attribute that holds the numerical value used
           as a weight.  If None, then each edge has weight 1.
           The degree is the sum of the edge weights adjacent to the node.

        Returns
        -------
        deg:
            Degree of the node, if a single node is passed as argument.
        nd_iter : an iterator
            The iterator returns two-tuples of (node, degree).

        See Also
        --------
        degree

        Examples
        --------
        >>> G = nx.path_graph(4)
        >>> G.degree(0)  # node 0 with degree 1
        1
        >>> list(G.degree([0, 1]))
        [(0, 1), (1, 2)]

        """
        return self.AntiDegreeView(self)

    def adjacency(self):
        """Returns an iterator of (node, adjacency set) tuples for all nodes
           in the dense graph.

        This is the fastest way to look at every edge.
        For directed graphs, only outgoing adjacencies are included.

        Returns
        -------
        adj_iter : iterator
           An iterator of (node, adjacency set) for all nodes in
           the graph.

        """
        for n in self._adj:
            yield (n, set(self._adj) - set(self._adj[n]) - {n})
