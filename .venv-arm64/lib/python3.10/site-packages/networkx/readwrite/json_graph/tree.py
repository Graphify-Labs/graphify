from itertools import chain

import networkx as nx

__all__ = ["tree_data", "tree_graph"]


def tree_data(G, root, ident="id", children="children"):
    """Returns data in tree format that is suitable for JSON serialization
    and use in JavaScript documents.

    Parameters
    ----------
    G : NetworkX graph
       G must be an oriented tree

    root : node
       The root of the tree

    ident : string
        Attribute name for storing NetworkX-internal graph data. `ident` must
        have a different value than `children`. The default is 'id'.

    children : string
        Attribute name for storing NetworkX-internal graph data. `children`
        must have a different value than `ident`. The default is 'children'.

    Returns
    -------
    data : dict
       A dictionary with node-link formatted data.

    Raises
    ------
    NetworkXError
        If `children` and `ident` attributes are identical.

    Examples
    --------
    >>> from networkx.readwrite import json_graph
    >>> G = nx.DiGraph([(1, 2)])
    >>> data = json_graph.tree_data(G, root=1)

    To serialize with json

    >>> import json
    >>> s = json.dumps(data)

    Notes
    -----
    Node attributes are stored in this format but keys
    for attributes must be strings if you want to serialize with JSON.

    Graph and edge attributes are not stored.

    See Also
    --------
    tree_graph, node_link_data, adjacency_data
    """
    if G.number_of_nodes() != G.number_of_edges() + 1:
        raise TypeError("G is not a tree.")
    if not G.is_directed():
        raise TypeError("G is not directed.")
    if not nx.is_weakly_connected(G):
        raise TypeError("G is not weakly connected.")

    if ident == children:
        raise nx.NetworkXError("The values for `id` and `children` must be different.")

    def add_children(n, G):
        nbrs = G[n]
        if len(nbrs) == 0:
            return []
        children_ = []
        for child in nbrs:
            d = {**G.nodes[child], ident: child}
            c = add_children(child, G)
            if c:
                d[children] = c
            children_.append(d)
        return children_

    return {**G.nodes[root], ident: root, children: add_children(root, G)}


@nx._dispatchable(graphs=None, returns_graph=True)
def tree_graph(data, ident="id", children="children"):
    """Returns graph from tree data format.

    Parameters
    ----------
    data : dict
        Tree formatted graph data

    ident : string
        Attribute name for storing NetworkX-internal graph data. `ident` must
        have a different value than `children`. The default is 'id'.

    children : string
        Attribute name for storing NetworkX-internal graph data. `children`
        must have a different value than `ident`. The default is 'children'.

    Returns
    -------
    G : NetworkX DiGraph

    Examples
    --------
    >>> from networkx.readwrite import json_graph
    >>> G = nx.DiGraph([(1, 2)])
    >>> data = json_graph.tree_data(G, root=1)
    >>> H = json_graph.tree_graph(data)

    See Also
    --------
    tree_data, node_link_data, adjacency_data
    """
    graph = nx.DiGraph()

    def add_children(parent, children_):
        for data in children_:
            child = data[ident]
            graph.add_edge(parent, child)
            grandchildren = data.get(children, [])
            if grandchildren:
                add_children(child, grandchildren)
            nodedata = {
                str(k): v for k, v in data.items() if k != ident and k != children
            }
            graph.add_node(child, **nodedata)

    root = data[ident]
    children_ = data.get(children, [])
    nodedata = {str(k): v for k, v in data.items() if k != ident and k != children}
    graph.add_node(root, **nodedata)
    add_children(root, children_)
    return graph
