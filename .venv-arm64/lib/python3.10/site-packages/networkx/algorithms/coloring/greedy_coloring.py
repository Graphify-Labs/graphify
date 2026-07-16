"""
Greedy graph coloring using various strategies.
"""

import itertools
from collections import defaultdict, deque

import networkx as nx
from networkx.utils import arbitrary_element, py_random_state

__all__ = [
    "greedy_color",
    "strategy_connected_sequential",
    "strategy_connected_sequential_bfs",
    "strategy_connected_sequential_dfs",
    "strategy_independent_set",
    "strategy_largest_first",
    "strategy_random_sequential",
    "strategy_saturation_largest_first",
    "strategy_smallest_last",
]


def strategy_largest_first(G, colors):
    """Returns a list of the nodes of ``G`` in decreasing order by
    degree.

    ``G`` is a NetworkX graph. ``colors`` is ignored.

    """
    return sorted(G, key=G.degree, reverse=True)


@py_random_state(2)
def strategy_random_sequential(G, colors, seed=None):
    """Returns a random permutation of the nodes of ``G`` as a list.

    ``G`` is a NetworkX graph. ``colors`` is ignored.

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.
    """
    nodes = list(G)
    seed.shuffle(nodes)
    return nodes


def strategy_smallest_last(G, colors):
    """Returns a deque of the nodes of ``G``, "smallest" last.

    Specifically, the degrees of each node are tracked in a bucket queue.
    From this, the node of minimum degree is repeatedly popped from the
    graph, updating its neighbors' degrees.

    ``G`` is a NetworkX graph. ``colors`` is ignored.

    This implementation of the strategy runs in $O(n + m)$ time
    (ignoring polylogarithmic factors), where $n$ is the number of nodes
    and $m$ is the number of edges.

    This strategy is related to :func:`strategy_independent_set`: if we
    interpret each node removed as an independent set of size one, then
    this strategy chooses an independent set of size one instead of a
    maximal independent set.

    """
    H = G.copy()
    result = deque()

    # Build initial degree list (i.e. the bucket queue data structure)
    degrees = defaultdict(set)  # set(), for fast random-access removals
    lbound = float("inf")
    for node, d in H.degree():
        degrees[d].add(node)
        lbound = min(lbound, d)  # Lower bound on min-degree.

    def find_min_degree():
        # Save time by starting the iterator at `lbound`, not 0.
        # The value that we find will be our new `lbound`, which we set later.
        return next(d for d in itertools.count(lbound) if d in degrees)

    for _ in G:
        # Pop a min-degree node and add it to the list.
        min_degree = find_min_degree()
        u = degrees[min_degree].pop()
        if not degrees[min_degree]:  # Clean up the degree list.
            del degrees[min_degree]
        result.appendleft(u)

        # Update degrees of removed node's neighbors.
        for v in H[u]:
            degree = H.degree(v)
            degrees[degree].remove(v)
            if not degrees[degree]:  # Clean up the degree list.
                del degrees[degree]
            degrees[degree - 1].add(v)

        # Finally, remove the node.
        H.remove_node(u)
        lbound = min_degree - 1  # Subtract 1 in case of tied neighbors.

    return result


def _maximal_independent_set(G):
    """Returns a maximal independent set of nodes in ``G`` by repeatedly
    choosing an independent node of minimum degree (with respect to the
    subgraph of unchosen nodes).

    """
    result = set()
    remaining = set(G)
    while remaining:
        G = G.subgraph(remaining)
        v = min(remaining, key=G.degree)
        result.add(v)
        remaining -= set(G[v]) | {v}
    return result


def strategy_independent_set(G, colors):
    """Uses a greedy independent set removal strategy to determine the
    colors.

    This function updates ``colors`` **in-place** and return ``None``,
    unlike the other strategy functions in this module.

    This algorithm repeatedly finds and removes a maximal independent
    set, assigning each node in the set an unused color.

    ``G`` is a NetworkX graph.

    This strategy is related to :func:`strategy_smallest_last`: in that
    strategy, an independent set of size one is chosen at each step
    instead of a maximal independent set.

    """
    remaining_nodes = set(G)
    while len(remaining_nodes) > 0:
        nodes = _maximal_independent_set(G.subgraph(remaining_nodes))
        remaining_nodes -= nodes
        yield from nodes


def strategy_connected_sequential_bfs(G, colors):
    """Returns an iterable over nodes in ``G`` in the order given by a
    breadth-first traversal.

    The generated sequence has the property that for each node except
    the first, at least one neighbor appeared earlier in the sequence.

    ``G`` is a NetworkX graph. ``colors`` is ignored.

    """
    return strategy_connected_sequential(G, colors, "bfs")


