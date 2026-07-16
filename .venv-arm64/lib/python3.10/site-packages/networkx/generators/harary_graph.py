"""Generators for Harary graphs

This module gives two generators for the Harary graph, which was
introduced by the famous mathematician Frank Harary in his 1962 work [H]_.
The first generator gives the Harary graph that maximizes the node
connectivity with given number of nodes and given number of edges.
The second generator gives the Harary graph that minimizes
the number of edges in the graph with given node connectivity and
number of nodes.

References
----------
.. [H] Harary, F. "The Maximum Connectivity of a Graph."
       Proc. Nat. Acad. Sci. USA 48, 1142-1146, 1962.

"""

import networkx as nx
from networkx.exception import NetworkXError

__all__ = ["hnm_harary_graph", "hkn_harary_graph"]


@nx._dispatchable(graphs=None, returns_graph=True)
def hnm_harary_graph(n, m, create_using=None):
    """Returns the Harary graph with given numbers of nodes and edges.

    The Harary graph $H_{n,m}$ is the graph that maximizes node connectivity
    with $n$ nodes and $m$ edges.

    This maximum node connectivity is known to be floor($2m/n$). [1]_

    Parameters
    ----------
    n: integer
       The number of nodes the generated graph is to contain

    m: integer
       The number of edges the generated graph is to contain

    create_using : NetworkX graph constructor, optional Graph type
     to create (default=nx.Graph). If graph instance, then cleared
     before populated.

    Returns
    -------
    NetworkX graph
        The Harary graph $H_{n,m}$.

    See Also
    --------
    hkn_harary_graph

    Notes
    -----
    This algorithm runs in $O(m)$ time.
    It is implemented by following the Reference [2]_.

    References
    ----------
    .. [1] F. T. Boesch, A. Satyanarayana, and C. L. Suffel,
       "A Survey of Some Network Reliability Analysis and Synthesis Results,"
       Networks, pp. 99-107, 2009.

    .. [2] Harary, F. "The Maximum Connectivity of a Graph."
       Proc. Nat. Acad. Sci. USA 48, 1142-1146, 1962.
    """

    if n < 1:
        raise NetworkXError("The number of nodes must be >= 1!")
    if m < n - 1:
        raise NetworkXError("The number of edges must be >= n - 1 !")
    if m > n * (n - 1) // 2:
        raise NetworkXError("The number of edges must be <= n(n-1)/2")

    # Construct an empty graph with n nodes first
    H = nx.empty_graph(n, create_using)
    # Get the floor of average node degree
    d = 2 * m // n

    # Test the parity of n and d
    if (n % 2 == 0) or (d % 2 == 0):
        # Start with a regular graph of d degrees
        offset = d // 2
        for i in range(n):
            for j in range(1, offset + 1):
                H.add_edge(i, (i - j) % n)
                H.add_edge(i, (i + j) % n)
        if d & 1:
            # in case d is odd; n must be even in this case
            half = n // 2
            for i in range(half):
                # add edges diagonally
                H.add_edge(i, i + half)
        # Get the remainder of 2*m modulo n
        r = 2 * m % n
        if r > 0:
            # add remaining edges at offset+1
            for i in range(r // 2):
                H.add_edge(i, i + offset + 1)
    else:
        # Start with a regular graph of (d - 1) degrees
        offset = (d - 1) // 2
        for i in range(n):
            for j in range(1, offset + 1):
                H.add_edge(i, (i - j) % n)
                H.add_edge(i, (i + j) % n)
        half = n // 2
        for i in range(m - n * offset):
            # add the remaining m - n*offset edges between i and i+half
            H.add_edge(i, (i + half) % n)

    return H


@nx._dispatchable(graphs=None, returns_graph=True)
def hkn_harary_graph(k, n, create_using=None):
    """Returns the Harary graph with given node connectivity and node number.

    The Harary graph $H_{k,n}$ is the graph that minimizes the number of
    edges needed with given node connectivity $k$ and node number $n$.

    This smallest number of edges is known to be ceil($kn/2$) [1]_.

    Parameters
    ----------
    k: integer
       The node connectivity of the generated graph

    n: integer
       The number of nodes the generated graph is to contain

    create_using : NetworkX graph constructor, optional Graph type
     to create (default=nx.Graph). If graph instance, then cleared
     before populated.

    Returns
    -------
    NetworkX graph
        The Harary graph $H_{k,n}$.

    See Also
    --------
    hnm_harary_graph

    Notes
    -----
    This algorithm runs in $O(kn)$ time.
    It is implemented by following the Reference [2]_.

    References
    ----------
    .. [1] Weisstein, Eric W. "Harary Graph." From MathWorld--A Wolfram Web
     Resource. http://mathworld.wolfram.com/HararyGraph.html.

    .. [2] Harary, F. "The Maximum Connectivity of a Graph."
      Proc. Nat. Acad. Sci. USA 48, 1142-1146, 1962.
    """

    if k < 1:
        raise NetworkXError("The node connectivity must be >= 1!")
    if n < k + 1:
        raise NetworkXError("The number of nodes must be >= k+1 !")

    # in case of connectivity 1, simply return the path graph
    if k == 1:
        H = nx.path_graph(n, create_using)
        return H

    # Construct an empty graph with n nodes first
    H = nx.empty_graph(n, create_using)

    # Test the parity of k and n
    if (k % 2 == 0) or (n % 2 == 0):
        # Construct a regular graph with k degrees
        offset = k // 2
        for i in range(n):
            for j in range(1, offset + 1):
                H.add_edge(i, (i - j) % n)
                H.add_edge(i, (i + j) % n)
        if k & 1:
            # odd degree; n must be even in this case
            half = n // 2
            for i in range(half):
                # add edges diagonally
                H.add_edge(i, i + half)
    else:
        # Construct a regular graph with (k - 1) degrees
        offset = (k - 1) // 2
        for i in range(n):
            for j in range(1, offset + 1):
                H.add_edge(i, (i - j) % n)
                H.add_edge(i, (i + j) % n)
        half = n // 2
        for i in range(half + 1):
            # add half+1 edges between i and i+half
            H.add_edge(i, (i + half) % n)

    return H
