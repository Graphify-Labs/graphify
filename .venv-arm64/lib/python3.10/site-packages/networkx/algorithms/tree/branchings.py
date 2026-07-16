"""
Algorithms for finding optimum branchings and spanning arborescences.

This implementation is based on:

    J. Edmonds, Optimum branchings, J. Res. Natl. Bur. Standards 71B (1967),
    233–240. URL: http://archive.org/details/jresv71Bn4p233

"""

# TODO: Implement method from Gabow, Galil, Spence and Tarjan:
#
# @article{
#    year={1986},
#    issn={0209-9683},
#    journal={Combinatorica},
#    volume={6},
#    number={2},
#    doi={10.1007/BF02579168},
#    title={Efficient algorithms for finding minimum spanning trees in
#        undirected and directed graphs},
#    url={https://doi.org/10.1007/BF02579168},
#    publisher={Springer-Verlag},
#    keywords={68 B 15; 68 C 05},
#    author={Gabow, Harold N. and Galil, Zvi and Spencer, Thomas and Tarjan,
#        Robert E.},
#    pages={109-122},
#    language={English}
# }
import string
from dataclasses import dataclass, field
from operator import itemgetter
from queue import PriorityQueue

import networkx as nx
from networkx.utils import py_random_state

from .recognition import is_arborescence, is_branching

__all__ = [
    "branching_weight",
    "greedy_branching",
    "maximum_branching",
    "minimum_branching",
    "minimal_branching",
    "maximum_spanning_arborescence",
    "minimum_spanning_arborescence",
    "ArborescenceIterator",
]

KINDS = {"max", "min"}

STYLES = {
    "branching": "branching",
    "arborescence": "arborescence",
    "spanning arborescence": "arborescence",
}

INF = float("inf")


@py_random_state(1)
def random_string(L=15, seed=None):
    return "".join([seed.choice(string.ascii_letters) for n in range(L)])


def _min_weight(weight):
    return -weight


def _max_weight(weight):
    return weight


@nx._dispatchable(edge_attrs={"attr": "default"})
def branching_weight(G, attr="weight", default=1):
    """
    Returns the total weight of a branching.

    You must access this function through the networkx.algorithms.tree module.

    Parameters
    ----------
    G : DiGraph
        The directed graph.
    attr : str
        The attribute to use as weights. If None, then each edge will be
        treated equally with a weight of 1.
    default : float
        When `attr` is not None, then if an edge does not have that attribute,
        `default` specifies what value it should take.

    Returns
    -------
    weight: int or float
        The total weight of the branching.

    Examples
    --------
    >>> G = nx.DiGraph()
    >>> G.add_weighted_edges_from([(0, 1, 2), (1, 2, 4), (2, 3, 3), (3, 4, 2)])
    >>> nx.tree.branching_weight(G)
    11

    """
    return sum(edge[2].get(attr, default) for edge in G.edges(data=True))


@py_random_state(4)
@nx._dispatchable(edge_attrs={"attr": "default"}, returns_graph=True)
def greedy_branching(G, attr="weight", default=1, kind="max", seed=None):
    """
    Returns a branching obtained through a greedy algorithm.

    This algorithm is wrong, and cannot give a proper optimal branching.
    However, we include it for pedagogical reasons, as it can be helpful to
    see what its outputs are.

    The output is a branching, and possibly, a spanning arborescence. However,
    it is not guaranteed to be optimal in either case.

    Parameters
    ----------
    G : DiGraph
        The directed graph to scan.
    attr : str
        The attribute to use as weights. If None, then each edge will be
        treated equally with a weight of 1.
    default : float
        When `attr` is not None, then if an edge does not have that attribute,
        `default` specifies what value it should take.
    kind : str
        The type of optimum to search for: 'min' or 'max' greedy branching.
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    B : directed graph
        The greedily obtained branching.

    """
    if kind not in KINDS:
        raise nx.NetworkXException("Unknown value for `kind`.")

    if kind == "min":
        reverse = False
    else:
        reverse = True

    if attr is None:
        # Generate a random string the graph probably won't have.
        attr = random_string(seed=seed)

    edges = [(u, v, data.get(attr, default)) for (u, v, data) in G.edges(data=True)]

    # We sort by weight, but also by nodes to normalize behavior across runs.
    try:
        edges.sort(key=itemgetter(2, 0, 1), reverse=reverse)
    except TypeError:
        # This will fail in Python 3.x if the nodes are of varying types.
        # In that case, we use the arbitrary order.
        edges.sort(key=itemgetter(2), reverse=reverse)

    # The branching begins with a forest of no edges.
    B = nx.DiGraph()
    B.add_nodes_from(G)

    # Now we add edges greedily so long we maintain the branching.
    uf = nx.utils.UnionFind()
    for i, (u, v, w) in enumerate(edges):
        if uf[u] == uf[v]:
            # Adding this edge would form a directed cycle.
            continue
        elif B.in_degree(v) == 1:
            # The edge would increase the degree to be greater than one.
            continue
        else:
            # If attr was None, then don't insert weights...
            data = {}
            if attr is not None:
                data[attr] = w
            B.add_edge(u, v, **data)
            uf.union(u, v)

    return B


