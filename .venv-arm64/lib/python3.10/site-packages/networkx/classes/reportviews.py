"""
View Classes provide node, edge and degree "views" of a graph.

Views for nodes, edges and degree are provided for all base graph classes.
A view means a read-only object that is quick to create, automatically
updated when the graph changes, and provides basic access like `n in V`,
`for n in V`, `V[n]` and sometimes set operations.

The views are read-only iterable containers that are updated as the
graph is updated. As with dicts, the graph should not be updated
while iterating through the view. Views can be iterated multiple times.

Edge and Node views also allow data attribute lookup.
The resulting attribute dict is writable as `G.edges[3, 4]['color']='red'`
Degree views allow lookup of degree values for single nodes.
Weighted degree is supported with the `weight` argument.

NodeView
========

    `V = G.nodes` (or `V = G.nodes()`) allows `len(V)`, `n in V`, set
    operations e.g. "G.nodes & H.nodes", and `dd = G.nodes[n]`, where
    `dd` is the node data dict. Iteration is over the nodes by default.

NodeDataView
============

    To iterate over (node, data) pairs, use arguments to `G.nodes()`
    to create a DataView e.g. `DV = G.nodes(data='color', default='red')`.
    The DataView iterates as `for n, color in DV` and allows
    `(n, 'red') in DV`. Using `DV = G.nodes(data=True)`, the DataViews
    use the full datadict in writeable form also allowing contain testing as
    `(n, {'color': 'red'}) in VD`. DataViews allow set operations when
    data attributes are hashable.

DegreeView
==========

    `V = G.degree` allows iteration over (node, degree) pairs as well
    as lookup: `deg=V[n]`. There are many flavors of DegreeView
    for In/Out/Directed/Multi. For Directed Graphs, `G.degree`
    counts both in and out going edges. `G.out_degree` and
    `G.in_degree` count only specific directions.
    Weighted degree using edge data attributes is provide via
    `V = G.degree(weight='attr_name')` where any string with the
    attribute name can be used. `weight=None` is the default.
    No set operations are implemented for degrees, use NodeView.

    The argument `nbunch` restricts iteration to nodes in nbunch.
    The DegreeView can still lookup any node even if nbunch is specified.

EdgeView
========

    `V = G.edges` or `V = G.edges()` allows iteration over edges as well as
    `e in V`, set operations and edge data lookup `dd = G.edges[2, 3]`.
    Iteration is over 2-tuples `(u, v)` for Graph/DiGraph. For multigraphs
    edges 3-tuples `(u, v, key)` are the default but 2-tuples can be obtained
    via `V = G.edges(keys=False)`.

    Set operations for directed graphs treat the edges as a set of 2-tuples.
    For undirected graphs, 2-tuples are not a unique representation of edges.
    So long as the set being compared to contains unique representations
    of its edges, the set operations will act as expected. If the other
    set contains both `(0, 1)` and `(1, 0)` however, the result of set
    operations may contain both representations of the same edge.

EdgeDataView
============

    Edge data can be reported using an EdgeDataView typically created
    by calling an EdgeView: `DV = G.edges(data='weight', default=1)`.
    The EdgeDataView allows iteration over edge tuples, membership checking
    but no set operations.

    Iteration depends on `data` and `default` and for multigraph `keys`
    If `data is False` (the default) then iterate over 2-tuples `(u, v)`.
    If `data is True` iterate over 3-tuples `(u, v, datadict)`.
    Otherwise iterate over `(u, v, datadict.get(data, default))`.
    For Multigraphs, if `keys is True`, replace `u, v` with `u, v, key`
    to create 3-tuples and 4-tuples.

    The argument `nbunch` restricts edges to those incident to nodes in nbunch.
"""

from abc import ABC
from collections.abc import Mapping, Set

import networkx as nx

__all__ = [
    "NodeView",
    "NodeDataView",
    "EdgeView",
    "OutEdgeView",
    "InEdgeView",
    "EdgeDataView",
    "OutEdgeDataView",
    "InEdgeDataView",
    "MultiEdgeView",
    "OutMultiEdgeView",
    "InMultiEdgeView",
    "MultiEdgeDataView",
    "OutMultiEdgeDataView",
    "InMultiEdgeDataView",
    "DegreeView",
    "DiDegreeView",
    "InDegreeView",
    "OutDegreeView",
    "MultiDegreeView",
    "DiMultiDegreeView",
    "InMultiDegreeView",
    "OutMultiDegreeView",
]


