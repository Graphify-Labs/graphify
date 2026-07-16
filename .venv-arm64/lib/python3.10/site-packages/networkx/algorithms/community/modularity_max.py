"""Functions for detecting communities based on modularity."""

from collections import defaultdict

import networkx as nx
from networkx.algorithms.community.quality import modularity
from networkx.utils import not_implemented_for
from networkx.utils.mapped_queue import MappedQueue

__all__ = [
    "greedy_modularity_communities",
    "naive_greedy_modularity_communities",
]


def _greedy_modularity_communities_generator(G, weight=None, resolution=1):
    r"""Yield community partitions of G and the modularity change at each step.

    This function performs Clauset-Newman-Moore greedy modularity maximization [2]_
    At each step of the process it yields the change in modularity that will occur in
    the next step followed by yielding the new community partition after that step.

    Greedy modularity maximization begins with each node in its own community
    and repeatedly joins the pair of communities that lead to the largest
    modularity until one community contains all nodes (the partition has one set).

    This function maximizes the generalized modularity, where `resolution`
    is the resolution parameter, often expressed as $\gamma$.
    See :func:`~networkx.algorithms.community.quality.modularity`.

    Parameters
    ----------
    G : NetworkX graph

    weight : string or None, optional (default=None)
        The name of an edge attribute that holds the numerical value used
        as a weight.  If None, then each edge has weight 1.
        The degree is the sum of the edge weights adjacent to the node.

    resolution : float (default=1)
        If resolution is less than 1, modularity favors larger communities.
        Greater than 1 favors smaller communities.

    Yields
    ------
    Alternating yield statements produce the following two objects:

    communities: dict_values
        A dict_values of frozensets of nodes, one for each community.
        This represents a partition of the nodes of the graph into communities.
        The first yield is the partition with each node in its own community.

    dq: float
        The change in modularity when merging the next two communities
        that leads to the largest modularity.

    See Also
    --------
    modularity

    References
    ----------
    .. [1] Newman, M. E. J. "Networks: An Introduction", page 224
       Oxford University Press 2011.
    .. [2] Clauset, A., Newman, M. E., & Moore, C.
       "Finding community structure in very large networks."
       Physical Review E 70(6), 2004.
    .. [3] Reichardt and Bornholdt "Statistical Mechanics of Community
       Detection" Phys. Rev. E74, 2006.
    .. [4] Newman, M. E. J."Analysis of weighted networks"
       Physical Review E 70(5 Pt 2):056131, 2004.
    """
    directed = G.is_directed()
    N = G.number_of_nodes()

    # Count edges (or the sum of edge-weights for weighted graphs)
    m = G.size(weight)
    q0 = 1 / m

    # Calculate degrees (notation from the papers)
    # a : the fraction of (weighted) out-degree for each node
    # b : the fraction of (weighted) in-degree for each node
    if directed:
        a = {node: deg_out * q0 for node, deg_out in G.out_degree(weight=weight)}
        b = {node: deg_in * q0 for node, deg_in in G.in_degree(weight=weight)}
    else:
        a = b = {node: deg * q0 * 0.5 for node, deg in G.degree(weight=weight)}

    # this preliminary step collects the edge weights for each node pair
    # It handles multigraph and digraph and works fine for graph.
    dq_dict = defaultdict(lambda: defaultdict(float))
    for u, v, wt in G.edges(data=weight, default=1):
        if u == v:
            continue
        dq_dict[u][v] += wt
        dq_dict[v][u] += wt

    # now scale and subtract the expected edge-weights term
    for u, nbrdict in dq_dict.items():
        for v, wt in nbrdict.items():
            dq_dict[u][v] = q0 * wt - resolution * (a[u] * b[v] + b[u] * a[v])

    # Use -dq to get a max_heap instead of a min_heap
    # dq_heap holds a heap for each node's neighbors
    dq_heap = {u: MappedQueue({(u, v): -dq for v, dq in dq_dict[u].items()}) for u in G}
    # H -> all_dq_heap holds a heap with the best items for each node
    H = MappedQueue([dq_heap[n].heap[0] for n in G if len(dq_heap[n]) > 0])

    # Initialize single-node communities
    communities = {n: frozenset([n]) for n in G}
    yield communities.values()

    # Merge the two communities that lead to the largest modularity
    while len(H) > 1:
        # Find best merge
        # Remove from heap of row maxes
        # Ties will be broken by choosing the pair with lowest min community id
        try:
            negdq, u, v = H.pop()
        except IndexError:
            break
        dq = -negdq
        yield dq
        # Remove best merge from row u heap
        dq_heap[u].pop()
        # Push new row max onto H
        if len(dq_heap[u]) > 0:
            H.push(dq_heap[u].heap[0])
        # If this element was also at the root of row v, we need to remove the
        # duplicate entry from H
        if dq_heap[v].heap[0] == (v, u):
            H.remove((v, u))
            # Remove best merge from row v heap
            dq_heap[v].remove((v, u))
            # Push new row max onto H
            if len(dq_heap[v]) > 0:
                H.push(dq_heap[v].heap[0])
        else:
            # Duplicate wasn't in H, just remove from row v heap
            dq_heap[v].remove((v, u))

        # Perform merge
        communities[v] = frozenset(communities[u] | communities[v])
        del communities[u]

        # Get neighbor communities connected to the merged communities
        u_nbrs = set(dq_dict[u])
        v_nbrs = set(dq_dict[v])
        all_nbrs = (u_nbrs | v_nbrs) - {u, v}
        both_nbrs = u_nbrs & v_nbrs
        # Update dq for merge of u into v
        for w in all_nbrs:
            # Calculate new dq value
            if w in both_nbrs:
                dq_vw = dq_dict[v][w] + dq_dict[u][w]
            elif w in v_nbrs:
                dq_vw = dq_dict[v][w] - resolution * (a[u] * b[w] + a[w] * b[u])
            else:  # w in u_nbrs
                dq_vw = dq_dict[u][w] - resolution * (a[v] * b[w] + a[w] * b[v])
            # Update rows v and w
            for row, col in [(v, w), (w, v)]:
                dq_heap_row = dq_heap[row]
                # Update dict for v,w only (u is removed below)
                dq_dict[row][col] = dq_vw
                # Save old max of per-row heap
                if len(dq_heap_row) > 0:
                    d_oldmax = dq_heap_row.heap[0]
                else:
                    d_oldmax = None
                # Add/update heaps
                d = (row, col)
                d_negdq = -dq_vw
                # Save old value for finding heap index
                if w in v_nbrs:
                    # Update existing element in per-row heap
                    dq_heap_row.update(d, d, priority=d_negdq)
                else:
                    # We're creating a new nonzero element, add to heap
                    dq_heap_row.push(d, priority=d_negdq)
                # Update heap of row maxes if necessary
                if d_oldmax is None:
                    # No entries previously in this row, push new max
                    H.push(d, priority=d_negdq)
                else:
                    # We've updated an entry in this row, has the max changed?
                    row_max = dq_heap_row.heap[0]
                    if d_oldmax != row_max or d_oldmax.priority != row_max.priority:
                        H.update(d_oldmax, row_max)

        # Remove row/col u from dq_dict matrix
        for w in dq_dict[u]:
            # Remove from dict
            dq_old = dq_dict[w][u]
            del dq_dict[w][u]
            # Remove from heaps if we haven't already
            if w != v:
                # Remove both row and column
                for row, col in [(w, u), (u, w)]:
                    dq_heap_row = dq_heap[row]
                    # Check if replaced dq is row max
                    d_old = (row, col)
                    if dq_heap_row.heap[0] == d_old:
                        # Update per-row heap and heap of row maxes
                        dq_heap_row.remove(d_old)
                        H.remove(d_old)
                        # Update row max
                        if len(dq_heap_row) > 0:
                            H.push(dq_heap_row.heap[0])
                    else:
                        # Only update per-row heap
                        dq_heap_row.remove(d_old)

        del dq_dict[u]
        # Mark row u as deleted, but keep placeholder
        dq_heap[u] = MappedQueue()
        # Merge u into v and update a
        a[v] += a[u]
        a[u] = 0
        if directed:
            b[v] += b[u]
            b[u] = 0

        yield communities.values()


