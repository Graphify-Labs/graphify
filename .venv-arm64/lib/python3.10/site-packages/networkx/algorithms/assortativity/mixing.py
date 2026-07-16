"""
Mixing matrices for node attributes and degree.
"""

import networkx as nx
from networkx.algorithms.assortativity.pairs import node_attribute_xy, node_degree_xy
from networkx.utils import dict_to_numpy_array

__all__ = [
    "attribute_mixing_matrix",
    "attribute_mixing_dict",
    "degree_mixing_matrix",
    "degree_mixing_dict",
    "mixing_dict",
]


@nx._dispatchable(node_attrs="attribute")
def attribute_mixing_dict(G, attribute, nodes=None, normalized=False):
    """Returns dictionary representation of mixing matrix for attribute.

    Parameters
    ----------
    G : graph
       NetworkX graph object.

    attribute : string
       Node attribute key.

    nodes: list or iterable (optional)
        Unse nodes in container to build the dict. The default is all nodes.

    normalized : bool (default=False)
       Return counts if False or probabilities if True.

    Examples
    --------
    >>> G = nx.Graph()
    >>> G.add_nodes_from([0, 1], color="red")
    >>> G.add_nodes_from([2, 3], color="blue")
    >>> G.add_edge(1, 3)
    >>> d = nx.attribute_mixing_dict(G, "color")
    >>> print(d["red"]["blue"])
    1
    >>> print(d["blue"]["red"])  # d symmetric for undirected graphs
    1

    Returns
    -------
    d : dictionary
       Counts or joint probability of occurrence of attribute pairs.
    """
    xy_iter = node_attribute_xy(G, attribute, nodes)
    return mixing_dict(xy_iter, normalized=normalized)


@nx._dispatchable(node_attrs="attribute")
def attribute_mixing_matrix(G, attribute, nodes=None, mapping=None, normalized=True):
    """Returns mixing matrix for attribute.

    Parameters
    ----------
    G : graph
       NetworkX graph object.

    attribute : string
       Node attribute key.

    nodes: list or iterable (optional)
        Use only nodes in container to build the matrix. The default is
        all nodes.

    mapping : dictionary, optional
       Mapping from node attribute to integer index in matrix.
       If not specified, an arbitrary ordering will be used.

    normalized : bool (default=True)
       Return counts if False or probabilities if True.

    Returns
    -------
    m: numpy array
       Counts or joint probability of occurrence of attribute pairs.

    Notes
    -----
    If each node has a unique attribute value, the unnormalized mixing matrix
    will be equal to the adjacency matrix. To get a denser mixing matrix,
    the rounding can be performed to form groups of nodes with equal values.
    For example, the exact height of persons in cm (180.79155222, 163.9080892,
    163.30095355, 167.99016217, 168.21590163, ...) can be rounded to (180, 163,
    163, 168, 168, ...).

    Definitions of attribute mixing matrix vary on whether the matrix
    should include rows for attribute values that don't arise. Here we
    do not include such empty-rows. But you can force them to appear
    by inputting a `mapping` that includes those values.

    Examples
    --------
    >>> G = nx.path_graph(3)
    >>> gender = {0: "male", 1: "female", 2: "female"}
    >>> nx.set_node_attributes(G, gender, "gender")
    >>> mapping = {"male": 0, "female": 1}
    >>> mix_mat = nx.attribute_mixing_matrix(G, "gender", mapping=mapping)
    >>> mix_mat
    array([[0.  , 0.25],
           [0.25, 0.5 ]])
    """
    d = attribute_mixing_dict(G, attribute, nodes)
    a = dict_to_numpy_array(d, mapping=mapping)
    if normalized:
        a = a / a.sum()
    return a


@nx._dispatchable(edge_attrs="weight")
def degree_mixing_dict(G, x="out", y="in", weight=None, nodes=None, normalized=False):
    """Returns dictionary representation of mixing matrix for degree.

    Parameters
    ----------
    G : graph
        NetworkX graph object.

    x: string ('in','out')
       The degree type for source node (directed graphs only).

    y: string ('in','out')
       The degree type for target node (directed graphs only).

    weight: string or None, optional (default=None)
       The edge attribute that holds the numerical value used
       as a weight.  If None, then each edge has weight 1.
       The degree is the sum of the edge weights adjacent to the node.

    normalized : bool (default=False)
        Return counts if False or probabilities if True.

    Returns
    -------
    d: dictionary
       Counts or joint probability of occurrence of degree pairs.
    """
    xy_iter = node_degree_xy(G, x=x, y=y, nodes=nodes, weight=weight)
    return mixing_dict(xy_iter, normalized=normalized)


@nx._dispatchable(edge_attrs="weight")
def degree_mixing_matrix(
    G, x="out", y="in", weight=None, nodes=None, normalized=True, mapping=None
):
    """Returns mixing matrix for attribute.

    Parameters
    ----------
    G : graph
       NetworkX graph object.

    x: string ('in','out')
       The degree type for source node (directed graphs only).

    y: string ('in','out')
       The degree type for target node (directed graphs only).

    nodes: list or iterable (optional)
        Build the matrix using only nodes in container.
        The default is all nodes.

    weight: string or None, optional (default=None)
       The edge attribute that holds the numerical value used
       as a weight.  If None, then each edge has weight 1.
       The degree is the sum of the edge weights adjacent to the node.

    normalized : bool (default=True)
       Return counts if False or probabilities if True.

    mapping : dictionary, optional
       Mapping from node degree to integer index in matrix.
       If not specified, an arbitrary ordering will be used.

    Returns
    -------
    m: numpy array
       Counts, or joint probability, of occurrence of node degree.

    Notes
    -----
    Definitions of degree mixing matrix vary on whether the matrix
    should include rows for degree values that don't arise. Here we
    do not include such empty-rows. But you can force them to appear
    by inputting a `mapping` that includes those values. See examples.

    Examples
    --------
    >>> G = nx.star_graph(3)
    >>> mix_mat = nx.degree_mixing_matrix(G)
    >>> mix_mat
    array([[0. , 0.5],
           [0.5, 0. ]])

    If you want every possible degree to appear as a row, even if no nodes
    have that degree, use `mapping` as follows,

    >>> max_degree = max(deg for n, deg in G.degree)
    >>> mapping = {x: x for x in range(max_degree + 1)}  # identity mapping
    >>> mix_mat = nx.degree_mixing_matrix(G, mapping=mapping)
    >>> mix_mat
    array([[0. , 0. , 0. , 0. ],
           [0. , 0. , 0. , 0.5],
           [0. , 0. , 0. , 0. ],
           [0. , 0.5, 0. , 0. ]])
    """
    d = degree_mixing_dict(G, x=x, y=y, nodes=nodes, weight=weight)
    a = dict_to_numpy_array(d, mapping=mapping)
    if normalized:
        a = a / a.sum()
    return a


def mixing_dict(xy, normalized=False):
    """Returns a dictionary representation of mixing matrix.

    Parameters
    ----------
    xy : list or container of two-tuples
       Pairs of (x,y) items.

    attribute : string
       Node attribute key

    normalized : bool (default=False)
       Return counts if False or probabilities if True.

    Returns
    -------
    d: dictionary
       Counts or Joint probability of occurrence of values in xy.
    """
    d = {}
    psum = 0.0
    for x, y in xy:
        if x not in d:
            d[x] = {}
        if y not in d:
            d[y] = {}
        v = d[x].get(y, 0)
        d[x][y] = v + 1
        psum += 1

    if normalized:
        for _, jdict in d.items():
            for j in jdict:
                jdict[j] /= psum
    return d
