"""
**************
Adjacency List
**************
Read and write NetworkX graphs as adjacency lists.

Adjacency list format is useful for graphs without data associated
with nodes or edges and for nodes that can be meaningfully represented
as strings.

Format
------
The adjacency list format consists of lines with node labels.  The
first label in a line is the source node.  Further labels in the line
are considered target nodes and are added to the graph along with an edge
between the source node and target node.

The graph with edges a-b, a-c, d-e can be represented as the following
adjacency list (anything following the # in a line is a comment)::

     a b c # source target target
     d e
"""

__all__ = ["generate_adjlist", "write_adjlist", "parse_adjlist", "read_adjlist"]

import networkx as nx
from networkx.utils import open_file


def generate_adjlist(G, delimiter=" "):
    """Generate a single line of the graph G in adjacency list format.

    Parameters
    ----------
    G : NetworkX graph

    delimiter : string, optional
       Separator for node labels

    Returns
    -------
    lines : string
        Lines of data in adjlist format.

    Examples
    --------
    >>> G = nx.lollipop_graph(4, 3)
    >>> for line in nx.generate_adjlist(G):
    ...     print(line)
    0 1 2 3
    1 2 3
    2 3
    3 4
    4 5
    5 6
    6

    See Also
    --------
    write_adjlist, read_adjlist

    Notes
    -----
    The default `delimiter=" "` will result in unexpected results if node names contain
    whitespace characters. To avoid this problem, specify an alternate delimiter when spaces are
    valid in node names.

    NB: This option is not available for data that isn't user-generated.

    """
    directed = G.is_directed()
    seen = set()
    for s, nbrs in G.adjacency():
        line = str(s) + delimiter
        for t, data in nbrs.items():
            if not directed and t in seen:
                continue
            if G.is_multigraph():
                for d in data.values():
                    line += str(t) + delimiter
            else:
                line += str(t) + delimiter
        if not directed:
            seen.add(s)
        yield line[: -len(delimiter)]


@open_file(1, mode="wb")
def write_adjlist(G, path, comments="#", delimiter=" ", encoding="utf-8"):
    """Write graph G in single-line adjacency-list format to path.


    Parameters
    ----------
    G : NetworkX graph

    path : string or file
       Filename or file handle for data output.
       Filenames ending in .gz or .bz2 will be compressed.

    comments : string, optional
       Marker for comment lines

    delimiter : string, optional
       Separator for node labels

    encoding : string, optional
       Text encoding.

    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> nx.write_adjlist(G, "test.adjlist")

    The path can be a filehandle or a string with the name of the file. If a
    filehandle is provided, it has to be opened in 'wb' mode.

    >>> fh = open("test.adjlist", "wb")
    >>> nx.write_adjlist(G, fh)

    Notes
    -----
    The default `delimiter=" "` will result in unexpected results if node names contain
    whitespace characters. To avoid this problem, specify an alternate delimiter when spaces are
    valid in node names.
    NB: This option is not available for data that isn't user-generated.

    This format does not store graph, node, or edge data.

    See Also
    --------
    read_adjlist, generate_adjlist
    """
    import sys
    import time

    pargs = comments + " ".join(sys.argv) + "\n"
    header = (
        pargs
        + comments
        + f" GMT {time.asctime(time.gmtime())}\n"
        + comments
        + f" {G.name}\n"
    )
    path.write(header.encode(encoding))

    for line in generate_adjlist(G, delimiter):
        line += "\n"
        path.write(line.encode(encoding))


@nx._dispatchable(graphs=None, returns_graph=True)
def parse_adjlist(
    lines, comments="#", delimiter=None, create_using=None, nodetype=None
):
    """Parse lines of a graph adjacency list representation.

    Parameters
    ----------
    lines : list or iterator of strings
        Input data in adjlist format

    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    nodetype : Python type, optional
       Convert nodes to this type.

    comments : string, optional
       Marker for comment lines

    delimiter : string, optional
       Separator for node labels.  The default is whitespace.

    Returns
    -------
    G: NetworkX graph
        The graph corresponding to the lines in adjacency list format.

    Examples
    --------
    >>> lines = ["1 2 5", "2 3 4", "3 5", "4", "5"]
    >>> G = nx.parse_adjlist(lines, nodetype=int)
    >>> nodes = [1, 2, 3, 4, 5]
    >>> all(node in G for node in nodes)
    True
    >>> edges = [(1, 2), (1, 5), (2, 3), (2, 4), (3, 5)]
    >>> all((u, v) in G.edges() or (v, u) in G.edges() for (u, v) in edges)
    True

    See Also
    --------
    read_adjlist

    """
    G = nx.empty_graph(0, create_using)
    for line in lines:
        p = line.find(comments)
        if p >= 0:
            line = line[:p]
        if not len(line):
            continue
        vlist = line.rstrip("\n").split(delimiter)
        u = vlist.pop(0)
        # convert types
        if nodetype is not None:
            try:
                u = nodetype(u)
            except BaseException as err:
                raise TypeError(
                    f"Failed to convert node ({u}) to type {nodetype}"
                ) from err
        G.add_node(u)
        if nodetype is not None:
            try:
                vlist = list(map(nodetype, vlist))
            except BaseException as err:
                raise TypeError(
                    f"Failed to convert nodes ({','.join(vlist)}) to type {nodetype}"
                ) from err
        G.add_edges_from([(u, v) for v in vlist])
    return G


@open_file(0, mode="rb")
@nx._dispatchable(graphs=None, returns_graph=True)
def read_adjlist(
    path,
    comments="#",
    delimiter=None,
    create_using=None,
    nodetype=None,
    encoding="utf-8",
):
    """Read graph in adjacency list format from path.

    Parameters
    ----------
    path : string or file
       Filename or file handle to read.
       Filenames ending in .gz or .bz2 will be uncompressed.

    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    nodetype : Python type, optional
       Convert nodes to this type.

    comments : string, optional
       Marker for comment lines

    delimiter : string, optional
       Separator for node labels.  The default is whitespace.

    Returns
    -------
    G: NetworkX graph
        The graph corresponding to the lines in adjacency list format.

    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> nx.write_adjlist(G, "test.adjlist")
    >>> G = nx.read_adjlist("test.adjlist")

    The path can be a filehandle or a string with the name of the file. If a
    filehandle is provided, it has to be opened in 'rb' mode.

    >>> fh = open("test.adjlist", "rb")
    >>> G = nx.read_adjlist(fh)

    Filenames ending in .gz or .bz2 will be compressed.

    >>> nx.write_adjlist(G, "test.adjlist.gz")
    >>> G = nx.read_adjlist("test.adjlist.gz")

    The optional nodetype is a function to convert node strings to nodetype.

    For example

    >>> G = nx.read_adjlist("test.adjlist", nodetype=int)

    will attempt to convert all nodes to integer type.

    Since nodes must be hashable, the function nodetype must return hashable
    types (e.g. int, float, str, frozenset - or tuples of those, etc.)

    The optional create_using parameter indicates the type of NetworkX graph
    created.  The default is `nx.Graph`, an undirected graph.
    To read the data as a directed graph use

    >>> G = nx.read_adjlist("test.adjlist", create_using=nx.DiGraph)

    Notes
    -----
    This format does not store graph or node data.

    See Also
    --------
    write_adjlist
    """
    lines = (line.decode(encoding) for line in path)
    return parse_adjlist(
        lines,
        comments=comments,
        delimiter=delimiter,
        create_using=create_using,
        nodetype=nodetype,
    )
