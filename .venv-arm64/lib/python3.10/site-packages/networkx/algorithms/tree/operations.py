"""Operations on trees."""

from functools import partial
from itertools import accumulate, chain

import networkx as nx

__all__ = ["join_trees"]


# Argument types don't match dispatching, but allow manual selection of backend
@nx._dispatchable(graphs=None, returns_graph=True)
def join_trees(rooted_trees, *, label_attribute=None, first_label=0):
    """Returns a new rooted tree made by joining `rooted_trees`

    Constructs a new tree by joining each tree in `rooted_trees`.
    A new root node is added and connected to each of the roots
    of the input trees. While copying the nodes from the trees,
    relabeling to integers occurs. If the `label_attribute` is provided,
    the old node labels will be stored in the new tree under this attribute.

    Parameters
    ----------
    rooted_trees : list
        A list of pairs in which each left element is a NetworkX graph
        object representing a tree and each right element is the root
        node of that tree. The nodes of these trees will be relabeled to
        integers.

    label_attribute : str
        If provided, the old node labels will be stored in the new tree
        under this node attribute. If not provided, the original labels
        of the nodes in the input trees are not stored.

    first_label : int, optional (default=0)
        Specifies the label for the new root node. If provided, the root node of the joined tree
        will have this label. If not provided, the root node will default to a label of 0.

    Returns
    -------
    NetworkX graph
        The rooted tree resulting from joining the provided `rooted_trees`. The new tree has a root node
        labeled as specified by `first_label` (defaulting to 0 if not provided). Subtrees from the input
        `rooted_trees` are attached to this new root node. Each non-root node, if the `label_attribute`
        is provided, has an attribute that indicates the original label of the node in the input tree.

    Notes
    -----
    Trees are stored in NetworkX as NetworkX Graphs. There is no specific
    enforcement of the fact that these are trees. Testing for each tree
    can be done using :func:`networkx.is_tree`.

    Graph, edge, and node attributes are propagated from the given
    rooted trees to the created tree. If there are any overlapping graph
    attributes, those from later trees will overwrite those from earlier
    trees in the tuple of positional arguments.

    Examples
    --------
    Join two full balanced binary trees of height *h* to get a full
    balanced binary tree of depth *h* + 1::

        >>> h = 4
        >>> left = nx.balanced_tree(2, h)
        >>> right = nx.balanced_tree(2, h)
        >>> joined_tree = nx.join_trees([(left, 0), (right, 0)])
        >>> nx.is_isomorphic(joined_tree, nx.balanced_tree(2, h + 1))
        True

    """
    if not rooted_trees:
        return nx.empty_graph(1)

    # Unzip the zipped list of (tree, root) pairs.
    trees, roots = zip(*rooted_trees)

    # The join of the trees has the same type as the type of the first tree.
    R = type(trees[0])()

    lengths = (len(tree) for tree in trees[:-1])
    first_labels = list(accumulate(lengths, initial=first_label + 1))

    new_roots = []
    for tree, root, first_node in zip(trees, roots, first_labels):
        new_root = first_node + list(tree.nodes()).index(root)
        new_roots.append(new_root)

    # Relabel the nodes so that their union is the integers starting at first_label.
    relabel = partial(
        nx.convert_node_labels_to_integers, label_attribute=label_attribute
    )
    new_trees = [
        relabel(tree, first_label=first_label)
        for tree, first_label in zip(trees, first_labels)
    ]

    # Add all sets of nodes and edges, attributes
    for tree in new_trees:
        R.update(tree)

    # Finally, join the subtrees at the root. We know first_label is unused by the way we relabeled the subtrees.
    R.add_node(first_label)
    R.add_edges_from((first_label, root) for root in new_roots)

    return R
