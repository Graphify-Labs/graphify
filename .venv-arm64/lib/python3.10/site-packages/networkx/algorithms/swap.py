"""Swap edges in a graph."""

import math

import networkx as nx
from networkx.utils import py_random_state

__all__ = ["double_edge_swap", "connected_double_edge_swap", "directed_edge_swap"]


@nx.utils.not_implemented_for("undirected")
@py_random_state(3)
@nx._dispatchable(mutates_input=True, returns_graph=True)
def directed_edge_swap(G, *, nswap=1, max_tries=100, seed=None):
    """Swap three edges in a directed graph while keeping the node degrees fixed.

    A directed edge swap swaps three edges such that a -> b -> c -> d becomes
    a -> c -> b -> d. This pattern of swapping allows all possible states with the
    same in- and out-degree distribution in a directed graph to be reached.

    If the swap would create parallel edges (e.g. if a -> c already existed in the
    previous example), another attempt is made to find a suitable trio of edges.

    Parameters
    ----------
    G : DiGraph
       A directed graph

    nswap : integer (optional, default=1)
       Number of three-edge (directed) swaps to perform

    max_tries : integer (optional, default=100)
       Maximum number of attempts to swap edges

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    G : DiGraph
       The graph after the edges are swapped.

    Raises
    ------
    NetworkXError
        If `G` is not directed, or
        If nswap > max_tries, or
        If there are fewer than 4 nodes or 3 edges in `G`.
    NetworkXAlgorithmError
        If the number of swap attempts exceeds `max_tries` before `nswap` swaps are made

    Notes
    -----
    Does not enforce any connectivity constraints.

    The graph G is modified in place.

    A later swap is allowed to undo a previous swap.

    References
    ----------
    .. [1] Erdős, Péter L., et al. “A Simple Havel-Hakimi Type Algorithm to Realize
           Graphical Degree Sequences of Directed Graphs.” ArXiv:0905.4913 [Math],
           Jan. 2010. https://doi.org/10.48550/arXiv.0905.4913.
           Published  2010 in Elec. J. Combinatorics (17(1)). R66.
           http://www.combinatorics.org/Volume_17/PDF/v17i1r66.pdf
    .. [2] “Combinatorics - Reaching All Possible Simple Directed Graphs with a given
           Degree Sequence with 2-Edge Swaps.” Mathematics Stack Exchange,
           https://math.stackexchange.com/questions/22272/. Accessed 30 May 2022.
    """
    if nswap > max_tries:
        raise nx.NetworkXError("Number of swaps > number of tries allowed.")
    if len(G) < 4:
        raise nx.NetworkXError("DiGraph has fewer than four nodes.")
    if len(G.edges) < 3:
        raise nx.NetworkXError("DiGraph has fewer than 3 edges")

    # Instead of choosing uniformly at random from a generated edge list,
    # this algorithm chooses nonuniformly from the set of nodes with
    # probability weighted by degree.
    tries = 0
    swapcount = 0
    keys, degrees = zip(*G.degree())  # keys, degree
    cdf = nx.utils.cumulative_distribution(degrees)  # cdf of degree
    discrete_sequence = nx.utils.discrete_sequence

    while swapcount < nswap:
        # choose source node index from discrete distribution
        start_index = discrete_sequence(1, cdistribution=cdf, seed=seed)[0]
        start = keys[start_index]
        tries += 1

        if tries > max_tries:
            msg = f"Maximum number of swap attempts ({tries}) exceeded before desired swaps achieved ({nswap})."
            raise nx.NetworkXAlgorithmError(msg)

        # If the given node doesn't have any out edges, then there isn't anything to swap
        if G.out_degree(start) == 0:
            continue
        second = seed.choice(list(G.succ[start]))
        if start == second:
            continue

        if G.out_degree(second) == 0:
            continue
        third = seed.choice(list(G.succ[second]))
        if second == third:
            continue

        if G.out_degree(third) == 0:
            continue
        fourth = seed.choice(list(G.succ[third]))
        if third == fourth:
            continue

        if (
            third not in G.succ[start]
            and fourth not in G.succ[second]
            and second not in G.succ[third]
        ):
            # Swap nodes
            G.add_edge(start, third)
            G.add_edge(third, second)
            G.add_edge(second, fourth)
            G.remove_edge(start, second)
            G.remove_edge(second, third)
            G.remove_edge(third, fourth)
            swapcount += 1

    return G


