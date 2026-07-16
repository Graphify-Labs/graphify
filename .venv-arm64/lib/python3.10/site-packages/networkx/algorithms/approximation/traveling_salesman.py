"""
=================================
Travelling Salesman Problem (TSP)
=================================

Implementation of approximate algorithms
for solving and approximating the TSP problem.

Categories of algorithms which are implemented:

- Christofides (provides a 3/2-approximation of TSP)
- Greedy
- Simulated Annealing (SA)
- Threshold Accepting (TA)
- Asadpour Asymmetric Traveling Salesman Algorithm

The Travelling Salesman Problem tries to find, given the weight
(distance) between all points where a salesman has to visit, the
route so that:

- The total distance (cost) which the salesman travels is minimized.
- The salesman returns to the starting point.
- Note that for a complete graph, the salesman visits each point once.

The function `travelling_salesman_problem` allows for incomplete
graphs by finding all-pairs shortest paths, effectively converting
the problem to a complete graph problem. It calls one of the
approximate methods on that problem and then converts the result
back to the original graph using the previously found shortest paths.

TSP is an NP-hard problem in combinatorial optimization,
important in operations research and theoretical computer science.

http://en.wikipedia.org/wiki/Travelling_salesman_problem
"""

import math

import networkx as nx
from networkx.algorithms.tree.mst import random_spanning_tree
from networkx.utils import not_implemented_for, pairwise, py_random_state

__all__ = [
    "traveling_salesman_problem",
    "christofides",
    "asadpour_atsp",
    "greedy_tsp",
    "simulated_annealing_tsp",
    "threshold_accepting_tsp",
]


def swap_two_nodes(soln, seed):
    """Swap two nodes in `soln` to give a neighbor solution.

    Parameters
    ----------
    soln : list of nodes
        Current cycle of nodes

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    list
        The solution after move is applied. (A neighbor solution.)

    Notes
    -----
        This function assumes that the incoming list `soln` is a cycle
        (that the first and last element are the same) and also that
        we don't want any move to change the first node in the list
        (and thus not the last node either).

        The input list is changed as well as returned. Make a copy if needed.

    See Also
    --------
        move_one_node
    """
    a, b = seed.sample(range(1, len(soln) - 1), k=2)
    soln[a], soln[b] = soln[b], soln[a]
    return soln


def move_one_node(soln, seed):
    """Move one node to another position to give a neighbor solution.

    The node to move and the position to move to are chosen randomly.
    The first and last nodes are left untouched as soln must be a cycle
    starting at that node.

    Parameters
    ----------
    soln : list of nodes
        Current cycle of nodes

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    list
        The solution after move is applied. (A neighbor solution.)

    Notes
    -----
        This function assumes that the incoming list `soln` is a cycle
        (that the first and last element are the same) and also that
        we don't want any move to change the first node in the list
        (and thus not the last node either).

        The input list is changed as well as returned. Make a copy if needed.

    See Also
    --------
        swap_two_nodes
    """
    a, b = seed.sample(range(1, len(soln) - 1), k=2)
    soln.insert(b, soln.pop(a))
    return soln


@not_implemented_for("directed")
@nx._dispatchable(edge_attrs="weight")
def christofides(G, weight="weight", tree=None):
    """Approximate a solution of the traveling salesman problem

    Compute a 3/2-approximation of the traveling salesman problem
    in a complete undirected graph using Christofides [1]_ algorithm.

    Parameters
    ----------
    G : Graph
        `G` should be a complete weighted undirected graph.
        The distance between all pairs of nodes should be included.

    weight : string, optional (default="weight")
        Edge data key corresponding to the edge weight.
        If any edge does not have this attribute the weight is set to 1.

    tree : NetworkX graph or None (default: None)
        A minimum spanning tree of G. Or, if None, the minimum spanning
        tree is computed using :func:`networkx.minimum_spanning_tree`

    Returns
    -------
    list
        List of nodes in `G` along a cycle with a 3/2-approximation of
        the minimal Hamiltonian cycle.

    References
    ----------
    .. [1] Christofides, Nicos. "Worst-case analysis of a new heuristic for
       the travelling salesman problem." No. RR-388. Carnegie-Mellon Univ
       Pittsburgh Pa Management Sciences Research Group, 1976.
    """
    # Remove selfloops if necessary
    loop_nodes = nx.nodes_with_selfloops(G)
    try:
        node = next(loop_nodes)
    except StopIteration:
        pass
    else:
        G = G.copy()
        G.remove_edge(node, node)
        G.remove_edges_from((n, n) for n in loop_nodes)
    # Check that G is a complete graph
    N = len(G) - 1
    # This check ignores selfloops which is what we want here.
    if any(len(nbrdict) != N for n, nbrdict in G.adj.items()):
        raise nx.NetworkXError("G must be a complete graph.")

    if tree is None:
        tree = nx.minimum_spanning_tree(G, weight=weight)
    L = G.copy()
    L.remove_nodes_from([v for v, degree in tree.degree if not (degree % 2)])
    MG = nx.MultiGraph()
    MG.add_edges_from(tree.edges)
    edges = nx.min_weight_matching(L, weight=weight)
    MG.add_edges_from(edges)
    return _shortcutting(nx.eulerian_circuit(MG))


def _shortcutting(circuit):
    """Remove duplicate nodes in the path"""
    nodes = []
    for u, v in circuit:
        if v in nodes:
            continue
        if not nodes:
            nodes.append(u)
        nodes.append(v)
    nodes.append(nodes[0])
    return nodes


