"""
Utilities for connectivity package
"""

import networkx as nx

__all__ = ["build_auxiliary_node_connectivity", "build_auxiliary_edge_connectivity"]


@nx._dispatchable(returns_graph=True)
def build_auxiliary_node_connectivity(G):
    r"""Creates a directed graph D from an undirected graph G to compute flow
    based node connectivity.

    For an undirected graph G having `n` nodes and `m` edges we derive a
    directed graph D with `2n` nodes and `2m+n` arcs by replacing each
    original node `v` with two nodes `vA`, `vB` linked by an (internal)
    arc in D. Then for each edge (`u`, `v`) in G we add two arcs (`uB`, `vA`)
    and (`vB`, `uA`) in D. Finally we set the attribute capacity = 1 for each
    arc in D [1]_.

    For a directed graph having `n` nodes and `m` arcs we derive a
    directed graph D with `2n` nodes and `m+n` arcs by replacing each
    original node `v` with two nodes `vA`, `vB` linked by an (internal)
    arc (`vA`, `vB`) in D. Then for each arc (`u`, `v`) in G we add one
    arc (`uB`, `vA`) in D. Finally we set the attribute capacity = 1 for
    each arc in D.

    A dictionary with a mapping between nodes in the original graph and the
    auxiliary digraph is stored as a graph attribute: D.graph['mapping'].

    References
    ----------
    .. [1] Kammer, Frank and Hanjo Taubig. Graph Connectivity. in Brandes and
        Erlebach, 'Network Analysis: Methodological Foundations', Lecture
        Notes in Computer Science, Volume 3418, Springer-Verlag, 2005.
        https://doi.org/10.1007/978-3-540-31955-9_7

    """
    directed = G.is_directed()

    mapping = {}
    H = nx.DiGraph()

    for i, node in enumerate(G):
        mapping[node] = i
        H.add_node(f"{i}A", id=node)
        H.add_node(f"{i}B", id=node)
        H.add_edge(f"{i}A", f"{i}B", capacity=1)

    edges = []
    for source, target in G.edges():
        edges.append((f"{mapping[source]}B", f"{mapping[target]}A"))
        if not directed:
            edges.append((f"{mapping[target]}B", f"{mapping[source]}A"))
    H.add_edges_from(edges, capacity=1)

    # Store mapping as graph attribute
    H.graph["mapping"] = mapping
    return H


@nx._dispatchable(returns_graph=True)
def build_auxiliary_edge_connectivity(G):
    """Auxiliary digraph for computing flow based edge connectivity

    If the input graph is undirected, we replace each edge (`u`,`v`) with
    two reciprocal arcs (`u`, `v`) and (`v`, `u`) and then we set the attribute
    'capacity' for each arc to 1. If the input graph is directed we simply
    add the 'capacity' attribute. Part of algorithm 1 in [1]_ .

    References
    ----------
    .. [1] Abdol-Hossein Esfahanian. Connectivity Algorithms. (this is a
        chapter, look for the reference of the book).
        http://www.cse.msu.edu/~cse835/Papers/Graph_connectivity_revised.pdf
    """
    if G.is_directed():
        H = nx.DiGraph()
        H.add_nodes_from(G.nodes())
        H.add_edges_from(G.edges(), capacity=1)
        return H
    else:
        H = nx.DiGraph()
        H.add_nodes_from(G.nodes())
        for source, target in G.edges():
            H.add_edges_from([(source, target), (target, source)], capacity=1)
        return H