@nx._dispatchable(preserve_edge_attrs=True, returns_graph=True)
def maximum_branching(
    G,
    attr="weight",
    default=1,
    preserve_attrs=False,
    partition=None,
):
    #######################################
    ### Data Structure Helper Functions ###
    #######################################

    def edmonds_add_edge(G, edge_index, u, v, key, **d):
        """
        Adds an edge to `G` while also updating the edge index.

        This algorithm requires the use of an external dictionary to track
        the edge keys since it is possible that the source or destination
        node of an edge will be changed and the default key-handling
        capabilities of the MultiDiGraph class do not account for this.

        Parameters
        ----------
        G : MultiDiGraph
            The graph to insert an edge into.
        edge_index : dict
            A mapping from integers to the edges of the graph.
        u : node
            The source node of the new edge.
        v : node
            The destination node of the new edge.
        key : int
            The key to use from `edge_index`.
        d : keyword arguments, optional
            Other attributes to store on the new edge.
        """

        if key in edge_index:
            uu, vv, _ = edge_index[key]
            if (u != uu) or (v != vv):
                raise Exception(f"Key {key!r} is already in use.")

        G.add_edge(u, v, key, **d)
        edge_index[key] = (u, v, G.succ[u][v][key])

    def edmonds_remove_node(G, edge_index, n):
        """
        Remove a node from the graph, updating the edge index to match.

        Parameters
        ----------
        G : MultiDiGraph
            The graph to remove an edge from.
        edge_index : dict
            A mapping from integers to the edges of the graph.
        n : node
            The node to remove from `G`.
        """
        keys = set()
        for keydict in G.pred[n].values():
            keys.update(keydict)
        for keydict in G.succ[n].values():
            keys.update(keydict)

        for key in keys:
            del edge_index[key]

        G.remove_node(n)

    #######################
    ### Algorithm Setup ###
    #######################

    # Pick an attribute name that the original graph is unlikly to have
    candidate_attr = "edmonds' secret candidate attribute"
    new_node_base_name = "edmonds new node base name "

    G_original = G
    G = nx.MultiDiGraph()
    G.__networkx_cache__ = None  # Disable caching

    # A dict to reliably track mutations to the edges using the key of the edge.
    G_edge_index = {}
    # Each edge is given an arbitrary numerical key
    for key, (u, v, data) in enumerate(G_original.edges(data=True)):
        d = {attr: data.get(attr, default)}

        if data.get(partition) is not None:
            d[partition] = data.get(partition)

        if preserve_attrs:
            for d_k, d_v in data.items():
                if d_k != attr:
                    d[d_k] = d_v

        edmonds_add_edge(G, G_edge_index, u, v, key, **d)

    level = 0  # Stores the number of contracted nodes

    # These are the buckets from the paper.
    #
    # In the paper, G^i are modified versions of the original graph.
    # D^i and E^i are the nodes and edges of the maximal edges that are
    # consistent with G^i. In this implementation, D^i and E^i are stored
    # together as the graph B^i. We will have strictly more B^i then the
    # paper will have.
    #
    # Note that the data in graphs and branchings are tuples with the graph as
    # the first element and the edge index as the second.
    B = nx.MultiDiGraph()
    B_edge_index = {}
    graphs = []  # G^i list
    branchings = []  # B^i list
    selected_nodes = set()  # D^i bucket
    uf = nx.utils.UnionFind()

    # A list of lists of edge indices. Each list is a circuit for graph G^i.
    # Note the edge list is not required to be a circuit in G^0.
    circuits = []

    # Stores the index of the minimum edge in the circuit found in G^i and B^i.
    # The ordering of the edges seems to preserver the weight ordering from
    # G^0. So even if the circuit does not form a circuit in G^0, it is still
    # true that the minimum edges in circuit G^0 (despite their weights being
    # different)
    minedge_circuit = []

    ###########################
    ### Algorithm Structure ###
    ###########################

    # Each step listed in the algorithm is an inner function. Thus, the overall
    # loop structure is:
    #
    # while True:
    #     step_I1()
    #     if cycle detected:
    #         step_I2()
    #     elif every node of G is in D and E is a branching:
    #         break

    ##################################
    ### Algorithm Helper Functions ###
    ##################################

    def edmonds_find_desired_edge(v):
        """
        Find the edge directed towards v with maximal weight.

        If an edge partition exists in this graph, return the included
        edge if it exists and never return any excluded edge.

        Note: There can only be one included edge for each vertex otherwise
        the edge partition is empty.

        Parameters
        ----------
        v : node
            The node to search for the maximal weight incoming edge.
        """
        edge = None
        max_weight = -INF
        for u, _, key, data in G.in_edges(v, data=True, keys=True):
            # Skip excluded edges
            if data.get(partition) == nx.EdgePartition.EXCLUDED:
                continue

            new_weight = data[attr]

            # Return the included edge
            if data.get(partition) == nx.EdgePartition.INCLUDED:
                max_weight = new_weight
                edge = (u, v, key, new_weight, data)
                break

            # Find the best open edge
            if new_weight > max_weight:
                max_weight = new_weight
                edge = (u, v, key, new_weight, data)

        return edge, max_weight

    def edmonds_step_I2(v, desired_edge, level):
        """
        Perform step I2 from Edmonds' paper

        First, check if the last step I1 created a cycle. If it did not, do nothing.
        If it did, store the cycle for later reference and contract it.

        Parameters
        ----------
        v : node
            The current node to consider
        desired_edge : edge
            The minimum desired edge to remove from the cycle.
        level : int
            The current level, i.e. the number of cycles that have already been removed.
        """
        u = desired_edge[0]

        Q_nodes = nx.shortest_path(B, v, u)
        Q_edges = [
            list(B[Q_nodes[i]][vv].keys())[0] for i, vv in enumerate(Q_nodes[1:])
        ]
        Q_edges.append(desired_edge[2])  # Add the new edge key to complete the circuit

        # Get the edge in the circuit with the minimum weight.
        # Also, save the incoming weights for each node.
        minweight = INF
        minedge = None
        Q_incoming_weight = {}
        for edge_key in Q_edges:
            u, v, data = B_edge_index[edge_key]
            w = data[attr]
            # We cannot remove an included edge, even if it is the
            # minimum edge in the circuit
            Q_incoming_weight[v] = w
            if data.get(partition) == nx.EdgePartition.INCLUDED:
                continue
            if w < minweight:
                minweight = w
                minedge = edge_key

        circuits.append(Q_edges)
        minedge_circuit.append(minedge)
        graphs.append((G.copy(), G_edge_index.copy()))
        branchings.append((B.copy(), B_edge_index.copy()))

        # Mutate the graph to contract the circuit
        new_node = new_node_base_name + str(level)
        G.add_node(new_node)
        new_edges = []
        for u, v, key, data in G.edges(data=True, keys=True):
            if u in Q_incoming_weight:
                if v in Q_incoming_weight:
                    # Circuit edge. For the moment do nothing,
                    # eventually it will be removed.
                    continue
                else:
                    # Outgoing edge from a node in the circuit.
                    # Make it come from the new node instead
                    dd = data.copy()
                    new_edges.append((new_node, v, key, dd))
            else:
                if v in Q_incoming_weight:
                    # Incoming edge to the circuit.
                    # Update it's weight
                    w = data[attr]
                    w += minweight - Q_incoming_weight[v]
                    dd = data.copy()
                    dd[attr] = w
                    new_edges.append((u, new_node, key, dd))
                else:
                    # Outside edge. No modification needed
                    continue

        for node in Q_nodes:
            edmonds_remove_node(G, G_edge_index, node)
            edmonds_remove_node(B, B_edge_index, node)

        selected_nodes.difference_update(set(Q_nodes))

        for u, v, key, data in new_edges:
            edmonds_add_edge(G, G_edge_index, u, v, key, **data)
            if candidate_attr in data:
                del data[candidate_attr]
                edmonds_add_edge(B, B_edge_index, u, v, key, **data)
                uf.union(u, v)

    def is_root(G, u, edgekeys):
        """
        Returns True if `u` is a root node in G.

        Node `u` is a root node if its in-degree over the specified edges is zero.

        Parameters
        ----------
        G : Graph
            The current graph.
        u : node
            The node in `G` to check if it is a root.
        edgekeys : iterable of edges
            The edges for which to check if `u` is a root of.
        """
        if u not in G:
            raise Exception(f"{u!r} not in G")

        for v in G.pred[u]:
            for edgekey in G.pred[u][v]:
                if edgekey in edgekeys:
                    return False, edgekey
        else:
            return True, None

    nodes = iter(list(G.nodes))
    while True:
        try:
            v = next(nodes)
        except StopIteration:
            # If there are no more new nodes to consider, then we should
            # meet stopping condition (b) from the paper:
            #   (b) every node of G^i is in D^i and E^i is a branching
            assert len(G) == len(B)
            if len(B):
                assert is_branching(B)

            graphs.append((G.copy(), G_edge_index.copy()))
            branchings.append((B.copy(), B_edge_index.copy()))
            circuits.append([])
            minedge_circuit.append(None)

            break
        else:
            #####################
            ### BEGIN STEP I1 ###
            #####################

            # This is a very simple step, so I don't think it needs a method of it's own
            if v in selected_nodes:
                continue

        selected_nodes.add(v)
        B.add_node(v)
        desired_edge, desired_edge_weight = edmonds_find_desired_edge(v)

        # There might be no desired edge if all edges are excluded or
        # v is the last node to be added to B, the ultimate root of the branching
        if desired_edge is not None and desired_edge_weight > 0:
            u = desired_edge[0]
            # Flag adding the edge will create a circuit before merging the two
            # connected components of u and v in B
            circuit = uf[u] == uf[v]
            dd = {attr: desired_edge_weight}
            if desired_edge[4].get(partition) is not None:
                dd[partition] = desired_edge[4].get(partition)

            edmonds_add_edge(B, B_edge_index, u, v, desired_edge[2], **dd)
            G[u][v][desired_edge[2]][candidate_attr] = True
            uf.union(u, v)

            ###################
            ### END STEP I1 ###
            ###################

            #####################
            ### BEGIN STEP I2 ###
            #####################

            if circuit:
                edmonds_step_I2(v, desired_edge, level)
                nodes = iter(list(G.nodes()))
                level += 1

            ###################
            ### END STEP I2 ###
            ###################

    #####################
    ### BEGIN STEP I3 ###
    #####################

    # Create a new graph of the same class as the input graph
    H = G_original.__class__()

    # Start with the branching edges in the last level.
    edges = set(branchings[level][1])
    while level > 0:
        level -= 1

        # The current level is i, and we start counting from 0.
        #
        # We need the node at level i+1 that results from merging a circuit
        # at level i. basename_0 is the first merged node and this happens
        # at level 1. That is basename_0 is a node at level 1 that results
        # from merging a circuit at level 0.

        merged_node = new_node_base_name + str(level)
        circuit = circuits[level]
        isroot, edgekey = is_root(graphs[level + 1][0], merged_node, edges)
        edges.update(circuit)

        if isroot:
            minedge = minedge_circuit[level]
            if minedge is None:
                raise Exception

            # Remove the edge in the cycle with minimum weight
            edges.remove(minedge)
        else:
            # We have identified an edge at the next higher level that
            # transitions into the merged node at this level. That edge
            # transitions to some corresponding node at the current level.
            #
            # We want to remove an edge from the cycle that transitions
            # into the corresponding node, otherwise the result would not
            # be a branching.

            G, G_edge_index = graphs[level]
            target = G_edge_index[edgekey][1]
            for edgekey in circuit:
                u, v, data = G_edge_index[edgekey]
                if v == target:
                    break
            else:
                raise Exception("Couldn't find edge incoming to merged node.")

            edges.remove(edgekey)

    H.add_nodes_from(G_original)
    for edgekey in edges:
        u, v, d = graphs[0][1][edgekey]
        dd = {attr: d[attr]}

        if preserve_attrs:
            for key, value in d.items():
                if key not in [attr, candidate_attr]:
                    dd[key] = value

        H.add_edge(u, v, **dd)

    ###################
    ### END STEP I3 ###
    ###################

    return H


