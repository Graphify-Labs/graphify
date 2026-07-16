"""Copyright (c) 2015 – Thomson Licensing, SAS

Redistribution and use in source and binary forms, with or without
modification, are permitted (subject to the limitations in the
disclaimer below) provided that the following conditions are met:

* Redistributions of source code must retain the above copyright
notice, this list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright
notice, this list of conditions and the following disclaimer in the
documentation and/or other materials provided with the distribution.

* Neither the name of Thomson Licensing, or Technicolor, nor the names
of its contributors may be used to endorse or promote products derived
from this software without specific prior written permission.

NO EXPRESS OR IMPLIED LICENSES TO ANY PARTY'S PATENT RIGHTS ARE
GRANTED BY THIS LICENSE.  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT
HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED
WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR
BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN
IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

import networkx as nx
from networkx.utils import not_implemented_for

# Authors: Erwan Le Merrer (erwan.lemerrer@technicolor.com)

__all__ = ["second_order_centrality"]


@not_implemented_for("directed")
@nx._dispatchable(edge_attrs="weight")
def second_order_centrality(G, weight="weight"):
    """Compute the second order centrality for nodes of G.

    The second order centrality of a given node is the standard deviation of
    the return times to that node of a perpetual random walk on G:

    Parameters
    ----------
    G : graph
      A NetworkX connected and undirected graph.

    weight : string or None, optional (default="weight")
        The name of an edge attribute that holds the numerical value
        used as a weight. If None then each edge has weight 1.

    Returns
    -------
    nodes : dictionary
       Dictionary keyed by node with second order centrality as the value.

    Examples
    --------
    >>> G = nx.star_graph(10)
    >>> soc = nx.second_order_centrality(G)
    >>> print(sorted(soc.items(), key=lambda x: x[1])[0][0])  # pick first id
    0

    Raises
    ------
    NetworkXException
        If the graph G is empty, non connected or has negative weights.

    See Also
    --------
    betweenness_centrality

    Notes
    -----
    Lower values of second order centrality indicate higher centrality.

    The algorithm is from Kermarrec, Le Merrer, Sericola and Trédan [1]_.

    This code implements the analytical version of the algorithm, i.e.,
    there is no simulation of a random walk process involved. The random walk
    is here unbiased (corresponding to eq 6 of the paper [1]_), thus the
    centrality values are the standard deviations for random walk return times
    on the transformed input graph G (equal in-degree at each nodes by adding
    self-loops).

    Complexity of this implementation, made to run locally on a single machine,
    is O(n^3), with n the size of G, which makes it viable only for small
    graphs.

    References
    ----------
    .. [1] Anne-Marie Kermarrec, Erwan Le Merrer, Bruno Sericola, Gilles Trédan
       "Second order centrality: Distributed assessment of nodes criticity in
       complex networks", Elsevier Computer Communications 34(5):619-628, 2011.
    """
    import numpy as np

    n = len(G)

    if n == 0:
        raise nx.NetworkXException("Empty graph.")
    if not nx.is_connected(G):
        raise nx.NetworkXException("Non connected graph.")
    if any(d.get(weight, 0) < 0 for u, v, d in G.edges(data=True)):
        raise nx.NetworkXException("Graph has negative edge weights.")

    # balancing G for Metropolis-Hastings random walks
    G = nx.DiGraph(G)
    in_deg = dict(G.in_degree(weight=weight))
    d_max = max(in_deg.values())
    for i, deg in in_deg.items():
        if deg < d_max:
            G.add_edge(i, i, weight=d_max - deg)

    P = nx.to_numpy_array(G)
    P /= P.sum(axis=1)[:, np.newaxis]  # to transition probability matrix

    def _Qj(P, j):
        P = P.copy()
        P[:, j] = 0
        return P

    M = np.empty([n, n])

    for i in range(n):
        M[:, i] = np.linalg.solve(
            np.identity(n) - _Qj(P, i), np.ones([n, 1])[:, 0]
        )  # eq 3

    return dict(
        zip(
            G.nodes,
            (float(np.sqrt(2 * np.sum(M[:, i]) - n * (n + 1))) for i in range(n)),
        )
    )  # eq 6
