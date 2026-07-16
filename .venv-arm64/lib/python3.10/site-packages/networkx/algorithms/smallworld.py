"""Functions for estimating the small-world-ness of graphs.

A small world network is characterized by a small average shortest path length,
and a large clustering coefficient.

Small-worldness is commonly measured with the coefficient sigma or omega.

Both coefficients compare the average clustering coefficient and shortest path
length of a given graph against the same quantities for an equivalent random
or lattice graph.

For more information, see the Wikipedia article on small-world network [1]_.

.. [1] Small-world network:: https://en.wikipedia.org/wiki/Small-world_network

"""

import networkx as nx
from networkx.utils import not_implemented_for, py_random_state

__all__ = ["random_reference", "lattice_reference", "sigma", "omega"]


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@py_random_state(3)
@nx._dispatchable(returns_graph=True)
def random_reference(G, niter=1, connectivity=True, seed=None):
    """Compute a random graph by swapping edges of a given graph.

    Parameters
    ----------
    G : graph
        An undirected graph with 4 or more nodes.

    niter : integer (optional, default=1)
        An edge is rewired approximately `niter` times.

    connectivity : boolean (optional, default=True)
        When True, ensure connectivity for the randomized graph.

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    G : graph
        The randomized graph.

    Raises
    ------
    NetworkXError
        If there are fewer than 4 nodes or 2 edges in `G`

    Notes
    -----
    The implementation is adapted from the algorithm by Maslov and Sneppen
    (2002) [1]_.

    References
    ----------
    .. [1] Maslov, Sergei, and Kim Sneppen.
           "Specificity and stability in topology of protein networks."
           Science 296.5569 (2002): 910-913.
    """
    if len(G) < 4:
        raise nx.NetworkXError("Graph has fewer than four nodes.")
    if len(G.edges) < 2:
        raise nx.NetworkXError("Graph has fewer that 2 edges")

    from networkx.utils import cumulative_distribution, discrete_sequence

    local_conn = nx.connectivity.local_edge_connectivity

    G = G.copy()
    keys, degrees = zip(*G.degree())  # keys, degree
    cdf = cumulative_distribution(degrees)  # cdf of degree
    nnodes = len(G)
    nedges = nx.number_of_edges(G)
    niter = niter * nedges
    ntries = int(nnodes * nedges / (nnodes * (nnodes - 1) / 2))
    swapcount = 0

    for i in range(niter):
        n = 0
        while n < ntries:
            # pick two random edges without creating edge list
            # choose source node indices from discrete distribution
            (ai, ci) = discrete_sequence(2, cdistribution=cdf, seed=seed)
            if ai == ci:
                continue  # same source, skip
            a = keys[ai]  # convert index to label
            c = keys[ci]
            # choose target uniformly from neighbors
            b = seed.choice(list(G.neighbors(a)))
            d = seed.choice(list(G.neighbors(c)))
            if b in [a, c, d] or d in [a, b, c]:
                continue  # all vertices should be different

            # don't create parallel edges
            if (d not in G[a]) and (b not in G[c]):
                G.add_edge(a, d)
                G.add_edge(c, b)
                G.remove_edge(a, b)
                G.remove_edge(c, d)

                # Check if the graph is still connected
                if connectivity and local_conn(G, a, b) == 0:
                    # Not connected, revert the swap
                    G.remove_edge(a, d)
                    G.remove_edge(c, b)
                    G.add_edge(a, b)
                    G.add_edge(c, d)
                else:
                    swapcount += 1
                    break
            n += 1
    return G


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@py_random_state(4)
@nx._dispatchable(returns_graph=True)
def lattice_reference(G, niter=5, D=None, connectivity=True, seed=None):
    """Latticize the given graph by swapping edges.

    Parameters
    ----------
    G : graph
        An undirected graph.

    niter : integer (optional, default=1)
        An edge is rewired approximately niter times.

    D : numpy.array (optional, default=None)
        Distance to the diagonal matrix.

    connectivity : boolean (optional, default=True)
        Ensure connectivity for the latticized graph when set to True.

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    G : graph
        The latticized graph.

    Raises
    ------
    NetworkXError
        If there are fewer than 4 nodes or 2 edges in `G`

    Notes
    -----
    The implementation is adapted from the algorithm by Sporns et al. [1]_.
    which is inspired from the original work by Maslov and Sneppen(2002) [2]_.

    References
    ----------
    .. [1] Sporns, Olaf, and Jonathan D. Zwi.
       "The small world of the cerebral cortex."
       Neuroinformatics 2.2 (2004): 145-162.
    .. [2] Maslov, Sergei, and Kim Sneppen.
       "Specificity and stability in topology of protein networks."
       Science 296.5569 (2002): 910-913.
    """
    import numpy as np

    from networkx.utils import cumulative_distribution, discrete_sequence

    local_conn = nx.connectivity.local_edge_connectivity

    if len(G) < 4:
        raise nx.NetworkXError("Graph has fewer than four nodes.")
    if len(G.edges) < 2:
        raise nx.NetworkXError("Graph has fewer that 2 edges")
    # Instead of choosing uniformly at random from a generated edge list,
    # this algorithm chooses nonuniformly from the set of nodes with
    # probability weighted by degree.
    G = G.copy()
    keys, degrees = zip(*G.degree())  # keys, degree
    cdf = cumulative_distribution(degrees)  # cdf of degree

    nnodes = len(G)
    nedges = nx.number_of_edges(G)
    if D is None:
        D = np.zeros((nnodes, nnodes))
        un = np.arange(1, nnodes)
        um = np.arange(nnodes - 1, 0, -1)
        u = np.append((0,), np.where(un < um, un, um))

        for v in range(int(np.ceil(nnodes / 2))):
            D[nnodes - v - 1, :] = np.append(u[v + 1 :], u[: v + 1])
            D[v, :] = D[nnodes - v - 1, :][::-1]

    niter = niter * nedges
    # maximal number of rewiring attempts per 'niter'
    max_attempts = int(nnodes * nedges / (nnodes * (nnodes - 1) / 2))

    for _ in range(niter):
        n = 0
        while n < max_attempts:
            # pick two random edges without creating edge list
            # choose source node indices from discrete distribution
            (ai, ci) = discrete_sequence(2, cdistribution=cdf, seed=seed)
            if ai == ci:
                continue  # same source, skip
            a = keys[ai]  # convert index to label
            c = keys[ci]
            # choose target uniformly from neighbors
            b = seed.choice(list(G.neighbors(a)))
            d = seed.choice(list(G.neighbors(c)))
            bi = keys.index(b)
            di = keys.index(d)

            if b in [a, c, d] or d in [a, b, c]:
                continue  # all vertices should be different

            # don't create parallel edges
            if (d not in G[a]) and (b not in G[c]):
                if D[ai, bi] + D[ci, di] >= D[ai, ci] + D[bi, di]:
                    # only swap if we get closer to the diagonal
                    G.add_edge(a, d)
                    G.add_edge(c, b)
                    G.remove_edge(a, b)
                    G.remove_edge(c, d)

                    # Check if the graph is still connected
                    if connectivity and local_conn(G, a, b) == 0:
                        # Not connected, revert the swap
                        G.remove_edge(a, d)
                        G.remove_edge(c, b)
                        G.add_edge(a, b)
                        G.add_edge(c, d)
                    else:
                        break
            n += 1

    return G


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@py_random_state(3)
@nx._dispatchable
def sigma(G, niter=100, nrand=10, seed=None):
    """Returns the small-world coefficient (sigma) of the given graph.

    The small-world coefficient is defined as:
    sigma = C/Cr / L/Lr
    where C and L are respectively the average clustering coefficient and
    average shortest path length of G. Cr and Lr are respectively the average
    clustering coefficient and average shortest path length of an equivalent
    random graph.

    A graph is commonly classified as small-world if sigma>1.

    Parameters
    ----------
    G : NetworkX graph
        An undirected graph.
    niter : integer (optional, default=100)
        Approximate number of rewiring per edge to compute the equivalent
        random graph.
    nrand : integer (optional, default=10)
        Number of random graphs generated to compute the average clustering
        coefficient (Cr) and average shortest path length (Lr).
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    sigma : float
        The small-world coefficient of G.

    Notes
    -----
    The implementation is adapted from Humphries et al. [1]_ [2]_.

    References
    ----------
    .. [1] The brainstem reticular formation is a small-world, not scale-free,
           network M. D. Humphries, K. Gurney and T. J. Prescott,
           Proc. Roy. Soc. B 2006 273, 503-511, doi:10.1098/rspb.2005.3354.
    .. [2] Humphries and Gurney (2008).
           "Network 'Small-World-Ness': A Quantitative Method for Determining
           Canonical Network Equivalence".
           PLoS One. 3 (4). PMID 18446219. doi:10.1371/journal.pone.0002051.
    """
    import numpy as np

    # Compute the mean clustering coefficient and average shortest path length
    # for an equivalent random graph
    randMetrics = {"C": [], "L": []}
    for i in range(nrand):
        Gr = random_reference(G, niter=niter, seed=seed)
        randMetrics["C"].append(nx.transitivity(Gr))
        randMetrics["L"].append(nx.average_shortest_path_length(Gr))

    C = nx.transitivity(G)
    L = nx.average_shortest_path_length(G)
    Cr = np.mean(randMetrics["C"])
    Lr = np.mean(randMetrics["L"])

    sigma = (C / Cr) / (L / Lr)

    return float(sigma)


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@py_random_state(3)
@nx._dispatchable
def omega(G, niter=5, nrand=10, seed=None):
    """Returns the small-world coefficient (omega) of a graph

    The small-world coefficient of a graph G is:

    omega = Lr/L - C/Cl

    where C and L are respectively the average clustering coefficient and
    average shortest path length of G. Lr is the average shortest path length
    of an equivalent random graph and Cl is the average clustering coefficient
    of an equivalent lattice graph.

    The small-world coefficient (omega) measures how much G is like a lattice
    or a random graph. Negative values mean G is similar to a lattice whereas
    positive values mean G is a random graph.
    Values close to 0 mean that G has small-world characteristics.

    Parameters
    ----------
    G : NetworkX graph
        An undirected graph.

    niter: integer (optional, default=5)
        Approximate number of rewiring per edge to compute the equivalent
        random graph.

    nrand: integer (optional, default=10)
        Number of random graphs generated to compute the maximal clustering
        coefficient (Cr) and average shortest path length (Lr).

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.


    Returns
    -------
    omega : float
        The small-world coefficient (omega)

    Notes
    -----
    The implementation is adapted from the algorithm by Telesford et al. [1]_.

    References
    ----------
    .. [1] Telesford, Joyce, Hayasaka, Burdette, and Laurienti (2011).
           "The Ubiquity of Small-World Networks".
           Brain Connectivity. 1 (0038): 367-75.  PMC 3604768. PMID 22432451.
           doi:10.1089/brain.2011.0038.
    """
    import numpy as np

    # Compute the mean clustering coefficient and average shortest path length
    # for an equivalent random graph
    randMetrics = {"C": [], "L": []}

    # Calculate initial average clustering coefficient which potentially will
    # get replaced by higher clustering coefficients from generated lattice
    # reference graphs
    Cl = nx.average_clustering(G)

    niter_lattice_reference = niter
    niter_random_reference = niter * 2

    for _ in range(nrand):
        # Generate random graph
        Gr = random_reference(G, niter=niter_random_reference, seed=seed)
        randMetrics["L"].append(nx.average_shortest_path_length(Gr))

        # Generate lattice graph
        Gl = lattice_reference(G, niter=niter_lattice_reference, seed=seed)

        # Replace old clustering coefficient, if clustering is higher in
        # generated lattice reference
        Cl_temp = nx.average_clustering(Gl)
        if Cl_temp > Cl:
            Cl = Cl_temp

    C = nx.average_clustering(G)
    L = nx.average_shortest_path_length(G)
    Lr = np.mean(randMetrics["L"])

    omega = (Lr / L) - (C / Cl)

    return float(omega)
