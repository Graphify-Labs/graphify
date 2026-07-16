"""
Various small and named graphs, together with some compact generators.

"""

__all__ = [
    "LCF_graph",
    "bull_graph",
    "chvatal_graph",
    "cubical_graph",
    "desargues_graph",
    "diamond_graph",
    "dodecahedral_graph",
    "frucht_graph",
    "heawood_graph",
    "hoffman_singleton_graph",
    "house_graph",
    "house_x_graph",
    "icosahedral_graph",
    "krackhardt_kite_graph",
    "moebius_kantor_graph",
    "octahedral_graph",
    "pappus_graph",
    "petersen_graph",
    "sedgewick_maze_graph",
    "tetrahedral_graph",
    "truncated_cube_graph",
    "truncated_tetrahedron_graph",
    "tutte_graph",
]

from functools import wraps

import networkx as nx
from networkx.exception import NetworkXError
from networkx.generators.classic import (
    complete_graph,
    cycle_graph,
    empty_graph,
    path_graph,
)


def _raise_on_directed(func):
    """
    A decorator which inspects the `create_using` argument and raises a
    NetworkX exception when `create_using` is a DiGraph (class or instance) for
    graph generators that do not support directed outputs.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        if kwargs.get("create_using") is not None:
            G = nx.empty_graph(create_using=kwargs["create_using"])
            if G.is_directed():
                raise NetworkXError("Directed Graph not supported")
        return func(*args, **kwargs)

    return wrapper


@nx._dispatchable(graphs=None, returns_graph=True)
def LCF_graph(n, shift_list, repeats, create_using=None):
    """
    Return the cubic graph specified in LCF notation.

    LCF (Lederberg-Coxeter-Fruchte) notation[1]_ is a compressed
    notation used in the generation of various cubic Hamiltonian
    graphs of high symmetry. See, for example, `dodecahedral_graph`,
    `desargues_graph`, `heawood_graph` and `pappus_graph`.

    Nodes are drawn from ``range(n)``. Each node ``n_i`` is connected with
    node ``n_i + shift % n`` where ``shift`` is given by cycling through
    the input `shift_list` `repeat` s times.

    Parameters
    ----------
    n : int
       The starting graph is the `n`-cycle with nodes ``0, ..., n-1``.
       The null graph is returned if `n` < 1.

    shift_list : list
       A list of integer shifts mod `n`, ``[s1, s2, .., sk]``

    repeats : int
       Integer specifying the number of times that shifts in `shift_list`
       are successively applied to each current node in the n-cycle
       to generate an edge between ``n_current`` and ``n_current + shift mod n``.

    Returns
    -------
    G : Graph
       A graph instance created from the specified LCF notation.

    Examples
    --------
    The utility graph $K_{3,3}$

    >>> G = nx.LCF_graph(6, [3, -3], 3)
    >>> G.edges()
    EdgeView([(0, 1), (0, 5), (0, 3), (1, 2), (1, 4), (2, 3), (2, 5), (3, 4), (4, 5)])

    The Heawood graph:

    >>> G = nx.LCF_graph(14, [5, -5], 7)
    >>> nx.is_isomorphic(G, nx.heawood_graph())
    True

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/LCF_notation

    """
    if n <= 0:
        return empty_graph(0, create_using)

    # start with the n-cycle
    G = cycle_graph(n, create_using)
    if G.is_directed():
        raise NetworkXError("Directed Graph not supported")
    G.name = "LCF_graph"
    nodes = sorted(G)

    n_extra_edges = repeats * len(shift_list)
    # edges are added n_extra_edges times
    # (not all of these need be new)
    if n_extra_edges < 1:
        return G

    for i in range(n_extra_edges):
        shift = shift_list[i % len(shift_list)]  # cycle through shift_list
        v1 = nodes[i % n]  # cycle repeatedly through nodes
        v2 = nodes[(i + shift) % n]
        G.add_edge(v1, v2)
    return G


# -------------------------------------------------------------------------------
#   Various small and named graphs
# -------------------------------------------------------------------------------


@_raise_on_directed
@nx._dispatchable(graphs=None, returns_graph=True)
def bull_graph(create_using=None):
    """
    Returns the Bull Graph

    The Bull Graph has 5 nodes and 5 edges. It is a planar undirected
    graph in the form of a triangle with two disjoint pendant edges [1]_
    The name comes from the triangle and pendant edges representing
    respectively the body and legs of a bull.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        A bull graph with 5 nodes

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/Bull_graph.

    """
    G = nx.from_dict_of_lists(
        {0: [1, 2], 1: [0, 2, 3], 2: [0, 1, 4], 3: [1], 4: [2]},
        create_using=create_using,
    )
    G.name = "Bull Graph"
    return G


@_raise_on_directed
@nx._dispatchable(graphs=None, returns_graph=True)
def chvatal_graph(create_using=None):
    """
    Returns the Chvátal Graph

    The Chvátal Graph is an undirected graph with 12 nodes and 24 edges [1]_.
    It has 370 distinct (directed) Hamiltonian cycles, giving a unique generalized
    LCF notation of order 4, two of order 6 , and 43 of order 1 [2]_.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        The Chvátal graph with 12 nodes and 24 edges

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/Chv%C3%A1tal_graph
    .. [2] https://mathworld.wolfram.com/ChvatalGraph.html

    """
    G = nx.from_dict_of_lists(
        {
            0: [1, 4, 6, 9],
            1: [2, 5, 7],
            2: [3, 6, 8],
            3: [4, 7, 9],
            4: [5, 8],
            5: [10, 11],
            6: [10, 11],
            7: [8, 11],
            8: [10],
            9: [10, 11],
        },
        create_using=create_using,
    )
    G.name = "Chvatal Graph"
    return G


@_raise_on_directed
@nx._dispatchable(graphs=None, returns_graph=True)
def cubical_graph(create_using=None):
    """
    Returns the 3-regular Platonic Cubical Graph

    The skeleton of the cube (the nodes and edges) form a graph, with 8
    nodes, and 12 edges. It is a special case of the hypercube graph.
    It is one of 5 Platonic graphs, each a skeleton of its
    Platonic solid [1]_.
    Such graphs arise in parallel processing in computers.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        A cubical graph with 8 nodes and 12 edges

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/Cube#Cubical_graph

    """
    G = nx.from_dict_of_lists(
        {
            0: [1, 3, 4],
            1: [0, 2, 7],
            2: [1, 3, 6],
            3: [0, 2, 5],
            4: [0, 5, 7],
            5: [3, 4, 6],
            6: [2, 5, 7],
            7: [1, 4, 6],
        },
        create_using=create_using,
    )
    G.name = "Platonic Cubical Graph"
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def desargues_graph(create_using=None):
    """
    Returns the Desargues Graph

    The Desargues Graph is a non-planar, distance-transitive cubic graph
    with 20 nodes and 30 edges [1]_.
    It is a symmetric graph. It can be represented in LCF notation
    as [5,-5,9,-9]^5 [2]_.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        Desargues Graph with 20 nodes and 30 edges

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/Desargues_graph
    .. [2] https://mathworld.wolfram.com/DesarguesGraph.html
    """
    G = LCF_graph(20, [5, -5, 9, -9], 5, create_using)
    G.name = "Desargues Graph"
    return G


@_raise_on_directed
@nx._dispatchable(graphs=None, returns_graph=True)
def diamond_graph(create_using=None):
    """
    Returns the Diamond graph

    The Diamond Graph is  planar undirected graph with 4 nodes and 5 edges.
    It is also sometimes known as the double triangle graph or kite graph [1]_.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        Diamond Graph with 4 nodes and 5 edges

    References
    ----------
    .. [1] https://mathworld.wolfram.com/DiamondGraph.html
    """
    G = nx.from_dict_of_lists(
        {0: [1, 2], 1: [0, 2, 3], 2: [0, 1, 3], 3: [1, 2]}, create_using=create_using
    )
    G.name = "Diamond Graph"
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def dodecahedral_graph(create_using=None):
    """
    Returns the Platonic Dodecahedral graph.

    The dodecahedral graph has 20 nodes and 30 edges. The skeleton of the
    dodecahedron forms a graph. It is one of 5 Platonic graphs [1]_.
    It can be described in LCF notation as:
    ``[10, 7, 4, -4, -7, 10, -4, 7, -7, 4]^2`` [2]_.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        Dodecahedral Graph with 20 nodes and 30 edges

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/Regular_dodecahedron#Dodecahedral_graph
    .. [2] https://mathworld.wolfram.com/DodecahedralGraph.html

    """
    G = LCF_graph(20, [10, 7, 4, -4, -7, 10, -4, 7, -7, 4], 2, create_using)
    G.name = "Dodecahedral Graph"
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def frucht_graph(create_using=None):
    """
    Returns the Frucht Graph.

    The Frucht Graph is the smallest cubical graph whose
    automorphism group consists only of the identity element [1]_.
    It has 12 nodes and 18 edges and no nontrivial symmetries.
    It is planar and Hamiltonian [2]_.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        Frucht Graph with 12 nodes and 18 edges

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/Frucht_graph
    .. [2] https://mathworld.wolfram.com/FruchtGraph.html

    """
    G = cycle_graph(7, create_using)
    G.add_edges_from(
        [
            [0, 7],
            [1, 7],
            [2, 8],
            [3, 9],
            [4, 9],
            [5, 10],
            [6, 10],
            [7, 11],
            [8, 11],
            [8, 9],
            [10, 11],
        ]
    )

    G.name = "Frucht Graph"
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def heawood_graph(create_using=None):
    """
    Returns the Heawood Graph, a (3,6) cage.

    The Heawood Graph is an undirected graph with 14 nodes and 21 edges,
    named after Percy John Heawood [1]_.
    It is cubic symmetric, nonplanar, Hamiltonian, and can be represented
    in LCF notation as ``[5,-5]^7`` [2]_.
    It is the unique (3,6)-cage: the regular cubic graph of girth 6 with
    minimal number of vertices [3]_.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        Heawood Graph with 14 nodes and 21 edges

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/Heawood_graph
    .. [2] https://mathworld.wolfram.com/HeawoodGraph.html
    .. [3] https://www.win.tue.nl/~aeb/graphs/Heawood.html

    """
    G = LCF_graph(14, [5, -5], 7, create_using)
    G.name = "Heawood Graph"
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def hoffman_singleton_graph():
    """
    Returns the Hoffman-Singleton Graph.

    The Hoffman–Singleton graph is a symmetrical undirected graph
    with 50 nodes and 175 edges.
    All indices lie in ``Z % 5``: that is, the integers mod 5 [1]_.
    It is the only regular graph of vertex degree 7, diameter 2, and girth 5.
    It is the unique (7,5)-cage graph and Moore graph, and contains many
    copies of the Petersen graph [2]_.

    Returns
    -------
    G : networkx Graph
        Hoffman–Singleton Graph with 50 nodes and 175 edges

    Notes
    -----
    Constructed from pentagon and pentagram as follows: Take five pentagons $P_h$
    and five pentagrams $Q_i$ . Join vertex $j$ of $P_h$ to vertex $h·i+j$ of $Q_i$ [3]_.

    References
    ----------
    .. [1] https://blogs.ams.org/visualinsight/2016/02/01/hoffman-singleton-graph/
    .. [2] https://mathworld.wolfram.com/Hoffman-SingletonGraph.html
    .. [3] https://en.wikipedia.org/wiki/Hoffman%E2%80%93Singleton_graph

    """
    G = nx.Graph()
    for i in range(5):
        for j in range(5):
            G.add_edge(("pentagon", i, j), ("pentagon", i, (j - 1) % 5))
            G.add_edge(("pentagon", i, j), ("pentagon", i, (j + 1) % 5))
            G.add_edge(("pentagram", i, j), ("pentagram", i, (j - 2) % 5))
            G.add_edge(("pentagram", i, j), ("pentagram", i, (j + 2) % 5))
            for k in range(5):
                G.add_edge(("pentagon", i, j), ("pentagram", k, (i * k + j) % 5))
    G = nx.convert_node_labels_to_integers(G)
    G.name = "Hoffman-Singleton Graph"
    return G


@_raise_on_directed
@nx._dispatchable(graphs=None, returns_graph=True)
def house_graph(create_using=None):
    """
    Returns the House graph (square with triangle on top)

    The house graph is a simple undirected graph with
    5 nodes and 6 edges [1]_.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        House graph in the form of a square with a triangle on top

    References
    ----------
    .. [1] https://mathworld.wolfram.com/HouseGraph.html
    """
    G = nx.from_dict_of_lists(
        {0: [1, 2], 1: [0, 3], 2: [0, 3, 4], 3: [1, 2, 4], 4: [2, 3]},
        create_using=create_using,
    )
    G.name = "House Graph"
    return G


@_raise_on_directed
@nx._dispatchable(graphs=None, returns_graph=True)
def house_x_graph(create_using=None):
    """
    Returns the House graph with a cross inside the house square.

    The House X-graph is the House graph plus the two edges connecting diagonally
    opposite vertices of the square base. It is also one of the two graphs
    obtained by removing two edges from the pentatope graph [1]_.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        House graph with diagonal vertices connected

    References
    ----------
    .. [1] https://mathworld.wolfram.com/HouseGraph.html
    """
    G = house_graph(create_using)
    G.add_edges_from([(0, 3), (1, 2)])
    G.name = "House-with-X-inside Graph"
    return G


@_raise_on_directed
@nx._dispatchable(graphs=None, returns_graph=True)
def icosahedral_graph(create_using=None):
    """
    Returns the Platonic Icosahedral graph.

    The icosahedral graph has 12 nodes and 30 edges. It is a Platonic graph
    whose nodes have the connectivity of the icosahedron. It is undirected,
    regular and Hamiltonian [1]_.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        Icosahedral graph with 12 nodes and 30 edges.

    References
    ----------
    .. [1] https://mathworld.wolfram.com/IcosahedralGraph.html
    """
    G = nx.from_dict_of_lists(
        {
            0: [1, 5, 7, 8, 11],
            1: [2, 5, 6, 8],
            2: [3, 6, 8, 9],
            3: [4, 6, 9, 10],
            4: [5, 6, 10, 11],
            5: [6, 11],
            7: [8, 9, 10, 11],
            8: [9],
            9: [10],
            10: [11],
        },
        create_using=create_using,
    )
    G.name = "Platonic Icosahedral Graph"
    return G


@_raise_on_directed
@nx._dispatchable(graphs=None, returns_graph=True)
def krackhardt_kite_graph(create_using=None):
    """
    Returns the Krackhardt Kite Social Network.

    A 10 actor social network introduced by David Krackhardt
    to illustrate different centrality measures [1]_.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        Krackhardt Kite graph with 10 nodes and 18 edges

    Notes
    -----
    The traditional labeling is:
    Andre=1, Beverley=2, Carol=3, Diane=4,
    Ed=5, Fernando=6, Garth=7, Heather=8, Ike=9, Jane=10.

    References
    ----------
    .. [1] Krackhardt, David. "Assessing the Political Landscape: Structure,
       Cognition, and Power in Organizations". Administrative Science Quarterly.
       35 (2): 342–369. doi:10.2307/2393394. JSTOR 2393394. June 1990.

    """
    G = nx.from_dict_of_lists(
        {
            0: [1, 2, 3, 5],
            1: [0, 3, 4, 6],
            2: [0, 3, 5],
            3: [0, 1, 2, 4, 5, 6],
            4: [1, 3, 6],
            5: [0, 2, 3, 6, 7],
            6: [1, 3, 4, 5, 7],
            7: [5, 6, 8],
            8: [7, 9],
            9: [8],
        },
        create_using=create_using,
    )
    G.name = "Krackhardt Kite Social Network"
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def moebius_kantor_graph(create_using=None):
    """
    Returns the Moebius-Kantor graph.

    The Möbius-Kantor graph is the cubic symmetric graph on 16 nodes.
    Its LCF notation is [5,-5]^8, and it is isomorphic to the generalized
    Petersen graph [1]_.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        Moebius-Kantor graph

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/M%C3%B6bius%E2%80%93Kantor_graph

    """
    G = LCF_graph(16, [5, -5], 8, create_using)
    G.name = "Moebius-Kantor Graph"
    return G


@_raise_on_directed
@nx._dispatchable(graphs=None, returns_graph=True)
def octahedral_graph(create_using=None):
    """
    Returns the Platonic Octahedral graph.

    The octahedral graph is the 6-node 12-edge Platonic graph having the
    connectivity of the octahedron [1]_. If 6 couples go to a party,
    and each person shakes hands with every person except his or her partner,
    then this graph describes the set of handshakes that take place;
    for this reason it is also called the cocktail party graph [2]_.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        Octahedral graph

    References
    ----------
    .. [1] https://mathworld.wolfram.com/OctahedralGraph.html
    .. [2] https://en.wikipedia.org/wiki/Tur%C3%A1n_graph#Special_cases

    """
    G = nx.from_dict_of_lists(
        {0: [1, 2, 3, 4], 1: [2, 3, 5], 2: [4, 5], 3: [4, 5], 4: [5]},
        create_using=create_using,
    )
    G.name = "Platonic Octahedral Graph"
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def pappus_graph():
    """
    Returns the Pappus graph.

    The Pappus graph is a cubic symmetric distance-regular graph with 18 nodes
    and 27 edges. It is Hamiltonian and can be represented in LCF notation as
    [5,7,-7,7,-7,-5]^3 [1]_.

    Returns
    -------
    G : networkx Graph
        Pappus graph

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/Pappus_graph
    """
    G = LCF_graph(18, [5, 7, -7, 7, -7, -5], 3)
    G.name = "Pappus Graph"
    return G


@_raise_on_directed
@nx._dispatchable(graphs=None, returns_graph=True)
def petersen_graph(create_using=None):
    """
    Returns the Petersen graph.

    The Peterson graph is a cubic, undirected graph with 10 nodes and 15 edges [1]_.
    Julius Petersen constructed the graph as the smallest counterexample
    against the claim that a connected bridgeless cubic graph
    has an edge colouring with three colours [2]_.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        Petersen graph

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/Petersen_graph
    .. [2] https://www.win.tue.nl/~aeb/drg/graphs/Petersen.html
    """
    G = nx.from_dict_of_lists(
        {
            0: [1, 4, 5],
            1: [0, 2, 6],
            2: [1, 3, 7],
            3: [2, 4, 8],
            4: [3, 0, 9],
            5: [0, 7, 8],
            6: [1, 8, 9],
            7: [2, 5, 9],
            8: [3, 5, 6],
            9: [4, 6, 7],
        },
        create_using=create_using,
    )
    G.name = "Petersen Graph"
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def sedgewick_maze_graph(create_using=None):
    """
    Return a small maze with a cycle.

    This is the maze used in Sedgewick, 3rd Edition, Part 5, Graph
    Algorithms, Chapter 18, e.g. Figure 18.2 and following [1]_.
    Nodes are numbered 0,..,7

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        Small maze with a cycle

    References
    ----------
    .. [1] Figure 18.2, Chapter 18, Graph Algorithms (3rd Ed), Sedgewick
    """
    G = empty_graph(0, create_using)
    G.add_nodes_from(range(8))
    G.add_edges_from([[0, 2], [0, 7], [0, 5]])
    G.add_edges_from([[1, 7], [2, 6]])
    G.add_edges_from([[3, 4], [3, 5]])
    G.add_edges_from([[4, 5], [4, 7], [4, 6]])
    G.name = "Sedgewick Maze"
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def tetrahedral_graph(create_using=None):
    """
    Returns the 3-regular Platonic Tetrahedral graph.

    Tetrahedral graph has 4 nodes and 6 edges. It is a
    special case of the complete graph, K4, and wheel graph, W4.
    It is one of the 5 platonic graphs [1]_.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        Tetrahedral Graph

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/Tetrahedron#Tetrahedral_graph

    """
    G = complete_graph(4, create_using)
    G.name = "Platonic Tetrahedral Graph"
    return G


@_raise_on_directed
@nx._dispatchable(graphs=None, returns_graph=True)
def truncated_cube_graph(create_using=None):
    """
    Returns the skeleton of the truncated cube.

    The truncated cube is an Archimedean solid with 14 regular
    faces (6 octagonal and 8 triangular), 36 edges and 24 nodes [1]_.
    The truncated cube is created by truncating (cutting off) the tips
    of the cube one third of the way into each edge [2]_.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        Skeleton of the truncated cube

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/Truncated_cube
    .. [2] https://www.coolmath.com/reference/polyhedra-truncated-cube

    """
    G = nx.from_dict_of_lists(
        {
            0: [1, 2, 4],
            1: [11, 14],
            2: [3, 4],
            3: [6, 8],
            4: [5],
            5: [16, 18],
            6: [7, 8],
            7: [10, 12],
            8: [9],
            9: [17, 20],
            10: [11, 12],
            11: [14],
            12: [13],
            13: [21, 22],
            14: [15],
            15: [19, 23],
            16: [17, 18],
            17: [20],
            18: [19],
            19: [23],
            20: [21],
            21: [22],
            22: [23],
        },
        create_using=create_using,
    )
    G.name = "Truncated Cube Graph"
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def truncated_tetrahedron_graph(create_using=None):
    """
    Returns the skeleton of the truncated Platonic tetrahedron.

    The truncated tetrahedron is an Archimedean solid with 4 regular hexagonal faces,
    4 equilateral triangle faces, 12 nodes and 18 edges. It can be constructed by truncating
    all 4 vertices of a regular tetrahedron at one third of the original edge length [1]_.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        Skeleton of the truncated tetrahedron

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/Truncated_tetrahedron

    """
    G = path_graph(12, create_using)
    G.add_edges_from([(0, 2), (0, 9), (1, 6), (3, 11), (4, 11), (5, 7), (8, 10)])
    G.name = "Truncated Tetrahedron Graph"
    return G


@_raise_on_directed
@nx._dispatchable(graphs=None, returns_graph=True)
def tutte_graph(create_using=None):
    """
    Returns the Tutte graph.

    The Tutte graph is a cubic polyhedral, non-Hamiltonian graph. It has
    46 nodes and 69 edges.
    It is a counterexample to Tait's conjecture that every 3-regular polyhedron
    has a Hamiltonian cycle.
    It can be realized geometrically from a tetrahedron by multiply truncating
    three of its vertices [1]_.

    Parameters
    ----------
    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    Returns
    -------
    G : networkx Graph
        Tutte graph

    References
    ----------
    .. [1] https://en.wikipedia.org/wiki/Tutte_graph
    """
    G = nx.from_dict_of_lists(
        {
            0: [1, 2, 3],
            1: [4, 26],
            2: [10, 11],
            3: [18, 19],
            4: [5, 33],
            5: [6, 29],
            6: [7, 27],
            7: [8, 14],
            8: [9, 38],
            9: [10, 37],
            10: [39],
            11: [12, 39],
            12: [13, 35],
            13: [14, 15],
            14: [34],
            15: [16, 22],
            16: [17, 44],
            17: [18, 43],
            18: [45],
            19: [20, 45],
            20: [21, 41],
            21: [22, 23],
            22: [40],
            23: [24, 27],
            24: [25, 32],
            25: [26, 31],
            26: [33],
            27: [28],
            28: [29, 32],
            29: [30],
            30: [31, 33],
            31: [32],
            34: [35, 38],
            35: [36],
            36: [37, 39],
            37: [38],
            40: [41, 44],
            41: [42],
            42: [43, 45],
            43: [44],
        },
        create_using=create_using,
    )
    G.name = "Tutte's Graph"
    return G