@py_random_state(3)
@nx._dispatchable(mutates_input=True, returns_graph=True)
def double_edge_swap(G, nswap=1, max_tries=100, seed=None):
    """Swap two edges in the graph while keeping the node degrees fixed.

    A double-edge swap removes two randomly chosen edges u-v and x-y
    and creates the new edges u-x and v-y::

     u--v            u  v
            becomes  |  |
     x--y            x  y

    If either the edge u-x or v-y already exist no swap is performed
    and another attempt is made to find a suitable edge pair.

    Parameters
    ----------
    G : graph
       An undirected graph

    nswap : integer (optional, default=1)
       Number of double-edge swaps to perform

    max_tries : integer (optional)
       Maximum number of attempts to swap edges

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    G : graph
       The graph after double edge swaps.

    Raises
    ------
    NetworkXError
        If `G` is directed, or
        If `nswap` > `max_tries`, or
        If there are fewer than 4 nodes or 2 edges in `G`.
    NetworkXAlgorithmError
        If the number of swap attempts exceeds `max_tries` before `nswap` swaps are made

    Notes
    -----
    Does not enforce any connectivity constraints.

    The graph G is modified in place.
    """
    if G.is_directed():
        raise nx.NetworkXError(
            "double_edge_swap() not defined for directed graphs. Use directed_edge_swap instead."
        )
    if nswap > max_tries:
        raise nx.NetworkXError("Number of swaps > number of tries allowed.")
    if len(G) < 4:
        raise nx.NetworkXError("Graph has fewer than four nodes.")
    if len(G.edges) < 2:
        raise nx.NetworkXError("Graph has fewer than 2 edges")
    # Instead of choosing uniformly at random from a generated edge list,
    # this algorithm chooses nonuniformly from the set of nodes with
    # probability weighted by degree.
    n = 0
    swapcount = 0
    keys, degrees = zip(*G.degree())  # keys, degree
    cdf = nx.utils.cumulative_distribution(degrees)  # cdf of degree
    discrete_sequence = nx.utils.discrete_sequence
    while swapcount < nswap:
        #        if random.random() < 0.5: continue # trick to avoid periodicities?
        # pick two random edges without creating edge list
        # choose source node indices from discrete distribution
        (ui, xi) = discrete_sequence(2, cdistribution=cdf, seed=seed)
        if ui == xi:
            continue  # same source, skip
        u = keys[ui]  # convert index to label
        x = keys[xi]
        # choose target uniformly from neighbors
        v = seed.choice(list(G[u]))
        y = seed.choice(list(G[x]))
        if v == y:
            continue  # same target, skip
        if (x not in G[u]) and (y not in G[v]):  # don't create parallel edges
            G.add_edge(u, x)
            G.add_edge(v, y)
            G.remove_edge(u, v)
            G.remove_edge(x, y)
            swapcount += 1
        if n >= max_tries:
            e = (
                f"Maximum number of swap attempts ({n}) exceeded "
                f"before desired swaps achieved ({nswap})."
            )
            raise nx.NetworkXAlgorithmError(e)
        n += 1
    return G