@nx._dispatchable(edge_attrs="weight")
def traveling_salesman_problem(
    G, weight="weight", nodes=None, cycle=True, method=None, **kwargs
):
    """Find the shortest path in `G` connecting specified nodes

    This function allows approximate solution to the traveling salesman
    problem on networks that are not complete graphs and/or where the
    salesman does not need to visit all nodes.

    This function proceeds in two steps. First, it creates a complete
    graph using the all-pairs shortest_paths between nodes in `nodes`.
    Edge weights in the new graph are the lengths of the paths
    between each pair of nodes in the original graph.
    Second, an algorithm (default: `christofides` for undirected and
    `asadpour_atsp` for directed) is used to approximate the minimal Hamiltonian
    cycle on this new graph. The available algorithms are:

     - christofides
     - greedy_tsp
     - simulated_annealing_tsp
     - threshold_accepting_tsp
     - asadpour_atsp

    Once the Hamiltonian Cycle is found, this function post-processes to
    accommodate the structure of the original graph. If `cycle` is ``False``,
    the biggest weight edge is removed to make a Hamiltonian path.
    Then each edge on the new complete graph used for that analysis is
    replaced by the shortest_path between those nodes on the original graph.
    If the input graph `G` includes edges with weights that do not adhere to
    the triangle inequality, such as when `G` is not a complete graph (i.e
    length of non-existent edges is infinity), then the returned path may
    contain some repeating nodes (other than the starting node).

    Parameters
    ----------
    G : NetworkX graph
        A possibly weighted graph

    nodes : collection of nodes (default=G.nodes)
        collection (list, set, etc.) of nodes to visit

    weight : string, optional (default="weight")
        Edge data key corresponding to the edge weight.
        If any edge does not have this attribute the weight is set to 1.

    cycle : bool (default: True)
        Indicates whether a cycle should be returned, or a path.
        Note: the cycle is the approximate minimal cycle.
        The path simply removes the biggest edge in that cycle.

    method : function (default: None)
        A function that returns a cycle on all nodes and approximates
        the solution to the traveling salesman problem on a complete
        graph. The returned cycle is then used to find a corresponding
        solution on `G`. `method` should be callable; take inputs
        `G`, and `weight`; and return a list of nodes along the cycle.

        Provided options include :func:`christofides`, :func:`greedy_tsp`,
        :func:`simulated_annealing_tsp` and :func:`threshold_accepting_tsp`.

        If `method is None`: use :func:`christofides` for undirected `G` and
        :func:`asadpour_atsp` for directed `G`.

    **kwargs : dict
        Other keyword arguments to be passed to the `method` function passed in.

    Returns
    -------
    list
        List of nodes in `G` along a path with an approximation of the minimal
        path through `nodes`.

    Raises
    ------
    NetworkXError
        If `G` is a directed graph it has to be strongly connected or the
        complete version cannot be generated.

    Examples
    --------
    >>> tsp = nx.approximation.traveling_salesman_problem
    >>> G = nx.cycle_graph(9)
    >>> G[4][5]["weight"] = 5  # all other weights are 1
    >>> tsp(G, nodes=[3, 6])
    [3, 2, 1, 0, 8, 7, 6, 7, 8, 0, 1, 2, 3]
    >>> path = tsp(G, cycle=False)
    >>> path in ([4, 3, 2, 1, 0, 8, 7, 6, 5], [5, 6, 7, 8, 0, 1, 2, 3, 4])
    True

    While no longer required, you can still build (curry) your own function
    to provide parameter values to the methods.

    >>> SA_tsp = nx.approximation.simulated_annealing_tsp
    >>> method = lambda G, weight: SA_tsp(G, "greedy", weight=weight, temp=500)
    >>> path = tsp(G, cycle=False, method=method)
    >>> path in ([4, 3, 2, 1, 0, 8, 7, 6, 5], [5, 6, 7, 8, 0, 1, 2, 3, 4])
    True

    Otherwise, pass other keyword arguments directly into the tsp function.

    >>> path = tsp(
    ...     G,
    ...     cycle=False,
    ...     method=nx.approximation.simulated_annealing_tsp,
    ...     init_cycle="greedy",
    ...     temp=500,
    ... )
    >>> path in ([4, 3, 2, 1, 0, 8, 7, 6, 5], [5, 6, 7, 8, 0, 1, 2, 3, 4])
    True
    """
    if method is None:
        if G.is_directed():
            method = asadpour_atsp
        else:
            method = christofides
    if nodes is None:
        nodes = list(G.nodes)

    dist = {}
    path = {}
    for n, (d, p) in nx.all_pairs_dijkstra(G, weight=weight):
        dist[n] = d
        path[n] = p

    if G.is_directed():
        # If the graph is not strongly connected, raise an exception
        if not nx.is_strongly_connected(G):
            raise nx.NetworkXError("G is not strongly connected")
        GG = nx.DiGraph()
    else:
        GG = nx.Graph()
    for u in nodes:
        for v in nodes:
            if u == v:
                continue
            GG.add_edge(u, v, weight=dist[u][v])

    best_GG = method(GG, weight=weight, **kwargs)

    if not cycle:
        # find and remove the biggest edge
        (u, v) = max(pairwise(best_GG), key=lambda x: dist[x[0]][x[1]])
        pos = best_GG.index(u) + 1
        while best_GG[pos] != v:
            pos = best_GG[pos:].index(u) + 1
        best_GG = best_GG[pos:-1] + best_GG[:pos]

    best_path = []
    for u, v in pairwise(best_GG):
        best_path.extend(path[u][v][:-1])
    best_path.append(v)
    return best_path