@nx._dispatchable(edge_attrs="weight")
def greedy_modularity_communities(
    G,
    weight=None,
    resolution=1,
    cutoff=1,
    best_n=None,
):
    r"""Find communities in G using greedy modularity maximization.

    This function uses Clauset-Newman-Moore greedy modularity maximization [2]_
    to find the community partition with the largest modularity.

    Greedy modularity maximization begins with each node in its own community
    and repeatedly joins the pair of communities that lead to the largest
    modularity until no further increase in modularity is possible (a maximum).
    Two keyword arguments adjust the stopping condition. `cutoff` is a lower
    limit on the number of communities so you can stop the process before
    reaching a maximum (used to save computation time). `best_n` is an upper
    limit on the number of communities so you can make the process continue
    until at most n communities remain even if the maximum modularity occurs
    for more. To obtain exactly n communities, set both `cutoff` and `best_n` to n.

    This function maximizes the generalized modularity, where `resolution`
    is the resolution parameter, often expressed as $\gamma$.
    See :func:`~networkx.algorithms.community.quality.modularity`.

    Parameters
    ----------
    G : NetworkX graph

    weight : string or None, optional (default=None)
        The name of an edge attribute that holds the numerical value used
        as a weight.  If None, then each edge has weight 1.
        The degree is the sum of the edge weights adjacent to the node.

    resolution : float, optional (default=1)
        If resolution is less than 1, modularity favors larger communities.
        Greater than 1 favors smaller communities.

    cutoff : int, optional (default=1)
        A minimum number of communities below which the merging process stops.
        The process stops at this number of communities even if modularity
        is not maximized. The goal is to let the user stop the process early.
        The process stops before the cutoff if it finds a maximum of modularity.

    best_n : int or None, optional (default=None)
        A maximum number of communities above which the merging process will
        not stop. This forces community merging to continue after modularity
        starts to decrease until `best_n` communities remain.
        If ``None``, don't force it to continue beyond a maximum.

    Raises
    ------
    ValueError : If the `cutoff` or `best_n`  value is not in the range
        ``[1, G.number_of_nodes()]``, or if `best_n` < `cutoff`.

    Returns
    -------
    communities: list
        A list of frozensets of nodes, one for each community.
        Sorted by length with largest communities first.

    Examples
    --------
    >>> G = nx.karate_club_graph()
    >>> c = nx.community.greedy_modularity_communities(G)
    >>> sorted(c[0])
    [8, 14, 15, 18, 20, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33]

    See Also
    --------
    modularity

    References
    ----------
    .. [1] Newman, M. E. J. "Networks: An Introduction", page 224
       Oxford University Press 2011.
    .. [2] Clauset, A., Newman, M. E., & Moore, C.
       "Finding community structure in very large networks."
       Physical Review E 70(6), 2004.
    .. [3] Reichardt and Bornholdt "Statistical Mechanics of Community
       Detection" Phys. Rev. E74, 2006.
    .. [4] Newman, M. E. J."Analysis of weighted networks"
       Physical Review E 70(5 Pt 2):056131, 2004.
    """
    if not G.size():
        return [{n} for n in G]

    if (cutoff < 1) or (cutoff > G.number_of_nodes()):
        raise ValueError(f"cutoff must be between 1 and {len(G)}. Got {cutoff}.")
    if best_n is not None:
        if (best_n < 1) or (best_n > G.number_of_nodes()):
            raise ValueError(f"best_n must be between 1 and {len(G)}. Got {best_n}.")
        if best_n < cutoff:
            raise ValueError(f"Must have best_n >= cutoff. Got {best_n} < {cutoff}")
        if best_n == 1:
            return [set(G)]
    else:
        best_n = G.number_of_nodes()

    # retrieve generator object to construct output
    community_gen = _greedy_modularity_communities_generator(
        G, weight=weight, resolution=resolution
    )

    # construct the first best community
    communities = next(community_gen)

    # continue merging communities until one of the breaking criteria is satisfied
    while len(communities) > cutoff:
        try:
            dq = next(community_gen)
        # StopIteration occurs when communities are the connected components
        except StopIteration:
            communities = sorted(communities, key=len, reverse=True)
            # if best_n requires more merging, merge big sets for highest modularity
            while len(communities) > best_n:
                comm1, comm2, *rest = communities
                communities = [comm1 ^ comm2]
                communities.extend(rest)
            return communities

        # keep going unless max_mod is reached or best_n says to merge more
        if dq < 0 and len(communities) <= best_n:
            break
        communities = next(community_gen)

    return sorted(communities, key=len, reverse=True)


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable(edge_attrs="weight")
def naive_greedy_modularity_communities(G, resolution=1, weight=None):
    r"""Find communities in G using greedy modularity maximization.

    This implementation is O(n^4), much slower than alternatives, but it is
    provided as an easy-to-understand reference implementation.

    Greedy modularity maximization begins with each node in its own community
    and joins the pair of communities that most increases modularity until no
    such pair exists.

    This function maximizes the generalized modularity, where `resolution`
    is the resolution parameter, often expressed as $\gamma$.
    See :func:`~networkx.algorithms.community.quality.modularity`.

    Parameters
    ----------
    G : NetworkX graph
        Graph must be simple and undirected.

    resolution : float (default=1)
        If resolution is less than 1, modularity favors larger communities.
        Greater than 1 favors smaller communities.

    weight : string or None, optional (default=None)
        The name of an edge attribute that holds the numerical value used
        as a weight.  If None, then each edge has weight 1.
        The degree is the sum of the edge weights adjacent to the node.

    Returns
    -------
    list
        A list of sets of nodes, one for each community.
        Sorted by length with largest communities first.

    Examples
    --------
    >>> G = nx.karate_club_graph()
    >>> c = nx.community.naive_greedy_modularity_communities(G)
    >>> sorted(c[0])
    [8, 14, 15, 18, 20, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33]

    See Also
    --------
    greedy_modularity_communities
    modularity
    """
    # First create one community for each node
    communities = [frozenset([u]) for u in G.nodes()]
    # Track merges
    merges = []
    # Greedily merge communities until no improvement is possible
    old_modularity = None
    new_modularity = modularity(G, communities, resolution=resolution, weight=weight)
    while old_modularity is None or new_modularity > old_modularity:
        # Save modularity for comparison
        old_modularity = new_modularity
        # Find best pair to merge
        trial_communities = list(communities)
        to_merge = None
        for i, u in enumerate(communities):
            for j, v in enumerate(communities):
                # Skip i==j and empty communities
                if j <= i or len(u) == 0 or len(v) == 0:
                    continue
                # Merge communities u and v
                trial_communities[j] = u | v
                trial_communities[i] = frozenset([])
                trial_modularity = modularity(
                    G, trial_communities, resolution=resolution, weight=weight
                )
                if trial_modularity >= new_modularity:
                    # Check if strictly better or tie
                    if trial_modularity > new_modularity:
                        # Found new best, save modularity and group indexes
                        new_modularity = trial_modularity
                        to_merge = (i, j, new_modularity - old_modularity)
                    elif to_merge and min(i, j) < min(to_merge[0], to_merge[1]):
                        # Break ties by choosing pair with lowest min id
                        new_modularity = trial_modularity
                        to_merge = (i, j, new_modularity - old_modularity)
                # Un-merge
                trial_communities[i] = u
                trial_communities[j] = v
        if to_merge is not None:
            # If the best merge improves modularity, use it
            merges.append(to_merge)
            i, j, dq = to_merge
            u, v = communities[i], communities[j]
            communities[j] = u | v
            communities[i] = frozenset([])
    # Remove empty communities and sort
    return sorted((c for c in communities if len(c) > 0), key=len, reverse=True)