def strategy_connected_sequential_dfs(G, colors):
    """Returns an iterable over nodes in ``G`` in the order given by a
    depth-first traversal.

    The generated sequence has the property that for each node except
    the first, at least one neighbor appeared earlier in the sequence.

    ``G`` is a NetworkX graph. ``colors`` is ignored.

    """
    return strategy_connected_sequential(G, colors, "dfs")


def strategy_connected_sequential(G, colors, traversal="bfs"):
    """Returns an iterable over nodes in ``G`` in the order given by a
    breadth-first or depth-first traversal.

    ``traversal`` must be one of the strings ``'dfs'`` or ``'bfs'``,
    representing depth-first traversal or breadth-first traversal,
    respectively.

    The generated sequence has the property that for each node except
    the first, at least one neighbor appeared earlier in the sequence.

    ``G`` is a NetworkX graph. ``colors`` is ignored.

    """
    if traversal == "bfs":
        traverse = nx.bfs_edges
    elif traversal == "dfs":
        traverse = nx.dfs_edges
    else:
        raise nx.NetworkXError(
            "Please specify one of the strings 'bfs' or"
            " 'dfs' for connected sequential ordering"
        )
    for component in nx.connected_components(G):
        source = arbitrary_element(component)
        # Yield the source node, then all the nodes in the specified
        # traversal order.
        yield source
        for _, end in traverse(G.subgraph(component), source):
            yield end


def strategy_saturation_largest_first(G, colors):
    """Iterates over all the nodes of ``G`` in "saturation order" (also
    known as "DSATUR").

    ``G`` is a NetworkX graph. ``colors`` is a dictionary mapping nodes of
    ``G`` to colors, for those nodes that have already been colored.

    """
    distinct_colors = {v: set() for v in G}

    # Add the node color assignments given in colors to the
    # distinct colors set for each neighbor of that node
    for node, color in colors.items():
        for neighbor in G[node]:
            distinct_colors[neighbor].add(color)

    # Check that the color assignments in colors are valid
    # i.e. no neighboring nodes have the same color
    if len(colors) >= 2:
        for node, color in colors.items():
            if color in distinct_colors[node]:
                raise nx.NetworkXError("Neighboring nodes must have different colors")

    # If 0 nodes have been colored, simply choose the node of highest degree.
    if not colors:
        node = max(G, key=G.degree)
        yield node
        # Add the color 0 to the distinct colors set for each
        # neighbor of that node.
        for v in G[node]:
            distinct_colors[v].add(0)

    while len(G) != len(colors):
        # Update the distinct color sets for the neighbors.
        for node, color in colors.items():
            for neighbor in G[node]:
                distinct_colors[neighbor].add(color)

        # Compute the maximum saturation and the set of nodes that
        # achieve that saturation.
        saturation = {v: len(c) for v, c in distinct_colors.items() if v not in colors}
        # Yield the node with the highest saturation, and break ties by
        # degree.
        node = max(saturation, key=lambda v: (saturation[v], G.degree(v)))
        yield node


#: Dictionary mapping name of a strategy as a string to the strategy function.
STRATEGIES = {
    "largest_first": strategy_largest_first,
    "random_sequential": strategy_random_sequential,
    "smallest_last": strategy_smallest_last,
    "independent_set": strategy_independent_set,
    "connected_sequential_bfs": strategy_connected_sequential_bfs,
    "connected_sequential_dfs": strategy_connected_sequential_dfs,
    "connected_sequential": strategy_connected_sequential,
    "saturation_largest_first": strategy_saturation_largest_first,
    "DSATUR": strategy_saturation_largest_first,
}


