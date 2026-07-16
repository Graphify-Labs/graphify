import networkx as nx
from networkx.utils.decorators import not_implemented_for, py_random_state

__all__ = ["randomized_partitioning", "one_exchange"]


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@py_random_state(1)
@nx._dispatchable(edge_attrs="weight")
def randomized_partitioning(G, seed=None, p=0.5, weight=None):
    """Compute a random partitioning of the graph nodes and its cut value.

    A partitioning is calculated by observing each node
    and deciding to add it to the partition with probability `p`,
    returning a random cut and its corresponding value (the
    sum of weights of edges connecting different partitions).

    Parameters
    ----------
    G : NetworkX graph

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    p : scalar
        Probability for each node to be part of the first partition.
        Should be in [0,1]

    weight : object
        Edge attribute key to use as weight. If not specified, edges
        have weight one.

    Returns
    -------
    cut_size : scalar
        Value of the minimum cut.

    partition : pair of node sets
        A partitioning of the nodes that defines a minimum cut.

    Examples
    --------
    >>> G = nx.complete_graph(5)
    >>> cut_size, partition = nx.approximation.randomized_partitioning(G, seed=1)
    >>> cut_size
    6
    >>> partition
    ({0, 3, 4}, {1, 2})

    Raises
    ------
    NetworkXNotImplemented
        If the graph is directed or is a multigraph.
    """
    cut = {node for node in G.nodes() if seed.random() < p}
    cut_size = nx.algorithms.cut_size(G, cut, weight=weight)
    partition = (cut, G.nodes - cut)
    return cut_size, partition


def _swap_node_partition(cut, node):
    return cut - {node} if node in cut else cut.union({node})


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@py_random_state(2)
@nx._dispatchable(edge_attrs="weight")
def one_exchange(G, initial_cut=None, seed=None, weight=None):
    """Compute a partitioning of the graphs nodes and the corresponding cut value.

    Use a greedy one exchange strategy to find a locally maximal cut
    and its value, it works by finding the best node (one that gives
    the highest gain to the cut value) to add to the current cut
    and repeats this process until no improvement can be made.

    Parameters
    ----------
    G : networkx Graph
        Graph to find a maximum cut for.

    initial_cut : set
        Cut to use as a starting point. If not supplied the algorithm
        starts with an empty cut.

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    weight : object
        Edge attribute key to use as weight. If not specified, edges
        have weight one.

    Returns
    -------
    cut_value : scalar
        Value of the maximum cut.

    partition : pair of node sets
        A partitioning of the nodes that defines a maximum cut.

    Examples
    --------
    >>> G = nx.complete_graph(5)
    >>> curr_cut_size, partition = nx.approximation.one_exchange(G, seed=1)
    >>> curr_cut_size
    6
    >>> partition
    ({0, 2}, {1, 3, 4})

    Raises
    ------
    NetworkXNotImplemented
        If the graph is directed or is a multigraph.
    """
    if initial_cut is None:
        initial_cut = set()
    cut = set(initial_cut)
    current_cut_size = nx.algorithms.cut_size(G, cut, weight=weight)
    while True:
        nodes = list(G.nodes())
        # Shuffling the nodes ensures random tie-breaks in the following call to max
        seed.shuffle(nodes)
        best_node_to_swap = max(
            nodes,
            key=lambda v: nx.algorithms.cut_size(
                G, _swap_node_partition(cut, v), weight=weight
            ),
            default=None,
        )
        potential_cut = _swap_node_partition(cut, best_node_to_swap)
        potential_cut_size = nx.algorithms.cut_size(G, potential_cut, weight=weight)

        if potential_cut_size > current_cut_size:
            cut = potential_cut
            current_cut_size = potential_cut_size
        else:
            break

    partition = (cut, G.nodes - cut)
    return current_cut_size, partition