@py_random_state(3)
@nx._dispatchable(mutates_input=True)
def connected_double_edge_swap(G, nswap=1, _window_threshold=3, seed=None):
    """Attempts the specified number of double-edge swaps in the graph `G`.

    A double-edge swap removes two randomly chosen edges `(u, v)` and `(x,
    y)` and creates the new edges `(u, x)` and `(v, y)`::

     u--v            u  v
            becomes  |  |
     x--y            x  y

    If either `(u, x)` or `(v, y)` already exist, then no swap is performed
    so the actual number of swapped edges is always *at most* `nswap`.

    Parameters
    ----------
    G : graph
       An undirected graph

    nswap : integer (optional, default=1)
       Number of double-edge swaps to perform

    _window_threshold : integer

       The window size below which connectedness of the graph will be checked
       after each swap.

       The "window" in this function is a dynamically updated integer that
       represents the number of swap attempts to make before checking if the
       graph remains connected. It is an optimization used to decrease the
       running time of the algorithm in exchange for increased complexity of
       implementation.

       If the window size is below this threshold, then the algorithm checks
       after each swap if the graph remains connected by checking if there is a
       path joining the two nodes whose edge was just removed. If the window
       size is above this threshold, then the algorithm performs do all the
       swaps in the window and only then check if the graph is still connected.

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    int
       The number of successful swaps

    Raises
    ------

    NetworkXError

       If the input graph is not connected, or if the graph has fewer than four
       nodes.

    Notes
    -----

    The initial graph `G` must be connected, and the resulting graph is
    connected. The graph `G` is modified in place.

    References
    ----------
    .. [1] C. Gkantsidis and M. Mihail and E. Zegura,
           The Markov chain simulation method for generating connected
           power law random graphs, 2003.
           http://citeseer.ist.psu.edu/gkantsidis03markov.html
    """
    if not nx.is_connected(G):
        raise nx.NetworkXError("Graph not connected")
    if len(G) < 4:
        raise nx.NetworkXError("Graph has fewer than four nodes.")
    n = 0
    swapcount = 0
    deg = G.degree()
    # Label key for nodes
    dk = [n for n, d in G.degree()]
    cdf = nx.utils.cumulative_distribution([d for n, d in G.degree()])
    discrete_sequence = nx.utils.discrete_sequence
    window = 1
    while n < nswap:
        wcount = 0
        swapped = []
        # If the window is small, we just check each time whether the graph is
        # connected by checking if the nodes that were just separated are still
        # connected.
        if window < _window_threshold:
            # This Boolean keeps track of whether there was a failure or not.
            fail = False
            while wcount < window and n < nswap:
                # Pick two random edges without creating the edge list. Choose
                # source nodes from the discrete degree distribution.
                (ui, xi) = discrete_sequence(2, cdistribution=cdf, seed=seed)
                # If the source nodes are the same, skip this pair.
                if ui == xi:
                    continue
                # Convert an index to a node label.
                u = dk[ui]
                x = dk[xi]
                # Choose targets uniformly from neighbors.
                v = seed.choice(list(G.neighbors(u)))
                y = seed.choice(list(G.neighbors(x)))
                # If the target nodes are the same, skip this pair.
                if v == y:
                    continue
                if x not in G[u] and y not in G[v]:
                    G.remove_edge(u, v)
                    G.remove_edge(x, y)
                    G.add_edge(u, x)
                    G.add_edge(v, y)
                    swapped.append((u, v, x, y))
                    swapcount += 1
                n += 1
                # If G remains connected...
                if nx.has_path(G, u, v):
                    wcount += 1
                # Otherwise, undo the changes.
                else:
                    G.add_edge(u, v)
                    G.add_edge(x, y)
                    G.remove_edge(u, x)
                    G.remove_edge(v, y)
                    swapcount -= 1
                    fail = True
            # If one of the swaps failed, reduce the window size.
            if fail:
                window = math.ceil(window / 2)
            else:
                window += 1
        # If the window is large, then there is a good chance that a bunch of
        # swaps will work. It's quicker to do all those swaps first and then
        # check if the graph remains connected.
        else:
            while wcount < window and n < nswap:
                # Pick two random edges without creating the edge list. Choose
                # source nodes from the discrete degree distribution.
                (ui, xi) = discrete_sequence(2, cdistribution=cdf, seed=seed)
                # If the source nodes are the same, skip this pair.
                if ui == xi:
                    continue
                # Convert an index to a node label.
                u = dk[ui]
                x = dk[xi]
                # Choose targets uniformly from neighbors.
                v = seed.choice(list(G.neighbors(u)))
                y = seed.choice(list(G.neighbors(x)))
                # If the target nodes are the same, skip this pair.
                if v == y:
                    continue
                if x not in G[u] and y not in G[v]:
                    G.remove_edge(u, v)
                    G.remove_edge(x, y)
                    G.add_edge(u, x)
                    G.add_edge(v, y)
                    swapped.append((u, v, x, y))
                    swapcount += 1
                n += 1
                wcount += 1
            # If the graph remains connected, increase the window size.
            if nx.is_connected(G):
                window += 1
            # Otherwise, undo the changes from the previous window and decrease
            # the window size.
            else:
                while swapped:
                    (u, v, x, y) = swapped.pop()
                    G.add_edge(u, v)
                    G.add_edge(x, y)
                    G.remove_edge(u, x)
                    G.remove_edge(v, y)
                    swapcount -= 1
                window = math.ceil(window / 2)
    return swapcount
