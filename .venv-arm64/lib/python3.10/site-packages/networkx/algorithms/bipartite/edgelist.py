"""
********************
Bipartite Edge Lists
********************
Read and write NetworkX graphs as bipartite edge lists.

Format
------
You can read or write three formats of edge lists with these functions.

Node pairs with no data::

 1 2

Python dictionary as data::

 1 2 {'weight':7, 'color':'green'}

Arbitrary data::

 1 2 7 green

For each edge (u, v) the node u is assigned to part 0 and the node v to part 1.
"""

__all__ = ["generate_edgelist", "write_edgelist", "parse_edgelist", "read_edgelist"]

import networkx as nx
from networkx.utils import not_implemented_for, open_file


@open_file(1, mode="wb")
def write_edgelist(G, path, comments="#", delimiter=" ", data=True, encoding="utf-8"):
    """Write a bipartite graph as a list of edges.

    Parameters
    ----------
    G : Graph
       A NetworkX bipartite graph
    path : file or string
       File or filename to write. If a file is provided, it must be
       opened in 'wb' mode. Filenames ending in .gz or .bz2 will be compressed.
    comments : string, optional
       The character used to indicate the start of a comment
    delimiter : string, optional
       The string used to separate values.  The default is whitespace.
    data : bool or list, optional
       If False write no edge data.
       If True write a string representation of the edge data dictionary..
       If a list (or other iterable) is provided, write the  keys specified
       in the list.
    encoding: string, optional
       Specify which encoding to use when writing file.

    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> G.add_nodes_from([0, 2], bipartite=0)
    >>> G.add_nodes_from([1, 3], bipartite=1)
    >>> nx.write_edgelist(G, "test.edgelist")
    >>> fh = open("test.edgelist", "wb")
    >>> nx.write_edgelist(G, fh)
    >>> nx.write_edgelist(G, "test.edgelist.gz")
    >>> nx.write_edgelist(G, "test.edgelist.gz", data=False)

    >>> G = nx.Graph()
    >>> G.add_edge(1, 2, weight=7, color="red")
    >>> nx.write_edgelist(G, "test.edgelist", data=False)
    >>> nx.write_edgelist(G, "test.edgelist", data=["color"])
    >>> nx.write_edgelist(G, "test.edgelist", data=["color", "weight"])

    See Also
    --------
    write_edgelist
    generate_edgelist
    """
    for line in generate_edgelist(G, delimiter, data):
        line += "\n"
        path.write(line.encode(encoding))


@not_implemented_for("directed")
def generate_edgelist(G, delimiter=" ", data=True):
    """Generate a single line of the bipartite graph G in edge list format.

    Parameters
    ----------
    G : NetworkX graph
       The graph is assumed to have node attribute `part` set to 0,1 representing
       the two graph parts

    delimiter : string, optional
       Separator for node labels

    data : bool or list of keys
       If False generate no edge data.  If True use a dictionary
       representation of edge data.  If a list of keys use a list of data
       values corresponding to the keys.

    Returns
    -------
    lines : string
        Lines of data in adjlist format.

    Examples
    --------
    >>> from networkx.algorithms import bipartite
    >>> G = nx.path_graph(4)
    >>> G.add_nodes_from([0, 2], bipartite=0)
    >>> G.add_nodes_from([1, 3], bipartite=1)
    >>> G[1][2]["weight"] = 3
    >>> G[2][3]["capacity"] = 12
    >>> for line in bipartite.generate_edgelist(G, data=False):
    ...     print(line)
    0 1
    2 1
    2 3

    >>> for line in bipartite.generate_edgelist(G):
    ...     print(line)
    0 1 {}
    2 1 {'weight': 3}
    2 3 {'capacity': 12}

    >>> for line in bipartite.generate_edgelist(G, data=["weight"]):
    ...     print(line)
    0 1
    2 1 3
    2 3
    """
    try:
        part0 = [n for n, d in G.nodes.items() if d["bipartite"] == 0]
    except BaseException as err:
        raise AttributeError("Missing node attribute `bipartite`") from err
    if data is True or data is False:
        for n in part0:
            for edge in G.edges(n, data=data):
                yield delimiter.join(map(str, edge))
    else:
        for n in part0:
            for u, v, d in G.edges(n, data=True):
                edge = [u, v]
                try:
                    edge.extend(d[k] for k in data)
                except KeyError:
                    pass  # missing data for this edge, should warn?
                yield delimiter.join(map(str, edge))


