"""Functions for computing and verifying regular graphs."""

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = ["is_regular", "is_k_regular", "k_factor"]


@nx._dispatchable
def is_regular(G):
    """Determines whether the graph ``G`` is a regular graph.

    A regular graph is a graph where each vertex has the same degree. A
    regular digraph is a graph where the indegree and outdegree of each
    vertex are equal.

    Parameters
    ----------
    G : NetworkX graph

    Returns
    -------
    bool
        Whether the given graph or digraph is regular.

    Examples
    --------
    >>> G = nx.DiGraph([(1, 2), (2, 3), (3, 4), (4, 1)])
    >>> nx.is_regular(G)
    True

    """
    if len(G) == 0:
        raise nx.NetworkXPointlessConcept("Graph has no nodes.")
    n1 = nx.utils.arbitrary_element(G)
    if not G.is_directed():
        d1 = G.degree(n1)
        return all(d1 == d for _, d in G.degree)
    else:
        d_in = G.in_degree(n1)
        in_regular = all(d_in == d for _, d in G.in_degree)
        d_out = G.out_degree(n1)
        out_regular = all(d_out == d for _, d in G.out_degree)
        return in_regular and out_regular


@not_implemented_for("directed")
@nx._dispatchable
def is_k_regular(G, k):
    """Determines whether the graph ``G`` is a k-regular graph.

    A k-regular graph is a graph where each vertex has degree k.

    Parameters
    ----------
    G : NetworkX graph

    Returns
    -------
    bool
        Whether the given graph is k-regular.

    Examples
    --------
    >>> G = nx.Graph([(1, 2), (2, 3), (3, 4), (4, 1)])
    >>> nx.is_k_regular(G, k=3)
    False

    """
    return all(d == k for n, d in G.degree)


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable(preserve_edge_attrs=True, returns_graph=True)
def k_factor(G, k, matching_weight="weight"):
    """Compute a k-factor of G

    A k-factor of a graph is a spanning k-regular subgraph.
    A spanning k-regular subgraph of G is a subgraph that contains
    each vertex of G and a subset of the edges of G such that each
    vertex has degree k.

    Parameters
    ----------
    G : NetworkX graph
      Undirected graph

    matching_weight: string, optional (default='weight')
       Edge data key corresponding to the edge weight.
       Used for finding the max-weighted perfect matching.
       If key not found, uses 1 as weight.

    Returns
    -------
    G2 : NetworkX graph
        A k-factor of G

    Examples
    --------
    >>> G = nx.Graph([(1, 2), (2, 3), (3, 4), (4, 1)])
    >>> G2 = nx.k_factor(G, k=1)
    >>> G2.edges()
    EdgeView([(1, 2), (3, 4)])

    References
    ----------
    .. [1] "An algorithm for computing simple k-factors.",
       Meijer, Henk, Yurai Núñez-Rodríguez, and David Rappaport,
       Information processing letters, 2009.
    """

    from networkx.algorithms.matching import is_perfect_matching, max_weight_matching

    class LargeKGadget:
        def __init__(self, k, degree, node, g):
            self.original = node
            self.g = g
            self.k = k
            self.degree = degree

            self.outer_vertices = [(node, x) for x in range(degree)]
            self.core_vertices = [(node, x + degree) for x in range(degree - k)]

        def replace_node(self):
            adj_view = self.g[self.original]
            neighbors = list(adj_view.keys())
            edge_attrs = list(adj_view.values())
            for outer, neighbor, edge_attrs in zip(
                self.outer_vertices, neighbors, edge_attrs
            ):
                self.g.add_edge(outer, neighbor, **edge_attrs)
            for core in self.core_vertices:
                for outer in self.outer_vertices:
                    self.g.add_edge(core, outer)
            self.g.remove_node(self.original)

        def restore_node(self):
            self.g.add_node(self.original)
            for outer in self.outer_vertices:
                adj_view = self.g[outer]
                for neighbor, edge_attrs in list(adj_view.items()):
                    if neighbor not in self.core_vertices:
                        self.g.add_edge(self.original, neighbor, **edge_attrs)
                        break
            g.remove_nodes_from(self.outer_vertices)
            g.remove_nodes_from(self.core_vertices)

    class SmallKGadget:
        def __init__(self, k, degree, node, g):
            self.original = node
            self.k = k
            self.degree = degree
            self.g = g

            self.outer_vertices = [(node, x) for x in range(degree)]
            self.inner_vertices = [(node, x + degree) for x in range(degree)]
            self.core_vertices = [(node, x + 2 * degree) for x in range(k)]

        def replace_node(self):
            adj_view = self.g[self.original]
            for outer, inner, (neighbor, edge_attrs) in zip(
                self.outer_vertices, self.inner_vertices, list(adj_view.items())
            ):
                self.g.add_edge(outer, inner)
                self.g.add_edge(outer, neighbor, **edge_attrs)
            for core in self.core_vertices:
                for inner in self.inner_vertices:
                    self.g.add_edge(core, inner)
            self.g.remove_node(self.original)

        def restore_node(self):
            self.g.add_node(self.original)
            for outer in self.outer_vertices:
                adj_view = self.g[outer]
                for neighbor, edge_attrs in adj_view.items():
                    if neighbor not in self.core_vertices:
                        self.g.add_edge(self.original, neighbor, **edge_attrs)
                        break
            self.g.remove_nodes_from(self.outer_vertices)
            self.g.remove_nodes_from(self.inner_vertices)
            self.g.remove_nodes_from(self.core_vertices)

    # Step 1
    if any(d < k for _, d in G.degree):
        raise nx.NetworkXUnfeasible("Graph contains a vertex with degree less than k")
    g = G.copy()

    # Step 2
    gadgets = []
    for node, degree in list(g.degree):
        if k < degree / 2.0:
            gadget = SmallKGadget(k, degree, node, g)
        else:
            gadget = LargeKGadget(k, degree, node, g)
        gadget.replace_node()
        gadgets.append(gadget)

    # Step 3
    matching = max_weight_matching(g, maxcardinality=True, weight=matching_weight)

    # Step 4
    if not is_perfect_matching(g, matching):
        raise nx.NetworkXUnfeasible(
            "Cannot find k-factor because no perfect matching exists"
        )

    for edge in g.edges():
        if edge not in matching and (edge[1], edge[0]) not in matching:
            g.remove_edge(edge[0], edge[1])

    for gadget in gadgets:
        gadget.restore_node()

    return g