@nx._dispatchable(preserve_edge_attrs=True, mutates_input=True, returns_graph=True)
def minimum_branching(
    G, attr="weight", default=1, preserve_attrs=False, partition=None
):
    for _, _, d in G.edges(data=True):
        d[attr] = -d.get(attr, default)
    nx._clear_cache(G)

    B = maximum_branching(G, attr, default, preserve_attrs, partition)

    for _, _, d in G.edges(data=True):
        d[attr] = -d.get(attr, default)
    nx._clear_cache(G)

    for _, _, d in B.edges(data=True):
        d[attr] = -d.get(attr, default)
    nx._clear_cache(B)

    return B


@nx._dispatchable(preserve_edge_attrs=True, mutates_input=True, returns_graph=True)
def minimal_branching(
    G, /, *, attr="weight", default=1, preserve_attrs=False, partition=None
):
    """
    Returns a minimal branching from `G`.

    A minimal branching is a branching similar to a minimal arborescence but
    without the requirement that the result is actually a spanning arborescence.
    This allows minimal branchinges to be computed over graphs which may not
    have arborescence (such as multiple components).

    Parameters
    ----------
    G : (multi)digraph-like
        The graph to be searched.
    attr : str
        The edge attribute used in determining optimality.
    default : float
        The value of the edge attribute used if an edge does not have
        the attribute `attr`.
    preserve_attrs : bool
        If True, preserve the other attributes of the original graph (that are not
        passed to `attr`)
    partition : str
        The key for the edge attribute containing the partition
        data on the graph. Edges can be included, excluded or open using the
        `EdgePartition` enum.

    Returns
    -------
    B : (multi)digraph-like
        A minimal branching.
    """
    max_weight = -INF
    min_weight = INF
    for _, _, w in G.edges(data=attr, default=default):
        if w > max_weight:
            max_weight = w
        if w < min_weight:
            min_weight = w

    for _, _, d in G.edges(data=True):
        # Transform the weights so that the minimum weight is larger than
        # the difference between the max and min weights. This is important
        # in order to prevent the edge weights from becoming negative during
        # computation
        d[attr] = max_weight + 1 + (max_weight - min_weight) - d.get(attr, default)
    nx._clear_cache(G)

    B = maximum_branching(G, attr, default, preserve_attrs, partition)

    # Reverse the weight transformations
    for _, _, d in G.edges(data=True):
        d[attr] = max_weight + 1 + (max_weight - min_weight) - d.get(attr, default)
    nx._clear_cache(G)

    for _, _, d in B.edges(data=True):
        d[attr] = max_weight + 1 + (max_weight - min_weight) - d.get(attr, default)
    nx._clear_cache(B)

    return B


