from collections import defaultdict

import networkx as nx

__all__ = ["check_planarity", "is_planar", "PlanarEmbedding"]


@nx._dispatchable
def is_planar(G):
    """Returns True if and only if `G` is planar.

    A graph is *planar* iff it can be drawn in a plane without
    any edge intersections.

    Parameters
    ----------
    G : NetworkX graph

    Returns
    -------
    bool
       Whether the graph is planar.

    Examples
    --------
    >>> G = nx.Graph([(0, 1), (0, 2)])
    >>> nx.is_planar(G)
    True
    >>> nx.is_planar(nx.complete_graph(5))
    False

    See Also
    --------
    check_planarity :
        Check if graph is planar *and* return a `PlanarEmbedding` instance if True.
    """

    return check_planarity(G, counterexample=False)[0]


@nx._dispatchable(returns_graph=True)
def check_planarity(G, counterexample=False):
    """Check if a graph is planar and return a counterexample or an embedding.

    A graph is planar iff it can be drawn in a plane without
    any edge intersections.

    Parameters
    ----------
    G : NetworkX graph
    counterexample : bool
        A Kuratowski subgraph (to proof non planarity) is only returned if set
        to true.

    Returns
    -------
    (is_planar, certificate) : (bool, NetworkX graph) tuple
        is_planar is true if the graph is planar.
        If the graph is planar `certificate` is a PlanarEmbedding
        otherwise it is a Kuratowski subgraph.

    Examples
    --------
    >>> G = nx.Graph([(0, 1), (0, 2)])
    >>> is_planar, P = nx.check_planarity(G)
    >>> print(is_planar)
    True

    When `G` is planar, a `PlanarEmbedding` instance is returned:

    >>> P.get_data()
    {0: [1, 2], 1: [0], 2: [0]}

    Notes
    -----
    A (combinatorial) embedding consists of cyclic orderings of the incident
    edges at each vertex. Given such an embedding there are multiple approaches
    discussed in literature to drawing the graph (subject to various
    constraints, e.g. integer coordinates), see e.g. [2].

    The planarity check algorithm and extraction of the combinatorial embedding
    is based on the Left-Right Planarity Test [1].

    A counterexample is only generated if the corresponding parameter is set,
    because the complexity of the counterexample generation is higher.

    See also
    --------
    is_planar :
        Check for planarity without creating a `PlanarEmbedding` or counterexample.

    References
    ----------
    .. [1] Ulrik Brandes:
        The Left-Right Planarity Test
        2009
        http://citeseerx.ist.psu.edu/viewdoc/summary?doi=10.1.1.217.9208
    .. [2] Takao Nishizeki, Md Saidur Rahman:
        Planar graph drawing
        Lecture Notes Series on Computing: Volume 12
        2004
    """

    planarity_state = LRPlanarity(G)
    embedding = planarity_state.lr_planarity()
    if embedding is None:
        # graph is not planar
        if counterexample:
            return False, get_counterexample(G)
        else:
            return False, None
    else:
        # graph is planar
        return True, embedding


@nx._dispatchable(returns_graph=True)
def check_planarity_recursive(G, counterexample=False):
    """Recursive version of :meth:`check_planarity`."""
    planarity_state = LRPlanarity(G)
    embedding = planarity_state.lr_planarity_recursive()
    if embedding is None:
        # graph is not planar
        if counterexample:
            return False, get_counterexample_recursive(G)
        else:
            return False, None
    else:
        # graph is planar
        return True, embedding


@nx._dispatchable(returns_graph=True)
def get_counterexample(G):
    """Obtains a Kuratowski subgraph.

    Raises nx.NetworkXException if G is planar.

    The function removes edges such that the graph is still not planar.
    At some point the removal of any edge would make the graph planar.
    This subgraph must be a Kuratowski subgraph.

    Parameters
    ----------
    G : NetworkX graph

    Returns
    -------
    subgraph : NetworkX graph
        A Kuratowski subgraph that proves that G is not planar.

    """
    # copy graph
    G = nx.Graph(G)

    if check_planarity(G)[0]:
        raise nx.NetworkXException("G is planar - no counter example.")

    # find Kuratowski subgraph
    subgraph = nx.Graph()
    for u in G:
        nbrs = list(G[u])
        for v in nbrs:
            G.remove_edge(u, v)
            if check_planarity(G)[0]:
                G.add_edge(u, v)
                subgraph.add_edge(u, v)

    return subgraph


@nx._dispatchable(returns_graph=True)
def get_counterexample_recursive(G):
    """Recursive version of :meth:`get_counterexample`."""

    # copy graph
    G = nx.Graph(G)

    if check_planarity_recursive(G)[0]:
        raise nx.NetworkXException("G is planar - no counter example.")

    # find Kuratowski subgraph
    subgraph = nx.Graph()
    for u in G:
        nbrs = list(G[u])
        for v in nbrs:
            G.remove_edge(u, v)
            if check_planarity_recursive(G)[0]:
                G.add_edge(u, v)
                subgraph.add_edge(u, v)

    return subgraph