@not_implemented_for("undirected")
@py_random_state(2)
@nx._dispatchable(edge_attrs="weight", mutates_input=True)
def asadpour_atsp(G, weight="weight", seed=None, source=None):
    """
    Returns an approximate solution to the traveling salesman problem.

    This approximate solution is one of the best known approximations for the
    asymmetric traveling salesman problem developed by Asadpour et al,
    [1]_. The algorithm first solves the Held-Karp relaxation to find a lower
    bound for the weight of the cycle. Next, it constructs an exponential
    distribution of undirected spanning trees where the probability of an
    edge being in the tree corresponds to the weight of that edge using a
    maximum entropy rounding scheme. Next we sample that distribution
    $2 \\lceil \\ln n \\rceil$ times and save the minimum sampled tree once the
    direction of the arcs is added back to the edges. Finally, we augment
    then short circuit that graph to find the approximate tour for the
    salesman.

    Parameters
    ----------
    G : nx.DiGraph
        The graph should be a complete weighted directed graph. The
        distance between all paris of nodes should be included and the triangle
        inequality should hold. That is, the direct edge between any two nodes
        should be the path of least cost.

    weight : string, optional (default="weight")
        Edge data key corresponding to the edge weight.
        If any edge does not have this attribute the weight is set to 1.

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    source : node label (default=`None`)
        If given, return the cycle starting and ending at the given node.

    Returns
    -------
    cycle : list of nodes
        Returns the cycle (list of nodes) that a salesman can follow to minimize
        the total weight of the trip.

    Raises
    ------
    NetworkXError
        If `G` is not complete or has less than two nodes, the algorithm raises
        an exception.

    NetworkXError
        If `source` is not `None` and is not a node in `G`, the algorithm raises
        an exception.

    NetworkXNotImplemented
        If `G` is an undirected graph.

    References
    ----------
    .. [1] A. Asadpour, M. X. Goemans, A. Madry, S. O. Gharan, and A. Saberi,
       An o(log n/log log n)-approximation algorithm for the asymmetric
       traveling salesman problem, Operations research, 65 (2017),
       pp. 1043–1061

    Examples
    --------
    >>> import networkx as nx
    >>> import networkx.algorithms.approximation as approx
    >>> G = nx.complete_graph(3, create_using=nx.DiGraph)
    >>> nx.set_edge_attributes(
    ...     G,
    ...     {(0, 1): 2, (1, 2): 2, (2, 0): 2, (0, 2): 1, (2, 1): 1, (1, 0): 1},
    ...     "weight",
    ... )
    >>> tour = approx.asadpour_atsp(G, source=0)
    >>> tour
    [0, 2, 1, 0]
    """
    from math import ceil, exp
    from math import log as ln

    # Check that G is a complete graph
    N = len(G) - 1
    if N < 2:
        raise nx.NetworkXError("G must have at least two nodes")
    # This check ignores selfloops which is what we want here.
    if any(len(nbrdict) - (n in nbrdict) != N for n, nbrdict in G.adj.items()):
        raise nx.NetworkXError("G is not a complete DiGraph")
    # Check that the source vertex, if given, is in the graph
    if source is not None and source not in G.nodes:
        raise nx.NetworkXError("Given source node not in G.")

    opt_hk, z_star = held_karp_ascent(G, weight)

    # Test to see if the ascent method found an integer solution or a fractional
    # solution. If it is integral then z_star is a nx.Graph, otherwise it is
    # a dict
    if not isinstance(z_star, dict):
        # Here we are using the shortcutting method to go from the list of edges
        # returned from eulerian_circuit to a list of nodes
        return _shortcutting(nx.eulerian_circuit(z_star, source=source))

    # Create the undirected support of z_star
    z_support = nx.MultiGraph()
    for u, v in z_star:
        if (u, v) not in z_support.edges:
            edge_weight = min(G[u][v][weight], G[v][u][weight])
            z_support.add_edge(u, v, **{weight: edge_weight})

    # Create the exponential distribution of spanning trees
    gamma = spanning_tree_distribution(z_support, z_star)

    # Write the lambda values to the edges of z_support
    z_support = nx.Graph(z_support)
    lambda_dict = {(u, v): exp(gamma[(u, v)]) for u, v in z_support.edges()}
    nx.set_edge_attributes(z_support, lambda_dict, "weight")
    del gamma, lambda_dict

    # Sample 2 * ceil( ln(n) ) spanning trees and record the minimum one
    minimum_sampled_tree = None
    minimum_sampled_tree_weight = math.inf
    for _ in range(2 * ceil(ln(G.number_of_nodes()))):
        sampled_tree = random_spanning_tree(z_support, "weight", seed=seed)
        sampled_tree_weight = sampled_tree.size(weight)
        if sampled_tree_weight < minimum_sampled_tree_weight:
            minimum_sampled_tree = sampled_tree.copy()
            minimum_sampled_tree_weight = sampled_tree_weight

    # Orient the edges in that tree to keep the cost of the tree the same.
    t_star = nx.MultiDiGraph()
    for u, v, d in minimum_sampled_tree.edges(data=weight):
        if d == G[u][v][weight]:
            t_star.add_edge(u, v, **{weight: d})
        else:
            t_star.add_edge(v, u, **{weight: d})

    # Find the node demands needed to neutralize the flow of t_star in G
    node_demands = {n: t_star.out_degree(n) - t_star.in_degree(n) for n in t_star}
    nx.set_node_attributes(G, node_demands, "demand")

    # Find the min_cost_flow
    flow_dict = nx.min_cost_flow(G, "demand")

    # Build the flow into t_star
    for source, values in flow_dict.items():
        for target in values:
            if (source, target) not in t_star.edges and values[target] > 0:
                # IF values[target] > 0 we have to add that many edges
                for _ in range(values[target]):
                    t_star.add_edge(source, target)

    # Return the shortcut eulerian circuit
    circuit = nx.eulerian_circuit(t_star, source=source)
    return _shortcutting(circuit)


