"""
Graph summarization finds smaller representations of graphs resulting in faster
runtime of algorithms, reduced storage needs, and noise reduction.
Summarization has applications in areas such as visualization, pattern mining,
clustering and community detection, and more.  Core graph summarization
techniques are grouping/aggregation, bit-compression,
simplification/sparsification, and influence based. Graph summarization
algorithms often produce either summary graphs in the form of supergraphs or
sparsified graphs, or a list of independent structures. Supergraphs are the
most common product, which consist of supernodes and original nodes and are
connected by edges and superedges, which represent aggregate edges between
nodes and supernodes.

Grouping/aggregation based techniques compress graphs by representing
close/connected nodes and edges in a graph by a single node/edge in a
supergraph. Nodes can be grouped together into supernodes based on their
structural similarities or proximity within a graph to reduce the total number
of nodes in a graph. Edge-grouping techniques group edges into lossy/lossless
nodes called compressor or virtual nodes to reduce the total number of edges in
a graph. Edge-grouping techniques can be lossless, meaning that they can be
used to re-create the original graph, or techniques can be lossy, requiring
less space to store the summary graph, but at the expense of lower
reconstruction accuracy of the original graph.

Bit-compression techniques minimize the amount of information needed to
describe the original graph, while revealing structural patterns in the
original graph.  The two-part minimum description length (MDL) is often used to
represent the model and the original graph in terms of the model.  A key
difference between graph compression and graph summarization is that graph
summarization focuses on finding structural patterns within the original graph,
whereas graph compression focuses on compressions the original graph to be as
small as possible.  **NOTE**: Some bit-compression methods exist solely to
compress a graph without creating a summary graph or finding comprehensible
structural patterns.

Simplification/Sparsification techniques attempt to create a sparse
representation of a graph by removing unimportant nodes and edges from the
graph.  Sparsified graphs differ from supergraphs created by
grouping/aggregation by only containing a subset of the original nodes and
edges of the original graph.

Influence based techniques aim to find a high-level description of influence
propagation in a large graph.  These methods are scarce and have been mostly
applied to social graphs.

*dedensification* is a grouping/aggregation based technique to compress the
neighborhoods around high-degree nodes in unweighted graphs by adding
compressor nodes that summarize multiple edges of the same type to
high-degree nodes (nodes with a degree greater than a given threshold).
Dedensification was developed for the purpose of increasing performance of
query processing around high-degree nodes in graph databases and enables direct
operations on the compressed graph.  The structural patterns surrounding
high-degree nodes in the original is preserved while using fewer edges and
adding a small number of compressor nodes.  The degree of nodes present in the
original graph is also preserved. The current implementation of dedensification
supports graphs with one edge type.

For more information on graph summarization, see `Graph Summarization Methods
and Applications: A Survey <https://dl.acm.org/doi/abs/10.1145/3186727>`_
"""

from collections import Counter, defaultdict

import networkx as nx

__all__ = ["dedensify", "snap_aggregation"]


