# See https://github.com/networkx/networkx/pull/1474
# Copyright 2011 Reya Group <http://www.reyagroup.com>
# Copyright 2011 Alex Levenson <alex@isnotinvain.com>
# Copyright 2011 Diederik van Liere <diederik.vanliere@rotman.utoronto.ca>
"""Functions that generate the triad graphs, that is, the possible
digraphs on three nodes.

"""

import networkx as nx
from networkx.classes import DiGraph

__all__ = ["triad_graph"]

#: Dictionary mapping triad name to list of directed edges in the
#: digraph representation of that triad (with nodes 'a', 'b', and 'c').
TRIAD_EDGES = {
    "003": [],
    "012": ["ab"],
    "102": ["ab", "ba"],
    "021D": ["ba", "bc"],
    "021U": ["ab", "cb"],
    "021C": ["ab", "bc"],
    "111D": ["ac", "ca", "bc"],
    "111U": ["ac", "ca", "cb"],
    "030T": ["ab", "cb", "ac"],
    "030C": ["ba", "cb", "ac"],
    "201": ["ab", "ba", "ac", "ca"],
    "120D": ["bc", "ba", "ac", "ca"],
    "120U": ["ab", "cb", "ac", "ca"],
    "120C": ["ab", "bc", "ac", "ca"],
    "210": ["ab", "bc", "cb", "ac", "ca"],
    "300": ["ab", "ba", "bc", "cb", "ac", "ca"],
}


@nx._dispatchable(graphs=None, returns_graph=True)
def triad_graph(triad_name):
    """Returns the triad graph with the given name.

    Each string in the following tuple is a valid triad name::

        (
            "003",
            "012",
            "102",
            "021D",
            "021U",
            "021C",
            "111D",
            "111U",
            "030T",
            "030C",
            "201",
            "120D",
            "120U",
            "120C",
            "210",
            "300",
        )

    Each triad name corresponds to one of the possible valid digraph on
    three nodes.

    Parameters
    ----------
    triad_name : string
        The name of a triad, as described above.

    Returns
    -------
    :class:`~networkx.DiGraph`
        The digraph on three nodes with the given name. The nodes of the
        graph are the single-character strings 'a', 'b', and 'c'.

    Raises
    ------
    ValueError
        If `triad_name` is not the name of a triad.

    See also
    --------
    triadic_census

    """
    if triad_name not in TRIAD_EDGES:
        raise ValueError(
            f'unknown triad name "{triad_name}"; use one of the triad names'
            " in the TRIAD_NAMES constant"
        )
    G = DiGraph()
    G.add_nodes_from("abc")
    G.add_edges_from(TRIAD_EDGES[triad_name])
    return G
