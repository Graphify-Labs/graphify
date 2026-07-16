"""
*************************
Multi-line Adjacency List
*************************
Read and write NetworkX graphs as multi-line adjacency lists.

The multi-line adjacency list format is useful for graphs with
nodes that can be meaningfully represented as strings.  With this format
simple edge data can be stored but node or graph data is not.

Format
------
The first label in a line is the source node label followed by the node degree
d.  The next d lines are target node labels and optional edge data.
That pattern repeats for all nodes in the graph.

The graph with edges a-b, a-c, d-e can be represented as the following
adjacency list (anything following the # in a line is a comment)::

     # example.multiline-adjlist
     a 2
     b
     c
     d 1
     e
"""

__all__ = [
    "generate_multiline_adjlist",
    "write_multiline_adjlist",
    "parse_multiline_adjlist",
    "read_multiline_adjlist",
]

import networkx as nx
from networkx.utils import open_file


def generate_multiline_adjlist(G, delimiter=" "):
    """Generate a single line of the graph G in multiline adjacency list format.

    Parameters
    ----------
    G : NetworkX graph

    delimiter : string, optional
       Separator for node labels

    Returns
    -------
    lines : string
        Lines of data in multiline adjlist format.

    Examples
    --------
    >>> G = nx.lollipop_graph(4, 3)
    >>> for line in nx.generate_multiline_adjlist(G):
    ...     print(line)
    0 3
    1 {}
    2 {}
    3 {}
    1 2
    2 {}
    3 {}
    2 1
    3 {}
    3 1
    4 {}
    4 1
    5 {}
    5 1
    6 {}
    6 0

    See Also
    --------
    write_multiline_adjlist, read_multiline_adjlist
    """
    if G.is_directed():
        if G.is_multigraph():
            for s, nbrs in G.adjacency():
                nbr_edges = [
                    (u, data)
                    for u, datadict in nbrs.items()
                    for key, data in datadict.items()
                ]
                deg = len(nbr_edges)
                yield str(s) + delimiter + str(deg)
                for u, d in nbr_edges:
                    if d is None:
                        yield str(u)
                    else:
                        yield str(u) + delimiter + str(d)
        else:  # directed single edges
            for s, nbrs in G.adjacency():
                deg = len(nbrs)
                yield str(s) + delimiter + str(deg)
                for u, d in nbrs.items():
                    if d is None:
                        yield str(u)
                    else:
                        yield str(u) + delimiter + str(d)
    else:  # undirected
        if G.is_multigraph():
            seen = set()  # helper dict used to avoid duplicate edges
            for s, nbrs in G.adjacency():
                nbr_edges = [
                    (u, data)
                    for u, datadict in nbrs.items()
                    if u not in seen
                    for key, data in datadict.items()
                ]
                deg = len(nbr_edges)
                yield str(s) + delimiter + str(deg)
                for u, d in nbr_edges:
                    if d is None:
                        yield str(u)
                    else:
                        yield str(u) + delimiter + str(d)
                seen.add(s)
        else:  # undirected single edges
            seen = set()  # helper dict used to avoid duplicate edges
            for s, nbrs in G.adjacency():
                nbr_edges = [(u, d) for u, d in nbrs.items() if u not in seen]
                deg = len(nbr_edges)
                yield str(s) + delimiter + str(deg)
                for u, d in nbr_edges:
                    if d is None:
                        yield str(u)
                    else:
                        yield str(u) + delimiter + str(d)
                seen.add(s)


@open_file(1, mode="wb")
def write_multiline_adjlist(G, path, delimiter=" ", comments="#", encoding="utf-8"):
    """Write the graph G in multiline adjacency list format to path

    Parameters
    ----------
    G : NetworkX graph

    path : string or file
       Filename or file handle to write to.
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
    >>> nx.write_multiline_adjlist(G, "test.adjlist")

    The path can be a file handle or a string with the name of the file. If a
    file handle is provided, it has to be opened in 'wb' mode.

    >>> fh = open("test.adjlist", "wb")
    >>> nx.write_multiline_adjlist(G, fh)

    Filenames ending in .gz or .bz2 will be compressed.

    >>> nx.write_multiline_adjlist(G, "test.adjlist.gz")

    See Also
    --------
    read_multiline_adjlist
    """
    import sys
    import time

    pargs = comments + " ".join(sys.argv)
    header = (
        f"{pargs}\n"
        + comments
        + f" GMT {time.asctime(time.gmtime())}\n"
        + comments
        + f" {G.name}\n"
    )
    path.write(header.encode(encoding))

    for multiline in generate_multiline_adjlist(G, delimiter):
        multiline += "\n"
        path.write(multiline.encode(encoding))