@nx._dispatchable(preserve_edge_attrs=True, mutates_input=True, returns_graph=True)
def maximum_spanning_arborescence(
    G, attr="weight", default=1, preserve_attrs=False, partition=None
):
    # In order to use the same algorithm is the maximum branching, we need to adjust
    # the weights of the graph. The branching algorithm can choose to not include an
    # edge if it doesn't help find a branching, mainly triggered by edges with negative
    # weights.
    #
    # To prevent this from happening while trying to find a spanning arborescence, we
    # just have to tweak the edge weights so that they are all positive and cannot
    # become negative during the branching algorithm, find the maximum branching and
    # then return them to their original values.

    min_weight = INF
    max_weight = -INF
    for _, _, w in G.edges(data=attr, default=default):
        if w < min_weight:
            min_weight = w
        if w > max_weight:
            max_weight = w

    for _, _, d in G.edges(data=True):
        d[attr] = d.get(attr, default) - min_weight + 1 - (min_weight - max_weight)
    nx._clear_cache(G)

    B = maximum_branching(G, attr, default, preserve_attrs, partition)

    for _, _, d in G.edges(data=True):
        d[attr] = d.get(attr, default) + min_weight - 1 + (min_weight - max_weight)
    nx._clear_cache(G)

    for _, _, d in B.edges(data=True):
        d[attr] = d.get(attr, default) + min_weight - 1 + (min_weight - max_weight)
    nx._clear_cache(B)

    if not is_arborescence(B):
        raise nx.exception.NetworkXException("No maximum spanning arborescence in G.")

    return B