@nx._dispatchable(edge_attrs="weight", mutates_input=True, returns_graph=True)
def held_karp_ascent(G, weight="weight"):
    """
    Minimizes the Held-Karp relaxation of the TSP for `G`

    Solves the Held-Karp relaxation of the input complete digraph and scales
    the output solution for use in the Asadpour [1]_ ASTP algorithm.

    The Held-Karp relaxation defines the lower bound for solutions to the
    ATSP, although it does return a fractional solution. This is used in the
    Asadpour algorithm as an initial solution which is later rounded to a
    integral tree within the spanning tree polytopes. This function solves
    the relaxation with the branch and bound method in [2]_.

    Parameters
    ----------
    G : nx.DiGraph
        The graph should be a complete weighted directed graph.
        The distance between all paris of nodes should be included.

    weight : string, optional (default="weight")
        Edge data key corresponding to the edge weight.
        If any edge does not have this attribute the weight is set to 1.

    Returns
    -------
    OPT : float
        The cost for the optimal solution to the Held-Karp relaxation
    z : dict or nx.Graph
        A symmetrized and scaled version of the optimal solution to the
        Held-Karp relaxation for use in the Asadpour algorithm.

        If an integral solution is found, then that is an optimal solution for
        the ATSP problem and that is returned instead.

    References
    ----------
    .. [1] A. Asadpour, M. X. Goemans, A. Madry, S. O. Gharan, and A. Saberi,
       An o(log n/log log n)-approximation algorithm for the asymmetric
       traveling salesman problem, Operations research, 65 (2017),
       pp. 1043–1061

    .. [2] M. Held, R. M. Karp, The traveling-salesman problem and minimum
           spanning trees, Operations Research, 1970-11-01, Vol. 18 (6),
           pp.1138-1162
    """
    import numpy as np
    from scipy import optimize

    def k_pi():
        """
        Find the set of minimum 1-Arborescences for G at point pi.

        Returns
        -------
        Set
            The set of minimum 1-Arborescences
        """
        # Create a copy of G without vertex 1.
        G_1 = G.copy()
        minimum_1_arborescences = set()
        minimum_1_arborescence_weight = math.inf

        # node is node '1' in the Held and Karp paper
        n = next(G.__iter__())
        G_1.remove_node(n)

        # Iterate over the spanning arborescences of the graph until we know
        # that we have found the minimum 1-arborescences. My proposed strategy
        # is to find the most extensive root to connect to from 'node 1' and
        # the least expensive one. We then iterate over arborescences until
        # the cost of the basic arborescence is the cost of the minimum one
        # plus the difference between the most and least expensive roots,
        # that way the cost of connecting 'node 1' will by definition not by
        # minimum
        min_root = {"node": None, weight: math.inf}
        max_root = {"node": None, weight: -math.inf}
        for u, v, d in G.edges(n, data=True):
            if d[weight] < min_root[weight]:
                min_root = {"node": v, weight: d[weight]}
            if d[weight] > max_root[weight]:
                max_root = {"node": v, weight: d[weight]}

        min_in_edge = min(G.in_edges(n, data=True), key=lambda x: x[2][weight])
        min_root[weight] = min_root[weight] + min_in_edge[2][weight]
        max_root[weight] = max_root[weight] + min_in_edge[2][weight]

        min_arb_weight = math.inf
        for arb in nx.ArborescenceIterator(G_1):
            arb_weight = arb.size(weight)
            if min_arb_weight == math.inf:
                min_arb_weight = arb_weight
            elif arb_weight > min_arb_weight + max_root[weight] - min_root[weight]:
                break
            # We have to pick the root node of the arborescence for the out
            # edge of the first vertex as that is the only node without an
            # edge directed into it.
            for N, deg in arb.in_degree:
                if deg == 0:
                    # root found
                    arb.add_edge(n, N, **{weight: G[n][N][weight]})
                    arb_weight += G[n][N][weight]
                    break

            # We can pick the minimum weight in-edge for the vertex with
            # a cycle. If there are multiple edges with the same, minimum
            # weight, We need to add all of them.
            #
            # Delete the edge (N, v) so that we cannot pick it.
            edge_data = G[N][n]
            G.remove_edge(N, n)
            min_weight = min(G.in_edges(n, data=weight), key=lambda x: x[2])[2]
            min_edges = [
                (u, v, d) for u, v, d in G.in_edges(n, data=weight) if d == min_weight
            ]
            for u, v, d in min_edges:
                new_arb = arb.copy()
                new_arb.add_edge(u, v, **{weight: d})
                new_arb_weight = arb_weight + d
                # Check to see the weight of the arborescence, if it is a
                # new minimum, clear all of the old potential minimum
                # 1-arborescences and add this is the only one. If its
                # weight is above the known minimum, do not add it.
                if new_arb_weight < minimum_1_arborescence_weight:
                    minimum_1_arborescences.clear()
                    minimum_1_arborescence_weight = new_arb_weight
                # We have a 1-arborescence, add it to the set
                if new_arb_weight == minimum_1_arborescence_weight:
                    minimum_1_arborescences.add(new_arb)
            G.add_edge(N, n, **edge_data)

        return minimum_1_arborescences

    def direction_of_ascent():
        """
        Find the direction of ascent at point pi.

        See [1]_ for more information.

        Returns
        -------
        dict
            A mapping from the nodes of the graph which represents the direction
            of ascent.

        References
        ----------
        .. [1] M. Held, R. M. Karp, The traveling-salesman problem and minimum
           spanning trees, Operations Research, 1970-11-01, Vol. 18 (6),
           pp.1138-1162
        """
        # 1. Set d equal to the zero n-vector.
        d = {}
        for n in G:
            d[n] = 0
        del n
        # 2. Find a 1-Arborescence T^k such that k is in K(pi, d).
        minimum_1_arborescences = k_pi()
        while True:
            # Reduce K(pi) to K(pi, d)
            # Find the arborescence in K(pi) which increases the lest in
            # direction d
            min_k_d_weight = math.inf
            min_k_d = None
            for arborescence in minimum_1_arborescences:
                weighted_cost = 0
                for n, deg in arborescence.degree:
                    weighted_cost += d[n] * (deg - 2)
                if weighted_cost < min_k_d_weight:
                    min_k_d_weight = weighted_cost
                    min_k_d = arborescence

            # 3. If sum of d_i * v_{i, k} is greater than zero, terminate
            if min_k_d_weight > 0:
                return d, min_k_d
            # 4. d_i = d_i + v_{i, k}
            for n, deg in min_k_d.degree:
                d[n] += deg - 2
            # Check that we do not need to terminate because the direction
            # of ascent does not exist. This is done with linear
            # programming.
            c = np.full(len(minimum_1_arborescences), -1, dtype=int)
            a_eq = np.empty((len(G) + 1, len(minimum_1_arborescences)), dtype=int)
            b_eq = np.zeros(len(G) + 1, dtype=int)
            b_eq[len(G)] = 1
            for arb_count, arborescence in enumerate(minimum_1_arborescences):
                n_count = len(G) - 1
                for n, deg in arborescence.degree:
                    a_eq[n_count][arb_count] = deg - 2
                    n_count -= 1
                a_eq[len(G)][arb_count] = 1
            program_result = optimize.linprog(
                c, A_eq=a_eq, b_eq=b_eq, method="highs-ipm"
            )
            # If the constants exist, then the direction of ascent doesn't
            if program_result.success:
                # There is no direction of ascent
                return None, minimum_1_arborescences

            # 5. GO TO 2

    def find_epsilon(k, d):
        """
        Given the direction of ascent at pi, find the maximum distance we can go
        in that direction.

        Parameters
        ----------
        k_xy : set
            The set of 1-arborescences which have the minimum rate of increase
            in the direction of ascent

        d : dict
            The direction of ascent

        Returns
        -------
        float
            The distance we can travel in direction `d`
        """
        min_epsilon = math.inf
        for e_u, e_v, e_w in G.edges(data=weight):
            if (e_u, e_v) in k.edges:
                continue
            # Now, I have found a condition which MUST be true for the edges to
            # be a valid substitute. The edge in the graph which is the
            # substitute is the one with the same terminated end. This can be
            # checked rather simply.
            #
            # Find the edge within k which is the substitute. Because k is a
            # 1-arborescence, we know that they is only one such edges
            # leading into every vertex.
            if len(k.in_edges(e_v, data=weight)) > 1:
                raise Exception
            sub_u, sub_v, sub_w = next(k.in_edges(e_v, data=weight).__iter__())
            k.add_edge(e_u, e_v, **{weight: e_w})
            k.remove_edge(sub_u, sub_v)
            if (
                max(d for n, d in k.in_degree()) <= 1
                and len(G) == k.number_of_edges()
                and nx.is_weakly_connected(k)
            ):
                # Ascent method calculation
                if d[sub_u] == d[e_u] or sub_w == e_w:
                    # Revert to the original graph
                    k.remove_edge(e_u, e_v)
                    k.add_edge(sub_u, sub_v, **{weight: sub_w})
                    continue
                epsilon = (sub_w - e_w) / (d[e_u] - d[sub_u])
                if 0 < epsilon < min_epsilon:
                    min_epsilon = epsilon
            # Revert to the original graph
            k.remove_edge(e_u, e_v)
            k.add_edge(sub_u, sub_v, **{weight: sub_w})

        return min_epsilon

    # I have to know that the elements in pi correspond to the correct elements
    # in the direction of ascent, even if the node labels are not integers.
    # Thus, I will use dictionaries to made that mapping.
    pi_dict = {}
    for n in G:
        pi_dict[n] = 0
    del n
    original_edge_weights = {}
    for u, v, d in G.edges(data=True):
        original_edge_weights[(u, v)] = d[weight]
    dir_ascent, k_d = direction_of_ascent()
    while dir_ascent is not None:
        max_distance = find_epsilon(k_d, dir_ascent)
        for n, v in dir_ascent.items():
            pi_dict[n] += max_distance * v
        for u, v, d in G.edges(data=True):
            d[weight] = original_edge_weights[(u, v)] + pi_dict[u]
        dir_ascent, k_d = direction_of_ascent()
    nx._clear_cache(G)
    # k_d is no longer an individual 1-arborescence but rather a set of
    # minimal 1-arborescences at the maximum point of the polytope and should
    # be reflected as such
    k_max = k_d

    # Search for a cycle within k_max. If a cycle exists, return it as the
    # solution
    for k in k_max:
        if len([n for n in k if k.degree(n) == 2]) == G.order():
            # Tour found
            # TODO: this branch does not restore original_edge_weights of G!
            return k.size(weight), k

    # Write the original edge weights back to G and every member of k_max at
    # the maximum point. Also average the number of times that edge appears in
    # the set of minimal 1-arborescences.
    x_star = {}
    size_k_max = len(k_max)
    for u, v, d in G.edges(data=True):
        edge_count = 0
        d[weight] = original_edge_weights[(u, v)]
        for k in k_max:
            if (u, v) in k.edges():
                edge_count += 1
                k[u][v][weight] = original_edge_weights[(u, v)]
        x_star[(u, v)] = edge_count / size_k_max
    # Now symmetrize the edges in x_star and scale them according to (5) in
    # reference [1]
    z_star = {}
    scale_factor = (G.order() - 1) / G.order()
    for u, v in x_star:
        frequency = x_star[(u, v)] + x_star[(v, u)]
        if frequency > 0:
            z_star[(u, v)] = scale_factor * frequency
    del x_star
    # Return the optimal weight and the z dict
    return next(k_max.__iter__()).size(weight), z_star


