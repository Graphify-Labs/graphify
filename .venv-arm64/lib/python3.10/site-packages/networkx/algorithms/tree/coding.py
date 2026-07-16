"""Functions for encoding and decoding trees.

Since a tree is a highly restricted form of graph, it can be represented
concisely in several ways. This module includes functions for encoding
and decoding trees in the form of nested tuples and Prüfer
sequences. The former requires a rooted tree, whereas the latter can be
applied to unrooted trees. Furthermore, there is a bijection from Prüfer
sequences to labeled trees.

"""

from collections import Counter
from itertools import chain

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = [
    "from_nested_tuple",
    "from_prufer_sequence",
    "NotATree",
    "to_nested_tuple",
    "to_prufer_sequence",
]


class NotATree(nx.NetworkXException):
    """Raised when a function expects a tree (that is, a connected
    undirected graph with no cycles) but gets a non-tree graph as input
    instead.

    """


@not_implemented_for("directed")
@nx._dispatchable(graphs="T")
def to_nested_tuple(T, root, canonical_form=False):
    """Returns a nested tuple representation of the given tree.

    The nested tuple representation of a tree is defined
    recursively. The tree with one node and no edges is represented by
    the empty tuple, ``()``. A tree with ``k`` subtrees is represented
    by a tuple of length ``k`` in which each element is the nested tuple
    representation of a subtree.

    Parameters
    ----------
    T : NetworkX graph
        An undirected graph object representing a tree.

    root : node
        The node in ``T`` to interpret as the root of the tree.

    canonical_form : bool
        If ``True``, each tuple is sorted so that the function returns
        a canonical form for rooted trees. This means "lighter" subtrees
        will appear as nested tuples before "heavier" subtrees. In this
        way, each isomorphic rooted tree has the same nested tuple
        representation.

    Returns
    -------
    tuple
        A nested tuple representation of the tree.

    Notes
    -----
    This function is *not* the inverse of :func:`from_nested_tuple`; the
    only guarantee is that the rooted trees are isomorphic.

    See also
    --------
    from_nested_tuple
    to_prufer_sequence

    Examples
    --------
    The tree need not be a balanced binary tree::

        >>> T = nx.Graph()
        >>> T.add_edges_from([(0, 1), (0, 2), (0, 3)])
        >>> T.add_edges_from([(1, 4), (1, 5)])
        >>> T.add_edges_from([(3, 6), (3, 7)])
        >>> root = 0
        >>> nx.to_nested_tuple(T, root)
        (((), ()), (), ((), ()))

    Continuing the above example, if ``canonical_form`` is ``True``, the
    nested tuples will be sorted::

        >>> nx.to_nested_tuple(T, root, canonical_form=True)
        ((), ((), ()), ((), ()))

    Even the path graph can be interpreted as a tree::

        >>> T = nx.path_graph(4)
        >>> root = 0
        >>> nx.to_nested_tuple(T, root)
        ((((),),),)

    """

    def _make_tuple(T, root, _parent):
        """Recursively compute the nested tuple representation of the
        given rooted tree.

        ``_parent`` is the parent node of ``root`` in the supertree in
        which ``T`` is a subtree, or ``None`` if ``root`` is the root of
        the supertree. This argument is used to determine which
        neighbors of ``root`` are children and which is the parent.

        """
        # Get the neighbors of `root` that are not the parent node. We
        # are guaranteed that `root` is always in `T` by construction.
        children = set(T[root]) - {_parent}
        if len(children) == 0:
            return ()
        nested = (_make_tuple(T, v, root) for v in children)
        if canonical_form:
            nested = sorted(nested)
        return tuple(nested)

    # Do some sanity checks on the input.
    if not nx.is_tree(T):
        raise nx.NotATree("provided graph is not a tree")
    if root not in T:
        raise nx.NodeNotFound(f"Graph {T} contains no node {root}")

    return _make_tuple(T, root, None)


