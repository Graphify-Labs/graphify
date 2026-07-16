# Original author: D. Eppstein, UC Irvine, August 12, 2003.
# The original code at http://www.ics.uci.edu/~eppstein/PADS/ is public domain.
"""Functions for reading and writing graphs in the *graph6* format.

The *graph6* file format is suitable for small graphs or large dense
graphs. For large sparse graphs, use the *sparse6* format.

For more information, see the `graph6`_ homepage.

.. _graph6: http://users.cecs.anu.edu.au/~bdm/data/formats.html

"""

from itertools import islice

import networkx as nx
from networkx.exception import NetworkXError
from networkx.utils import not_implemented_for, open_file

__all__ = ["from_graph6_bytes", "read_graph6", "to_graph6_bytes", "write_graph6"]


def _generate_graph6_bytes(G, nodes, header):
    """Yield bytes in the graph6 encoding of a graph.

    `G` is an undirected simple graph. `nodes` is the list of nodes for
    which the node-induced subgraph will be encoded; if `nodes` is the
    list of all nodes in the graph, the entire graph will be
    encoded. `header` is a Boolean that specifies whether to generate
    the header ``b'>>graph6<<'`` before the remaining data.

    This function generates `bytes` objects in the following order:

    1. the header (if requested),
    2. the encoding of the number of nodes,
    3. each character, one-at-a-time, in the encoding of the requested
       node-induced subgraph,
    4. a newline character.

    This function raises :exc:`ValueError` if the graph is too large for
    the graph6 format (that is, greater than ``2 ** 36`` nodes).

    """
    n = len(G)
    if n >= 2**36:
        raise ValueError(
            "graph6 is only defined if number of nodes is less than 2 ** 36"
        )
    if header:
        yield b">>graph6<<"
    for d in n_to_data(n):
        yield str.encode(chr(d + 63))
    # This generates the same as `(v in G[u] for u, v in combinations(G, 2))`,
    # but in "column-major" order instead of "row-major" order.
    bits = (nodes[j] in G[nodes[i]] for j in range(1, n) for i in range(j))
    chunk = list(islice(bits, 6))
    while chunk:
        d = sum(b << 5 - i for i, b in enumerate(chunk))
        yield str.encode(chr(d + 63))
        chunk = list(islice(bits, 6))
    yield b"\n"