@nx._dispatchable
def spanning_tree_distribution(G, z):
    """
    Find the asadpour exponential distribution of spanning trees.

    Solves the Maximum Entropy Convex Program in the Asadpour algorithm [1]_
    using the approach in section 7 to build an exponential distribution of
    undirected spanning trees.

    This algorithm ensures that the probability of any edge in a spanning
    tree is proportional to the sum of the probabilities of the tress
    containing that edge over the sum of the probabilities of all spanning
    trees of the graph.

    Parameters
    ----------
    G : nx.MultiGraph
        The undirected support graph for the Held Karp relaxation

    z : dict
        The output of `held_karp_ascent()`, a scaled version of the Held-Karp
        solution.

    Returns
    -------
    gamma : dict
        The probability distribution which approximately preserves the marginal
        probabilities of `z`.
    """
    from math import exp
    from math import log as ln

    def q(e):
        """
        The value of q(e) is described in the Asadpour paper is "the
        probability that edge e will be included in a spanning tree T that is
        chosen with probability proportional to exp(gamma(T))" which
        basically means that it is the total probability of the edge appearing
        across the whole distribution.

        Parameters
        ----------
        e : tuple
            The `(u, v)` tuple describing the edge we are interested in

        Returns
        -------
        float
            The probability that a spanning tree chosen according to the
            current values of gamma will include edge `e`.
        """
        # Create the laplacian matrices
        for u, v, d in G.edges(data=True):
            d[lambda_key] = exp(gamma[(u, v)])
        G_Kirchhoff = nx.total_spanning_tree_weight(G, lambda_key)
        G_e = nx.contracted_edge(G, e, self_loops=False)
        G_e_Kirchhoff = nx.total_spanning_tree_weight(G_e, lambda_key)

        # Multiply by the weight of the contracted edge since it is not included
        # in the total weight of the contracted graph.
        return exp(gamma[(e[0], e[1])]) * G_e_Kirchhoff / G_Kirchhoff

    # initialize gamma to the zero dict
    gamma = {}
    for u, v, _ in G.edges:
        gamma[(u, v)] = 0

    # set epsilon
    EPSILON = 0.2

    # pick an edge attribute name that is unlikely to be in the graph
    lambda_key = "spanning_tree_distribution's secret attribute name for lambda"

    while True:
        # We need to know that know that no values of q_e are greater than
        # (1 + epsilon) * z_e, however changing one gamma value can increase the
        # value of a different q_e, so we have to complete the for loop without
        # changing anything for the condition to be meet
        in_range_count = 0
        # Search for an edge with q_e > (1 + epsilon) * z_e
        for u, v in gamma:
            e = (u, v)
            q_e = q(e)
            z_e = z[e]
            if q_e > (1 + EPSILON) * z_e:
                delta = ln(
                    (q_e * (1 - (1 + EPSILON / 2) * z_e))
                    / ((1 - q_e) * (1 + EPSILON / 2) * z_e)
                )
                gamma[e] -= delta
                # Check that delta had the desired effect
                new_q_e = q(e)
                desired_q_e = (1 + EPSILON / 2) * z_e
                if round(new_q_e, 8) != round(desired_q_e, 8):
                    raise nx.NetworkXError(
                        f"Unable to modify probability for edge ({u}, {v})"
                    )
            else:
                in_range_count += 1
        # Check if the for loop terminated without changing any gamma
        if in_range_count == len(gamma):
            break

    # Remove the new edge attributes
    for _, _, d in G.edges(data=True):
        if lambda_key in d:
            del d[lambda_key]

    return gamma