@nx._dispatchable(name="bipartite_parse_edgelist", graphs=None, returns_graph=True)
def parse_edgelist(
    lines, comments="#", delimiter=None, create_using=None, nodetype=None, data=True
):
    """Parse lines of an edge list representation of a bipartite graph.

    Parameters
    ----------
    lines : list or iterator of strings
        Input data in edgelist format
    comments : string, optional
       Marker for comment lines
    delimiter : string, optional
       Separator for node labels
    create_using: NetworkX graph container, optional
       Use given NetworkX graph for holding nodes or edges.
    nodetype : Python type, optional
       Convert nodes to this type.
    data : bool or list of (label,type) tuples
       If False generate no edge data or if True use a dictionary
       representation of edge data or a list tuples specifying dictionary
       key names and types for edge data.

    Returns
    -------
    G: NetworkX Graph
        The bipartite graph corresponding to lines

    Examples
    --------
    Edgelist with no data:

    >>> from networkx.algorithms import bipartite
    >>> lines = ["1 2", "2 3", "3 4"]
    >>> G = bipartite.parse_edgelist(lines, nodetype=int)
    >>> sorted(G.nodes())
    [1, 2, 3, 4]
    >>> sorted(G.nodes(data=True))
    [(1, {'bipartite': 0}), (2, {'bipartite': 0}), (3, {'bipartite': 0}), (4, {'bipartite': 1})]
    >>> sorted(G.edges())
    [(1, 2), (2, 3), (3, 4)]

    Edgelist with data in Python dictionary representation:

    >>> lines = ["1 2 {'weight':3}", "2 3 {'weight':27}", "3 4 {'weight':3.0}"]
    >>> G = bipartite.parse_edgelist(lines, nodetype=int)
    >>> sorted(G.nodes())
    [1, 2, 3, 4]
    >>> sorted(G.edges(data=True))
    [(1, 2, {'weight': 3}), (2, 3, {'weight': 27}), (3, 4, {'weight': 3.0})]

    Edgelist with data in a list:

    >>> lines = ["1 2 3", "2 3 27", "3 4 3.0"]
    >>> G = bipartite.parse_edgelist(lines, nodetype=int, data=(("weight", float),))
    >>> sorted(G.nodes())
    [1, 2, 3, 4]
    >>> sorted(G.edges(data=True))
    [(1, 2, {'weight': 3.0}), (2, 3, {'weight': 27.0}), (3, 4, {'weight': 3.0})]

    See Also
    --------
    """
    from ast import literal_eval

    G = nx.empty_graph(0, create_using)
    for line in lines:
        p = line.find(comments)
        if p >= 0:
            line = line[:p]
        if not len(line):
            continue
        # split line, should have 2 or more
        s = line.rstrip("\n").split(delimiter)
        if len(s) < 2:
            continue
        u = s.pop(0)
        v = s.pop(0)
        d = s
        if nodetype is not None:
            try:
                u = nodetype(u)
                v = nodetype(v)
            except BaseException as err:
                raise TypeError(
                    f"Failed to convert nodes {u},{v} to type {nodetype}."
                ) from err

        if len(d) == 0 or data is False:
            # no data or data type specified
            edgedata = {}
        elif data is True:
            # no edge types specified
            try:  # try to evaluate as dictionary
                edgedata = dict(literal_eval(" ".join(d)))
            except BaseException as err:
                raise TypeError(
                    f"Failed to convert edge data ({d}) to dictionary."
                ) from err
        else:
            # convert edge data to dictionary with specified keys and type
            if len(d) != len(data):
                raise IndexError(
                    f"Edge data {d} and data_keys {data} are not the same length"
                )
            edgedata = {}
            for (edge_key, edge_type), edge_value in zip(data, d):
                try:
                    edge_value = edge_type(edge_value)
                except BaseException as err:
                    raise TypeError(
                        f"Failed to convert {edge_key} data "
                        f"{edge_value} to type {edge_type}."
                    ) from err
                edgedata.update({edge_key: edge_value})
        G.add_node(u, bipartite=0)
        G.add_node(v, bipartite=1)
        G.add_edge(u, v, **edgedata)
    return G


@open_file(0, mode="rb")
@nx._dispatchable(name="bipartite_read_edgelist", graphs=None, returns_graph=True)
def read_edgelist(
    path,
    comments="#",
    delimiter=None,
    create_using=None,
    nodetype=None,
    data=True,
    edgetype=None,
    encoding="utf-8",
):
    """Read a bipartite graph from a list of edges.

    Parameters
    ----------
    path : file or string
       File or filename to read. If a file is provided, it must be
       opened in 'rb' mode.
       Filenames ending in .gz or .bz2 will be uncompressed.
    comments : string, optional
       The character used to indicate the start of a comment.
    delimiter : string, optional
       The string used to separate values.  The default is whitespace.
    create_using : Graph container, optional,
       Use specified container to build graph.  The default is networkx.Graph,
       an undirected graph.
    nodetype : int, float, str, Python type, optional
       Convert node data from strings to specified type
    data : bool or list of (label,type) tuples
       Tuples specifying dictionary key names and types for edge data
    edgetype : int, float, str, Python type, optional OBSOLETE
       Convert edge data from strings to specified type and use as 'weight'
    encoding: string, optional
       Specify which encoding to use when reading file.

    Returns
    -------
    G : graph
       A networkx Graph or other type specified with create_using

    Examples
    --------
    >>> from networkx.algorithms import bipartite
    >>> G = nx.path_graph(4)
    >>> G.add_nodes_from([0, 2], bipartite=0)
    >>> G.add_nodes_from([1, 3], bipartite=1)
    >>> bipartite.write_edgelist(G, "test.edgelist")
    >>> G = bipartite.read_edgelist("test.edgelist")

    >>> fh = open("test.edgelist", "rb")
    >>> G = bipartite.read_edgelist(fh)
    >>> fh.close()

    >>> G = bipartite.read_edgelist("test.edgelist", nodetype=int)

    Edgelist with data in a list:

    >>> textline = "1 2 3"
    >>> fh = open("test.edgelist", "w")
    >>> d = fh.write(textline)
    >>> fh.close()
    >>> G = bipartite.read_edgelist(
    ...     "test.edgelist", nodetype=int, data=(("weight", float),)
    ... )
    >>> list(G)
    [1, 2]
    >>> list(G.edges(data=True))
    [(1, 2, {'weight': 3.0})]

    See parse_edgelist() for more examples of formatting.

    See Also
    --------
    parse_edgelist

    Notes
    -----
    Since nodes must be hashable, the function nodetype must return hashable
    types (e.g. int, float, str, frozenset - or tuples of those, etc.)
    """
    lines = (line.decode(encoding) for line in path)
    return parse_edgelist(
        lines,
        comments=comments,
        delimiter=delimiter,
        create_using=create_using,
        nodetype=nodetype,
        data=data,
    )
