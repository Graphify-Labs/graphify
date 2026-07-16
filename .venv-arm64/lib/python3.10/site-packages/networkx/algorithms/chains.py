"""Functions for finding chains in a graph."""

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = ["chain_decomposition"]


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def chain_decomposition(G, root=None):
    """Returns the chain decomposition of a graph.

    The *chain decomposition* of a graph with respect a depth-first
    search tree is a set of cycles or paths derived from the set of
    fundamental cycles of the tree in the following manner. Consider
    each fundamental cycle with respect to the given tree, represented
    as a list of edges beginning with the nontree edge oriented away
    from the root of the tree. For each fundamental cycle, if it
    overlaps with any previous fundamental cycle, just take the initial
    non-overlapping segment, which is a path instead of a cycle. Each
    cycle or path is called a *chain*. For more information, see [1]_.

    Parameters
    ----------
    G : undirected graph

    root : node (optional)
       A node in the graph `G`. If specified, only the chain
       decomposition for the connected component containing this node
       will be returned. This node indicates the root of the depth-first
       search tree.

    Yields
    ------
    chain : list
       A list of edges representing a chain. There is no guarantee on
       the orientation of the edges in each chain (for example, if a
       chain includes the edge joining nodes 1 and 2, the chain may
       include either (1, 2) or (2, 1)).

    Raises
    ------
    NodeNotFound
       If `root` is not in the graph `G`.

    Examples
    --------
    >>> G = nx.Graph([(0, 1), (1, 4), (3, 4), (3, 5), (4, 5)])
    >>> list(nx.chain_decomposition(G))
    [[(4, 5), (5, 3), (3, 4)]]

    Notes
    -----
    The worst-case running time of this implementation is linear in the
    number of nodes and number of edges [1]_.

    References
    ----------
    .. [1] Jens M. Schmidt (2013). "A simple test on 2-vertex-
       and 2-edge-connectivity." *Information Processing Letters*,
       113, 241–244. Elsevier. <https://doi.org/10.1016/j.ipl.2013.01.016>

    """

    def _dfs_cycle_forest(G, root=None):
        """Builds a directed graph composed of cycles from the given graph.

        `G` is an undirected simple graph. `root` is a node in the graph
        from which the depth-first search is started.

        This function returns both the depth-first search cycle graph
        (as a :class:`~networkx.DiGraph`) and the list of nodes in
        depth-first preorder. The depth-first search cycle graph is a
        directed graph whose edges are the edges of `G` oriented toward
        the root if the edge is a tree edge and away from the root if
        the edge is a non-tree edge. If `root` is not specified, this
        performs a depth-first search on each connected component of `G`
        and returns a directed forest instead.

        If `root` is not in the graph, this raises :exc:`KeyError`.

        """
        # Create a directed graph from the depth-first search tree with
        # root node `root` in which tree edges are directed toward the
        # root and nontree edges are directed away from the root. For
        # each node with an incident nontree edge, this creates a
        # directed cycle starting with the nontree edge and returning to
        # that node.
        #
        # The `parent` node attribute stores the parent of each node in
        # the DFS tree. The `nontree` edge attribute indicates whether
        # the edge is a tree edge or a nontree edge.
        #
        # We also store the order of the nodes found in the depth-first
        # search in the `nodes` list.
        H = nx.DiGraph()
        nodes = []
        for u, v, d in nx.dfs_labeled_edges(G, source=root):
            if d == "forward":
                # `dfs_labeled_edges()` yields (root, root, 'forward')
                # if it is beginning the search on a new connected
                # component.
                if u == v:
                    H.add_node(v, parent=None)
                    nodes.append(v)
                else:
                    H.add_node(v, parent=u)
                    H.add_edge(v, u, nontree=False)
                    nodes.append(v)
            # `dfs_labeled_edges` considers nontree edges in both
            # orientations, so we need to not add the edge if it its
            # other orientation has been added.
            elif d == "nontree" and v not in H[u]:
                H.add_edge(v, u, nontree=True)
            else:
                # Do nothing on 'reverse' edges; we only care about
                # forward and nontree edges.
                pass
        return H, nodes

    def _build_chain(G, u, v, visited):
        """Generate the chain starting from the given nontree edge.

        `G` is a DFS cycle graph as constructed by
        :func:`_dfs_cycle_graph`. The edge (`u`, `v`) is a nontree edge
        that begins a chain. `visited` is a set representing the nodes
        in `G` that have already been visited.

        This function yields the edges in an initial segment of the
        fundamental cycle of `G` starting with the nontree edge (`u`,
        `v`) that includes all the edges up until the first node that
        appears in `visited`. The tree edges are given by the 'parent'
        node attribute. The `visited` set is updated to add each node in
        an edge yielded by this function.

        """
        while v not in visited:
            yield u, v
            visited.add(v)
            u, v = v, G.nodes[v]["parent"]
        yield u, v

    # Check if the root is in the graph G. If not, raise NodeNotFound
    if root is not None and root not in G:
        raise nx.NodeNotFound(f"Root node {root} is not in graph")

    # Create a directed version of H that has the DFS edges directed
    # toward the root and the nontree edges directed away from the root
    # (in each connected component).
    H, nodes = _dfs_cycle_forest(G, root)

    # Visit the nodes again in DFS order. For each node, and for each
    # nontree edge leaving that node, compute the fundamental cycle for
    # that nontree edge starting with that edge. If the fundamental
    # cycle overlaps with any visited nodes, just take the prefix of the
    # cycle up to the point of visited nodes.
    #
    # We repeat this process for each connected component (implicitly,
    # since `nodes` already has a list of the nodes grouped by connected
    # component).
    visited = set()
    for u in nodes:
        visited.add(u)
        # For each nontree edge going out of node u...
        edges = ((u, v) for u, v, d in H.out_edges(u, data="nontree") if d)
        for u, v in edges:
            # Create the cycle or cycle prefix starting with the
            # nontree edge.
            chain = list(_build_chain(H, u, v, visited))
            yield chain
