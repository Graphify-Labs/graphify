r"""Function for computing a junction tree of a graph."""

from itertools import combinations

import networkx as nx
from networkx.algorithms import chordal_graph_cliques, complete_to_chordal_graph, moral
from networkx.utils import not_implemented_for

__all__ = ["junction_tree"]


@not_implemented_for("multigraph")
@nx._dispatchable(returns_graph=True)
def junction_tree(G):
    r"""Returns a junction tree of a given graph.

    A junction tree (or clique tree) is constructed from a (un)directed graph G.
    The tree is constructed based on a moralized and triangulated version of G.
    The tree's nodes consist of maximal cliques and sepsets of the revised graph.
    The sepset of two cliques is the intersection of the nodes of these cliques,
    e.g. the sepset of (A,B,C) and (A,C,E,F) is (A,C). These nodes are often called
    "variables" in this literature. The tree is bipartite with each sepset
    connected to its two cliques.

    Junction Trees are not unique as the order of clique consideration determines
    which sepsets are included.

    The junction tree algorithm consists of five steps [1]_:

    1. Moralize the graph
    2. Triangulate the graph
    3. Find maximal cliques
    4. Build the tree from cliques, connecting cliques with shared
       nodes, set edge-weight to number of shared variables
    5. Find maximum spanning tree


    Parameters
    ----------
    G : networkx.Graph
        Directed or undirected graph.

    Returns
    -------
    junction_tree : networkx.Graph
        The corresponding junction tree of `G`.

    Raises
    ------
    NetworkXNotImplemented
        Raised if `G` is an instance of `MultiGraph` or `MultiDiGraph`.

    References
    ----------
    .. [1] Junction tree algorithm:
       https://en.wikipedia.org/wiki/Junction_tree_algorithm

    .. [2] Finn V. Jensen and Frank Jensen. 1994. Optimal
       junction trees. In Proceedings of the Tenth international
       conference on Uncertainty in artificial intelligence (UAI’94).
       Morgan Kaufmann Publishers Inc., San Francisco, CA, USA, 360–366.
    """

    clique_graph = nx.Graph()

    if G.is_directed():
        G = moral.moral_graph(G)
    chordal_graph, _ = complete_to_chordal_graph(G)

    cliques = [tuple(sorted(i)) for i in chordal_graph_cliques(chordal_graph)]
    clique_graph.add_nodes_from(cliques, type="clique")

    for edge in combinations(cliques, 2):
        set_edge_0 = set(edge[0])
        set_edge_1 = set(edge[1])
        if not set_edge_0.isdisjoint(set_edge_1):
            sepset = tuple(sorted(set_edge_0.intersection(set_edge_1)))
            clique_graph.add_edge(edge[0], edge[1], weight=len(sepset), sepset=sepset)

    junction_tree = nx.maximum_spanning_tree(clique_graph)

    for edge in list(junction_tree.edges(data=True)):
        junction_tree.add_node(edge[2]["sepset"], type="sepset")
        junction_tree.add_edge(edge[0], edge[2]["sepset"])
        junction_tree.add_edge(edge[1], edge[2]["sepset"])
        junction_tree.remove_edge(edge[0], edge[1])

    return junction_tree