# NodeViews
class NodeView(Mapping, Set):
    """A NodeView class to act as G.nodes for a NetworkX Graph

    Set operations act on the nodes without considering data.
    Iteration is over nodes. Node data can be looked up like a dict.
    Use NodeDataView to iterate over node data or to specify a data
    attribute for lookup. NodeDataView is created by calling the NodeView.

    Parameters
    ----------
    graph : NetworkX graph-like class

    Examples
    --------
    >>> G = nx.path_graph(3)
    >>> NV = G.nodes()
    >>> 2 in NV
    True
    >>> for n in NV:
    ...     print(n)
    0
    1
    2
    >>> assert NV & {1, 2, 3} == {1, 2}

    >>> G.add_node(2, color="blue")
    >>> NV[2]
    {'color': 'blue'}
    >>> G.add_node(8, color="red")
    >>> NDV = G.nodes(data=True)
    >>> (2, NV[2]) in NDV
    True
    >>> for n, dd in NDV:
    ...     print((n, dd.get("color", "aqua")))
    (0, 'aqua')
    (1, 'aqua')
    (2, 'blue')
    (8, 'red')
    >>> NDV[2] == NV[2]
    True

    >>> NVdata = G.nodes(data="color", default="aqua")
    >>> (2, NVdata[2]) in NVdata
    True
    >>> for n, dd in NVdata:
    ...     print((n, dd))
    (0, 'aqua')
    (1, 'aqua')
    (2, 'blue')
    (8, 'red')
    >>> NVdata[2] == NV[2]  # NVdata gets 'color', NV gets datadict
    False
    """

    __slots__ = ("_nodes",)

    def __getstate__(self):
        return {"_nodes": self._nodes}

    def __setstate__(self, state):
        self._nodes = state["_nodes"]

    def __init__(self, graph):
        self._nodes = graph._node

    # Mapping methods
    def __len__(self):
        return len(self._nodes)

    def __iter__(self):
        return iter(self._nodes)

    def __getitem__(self, n):
        if isinstance(n, slice):
            raise nx.NetworkXError(
                f"{type(self).__name__} does not support slicing, "
                f"try list(G.nodes)[{n.start}:{n.stop}:{n.step}]"
            )
        return self._nodes[n]

    # Set methods
    def __contains__(self, n):
        return n in self._nodes

    @classmethod
    def _from_iterable(cls, it):
        return set(it)

    # DataView method
    def __call__(self, data=False, default=None):
        if data is False:
            return self
        return NodeDataView(self._nodes, data, default)

    def data(self, data=True, default=None):
        """
        Return a read-only view of node data.

        Parameters
        ----------
        data : bool or node data key, default=True
            If ``data=True`` (the default), return a `NodeDataView` object that
            maps each node to *all* of its attributes. `data` may also be an
            arbitrary key, in which case the `NodeDataView` maps each node to
            the value for the keyed attribute. In this case, if a node does
            not have the `data` attribute, the `default` value is used.
        default : object, default=None
            The value used when a node does not have a specific attribute.

        Returns
        -------
        NodeDataView
            The layout of the returned NodeDataView depends on the value of the
            `data` parameter.

        Notes
        -----
        If ``data=False``, returns a `NodeView` object without data.

        See Also
        --------
        NodeDataView

        Examples
        --------
        >>> G = nx.Graph()
        >>> G.add_nodes_from(
        ...     [
        ...         (0, {"color": "red", "weight": 10}),
        ...         (1, {"color": "blue"}),
        ...         (2, {"color": "yellow", "weight": 2}),
        ...     ]
        ... )

        Accessing node data with ``data=True`` (the default) returns a
        NodeDataView mapping each node to all of its attributes:

        >>> G.nodes.data()
        NodeDataView({0: {'color': 'red', 'weight': 10}, 1: {'color': 'blue'}, 2: {'color': 'yellow', 'weight': 2}})

        If `data` represents  a key in the node attribute dict, a NodeDataView mapping
        the nodes to the value for that specific key is returned:

        >>> G.nodes.data("color")
        NodeDataView({0: 'red', 1: 'blue', 2: 'yellow'}, data='color')

        If a specific key is not found in an attribute dict, the value specified
        by `default` is returned:

        >>> G.nodes.data("weight", default=-999)
        NodeDataView({0: 10, 1: -999, 2: 2}, data='weight')

        Note that there is no check that the `data` key is in any of the
        node attribute dictionaries:

        >>> G.nodes.data("height")
        NodeDataView({0: None, 1: None, 2: None}, data='height')
        """
        if data is False:
            return self
        return NodeDataView(self._nodes, data, default)

    def __str__(self):
        return str(list(self))

    def __repr__(self):
        return f"{self.__class__.__name__}({tuple(self)})"


class NodeDataView(Set):
    """A DataView class for nodes of a NetworkX Graph

    The main use for this class is to iterate through node-data pairs.
    The data can be the entire data-dictionary for each node, or it
    can be a specific attribute (with default) for each node.
    Set operations are enabled with NodeDataView, but don't work in
    cases where the data is not hashable. Use with caution.
    Typically, set operations on nodes use NodeView, not NodeDataView.
    That is, they use `G.nodes` instead of `G.nodes(data='foo')`.

    Parameters
    ==========
    graph : NetworkX graph-like class
    data : bool or string (default=False)
    default : object (default=None)
    """

    __slots__ = ("_nodes", "_data", "_default")

    def __getstate__(self):
        return {"_nodes": self._nodes, "_data": self._data, "_default": self._default}

    def __setstate__(self, state):
        self._nodes = state["_nodes"]
        self._data = state["_data"]
        self._default = state["_default"]

    def __init__(self, nodedict, data=False, default=None):
        self._nodes = nodedict
        self._data = data
        self._default = default

    @classmethod
    def _from_iterable(cls, it):
        try:
            return set(it)
        except TypeError as err:
            if "unhashable" in str(err):
                msg = " : Could be b/c data=True or your values are unhashable"
                raise TypeError(str(err) + msg) from err
            raise

    def __len__(self):
        return len(self._nodes)

    def __iter__(self):
        data = self._data
        if data is False:
            return iter(self._nodes)
        if data is True:
            return iter(self._nodes.items())
        return (
            (n, dd[data] if data in dd else self._default)
            for n, dd in self._nodes.items()
        )

    def __contains__(self, n):
        try:
            node_in = n in self._nodes
        except TypeError:
            n, d = n
            return n in self._nodes and self[n] == d
        if node_in is True:
            return node_in
        try:
            n, d = n
        except (TypeError, ValueError):
            return False
        return n in self._nodes and self[n] == d

    def __getitem__(self, n):
        if isinstance(n, slice):
            raise nx.NetworkXError(
                f"{type(self).__name__} does not support slicing, "
                f"try list(G.nodes.data())[{n.start}:{n.stop}:{n.step}]"
            )
        ddict = self._nodes[n]
        data = self._data
        if data is False or data is True:
            return ddict
        return ddict[data] if data in ddict else self._default

    def __str__(self):
        return str(list(self))

    def __repr__(self):
        name = self.__class__.__name__
        if self._data is False:
            return f"{name}({tuple(self)})"
        if self._data is True:
            return f"{name}({dict(self)})"
        return f"{name}({dict(self)}, data={self._data!r})"