@nx._dispatchable(preserve_edge_attrs=True, mutates_input=True, returns_graph=True)
def minimum_spanning_arborescence(
    G, attr="weight", default=1, preserve_attrs=False, partition=None
):
    B = minimal_branching(
        G,
        attr=attr,
        default=default,
        preserve_attrs=preserve_attrs,
        partition=partition,
    )

    if not is_arborescence(B):
        raise nx.exception.NetworkXException("No minimum spanning arborescence in G.")

    return B


docstring_branching = """
Returns a {kind} {style} from G.

Parameters
----------
G : (multi)digraph-like
    The graph to be searched.
attr : str
    The edge attribute used to in determining optimality.
default : float
    The value of the edge attribute used if an edge does not have
    the attribute `attr`.
preserve_attrs : bool
    If True, preserve the other attributes of the original graph (that are not
    passed to `attr`)
partition : str
    The key for the edge attribute containing the partition
    data on the graph. Edges can be included, excluded or open using the
    `EdgePartition` enum.

Returns
-------
B : (multi)digraph-like
    A {kind} {style}.
"""

docstring_arborescence = (
    docstring_branching
    + """
Raises
------
NetworkXException
    If the graph does not contain a {kind} {style}.

"""
)

maximum_branching.__doc__ = docstring_branching.format(
    kind="maximum", style="branching"
)

