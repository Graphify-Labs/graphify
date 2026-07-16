# Original author: D. Eppstein, UC Irvine, August 12, 2003.
# The original code at https://www.ics.uci.edu/~eppstein/PADS/ is public domain.
"""Functions for reading and writing graphs in the *sparse6* format.

The *sparse6* file format is a space-efficient format for large sparse
graphs. For small graphs or large dense graphs, use the *graph6* file
format.

For more information, see the `sparse6`_ homepage.

.. _sparse6: https://users.cecs.anu.edu.au/~bdm/data/formats.html

"""

import networkx as nx
from networkx.exception import NetworkXError
from networkx.readwrite.graph6 import data_to_n, n_to_data
from networkx.utils import not_implemented_for, open_file

__all__ = ["from_sparse6_bytes", "read_sparse6", "to_sparse6_bytes", "write_sparse6"]


def _generate_sparse6_bytes(G, nodes, header):
    """Yield bytes in the sparse6 encoding of a graph.

    `G` is an undirected simple graph. `nodes` is the list of nodes for
    which the node-induced subgraph will be encoded; if `nodes` is the
    list of all nodes in the graph, the entire graph will be
    encoded. `header` is a Boolean that specifies whether to generate
    the header ``b'>>sparse6<<'`` before the remaining data.

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
            "sparse6 is only defined if number of nodes is less than 2 ** 36"
        )
    if header:
        yield b">>sparse6<<"
    yield b":"
    for d in n_to_data(n):
        yield str.encode(chr(d + 63))

    k = 1
    while 1 << k < n:
        k += 1

    def enc(x):
        """Big endian k-bit encoding of x"""
        return [1 if (x & 1 << (k - 1 - i)) else 0 for i in range(k)]

    edges = sorted((max(u, v), min(u, v)) for u, v in G.edges())
    bits = []
    curv = 0
    for v, u in edges:
        if v == curv:  # current vertex edge
            bits.append(0)
            bits.extend(enc(u))
        elif v == curv + 1:  # next vertex edge
            curv += 1
            bits.append(1)
            bits.extend(enc(u))
        else:  # skip to vertex v and then add edge to u
            curv = v
            bits.append(1)
            bits.extend(enc(v))
            bits.append(0)
            bits.extend(enc(u))
    if k < 6 and n == (1 << k) and ((-len(bits)) % 6) >= k and curv < (n - 1):
        # Padding special case: small k, n=2^k,
        # more than k bits of padding needed,
        # current vertex is not (n-1) --
        # appending 1111... would add a loop on (n-1)
        bits.append(0)
        bits.extend([1] * ((-len(bits)) % 6))
    else:
        bits.extend([1] * ((-len(bits)) % 6))

    data = [
        (bits[i + 0] << 5)
        + (bits[i + 1] << 4)
        + (bits[i + 2] << 3)
        + (bits[i + 3] << 2)
        + (bits[i + 4] << 1)
        + (bits[i + 5] << 0)
        for i in range(0, len(bits), 6)
    ]

    for d in data:
        yield str.encode(chr(d + 63))
    yield b"\n"


@nx._dispatchable(graphs=None, returns_graph=True)
def from_sparse6_bytes(string):
    """Read an undirected graph in sparse6 format from string.

    Parameters
    ----------
    string : string
       Data in sparse6 format

    Returns
    -------
    G : Graph

    Raises
    ------
    NetworkXError
        If the string is unable to be parsed in sparse6 format

    Examples
    --------
    >>> G = nx.from_sparse6_bytes(b":A_")
    >>> sorted(G.edges())
    [(0, 1), (0, 1), (0, 1)]

    See Also
    --------
    read_sparse6, write_sparse6

    References
    ----------
    .. [1] Sparse6 specification
           <https://users.cecs.anu.edu.au/~bdm/data/formats.html>

    """
    if string.startswith(b">>sparse6<<"):
        string = string[11:]
    if not string.startswith(b":"):
        raise NetworkXError("Expected leading colon in sparse6")

    chars = [c - 63 for c in string[1:]]
    n, data = data_to_n(chars)
    k = 1
    while 1 << k < n:
        k += 1

    def parseData():
        """Returns stream of pairs b[i], x[i] for sparse6 format."""
        chunks = iter(data)
        d = None  # partial data word
        dLen = 0  # how many unparsed bits are left in d

        while 1:
            if dLen < 1:
                try:
                    d = next(chunks)
                except StopIteration:
                    return
                dLen = 6
            dLen -= 1
            b = (d >> dLen) & 1  # grab top remaining bit

            x = d & ((1 << dLen) - 1)  # partially built up value of x
            xLen = dLen  # how many bits included so far in x
            while xLen < k:  # now grab full chunks until we have enough
                try:
                    d = next(chunks)
                except StopIteration:
                    return
                dLen = 6
                x = (x << 6) + d
                xLen += 6
            x = x >> (xLen - k)  # shift back the extra bits
            dLen = xLen - k
            yield b, x

    v = 0

    G = nx.MultiGraph()
    G.add_nodes_from(range(n))

    multigraph = False
    for b, x in parseData():
        if b == 1:
            v += 1
        # padding with ones can cause overlarge number here
        if x >= n or v >= n:
            break
        elif x > v:
            v = x
        else:
            if G.has_edge(x, v):
                multigraph = True
            G.add_edge(x, v)
    if not multigraph:
        G = nx.Graph(G)
    return G


def to_sparse6_bytes(G, nodes=None, header=True):
    """Convert an undirected graph to bytes in sparse6 format.

    Parameters
    ----------
    G : Graph (undirected)

    nodes: list or iterable
       Nodes are labeled 0...n-1 in the order provided.  If None the ordering
       given by ``G.nodes()`` is used.

    header: bool
       If True add '>>sparse6<<' bytes to head of data.

    Raises
    ------
    NetworkXNotImplemented
        If the graph is directed.

    ValueError
        If the graph has at least ``2 ** 36`` nodes; the sparse6 format
        is only defined for graphs of order less than ``2 ** 36``.

    Examples
    --------
    >>> nx.to_sparse6_bytes(nx.path_graph(2))
    b'>>sparse6<<:An\\n'

    See Also
    --------
    to_sparse6_bytes, read_sparse6, write_sparse6_bytes

    Notes
    -----
    The returned bytes end with a newline character.

    The format does not support edge or node labels.

    References
    ----------
    .. [1] Graph6 specification
           <https://users.cecs.anu.edu.au/~bdm/data/formats.html>

    """
    if nodes is not None:
        G = G.subgraph(nodes)
    G = nx.convert_node_labels_to_integers(G, ordering="sorted")
    return b"".join(_generate_sparse6_bytes(G, nodes, header))


@open_file(0, mode="rb")
@nx._dispatchable(graphs=None, returns_graph=True)
def read_sparse6(path):
    """Read an undirected graph in sparse6 format from path.

    Parameters
    ----------
    path : file or string
       File or filename to write.

    Returns
    -------
    G : Graph/Multigraph or list of Graphs/MultiGraphs
       If the file contains multiple lines then a list of graphs is returned

    Raises
    ------
    NetworkXError
        If the string is unable to be parsed in sparse6 format

    Examples
    --------
    You can read a sparse6 file by giving the path to the file::

        >>> import tempfile
        >>> with tempfile.NamedTemporaryFile(delete=False) as f:
        ...     _ = f.write(b">>sparse6<<:An\\n")
        ...     _ = f.seek(0)
        ...     G = nx.read_sparse6(f.name)
        >>> list(G.edges())
        [(0, 1)]

    You can also read a sparse6 file by giving an open file-like object::

        >>> import tempfile
        >>> with tempfile.NamedTemporaryFile() as f:
        ...     _ = f.write(b">>sparse6<<:An\\n")
        ...     _ = f.seek(0)
        ...     G = nx.read_sparse6(f)
        >>> list(G.edges())
        [(0, 1)]

    See Also
    --------
    read_sparse6, from_sparse6_bytes

    References
    ----------
    .. [1] Sparse6 specification
           <https://users.cecs.anu.edu.au/~bdm/data/formats.html>

    """
    glist = []
    for line in path:
        line = line.strip()
        if not len(line):
            continue
        glist.append(from_sparse6_bytes(line))
    if len(glist) == 1:
        return glist[0]
    else:
        return glist


@not_implemented_for("directed")
@open_file(1, mode="wb")
def write_sparse6(G, path, nodes=None, header=True):
    """Write graph G to given path in sparse6 format.

    Parameters
    ----------
    G : Graph (undirected)

    path : file or string
       File or filename to write

    nodes: list or iterable
       Nodes are labeled 0...n-1 in the order provided.  If None the ordering
       given by G.nodes() is used.

    header: bool
       If True add '>>sparse6<<' string to head of data

    Raises
    ------
    NetworkXError
        If the graph is directed

    Examples
    --------
    You can write a sparse6 file by giving the path to the file::

        >>> import tempfile
        >>> with tempfile.NamedTemporaryFile(delete=False) as f:
        ...     nx.write_sparse6(nx.path_graph(2), f.name)
        ...     print(f.read())
        b'>>sparse6<<:An\\n'

    You can also write a sparse6 file by giving an open file-like object::

        >>> with tempfile.NamedTemporaryFile() as f:
        ...     nx.write_sparse6(nx.path_graph(2), f)
        ...     _ = f.seek(0)
        ...     print(f.read())
        b'>>sparse6<<:An\\n'

    See Also
    --------
    read_sparse6, from_sparse6_bytes

    Notes
    -----
    The format does not support edge or node labels.

    References
    ----------
    .. [1] Sparse6 specification
           <https://users.cecs.anu.edu.au/~bdm/data/formats.html>

    """
    if nodes is not None:
        G = G.subgraph(nodes)
    G = nx.convert_node_labels_to_integers(G, ordering="sorted")
    for b in _generate_sparse6_bytes(G, nodes, header):
        path.write(b)
