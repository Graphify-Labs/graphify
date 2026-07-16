"""
An algorithm for finding if two undirected trees are isomorphic,
and if so returns an isomorphism between the two sets of nodes.

This algorithm uses a routine to tell if two rooted trees (trees with a
specified root node) are isomorphic, which may be independently useful.

This implements an algorithm from:
The Design and Analysis of Computer Algorithms
by Aho, Hopcroft, and Ullman
Addison-Wesley Publishing 1974
Example 3.2 pp. 84-86.

A more understandable version of this algorithm is described in:
Homework Assignment 5
McGill University SOCS 308-250B, Winter 2002
by Matthew Suderman
http://crypto.cs.mcgill.ca/~crepeau/CS250/2004/HW5+.pdf
"""

import networkx as nx
from networkx.utils.decorators import not_implemented_for

__all__ = ["rooted_tree_isomorphism", "tree_isomorphism"]


@nx._dispatchable(graphs={"t1": 0, "t2": 2}, returns_graph=True)
def root_trees(t1, root1, t2, root2):
    """Create a single digraph dT of free trees t1 and t2
    #   with roots root1 and root2 respectively
    # rename the nodes with consecutive integers
    # so that all nodes get a unique name between both trees

    # our new "fake" root node is 0
    # t1 is numbers from 1 ... n
    # t2 is numbered from n+1 to 2n
    """

    dT = nx.DiGraph()

    newroot1 = 1  # left root will be 1
    newroot2 = nx.number_of_nodes(t1) + 1  # right will be n+1

    # may be overlap in node names here so need separate maps
    # given the old name, what is the new
    namemap1 = {root1: newroot1}
    namemap2 = {root2: newroot2}

    # add an edge from our new root to root1 and root2
    dT.add_edge(0, namemap1[root1])
    dT.add_edge(0, namemap2[root2])

    for i, (v1, v2) in enumerate(nx.bfs_edges(t1, root1)):
        namemap1[v2] = i + namemap1[root1] + 1
        dT.add_edge(namemap1[v1], namemap1[v2])

    for i, (v1, v2) in enumerate(nx.bfs_edges(t2, root2)):
        namemap2[v2] = i + namemap2[root2] + 1
        dT.add_edge(namemap2[v1], namemap2[v2])

    # now we really want the inverse of namemap1 and namemap2
    # giving the old name given the new
    # since the values of namemap1 and namemap2 are unique
    # there won't be collisions
    namemap = {}
    for old, new in namemap1.items():
        namemap[new] = old
    for old, new in namemap2.items():
        namemap[new] = old

    return (dT, namemap, newroot1, newroot2)


# figure out the level of each node, with 0 at root
@nx._dispatchable
def assign_levels(G, root):
    level = {}
    level[root] = 0
    for v1, v2 in nx.bfs_edges(G, root):
        level[v2] = level[v1] + 1

    return level


# now group the nodes at each level
def group_by_levels(levels):
    L = {}
    for n, lev in levels.items():
        if lev not in L:
            L[lev] = []
        L[lev].append(n)

    return L


# now lets get the isomorphism by walking the ordered_children
def generate_isomorphism(v, w, M, ordered_children):
    # make sure tree1 comes first
    assert v < w
    M.append((v, w))
    for i, (x, y) in enumerate(zip(ordered_children[v], ordered_children[w])):
        generate_isomorphism(x, y, M, ordered_children)


