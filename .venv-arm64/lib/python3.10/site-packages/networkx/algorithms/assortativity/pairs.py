"""Generators of x-y pairs of node data."""

import networkx as nx

__all__ = ["node_attribute_xy", "node_degree_xy"]


@nx._dispatchable(node_attrs="attribute")
def node_attribute_xy(G, attribute, nodes=None):
    """Yields 2-tuples of node attribute values for all edges in `G`.

    This generator yields, for each edge in `G` incident to a node in `nodes`,
    a 2-tuple of form ``(attribute value,  attribute value)`` for the parameter
    specified node-attribute.

    Parameters
    ----------
    G: NetworkX graph

    attribute: key
        The node attribute key.

    nodes: list or iterable (optional)
        Use only edges that are incident to specified nodes.
        The default is all nodes.

    Yields
    ------
    (x, y): 2-tuple
        Generates 2-tuple of (attribute, attribute) values.

    Examples
    --------
    >>> G = nx.DiGraph()
    >>> G.add_node(1, color="red")
    >>> G.add_node(2, color="blue")
    >>> G.add_node(3, color="green")
    >>> G.add_edge(1, 2)
    >>> list(nx.node_attribute_xy(G, "color"))
    [('red', 'blue')]

    Notes
    -----
    For undirected graphs, each edge is produced twice, once for each edge
    representation (u, v) and (v, u), with the exception of self-loop edges
    which only appear once.
    """
    if nodes is None:
        nodes = set(G)
    else:
        nodes = set(nodes)
    Gnodes = G.nodes
    for u, nbrsdict in G.adjacency():
        if u not in nodes:
            continue
        uattr = Gnodes[u].get(attribute, None)
        if G.is_multigraph():
            for v, keys in nbrsdict.items():
                vattr = Gnodes[v].get(attribute, None)
                for _ in keys:
                    yield (uattr, vattr)
        else:
            for v in nbrsdict:
                vattr = Gnodes[v].get(attribute, None)
                yield (uattr, vattr)


@nx._dispatchable(edge_attrs="weight")
def node_degree_xy(G, x="out", y="in", weight=None, nodes=None):
    """Yields 2-tuples of ``(degree, degree)`` values for edges in `G`.

    This generator yields, for each edge in `G` incident to a node in `nodes`,
    a 2-tuple of form ``(degree, degree)``. The node degrees are weighted
    when a `weight` attribute is specified.

    Parameters
    ----------
    G: NetworkX graph

    x: string ('in','out')
       The degree type for source node (directed graphs only).

    y: string ('in','out')
       The degree type for target node (directed graphs only).

    weight: string or None, optional (default=None)
       The edge attribute that holds the numerical value used
       as a weight.  If None, then each edge has weight 1.
       The degree is the sum of the edge weights adjacent to the node.

    nodes: list or iterable (optional)
        Use only edges that are adjacency to specified nodes.
        The default is all nodes.

    Yields
    ------
    (x, y): 2-tuple
        Generates 2-tuple of (degree, degree) values.

    Examples
    --------
    >>> G = nx.DiGraph()
    >>> G.add_edge(1, 2)
    >>> list(nx.node_degree_xy(G, x="out", y="in"))
    [(1, 1)]
    >>> list(nx.node_degree_xy(G, x="in", y="out"))
    [(0, 0)]

    Notes
    -----
    For undirected graphs, each edge is produced twice, once for each edge
    representation (u, v) and (v, u), with the exception of self-loop edges
    which only appear once.
    """
    nodes = set(G) if nodes is None else set(nodes)
    if G.is_directed():
        direction = {"out": G.out_degree, "in": G.in_degree}
        xdeg = direction[x]
        ydeg = direction[y]
    else:
        xdeg = ydeg = G.degree

    for u, degu in xdeg(nodes, weight=weight):
        # use G.edges to treat multigraphs correctly
        neighbors = (nbr for _, nbr in G.edges(u) if nbr in nodes)
        for _, degv in ydeg(neighbors, weight=weight):
            yield degu, degv
