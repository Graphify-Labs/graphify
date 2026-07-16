"""
Ego graph.
"""

__all__ = ["ego_graph"]

import networkx as nx


@nx._dispatchable(preserve_all_attrs=True, returns_graph=True)
def ego_graph(G, n, radius=1, center=True, undirected=False, distance=None):
    """Returns induced subgraph of neighbors centered at node n within
    a given radius.

    Parameters
    ----------
    G : graph
      A NetworkX Graph or DiGraph

    n : node
      A single node

    radius : number, optional
      Include all neighbors of distance<=radius from n.

    center : bool, optional
      If False, do not include center node in graph

    undirected : bool, optional
      If True use both in- and out-neighbors of directed graphs.

    distance : key, optional
      Use specified edge data key as distance.  For example, setting
      distance='weight' will use the edge weight to measure the
      distance from the node n.

    Notes
    -----
    For directed graphs D this produces the "out" neighborhood
    or successors.  If you want the neighborhood of predecessors
    first reverse the graph with D.reverse().  If you want both
    directions use the keyword argument undirected=True.

    Node, edge, and graph attributes are copied to the returned subgraph.
    """
    if undirected:
        if distance is not None:
            sp, _ = nx.single_source_dijkstra(
                G.to_undirected(), n, cutoff=radius, weight=distance
            )
        else:
            sp = dict(
                nx.single_source_shortest_path_length(
                    G.to_undirected(), n, cutoff=radius
                )
            )
    else:
        if distance is not None:
            sp, _ = nx.single_source_dijkstra(G, n, cutoff=radius, weight=distance)
        else:
            sp = dict(nx.single_source_shortest_path_length(G, n, cutoff=radius))

    H = G.subgraph(sp).copy()
    if not center:
        H.remove_node(n)
    return H