@nx._dispatchable(edge_attrs="weight")
def greedy_tsp(G, weight="weight", source=None):
    """Return a low cost cycle starting at `source` and its cost.

    This approximates a solution to the traveling salesman problem.
    It finds a cycle of all the nodes that a salesman can visit in order
    to visit many nodes while minimizing total distance.
    It uses a simple greedy algorithm.
    In essence, this function returns a large cycle given a source point
    for which the total cost of the cycle is minimized.

    Parameters
    ----------
    G : Graph
        The Graph should be a complete weighted undirected graph.
        The distance between all pairs of nodes should be included.

    weight : string, optional (default="weight")
        Edge data key corresponding to the edge weight.
        If any edge does not have this attribute the weight is set to 1.

    source : node, optional (default: first node in list(G))
        Starting node.  If None, defaults to ``next(iter(G))``

    Returns
    -------
    cycle : list of nodes
        Returns the cycle (list of nodes) that a salesman
        can follow to minimize total weight of the trip.

    Raises
    ------
    NetworkXError
        If `G` is not complete, the algorithm raises an exception.

    Examples
    --------
    >>> from networkx.algorithms import approximation as approx
    >>> G = nx.DiGraph()
    >>> G.add_weighted_edges_from(
    ...     {
    ...         ("A", "B", 3),
    ...         ("A", "C", 17),
    ...         ("A", "D", 14),
    ...         ("B", "A", 3),
    ...         ("B", "C", 12),
    ...         ("B", "D", 16),
    ...         ("C", "A", 13),
    ...         ("C", "B", 12),
    ...         ("C", "D", 4),
    ...         ("D", "A", 14),
    ...         ("D", "B", 15),
    ...         ("D", "C", 2),
    ...     }
    ... )
    >>> cycle = approx.greedy_tsp(G, source="D")
    >>> cost = sum(G[n][nbr]["weight"] for n, nbr in nx.utils.pairwise(cycle))
    >>> cycle
    ['D', 'C', 'B', 'A', 'D']
    >>> cost
    31

    Notes
    -----
    This implementation of a greedy algorithm is based on the following:

    - The algorithm adds a node to the solution at every iteration.
    - The algorithm selects a node not already in the cycle whose connection
      to the previous node adds the least cost to the cycle.

    A greedy algorithm does not always give the best solution.
    However, it can construct a first feasible solution which can
    be passed as a parameter to an iterative improvement algorithm such
    as Simulated Annealing, or Threshold Accepting.

    Time complexity: It has a running time $O(|V|^2)$
    """
    # Check that G is a complete graph
    N = len(G) - 1
    # This check ignores selfloops which is what we want here.
    if any(len(nbrdict) - (n in nbrdict) != N for n, nbrdict in G.adj.items()):
        raise nx.NetworkXError("G must be a complete graph.")

    if source is None:
        source = nx.utils.arbitrary_element(G)

    if G.number_of_nodes() == 2:
        neighbor = next(G.neighbors(source))
        return [source, neighbor, source]

    nodeset = set(G)
    nodeset.remove(source)
    cycle = [source]
    next_node = source
    while nodeset:
        nbrdict = G[next_node]
        next_node = min(nodeset, key=lambda n: nbrdict[n].get(weight, 1))
        cycle.append(next_node)
        nodeset.remove(next_node)
    cycle.append(cycle[0])
    return cycle