# DegreeViews
class DiDegreeView:
    """A View class for degree of nodes in a NetworkX Graph

    The functionality is like dict.items() with (node, degree) pairs.
    Additional functionality includes read-only lookup of node degree,
    and calling with optional features nbunch (for only a subset of nodes)
    and weight (use edge weights to compute degree).

    Parameters
    ==========
    graph : NetworkX graph-like class
    nbunch : node, container of nodes, or None meaning all nodes (default=None)
    weight : bool or string (default=None)

    Notes
    -----
    DegreeView can still lookup any node even if nbunch is specified.

    Examples
    --------
    >>> G = nx.path_graph(3)
    >>> DV = G.degree()
    >>> assert DV[2] == 1
    >>> assert sum(deg for n, deg in DV) == 4

    >>> DVweight = G.degree(weight="span")
    >>> G.add_edge(1, 2, span=34)
    >>> DVweight[2]
    34
    >>> DVweight[0]  #  default edge weight is 1
    1
    >>> sum(span for n, span in DVweight)  # sum weighted degrees
    70

    >>> DVnbunch = G.degree(nbunch=(1, 2))
    >>> assert len(list(DVnbunch)) == 2  # iteration over nbunch only
    """

    def __init__(self, G, nbunch=None, weight=None):
        self._graph = G
        self._succ = G._succ if hasattr(G, "_succ") else G._adj
        self._pred = G._pred if hasattr(G, "_pred") else G._adj
        self._nodes = self._succ if nbunch is None else list(G.nbunch_iter(nbunch))
        self._weight = weight

    def __call__(self, nbunch=None, weight=None):
        if nbunch is None:
            if weight == self._weight:
                return self
            return self.__class__(self._graph, None, weight)
        try:
            if nbunch in self._nodes:
                if weight == self._weight:
                    return self[nbunch]
                return self.__class__(self._graph, None, weight)[nbunch]
        except TypeError:
            pass
        return self.__class__(self._graph, nbunch, weight)

    def __getitem__(self, n):
        weight = self._weight
        succs = self._succ[n]
        preds = self._pred[n]
        if weight is None:
            return len(succs) + len(preds)
        return sum(dd.get(weight, 1) for dd in succs.values()) + sum(
            dd.get(weight, 1) for dd in preds.values()
        )

    def __iter__(self):
        weight = self._weight
        if weight is None:
            for n in self._nodes:
                succs = self._succ[n]
                preds = self._pred[n]
                yield (n, len(succs) + len(preds))
        else:
            for n in self._nodes:
                succs = self._succ[n]
                preds = self._pred[n]
                deg = sum(dd.get(weight, 1) for dd in succs.values()) + sum(
                    dd.get(weight, 1) for dd in preds.values()
                )
                yield (n, deg)

    def __len__(self):
        return len(self._nodes)

    def __str__(self):
        return str(list(self))

    def __repr__(self):
        return f"{self.__class__.__name__}({dict(self)})"


class DegreeView(DiDegreeView):
    """A DegreeView class to act as G.degree for a NetworkX Graph

    Typical usage focuses on iteration over `(node, degree)` pairs.
    The degree is by default the number of edges incident to the node.
    Optional argument `weight` enables weighted degree using the edge
    attribute named in the `weight` argument.  Reporting and iteration
    can also be restricted to a subset of nodes using `nbunch`.

    Additional functionality include node lookup so that `G.degree[n]`
    reported the (possibly weighted) degree of node `n`. Calling the
    view creates a view with different arguments `nbunch` or `weight`.

    Parameters
    ==========
    graph : NetworkX graph-like class
    nbunch : node, container of nodes, or None meaning all nodes (default=None)
    weight : string or None (default=None)

    Notes
    -----
    DegreeView can still lookup any node even if nbunch is specified.

    Examples
    --------
    >>> G = nx.path_graph(3)
    >>> DV = G.degree()
    >>> assert DV[2] == 1
    >>> assert G.degree[2] == 1
    >>> assert sum(deg for n, deg in DV) == 4

    >>> DVweight = G.degree(weight="span")
    >>> G.add_edge(1, 2, span=34)
    >>> DVweight[2]
    34
    >>> DVweight[0]  #  default edge weight is 1
    1
    >>> sum(span for n, span in DVweight)  # sum weighted degrees
    70

    >>> DVnbunch = G.degree(nbunch=(1, 2))
    >>> assert len(list(DVnbunch)) == 2  # iteration over nbunch only
    """

    def __getitem__(self, n):
        weight = self._weight
        nbrs = self._succ[n]
        if weight is None:
            return len(nbrs) + (n in nbrs)
        return sum(dd.get(weight, 1) for dd in nbrs.values()) + (
            n in nbrs and nbrs[n].get(weight, 1)
        )

    def __iter__(self):
        weight = self._weight
        if weight is None:
            for n in self._nodes:
                nbrs = self._succ[n]
                yield (n, len(nbrs) + (n in nbrs))
        else:
            for n in self._nodes:
                nbrs = self._succ[n]
                deg = sum(dd.get(weight, 1) for dd in nbrs.values()) + (
                    n in nbrs and nbrs[n].get(weight, 1)
                )
                yield (n, deg)