@nx._dispatchable(graphs=None, returns_graph=True)
def parse_multiline_adjlist(
    lines, comments="#", delimiter=None, create_using=None, nodetype=None, edgetype=None
):
    """Parse lines of a multiline adjacency list representation of a graph.

    Parameters
    ----------
    lines : list or iterator of strings
        Input data in multiline adjlist format

    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    nodetype : Python type, optional
       Convert nodes to this type.

    edgetype : Python type, optional
       Convert edges to this type.

    comments : string, optional
       Marker for comment lines

    delimiter : string, optional
       Separator for node labels.  The default is whitespace.

    Returns
    -------
    G: NetworkX graph
        The graph corresponding to the lines in multiline adjacency list format.

    Examples
    --------
    >>> lines = [
    ...     "1 2",
    ...     "2 {'weight':3, 'name': 'Frodo'}",
    ...     "3 {}",
    ...     "2 1",
    ...     "5 {'weight':6, 'name': 'Saruman'}",
    ... ]
    >>> G = nx.parse_multiline_adjlist(iter(lines), nodetype=int)
    >>> list(G)
    [1, 2, 3, 5]

    """
    from ast import literal_eval

    G = nx.empty_graph(0, create_using)
    for line in lines:
        p = line.find(comments)
        if p >= 0:
            line = line[:p]
        if not line:
            continue
        try:
            (u, deg) = line.rstrip("\n").split(delimiter)
            deg = int(deg)
        except BaseException as err:
            raise TypeError(f"Failed to read node and degree on line ({line})") from err
        if nodetype is not None:
            try:
                u = nodetype(u)
            except BaseException as err:
                raise TypeError(
                    f"Failed to convert node ({u}) to type {nodetype}"
                ) from err
        G.add_node(u)
        for i in range(deg):
            while True:
                try:
                    line = next(lines)
                except StopIteration as err:
                    msg = f"Failed to find neighbor for node ({u})"
                    raise TypeError(msg) from err
                p = line.find(comments)
                if p >= 0:
                    line = line[:p]
                if line:
                    break
            vlist = line.rstrip("\n").split(delimiter)
            numb = len(vlist)
            if numb < 1:
                continue  # isolated node
            v = vlist.pop(0)
            data = "".join(vlist)
            if nodetype is not None:
                try:
                    v = nodetype(v)
                except BaseException as err:
                    raise TypeError(
                        f"Failed to convert node ({v}) to type {nodetype}"
                    ) from err
            if edgetype is not None:
                try:
                    edgedata = {"weight": edgetype(data)}
                except BaseException as err:
                    raise TypeError(
                        f"Failed to convert edge data ({data}) to type {edgetype}"
                    ) from err
            else:
                try:  # try to evaluate
                    edgedata = literal_eval(data)
                except:
                    edgedata = {}
            G.add_edge(u, v, **edgedata)

    return G


@open_file(0, mode="rb")
@nx._dispatchable(graphs=None, returns_graph=True)
def read_multiline_adjlist(
    path,
    comments="#",
    delimiter=None,
    create_using=None,
    nodetype=None,
    edgetype=None,
    encoding="utf-8",
):
    """Read graph in multi-line adjacency list format from path.

    Parameters
    ----------
    path : string or file
       Filename or file handle to read.
       Filenames ending in .gz or .bz2 will be uncompressed.

    create_using : NetworkX graph constructor, optional (default=nx.Graph)
       Graph type to create. If graph instance, then cleared before populated.

    nodetype : Python type, optional
       Convert nodes to this type.

    edgetype : Python type, optional
       Convert edge data to this type.

    comments : string, optional
       Marker for comment lines

    delimiter : string, optional
       Separator for node labels.  The default is whitespace.

    Returns
    -------
    G: NetworkX graph

    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> nx.write_multiline_adjlist(G, "test.adjlist")
    >>> G = nx.read_multiline_adjlist("test.adjlist")

    The path can be a file or a string with the name of the file. If a
    file s provided, it has to be opened in 'rb' mode.

    >>> fh = open("test.adjlist", "rb")
    >>> G = nx.read_multiline_adjlist(fh)

    Filenames ending in .gz or .bz2 will be compressed.

    >>> nx.write_multiline_adjlist(G, "test.adjlist.gz")
    >>> G = nx.read_multiline_adjlist("test.adjlist.gz")

    The optional nodetype is a function to convert node strings to nodetype.

    For example

    >>> G = nx.read_multiline_adjlist("test.adjlist", nodetype=int)

    will attempt to convert all nodes to integer type.

    The optional edgetype is a function to convert edge data strings to
    edgetype.

    >>> G = nx.read_multiline_adjlist("test.adjlist")

    The optional create_using parameter is a NetworkX graph container.
    The default is Graph(), an undirected graph.  To read the data as
    a directed graph use

    >>> G = nx.read_multiline_adjlist("test.adjlist", create_using=nx.DiGraph)

    Notes
    -----
    This format does not store graph, node, or edge data.

    See Also
    --------
    write_multiline_adjlist
    """
    lines = (line.decode(encoding) for line in path)
    return parse_multiline_adjlist(
        lines,
        comments=comments,
        delimiter=delimiter,
        create_using=create_using,
        nodetype=nodetype,
        edgetype=edgetype,
    )