@nx._dispatchable(graphs=None, returns_graph=True)
def from_graph6_bytes(bytes_in):
    """Read a simple undirected graph in graph6 format from bytes.

    Parameters
    ----------
    bytes_in : bytes
       Data in graph6 format, without a trailing newline.

    Returns
    -------
    G : Graph

    Raises
    ------
    NetworkXError
        If bytes_in is unable to be parsed in graph6 format

    ValueError
        If any character ``c`` in bytes_in does not satisfy
        ``63 <= ord(c) < 127``.

    Examples
    --------
    >>> G = nx.from_graph6_bytes(b"A_")
    >>> sorted(G.edges())
    [(0, 1)]

    See Also
    --------
    read_graph6, write_graph6

    References
    ----------
    .. [1] Graph6 specification
           <http://users.cecs.anu.edu.au/~bdm/data/formats.html>

    """

    def bits():
        """Returns sequence of individual bits from 6-bit-per-value
        list of data values."""
        for d in data:
            for i in [5, 4, 3, 2, 1, 0]:
                yield (d >> i) & 1

    if bytes_in.startswith(b">>graph6<<"):
        bytes_in = bytes_in[10:]

    data = [c - 63 for c in bytes_in]
    if any(c > 63 for c in data):
        raise ValueError("each input character must be in range(63, 127)")

    n, data = data_to_n(data)
    nd = (n * (n - 1) // 2 + 5) // 6
    if len(data) != nd:
        raise NetworkXError(
            f"Expected {n * (n - 1) // 2} bits but got {len(data) * 6} in graph6"
        )

    G = nx.Graph()
    G.add_nodes_from(range(n))
    for (i, j), b in zip(((i, j) for j in range(1, n) for i in range(j)), bits()):
        if b:
            G.add_edge(i, j)

    return G


@not_implemented_for("directed")
@not_implemented_for("multigraph")
def to_graph6_bytes(G, nodes=None, header=True):
    """Convert a simple undirected graph to bytes in graph6 format.

    Parameters
    ----------
    G : Graph (undirected)

    nodes: list or iterable
       Nodes are labeled 0...n-1 in the order provided.  If None the ordering
       given by ``G.nodes()`` is used.

    header: bool
       If True add '>>graph6<<' bytes to head of data.

    Raises
    ------
    NetworkXNotImplemented
        If the graph is directed or is a multigraph.

    ValueError
        If the graph has at least ``2 ** 36`` nodes; the graph6 format
        is only defined for graphs of order less than ``2 ** 36``.

    Examples
    --------
    >>> nx.to_graph6_bytes(nx.path_graph(2))
    b'>>graph6<<A_\\n'

    See Also
    --------
    from_graph6_bytes, read_graph6, write_graph6_bytes

    Notes
    -----
    The returned bytes end with a newline character.

    The format does not support edge or node labels, parallel edges or
    self loops. If self loops are present they are silently ignored.

    References
    ----------
    .. [1] Graph6 specification
           <http://users.cecs.anu.edu.au/~bdm/data/formats.html>

    """
    if nodes is not None:
        G = G.subgraph(nodes)
    H = nx.convert_node_labels_to_integers(G)
    nodes = sorted(H.nodes())
    return b"".join(_generate_graph6_bytes(H, nodes, header))


@open_file(0, mode="rb")
@nx._dispatchable(graphs=None, returns_graph=True)
def read_graph6(path):
    """Read simple undirected graphs in graph6 format from path.

    Parameters
    ----------
    path : file or string
       File or filename to write.

    Returns
    -------
    G : Graph or list of Graphs
       If the file contains multiple lines then a list of graphs is returned

    Raises
    ------
    NetworkXError
        If the string is unable to be parsed in graph6 format

    Examples
    --------
    You can read a graph6 file by giving the path to the file::

        >>> import tempfile
        >>> with tempfile.NamedTemporaryFile(delete=False) as f:
        ...     _ = f.write(b">>graph6<<A_\\n")
        ...     _ = f.seek(0)
        ...     G = nx.read_graph6(f.name)
        >>> list(G.edges())
        [(0, 1)]

    You can also read a graph6 file by giving an open file-like object::

        >>> import tempfile
        >>> with tempfile.NamedTemporaryFile() as f:
        ...     _ = f.write(b">>graph6<<A_\\n")
        ...     _ = f.seek(0)
        ...     G = nx.read_graph6(f)
        >>> list(G.edges())
        [(0, 1)]

    See Also
    --------
    from_graph6_bytes, write_graph6

    References
    ----------
    .. [1] Graph6 specification
           <http://users.cecs.anu.edu.au/~bdm/data/formats.html>

    """
    glist = []
    for line in path:
        line = line.strip()
        if not len(line):
            continue
        glist.append(from_graph6_bytes(line))
    if len(glist) == 1:
        return glist[0]
    else:
        return glist


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@open_file(1, mode="wb")
def write_graph6(G, path, nodes=None, header=True):
    """Write a simple undirected graph to a path in graph6 format.

    Parameters
    ----------
    G : Graph (undirected)

    path : str
       The path naming the file to which to write the graph.

    nodes: list or iterable
       Nodes are labeled 0...n-1 in the order provided.  If None the ordering
       given by ``G.nodes()`` is used.

    header: bool
       If True add '>>graph6<<' string to head of data

    Raises
    ------
    NetworkXNotImplemented
        If the graph is directed or is a multigraph.

    ValueError
        If the graph has at least ``2 ** 36`` nodes; the graph6 format
        is only defined for graphs of order less than ``2 ** 36``.

    Examples
    --------
    You can write a graph6 file by giving the path to a file::

        >>> import tempfile
        >>> with tempfile.NamedTemporaryFile(delete=False) as f:
        ...     nx.write_graph6(nx.path_graph(2), f.name)
        ...     _ = f.seek(0)
        ...     print(f.read())
        b'>>graph6<<A_\\n'

    See Also
    --------
    from_graph6_bytes, read_graph6

    Notes
    -----
    The function writes a newline character after writing the encoding
    of the graph.

    The format does not support edge or node labels, parallel edges or
    self loops.  If self loops are present they are silently ignored.

    References
    ----------
    .. [1] Graph6 specification
           <http://users.cecs.anu.edu.au/~bdm/data/formats.html>

    """
    return write_graph6_file(G, path, nodes=nodes, header=header)


@not_implemented_for("directed")
@not_implemented_for("multigraph")
def write_graph6_file(G, f, nodes=None, header=True):
    """Write a simple undirected graph to a file-like object in graph6 format.

    Parameters
    ----------
    G : Graph (undirected)

    f : file-like object
       The file to write.

    nodes: list or iterable
       Nodes are labeled 0...n-1 in the order provided.  If None the ordering
       given by ``G.nodes()`` is used.

    header: bool
       If True add '>>graph6<<' string to head of data

    Raises
    ------
    NetworkXNotImplemented
        If the graph is directed or is a multigraph.

    ValueError
        If the graph has at least ``2 ** 36`` nodes; the graph6 format
        is only defined for graphs of order less than ``2 ** 36``.

    Examples
    --------
    You can write a graph6 file by giving an open file-like object::

        >>> import tempfile
        >>> with tempfile.NamedTemporaryFile() as f:
        ...     nx.write_graph6(nx.path_graph(2), f)
        ...     _ = f.seek(0)
        ...     print(f.read())
        b'>>graph6<<A_\\n'

    See Also
    --------
    from_graph6_bytes, read_graph6

    Notes
    -----
    The function writes a newline character after writing the encoding
    of the graph.

    The format does not support edge or node labels, parallel edges or
    self loops.  If self loops are present they are silently ignored.

    References
    ----------
    .. [1] Graph6 specification
           <http://users.cecs.anu.edu.au/~bdm/data/formats.html>

    """
    if nodes is not None:
        G = G.subgraph(nodes)
    H = nx.convert_node_labels_to_integers(G)
    nodes = sorted(H.nodes())
    for b in _generate_graph6_bytes(H, nodes, header):
        f.write(b)


def data_to_n(data):
    """Read initial one-, four- or eight-unit value from graph6
    integer sequence.

    Return (value, rest of seq.)"""
    if data[0] <= 62:
        return data[0], data[1:]
    if data[1] <= 62:
        return (data[1] << 12) + (data[2] << 6) + data[3], data[4:]
    return (
        (data[2] << 30)
        + (data[3] << 24)
        + (data[4] << 18)
        + (data[5] << 12)
        + (data[6] << 6)
        + data[7],
        data[8:],
    )


def n_to_data(n):
    """Convert an integer to one-, four- or eight-unit graph6 sequence.

    This function is undefined if `n` is not in ``range(2 ** 36)``.

    """
    if n <= 62:
        return [n]
    elif n <= 258047:
        return [63, (n >> 12) & 0x3F, (n >> 6) & 0x3F, n & 0x3F]
    else:  # if n <= 68719476735:
        return [
            63,
            63,
            (n >> 30) & 0x3F,
            (n >> 24) & 0x3F,
            (n >> 18) & 0x3F,
            (n >> 12) & 0x3F,
            (n >> 6) & 0x3F,
            n & 0x3F,
        ]
