"""Algorithm to select influential nodes in a graph using VoteRank."""

import networkx as nx

__all__ = ["voterank"]


@nx._dispatchable
def voterank(G, number_of_nodes=None):
    """Select a list of influential nodes in a graph using VoteRank algorithm

    VoteRank [1]_ computes a ranking of the nodes in a graph G based on a
    voting scheme. With VoteRank, all nodes vote for each of its in-neighbors
    and the node with the highest votes is elected iteratively. The voting
    ability of out-neighbors of elected nodes is decreased in subsequent turns.

    Parameters
    ----------
    G : graph
        A NetworkX graph.

    number_of_nodes : integer, optional
        Number of ranked nodes to extract (default all nodes).

    Returns
    -------
    voterank : list
        Ordered list of computed seeds.
        Only nodes with positive number of votes are returned.

    Examples
    --------
    >>> G = nx.Graph([(0, 1), (0, 2), (0, 3), (1, 4)])
    >>> nx.voterank(G)
    [0, 1]

    The algorithm can be used both for undirected and directed graphs.
    However, the directed version is different in two ways:
    (i) nodes only vote for their in-neighbors and
    (ii) only the voting ability of elected node and its out-neighbors are updated:

    >>> G = nx.DiGraph([(0, 1), (2, 1), (2, 3), (3, 4)])
    >>> nx.voterank(G)
    [2, 3]

    Notes
    -----
    Each edge is treated independently in case of multigraphs.

    References
    ----------
    .. [1] Zhang, J.-X. et al. (2016).
        Identifying a set of influential spreaders in complex networks.
        Sci. Rep. 6, 27823; doi: 10.1038/srep27823.
    """
    influential_nodes = []
    vote_rank = {}
    if len(G) == 0:
        return influential_nodes
    if number_of_nodes is None or number_of_nodes > len(G):
        number_of_nodes = len(G)
    if G.is_directed():
        # For directed graphs compute average out-degree
        avgDegree = sum(deg for _, deg in G.out_degree()) / len(G)
    else:
        # For undirected graphs compute average degree
        avgDegree = sum(deg for _, deg in G.degree()) / len(G)
    # step 1 - initiate all nodes to (0,1) (score, voting ability)
    for n in G.nodes():
        vote_rank[n] = [0, 1]
    # Repeat steps 1b to 4 until num_seeds are elected.
    for _ in range(number_of_nodes):
        # step 1b - reset rank
        for n in G.nodes():
            vote_rank[n][0] = 0
        # step 2 - vote
        for n, nbr in G.edges():
            # In directed graphs nodes only vote for their in-neighbors
            vote_rank[n][0] += vote_rank[nbr][1]
            if not G.is_directed():
                vote_rank[nbr][0] += vote_rank[n][1]
        for n in influential_nodes:
            vote_rank[n][0] = 0
        # step 3 - select top node
        n = max(G.nodes, key=lambda x: vote_rank[x][0])
        if vote_rank[n][0] == 0:
            return influential_nodes
        influential_nodes.append(n)
        # weaken the selected node
        vote_rank[n] = [0, 0]
        # step 4 - update voterank properties
        for _, nbr in G.edges(n):
            vote_rank[nbr][1] -= 1 / avgDegree
            vote_rank[nbr][1] = max(vote_rank[nbr][1], 0)
    return influential_nodes