class OutDegreeView(DiDegreeView):
    """A DegreeView class to report out_degree for a DiGraph; See DegreeView"""

    def __getitem__(self, n):
        weight = self._weight
        nbrs = self._succ[n]
        if self._weight is None:
            return len(nbrs)
        return sum(dd.get(self._weight, 1) for dd in nbrs.values())

    def __iter__(self):
        weight = self._weight
        if weight is None:
            for n in self._nodes:
                succs = self._succ[n]
                yield (n, len(succs))
        else:
            for n in self._nodes:
                succs = self._succ[n]
                deg = sum(dd.get(weight, 1) for dd in succs.values())
                yield (n, deg)


class InDegreeView(DiDegreeView):
    """A DegreeView class to report in_degree for a DiGraph; See DegreeView"""

    def __getitem__(self, n):
        weight = self._weight
        nbrs = self._pred[n]
        if weight is None:
            return len(nbrs)
        return sum(dd.get(weight, 1) for dd in nbrs.values())

    def __iter__(self):
        weight = self._weight
        if weight is None:
            for n in self._nodes:
                preds = self._pred[n]
                yield (n, len(preds))
        else:
            for n in self._nodes:
                preds = self._pred[n]
                deg = sum(dd.get(weight, 1) for dd in preds.values())
                yield (n, deg)


class MultiDegreeView(DiDegreeView):
    """A DegreeView class for undirected multigraphs; See DegreeView"""

    def __getitem__(self, n):
        weight = self._weight
        nbrs = self._succ[n]
        if weight is None:
            return sum(len(keys) for keys in nbrs.values()) + (
                n in nbrs and len(nbrs[n])
            )
        # edge weighted graph - degree is sum of nbr edge weights
        deg = sum(
            d.get(weight, 1) for key_dict in nbrs.values() for d in key_dict.values()
        )
        if n in nbrs:
            deg += sum(d.get(weight, 1) for d in nbrs[n].values())
        return deg

    def __iter__(self):
        weight = self._weight
        if weight is None:
            for n in self._nodes:
                nbrs = self._succ[n]
                deg = sum(len(keys) for keys in nbrs.values()) + (
                    n in nbrs and len(nbrs[n])
                )
                yield (n, deg)
        else:
            for n in self._nodes:
                nbrs = self._succ[n]
                deg = sum(
                    d.get(weight, 1)
                    for key_dict in nbrs.values()
                    for d in key_dict.values()
                )
                if n in nbrs:
                    deg += sum(d.get(weight, 1) for d in nbrs[n].values())
                yield (n, deg)


class DiMultiDegreeView(DiDegreeView):
    """A DegreeView class for MultiDiGraph; See DegreeView"""

    def __getitem__(self, n):
        weight = self._weight
        succs = self._succ[n]
        preds = self._pred[n]
        if weight is None:
            return sum(len(keys) for keys in succs.values()) + sum(
                len(keys) for keys in preds.values()
            )
        # edge weighted graph - degree is sum of nbr edge weights
        deg = sum(
            d.get(weight, 1) for key_dict in succs.values() for d in key_dict.values()
        ) + sum(
            d.get(weight, 1) for key_dict in preds.values() for d in key_dict.values()
        )
        return deg

    def __iter__(self):
        weight = self._weight
        if weight is None:
            for n in self._nodes:
                succs = self._succ[n]
                preds = self._pred[n]
                deg = sum(len(keys) for keys in succs.values()) + sum(
                    len(keys) for keys in preds.values()
                )
                yield (n, deg)
        else:
            for n in self._nodes:
                succs = self._succ[n]
                preds = self._pred[n]
                deg = sum(
                    d.get(weight, 1)
                    for key_dict in succs.values()
                    for d in key_dict.values()
                ) + sum(
                    d.get(weight, 1)
                    for key_dict in preds.values()
                    for d in key_dict.values()
                )
                yield (n, deg)


class InMultiDegreeView(DiDegreeView):
    """A DegreeView class for inward degree of MultiDiGraph; See DegreeView"""

    def __getitem__(self, n):
        weight = self._weight
        nbrs = self._pred[n]
        if weight is None:
            return sum(len(data) for data in nbrs.values())
        # edge weighted graph - degree is sum of nbr edge weights
        return sum(
            d.get(weight, 1) for key_dict in nbrs.values() for d in key_dict.values()
        )

    def __iter__(self):
        weight = self._weight
        if weight is None:
            for n in self._nodes:
                nbrs = self._pred[n]
                deg = sum(len(data) for data in nbrs.values())
                yield (n, deg)
        else:
            for n in self._nodes:
                nbrs = self._pred[n]
                deg = sum(
                    d.get(weight, 1)
                    for key_dict in nbrs.values()
                    for d in key_dict.values()
                )
                yield (n, deg)


