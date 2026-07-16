"""
Kanevsky all minimum node k cutsets algorithm.
"""

import copy
from collections import defaultdict
from itertools import combinations
from operator import itemgetter

import networkx as nx
from networkx.algorithms.flow import (
    build_residual_network,
    edmonds_karp,
    shortest_augmenting_path,
)

from .utils import build_auxiliary_node_connectivity

default_flow_func = edmonds_karp


__all__ = ["all_node_cuts"]


@nx._dispatchable
def all_node_cuts(G, k=None, flow_func=None):
    r"""Returns all minimum k cutsets of an undirected graph G.

    This implementation is based on Kanevsky's algorithm [1]_ for finding all
    minimum-size node cut-sets of an undirected graph G; ie the set (or sets)
    of nodes of cardinality equal to the node connectivity of G. Thus if
    removed, would break G into two or more connected components.

    Parameters
    ----------
    G : NetworkX graph
        Undirected graph

    k : Integer
        Node connectivity of the input graph. If k is None, then it is
        computed. Default value: None.

    flow_func : function
        Function to perform the underlying flow computations. Default value is
        :func:`~networkx.algorithms.flow.edmonds_karp`. This function performs
        better in sparse graphs with right tailed degree distributions.
        :func:`~networkx.algorithms.flow.shortest_augmenting_path` will
        perform better in denser graphs.


    Returns
    -------
    cuts : a generator of node cutsets
        Each node cutset has cardinality equal to the node connectivity of
        the input graph.

    Examples
    --------
    >>> # A two-dimensional grid graph has 4 cutsets of cardinality 2
    >>> G = nx.grid_2d_graph(5, 5)
    >>> cutsets = list(nx.all_node_cuts(G))
    >>> len(cutsets)
    4
    >>> all(2 == len(cutset) for cutset in cutsets)
    True
    >>> nx.node_connectivity(G)
    2

    Notes
    -----
    This implementation is based on the sequential algorithm for finding all
    minimum-size separating vertex sets in a graph [1]_. The main idea is to
    compute minimum cuts using local maximum flow computations among a set
    of nodes of highest degree and all other non-adjacent nodes in the Graph.
    Once we find a minimum cut, we add an edge between the high degree
    node and the target node of the local maximum flow computation to make
    sure that we will not find that minimum cut again.

    See also
    --------
    node_connectivity
    edmonds_karp
    shortest_augmenting_path

    References
    ----------
    .. [1]  Kanevsky, A. (1993). Finding all minimum-size separating vertex
            sets in a graph. Networks 23(6), 533--541.
            http://onlinelibrary.wiley.com/doi/10.1002/net.3230230604/abstract

    """
    if not nx.is_connected(G):
        raise nx.NetworkXError("Input graph is disconnected.")

    # Address some corner cases first.
    # For complete Graphs

    if nx.density(G) == 1:
        yield from ()
        return

    # Initialize data structures.
    # Keep track of the cuts already computed so we do not repeat them.
    seen = []
    # Even-Tarjan reduction is what we call auxiliary digraph
    # for node connectivity.
    H = build_auxiliary_node_connectivity(G)
    H_nodes = H.nodes  # for speed
    mapping = H.graph["mapping"]
    # Keep a copy of original predecessors, H will be modified later.
    # Shallow copy is enough.
    original_H_pred = copy.copy(H._pred)
    R = build_residual_network(H, "capacity")
    kwargs = {"capacity": "capacity", "residual": R}
    # Define default flow function
    if flow_func is None:
        flow_func = default_flow_func
    if flow_func is shortest_augmenting_path:
        kwargs["two_phase"] = True
    # Begin the actual algorithm
    # step 1: Find node connectivity k of G
    if k is None:
        k = nx.node_connectivity(G, flow_func=flow_func)
    # step 2:
    # Find k nodes with top degree, call it X:
    X = {n for n, d in sorted(G.degree(), key=itemgetter(1), reverse=True)[:k]}
    # Check if X is a k-node-cutset
    if _is_separating_set(G, X):
        seen.append(X)
        yield X

    for x in X:
        # step 3: Compute local connectivity flow of x with all other
        # non adjacent nodes in G
        non_adjacent = set(G) - {x} - set(G[x])
        for v in non_adjacent:
            # step 4: compute maximum flow in an Even-Tarjan reduction H of G
            # and step 5: build the associated residual network R
            R = flow_func(H, f"{mapping[x]}B", f"{mapping[v]}A", **kwargs)
            flow_value = R.graph["flow_value"]

            if flow_value == k:
                # Find the nodes incident to the flow.
                E1 = flowed_edges = [
                    (u, w) for (u, w, d) in R.edges(data=True) if d["flow"] != 0
                ]
                VE1 = incident_nodes = {n for edge in E1 for n in edge}
                # Remove saturated edges form the residual network.
                # Note that reversed edges are introduced with capacity 0
                # in the residual graph and they need to be removed too.
                saturated_edges = [
                    (u, w, d)
                    for (u, w, d) in R.edges(data=True)
                    if d["capacity"] == d["flow"] or d["capacity"] == 0
                ]
                R.remove_edges_from(saturated_edges)
                R_closure = nx.transitive_closure(R)
                # step 6: shrink the strongly connected components of
                # residual flow network R and call it L.
                L = nx.condensation(R)
                cmap = L.graph["mapping"]
                inv_cmap = defaultdict(list)
                for n, scc in cmap.items():
                    inv_cmap[scc].append(n)
                # Find the incident nodes in the condensed graph.
                VE1 = {cmap[n] for n in VE1}
                # step 7: Compute all antichains of L;
                # they map to closed sets in H.
                # Any edge in H that links a closed set is part of a cutset.
                for antichain in nx.antichains(L):
                    # Only antichains that are subsets of incident nodes counts.
                    # Lemma 8 in reference.
                    if not set(antichain).issubset(VE1):
                        continue
                    # Nodes in an antichain of the condensation graph of
                    # the residual network map to a closed set of nodes that
                    # define a node partition of the auxiliary digraph H
                    # through taking all of antichain's predecessors in the
                    # transitive closure.
                    S = set()
                    for scc in antichain:
                        S.update(inv_cmap[scc])
                    S_ancestors = set()
                    for n in S:
                        S_ancestors.update(R_closure._pred[n])
                    S.update(S_ancestors)
                    if f"{mapping[x]}B" not in S or f"{mapping[v]}A" in S:
                        continue
                    # Find the cutset that links the node partition (S,~S) in H
                    cutset = set()
                    for u in S:
                        cutset.update((u, w) for w in original_H_pred[u] if w not in S)
                    # The edges in H that form the cutset are internal edges
                    # (ie edges that represent a node of the original graph G)
                    if any(H_nodes[u]["id"] != H_nodes[w]["id"] for u, w in cutset):
                        continue
                    node_cut = {H_nodes[u]["id"] for u, _ in cutset}

                    if len(node_cut) == k:
                        # The cut is invalid if it includes internal edges of
                        # end nodes. The other half of Lemma 8 in ref.
                        if x in node_cut or v in node_cut:
                            continue
                        if node_cut not in seen:
                            yield node_cut
                            seen.append(node_cut)

                # Add an edge (x, v) to make sure that we do not
                # find this cutset again. This is equivalent
                # of adding the edge in the input graph
                # G.add_edge(x, v) and then regenerate H and R:
                # Add edges to the auxiliary digraph.
                # See build_residual_network for convention we used
                # in residual graphs.
                H.add_edge(f"{mapping[x]}B", f"{mapping[v]}A", capacity=1)
                H.add_edge(f"{mapping[v]}B", f"{mapping[x]}A", capacity=1)
                # Add edges to the residual network.
                R.add_edge(f"{mapping[x]}B", f"{mapping[v]}A", capacity=1)
                R.add_edge(f"{mapping[v]}A", f"{mapping[x]}B", capacity=0)
                R.add_edge(f"{mapping[v]}B", f"{mapping[x]}A", capacity=1)
                R.add_edge(f"{mapping[x]}A", f"{mapping[v]}B", capacity=0)

                # Add again the saturated edges to reuse the residual network
                R.add_edges_from(saturated_edges)


def _is_separating_set(G, cut):
    """Assumes that the input graph is connected"""
    if len(cut) == len(G) - 1:
        return True

    H = nx.restricted_view(G, cut, [])
    if nx.is_connected(H):
        return False
    return True