@nx._dispatchable(graphs={"t1": 0, "t2": 2})
def rooted_tree_isomorphism(t1, root1, t2, root2):
    """
    Given two rooted trees `t1` and `t2`,
    with roots `root1` and `root2` respectively
    this routine will determine if they are isomorphic.

    These trees may be either directed or undirected,
    but if they are directed, all edges should flow from the root.

    It returns the isomorphism, a mapping of the nodes of `t1` onto the nodes
    of `t2`, such that two trees are then identical.

    Note that two trees may have more than one isomorphism, and this
    routine just returns one valid mapping.

    Parameters
    ----------
    `t1` :  NetworkX graph
        One of the trees being compared

    `root1` : a node of `t1` which is the root of the tree

    `t2` : undirected NetworkX graph
        The other tree being compared

    `root2` : a node of `t2` which is the root of the tree

    This is a subroutine used to implement `tree_isomorphism`, but will
    be somewhat faster if you already have rooted trees.

    Returns
    -------
    isomorphism : list
        A list of pairs in which the left element is a node in `t1`
        and the right element is a node in `t2`.  The pairs are in
        arbitrary order.  If the nodes in one tree is mapped to the names in
        the other, then trees will be identical. Note that an isomorphism
        will not necessarily be unique.

        If `t1` and `t2` are not isomorphic, then it returns the empty list.
    """

    assert nx.is_tree(t1)
    assert nx.is_tree(t2)

    # get the rooted tree formed by combining them
    # with unique names
    (dT, namemap, newroot1, newroot2) = root_trees(t1, root1, t2, root2)

    # compute the distance from the root, with 0 for our
    levels = assign_levels(dT, 0)

    # height
    h = max(levels.values())

    # collect nodes into a dict by level
    L = group_by_levels(levels)

    # each node has a label, initially set to 0
    label = {v: 0 for v in dT}
    # and also ordered_labels and ordered_children
    # which will store ordered tuples
    ordered_labels = {v: () for v in dT}
    ordered_children = {v: () for v in dT}

    # nothing to do on last level so start on h-1
    # also nothing to do for our fake level 0, so skip that
    for i in range(h - 1, 0, -1):
        # update the ordered_labels and ordered_children
        # for any children
        for v in L[i]:
            # nothing to do if no children
            if dT.out_degree(v) > 0:
                # get all the pairs of labels and nodes of children
                # and sort by labels
                s = sorted((label[u], u) for u in dT.successors(v))

                # invert to give a list of two tuples
                # the sorted labels, and the corresponding children
                ordered_labels[v], ordered_children[v] = list(zip(*s))

        # now collect and sort the sorted ordered_labels
        # for all nodes in L[i], carrying along the node
        forlabel = sorted((ordered_labels[v], v) for v in L[i])

        # now assign labels to these nodes, according to the sorted order
        # starting from 0, where identical ordered_labels get the same label
        current = 0
        for i, (ol, v) in enumerate(forlabel):
            # advance to next label if not 0, and different from previous
            if (i != 0) and (ol != forlabel[i - 1][0]):
                current += 1
            label[v] = current

    # they are isomorphic if the labels of newroot1 and newroot2 are 0
    isomorphism = []
    if label[newroot1] == 0 and label[newroot2] == 0:
        generate_isomorphism(newroot1, newroot2, isomorphism, ordered_children)

        # get the mapping back in terms of the old names
        # return in sorted order for neatness
        isomorphism = [(namemap[u], namemap[v]) for (u, v) in isomorphism]

    return isomorphism


@not_implemented_for("directed")
@not_implemented_for("multigraph")
@nx._dispatchable(graphs={"t1": 0, "t2": 1})
def tree_isomorphism(t1, t2):
    """
    Given two undirected (or free) trees `t1` and `t2`,
    this routine will determine if they are isomorphic.
    It returns the isomorphism, a mapping of the nodes of `t1` onto the nodes
    of `t2`, such that two trees are then identical.

    Note that two trees may have more than one isomorphism, and this
    routine just returns one valid mapping.

    Parameters
    ----------
    t1 : undirected NetworkX graph
        One of the trees being compared

    t2 : undirected NetworkX graph
        The other tree being compared

    Returns
    -------
    isomorphism : list
        A list of pairs in which the left element is a node in `t1`
        and the right element is a node in `t2`.  The pairs are in
        arbitrary order.  If the nodes in one tree is mapped to the names in
        the other, then trees will be identical. Note that an isomorphism
        will not necessarily be unique.

        If `t1` and `t2` are not isomorphic, then it returns the empty list.

    Notes
    -----
    This runs in O(n*log(n)) time for trees with n nodes.
    """

    assert nx.is_tree(t1)
    assert nx.is_tree(t2)

    # To be isomorphic, t1 and t2 must have the same number of nodes.
    if nx.number_of_nodes(t1) != nx.number_of_nodes(t2):
        return []

    # Another shortcut is that the sorted degree sequences need to be the same.
    degree_sequence1 = sorted(d for (n, d) in t1.degree())
    degree_sequence2 = sorted(d for (n, d) in t2.degree())

    if degree_sequence1 != degree_sequence2:
        return []

    # A tree can have either 1 or 2 centers.
    # If the number doesn't match then t1 and t2 are not isomorphic.
    center1 = nx.center(t1)
    center2 = nx.center(t2)

    if len(center1) != len(center2):
        return []

    # If there is only 1 center in each, then use it.
    if len(center1) == 1:
        return rooted_tree_isomorphism(t1, center1[0], t2, center2[0])

    # If there both have 2 centers,  then try the first for t1
    # with the first for t2.
    attempts = rooted_tree_isomorphism(t1, center1[0], t2, center2[0])

    # If that worked we're done.
    if len(attempts) > 0:
        return attempts

    # Otherwise, try center1[0] with the center2[1], and see if that works
    return rooted_tree_isomorphism(t1, center1[0], t2, center2[1])