@nx._dispatchable(mutates_input={"not copy": 3}, returns_graph=True)
def dedensify(G, threshold, prefix=None, copy=True):
    """Compresses neighborhoods around high-degree nodes

    Reduces the number of edges to high-degree nodes by adding compressor nodes
    that summarize multiple edges of the same type to high-degree nodes (nodes
    with a degree greater than a given threshold).  Dedensification also has
    the added benefit of reducing the number of edges around high-degree nodes.
    The implementation currently supports graphs with a single edge type.

    Parameters
    ----------
    G: graph
       A networkx graph
    threshold: int
       Minimum degree threshold of a node to be considered a high degree node.
       The threshold must be greater than or equal to 2.
    prefix: str or None, optional (default: None)
       An optional prefix for denoting compressor nodes
    copy: bool, optional (default: True)
       Indicates if dedensification should be done inplace

    Returns
    -------
    dedensified networkx graph : (graph, set)
        2-tuple of the dedensified graph and set of compressor nodes

    Notes
    -----
    According to the algorithm in [1]_, removes edges in a graph by
    compressing/decompressing the neighborhoods around high degree nodes by
    adding compressor nodes that summarize multiple edges of the same type
    to high-degree nodes.  Dedensification will only add a compressor node when
    doing so will reduce the total number of edges in the given graph. This
    implementation currently supports graphs with a single edge type.

    Examples
    --------
    Dedensification will only add compressor nodes when doing so would result
    in fewer edges::

        >>> original_graph = nx.DiGraph()
        >>> original_graph.add_nodes_from(
        ...     ["1", "2", "3", "4", "5", "6", "A", "B", "C"]
        ... )
        >>> original_graph.add_edges_from(
        ...     [
        ...         ("1", "C"), ("1", "B"),
        ...         ("2", "C"), ("2", "B"), ("2", "A"),
        ...         ("3", "B"), ("3", "A"), ("3", "6"),
        ...         ("4", "C"), ("4", "B"), ("4", "A"),
        ...         ("5", "B"), ("5", "A"),
        ...         ("6", "5"),
        ...         ("A", "6")
        ...     ]
        ... )
        >>> c_graph, c_nodes = nx.dedensify(original_graph, threshold=2)
        >>> original_graph.number_of_edges()
        15
        >>> c_graph.number_of_edges()
        14

    A dedensified, directed graph can be "densified" to reconstruct the
    original graph::

        >>> original_graph = nx.DiGraph()
        >>> original_graph.add_nodes_from(
        ...     ["1", "2", "3", "4", "5", "6", "A", "B", "C"]
        ... )
        >>> original_graph.add_edges_from(
        ...     [
        ...         ("1", "C"), ("1", "B"),
        ...         ("2", "C"), ("2", "B"), ("2", "A"),
        ...         ("3", "B"), ("3", "A"), ("3", "6"),
        ...         ("4", "C"), ("4", "B"), ("4", "A"),
        ...         ("5", "B"), ("5", "A"),
        ...         ("6", "5"),
        ...         ("A", "6")
        ...     ]
        ... )
        >>> c_graph, c_nodes = nx.dedensify(original_graph, threshold=2)
        >>> # re-densifies the compressed graph into the original graph
        >>> for c_node in c_nodes:
        ...     all_neighbors = set(nx.all_neighbors(c_graph, c_node))
        ...     out_neighbors = set(c_graph.neighbors(c_node))
        ...     for out_neighbor in out_neighbors:
        ...         c_graph.remove_edge(c_node, out_neighbor)
        ...     in_neighbors = all_neighbors - out_neighbors
        ...     for in_neighbor in in_neighbors:
        ...         c_graph.remove_edge(in_neighbor, c_node)
        ...         for out_neighbor in out_neighbors:
        ...             c_graph.add_edge(in_neighbor, out_neighbor)
        ...     c_graph.remove_node(c_node)
        ...
        >>> nx.is_isomorphic(original_graph, c_graph)
        True

    References
    ----------
    .. [1] Maccioni, A., & Abadi, D. J. (2016, August).
       Scalable pattern matching over compressed graphs via dedensification.
       In Proceedings of the 22nd ACM SIGKDD International Conference on
       Knowledge Discovery and Data Mining (pp. 1755-1764).
       http://www.cs.umd.edu/~abadi/papers/graph-dedense.pdf
    """
    if threshold < 2:
        raise nx.NetworkXError("The degree threshold must be >= 2")

    degrees = G.in_degree if G.is_directed() else G.degree
    # Group nodes based on degree threshold
    high_degree_nodes = {n for n, d in degrees if d > threshold}
    low_degree_nodes = G.nodes() - high_degree_nodes

    auxiliary = {}
    for node in G:
        high_degree_nbrs = frozenset(high_degree_nodes & set(G[node]))
        if high_degree_nbrs:
            if high_degree_nbrs in auxiliary:
                auxiliary[high_degree_nbrs].add(node)
            else:
                auxiliary[high_degree_nbrs] = {node}

    if copy:
        G = G.copy()

    compressor_nodes = set()
    for index, (high_degree_nodes, low_degree_nodes) in enumerate(auxiliary.items()):
        low_degree_node_count = len(low_degree_nodes)
        high_degree_node_count = len(high_degree_nodes)
        old_edges = high_degree_node_count * low_degree_node_count
        new_edges = high_degree_node_count + low_degree_node_count
        if old_edges <= new_edges:
            continue
        compression_node = "".join(str(node) for node in high_degree_nodes)
        if prefix:
            compression_node = str(prefix) + compression_node
        for node in low_degree_nodes:
            for high_node in high_degree_nodes:
                if G.has_edge(node, high_node):
                    G.remove_edge(node, high_node)

            G.add_edge(node, compression_node)
        for node in high_degree_nodes:
            G.add_edge(compression_node, node)
        compressor_nodes.add(compression_node)
    return G, compressor_nodes