class OutMultiDegreeView(DiDegreeView):
    """A DegreeView class for outward degree of MultiDiGraph; See DegreeView"""

    def __getitem__(self, n):
        weight = self._weight
        nbrs = self._succ[n]
        if weight is None:
            return sum(len(data) for data in nbrs.values())
        # edge weighted graph - degree is sum of nbr edge weights
        return sum(
            d.get(weight, 1) for key_dict in nbrs.values() for d in key_dict.values()
        )

    def __iter__(self):
        weight = self._weight
        if weight is None:
            for n in self._nodes:
                nbrs = self._succ[n]
                deg = sum(len(data) for data in nbrs.values())
                yield (n, deg)
        else:
            for n in self._nodes:
                nbrs = self._succ[n]
                deg = sum(
                    d.get(weight, 1)
                    for key_dict in nbrs.values()
                    for d in key_dict.values()
                )
                yield (n, deg)


# A base class for all edge views. Ensures all edge view and edge data view
# objects/classes are captured by `isinstance(obj, EdgeViewABC)` and
# `issubclass(cls, EdgeViewABC)` respectively
class EdgeViewABC(ABC):
    pass


# EdgeDataViews
class OutEdgeDataView(EdgeViewABC):
    """EdgeDataView for outward edges of DiGraph; See EdgeDataView"""

    __slots__ = (
        "_viewer",
        "_nbunch",
        "_data",
        "_default",
        "_adjdict",
        "_nodes_nbrs",
        "_report",
    )

    def __getstate__(self):
        return {
            "viewer": self._viewer,
            "nbunch": self._nbunch,
            "data": self._data,
            "default": self._default,
        }

    def __setstate__(self, state):
        self.__init__(**state)

    def __init__(self, viewer, nbunch=None, data=False, *, default=None):
        self._viewer = viewer
        adjdict = self._adjdict = viewer._adjdict
        if nbunch is None:
            self._nodes_nbrs = adjdict.items
        else:
            # dict retains order of nodes but acts like a set
            nbunch = dict.fromkeys(viewer._graph.nbunch_iter(nbunch))
            self._nodes_nbrs = lambda: [(n, adjdict[n]) for n in nbunch]
        self._nbunch = nbunch
        self._data = data
        self._default = default
        # Set _report based on data and default
        if data is True:
            self._report = lambda n, nbr, dd: (n, nbr, dd)
        elif data is False:
            self._report = lambda n, nbr, dd: (n, nbr)
        else:  # data is attribute name
            self._report = (
                lambda n, nbr, dd: (n, nbr, dd[data])
                if data in dd
                else (n, nbr, default)
            )

    def __len__(self):
        return sum(len(nbrs) for n, nbrs in self._nodes_nbrs())

    def __iter__(self):
        return (
            self._report(n, nbr, dd)
            for n, nbrs in self._nodes_nbrs()
            for nbr, dd in nbrs.items()
        )

    def __contains__(self, e):
        u, v = e[:2]
        if self._nbunch is not None and u not in self._nbunch:
            return False  # this edge doesn't start in nbunch
        try:
            ddict = self._adjdict[u][v]
        except KeyError:
            return False
        return e == self._report(u, v, ddict)

    def __str__(self):
        return str(list(self))

    def __repr__(self):
        return f"{self.__class__.__name__}({list(self)})"


class EdgeDataView(OutEdgeDataView):
    """A EdgeDataView class for edges of Graph

    This view is primarily used to iterate over the edges reporting
    edges as node-tuples with edge data optionally reported. The
    argument `nbunch` allows restriction to edges incident to nodes
    in that container/singleton. The default (nbunch=None)
    reports all edges. The arguments `data` and `default` control
    what edge data is reported. The default `data is False` reports
    only node-tuples for each edge. If `data is True` the entire edge
    data dict is returned. Otherwise `data` is assumed to hold the name
    of the edge attribute to report with default `default` if  that
    edge attribute is not present.

    Parameters
    ----------
    nbunch : container of nodes, node or None (default None)
    data : False, True or string (default False)
    default : default value (default None)

    Examples
    --------
    >>> G = nx.path_graph(3)
    >>> G.add_edge(1, 2, foo="bar")
    >>> list(G.edges(data="foo", default="biz"))
    [(0, 1, 'biz'), (1, 2, 'bar')]
    >>> assert (0, 1, "biz") in G.edges(data="foo", default="biz")
    """

    __slots__ = ()

    def __len__(self):
        return sum(1 for e in self)

    def __iter__(self):
        seen = {}
        for n, nbrs in self._nodes_nbrs():
            for nbr, dd in nbrs.items():
                if nbr not in seen:
                    yield self._report(n, nbr, dd)
            seen[n] = 1
        del seen

    def __contains__(self, e):
        u, v = e[:2]
        if self._nbunch is not None and u not in self._nbunch and v not in self._nbunch:
            return False  # this edge doesn't start and it doesn't end in nbunch
        try:
            ddict = self._adjdict[u][v]
        except KeyError:
            return False
        return e == self._report(u, v, ddict)


class InEdgeDataView(OutEdgeDataView):
    """An EdgeDataView class for outward edges of DiGraph; See EdgeDataView"""

    __slots__ = ()

    def __iter__(self):
        return (
            self._report(nbr, n, dd)
            for n, nbrs in self._nodes_nbrs()
            for nbr, dd in nbrs.items()
        )

    def __contains__(self, e):
        u, v = e[:2]
        if self._nbunch is not None and v not in self._nbunch:
            return False  # this edge doesn't end in nbunch
        try:
            ddict = self._adjdict[v][u]
        except KeyError:
            return False
        return e == self._report(u, v, ddict)