@py_random_state(9)
@nx._dispatchable(edge_attrs="weight")
def simulated_annealing_tsp(
    G,
    init_cycle,
    weight="weight",
    source=None,
    temp=100,
    move="1-1",
    max_iterations=10,
    N_inner=100,
    alpha=0.01,
    seed=None,
):
    """Returns an approximate solution to the traveling salesman problem.

    This function uses simulated annealing to approximate the minimal cost
    cycle through the nodes. Starting from a suboptimal solution, simulated
    annealing perturbs that solution, occasionally accepting changes that make
    the solution worse to escape from a locally optimal solution. The chance
    of accepting such changes decreases over the iterations to encourage
    an optimal result.  In summary, the function returns a cycle starting
    at `source` for which the total cost is minimized. It also returns the cost.

    The chance of accepting a proposed change is related to a parameter called
    the temperature (annealing has a physical analogue of steel hardening
    as it cools). As the temperature is reduced, the chance of moves that
    increase cost goes down.

    Parameters
    ----------
    G : Graph
        `G` should be a complete weighted graph.
        The distance between all pairs of nodes should be included.

    init_cycle : list of all nodes or "greedy"
        The initial solution (a cycle through all nodes returning to the start).
        This argument has no default to make you think about it.
        If "greedy", use `greedy_tsp(G, weight)`.
        Other common starting cycles are `list(G) + [next(iter(G))]` or the final
        result of `simulated_annealing_tsp` when doing `threshold_accepting_tsp`.

    weight : string, optional (default="weight")
        Edge data key corresponding to the edge weight.
        If any edge does not have this attribute the weight is set to 1.

    source : node, optional (default: first node in list(G))
        Starting node.  If None, defaults to ``next(iter(G))``

    temp : int, optional (default=100)
        The algorithm's temperature parameter. It represents the initial
        value of temperature

    move : "1-1" or "1-0" or function, optional (default="1-1")
        Indicator of what move to use when finding new trial solutions.
        Strings indicate two special built-in moves:

        - "1-1": 1-1 exchange which transposes the position
          of two elements of the current solution.
          The function called is :func:`swap_two_nodes`.
          For example if we apply 1-1 exchange in the solution
          ``A = [3, 2, 1, 4, 3]``
          we can get the following by the transposition of 1 and 4 elements:
          ``A' = [3, 2, 4, 1, 3]``
        - "1-0": 1-0 exchange which moves an node in the solution
          to a new position.
          The function called is :func:`move_one_node`.
          For example if we apply 1-0 exchange in the solution
          ``A = [3, 2, 1, 4, 3]``
          we can transfer the fourth element to the second position:
          ``A' = [3, 4, 2, 1, 3]``

        You may provide your own functions to enact a move from
        one solution to a neighbor solution. The function must take
        the solution as input along with a `seed` input to control
        random number generation (see the `seed` input here).
        Your function should maintain the solution as a cycle with
        equal first and last node and all others appearing once.
        Your function should return the new solution.

    max_iterations : int, optional (default=10)
        Declared done when this number of consecutive iterations of
        the outer loop occurs without any change in the best cost solution.

    N_inner : int, optional (default=100)
        The number of iterations of the inner loop.

    alpha : float between (0, 1), optional (default=0.01)
        Percentage of temperature decrease in each iteration
        of outer loop

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    cycle : list of nodes
        Returns the cycle (list of nodes) that a salesman
        can follow to minimize total weight of the trip.

    Raises
    ------
    NetworkXError
        If `G` is not complete the algorithm raises an exception.

    Examples
    --------
    >>> from networkx.algorithms import approximation as approx
    >>> G = nx.DiGraph()
    >>> G.add_weighted_edges_from(
    ...     {
    ...         ("A", "B", 3),
    ...         ("A", "C", 17),
    ...         ("A", "D", 14),
    ...         ("B", "A", 3),
    ...         ("B", "C", 12),
    ...         ("B", "D", 16),
    ...         ("C", "A", 13),
    ...         ("C", "B", 12),
    ...         ("C", "D", 4),
    ...         ("D", "A", 14),
    ...         ("D", "B", 15),
    ...         ("D", "C", 2),
    ...     }
    ... )
    >>> cycle = approx.simulated_annealing_tsp(G, "greedy", source="D")
    >>> cost = sum(G[n][nbr]["weight"] for n, nbr in nx.utils.pairwise(cycle))
    >>> cycle
    ['D', 'C', 'B', 'A', 'D']
    >>> cost
    31
    >>> incycle = ["D", "B", "A", "C", "D"]
    >>> cycle = approx.simulated_annealing_tsp(G, incycle, source="D")
    >>> cost = sum(G[n][nbr]["weight"] for n, nbr in nx.utils.pairwise(cycle))
    >>> cycle
    ['D', 'C', 'B', 'A', 'D']
    >>> cost
    31

    Notes
    -----
    Simulated Annealing is a metaheuristic local search algorithm.
    The main characteristic of this algorithm is that it accepts
    even solutions which lead to the increase of the cost in order
    to escape from low quality local optimal solutions.

    This algorithm needs an initial solution. If not provided, it is
    constructed by a simple greedy algorithm. At every iteration, the
    algorithm selects thoughtfully a neighbor solution.
    Consider $c(x)$ cost of current solution and $c(x')$ cost of a
    neighbor solution.
    If $c(x') - c(x) <= 0$ then the neighbor solution becomes the current
    solution for the next iteration. Otherwise, the algorithm accepts
    the neighbor solution with probability $p = exp - ([c(x') - c(x)] / temp)$.
    Otherwise the current solution is retained.

    `temp` is a parameter of the algorithm and represents temperature.

    Time complexity:
    For $N_i$ iterations of the inner loop and $N_o$ iterations of the
    outer loop, this algorithm has running time $O(N_i * N_o * |V|)$.

    For more information and how the algorithm is inspired see:
    http://en.wikipedia.org/wiki/Simulated_annealing
    """
    if move == "1-1":
        move = swap_two_nodes
    elif move == "1-0":
        move = move_one_node
    if init_cycle == "greedy":
        # Construct an initial solution using a greedy algorithm.
        cycle = greedy_tsp(G, weight=weight, source=source)
        if G.number_of_nodes() == 2:
            return cycle

    else:
        cycle = list(init_cycle)
        if source is None:
            source = cycle[0]
        elif source != cycle[0]:
            raise nx.NetworkXError("source must be first node in init_cycle")
        if cycle[0] != cycle[-1]:
            raise nx.NetworkXError("init_cycle must be a cycle. (return to start)")

        if len(cycle) - 1 != len(G) or len(set(G.nbunch_iter(cycle))) != len(G):
            raise nx.NetworkXError("init_cycle should be a cycle over all nodes in G.")

        # Check that G is a complete graph
        N = len(G) - 1
        # This check ignores selfloops which is what we want here.
        if any(len(nbrdict) - (n in nbrdict) != N for n, nbrdict in G.adj.items()):
            raise nx.NetworkXError("G must be a complete graph.")

        if G.number_of_nodes() == 2:
            neighbor = next(G.neighbors(source))
            return [source, neighbor, source]

    # Find the cost of initial solution
    cost = sum(G[u][v].get(weight, 1) for u, v in pairwise(cycle))

    count = 0
    best_cycle = cycle.copy()
    best_cost = cost
    while count <= max_iterations and temp > 0:
        count += 1
        for i in range(N_inner):
            adj_sol = move(cycle, seed)
            adj_cost = sum(G[u][v].get(weight, 1) for u, v in pairwise(adj_sol))
            delta = adj_cost - cost
            if delta <= 0:
                # Set current solution the adjacent solution.
                cycle = adj_sol
                cost = adj_cost

                if cost < best_cost:
                    count = 0
                    best_cycle = cycle.copy()
                    best_cost = cost
            else:
                # Accept even a worse solution with probability p.
                p = math.exp(-delta / temp)
                if p >= seed.random():
                    cycle = adj_sol
                    cost = adj_cost
        temp -= temp * alpha

    return best_cycle