@nx._dispatchable
def greedy_color(G, strategy="largest_first", interchange=False):
    """Color a graph using various strategies of greedy graph coloring.

    Attempts to color a graph using as few colors as possible, where no
    neighbors of a node can have same color as the node itself. The
    given strategy determines the order in which nodes are colored.

    The strategies are described in [1]_, and smallest-last is based on
    [2]_.

    Parameters
    ----------
    G : NetworkX graph

    strategy : string or function(G, colors)
       A function (or a string representing a function) that provides
       the coloring strategy, by returning nodes in the ordering they
       should be colored. ``G`` is the graph, and ``colors`` is a
       dictionary of the currently assigned colors, keyed by nodes. The
       function must return an iterable over all the nodes in ``G``.

       If the strategy function is an iterator generator (that is, a
       function with ``yield`` statements), keep in mind that the
       ``colors`` dictionary will be updated after each ``yield``, since
       this function chooses colors greedily.

       If ``strategy`` is a string, it must be one of the following,
       each of which represents one of the built-in strategy functions.

       * ``'largest_first'``
       * ``'random_sequential'``
       * ``'smallest_last'``
       * ``'independent_set'``
       * ``'connected_sequential_bfs'``
       * ``'connected_sequential_dfs'``
       * ``'connected_sequential'`` (alias for the previous strategy)
       * ``'saturation_largest_first'``
       * ``'DSATUR'`` (alias for the previous strategy)

    interchange: bool
       Will use the color interchange algorithm described by [3]_ if set
       to ``True``.

       Note that ``saturation_largest_first`` and ``independent_set``
       do not work with interchange. Furthermore, if you use
       interchange with your own strategy function, you cannot rely
       on the values in the ``colors`` argument.

    Returns
    -------
    A dictionary with keys representing nodes and values representing
    corresponding coloring.

    Examples
    --------
    >>> G = nx.cycle_graph(4)
    >>> d = nx.coloring.greedy_color(G, strategy="largest_first")
    >>> d in [{0: 0, 1: 1, 2: 0, 3: 1}, {0: 1, 1: 0, 2: 1, 3: 0}]
    True

    Raises
    ------
    NetworkXPointlessConcept
        If ``strategy`` is ``saturation_largest_first`` or
        ``independent_set`` and ``interchange`` is ``True``.

    References
    ----------
    .. [1] Adrian Kosowski, and Krzysztof Manuszewski,
       Classical Coloring of Graphs, Graph Colorings, 2-19, 2004.
       ISBN 0-8218-3458-4.
    .. [2] David W. Matula, and Leland L. Beck, "Smallest-last
       ordering and clustering and graph coloring algorithms." *J. ACM* 30,
       3 (July 1983), 417–427. <https://doi.org/10.1145/2402.322385>
    .. [3] Maciej M. Sysło, Narsingh Deo, Janusz S. Kowalik,
       Discrete Optimization Algorithms with Pascal Programs, 415-424, 1983.
       ISBN 0-486-45353-7.

    """
    if len(G) == 0:
        return {}
    # Determine the strategy provided by the caller.
    strategy = STRATEGIES.get(strategy, strategy)
    if not callable(strategy):
        raise nx.NetworkXError(
            f"strategy must be callable or a valid string. {strategy} not valid."
        )
    # Perform some validation on the arguments before executing any
    # strategy functions.
    if interchange:
        if strategy is strategy_independent_set:
            msg = "interchange cannot be used with independent_set"
            raise nx.NetworkXPointlessConcept(msg)
        if strategy is strategy_saturation_largest_first:
            msg = "interchange cannot be used with" " saturation_largest_first"
            raise nx.NetworkXPointlessConcept(msg)
    colors = {}
    nodes = strategy(G, colors)
    if interchange:
        return _greedy_coloring_with_interchange(G, nodes)
    for u in nodes:
        # Set to keep track of colors of neighbors
        nbr_colors = {colors[v] for v in G[u] if v in colors}
        # Find the first unused color.
        for color in itertools.count():
            if color not in nbr_colors:
                break
        # Assign the new color to the current node.
        colors[u] = color
    return colors


# Tools for coloring with interchanges
class _Node:
    __slots__ = ["node_id", "color", "adj_list", "adj_color"]

    def __init__(self, node_id, n):
        self.node_id = node_id
        self.color = -1
        self.adj_list = None
        self.adj_color = [None for _ in range(n)]

    def __repr__(self):
        return (
            f"Node_id: {self.node_id}, Color: {self.color}, "
            f"Adj_list: ({self.adj_list}), adj_color: ({self.adj_color})"
        )

    def assign_color(self, adj_entry, color):
        adj_entry.col_prev = None
        adj_entry.col_next = self.adj_color[color]
        self.adj_color[color] = adj_entry
        if adj_entry.col_next is not None:
            adj_entry.col_next.col_prev = adj_entry

    def clear_color(self, adj_entry, color):
        if adj_entry.col_prev is None:
            self.adj_color[color] = adj_entry.col_next
        else:
            adj_entry.col_prev.col_next = adj_entry.col_next
        if adj_entry.col_next is not None:
            adj_entry.col_next.col_prev = adj_entry.col_prev

    def iter_neighbors(self):
        adj_node = self.adj_list
        while adj_node is not None:
            yield adj_node
            adj_node = adj_node.next

    def iter_neighbors_color(self, color):
        adj_color_node = self.adj_color[color]
        while adj_color_node is not None:
            yield adj_color_node.node_id
            adj_color_node = adj_color_node.col_next