class OutMultiEdgeDataView(OutEdgeDataView):
    """An EdgeDataView for outward edges of MultiDiGraph; See EdgeDataView"""

    __slots__ = ("keys",)

    def __getstate__(self):
        return {
            "viewer": self._viewer,
            "nbunch": self._nbunch,
            "keys": self.keys,
            "data": self._data,
            "default": self._default,
        }

    def __setstate__(self, state):
        self.__init__(**state)

    def __init__(self, viewer, nbunch=None, data=False, *, default=None, keys=False):
        self._viewer = viewer
        adjdict = self._adjdict = viewer._adjdict
        self.keys = keys
        if nbunch is None:
            self._nodes_nbrs = adjdict.items
        else:
            # dict retains order of nodes but acts like a set
            nbunch = dict.fromkeys(viewer._graph.nbunch_iter(nbunch))
            self._nodes_nbrs = lambda: [(n, adjdict[n]) for n in nbunch]
        self._nbunch = nbunch
        self._data = data
        self._default = default
        # Set _report based on data and default
        if data is True:
            if keys is True:
                self._report = lambda n, nbr, k, dd: (n, nbr, k, dd)
            else:
                self._report = lambda n, nbr, k, dd: (n, nbr, dd)
        elif data is False:
            if keys is True:
                self._report = lambda n, nbr, k, dd: (n, nbr, k)
            else:
                self._report = lambda n, nbr, k, dd: (n, nbr)
        else:  # data is attribute name
            if keys is True:
                self._report = (
                    lambda n, nbr, k, dd: (n, nbr, k, dd[data])
                    if data in dd
                    else (n, nbr, k, default)
                )
            else:
                self._report = (
                    lambda n, nbr, k, dd: (n, nbr, dd[data])
                    if data in dd
                    else (n, nbr, default)
                )

    def __len__(self):
        return sum(1 for e in self)

    def __iter__(self):
        return (
            self._report(n, nbr, k, dd)
            for n, nbrs in self._nodes_nbrs()
            for nbr, kd in nbrs.items()
            for k, dd in kd.items()
        )

    def __contains__(self, e):
        u, v = e[:2]
        if self._nbunch is not None and u not in self._nbunch:
            return False  # this edge doesn't start in nbunch
        try:
            kdict = self._adjdict[u][v]
        except KeyError:
            return False
        if self.keys is True:
            k = e[2]
            try:
                dd = kdict[k]
            except KeyError:
                return False
            return e == self._report(u, v, k, dd)
        return any(e == self._report(u, v, k, dd) for k, dd in kdict.items())


class MultiEdgeDataView(OutMultiEdgeDataView):
    """An EdgeDataView class for edges of MultiGraph; See EdgeDataView"""

    __slots__ = ()

    def __iter__(self):
        seen = {}
        for n, nbrs in self._nodes_nbrs():
            for nbr, kd in nbrs.items():
                if nbr not in seen:
                    for k, dd in kd.items():
                        yield self._report(n, nbr, k, dd)
            seen[n] = 1
        del seen

    def __contains__(self, e):
        u, v = e[:2]
        if self._nbunch is not None and u not in self._nbunch and v not in self._nbunch:
            return False  # this edge doesn't start and doesn't end in nbunch
        try:
            kdict = self._adjdict[u][v]
        except KeyError:
            try:
                kdict = self._adjdict[v][u]
            except KeyError:
                return False
        if self.keys is True:
            k = e[2]
            try:
                dd = kdict[k]
            except KeyError:
                return False
            return e == self._report(u, v, k, dd)
        return any(e == self._report(u, v, k, dd) for k, dd in kdict.items())


class InMultiEdgeDataView(OutMultiEdgeDataView):
    """An EdgeDataView for inward edges of MultiDiGraph; See EdgeDataView"""

    __slots__ = ()

    def __iter__(self):
        return (
            self._report(nbr, n, k, dd)
            for n, nbrs in self._nodes_nbrs()
            for nbr, kd in nbrs.items()
            for k, dd in kd.items()
        )

    def __contains__(self, e):
        u, v = e[:2]
        if self._nbunch is not None and v not in self._nbunch:
            return False  # this edge doesn't end in nbunch
        try:
            kdict = self._adjdict[v][u]
        except KeyError:
            return False
        if self.keys is True:
            k = e[2]
            dd = kdict[k]
            return e == self._report(u, v, k, dd)
        return any(e == self._report(u, v, k, dd) for k, dd in kdict.items())