def _snap_build_graph(
    G,
    groups,
    node_attributes,
    edge_attributes,
    neighbor_info,
    edge_types,
    prefix,
    supernode_attribute,
    superedge_attribute,
):
    """
    Build the summary graph from the data structures produced in the SNAP aggregation algorithm

    Used in the SNAP aggregation algorithm to build the output summary graph and supernode
    lookup dictionary.  This process uses the original graph and the data structures to
    create the supernodes with the correct node attributes, and the superedges with the correct
    edge attributes

    Parameters
    ----------
    G: networkx.Graph
        the original graph to be summarized
    groups: dict
        A dictionary of unique group IDs and their corresponding node groups
    node_attributes: iterable
        An iterable of the node attributes considered in the summarization process
    edge_attributes: iterable
        An iterable of the edge attributes considered in the summarization process
    neighbor_info: dict
        A data structure indicating the number of edges a node has with the
        groups in the current summarization of each edge type
    edge_types: dict
        dictionary of edges in the graph and their corresponding attributes recognized
        in the summarization
    prefix: string
        The prefix to be added to all supernodes
    supernode_attribute: str
        The node attribute for recording the supernode groupings of nodes
    superedge_attribute: str
        The edge attribute for recording the edge types represented by superedges

    Returns
    -------
    summary graph: Networkx graph
    """
    output = G.__class__()
    node_label_lookup = {}
    for index, group_id in enumerate(groups):
        group_set = groups[group_id]
        supernode = f"{prefix}{index}"
        node_label_lookup[group_id] = supernode
        supernode_attributes = {
            attr: G.nodes[next(iter(group_set))][attr] for attr in node_attributes
        }
        supernode_attributes[supernode_attribute] = group_set
        output.add_node(supernode, **supernode_attributes)

    for group_id in groups:
        group_set = groups[group_id]
        source_supernode = node_label_lookup[group_id]
        for other_group, group_edge_types in neighbor_info[
            next(iter(group_set))
        ].items():
            if group_edge_types:
                target_supernode = node_label_lookup[other_group]
                summary_graph_edge = (source_supernode, target_supernode)

                edge_types = [
                    dict(zip(edge_attributes, edge_type))
                    for edge_type in group_edge_types
                ]

                has_edge = output.has_edge(*summary_graph_edge)
                if output.is_multigraph():
                    if not has_edge:
                        for edge_type in edge_types:
                            output.add_edge(*summary_graph_edge, **edge_type)
                    elif not output.is_directed():
                        existing_edge_data = output.get_edge_data(*summary_graph_edge)
                        for edge_type in edge_types:
                            if edge_type not in existing_edge_data.values():
                                output.add_edge(*summary_graph_edge, **edge_type)
                else:
                    superedge_attributes = {superedge_attribute: edge_types}
                    output.add_edge(*summary_graph_edge, **superedge_attributes)

    return output


