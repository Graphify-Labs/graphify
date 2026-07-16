"""Helper functions for community-finding algorithms."""

import networkx as nx

__all__ = ["is_partition"]


@nx._dispatchable
def is_partition(G, communities):
    """Returns *True* if `communities` is a partition of the nodes of `G`.

    A partition of a universe set is a family of pairwise disjoint sets
    whose union is the entire universe set.

    Parameters
    ----------
    G : NetworkX graph.

    communities : list or iterable of sets of nodes
        If not a list, the iterable is converted internally to a list.
        If it is an iterator it is exhausted.

    """
    # Alternate implementation:
    # return all(sum(1 if v in c else 0 for c in communities) == 1 for v in G)
    if not isinstance(communities, list):
        communities = list(communities)
    nodes = {n for c in communities for n in c if n in G}

    return len(G) == len(nodes) == sum(len(c) for c in communities)