minimum_branching.__doc__ = (
    docstring_branching.format(kind="minimum", style="branching")
    + """
See Also
--------
    minimal_branching
"""
)

maximum_spanning_arborescence.__doc__ = docstring_arborescence.format(
    kind="maximum", style="spanning arborescence"
)

minimum_spanning_arborescence.__doc__ = docstring_arborescence.format(
    kind="minimum", style="spanning arborescence"
)


class ArborescenceIterator:
    """
    Iterate over all spanning arborescences of a graph in either increasing or
    decreasing cost.

    Notes
    -----
    This iterator uses the partition scheme from [1]_ (included edges,
    excluded edges and open edges). It generates minimum spanning
    arborescences using a modified Edmonds' Algorithm which respects the
    partition of edges. For arborescences with the same weight, ties are
    broken arbitrarily.

    References
    ----------
    .. [1] G.K. Janssens, K. Sörensen, An algorithm to generate all spanning
           trees in order of increasing cost, Pesquisa Operacional, 2005-08,
           Vol. 25 (2), p. 219-229,
           https://www.scielo.br/j/pope/a/XHswBwRwJyrfL88dmMwYNWp/?lang=en
    """

    @dataclass(order=True)
    class Partition:
        """
        This dataclass represents a partition and stores a dict with the edge
        data and the weight of the minimum spanning arborescence of the
        partition dict.
        """

        mst_weight: float
        partition_dict: dict = field(compare=False)

        def __copy__(self):
            return ArborescenceIterator.Partition(
                self.mst_weight, self.partition_dict.copy()
            )

    def __init__(self, G, weight="weight", minimum=True, init_partition=None):
        """
        Initialize the iterator

        Parameters
        ----------
        G : nx.DiGraph
            The directed graph which we need to iterate trees over

        weight : String, default = "weight"
            The edge attribute used to store the weight of the edge

        minimum : bool, default = True
            Return the trees in increasing order while true and decreasing order
            while false.

        init_partition : tuple, default = None
            In the case that certain edges have to be included or excluded from
            the arborescences, `init_partition` should be in the form
            `(included_edges, excluded_edges)` where each edges is a
            `(u, v)`-tuple inside an iterable such as a list or set.

        """
        self.G = G.copy()
        self.weight = weight
        self.minimum = minimum
        self.method = (
            minimum_spanning_arborescence if minimum else maximum_spanning_arborescence
        )
        # Randomly create a key for an edge attribute to hold the partition data
        self.partition_key = (
            "ArborescenceIterators super secret partition attribute name"
        )
        if init_partition is not None:
            partition_dict = {}
            for e in init_partition[0]:
                partition_dict[e] = nx.EdgePartition.INCLUDED
            for e in init_partition[1]:
                partition_dict[e] = nx.EdgePartition.EXCLUDED
            self.init_partition = ArborescenceIterator.Partition(0, partition_dict)
        else:
            self.init_partition = None

    def __iter__(self):
        """
        Returns
        -------
        ArborescenceIterator
            The iterator object for this graph
        """
        self.partition_queue = PriorityQueue()
        self._clear_partition(self.G)

        # Write the initial partition if it exists.
        if self.init_partition is not None:
            self._write_partition(self.init_partition)

        mst_weight = self.method(
            self.G,
            self.weight,
            partition=self.partition_key,
            preserve_attrs=True,
        ).size(weight=self.weight)

        self.partition_queue.put(
            self.Partition(
                mst_weight if self.minimum else -mst_weight,
                (
                    {}
                    if self.init_partition is None
                    else self.init_partition.partition_dict
                ),
            )
        )

        return self

    def __next__(self):
        """
        Returns
        -------
        (multi)Graph
            The spanning tree of next greatest weight, which ties broken
            arbitrarily.
        """
        if self.partition_queue.empty():
            del self.G, self.partition_queue
            raise StopIteration

        partition = self.partition_queue.get()
        self._write_partition(partition)
        next_arborescence = self.method(
            self.G,
            self.weight,
            partition=self.partition_key,
            preserve_attrs=True,
        )
        self._partition(partition, next_arborescence)

        self._clear_partition(next_arborescence)
        return next_arborescence

    def _partition(self, partition, partition_arborescence):
        """
        Create new partitions based of the minimum spanning tree of the
        current minimum partition.

        Parameters
        ----------
        partition : Partition
            The Partition instance used to generate the current minimum spanning
            tree.
        partition_arborescence : nx.Graph
            The minimum spanning arborescence of the input partition.
        """
        # create two new partitions with the data from the input partition dict
        p1 = self.Partition(0, partition.partition_dict.copy())
        p2 = self.Partition(0, partition.partition_dict.copy())
        for e in partition_arborescence.edges:
            # determine if the edge was open or included
            if e not in partition.partition_dict:
                # This is an open edge
                p1.partition_dict[e] = nx.EdgePartition.EXCLUDED
                p2.partition_dict[e] = nx.EdgePartition.INCLUDED

                self._write_partition(p1)
                try:
                    p1_mst = self.method(
                        self.G,
                        self.weight,
                        partition=self.partition_key,
                        preserve_attrs=True,
                    )

                    p1_mst_weight = p1_mst.size(weight=self.weight)
                    p1.mst_weight = p1_mst_weight if self.minimum else -p1_mst_weight
                    self.partition_queue.put(p1.__copy__())
                except nx.NetworkXException:
                    pass

                p1.partition_dict = p2.partition_dict.copy()

    def _write_partition(self, partition):
        """
        Writes the desired partition into the graph to calculate the minimum
        spanning tree. Also, if one incoming edge is included, mark all others
        as excluded so that if that vertex is merged during Edmonds' algorithm
        we cannot still pick another of that vertex's included edges.

        Parameters
        ----------
        partition : Partition
            A Partition dataclass describing a partition on the edges of the
            graph.
        """
        for u, v, d in self.G.edges(data=True):
            if (u, v) in partition.partition_dict:
                d[self.partition_key] = partition.partition_dict[(u, v)]
            else:
                d[self.partition_key] = nx.EdgePartition.OPEN
        nx._clear_cache(self.G)

        for n in self.G:
            included_count = 0
            excluded_count = 0
            for u, v, d in self.G.in_edges(nbunch=n, data=True):
                if d.get(self.partition_key) == nx.EdgePartition.INCLUDED:
                    included_count += 1
                elif d.get(self.partition_key) == nx.EdgePartition.EXCLUDED:
                    excluded_count += 1
            # Check that if there is an included edges, all other incoming ones
            # are excluded. If not fix it!
            if included_count == 1 and excluded_count != self.G.in_degree(n) - 1:
                for u, v, d in self.G.in_edges(nbunch=n, data=True):
                    if d.get(self.partition_key) != nx.EdgePartition.INCLUDED:
                        d[self.partition_key] = nx.EdgePartition.EXCLUDED

    def _clear_partition(self, G):
        """
        Removes partition data from the graph
        """
        for u, v, d in G.edges(data=True):
            if self.partition_key in d:
                del d[self.partition_key]
        nx._clear_cache(self.G)
