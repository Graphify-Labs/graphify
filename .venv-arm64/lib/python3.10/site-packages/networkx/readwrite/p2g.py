"""
This module provides the following: read and write of p2g format
used in metabolic pathway studies.

See https://web.archive.org/web/20080626113807/http://www.cs.purdue.edu/homes/koyuturk/pathway/ for a description.

The summary is included here:

A file that describes a uniquely labeled graph (with extension ".gr")
format looks like the following:


name
3 4
a
1 2
b

c
0 2

"name" is simply a description of what the graph corresponds to. The
second line displays the number of nodes and number of edges,
respectively. This sample graph contains three nodes labeled "a", "b",
and "c". The rest of the graph contains two lines for each node. The
first line for a node contains the node label. After the declaration
of the node label, the out-edges of that node in the graph are
provided. For instance, "a" is linked to nodes 1 and 2, which are
labeled "b" and "c", while the node labeled "b" has no outgoing
edges. Observe that node labeled "c" has an outgoing edge to
itself. Indeed, self-loops are allowed. Node index starts from 0.

"""

import networkx as nx
from networkx.utils import open_file


@open_file(1, mode="w")
def write_p2g(G, path, encoding="utf-8"):
    """Write NetworkX graph in p2g format.

    Notes
    -----
    This format is meant to be used with directed graphs with
    possible self loops.
    """
    path.write((f"{G.name}\n").encode(encoding))
    path.write((f"{G.order()} {G.size()}\n").encode(encoding))
    nodes = list(G)
    # make dictionary mapping nodes to integers
    nodenumber = dict(zip(nodes, range(len(nodes))))
    for n in nodes:
        path.write((f"{n}\n").encode(encoding))
        for nbr in G.neighbors(n):
            path.write((f"{nodenumber[nbr]} ").encode(encoding))
        path.write("\n".encode(encoding))


@open_file(0, mode="r")
@nx._dispatchable(graphs=None, returns_graph=True)
def read_p2g(path, encoding="utf-8"):
    """Read graph in p2g format from path.

    Returns
    -------
    MultiDiGraph

    Notes
    -----
    If you want a DiGraph (with no self loops allowed and no edge data)
    use D=nx.DiGraph(read_p2g(path))
    """
    lines = (line.decode(encoding) for line in path)
    G = parse_p2g(lines)
    return G


@nx._dispatchable(graphs=None, returns_graph=True)
def parse_p2g(lines):
    """Parse p2g format graph from string or iterable.

    Returns
    -------
    MultiDiGraph
    """
    description = next(lines).strip()
    # are multiedges (parallel edges) allowed?
    G = nx.MultiDiGraph(name=description, selfloops=True)
    nnodes, nedges = map(int, next(lines).split())
    nodelabel = {}
    nbrs = {}
    # loop over the nodes keeping track of node labels and out neighbors
    # defer adding edges until all node labels are known
    for i in range(nnodes):
        n = next(lines).strip()
        nodelabel[i] = n
        G.add_node(n)
        nbrs[n] = map(int, next(lines).split())
    # now we know all of the node labels so we can add the edges
    # with the correct labels
    for n in G:
        for nbr in nbrs[n]:
            G.add_edge(n, nodelabel[nbr])
    return G