# EdgeViews    have set operations and no data reported
class OutEdgeView(Set, Mapping, EdgeViewABC):
    """A EdgeView class for outward edges of a DiGraph"""

    __slots__ = ("_adjdict", "_graph", "_nodes_nbrs")

    def __getstate__(self):
        return {"_graph": self._graph, "_adjdict": self._adjdict}

    def __setstate__(self, state):
        self._graph = state["_graph"]
        self._adjdict = state["_adjdict"]
        self._nodes_nbrs = self._adjdict.items

    @classmethod
    def _from_iterable(cls, it):
        return set(it)

    dataview = OutEdgeDataView

    def __init__(self, G):
        self._graph = G
        self._adjdict = G._succ if hasattr(G, "succ") else G._adj
        self._nodes_nbrs = self._adjdict.items

    # Set methods
    def __len__(self):
        return sum(len(nbrs) for n, nbrs in self._nodes_nbrs())

    def __iter__(self):
        for n, nbrs in self._nodes_nbrs():
            for nbr in nbrs:
                yield (n, nbr)

    def __contains__(self, e):
        try:
            u, v = e
            return v in self._adjdict[u]
        except KeyError:
            return False

    # Mapping Methods
    def __getitem__(self, e):
        if isinstance(e, slice):
            raise nx.NetworkXError(
                f"{type(self).__name__} does not support slicing, "
                f"try list(G.edges)[{e.start}:{e.stop}:{e.step}]"
            )
        u, v = e
        try:
            return self._adjdict[u][v]
        except KeyError as ex:  # Customize msg to indicate exception origin
            raise KeyError(f"The edge {e} is not in the graph.")

    # EdgeDataView methods
    def __call__(self, nbunch=None, data=False, *, default=None):
        if nbunch is None and data is False:
            return self
        return self.dataview(self, nbunch, data, default=default)

    def data(self, data=True, default=None, nbunch=None):
        """
        Return a read-only view of edge data.

        Parameters
        ----------
        data : bool or edge attribute key
            If ``data=True``, then the data view maps each edge to a dictionary
            containing all of its attributes. If `data` is a key in the edge
            dictionary, then the data view maps each edge to its value for
            the keyed attribute. In this case, if the edge doesn't have the
            attribute, the `default` value is returned.
        default : object, default=None
            The value used when an edge does not have a specific attribute
        nbunch : container of nodes, optional (default=None)
            Allows restriction to edges only involving certain nodes. All edges
            are considered by default.

        Returns
        -------
        dataview
            Returns an `EdgeDataView` for undirected Graphs, `OutEdgeDataView`
            for DiGraphs, `MultiEdgeDataView` for MultiGraphs and
            `OutMultiEdgeDataView` for MultiDiGraphs.

        Notes
        -----
        If ``data=False``, returns an `EdgeView` without any edge data.

        See Also
        --------
        EdgeDataView
        OutEdgeDataView
        MultiEdgeDataView
        OutMultiEdgeDataView

        Examples
        --------
        >>> G = nx.Graph()
        >>> G.add_edges_from(
        ...     [
        ...         (0, 1, {"dist": 3, "capacity": 20}),
        ...         (1, 2, {"dist": 4}),
        ...         (2, 0, {"dist": 5}),
        ...     ]
        ... )

        Accessing edge data with ``data=True`` (the default) returns an
        edge data view object listing each edge with all of its attributes:

        >>> G.edges.data()
        EdgeDataView([(0, 1, {'dist': 3, 'capacity': 20}), (0, 2, {'dist': 5}), (1, 2, {'dist': 4})])

        If `data` represents a key in the edge attribute dict, a dataview listing
        each edge with its value for that specific key is returned:

        >>> G.edges.data("dist")
        EdgeDataView([(0, 1, 3), (0, 2, 5), (1, 2, 4)])

        `nbunch` can be used to limit the edges:

        >>> G.edges.data("dist", nbunch=[0])
        EdgeDataView([(0, 1, 3), (0, 2, 5)])

        If a specific key is not found in an edge attribute dict, the value
        specified by `default` is used:

        >>> G.edges.data("capacity")
        EdgeDataView([(0, 1, 20), (0, 2, None), (1, 2, None)])

        Note that there is no check that the `data` key is present in any of
        the edge attribute dictionaries:

        >>> G.edges.data("speed")
        EdgeDataView([(0, 1, None), (0, 2, None), (1, 2, None)])
        """
        if nbunch is None and data is False:
            return self
        return self.dataview(self, nbunch, data, default=default)

    # String Methods
    def __str__(self):
        return str(list(self))

    def __repr__(self):
        return f"{self.__class__.__name__}({list(self)})"


class EdgeView(OutEdgeView):
    """A EdgeView class for edges of a Graph

    This densely packed View allows iteration over edges, data lookup
    like a dict and set operations on edges represented by node-tuples.
    In addition, edge data can be controlled by calling this object
    possibly creating an EdgeDataView. Typically edges are iterated over
    and reported as `(u, v)` node tuples or `(u, v, key)` node/key tuples
    for multigraphs. Those edge representations can also be using to
    lookup the data dict for any edge. Set operations also are available
    where those tuples are the elements of the set.
    Calling this object with optional arguments `data`, `default` and `keys`
    controls the form of the tuple (see EdgeDataView). Optional argument
    `nbunch` allows restriction to edges only involving certain nodes.

    If `data is False` (the default) then iterate over 2-tuples `(u, v)`.
    If `data is True` iterate over 3-tuples `(u, v, datadict)`.
    Otherwise iterate over `(u, v, datadict.get(data, default))`.
    For Multigraphs, if `keys is True`, replace `u, v` with `u, v, key` above.

    Parameters
    ==========
    graph : NetworkX graph-like class
    nbunch : (default= all nodes in graph) only report edges with these nodes
    keys : (only for MultiGraph. default=False) report edge key in tuple
    data : bool or string (default=False) see above
    default : object (default=None)

    Examples
    ========
    >>> G = nx.path_graph(4)
    >>> EV = G.edges()
    >>> (2, 3) in EV
    True
    >>> for u, v in EV:
    ...     print((u, v))
    (0, 1)
    (1, 2)
    (2, 3)
    >>> assert EV & {(1, 2), (3, 4)} == {(1, 2)}

    >>> EVdata = G.edges(data="color", default="aqua")
    >>> G.add_edge(2, 3, color="blue")
    >>> assert (2, 3, "blue") in EVdata
    >>> for u, v, c in EVdata:
    ...     print(f"({u}, {v}) has color: {c}")
    (0, 1) has color: aqua
    (1, 2) has color: aqua
    (2, 3) has color: blue

    >>> EVnbunch = G.edges(nbunch=2)
    >>> assert (2, 3) in EVnbunch
    >>> assert (0, 1) not in EVnbunch
    >>> for u, v in EVnbunch:
    ...     assert u == 2 or v == 2

    >>> MG = nx.path_graph(4, create_using=nx.MultiGraph)
    >>> EVmulti = MG.edges(keys=True)
    >>> (2, 3, 0) in EVmulti
    True
    >>> (2, 3) in EVmulti  # 2-tuples work even when keys is True
    True
    >>> key = MG.add_edge(2, 3)
    >>> for u, v, k in EVmulti:
    ...     print((u, v, k))
    (0, 1, 0)
    (1, 2, 0)
    (2, 3, 0)
    (2, 3, 1)
    """

    __slots__ = ()

    dataview = EdgeDataView

    def __len__(self):
        num_nbrs = (len(nbrs) + (n in nbrs) for n, nbrs in self._nodes_nbrs())
        return sum(num_nbrs) // 2

    def __iter__(self):
        seen = {}
        for n, nbrs in self._nodes_nbrs():
            for nbr in list(nbrs):
                if nbr not in seen:
                    yield (n, nbr)
            seen[n] = 1
        del seen

    def __contains__(self, e):
        try:
            u, v = e[:2]
            return v in self._adjdict[u] or u in self._adjdict[v]
        except (KeyError, ValueError):
            return False