class Interval:
    """Represents a set of return edges.

    All return edges in an interval induce a same constraint on the contained
    edges, which means that all edges must either have a left orientation or
    all edges must have a right orientation.
    """

    def __init__(self, low=None, high=None):
        self.low = low
        self.high = high

    def empty(self):
        """Check if the interval is empty"""
        return self.low is None and self.high is None

    def copy(self):
        """Returns a copy of this interval"""
        return Interval(self.low, self.high)

    def conflicting(self, b, planarity_state):
        """Returns True if interval I conflicts with edge b"""
        return (
            not self.empty()
            and planarity_state.lowpt[self.high] > planarity_state.lowpt[b]
        )


class ConflictPair:
    """Represents a different constraint between two intervals.

    The edges in the left interval must have a different orientation than
    the one in the right interval.
    """

    def __init__(self, left=Interval(), right=Interval()):
        self.left = left
        self.right = right

    def swap(self):
        """Swap left and right intervals"""
        temp = self.left
        self.left = self.right
        self.right = temp

    def lowest(self, planarity_state):
        """Returns the lowest lowpoint of a conflict pair"""
        if self.left.empty():
            return planarity_state.lowpt[self.right.low]
        if self.right.empty():
            return planarity_state.lowpt[self.left.low]
        return min(
            planarity_state.lowpt[self.left.low], planarity_state.lowpt[self.right.low]
        )


def top_of_stack(l):
    """Returns the element on top of the stack."""
    if not l:
        return None
    return l[-1]


