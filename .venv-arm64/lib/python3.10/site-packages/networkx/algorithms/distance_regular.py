"""
=======================
Distance-regular graphs
=======================
"""

import networkx as nx
from networkx.utils import not_implemented_for

from .distance_measures import diameter

__all__ = [
    "is_distance_regular",
    "is_strongly_regular",
    "intersection_array",
    "global_parameters",
]


@nx._dispatchable
def is_distance_regular(G):
    """Returns True if the graph is distance regular, False otherwise.

    A connected graph G is distance-regular if for any nodes x,y
    and any integers i,j=0,1,...,d (where d is the graph
    diameter), the number of vertices at distance i from x and
    distance j from y depends only on i,j and the graph distance
    between x and y, independently of the choice of x and y.

    Parameters
    ----------
    G: Networkx graph (undirected)

    Returns
    -------
    bool
      True if the graph is Distance Regular, False otherwise

    Examples
    --------
    >>> G = nx.hypercube_graph(6)
    >>> nx.is_distance_regular(G)
    True

    See Also
    --------
    intersection_array, global_parameters

    Notes
    -----
    For undirected and simple graphs only

    References
    ----------
    .. [1] Brouwer, A. E.; Cohen, A. M.; and Neumaier, A.
        Distance-Regular Graphs. New York: Springer-Verlag, 1989.
    .. [2] Weisstein, Eric W. "Distance-Regular Graph."
        http://mathworld.wolfram.com/Distance-RegularGraph.html

    """
    try:
        intersection_array(G)
        return True
    except nx.NetworkXError:
        return False


def global_parameters(b, c):
    """Returns global parameters for a given intersection array.

    Given a distance-regular graph G with integers b_i, c_i,i = 0,....,d
    such that for any 2 vertices x,y in G at a distance i=d(x,y), there
    are exactly c_i neighbors of y at a distance of i-1 from x and b_i
    neighbors of y at a distance of i+1 from x.

    Thus, a distance regular graph has the global parameters,
    [[c_0,a_0,b_0],[c_1,a_1,b_1],......,[c_d,a_d,b_d]] for the
    intersection array  [b_0,b_1,.....b_{d-1};c_1,c_2,.....c_d]
    where a_i+b_i+c_i=k , k= degree of every vertex.

    Parameters
    ----------
    b : list

    c : list

    Returns
    -------
    iterable
       An iterable over three tuples.

    Examples
    --------
    >>> G = nx.dodecahedral_graph()
    >>> b, c = nx.intersection_array(G)
    >>> list(nx.global_parameters(b, c))
    [(0, 0, 3), (1, 0, 2), (1, 1, 1), (1, 1, 1), (2, 0, 1), (3, 0, 0)]

    References
    ----------
    .. [1] Weisstein, Eric W. "Global Parameters."
       From MathWorld--A Wolfram Web Resource.
       http://mathworld.wolfram.com/GlobalParameters.html

    See Also
    --------
    intersection_array
    """
    return ((y, b[0] - x - y, x) for x, y in zip(b + [0], [0] + c))


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def intersection_array(G):
    """Returns the intersection array of a distance-regular graph.

    Given a distance-regular graph G with integers b_i, c_i,i = 0,....,d
    such that for any 2 vertices x,y in G at a distance i=d(x,y), there
    are exactly c_i neighbors of y at a distance of i-1 from x and b_i
    neighbors of y at a distance of i+1 from x.

    A distance regular graph's intersection array is given by,
    [b_0,b_1,.....b_{d-1};c_1,c_2,.....c_d]

    Parameters
    ----------
    G: Networkx graph (undirected)

    Returns
    -------
    b,c: tuple of lists

    Examples
    --------
    >>> G = nx.icosahedral_graph()
    >>> nx.intersection_array(G)
    ([5, 2, 1], [1, 2, 5])

    References
    ----------
    .. [1] Weisstein, Eric W. "Intersection Array."
       From MathWorld--A Wolfram Web Resource.
       http://mathworld.wolfram.com/IntersectionArray.html

    See Also
    --------
    global_parameters
    """
    # test for regular graph (all degrees must be equal)
    if len(G) == 0:
        raise nx.NetworkXPointlessConcept("Graph has no nodes.")
    degree = iter(G.degree())
    (_, k) = next(degree)
    for _, knext in degree:
        if knext != k:
            raise nx.NetworkXError("Graph is not distance regular.")
        k = knext
    path_length = dict(nx.all_pairs_shortest_path_length(G))
    diameter = max(max(path_length[n].values()) for n in path_length)
    bint = {}  # 'b' intersection array
    cint = {}  # 'c' intersection array
    for u in G:
        for v in G:
            try:
                i = path_length[u][v]
            except KeyError as err:  # graph must be connected
                raise nx.NetworkXError("Graph is not distance regular.") from err
            # number of neighbors of v at a distance of i-1 from u
            c = len([n for n in G[v] if path_length[n][u] == i - 1])
            # number of neighbors of v at a distance of i+1 from u
            b = len([n for n in G[v] if path_length[n][u] == i + 1])
            # b,c are independent of u and v
            if cint.get(i, c) != c or bint.get(i, b) != b:
                raise nx.NetworkXError("Graph is not distance regular")
            bint[i] = b
            cint[i] = c
    return (
        [bint.get(j, 0) for j in range(diameter)],
        [cint.get(j + 1, 0) for j in range(diameter)],
    )


# TODO There is a definition for directed strongly regular graphs.
@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable
def is_strongly_regular(G):
    """Returns True if and only if the given graph is strongly
    regular.

    An undirected graph is *strongly regular* if

    * it is regular,
    * each pair of adjacent vertices has the same number of neighbors in
      common,
    * each pair of nonadjacent vertices has the same number of neighbors
      in common.

    Each strongly regular graph is a distance-regular graph.
    Conversely, if a distance-regular graph has diameter two, then it is
    a strongly regular graph. For more information on distance-regular
    graphs, see :func:`is_distance_regular`.

    Parameters
    ----------
    G : NetworkX graph
        An undirected graph.

    Returns
    -------
    bool
        Whether `G` is strongly regular.

    Examples
    --------

    The cycle graph on five vertices is strongly regular. It is
    two-regular, each pair of adjacent vertices has no shared neighbors,
    and each pair of nonadjacent vertices has one shared neighbor::

        >>> G = nx.cycle_graph(5)
        >>> nx.is_strongly_regular(G)
        True

    """
    # Here is an alternate implementation based directly on the
    # definition of strongly regular graphs:
    #
    #     return (all_equal(G.degree().values())
    #             and all_equal(len(common_neighbors(G, u, v))
    #                           for u, v in G.edges())
    #             and all_equal(len(common_neighbors(G, u, v))
    #                           for u, v in non_edges(G)))
    #
    # We instead use the fact that a distance-regular graph of diameter
    # two is strongly regular.
    return is_distance_regular(G) and diameter(G) == 2