class InEdgeView(OutEdgeView):
    """A EdgeView class for inward edges of a DiGraph"""

    __slots__ = ()

    def __setstate__(self, state):
        self._graph = state["_graph"]
        self._adjdict = state["_adjdict"]
        self._nodes_nbrs = self._adjdict.items

    dataview = InEdgeDataView

    def __init__(self, G):
        self._graph = G
        self._adjdict = G._pred if hasattr(G, "pred") else G._adj
        self._nodes_nbrs = self._adjdict.items

    def __iter__(self):
        for n, nbrs in self._nodes_nbrs():
            for nbr in nbrs:
                yield (nbr, n)

    def __contains__(self, e):
        try:
            u, v = e
            return u in self._adjdict[v]
        except KeyError:
            return False

    def __getitem__(self, e):
        if isinstance(e, slice):
            raise nx.NetworkXError(
                f"{type(self).__name__} does not support slicing, "
                f"try list(G.in_edges)[{e.start}:{e.stop}:{e.step}]"
            )
        u, v = e
        return self._adjdict[v][u]


class OutMultiEdgeView(OutEdgeView):
    """A EdgeView class for outward edges of a MultiDiGraph"""

    __slots__ = ()

    dataview = OutMultiEdgeDataView

    def __len__(self):
        return sum(
            len(kdict) for n, nbrs in self._nodes_nbrs() for nbr, kdict in nbrs.items()
        )

    def __iter__(self):
        for n, nbrs in self._nodes_nbrs():
            for nbr, kdict in nbrs.items():
                for key in kdict:
                    yield (n, nbr, key)

    def __contains__(self, e):
        N = len(e)
        if N == 3:
            u, v, k = e
        elif N == 2:
            u, v = e
            k = 0
        else:
            raise ValueError("MultiEdge must have length 2 or 3")
        try:
            return k in self._adjdict[u][v]
        except KeyError:
            return False

    def __getitem__(self, e):
        if isinstance(e, slice):
            raise nx.NetworkXError(
                f"{type(self).__name__} does not support slicing, "
                f"try list(G.edges)[{e.start}:{e.stop}:{e.step}]"
            )
        u, v, k = e
        return self._adjdict[u][v][k]

    def __call__(self, nbunch=None, data=False, *, default=None, keys=False):
        if nbunch is None and data is False and keys is True:
            return self
        return self.dataview(self, nbunch, data, default=default, keys=keys)

    def data(self, data=True, default=None, nbunch=None, keys=False):
        if nbunch is None and data is False and keys is True:
            return self
        return self.dataview(self, nbunch, data, default=default, keys=keys)


class MultiEdgeView(OutMultiEdgeView):
    """A EdgeView class for edges of a MultiGraph"""

    __slots__ = ()

    dataview = MultiEdgeDataView

    def __len__(self):
        return sum(1 for e in self)

    def __iter__(self):
        seen = {}
        for n, nbrs in self._nodes_nbrs():
            for nbr, kd in nbrs.items():
                if nbr not in seen:
                    for k, dd in kd.items():
                        yield (n, nbr, k)
            seen[n] = 1
        del seen


class InMultiEdgeView(OutMultiEdgeView):
    """A EdgeView class for inward edges of a MultiDiGraph"""

    __slots__ = ()

    def __setstate__(self, state):
        self._graph = state["_graph"]
        self._adjdict = state["_adjdict"]
        self._nodes_nbrs = self._adjdict.items

    dataview = InMultiEdgeDataView

    def __init__(self, G):
        self._graph = G
        self._adjdict = G._pred if hasattr(G, "pred") else G._adj
        self._nodes_nbrs = self._adjdict.items

    def __iter__(self):
        for n, nbrs in self._nodes_nbrs():
            for nbr, kdict in nbrs.items():
                for key in kdict:
                    yield (nbr, n, key)

    def __contains__(self, e):
        N = len(e)
        if N == 3:
            u, v, k = e
        elif N == 2:
            u, v = e
            k = 0
        else:
            raise ValueError("MultiEdge must have length 2 or 3")
        try:
            return k in self._adjdict[v][u]
        except KeyError:
            return False

    def __getitem__(self, e):
        if isinstance(e, slice):
            raise nx.NetworkXError(
                f"{type(self).__name__} does not support slicing, "
                f"try list(G.in_edges)[{e.start}:{e.stop}:{e.step}]"
            )
        u, v, k = e
        return self._adjdict[v][u][k]