class LRPlanarity:
    """A class to maintain the state during planarity check."""

    __slots__ = [
        "G",
        "roots",
        "height",
        "lowpt",
        "lowpt2",
        "nesting_depth",
        "parent_edge",
        "DG",
        "adjs",
        "ordered_adjs",
        "ref",
        "side",
        "S",
        "stack_bottom",
        "lowpt_edge",
        "left_ref",
        "right_ref",
        "embedding",
    ]

    def __init__(self, G):
        # copy G without adding self-loops
        self.G = nx.Graph()
        self.G.add_nodes_from(G.nodes)
        for e in G.edges:
            if e[0] != e[1]:
                self.G.add_edge(e[0], e[1])

        self.roots = []

        # distance from tree root
        self.height = defaultdict(lambda: None)

        self.lowpt = {}  # height of lowest return point of an edge
        self.lowpt2 = {}  # height of second lowest return point
        self.nesting_depth = {}  # for nesting order

        # None -> missing edge
        self.parent_edge = defaultdict(lambda: None)

        # oriented DFS graph
        self.DG = nx.DiGraph()
        self.DG.add_nodes_from(G.nodes)

        self.adjs = {}
        self.ordered_adjs = {}

        self.ref = defaultdict(lambda: None)
        self.side = defaultdict(lambda: 1)

        # stack of conflict pairs
        self.S = []
        self.stack_bottom = {}
        self.lowpt_edge = {}

        self.left_ref = {}
        self.right_ref = {}

        self.embedding = PlanarEmbedding()

    def lr_planarity(self):
        """Execute the LR planarity test.

        Returns
        -------
        embedding : dict
            If the graph is planar an embedding is returned. Otherwise None.
        """
        if self.G.order() > 2 and self.G.size() > 3 * self.G.order() - 6:
            # graph is not planar
            return None

        # make adjacency lists for dfs
        for v in self.G:
            self.adjs[v] = list(self.G[v])

        # orientation of the graph by depth first search traversal
        for v in self.G:
            if self.height[v] is None:
                self.height[v] = 0
                self.roots.append(v)
                self.dfs_orientation(v)

        # Free no longer used variables
        self.G = None
        self.lowpt2 = None
        self.adjs = None

        # testing
        for v in self.DG:  # sort the adjacency lists by nesting depth
            # note: this sorting leads to non linear time
            self.ordered_adjs[v] = sorted(
                self.DG[v], key=lambda x: self.nesting_depth[(v, x)]
            )
        for v in self.roots:
            if not self.dfs_testing(v):
                return None

        # Free no longer used variables
        self.height = None
        self.lowpt = None
        self.S = None
        self.stack_bottom = None
        self.lowpt_edge = None

        for e in self.DG.edges:
            self.nesting_depth[e] = self.sign(e) * self.nesting_depth[e]

        self.embedding.add_nodes_from(self.DG.nodes)
        for v in self.DG:
            # sort the adjacency lists again
            self.ordered_adjs[v] = sorted(
                self.DG[v], key=lambda x: self.nesting_depth[(v, x)]
            )
            # initialize the embedding
            previous_node = None
            for w in self.ordered_adjs[v]:
                self.embedding.add_half_edge(v, w, ccw=previous_node)
                previous_node = w

        # Free no longer used variables
        self.DG = None
        self.nesting_depth = None
        self.ref = None

        # compute the complete embedding
        for v in self.roots:
            self.dfs_embedding(v)

        # Free no longer used variables
        self.roots = None
        self.parent_edge = None
        self.ordered_adjs = None
        self.left_ref = None
        self.right_ref = None
        self.side = None

        return self.embedding

    def lr_planarity_recursive(self):
        """Recursive version of :meth:`lr_planarity`."""
        if self.G.order() > 2 and self.G.size() > 3 * self.G.order() - 6:
            # graph is not planar
            return None

        # orientation of the graph by depth first search traversal
        for v in self.G:
            if self.height[v] is None:
                self.height[v] = 0
                self.roots.append(v)
                self.dfs_orientation_recursive(v)

        # Free no longer used variable
        self.G = None

        # testing
        for v in self.DG:  # sort the adjacency lists by nesting depth
            # note: this sorting leads to non linear time
            self.ordered_adjs[v] = sorted(
                self.DG[v], key=lambda x: self.nesting_depth[(v, x)]
            )
        for v in self.roots:
            if not self.dfs_testing_recursive(v):
                return None

        for e in self.DG.edges:
            self.nesting_depth[e] = self.sign_recursive(e) * self.nesting_depth[e]

        self.embedding.add_nodes_from(self.DG.nodes)
        for v in self.DG:
            # sort the adjacency lists again
            self.ordered_adjs[v] = sorted(
                self.DG[v], key=lambda x: self.nesting_depth[(v, x)]
            )
            # initialize the embedding
            previous_node = None
            for w in self.ordered_adjs[v]:
                self.embedding.add_half_edge(v, w, ccw=previous_node)
                previous_node = w

        # compute the complete embedding
        for v in self.roots:
            self.dfs_embedding_recursive(v)

        return self.embedding

    def dfs_orientation(self, v):
        """Orient the graph by DFS, compute lowpoints and nesting order."""
        # the recursion stack
        dfs_stack = [v]
        # index of next edge to handle in adjacency list of each node
        ind = defaultdict(lambda: 0)
        # boolean to indicate whether to skip the initial work for an edge
        skip_init = defaultdict(lambda: False)

        while dfs_stack:
            v = dfs_stack.pop()
            e = self.parent_edge[v]

            for w in self.adjs[v][ind[v] :]:
                vw = (v, w)

                if not skip_init[vw]:
                    if (v, w) in self.DG.edges or (w, v) in self.DG.edges:
                        ind[v] += 1
                        continue  # the edge was already oriented

                    self.DG.add_edge(v, w)  # orient the edge

                    self.lowpt[vw] = self.height[v]
                    self.lowpt2[vw] = self.height[v]
                    if self.height[w] is None:  # (v, w) is a tree edge
                        self.parent_edge[w] = vw
                        self.height[w] = self.height[v] + 1

                        dfs_stack.append(v)  # revisit v after finishing w
                        dfs_stack.append(w)  # visit w next
                        skip_init[vw] = True  # don't redo this block
                        break  # handle next node in dfs_stack (i.e. w)
                    else:  # (v, w) is a back edge
                        self.lowpt[vw] = self.height[w]

                # determine nesting graph
                self.nesting_depth[vw] = 2 * self.lowpt[vw]
                if self.lowpt2[vw] < self.height[v]:  # chordal
                    self.nesting_depth[vw] += 1

                # update lowpoints of parent edge e
                if e is not None:
                    if self.lowpt[vw] < self.lowpt[e]:
                        self.lowpt2[e] = min(self.lowpt[e], self.lowpt2[vw])
                        self.lowpt[e] = self.lowpt[vw]
                    elif self.lowpt[vw] > self.lowpt[e]:
                        self.lowpt2[e] = min(self.lowpt2[e], self.lowpt[vw])
                    else:
                        self.lowpt2[e] = min(self.lowpt2[e], self.lowpt2[vw])

                ind[v] += 1

    def dfs_orientation_recursive(self, v):
        """Recursive version of :meth:`dfs_orientation`."""
        e = self.parent_edge[v]
        for w in self.G[v]:
            if (v, w) in self.DG.edges or (w, v) in self.DG.edges:
                continue  # the edge was already oriented
            vw = (v, w)
            self.DG.add_edge(v, w)  # orient the edge

            self.lowpt[vw] = self.height[v]
            self.lowpt2[vw] = self.height[v]
            if self.height[w] is None:  # (v, w) is a tree edge
                self.parent_edge[w] = vw
                self.height[w] = self.height[v] + 1
                self.dfs_orientation_recursive(w)
            else:  # (v, w) is a back edge
                self.lowpt[vw] = self.height[w]

            # determine nesting graph
            self.nesting_depth[vw] = 2 * self.lowpt[vw]
            if self.lowpt2[vw] < self.height[v]:  # chordal
                self.nesting_depth[vw] += 1

            # update lowpoints of parent edge e
            if e is not None:
                if self.lowpt[vw] < self.lowpt[e]:
                    self.lowpt2[e] = min(self.lowpt[e], self.lowpt2[vw])
                    self.lowpt[e] = self.lowpt[vw]
                elif self.lowpt[vw] > self.lowpt[e]:
                    self.lowpt2[e] = min(self.lowpt2[e], self.lowpt[vw])
                else:
                    self.lowpt2[e] = min(self.lowpt2[e], self.lowpt2[vw])

    def dfs_testing(self, v):
        """Test for LR partition."""
        # the recursion stack
        dfs_stack = [v]
        # index of next edge to handle in adjacency list of each node
        ind = defaultdict(lambda: 0)
        # boolean to indicate whether to skip the initial work for an edge
        skip_init = defaultdict(lambda: False)

        while dfs_stack:
            v = dfs_stack.pop()
            e = self.parent_edge[v]
            # to indicate whether to skip the final block after the for loop
            skip_final = False

            for w in self.ordered_adjs[v][ind[v] :]:
                ei = (v, w)

                if not skip_init[ei]:
                    self.stack_bottom[ei] = top_of_stack(self.S)

                    if ei == self.parent_edge[w]:  # tree edge
                        dfs_stack.append(v)  # revisit v after finishing w
                        dfs_stack.append(w)  # visit w next
                        skip_init[ei] = True  # don't redo this block
                        skip_final = True  # skip final work after breaking
                        break  # handle next node in dfs_stack (i.e. w)
                    else:  # back edge
                        self.lowpt_edge[ei] = ei
                        self.S.append(ConflictPair(right=Interval(ei, ei)))

                # integrate new return edges
                if self.lowpt[ei] < self.height[v]:
                    if w == self.ordered_adjs[v][0]:  # e_i has return edge
                        self.lowpt_edge[e] = self.lowpt_edge[ei]
                    else:  # add constraints of e_i
                        if not self.add_constraints(ei, e):
                            # graph is not planar
                            return False

                ind[v] += 1

            if not skip_final:
                # remove back edges returning to parent
                if e is not None:  # v isn't root
                    self.remove_back_edges(e)

        return True

    def dfs_testing_recursive(self, v):
        """Recursive version of :meth:`dfs_testing`."""
        e = self.parent_edge[v]
        for w in self.ordered_adjs[v]:
            ei = (v, w)
            self.stack_bottom[ei] = top_of_stack(self.S)
            if ei == self.parent_edge[w]:  # tree edge
                if not self.dfs_testing_recursive(w):
                    return False
            else:  # back edge
                self.lowpt_edge[ei] = ei
                self.S.append(ConflictPair(right=Interval(ei, ei)))

            # integrate new return edges
            if self.lowpt[ei] < self.height[v]:
                if w == self.ordered_adjs[v][0]:  # e_i has return edge
                    self.lowpt_edge[e] = self.lowpt_edge[ei]
                else:  # add constraints of e_i
                    if not self.add_constraints(ei, e):
                        # graph is not planar
                        return False

        # remove back edges returning to parent
        if e is not None:  # v isn't root
            self.remove_back_edges(e)
        return True

    def add_constraints(self, ei, e):
        P = ConflictPair()
        # merge return edges of e_i into P.right
        while True:
            Q = self.S.pop()
            if not Q.left.empty():
                Q.swap()
            if not Q.left.empty():  # not planar
                return False
            if self.lowpt[Q.right.low] > self.lowpt[e]:
                # merge intervals
                if P.right.empty():  # topmost interval
                    P.right = Q.right.copy()
                else:
                    self.ref[P.right.low] = Q.right.high
                P.right.low = Q.right.low
            else:  # align
                self.ref[Q.right.low] = self.lowpt_edge[e]
            if top_of_stack(self.S) == self.stack_bottom[ei]:
                break
        # merge conflicting return edges of e_1,...,e_i-1 into P.L
        while top_of_stack(self.S).left.conflicting(ei, self) or top_of_stack(
            self.S
        ).right.conflicting(ei, self):
            Q = self.S.pop()
            if Q.right.conflicting(ei, self):
                Q.swap()
            if Q.right.conflicting(ei, self):  # not planar
                return False
            # merge interval below lowpt(e_i) into P.R
            self.ref[P.right.low] = Q.right.high
            if Q.right.low is not None:
                P.right.low = Q.right.low

            if P.left.empty():  # topmost interval
                P.left = Q.left.copy()
            else:
                self.ref[P.left.low] = Q.left.high
            P.left.low = Q.left.low

        if not (P.left.empty() and P.right.empty()):
            self.S.append(P)
        return True

    def remove_back_edges(self, e):
        u = e[0]
        # trim back edges ending at parent u
        # drop entire conflict pairs
        while self.S and top_of_stack(self.S).lowest(self) == self.height[u]:
            P = self.S.pop()
            if P.left.low is not None:
                self.side[P.left.low] = -1

        if self.S:  # one more conflict pair to consider
            P = self.S.pop()
            # trim left interval
            while P.left.high is not None and P.left.high[1] == u:
                P.left.high = self.ref[P.left.high]
            if P.left.high is None and P.left.low is not None:
                # just emptied
                self.ref[P.left.low] = P.right.low
                self.side[P.left.low] = -1
                P.left.low = None
            # trim right interval
            while P.right.high is not None and P.right.high[1] == u:
                P.right.high = self.ref[P.right.high]
            if P.right.high is None and P.right.low is not None:
                # just emptied
                self.ref[P.right.low] = P.left.low
                self.side[P.right.low] = -1
                P.right.low = None
            self.S.append(P)

        # side of e is side of a highest return edge
        if self.lowpt[e] < self.height[u]:  # e has return edge
            hl = top_of_stack(self.S).left.high
            hr = top_of_stack(self.S).right.high

            if hl is not None and (hr is None or self.lowpt[hl] > self.lowpt[hr]):
                self.ref[e] = hl
            else:
                self.ref[e] = hr

    def dfs_embedding(self, v):
        """Completes the embedding."""
        # the recursion stack
        dfs_stack = [v]
        # index of next edge to handle in adjacency list of each node
        ind = defaultdict(lambda: 0)

        while dfs_stack:
            v = dfs_stack.pop()

            for w in self.ordered_adjs[v][ind[v] :]:
                ind[v] += 1
                ei = (v, w)

                if ei == self.parent_edge[w]:  # tree edge
                    self.embedding.add_half_edge_first(w, v)
                    self.left_ref[v] = w
                    self.right_ref[v] = w

                    dfs_stack.append(v)  # revisit v after finishing w
                    dfs_stack.append(w)  # visit w next
                    break  # handle next node in dfs_stack (i.e. w)
                else:  # back edge
                    if self.side[ei] == 1:
                        self.embedding.add_half_edge(w, v, ccw=self.right_ref[w])
                    else:
                        self.embedding.add_half_edge(w, v, cw=self.left_ref[w])
                        self.left_ref[w] = v

    def dfs_embedding_recursive(self, v):
        """Recursive version of :meth:`dfs_embedding`."""
        for w in self.ordered_adjs[v]:
            ei = (v, w)
            if ei == self.parent_edge[w]:  # tree edge
                self.embedding.add_half_edge_first(w, v)
                self.left_ref[v] = w
                self.right_ref[v] = w
                self.dfs_embedding_recursive(w)
            else:  # back edge
                if self.side[ei] == 1:
                    # place v directly after right_ref[w] in embed. list of w
                    self.embedding.add_half_edge(w, v, ccw=self.right_ref[w])
                else:
                    # place v directly before left_ref[w] in embed. list of w
                    self.embedding.add_half_edge(w, v, cw=self.left_ref[w])
                    self.left_ref[w] = v

    def sign(self, e):
        """Resolve the relative side of an edge to the absolute side."""
        # the recursion stack
        dfs_stack = [e]
        # dict to remember reference edges
        old_ref = defaultdict(lambda: None)

        while dfs_stack:
            e = dfs_stack.pop()

            if self.ref[e] is not None:
                dfs_stack.append(e)  # revisit e after finishing self.ref[e]
                dfs_stack.append(self.ref[e])  # visit self.ref[e] next
                old_ref[e] = self.ref[e]  # remember value of self.ref[e]
                self.ref[e] = None
            else:
                self.side[e] *= self.side[old_ref[e]]

        return self.side[e]

    def sign_recursive(self, e):
        """Recursive version of :meth:`sign`."""
        if self.ref[e] is not None:
            self.side[e] = self.side[e] * self.sign_recursive(self.ref[e])
            self.ref[e] = None
        return self.side[e]