@nx._dispatchable(graphs=None, returns_graph=True)
def from_nested_tuple(sequence, sensible_relabeling=False):
    """Returns the rooted tree corresponding to the given nested tuple.

    The nested tuple representation of a tree is defined
    recursively. The tree with one node and no edges is represented by
    the empty tuple, ``()``. A tree with ``k`` subtrees is represented
    by a tuple of length ``k`` in which each element is the nested tuple
    representation of a subtree.

    Parameters
    ----------
    sequence : tuple
        A nested tuple representing a rooted tree.

    sensible_relabeling : bool
        Whether to relabel the nodes of the tree so that nodes are
        labeled in increasing order according to their breadth-first
        search order from the root node.

    Returns
    -------
    NetworkX graph
        The tree corresponding to the given nested tuple, whose root
        node is node 0. If ``sensible_labeling`` is ``True``, nodes will
        be labeled in breadth-first search order starting from the root
        node.

    Notes
    -----
    This function is *not* the inverse of :func:`to_nested_tuple`; the
    only guarantee is that the rooted trees are isomorphic.

    See also
    --------
    to_nested_tuple
    from_prufer_sequence

    Examples
    --------
    Sensible relabeling ensures that the nodes are labeled from the root
    starting at 0::

        >>> balanced = (((), ()), ((), ()))
        >>> T = nx.from_nested_tuple(balanced, sensible_relabeling=True)
        >>> edges = [(0, 1), (0, 2), (1, 3), (1, 4), (2, 5), (2, 6)]
        >>> all((u, v) in T.edges() or (v, u) in T.edges() for (u, v) in edges)
        True

    """

    def _make_tree(sequence):
        """Recursively creates a tree from the given sequence of nested
        tuples.

        This function employs the :func:`~networkx.tree.join` function
        to recursively join subtrees into a larger tree.

        """
        # The empty sequence represents the empty tree, which is the
        # (unique) graph with a single node. We mark the single node
        # with an attribute that indicates that it is the root of the
        # graph.
        if len(sequence) == 0:
            return nx.empty_graph(1)
        # For a nonempty sequence, get the subtrees for each child
        # sequence and join all the subtrees at their roots. After
        # joining the subtrees, the root is node 0.
        return nx.tree.join_trees([(_make_tree(child), 0) for child in sequence])

    # Make the tree and remove the `is_root` node attribute added by the
    # helper function.
    T = _make_tree(sequence)
    if sensible_relabeling:
        # Relabel the nodes according to their breadth-first search
        # order, starting from the root node (that is, the node 0).
        bfs_nodes = chain([0], (v for u, v in nx.bfs_edges(T, 0)))
        labels = {v: i for i, v in enumerate(bfs_nodes)}
        # We would like to use `copy=False`, but `relabel_nodes` doesn't
        # allow a relabel mapping that can't be topologically sorted.
        T = nx.relabel_nodes(T, labels)
    return T


@not_implemented_for("directed")
@nx._dispatchable(graphs="T")
def to_prufer_sequence(T):
    r"""Returns the Prüfer sequence of the given tree.

    A *Prüfer sequence* is a list of *n* - 2 numbers between 0 and
    *n* - 1, inclusive. The tree corresponding to a given Prüfer
    sequence can be recovered by repeatedly joining a node in the
    sequence with a node with the smallest potential degree according to
    the sequence.

    Parameters
    ----------
    T : NetworkX graph
        An undirected graph object representing a tree.

    Returns
    -------
    list
        The Prüfer sequence of the given tree.

    Raises
    ------
    NetworkXPointlessConcept
        If the number of nodes in `T` is less than two.

    NotATree
        If `T` is not a tree.

    KeyError
        If the set of nodes in `T` is not {0, …, *n* - 1}.

    Notes
    -----
    There is a bijection from labeled trees to Prüfer sequences. This
    function is the inverse of the :func:`from_prufer_sequence`
    function.

    Sometimes Prüfer sequences use nodes labeled from 1 to *n* instead
    of from 0 to *n* - 1. This function requires nodes to be labeled in
    the latter form. You can use :func:`~networkx.relabel_nodes` to
    relabel the nodes of your tree to the appropriate format.

    This implementation is from [1]_ and has a running time of
    $O(n)$.

    See also
    --------
    to_nested_tuple
    from_prufer_sequence

    References
    ----------
    .. [1] Wang, Xiaodong, Lei Wang, and Yingjie Wu.
           "An optimal algorithm for Prufer codes."
           *Journal of Software Engineering and Applications* 2.02 (2009): 111.
           <https://doi.org/10.4236/jsea.2009.22016>

    Examples
    --------
    There is a bijection between Prüfer sequences and labeled trees, so
    this function is the inverse of the :func:`from_prufer_sequence`
    function:

    >>> edges = [(0, 3), (1, 3), (2, 3), (3, 4), (4, 5)]
    >>> tree = nx.Graph(edges)
    >>> sequence = nx.to_prufer_sequence(tree)
    >>> sequence
    [3, 3, 3, 4]
    >>> tree2 = nx.from_prufer_sequence(sequence)
    >>> list(tree2.edges()) == edges
    True

    """
    # Perform some sanity checks on the input.
    n = len(T)
    if n < 2:
        msg = "Prüfer sequence undefined for trees with fewer than two nodes"
        raise nx.NetworkXPointlessConcept(msg)
    if not nx.is_tree(T):
        raise nx.NotATree("provided graph is not a tree")
    if set(T) != set(range(n)):
        raise KeyError("tree must have node labels {0, ..., n - 1}")

    degree = dict(T.degree())

    def parents(u):
        return next(v for v in T[u] if degree[v] > 1)

    index = u = next(k for k in range(n) if degree[k] == 1)
    result = []
    for i in range(n - 2):
        v = parents(u)
        result.append(v)
        degree[v] -= 1
        if v < index and degree[v] == 1:
            u = v
        else:
            index = u = next(k for k in range(index + 1, n) if degree[k] == 1)
    return result