@py_random_state(9)
@nx._dispatchable(edge_attrs="weight")
def threshold_accepting_tsp(
    G,
    init_cycle,
    weight="weight",
    source=None,
    threshold=1,
    move="1-1",
    max_iterations=10,
    N_inner=100,
    alpha=0.1,
    seed=None,
):
    """Returns an approximate solution to the traveling salesman problem.

    This function uses threshold accepting methods to approximate the minimal cost
    cycle through the nodes. Starting from a suboptimal solution, threshold
    accepting methods perturb that solution, accepting any changes that make
    the solution no worse than increasing by a threshold amount. Improvements
    in cost are accepted, but so are changes leading to small increases in cost.
    This allows the solution to leave suboptimal local minima in solution space.
    The threshold is decreased slowly as iterations proceed helping to ensure
    an optimum. In summary, the function returns a cycle starting at `source`
    for which the total cost is minimized.

    Parameters
    ----------
    G : Graph
        `G` should be a complete weighted graph.
        The distance between all pairs of nodes should be included.

    init_cycle : list or "greedy"
        The initial solution (a cycle through all nodes returning to the start).
        This argument has no default to make you think about it.
        If "greedy", use `greedy_tsp(G, weight)`.
        Other common starting cycles are `list(G) + [next(iter(G))]` or the final
        result of `simulated_annealing_tsp` when doing `threshold_accepting_tsp`.

    weight : string, optional (default="weight")
        Edge data key corresponding to the edge weight.
        If any edge does not have this attribute the weight is set to 1.

    source : node, optional (default: first node in list(G))
        Starting node.  If None, defaults to ``next(iter(G))``

    threshold : int, optional (default=1)
        The algorithm's threshold parameter. It represents the initial
        threshold's value

    move : "1-1" or "1-0" or function, optional (default="1-1")
        Indicator of what move to use when finding new trial solutions.
        Strings indicate two special built-in moves:

        - "1-1": 1-1 exchange which transposes the position
          of two elements of the current solution.
          The function called is :func:`swap_two_nodes`.
          For example if we apply 1-1 exchange in the solution
          ``A = [3, 2, 1, 4, 3]``
          we can get the following by the transposition of 1 and 4 elements:
          ``A' = [3, 2, 4, 1, 3]``
        - "1-0": 1-0 exchange which moves an node in the solution
          to a new position.
          The function called is :func:`move_one_node`.
          For example if we apply 1-0 exchange in the solution
          ``A = [3, 2, 1, 4, 3]``
          we can transfer the fourth element to the second position:
          ``A' = [3, 4, 2, 1, 3]``

        You may provide your own functions to enact a move from
        one solution to a neighbor solution. The function must take
        the solution as input along with a `seed` input to control
        random number generation (see the `seed` input here).
        Your function should maintain the solution as a cycle with
        equal first and last node and all others appearing once.
        Your function should return the new solution.

    max_iterations : int, optional (default=10)
        Declared done when this number of consecutive iterations of
        the outer loop occurs without any change in the best cost solution.

    N_inner : int, optional (default=100)
        The number of iterations of the inner loop.

    alpha : float between (0, 1), optional (default=0.1)
        Percentage of threshold decrease when there is at
        least one acceptance of a neighbor solution.
        If no inner loop moves are accepted the threshold remains unchanged.

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    cycle : list of nodes
        Returns the cycle (list of nodes) that a salesman
        can follow to minimize total weight of the trip.

    Raises
    ------
    NetworkXError
        If `G` is not complete the algorithm raises an exception.

    Examples
    --------
    >>> from networkx.algorithms import approximation as approx
    >>> G = nx.DiGraph()
    >>> G.add_weighted_edges_from(
    ...     {
    ...         ("A", "B", 3),
    ...         ("A", "C", 17),
    ...         ("A", "D", 14),
    ...         ("B", "A", 3),
    ...         ("B", "C", 12),
    ...         ("B", "D", 16),
    ...         ("C", "A", 13),
    ...         ("C", "B", 12),
    ...         ("C", "D", 4),
    ...         ("D", "A", 14),
    ...         ("D", "B", 15),
    ...         ("D", "C", 2),
    ...     }
    ... )
    >>> cycle = approx.threshold_accepting_tsp(G, "greedy", source="D")
    >>> cost = sum(G[n][nbr]["weight"] for n, nbr in nx.utils.pairwise(cycle))
    >>> cycle
    ['D', 'C', 'B', 'A', 'D']
    >>> cost
    31
    >>> incycle = ["D", "B", "A", "C", "D"]
    >>> cycle = approx.threshold_accepting_tsp(G, incycle, source="D")
    >>> cost = sum(G[n][nbr]["weight"] for n, nbr in nx.utils.pairwise(cycle))
    >>> cycle
    ['D', 'C', 'B', 'A', 'D']
    >>> cost
    31

    Notes
    -----
    Threshold Accepting is a metaheuristic local search algorithm.
    The main characteristic of this algorithm is that it accepts
    even solutions which lead to the increase of the cost in order
    to escape from low quality local optimal solutions.

    This algorithm needs an initial solution. This solution can be
    constructed by a simple greedy algorithm. At every iteration, it
    selects thoughtfully a neighbor solution.
    Consider $c(x)$ cost of current solution and $c(x')$ cost of
    neighbor solution.
    If $c(x') - c(x) <= threshold$ then the neighbor solution becomes the current
    solution for the next iteration, where the threshold is named threshold.

    In comparison to the Simulated Annealing algorithm, the Threshold
    Accepting algorithm does not accept very low quality solutions
    (due to the presence of the threshold value). In the case of
    Simulated Annealing, even a very low quality solution can
    be accepted with probability $p$.

    Time complexity:
    It has a running time $O(m * n * |V|)$ where $m$ and $n$ are the number
    of times the outer and inner loop run respectively.

    For more information and how algorithm is inspired see:
    https://doi.org/10.1016/0021-9991(90)90201-B

    See Also
    --------
    simulated_annealing_tsp

    """
    if move == "1-1":
        move = swap_two_nodes
    elif move == "1-0":
        move = move_one_node
    if init_cycle == "greedy":
        # Construct an initial solution using a greedy algorithm.
        cycle = greedy_tsp(G, weight=weight, source=source)
        if G.number_of_nodes() == 2:
            return cycle

    else:
        cycle = list(init_cycle)
        if source is None:
            source = cycle[0]
        elif source != cycle[0]:
            raise nx.NetworkXError("source must be first node in init_cycle")
        if cycle[0] != cycle[-1]:
            raise nx.NetworkXError("init_cycle must be a cycle. (return to start)")

        if len(cycle) - 1 != len(G) or len(set(G.nbunch_iter(cycle))) != len(G):
            raise nx.NetworkXError("init_cycle is not all and only nodes.")

        # Check that G is a complete graph
        N = len(G) - 1
        # This check ignores selfloops which is what we want here.
        if any(len(nbrdict) - (n in nbrdict) != N for n, nbrdict in G.adj.items()):
            raise nx.NetworkXError("G must be a complete graph.")

        if G.number_of_nodes() == 2:
            neighbor = list(G.neighbors(source))[0]
            return [source, neighbor, source]

    # Find the cost of initial solution
    cost = sum(G[u][v].get(weight, 1) for u, v in pairwise(cycle))

    count = 0
    best_cycle = cycle.copy()
    best_cost = cost
    while count <= max_iterations:
        count += 1
        accepted = False
        for i in range(N_inner):
            adj_sol = move(cycle, seed)
            adj_cost = sum(G[u][v].get(weight, 1) for u, v in pairwise(adj_sol))
            delta = adj_cost - cost
            if delta <= threshold:
                accepted = True

                # Set current solution the adjacent solution.
                cycle = adj_sol
                cost = adj_cost

                if cost < best_cost:
                    count = 0
                    best_cycle = cycle.copy()
                    best_cost = cost
        if accepted:
            threshold -= threshold * alpha

    return best_cycle