class PlanarEmbedding(nx.DiGraph):
    """Represents a planar graph with its planar embedding.

    The planar embedding is given by a `combinatorial embedding
    <https://en.wikipedia.org/wiki/Graph_embedding#Combinatorial_embedding>`_.

    .. note:: `check_planarity` is the preferred way to check if a graph is planar.

    **Neighbor ordering:**

    In comparison to a usual graph structure, the embedding also stores the
    order of all neighbors for every vertex.
    The order of the neighbors can be given in clockwise (cw) direction or
    counterclockwise (ccw) direction. This order is stored as edge attributes
    in the underlying directed graph. For the edge (u, v) the edge attribute
    'cw' is set to the neighbor of u that follows immediately after v in
    clockwise direction.

    In order for a PlanarEmbedding to be valid it must fulfill multiple
    conditions. It is possible to check if these conditions are fulfilled with
    the method :meth:`check_structure`.
    The conditions are:

    * Edges must go in both directions (because the edge attributes differ)
    * Every edge must have a 'cw' and 'ccw' attribute which corresponds to a
      correct planar embedding.

    As long as a PlanarEmbedding is invalid only the following methods should
    be called:

    * :meth:`add_half_edge`
    * :meth:`connect_components`

    Even though the graph is a subclass of nx.DiGraph, it can still be used
    for algorithms that require undirected graphs, because the method
    :meth:`is_directed` is overridden. This is possible, because a valid
    PlanarGraph must have edges in both directions.

    **Half edges:**

    In methods like `add_half_edge` the term "half-edge" is used, which is
    a term that is used in `doubly connected edge lists
    <https://en.wikipedia.org/wiki/Doubly_connected_edge_list>`_. It is used
    to emphasize that the edge is only in one direction and there exists
    another half-edge in the opposite direction.
    While conventional edges always have two faces (including outer face) next
    to them, it is possible to assign each half-edge *exactly one* face.
    For a half-edge (u, v) that is oriented such that u is below v then the
    face that belongs to (u, v) is to the right of this half-edge.

    See Also
    --------
    is_planar :
        Preferred way to check if an existing graph is planar.

    check_planarity :
        A convenient way to create a `PlanarEmbedding`. If not planar,
        it returns a subgraph that shows this.

    Examples
    --------

    Create an embedding of a star graph (compare `nx.star_graph(3)`):

    >>> G = nx.PlanarEmbedding()
    >>> G.add_half_edge(0, 1)
    >>> G.add_half_edge(0, 2, ccw=1)
    >>> G.add_half_edge(0, 3, ccw=2)
    >>> G.add_half_edge(1, 0)
    >>> G.add_half_edge(2, 0)
    >>> G.add_half_edge(3, 0)

    Alternatively the same embedding can also be defined in counterclockwise
    orientation. The following results in exactly the same PlanarEmbedding:

    >>> G = nx.PlanarEmbedding()
    >>> G.add_half_edge(0, 1)
    >>> G.add_half_edge(0, 3, cw=1)
    >>> G.add_half_edge(0, 2, cw=3)
    >>> G.add_half_edge(1, 0)
    >>> G.add_half_edge(2, 0)
    >>> G.add_half_edge(3, 0)

    After creating a graph, it is possible to validate that the PlanarEmbedding
    object is correct:

    >>> G.check_structure()

    """

    def __init__(self, incoming_graph_data=None, **attr):
        super().__init__(incoming_graph_data=incoming_graph_data, **attr)
        self.add_edge = self.__forbidden
        self.add_edges_from = self.__forbidden
        self.add_weighted_edges_from = self.__forbidden

    def __forbidden(self, *args, **kwargs):
        """Forbidden operation

        Any edge additions to a PlanarEmbedding should be done using
        method `add_half_edge`.
        """
        raise NotImplementedError(
            "Use `add_half_edge` method to add edges to a PlanarEmbedding."
        )

    def get_data(self):
        """Converts the adjacency structure into a better readable structure.

        Returns
        -------
        embedding : dict
            A dict mapping all nodes to a list of neighbors sorted in
            clockwise order.

        See Also
        --------
        set_data

        """
        embedding = {}
        for v in self:
            embedding[v] = list(self.neighbors_cw_order(v))
        return embedding

    def set_data(self, data):
        """Inserts edges according to given sorted neighbor list.

        The input format is the same as the output format of get_data().

        Parameters
        ----------
        data : dict
            A dict mapping all nodes to a list of neighbors sorted in
            clockwise order.

        See Also
        --------
        get_data

        """
        for v in data:
            ref = None
            for w in reversed(data[v]):
                self.add_half_edge(v, w, cw=ref)
                ref = w

    def remove_node(self, n):
        """Remove node n.

        Removes the node n and all adjacent edges, updating the
        PlanarEmbedding to account for any resulting edge removal.
        Attempting to remove a non-existent node will raise an exception.

        Parameters
        ----------
        n : node
           A node in the graph

        Raises
        ------
        NetworkXError
           If n is not in the graph.

        See Also
        --------
        remove_nodes_from

        """
        try:
            for u in self._pred[n]:
                succs_u = self._succ[u]
                un_cw = succs_u[n]["cw"]
                un_ccw = succs_u[n]["ccw"]
                del succs_u[n]
                del self._pred[u][n]
                if n != un_cw:
                    succs_u[un_cw]["ccw"] = un_ccw
                    succs_u[un_ccw]["cw"] = un_cw
            del self._node[n]
            del self._succ[n]
            del self._pred[n]
        except KeyError as err:  # NetworkXError if n not in self
            raise nx.NetworkXError(
                f"The node {n} is not in the planar embedding."
            ) from err
        nx._clear_cache(self)

    def remove_nodes_from(self, nodes):
        """Remove multiple nodes.

        Parameters
        ----------
        nodes : iterable container
            A container of nodes (list, dict, set, etc.).  If a node
            in the container is not in the graph it is silently ignored.

        See Also
        --------
        remove_node

        Notes
        -----
        When removing nodes from an iterator over the graph you are changing,
        a `RuntimeError` will be raised with message:
        `RuntimeError: dictionary changed size during iteration`. This
        happens when the graph's underlying dictionary is modified during
        iteration. To avoid this error, evaluate the iterator into a separate
        object, e.g. by using `list(iterator_of_nodes)`, and pass this
        object to `G.remove_nodes_from`.

        """
        for n in nodes:
            if n in self._node:
                self.remove_node(n)
            # silently skip non-existing nodes

    def neighbors_cw_order(self, v):
        """Generator for the neighbors of v in clockwise order.

        Parameters
        ----------
        v : node

        Yields
        ------
        node

        """
        succs = self._succ[v]
        if not succs:
            # v has no neighbors
            return
        start_node = next(reversed(succs))
        yield start_node
        current_node = succs[start_node]["cw"]
        while start_node != current_node:
            yield current_node
            current_node = succs[current_node]["cw"]

    def add_half_edge(self, start_node, end_node, *, cw=None, ccw=None):
        """Adds a half-edge from `start_node` to `end_node`.

        If the half-edge is not the first one out of `start_node`, a reference
        node must be provided either in the clockwise (parameter `cw`) or in
        the counterclockwise (parameter `ccw`) direction. Only one of `cw`/`ccw`
        can be specified (or neither in the case of the first edge).
        Note that specifying a reference in the clockwise (`cw`) direction means
        inserting the new edge in the first counterclockwise position with
        respect to the reference (and vice-versa).

        Parameters
        ----------
        start_node : node
            Start node of inserted edge.
        end_node : node
            End node of inserted edge.
        cw, ccw: node
            End node of reference edge.
            Omit or pass `None` if adding the first out-half-edge of `start_node`.


        Raises
        ------
        NetworkXException
            If the `cw` or `ccw` node is not a successor of `start_node`.
            If `start_node` has successors, but neither `cw` or `ccw` is provided.
            If both `cw` and `ccw` are specified.

        See Also
        --------
        connect_components
        """

        succs = self._succ.get(start_node)
        if succs:
            # there is already some edge out of start_node
            leftmost_nbr = next(reversed(self._succ[start_node]))
            if cw is not None:
                if cw not in succs:
                    raise nx.NetworkXError("Invalid clockwise reference node.")
                if ccw is not None:
                    raise nx.NetworkXError("Only one of cw/ccw can be specified.")
                ref_ccw = succs[cw]["ccw"]
                super().add_edge(start_node, end_node, cw=cw, ccw=ref_ccw)
                succs[ref_ccw]["cw"] = end_node
                succs[cw]["ccw"] = end_node
                # when (cw == leftmost_nbr), the newly added neighbor is
                # already at the end of dict self._succ[start_node] and
                # takes the place of the former leftmost_nbr
                move_leftmost_nbr_to_end = cw != leftmost_nbr
            elif ccw is not None:
                if ccw not in succs:
                    raise nx.NetworkXError("Invalid counterclockwise reference node.")
                ref_cw = succs[ccw]["cw"]
                super().add_edge(start_node, end_node, cw=ref_cw, ccw=ccw)
                succs[ref_cw]["ccw"] = end_node
                succs[ccw]["cw"] = end_node
                move_leftmost_nbr_to_end = True
            else:
                raise nx.NetworkXError(
                    "Node already has out-half-edge(s), either cw or ccw reference node required."
                )
            if move_leftmost_nbr_to_end:
                # LRPlanarity (via self.add_half_edge_first()) requires that
                # we keep track of the leftmost neighbor, which we accomplish
                # by keeping it as the last key in dict self._succ[start_node]
                succs[leftmost_nbr] = succs.pop(leftmost_nbr)

        else:
            if cw is not None or ccw is not None:
                raise nx.NetworkXError("Invalid reference node.")
            # adding the first edge out of start_node
            super().add_edge(start_node, end_node, ccw=end_node, cw=end_node)

    def check_structure(self):
        """Runs without exceptions if this object is valid.

        Checks that the following properties are fulfilled:

        * Edges go in both directions (because the edge attributes differ).
        * Every edge has a 'cw' and 'ccw' attribute which corresponds to a
          correct planar embedding.

        Running this method verifies that the underlying Graph must be planar.

        Raises
        ------
        NetworkXException
            This exception is raised with a short explanation if the
            PlanarEmbedding is invalid.
        """
        # Check fundamental structure
        for v in self:
            try:
                sorted_nbrs = set(self.neighbors_cw_order(v))
            except KeyError as err:
                msg = f"Bad embedding. Missing orientation for a neighbor of {v}"
                raise nx.NetworkXException(msg) from err

            unsorted_nbrs = set(self[v])
            if sorted_nbrs != unsorted_nbrs:
                msg = "Bad embedding. Edge orientations not set correctly."
                raise nx.NetworkXException(msg)
            for w in self[v]:
                # Check if opposite half-edge exists
                if not self.has_edge(w, v):
                    msg = "Bad embedding. Opposite half-edge is missing."
                    raise nx.NetworkXException(msg)

        # Check planarity
        counted_half_edges = set()
        for component in nx.connected_components(self):
            if len(component) == 1:
                # Don't need to check single node component
                continue
            num_nodes = len(component)
            num_half_edges = 0
            num_faces = 0
            for v in component:
                for w in self.neighbors_cw_order(v):
                    num_half_edges += 1
                    if (v, w) not in counted_half_edges:
                        # We encountered a new face
                        num_faces += 1
                        # Mark all half-edges belonging to this face
                        self.traverse_face(v, w, counted_half_edges)
            num_edges = num_half_edges // 2  # num_half_edges is even
            if num_nodes - num_edges + num_faces != 2:
                # The result does not match Euler's formula
                msg = "Bad embedding. The graph does not match Euler's formula"
                raise nx.NetworkXException(msg)

    def add_half_edge_ccw(self, start_node, end_node, reference_neighbor):
        """Adds a half-edge from start_node to end_node.

        The half-edge is added counter clockwise next to the existing half-edge
        (start_node, reference_neighbor).

        Parameters
        ----------
        start_node : node
            Start node of inserted edge.
        end_node : node
            End node of inserted edge.
        reference_neighbor: node
            End node of reference edge.

        Raises
        ------
        NetworkXException
            If the reference_neighbor does not exist.

        See Also
        --------
        add_half_edge
        add_half_edge_cw
        connect_components

        """
        self.add_half_edge(start_node, end_node, cw=reference_neighbor)

    def add_half_edge_cw(self, start_node, end_node, reference_neighbor):
        """Adds a half-edge from start_node to end_node.

        The half-edge is added clockwise next to the existing half-edge
        (start_node, reference_neighbor).

        Parameters
        ----------
        start_node : node
            Start node of inserted edge.
        end_node : node
            End node of inserted edge.
        reference_neighbor: node
            End node of reference edge.

        Raises
        ------
        NetworkXException
            If the reference_neighbor does not exist.

        See Also
        --------
        add_half_edge
        add_half_edge_ccw
        connect_components
        """
        self.add_half_edge(start_node, end_node, ccw=reference_neighbor)

    def remove_edge(self, u, v):
        """Remove the edge between u and v.

        Parameters
        ----------
        u, v : nodes
        Remove the half-edges (u, v) and (v, u) and update the
        edge ordering around the removed edge.

        Raises
        ------
        NetworkXError
        If there is not an edge between u and v.

        See Also
        --------
        remove_edges_from : remove a collection of edges
        """
        try:
            succs_u = self._succ[u]
            succs_v = self._succ[v]
            uv_cw = succs_u[v]["cw"]
            uv_ccw = succs_u[v]["ccw"]
            vu_cw = succs_v[u]["cw"]
            vu_ccw = succs_v[u]["ccw"]
            del succs_u[v]
            del self._pred[v][u]
            del succs_v[u]
            del self._pred[u][v]
            if v != uv_cw:
                succs_u[uv_cw]["ccw"] = uv_ccw
                succs_u[uv_ccw]["cw"] = uv_cw
            if u != vu_cw:
                succs_v[vu_cw]["ccw"] = vu_ccw
                succs_v[vu_ccw]["cw"] = vu_cw
        except KeyError as err:
            raise nx.NetworkXError(
                f"The edge {u}-{v} is not in the planar embedding."
            ) from err
        nx._clear_cache(self)

    def remove_edges_from(self, ebunch):
        """Remove all edges specified in ebunch.

        Parameters
        ----------
        ebunch: list or container of edge tuples
            Each pair of half-edges between the nodes given in the tuples
            will be removed from the graph. The nodes can be passed as:

                - 2-tuples (u, v) half-edges (u, v) and (v, u).
                - 3-tuples (u, v, k) where k is ignored.

        See Also
        --------
        remove_edge : remove a single edge

        Notes
        -----
        Will fail silently if an edge in ebunch is not in the graph.

        Examples
        --------
        >>> G = nx.path_graph(4)  # or DiGraph, MultiGraph, MultiDiGraph, etc
        >>> ebunch = [(1, 2), (2, 3)]
        >>> G.remove_edges_from(ebunch)
        """
        for e in ebunch:
            u, v = e[:2]  # ignore edge data
            # assuming that the PlanarEmbedding is valid, if the half_edge
            # (u, v) is in the graph, then so is half_edge (v, u)
            if u in self._succ and v in self._succ[u]:
                self.remove_edge(u, v)

    def connect_components(self, v, w):
        """Adds half-edges for (v, w) and (w, v) at some position.

        This method should only be called if v and w are in different
        components, or it might break the embedding.
        This especially means that if `connect_components(v, w)`
        is called it is not allowed to call `connect_components(w, v)`
        afterwards. The neighbor orientations in both directions are
        all set correctly after the first call.

        Parameters
        ----------
        v : node
        w : node

        See Also
        --------
        add_half_edge
        """
        if v in self._succ and self._succ[v]:
            ref = next(reversed(self._succ[v]))
        else:
            ref = None
        self.add_half_edge(v, w, cw=ref)
        if w in self._succ and self._succ[w]:
            ref = next(reversed(self._succ[w]))
        else:
            ref = None
        self.add_half_edge(w, v, cw=ref)

    def add_half_edge_first(self, start_node, end_node):
        """Add a half-edge and set end_node as start_node's leftmost neighbor.

        The new edge is inserted counterclockwise with respect to the current
        leftmost neighbor, if there is one.

        Parameters
        ----------
        start_node : node
        end_node : node

        See Also
        --------
        add_half_edge
        connect_components
        """
        succs = self._succ.get(start_node)
        # the leftmost neighbor is the last entry in the
        # self._succ[start_node] dict
        leftmost_nbr = next(reversed(succs)) if succs else None
        self.add_half_edge(start_node, end_node, cw=leftmost_nbr)

    def next_face_half_edge(self, v, w):
        """Returns the following half-edge left of a face.

        Parameters
        ----------
        v : node
        w : node

        Returns
        -------
        half-edge : tuple
        """
        new_node = self[w][v]["ccw"]
        return w, new_node

    def traverse_face(self, v, w, mark_half_edges=None):
        """Returns nodes on the face that belong to the half-edge (v, w).

        The face that is traversed lies to the right of the half-edge (in an
        orientation where v is below w).

        Optionally it is possible to pass a set to which all encountered half
        edges are added. Before calling this method, this set must not include
        any half-edges that belong to the face.

        Parameters
        ----------
        v : node
            Start node of half-edge.
        w : node
            End node of half-edge.
        mark_half_edges: set, optional
            Set to which all encountered half-edges are added.

        Returns
        -------
        face : list
            A list of nodes that lie on this face.
        """
        if mark_half_edges is None:
            mark_half_edges = set()

        face_nodes = [v]
        mark_half_edges.add((v, w))
        prev_node = v
        cur_node = w
        # Last half-edge is (incoming_node, v)
        incoming_node = self[v][w]["cw"]

        while cur_node != v or prev_node != incoming_node:
            face_nodes.append(cur_node)
            prev_node, cur_node = self.next_face_half_edge(prev_node, cur_node)
            if (prev_node, cur_node) in mark_half_edges:
                raise nx.NetworkXException("Bad planar embedding. Impossible face.")
            mark_half_edges.add((prev_node, cur_node))

        return face_nodes

    def is_directed(self):
        """A valid PlanarEmbedding is undirected.

        All reverse edges are contained, i.e. for every existing
        half-edge (v, w) the half-edge in the opposite direction (w, v) is also
        contained.
        """
        return False

    def copy(self, as_view=False):
        if as_view is True:
            return nx.graphviews.generic_graph_view(self)
        G = self.__class__()
        G.graph.update(self.graph)
        G.add_nodes_from((n, d.copy()) for n, d in self._node.items())
        super(self.__class__, G).add_edges_from(
            (u, v, datadict.copy())
            for u, nbrs in self._adj.items()
            for v, datadict in nbrs.items()
        )
        return G