@nx._dispatchable(graphs=None, returns_graph=True)
def from_prufer_sequence(sequence):
    r"""Returns the tree corresponding to the given Prüfer sequence.

    A *Prüfer sequence* is a list of *n* - 2 numbers between 0 and
    *n* - 1, inclusive. The tree corresponding to a given Prüfer
    sequence can be recovered by repeatedly joining a node in the
    sequence with a node with the smallest potential degree according to
    the sequence.

    Parameters
    ----------
    sequence : list
        A Prüfer sequence, which is a list of *n* - 2 integers between
        zero and *n* - 1, inclusive.

    Returns
    -------
    NetworkX graph
        The tree corresponding to the given Prüfer sequence.

    Raises
    ------
    NetworkXError
        If the Prüfer sequence is not valid.

    Notes
    -----
    There is a bijection from labeled trees to Prüfer sequences. This
    function is the inverse of the :func:`from_prufer_sequence` function.

    Sometimes Prüfer sequences use nodes labeled from 1 to *n* instead
    of from 0 to *n* - 1. This function requires nodes to be labeled in
    the latter form. You can use :func:`networkx.relabel_nodes` to
    relabel the nodes of your tree to the appropriate format.

    This implementation is from [1]_ and has a running time of
    $O(n)$.

    References
    ----------
    .. [1] Wang, Xiaodong, Lei Wang, and Yingjie Wu.
           "An optimal algorithm for Prufer codes."
           *Journal of Software Engineering and Applications* 2.02 (2009): 111.
           <https://doi.org/10.4236/jsea.2009.22016>

    See also
    --------
    from_nested_tuple
    to_prufer_sequence

    Examples
    --------
    There is a bijection between Prüfer sequences and labeled trees, so
    this function is the inverse of the :func:`to_prufer_sequence`
    function:

    >>> edges = [(0, 3), (1, 3), (2, 3), (3, 4), (4, 5)]
    >>> tree = nx.Graph(edges)
    >>> sequence = nx.to_prufer_sequence(tree)
    >>> sequence
    [3, 3, 3, 4]
    >>> tree2 = nx.from_prufer_sequence(sequence)
    >>> list(tree2.edges()) == edges
    True

    """
    n = len(sequence) + 2
    # `degree` stores the remaining degree (plus one) for each node. The
    # degree of a node in the decoded tree is one more than the number
    # of times it appears in the code.
    degree = Counter(chain(sequence, range(n)))
    T = nx.empty_graph(n)
    # `not_orphaned` is the set of nodes that have a parent in the
    # tree. After the loop, there should be exactly two nodes that are
    # not in this set.
    not_orphaned = set()
    index = u = next(k for k in range(n) if degree[k] == 1)
    for v in sequence:
        # check the validity of the prufer sequence
        if v < 0 or v > n - 1:
            raise nx.NetworkXError(
                f"Invalid Prufer sequence: Values must be between 0 and {n-1}, got {v}"
            )
        T.add_edge(u, v)
        not_orphaned.add(u)
        degree[v] -= 1
        if v < index and degree[v] == 1:
            u = v
        else:
            index = u = next(k for k in range(index + 1, n) if degree[k] == 1)
    # At this point, there must be exactly two orphaned nodes; join them.
    orphans = set(T) - not_orphaned
    u, v = orphans
    T.add_edge(u, v)
    return T