class _AdjEntry:
    __slots__ = ["node_id", "next", "mate", "col_next", "col_prev"]

    def __init__(self, node_id):
        self.node_id = node_id
        self.next = None
        self.mate = None
        self.col_next = None
        self.col_prev = None

    def __repr__(self):
        col_next = None if self.col_next is None else self.col_next.node_id
        col_prev = None if self.col_prev is None else self.col_prev.node_id
        return (
            f"Node_id: {self.node_id}, Next: ({self.next}), "
            f"Mate: ({self.mate.node_id}), "
            f"col_next: ({col_next}), col_prev: ({col_prev})"
        )


def _greedy_coloring_with_interchange(G, nodes):
    """Return a coloring for `original_graph` using interchange approach

    This procedure is an adaption of the algorithm described by [1]_,
    and is an implementation of coloring with interchange. Please be
    advised, that the datastructures used are rather complex because
    they are optimized to minimize the time spent identifying
    subcomponents of the graph, which are possible candidates for color
    interchange.

    Parameters
    ----------
    G : NetworkX graph
        The graph to be colored

    nodes : list
        nodes ordered using the strategy of choice

    Returns
    -------
    dict :
        A dictionary keyed by node to a color value

    References
    ----------
    .. [1] Maciej M. Syslo, Narsingh Deo, Janusz S. Kowalik,
       Discrete Optimization Algorithms with Pascal Programs, 415-424, 1983.
       ISBN 0-486-45353-7.
    """
    n = len(G)

    graph = {node: _Node(node, n) for node in G}

    for node1, node2 in G.edges():
        adj_entry1 = _AdjEntry(node2)
        adj_entry2 = _AdjEntry(node1)
        adj_entry1.mate = adj_entry2
        adj_entry2.mate = adj_entry1
        node1_head = graph[node1].adj_list
        adj_entry1.next = node1_head
        graph[node1].adj_list = adj_entry1
        node2_head = graph[node2].adj_list
        adj_entry2.next = node2_head
        graph[node2].adj_list = adj_entry2

    k = 0
    for node in nodes:
        # Find the smallest possible, unused color
        neighbors = graph[node].iter_neighbors()
        col_used = {graph[adj_node.node_id].color for adj_node in neighbors}
        col_used.discard(-1)
        k1 = next(itertools.dropwhile(lambda x: x in col_used, itertools.count()))

        # k1 is now the lowest available color
        if k1 > k:
            connected = True
            visited = set()
            col1 = -1
            col2 = -1
            while connected and col1 < k:
                col1 += 1
                neighbor_cols = graph[node].iter_neighbors_color(col1)
                col1_adj = list(neighbor_cols)

                col2 = col1
                while connected and col2 < k:
                    col2 += 1
                    visited = set(col1_adj)
                    frontier = list(col1_adj)
                    i = 0
                    while i < len(frontier):
                        search_node = frontier[i]
                        i += 1
                        col_opp = col2 if graph[search_node].color == col1 else col1
                        neighbor_cols = graph[search_node].iter_neighbors_color(col_opp)

                        for neighbor in neighbor_cols:
                            if neighbor not in visited:
                                visited.add(neighbor)
                                frontier.append(neighbor)

                    # Search if node is not adj to any col2 vertex
                    connected = (
                        len(
                            visited.intersection(graph[node].iter_neighbors_color(col2))
                        )
                        > 0
                    )

            # If connected is false then we can swap !!!
            if not connected:
                # Update all the nodes in the component
                for search_node in visited:
                    graph[search_node].color = (
                        col2 if graph[search_node].color == col1 else col1
                    )
                    col2_adj = graph[search_node].adj_color[col2]
                    graph[search_node].adj_color[col2] = graph[search_node].adj_color[
                        col1
                    ]
                    graph[search_node].adj_color[col1] = col2_adj

                # Update all the neighboring nodes
                for search_node in visited:
                    col = graph[search_node].color
                    col_opp = col1 if col == col2 else col2
                    for adj_node in graph[search_node].iter_neighbors():
                        if graph[adj_node.node_id].color != col_opp:
                            # Direct reference to entry
                            adj_mate = adj_node.mate
                            graph[adj_node.node_id].clear_color(adj_mate, col_opp)
                            graph[adj_node.node_id].assign_color(adj_mate, col)
                k1 = col1

        # We can color this node color k1
        graph[node].color = k1
        k = max(k1, k)

        # Update the neighbors of this node
        for adj_node in graph[node].iter_neighbors():
            adj_mate = adj_node.mate
            graph[adj_node.node_id].assign_color(adj_mate, k1)

    return {node.node_id: node.color for node in graph.values()}
