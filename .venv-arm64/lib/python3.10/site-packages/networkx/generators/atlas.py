"""
Generators for the small graph atlas.
"""

import gzip
import importlib.resources
import os
import os.path
from itertools import islice

import networkx as nx

__all__ = ["graph_atlas", "graph_atlas_g"]

#: The total number of graphs in the atlas.
#:
#: The graphs are labeled starting from 0 and extending to (but not
#: including) this number.
NUM_GRAPHS = 1253

#: The path to the data file containing the graph edge lists.
#:
#: This is the absolute path of the gzipped text file containing the
#: edge list for each graph in the atlas. The file contains one entry
#: per graph in the atlas, in sequential order, starting from graph
#: number 0 and extending through graph number 1252 (see
#: :data:`NUM_GRAPHS`). Each entry looks like
#:
#: .. sourcecode:: text
#:
#:    GRAPH 6
#:    NODES 3
#:    0 1
#:    0 2
#:
#: where the first two lines are the graph's index in the atlas and the
#: number of nodes in the graph, and the remaining lines are the edge
#: list.
#:
#: This file was generated from a Python list of graphs via code like
#: the following::
#:
#:     import gzip
#:     from networkx.generators.atlas import graph_atlas_g
#:     from networkx.readwrite.edgelist import write_edgelist
#:
#:     with gzip.open('atlas.dat.gz', 'wb') as f:
#:         for i, G in enumerate(graph_atlas_g()):
#:             f.write(bytes(f'GRAPH {i}\n', encoding='utf-8'))
#:             f.write(bytes(f'NODES {len(G)}\n', encoding='utf-8'))
#:             write_edgelist(G, f, data=False)
#:

# Path to the atlas file
ATLAS_FILE = importlib.resources.files("networkx.generators") / "atlas.dat.gz"


def _generate_graphs():
    """Sequentially read the file containing the edge list data for the
    graphs in the atlas and generate the graphs one at a time.

    This function reads the file given in :data:`.ATLAS_FILE`.

    """
    with gzip.open(ATLAS_FILE, "rb") as f:
        line = f.readline()
        while line and line.startswith(b"GRAPH"):
            # The first two lines of each entry tell us the index of the
            # graph in the list and the number of nodes in the graph.
            # They look like this:
            #
            #     GRAPH 3
            #     NODES 2
            #
            graph_index = int(line[6:].rstrip())
            line = f.readline()
            num_nodes = int(line[6:].rstrip())
            # The remaining lines contain the edge list, until the next
            # GRAPH line (or until the end of the file).
            edgelist = []
            line = f.readline()
            while line and not line.startswith(b"GRAPH"):
                edgelist.append(line.rstrip())
                line = f.readline()
            G = nx.Graph()
            G.name = f"G{graph_index}"
            G.add_nodes_from(range(num_nodes))
            G.add_edges_from(tuple(map(int, e.split())) for e in edgelist)
            yield G


@nx._dispatchable(graphs=None, returns_graph=True)
def graph_atlas(i):
    """Returns graph number `i` from the Graph Atlas.

    For more information, see :func:`.graph_atlas_g`.

    Parameters
    ----------
    i : int
        The index of the graph from the atlas to get. The graph at index
        0 is assumed to be the null graph.

    Returns
    -------
    list
        A list of :class:`~networkx.Graph` objects, the one at index *i*
        corresponding to the graph *i* in the Graph Atlas.

    See also
    --------
    graph_atlas_g

    Notes
    -----
    The time required by this function increases linearly with the
    argument `i`, since it reads a large file sequentially in order to
    generate the graph [1]_.

    References
    ----------
    .. [1] Ronald C. Read and Robin J. Wilson, *An Atlas of Graphs*.
           Oxford University Press, 1998.

    """
    if not (0 <= i < NUM_GRAPHS):
        raise ValueError(f"index must be between 0 and {NUM_GRAPHS}")
    return next(islice(_generate_graphs(), i, None))


@nx._dispatchable(graphs=None, returns_graph=True)
def graph_atlas_g():
    """Returns the list of all graphs with up to seven nodes named in the
    Graph Atlas.

    The graphs are listed in increasing order by

    1. number of nodes,
    2. number of edges,
    3. degree sequence (for example 111223 < 112222),
    4. number of automorphisms,

    in that order, with three exceptions as described in the *Notes*
    section below. This causes the list to correspond with the index of
    the graphs in the Graph Atlas [atlas]_, with the first graph,
    ``G[0]``, being the null graph.

    Returns
    -------
    list
        A list of :class:`~networkx.Graph` objects, the one at index *i*
        corresponding to the graph *i* in the Graph Atlas.

    See also
    --------
    graph_atlas

    Notes
    -----
    This function may be expensive in both time and space, since it
    reads a large file sequentially in order to populate the list.

    Although the NetworkX atlas functions match the order of graphs
    given in the "Atlas of Graphs" book, there are (at least) three
    errors in the ordering described in the book. The following three
    pairs of nodes violate the lexicographically nondecreasing sorted
    degree sequence rule:

    - graphs 55 and 56 with degree sequences 001111 and 000112,
    - graphs 1007 and 1008 with degree sequences 3333444 and 3333336,
    - graphs 1012 and 1213 with degree sequences 1244555 and 1244456.

    References
    ----------
    .. [atlas] Ronald C. Read and Robin J. Wilson,
               *An Atlas of Graphs*.
               Oxford University Press, 1998.

    """
    return list(_generate_graphs())