def _snap_eligible_group(G, groups, group_lookup, edge_types):
    """
    Determines if a group is eligible to be split.

    A group is eligible to be split if all nodes in the group have edges of the same type(s)
    with the same other groups.

    Parameters
    ----------
    G: graph
        graph to be summarized
    groups: dict
        A dictionary of unique group IDs and their corresponding node groups
    group_lookup: dict
        dictionary of nodes and their current corresponding group ID
    edge_types: dict
        dictionary of edges in the graph and their corresponding attributes recognized
        in the summarization

    Returns
    -------
    tuple: group ID to split, and neighbor-groups participation_counts data structure
    """
    nbr_info = {node: {gid: Counter() for gid in groups} for node in group_lookup}
    for group_id in groups:
        current_group = groups[group_id]

        # build nbr_info for nodes in group
        for node in current_group:
            nbr_info[node] = {group_id: Counter() for group_id in groups}
            edges = G.edges(node, keys=True) if G.is_multigraph() else G.edges(node)
            for edge in edges:
                neighbor = edge[1]
                edge_type = edge_types[edge]
                neighbor_group_id = group_lookup[neighbor]
                nbr_info[node][neighbor_group_id][edge_type] += 1

        # check if group_id is eligible to be split
        group_size = len(current_group)
        for other_group_id in groups:
            edge_counts = Counter()
            for node in current_group:
                edge_counts.update(nbr_info[node][other_group_id].keys())

            if not all(count == group_size for count in edge_counts.values()):
                # only the nbr_info of the returned group_id is required for handling group splits
                return group_id, nbr_info

    # if no eligible groups, complete nbr_info is calculated
    return None, nbr_info


def _snap_split(groups, neighbor_info, group_lookup, group_id):
    """
    Splits a group based on edge types and updates the groups accordingly

    Splits the group with the given group_id based on the edge types
    of the nodes so that each new grouping will all have the same
    edges with other nodes.

    Parameters
    ----------
    groups: dict
        A dictionary of unique group IDs and their corresponding node groups
    neighbor_info: dict
        A data structure indicating the number of edges a node has with the
        groups in the current summarization of each edge type
    edge_types: dict
        dictionary of edges in the graph and their corresponding attributes recognized
        in the summarization
    group_lookup: dict
        dictionary of nodes and their current corresponding group ID
    group_id: object
        ID of group to be split

    Returns
    -------
    dict
        The updated groups based on the split
    """
    new_group_mappings = defaultdict(set)
    for node in groups[group_id]:
        signature = tuple(
            frozenset(edge_types) for edge_types in neighbor_info[node].values()
        )
        new_group_mappings[signature].add(node)

    # leave the biggest new_group as the original group
    new_groups = sorted(new_group_mappings.values(), key=len)
    for new_group in new_groups[:-1]:
        # Assign unused integer as the new_group_id
        # ids are tuples, so will not interact with the original group_ids
        new_group_id = len(groups)
        groups[new_group_id] = new_group
        groups[group_id] -= new_group
        for node in new_group:
            group_lookup[node] = new_group_id

    return groups


