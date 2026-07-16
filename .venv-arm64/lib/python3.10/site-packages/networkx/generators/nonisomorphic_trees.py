"""
Implementation of the Wright, Richmond, Odlyzko and McKay (WROM)
algorithm for the enumeration of all non-isomorphic free trees of a
given order.  Rooted trees are represented by level sequences, i.e.,
lists in which the i-th element specifies the distance of vertex i to
the root.

"""

__all__ = ["nonisomorphic_trees", "number_of_nonisomorphic_trees"]

import networkx as nx


@nx._dispatchable(graphs=None, returns_graph=True)
def nonisomorphic_trees(order, create="graph"):
    """Generates lists of nonisomorphic trees

    Parameters
    ----------
    order : int
       order of the desired tree(s)

    create : one of {"graph", "matrix"} (default="graph")
       If ``"graph"`` is selected a list of ``Graph`` instances will be returned,
       if matrix is selected a list of adjacency matrices will be returned.

       .. deprecated:: 3.3

          The `create` argument is deprecated and will be removed in NetworkX
          version 3.5. In the future, `nonisomorphic_trees` will yield graph
          instances by default. To generate adjacency matrices, call
          ``nx.to_numpy_array`` on the output, e.g.::

             [nx.to_numpy_array(G) for G in nx.nonisomorphic_trees(N)]

    Yields
    ------
    list
       A list of nonisomorphic trees, in one of two formats depending on the
       value of the `create` parameter:
       - ``create="graph"``: yields a list of `networkx.Graph` instances
       - ``create="matrix"``: yields a list of list-of-lists representing adjacency matrices
    """

    if order < 2:
        raise ValueError
    # start at the path graph rooted at its center
    layout = list(range(order // 2 + 1)) + list(range(1, (order + 1) // 2))

    while layout is not None:
        layout = _next_tree(layout)
        if layout is not None:
            if create == "graph":
                yield _layout_to_graph(layout)
            elif create == "matrix":
                import warnings

                warnings.warn(
                    (
                        "\n\nThe 'create=matrix' argument of nonisomorphic_trees\n"
                        "is deprecated and will be removed in version 3.5.\n"
                        "Use ``nx.to_numpy_array`` to convert graphs to adjacency "
                        "matrices, e.g.::\n\n"
                        "   [nx.to_numpy_array(G) for G in nx.nonisomorphic_trees(N)]"
                    ),
                    category=DeprecationWarning,
                    stacklevel=2,
                )

                yield _layout_to_matrix(layout)
            layout = _next_rooted_tree(layout)


@nx._dispatchable(graphs=None)
def number_of_nonisomorphic_trees(order):
    """Returns the number of nonisomorphic trees

    Parameters
    ----------
    order : int
      order of the desired tree(s)

    Returns
    -------
    length : Number of nonisomorphic graphs for the given order

    References
    ----------

    """
    return sum(1 for _ in nonisomorphic_trees(order))


def _next_rooted_tree(predecessor, p=None):
    """One iteration of the Beyer-Hedetniemi algorithm."""

    if p is None:
        p = len(predecessor) - 1
        while predecessor[p] == 1:
            p -= 1
    if p == 0:
        return None

    q = p - 1
    while predecessor[q] != predecessor[p] - 1:
        q -= 1
    result = list(predecessor)
    for i in range(p, len(result)):
        result[i] = result[i - p + q]
    return result


def _next_tree(candidate):
    """One iteration of the Wright, Richmond, Odlyzko and McKay
    algorithm."""

    # valid representation of a free tree if:
    # there are at least two vertices at layer 1
    # (this is always the case because we start at the path graph)
    left, rest = _split_tree(candidate)

    # and the left subtree of the root
    # is less high than the tree with the left subtree removed
    left_height = max(left)
    rest_height = max(rest)
    valid = rest_height >= left_height

    if valid and rest_height == left_height:
        # and, if left and rest are of the same height,
        # if left does not encompass more vertices
        if len(left) > len(rest):
            valid = False
        # and, if they have the same number or vertices,
        # if left does not come after rest lexicographically
        elif len(left) == len(rest) and left > rest:
            valid = False

    if valid:
        return candidate
    else:
        # jump to the next valid free tree
        p = len(left)
        new_candidate = _next_rooted_tree(candidate, p)
        if candidate[p] > 2:
            new_left, new_rest = _split_tree(new_candidate)
            new_left_height = max(new_left)
            suffix = range(1, new_left_height + 2)
            new_candidate[-len(suffix) :] = suffix
        return new_candidate


def _split_tree(layout):
    """Returns a tuple of two layouts, one containing the left
    subtree of the root vertex, and one containing the original tree
    with the left subtree removed."""

    one_found = False
    m = None
    for i in range(len(layout)):
        if layout[i] == 1:
            if one_found:
                m = i
                break
            else:
                one_found = True

    if m is None:
        m = len(layout)

    left = [layout[i] - 1 for i in range(1, m)]
    rest = [0] + [layout[i] for i in range(m, len(layout))]
    return (left, rest)


def _layout_to_matrix(layout):
    """Create the adjacency matrix for the tree specified by the
    given layout (level sequence)."""

    result = [[0] * len(layout) for i in range(len(layout))]
    stack = []
    for i in range(len(layout)):
        i_level = layout[i]
        if stack:
            j = stack[-1]
            j_level = layout[j]
            while j_level >= i_level:
                stack.pop()
                j = stack[-1]
                j_level = layout[j]
            result[i][j] = result[j][i] = 1
        stack.append(i)
    return result


def _layout_to_graph(layout):
    """Create a NetworkX Graph for the tree specified by the
    given layout(level sequence)"""
    G = nx.Graph()
    stack = []
    for i in range(len(layout)):
        i_level = layout[i]
        if stack:
            j = stack[-1]
            j_level = layout[j]
            while j_level >= i_level:
                stack.pop()
                j = stack[-1]
                j_level = layout[j]
            G.add_edge(i, j)
        stack.append(i)
    return G
