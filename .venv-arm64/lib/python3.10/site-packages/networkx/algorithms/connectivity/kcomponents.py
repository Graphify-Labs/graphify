"""
Moody and White algorithm for k-components
"""

from collections import defaultdict
from itertools import combinations
from operator import itemgetter

import networkx as nx

# Define the default maximum flow function.
from networkx.algorithms.flow import edmonds_karp
from networkx.utils import not_implemented_for

default_flow_func = edmonds_karp

__all__ = ["k_components"]


@not_implemented_for("directed")
@nx._dispatchable
def k_components(G, flow_func=None):
    r"""Returns the k-component structure of a graph G.

    A `k`-component is a maximal subgraph of a graph G that has, at least,
    node connectivity `k`: we need to remove at least `k` nodes to break it
    into more components. `k`-components have an inherent hierarchical
    structure because they are nested in terms of connectivity: a connected
    graph can contain several 2-components, each of which can contain
    one or more 3-components, and so forth.

    Parameters
    ----------
    G : NetworkX graph

    flow_func : function
        Function to perform the underlying flow computations. Default value
        :meth:`edmonds_karp`. This function performs better in sparse graphs with
        right tailed degree distributions. :meth:`shortest_augmenting_path` will
        perform better in denser graphs.

    Returns
    -------
    k_components : dict
        Dictionary with all connectivity levels `k` in the input Graph as keys
        and a list of sets of nodes that form a k-component of level `k` as
        values.

    Raises
    ------
    NetworkXNotImplemented
        If the input graph is directed.

    Examples
    --------
    >>> # Petersen graph has 10 nodes and it is triconnected, thus all
    >>> # nodes are in a single component on all three connectivity levels
    >>> G = nx.petersen_graph()
    >>> k_components = nx.k_components(G)

    Notes
    -----
    Moody and White [1]_ (appendix A) provide an algorithm for identifying
    k-components in a graph, which is based on Kanevsky's algorithm [2]_
    for finding all minimum-size node cut-sets of a graph (implemented in
    :meth:`all_node_cuts` function):

        1. Compute node connectivity, k, of the input graph G.

        2. Identify all k-cutsets at the current level of connectivity using
           Kanevsky's algorithm.

        3. Generate new graph components based on the removal of
           these cutsets. Nodes in a cutset belong to both sides
           of the induced cut.

        4. If the graph is neither complete nor trivial, return to 1;
           else end.

    This implementation also uses some heuristics (see [3]_ for details)
    to speed up the computation.

    See also
    --------
    node_connectivity
    all_node_cuts
    biconnected_components : special case of this function when k=2
    k_edge_components : similar to this function, but uses edge-connectivity
        instead of node-connectivity

    References
    ----------
    .. [1]  Moody, J. and D. White (2003). Social cohesion and embeddedness:
            A hierarchical conception of social groups.
            American Sociological Review 68(1), 103--28.
            http://www2.asanet.org/journals/ASRFeb03MoodyWhite.pdf

    .. [2]  Kanevsky, A. (1993). Finding all minimum-size separating vertex
            sets in a graph. Networks 23(6), 533--541.
            http://onlinelibrary.wiley.com/doi/10.1002/net.3230230604/abstract

    .. [3]  Torrents, J. and F. Ferraro (2015). Structural Cohesion:
            Visualization and Heuristics for Fast Computation.
            https://arxiv.org/pdf/1503.04476v1

    """
    # Dictionary with connectivity level (k) as keys and a list of
    # sets of nodes that form a k-component as values. Note that
    # k-components can overlap (but only k - 1 nodes).
    k_components = defaultdict(list)
    # Define default flow function
    if flow_func is None:
        flow_func = default_flow_func
    # Bicomponents as a base to check for higher order k-components
    for component in nx.connected_components(G):
        # isolated nodes have connectivity 0
        comp = set(component)
        if len(comp) > 1:
            k_components[1].append(comp)
    bicomponents = [G.subgraph(c) for c in nx.biconnected_components(G)]
    for bicomponent in bicomponents:
        bicomp = set(bicomponent)
        # avoid considering dyads as bicomponents
        if len(bicomp) > 2:
            k_components[2].append(bicomp)
    for B in bicomponents:
        if len(B) <= 2:
            continue
        k = nx.node_connectivity(B, flow_func=flow_func)
        if k > 2:
            k_components[k].append(set(B))
        # Perform cuts in a DFS like order.
        cuts = list(nx.all_node_cuts(B, k=k, flow_func=flow_func))
        stack = [(k, _generate_partition(B, cuts, k))]
        while stack:
            (parent_k, partition) = stack[-1]
            try:
                nodes = next(partition)
                C = B.subgraph(nodes)
                this_k = nx.node_connectivity(C, flow_func=flow_func)
                if this_k > parent_k and this_k > 2:
                    k_components[this_k].append(set(C))
                cuts = list(nx.all_node_cuts(C, k=this_k, flow_func=flow_func))
                if cuts:
                    stack.append((this_k, _generate_partition(C, cuts, this_k)))
            except StopIteration:
                stack.pop()

    # This is necessary because k-components may only be reported at their
    # maximum k level. But we want to return a dictionary in which keys are
    # connectivity levels and values list of sets of components, without
    # skipping any connectivity level. Also, it's possible that subsets of
    # an already detected k-component appear at a level k. Checking for this
    # in the while loop above penalizes the common case. Thus we also have to
    # _consolidate all connectivity levels in _reconstruct_k_components.
    return _reconstruct_k_components(k_components)


def _consolidate(sets, k):
    """Merge sets that share k or more elements.

    See: http://rosettacode.org/wiki/Set_consolidation

    The iterative python implementation posted there is
    faster than this because of the overhead of building a
    Graph and calling nx.connected_components, but it's not
    clear for us if we can use it in NetworkX because there
    is no licence for the code.

    """
    G = nx.Graph()
    nodes = dict(enumerate(sets))
    G.add_nodes_from(nodes)
    G.add_edges_from(
        (u, v) for u, v in combinations(nodes, 2) if len(nodes[u] & nodes[v]) >= k
    )
    for component in nx.connected_components(G):
        yield set.union(*[nodes[n] for n in component])


def _generate_partition(G, cuts, k):
    def has_nbrs_in_partition(G, node, partition):
        return any(n in partition for n in G[node])

    components = []
    nodes = {n for n, d in G.degree() if d > k} - {n for cut in cuts for n in cut}
    H = G.subgraph(nodes)
    for cc in nx.connected_components(H):
        component = set(cc)
        for cut in cuts:
            for node in cut:
                if has_nbrs_in_partition(G, node, cc):
                    component.add(node)
        if len(component) < G.order():
            components.append(component)
    yield from _consolidate(components, k + 1)


def _reconstruct_k_components(k_comps):
    result = {}
    max_k = max(k_comps)
    for k in reversed(range(1, max_k + 1)):
        if k == max_k:
            result[k] = list(_consolidate(k_comps[k], k))
        elif k not in k_comps:
            result[k] = list(_consolidate(result[k + 1], k))
        else:
            nodes_at_k = set.union(*k_comps[k])
            to_add = [c for c in result[k + 1] if any(n not in nodes_at_k for n in c)]
            if to_add:
                result[k] = list(_consolidate(k_comps[k] + to_add, k))
            else:
                result[k] = list(_consolidate(k_comps[k], k))
    return result


def build_k_number_dict(kcomps):
    result = {}
    for k, comps in sorted(kcomps.items(), key=itemgetter(0)):
        for comp in comps:
            for node in comp:
                result[node] = k
    return result