@nx._dispatchable(
    node_attrs="[node_attributes]", edge_attrs="[edge_attributes]", returns_graph=True
)
def snap_aggregation(
    G,
    node_attributes,
    edge_attributes=(),
    prefix="Supernode-",
    supernode_attribute="group",
    superedge_attribute="types",
):
    """Creates a summary graph based on attributes and connectivity.

    This function uses the Summarization by Grouping Nodes on Attributes
    and Pairwise edges (SNAP) algorithm for summarizing a given
    graph by grouping nodes by node attributes and their edge attributes
    into supernodes in a summary graph.  This name SNAP should not be
    confused with the Stanford Network Analysis Project (SNAP).

    Here is a high-level view of how this algorithm works:

    1) Group nodes by node attribute values.

    2) Iteratively split groups until all nodes in each group have edges
    to nodes in the same groups. That is, until all the groups are homogeneous
    in their member nodes' edges to other groups.  For example,
    if all the nodes in group A only have edge to nodes in group B, then the
    group is homogeneous and does not need to be split. If all nodes in group B
    have edges with nodes in groups {A, C}, but some also have edges with other
    nodes in B, then group B is not homogeneous and needs to be split into
    groups have edges with {A, C} and a group of nodes having
    edges with {A, B, C}.  This way, viewers of the summary graph can
    assume that all nodes in the group have the exact same node attributes and
    the exact same edges.

    3) Build the output summary graph, where the groups are represented by
    super-nodes. Edges represent the edges shared between all the nodes in each
    respective groups.

    A SNAP summary graph can be used to visualize graphs that are too large to display
    or visually analyze, or to efficiently identify sets of similar nodes with similar connectivity
    patterns to other sets of similar nodes based on specified node and/or edge attributes in a graph.

    Parameters
    ----------
    G: graph
        Networkx Graph to be summarized
    node_attributes: iterable, required
        An iterable of the node attributes used to group nodes in the summarization process. Nodes
        with the same values for these attributes will be grouped together in the summary graph.
    edge_attributes: iterable, optional
        An iterable of the edge attributes considered in the summarization process.  If provided, unique
        combinations of the attribute values found in the graph are used to
        determine the edge types in the graph.  If not provided, all edges
        are considered to be of the same type.
    prefix: str
        The prefix used to denote supernodes in the summary graph. Defaults to 'Supernode-'.
    supernode_attribute: str
        The node attribute for recording the supernode groupings of nodes. Defaults to 'group'.
    superedge_attribute: str
        The edge attribute for recording the edge types of multiple edges. Defaults to 'types'.

    Returns
    -------
    networkx.Graph: summary graph

    Examples
    --------
    SNAP aggregation takes a graph and summarizes it in the context of user-provided
    node and edge attributes such that a viewer can more easily extract and
    analyze the information represented by the graph

    >>> nodes = {
    ...     "A": dict(color="Red"),
    ...     "B": dict(color="Red"),
    ...     "C": dict(color="Red"),
    ...     "D": dict(color="Red"),
    ...     "E": dict(color="Blue"),
    ...     "F": dict(color="Blue"),
    ... }
    >>> edges = [
    ...     ("A", "E", "Strong"),
    ...     ("B", "F", "Strong"),
    ...     ("C", "E", "Weak"),
    ...     ("D", "F", "Weak"),
    ... ]
    >>> G = nx.Graph()
    >>> for node in nodes:
    ...     attributes = nodes[node]
    ...     G.add_node(node, **attributes)
    >>> for source, target, type in edges:
    ...     G.add_edge(source, target, type=type)
    >>> node_attributes = ("color",)
    >>> edge_attributes = ("type",)
    >>> summary_graph = nx.snap_aggregation(
    ...     G, node_attributes=node_attributes, edge_attributes=edge_attributes
    ... )

    Notes
    -----
    The summary graph produced is called a maximum Attribute-edge
    compatible (AR-compatible) grouping.  According to [1]_, an
    AR-compatible grouping means that all nodes in each group have the same
    exact node attribute values and the same exact edges and
    edge types to one or more nodes in the same groups.  The maximal
    AR-compatible grouping is the grouping with the minimal cardinality.

    The AR-compatible grouping is the most detailed grouping provided by
    any of the SNAP algorithms.

    References
    ----------
    .. [1] Y. Tian, R. A. Hankins, and J. M. Patel. Efficient aggregation
       for graph summarization. In Proc. 2008 ACM-SIGMOD Int. Conf.
       Management of Data (SIGMOD’08), pages 567–580, Vancouver, Canada,
       June 2008.
    """
    edge_types = {
        edge: tuple(attrs.get(attr) for attr in edge_attributes)
        for edge, attrs in G.edges.items()
    }
    if not G.is_directed():
        if G.is_multigraph():
            # list is needed to avoid mutating while iterating
            edges = [((v, u, k), etype) for (u, v, k), etype in edge_types.items()]
        else:
            # list is needed to avoid mutating while iterating
            edges = [((v, u), etype) for (u, v), etype in edge_types.items()]
        edge_types.update(edges)

    group_lookup = {
        node: tuple(attrs[attr] for attr in node_attributes)
        for node, attrs in G.nodes.items()
    }
    groups = defaultdict(set)
    for node, node_type in group_lookup.items():
        groups[node_type].add(node)

    eligible_group_id, nbr_info = _snap_eligible_group(
        G, groups, group_lookup, edge_types
    )
    while eligible_group_id:
        groups = _snap_split(groups, nbr_info, group_lookup, eligible_group_id)
        eligible_group_id, nbr_info = _snap_eligible_group(
            G, groups, group_lookup, edge_types
        )
    return _snap_build_graph(
        G,
        groups,
        node_attributes,
        edge_attributes,
        nbr_info,
        edge_types,
        prefix,
        supernode_attribute,
        superedge_attribute,
    )
