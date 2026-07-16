"""Base class for MultiDiGraph."""

from copy import deepcopy
from functools import cached_property

import networkx as nx
from networkx import convert
from networkx.classes.coreviews import MultiAdjacencyView
from networkx.classes.digraph import DiGraph
from networkx.classes.multigraph import MultiGraph
from networkx.classes.reportviews import (
    DiMultiDegreeView,
    InMultiDegreeView,
    InMultiEdgeView,
    OutMultiDegreeView,
    OutMultiEdgeView,
)
from networkx.exception import NetworkXError

__all__ = ["MultiDiGraph"]


class MultiDiGraph(MultiGraph, DiGraph):
    """A directed graph class that can store multiedges.

    Multiedges are multiple edges between two nodes.  Each edge
    can hold optional data or attributes.

    A MultiDiGraph holds directed edges.  Self loops are allowed.

    Nodes can be arbitrary (hashable) Python objects with optional
    key/value attributes. By convention `None` is not used as a node.

    Edges are represented as links between nodes with optional
    key/value attributes.

    Parameters
    ----------
    incoming_graph_data : input graph (optional, default: None)
        Data to initialize graph. If None (default) an empty
        graph is created.  The data can be any format that is supported
        by the to_networkx_graph() function, currently including edge list,
        dict of dicts, dict of lists, NetworkX graph, 2D NumPy array, SciPy
        sparse matrix, or PyGraphviz graph.

    multigraph_input : bool or None (default None)
        Note: Only used when `incoming_graph_data` is a dict.
        If True, `incoming_graph_data` is assumed to be a
        dict-of-dict-of-dict-of-dict structure keyed by
        node to neighbor to edge keys to edge data for multi-edges.
        A NetworkXError is raised if this is not the case.
        If False, :func:`to_networkx_graph` is used to try to determine
        the dict's graph data structure as either a dict-of-dict-of-dict
        keyed by node to neighbor to edge data, or a dict-of-iterable
        keyed by node to neighbors.
        If None, the treatment for True is tried, but if it fails,
        the treatment for False is tried.

    attr : keyword arguments, optional (default= no attributes)
        Attributes to add to graph as key=value pairs.

    See Also
    --------
    Graph
    DiGraph
    MultiGraph

    Examples
    --------
    Create an empty graph structure (a "null graph") with no nodes and
    no edges.

    >>> G = nx.MultiDiGraph()

    G can be grown in several ways.

    **Nodes:**

    Add one node at a time:

    >>> G.add_node(1)

    Add the nodes from any container (a list, dict, set or
    even the lines from a file or the nodes from another graph).

    >>> G.add_nodes_from([2, 3])
    >>> G.add_nodes_from(range(100, 110))
    >>> H = nx.path_graph(10)
    >>> G.add_nodes_from(H)

    In addition to strings and integers any hashable Python object
    (except None) can represent a node, e.g. a customized node object,
    or even another Graph.

    >>> G.add_node(H)

    **Edges:**

    G can also be grown by adding edges.

    Add one edge,

    >>> key = G.add_edge(1, 2)

    a list of edges,

    >>> keys = G.add_edges_from([(1, 2), (1, 3)])

    or a collection of edges,

    >>> keys = G.add_edges_from(H.edges)

    If some edges connect nodes not yet in the graph, the nodes
    are added automatically.  If an edge already exists, an additional
    edge is created and stored using a key to identify the edge.
    By default the key is the lowest unused integer.

    >>> keys = G.add_edges_from([(4, 5, dict(route=282)), (4, 5, dict(route=37))])
    >>> G[4]
    AdjacencyView({5: {0: {}, 1: {'route': 282}, 2: {'route': 37}}})

    **Attributes:**

    Each graph, node, and edge can hold key/value attribute pairs
    in an associated attribute dictionary (the keys must be hashable).
    By default these are empty, but can be added or changed using
    add_edge, add_node or direct manipulation of the attribute
    dictionaries named graph, node and edge respectively.

    >>> G = nx.MultiDiGraph(day="Friday")
    >>> G.graph
    {'day': 'Friday'}

    Add node attributes using add_node(), add_nodes_from() or G.nodes

    >>> G.add_node(1, time="5pm")
    >>> G.add_nodes_from([3], time="2pm")
    >>> G.nodes[1]
    {'time': '5pm'}
    >>> G.nodes[1]["room"] = 714
    >>> del G.nodes[1]["room"]  # remove attribute
    >>> list(G.nodes(data=True))
    [(1, {'time': '5pm'}), (3, {'time': '2pm'})]

    Add edge attributes using add_edge(), add_edges_from(), subscript
    notation, or G.edges.

    >>> key = G.add_edge(1, 2, weight=4.7)
    >>> keys = G.add_edges_from([(3, 4), (4, 5)], color="red")
    >>> keys = G.add_edges_from([(1, 2, {"color": "blue"}), (2, 3, {"weight": 8})])
    >>> G[1][2][0]["weight"] = 4.7
    >>> G.edges[1, 2, 0]["weight"] = 4

    Warning: we protect the graph data structure by making `G.edges[1,
    2, 0]` a read-only dict-like structure. However, you can assign to
    attributes in e.g. `G.edges[1, 2, 0]`. Thus, use 2 sets of brackets
    to add/change data attributes: `G.edges[1, 2, 0]['weight'] = 4`
    (for multigraphs the edge key is required: `MG.edges[u, v,
    key][name] = value`).

    **Shortcuts:**

    Many common graph features allow python syntax to speed reporting.

    >>> 1 in G  # check if node in graph
    True
    >>> [n for n in G if n < 3]  # iterate through nodes
    [1, 2]
    >>> len(G)  # number of nodes in graph
    5
    >>> G[1]  # adjacency dict-like view mapping neighbor -> edge key -> edge attributes
    AdjacencyView({2: {0: {'weight': 4}, 1: {'color': 'blue'}}})

    Often the best way to traverse all edges of a graph is via the neighbors.
    The neighbors are available as an adjacency-view `G.adj` object or via
    the method `G.adjacency()`.

    >>> for n, nbrsdict in G.adjacency():
    ...     for nbr, keydict in nbrsdict.items():
    ...         for key, eattr in keydict.items():
    ...             if "weight" in eattr:
    ...                 # Do something useful with the edges
    ...                 pass

    But the edges() method is often more convenient:

    >>> for u, v, keys, weight in G.edges(data="weight", keys=True):
    ...     if weight is not None:
    ...         # Do something useful with the edges
    ...         pass

    **Reporting:**

    Simple graph information is obtained using methods and object-attributes.
    Reporting usually provides views instead of containers to reduce memory
    usage. The views update as the graph is updated similarly to dict-views.
    The objects `nodes`, `edges` and `adj` provide access to data attributes
    via lookup (e.g. `nodes[n]`, `edges[u, v, k]`, `adj[u][v]`) and iteration
    (e.g. `nodes.items()`, `nodes.data('color')`,
    `nodes.data('color', default='blue')` and similarly for `edges`)
    Views exist for `nodes`, `edges`, `neighbors()`/`adj` and `degree`.

    For details on these and other miscellaneous methods, see below.

    **Subclasses (Advanced):**

    The MultiDiGraph class uses a dict-of-dict-of-dict-of-dict structure.
    The outer dict (node_dict) holds adjacency information keyed by node.
    The next dict (adjlist_dict) represents the adjacency information
    and holds edge_key dicts keyed by neighbor. The edge_key dict holds
    each edge_attr dict keyed by edge key. The inner dict
    (edge_attr_dict) represents the edge data and holds edge attribute
    values keyed by attribute names.

    Each of these four dicts in the dict-of-dict-of-dict-of-dict
    structure can be replaced by a user defined dict-like object.
    In general, the dict-like features should be maintained but
    extra features can be added. To replace one of the dicts create
    a new graph class by changing the class(!) variable holding the
    factory for that dict-like structure. The variable names are
    node_dict_factory, node_attr_dict_factory, adjlist_inner_dict_factory,
    adjlist_outer_dict_factory, edge_key_dict_factory, edge_attr_dict_factory
    and graph_attr_dict_factory.

    node_dict_factory : function, (default: dict)
        Factory function to be used to create the dict containing node
        attributes, keyed by node id.
        It should require no arguments and return a dict-like object

    node_attr_dict_factory: function, (default: dict)
        Factory function to be used to create the node attribute
        dict which holds attribute values keyed by attribute name.
        It should require no arguments and return a dict-like object

    adjlist_outer_dict_factory : function, (default: dict)
        Factory function to be used to create the outer-most dict
        in the data structure that holds adjacency info keyed by node.
        It should require no arguments and return a dict-like object.

    adjlist_inner_dict_factory : function, (default: dict)
        Factory function to be used to create the adjacency list
        dict which holds multiedge key dicts keyed by neighbor.
        It should require no arguments and return a dict-like object.

    edge_key_dict_factory : function, (default: dict)
        Factory function to be used to create the edge key dict
        which holds edge data keyed by edge key.
        It should require no arguments and return a dict-like object.

    edge_attr_dict_factory : function, (default: dict)
        Factory function to be used to create the edge attribute
        dict which holds attribute values keyed by attribute name.
        It should require no arguments and return a dict-like object.

    graph_attr_dict_factory : function, (default: dict)
        Factory function to be used to create the graph attribute
        dict which holds attribute values keyed by attribute name.
        It should require no arguments and return a dict-like object.

    Typically, if your extension doesn't impact the data structure all
    methods will inherited without issue except: `to_directed/to_undirected`.
    By default these methods create a DiGraph/Graph class and you probably
    want them to create your extension of a DiGraph/Graph. To facilitate
    this we define two class variables that you can set in your subclass.

    to_directed_class : callable, (default: DiGraph or MultiDiGraph)
        Class to create a new graph structure in the `to_directed` method.
        If `None`, a NetworkX class (DiGraph or MultiDiGraph) is used.

    to_undirected_class : callable, (default: Graph or MultiGraph)
        Class to create a new graph structure in the `to_undirected` method.
        If `None`, a NetworkX class (Graph or MultiGraph) is used.

    **Subclassing Example**

    Create a low memory graph class that effectively disallows edge
    attributes by using a single attribute dict for all edges.
    This reduces the memory used, but you lose edge attributes.

    >>> class ThinGraph(nx.Graph):
    ...     all_edge_dict = {"weight": 1}
    ...
    ...     def single_edge_dict(self):
    ...         return self.all_edge_dict
    ...
    ...     edge_attr_dict_factory = single_edge_dict
    >>> G = ThinGraph()
    >>> G.add_edge(2, 1)
    >>> G[2][1]
    {'weight': 1}
    >>> G.add_edge(2, 2)
    >>> G[2][1] is G[2][2]
    True
    """

    # node_dict_factory = dict    # already assigned in Graph
    # adjlist_outer_dict_factory = dict
    # adjlist_inner_dict_factory = dict
    edge_key_dict_factory = dict
    # edge_attr_dict_factory = dict

    def __init__(self, incoming_graph_data=None, multigraph_input=None, **attr):
        """Initialize a graph with edges, name, or graph attributes.

        Parameters
        ----------
        incoming_graph_data : input graph
            Data to initialize graph.  If incoming_graph_data=None (default)
            an empty graph is created.  The data can be an edge list, or any
            NetworkX graph object.  If the corresponding optional Python
            packages are installed the data can also be a 2D NumPy array, a
            SciPy sparse array, or a PyGraphviz graph.

        multigraph_input : bool or None (default None)
            Note: Only used when `incoming_graph_data` is a dict.
            If True, `incoming_graph_data` is assumed to be a
            dict-of-dict-of-dict-of-dict structure keyed by
            node to neighbor to edge keys to edge data for multi-edges.
            A NetworkXError is raised if this is not the case.
            If False, :func:`to_networkx_graph` is used to try to determine
            the dict's graph data structure as either a dict-of-dict-of-dict
            keyed by node to neighbor to edge data, or a dict-of-iterable
            keyed by node to neighbors.
            If None, the treatment for True is tried, but if it fails,
            the treatment for False is tried.

        attr : keyword arguments, optional (default= no attributes)
            Attributes to add to graph as key=value pairs.

        See Also
        --------
        convert

        Examples
        --------
        >>> G = nx.Graph()  # or DiGraph, MultiGraph, MultiDiGraph, etc
        >>> G = nx.Graph(name="my graph")
        >>> e = [(1, 2), (2, 3), (3, 4)]  # list of edges
        >>> G = nx.Graph(e)

        Arbitrary graph attribute pairs (key=value) may be assigned

        >>> G = nx.Graph(e, day="Friday")
        >>> G.graph
        {'day': 'Friday'}

        """
        # multigraph_input can be None/True/False. So check "is not False"
        if isinstance(incoming_graph_data, dict) and multigraph_input is not False:
            DiGraph.__init__(self)
            try:
                convert.from_dict_of_dicts(
                    incoming_graph_data, create_using=self, multigraph_input=True
                )
                self.graph.update(attr)
            except Exception as err:
                if multigraph_input is True:
                    raise nx.NetworkXError(
                        f"converting multigraph_input raised:\n{type(err)}: {err}"
                    )
                DiGraph.__init__(self, incoming_graph_data, **attr)
        else:
            DiGraph.__init__(self, incoming_graph_data, **attr)

    @cached_property
    def adj(self):
        """Graph adjacency object holding the neighbors of each node.

        This object is a read-only dict-like structure with node keys
        and neighbor-dict values.  The neighbor-dict is keyed by neighbor
        to the edgekey-dict.  So `G.adj[3][2][0]['color'] = 'blue'` sets
        the color of the edge `(3, 2, 0)` to `"blue"`.

        Iterating over G.adj behaves like a dict. Useful idioms include
        `for nbr, datadict in G.adj[n].items():`.

        The neighbor information is also provided by subscripting the graph.
        So `for nbr, foovalue in G[node].data('foo', default=1):` works.

        For directed graphs, `G.adj` holds outgoing (successor) info.
        """
        return MultiAdjacencyView(self._succ)

    @cached_property
    def succ(self):
        """Graph adjacency object holding the successors of each node.

        This object is a read-only dict-like structure with node keys
        and neighbor-dict values.  The neighbor-dict is keyed by neighbor
        to the edgekey-dict.  So `G.adj[3][2][0]['color'] = 'blue'` sets
        the color of the edge `(3, 2, 0)` to `"blue"`.

        Iterating over G.adj behaves like a dict. Useful idioms include
        `for nbr, datadict in G.adj[n].items():`.

        The neighbor information is also provided by subscripting the graph.
        So `for nbr, foovalue in G[node].data('foo', default=1):` works.

        For directed graphs, `G.succ` is identical to `G.adj`.
        """
        return MultiAdjacencyView(self._succ)

    @cached_property
    def pred(self):
        """Graph adjacency object holding the predecessors of each node.

        This object is a read-only dict-like structure with node keys
        and neighbor-dict values.  The neighbor-dict is keyed by neighbor
        to the edgekey-dict.  So `G.adj[3][2][0]['color'] = 'blue'` sets
        the color of the edge `(3, 2, 0)` to `"blue"`.

        Iterating over G.adj behaves like a dict. Useful idioms include
        `for nbr, datadict in G.adj[n].items():`.
        """
        return MultiAdjacencyView(self._pred)

    def add_edge(self, u_for_edge, v_for_edge, key=None, **attr):
        """Add an edge between u and v.

        The nodes u and v will be automatically added if they are
        not already in the graph.

        Edge attributes can be specified with keywords or by directly
        accessing the edge's attribute dictionary. See examples below.

        Parameters
        ----------
        u_for_edge, v_for_edge : nodes
            Nodes can be, for example, strings or numbers.
            Nodes must be hashable (and not None) Python objects.
        key : hashable identifier, optional (default=lowest unused integer)
            Used to distinguish multiedges between a pair of nodes.
        attr : keyword arguments, optional
            Edge data (or labels or objects) can be assigned using
            keyword arguments.

        Returns
        -------
        The edge key assigned to the edge.

        See Also
        --------
        add_edges_from : add a collection of edges

        Notes
        -----
        To replace/update edge data, use the optional key argument
        to identify a unique edge.  Otherwise a new edge will be created.

        NetworkX algorithms designed for weighted graphs cannot use
        multigraphs directly because it is not clear how to handle
        multiedge weights.  Convert to Graph using edge attribute
        'weight' to enable weighted graph algorithms.

        Default keys are generated using the method `new_edge_key()`.
        This method can be overridden by subclassing the base class and
        providing a custom `new_edge_key()` method.

        Examples
        --------
        The following all add the edge e=(1, 2) to graph G:

        >>> G = nx.MultiDiGraph()
        >>> e = (1, 2)
        >>> key = G.add_edge(1, 2)  # explicit two-node form
        >>> G.add_edge(*e)  # single edge as tuple of two nodes
        1
        >>> G.add_edges_from([(1, 2)])  # add edges from iterable container
        [2]

        Associate data to edges using keywords:

        >>> key = G.add_edge(1, 2, weight=3)
        >>> key = G.add_edge(1, 2, key=0, weight=4)  # update data for key=0
        >>> key = G.add_edge(1, 3, weight=7, capacity=15, length=342.7)

        For non-string attribute keys, use subscript notation.

        >>> ekey = G.add_edge(1, 2)
        >>> G[1][2][0].update({0: 5})
        >>> G.edges[1, 2, 0].update({0: 5})
        """
        u, v = u_for_edge, v_for_edge
        # add nodes
        if u not in self._succ:
            if u is None:
                raise ValueError("None cannot be a node")
            self._succ[u] = self.adjlist_inner_dict_factory()
            self._pred[u] = self.adjlist_inner_dict_factory()
            self._node[u] = self.node_attr_dict_factory()
        if v not in self._succ:
            if v is None:
                raise ValueError("None cannot be a node")
            self._succ[v] = self.adjlist_inner_dict_factory()
            self._pred[v] = self.adjlist_inner_dict_factory()
            self._node[v] = self.node_attr_dict_factory()
        if key is None:
            key = self.new_edge_key(u, v)
        if v in self._succ[u]:
            keydict = self._adj[u][v]
            datadict = keydict.get(key, self.edge_attr_dict_factory())
            datadict.update(attr)
            keydict[key] = datadict
        else:
            # selfloops work this way without special treatment
            datadict = self.edge_attr_dict_factory()
            datadict.update(attr)
            keydict = self.edge_key_dict_factory()
            keydict[key] = datadict
            self._succ[u][v] = keydict
            self._pred[v][u] = keydict
        nx._clear_cache(self)
        return key

    def remove_edge(self, u, v, key=None):
        """Remove an edge between u and v.

        Parameters
        ----------
        u, v : nodes
            Remove an edge between nodes u and v.
        key : hashable identifier, optional (default=None)
            Used to distinguish multiple edges between a pair of nodes.
            If None, remove a single edge between u and v. If there are
            multiple edges, removes the last edge added in terms of
            insertion order.

        Raises
        ------
        NetworkXError
            If there is not an edge between u and v, or
            if there is no edge with the specified key.

        See Also
        --------
        remove_edges_from : remove a collection of edges

        Examples
        --------
        >>> G = nx.MultiDiGraph()
        >>> nx.add_path(G, [0, 1, 2, 3])
        >>> G.remove_edge(0, 1)
        >>> e = (1, 2)
        >>> G.remove_edge(*e)  # unpacks e from an edge tuple

        For multiple edges

        >>> G = nx.MultiDiGraph()
        >>> G.add_edges_from([(1, 2), (1, 2), (1, 2)])  # key_list returned
        [0, 1, 2]

        When ``key=None`` (the default), edges are removed in the opposite
        order that they were added:

        >>> G.remove_edge(1, 2)
        >>> G.edges(keys=True)
        OutMultiEdgeView([(1, 2, 0), (1, 2, 1)])

        For edges with keys

        >>> G = nx.MultiDiGraph()
        >>> G.add_edge(1, 2, key="first")
        'first'
        >>> G.add_edge(1, 2, key="second")
        'second'
        >>> G.remove_edge(1, 2, key="first")
        >>> G.edges(keys=True)
        OutMultiEdgeView([(1, 2, 'second')])

        """
        try:
            d = self._adj[u][v]
        except KeyError as err:
            raise NetworkXError(f"The edge {u}-{v} is not in the graph.") from err
        # remove the edge with specified data
        if key is None:
            d.popitem()
        else:
            try:
                del d[key]
            except KeyError as err:
                msg = f"The edge {u}-{v} with key {key} is not in the graph."
                raise NetworkXError(msg) from err
        if len(d) == 0:
            # remove the key entries if last edge
            del self._succ[u][v]
            del self._pred[v][u]
        nx._clear_cache(self)

    @cached_property
    def edges(self):
        """An OutMultiEdgeView of the Graph as G.edges or G.edges().

        edges(self, nbunch=None, data=False, keys=False, default=None)

        The OutMultiEdgeView provides set-like operations on the edge-tuples
        as well as edge attribute lookup. When called, it also provides
        an EdgeDataView object which allows control of access to edge
        attributes (but does not provide set-like operations).
        Hence, ``G.edges[u, v, k]['color']`` provides the value of the color
        attribute for the edge from ``u`` to ``v`` with key ``k`` while
        ``for (u, v, k, c) in G.edges(data='color', default='red', keys=True):``
        iterates through all the edges yielding the color attribute with
        default `'red'` if no color attribute exists.

        Edges are returned as tuples with optional data and keys
        in the order (node, neighbor, key, data). If ``keys=True`` is not
        provided, the tuples will just be (node, neighbor, data), but
        multiple tuples with the same node and neighbor will be
        generated when multiple edges between two nodes exist.

        Parameters
        ----------
        nbunch : single node, container, or all nodes (default= all nodes)
            The view will only report edges from these nodes.
        data : string or bool, optional (default=False)
            The edge attribute returned in 3-tuple (u, v, ddict[data]).
            If True, return edge attribute dict in 3-tuple (u, v, ddict).
            If False, return 2-tuple (u, v).
        keys : bool, optional (default=False)
            If True, return edge keys with each edge, creating (u, v, k,
            d) tuples when data is also requested (the default) and (u,
            v, k) tuples when data is not requested.
        default : value, optional (default=None)
            Value used for edges that don't have the requested attribute.
            Only relevant if data is not True or False.

        Returns
        -------
        edges : OutMultiEdgeView
            A view of edge attributes, usually it iterates over (u, v)
            (u, v, k) or (u, v, k, d) tuples of edges, but can also be
            used for attribute lookup as ``edges[u, v, k]['foo']``.

        Notes
        -----
        Nodes in nbunch that are not in the graph will be (quietly) ignored.
        For directed graphs this returns the out-edges.

        Examples
        --------
        >>> G = nx.MultiDiGraph()
        >>> nx.add_path(G, [0, 1, 2])
        >>> key = G.add_edge(2, 3, weight=5)
        >>> key2 = G.add_edge(1, 2)  # second edge between these nodes
        >>> [e for e in G.edges()]
        [(0, 1), (1, 2), (1, 2), (2, 3)]
        >>> list(G.edges(data=True))  # default data is {} (empty dict)
        [(0, 1, {}), (1, 2, {}), (1, 2, {}), (2, 3, {'weight': 5})]
        >>> list(G.edges(data="weight", default=1))
        [(0, 1, 1), (1, 2, 1), (1, 2, 1), (2, 3, 5)]
        >>> list(G.edges(keys=True))  # default keys are integers
        [(0, 1, 0), (1, 2, 0), (1, 2, 1), (2, 3, 0)]
        >>> list(G.edges(data=True, keys=True))
        [(0, 1, 0, {}), (1, 2, 0, {}), (1, 2, 1, {}), (2, 3, 0, {'weight': 5})]
        >>> list(G.edges(data="weight", default=1, keys=True))
        [(0, 1, 0, 1), (1, 2, 0, 1), (1, 2, 1, 1), (2, 3, 0, 5)]
        >>> list(G.edges([0, 2]))
        [(0, 1), (2, 3)]
        >>> list(G.edges(0))
        [(0, 1)]
        >>> list(G.edges(1))
        [(1, 2), (1, 2)]

        See Also
        --------
        in_edges, out_edges
        """
        return OutMultiEdgeView(self)

    # alias out_edges to edges
    @cached_property
    def out_edges(self):
        return OutMultiEdgeView(self)

    out_edges.__doc__ = edges.__doc__

    @cached_property
    def in_edges(self):
        """A view of the in edges of the graph as G.in_edges or G.in_edges().

        in_edges(self, nbunch=None, data=False, keys=False, default=None)

        Parameters
        ----------
        nbunch : single node, container, or all nodes (default= all nodes)
            The view will only report edges incident to these nodes.
        data : string or bool, optional (default=False)
            The edge attribute returned in 3-tuple (u, v, ddict[data]).
            If True, return edge attribute dict in 3-tuple (u, v, ddict).
            If False, return 2-tuple (u, v).
        keys : bool, optional (default=False)
            If True, return edge keys with each edge, creating 3-tuples
            (u, v, k) or with data, 4-tuples (u, v, k, d).
        default : value, optional (default=None)
            Value used for edges that don't have the requested attribute.
            Only relevant if data is not True or False.

        Returns
        -------
        in_edges : InMultiEdgeView or InMultiEdgeDataView
            A view of edge attributes, usually it iterates over (u, v)
            or (u, v, k) or (u, v, k, d) tuples of edges, but can also be
            used for attribute lookup as `edges[u, v, k]['foo']`.

        See Also
        --------
        edges
        """
        return InMultiEdgeView(self)

    @cached_property
    def degree(self):
        """A DegreeView for the Graph as G.degree or G.degree().

        The node degree is the number of edges adjacent to the node.
        The weighted node degree is the sum of the edge weights for
        edges incident to that node.

        This object provides an iterator for (node, degree) as well as
        lookup for the degree for a single node.

        Parameters
        ----------
        nbunch : single node, container, or all nodes (default= all nodes)
            The view will only report edges incident to these nodes.

        weight : string or None, optional (default=None)
           The name of an edge attribute that holds the numerical value used
           as a weight.  If None, then each edge has weight 1.
           The degree is the sum of the edge weights adjacent to the node.

        Returns
        -------
        DiMultiDegreeView or int
            If multiple nodes are requested (the default), returns a `DiMultiDegreeView`
            mapping nodes to their degree.
            If a single node is requested, returns the degree of the node as an integer.

        See Also
        --------
        out_degree, in_degree

        Examples
        --------
        >>> G = nx.MultiDiGraph()
        >>> nx.add_path(G, [0, 1, 2, 3])
        >>> G.degree(0)  # node 0 with degree 1
        1
        >>> list(G.degree([0, 1, 2]))
        [(0, 1), (1, 2), (2, 2)]
        >>> G.add_edge(0, 1)  # parallel edge
        1
        >>> list(G.degree([0, 1, 2]))  # parallel edges are counted
        [(0, 2), (1, 3), (2, 2)]

        """
        return DiMultiDegreeView(self)

    @cached_property
    def in_degree(self):
        """A DegreeView for (node, in_degree) or in_degree for single node.

        The node in-degree is the number of edges pointing into the node.
        The weighted node degree is the sum of the edge weights for
        edges incident to that node.

        This object provides an iterator for (node, degree) as well as
        lookup for the degree for a single node.

        Parameters
        ----------
        nbunch : single node, container, or all nodes (default= all nodes)
            The view will only report edges incident to these nodes.

        weight : string or None, optional (default=None)
           The edge attribute that holds the numerical value used
           as a weight.  If None, then each edge has weight 1.
           The degree is the sum of the edge weights adjacent to the node.

        Returns
        -------
        If a single node is requested
        deg : int
            Degree of the node

        OR if multiple nodes are requested
        nd_iter : iterator
            The iterator returns two-tuples of (node, in-degree).

        See Also
        --------
        degree, out_degree

        Examples
        --------
        >>> G = nx.MultiDiGraph()
        >>> nx.add_path(G, [0, 1, 2, 3])
        >>> G.in_degree(0)  # node 0 with degree 0
        0
        >>> list(G.in_degree([0, 1, 2]))
        [(0, 0), (1, 1), (2, 1)]
        >>> G.add_edge(0, 1)  # parallel edge
        1
        >>> list(G.in_degree([0, 1, 2]))  # parallel edges counted
        [(0, 0), (1, 2), (2, 1)]

        """
        return InMultiDegreeView(self)

    @cached_property
    def out_degree(self):
        """Returns an iterator for (node, out-degree) or out-degree for single node.

        out_degree(self, nbunch=None, weight=None)

        The node out-degree is the number of edges pointing out of the node.
        This function returns the out-degree for a single node or an iterator
        for a bunch of nodes or if nothing is passed as argument.

        Parameters
        ----------
        nbunch : single node, container, or all nodes (default= all nodes)
            The view will only report edges incident to these nodes.

        weight : string or None, optional (default=None)
           The edge attribute that holds the numerical value used
           as a weight.  If None, then each edge has weight 1.
           The degree is the sum of the edge weights.

        Returns
        -------
        If a single node is requested
        deg : int
            Degree of the node

        OR if multiple nodes are requested
        nd_iter : iterator
            The iterator returns two-tuples of (node, out-degree).

        See Also
        --------
        degree, in_degree

        Examples
        --------
        >>> G = nx.MultiDiGraph()
        >>> nx.add_path(G, [0, 1, 2, 3])
        >>> G.out_degree(0)  # node 0 with degree 1
        1
        >>> list(G.out_degree([0, 1, 2]))
        [(0, 1), (1, 1), (2, 1)]
        >>> G.add_edge(0, 1)  # parallel edge
        1
        >>> list(G.out_degree([0, 1, 2]))  # counts parallel edges
        [(0, 2), (1, 1), (2, 1)]

        """
        return OutMultiDegreeView(self)

    def is_multigraph(self):
        """Returns True if graph is a multigraph, False otherwise."""
        return True

    def is_directed(self):
        """Returns True if graph is directed, False otherwise."""
        return True

    def to_undirected(self, reciprocal=False, as_view=False):
        """Returns an undirected representation of the digraph.

        Parameters
        ----------
        reciprocal : bool (optional)
          If True only keep edges that appear in both directions
          in the original digraph.
        as_view : bool (optional, default=False)
          If True return an undirected view of the original directed graph.

        Returns
        -------
        G : MultiGraph
            An undirected graph with the same name and nodes and
            with edge (u, v, data) if either (u, v, data) or (v, u, data)
            is in the digraph.  If both edges exist in digraph and
            their edge data is different, only one edge is created
            with an arbitrary choice of which edge data to use.
            You must check and correct for this manually if desired.

        See Also
        --------
        MultiGraph, copy, add_edge, add_edges_from

        Notes
        -----
        This returns a "deepcopy" of the edge, node, and
        graph attributes which attempts to completely copy
        all of the data and references.

        This is in contrast to the similar D=MultiDiGraph(G) which
        returns a shallow copy of the data.

        See the Python copy module for more information on shallow
        and deep copies, https://docs.python.org/3/library/copy.html.

        Warning: If you have subclassed MultiDiGraph to use dict-like
        objects in the data structure, those changes do not transfer
        to the MultiGraph created by this method.

        Examples
        --------
        >>> G = nx.path_graph(2)  # or MultiGraph, etc
        >>> H = G.to_directed()
        >>> list(H.edges)
        [(0, 1), (1, 0)]
        >>> G2 = H.to_undirected()
        >>> list(G2.edges)
        [(0, 1)]
        """
        graph_class = self.to_undirected_class()
        if as_view is True:
            return nx.graphviews.generic_graph_view(self, graph_class)
        # deepcopy when not a view
        G = graph_class()
        G.graph.update(deepcopy(self.graph))
        G.add_nodes_from((n, deepcopy(d)) for n, d in self._node.items())
        if reciprocal is True:
            G.add_edges_from(
                (u, v, key, deepcopy(data))
                for u, nbrs in self._adj.items()
                for v, keydict in nbrs.items()
                for key, data in keydict.items()
                if v in self._pred[u] and key in self._pred[u][v]
            )
        else:
            G.add_edges_from(
                (u, v, key, deepcopy(data))
                for u, nbrs in self._adj.items()
                for v, keydict in nbrs.items()
                for key, data in keydict.items()
            )
        return G

    def reverse(self, copy=True):
        """Returns the reverse of the graph.

        The reverse is a graph with the same nodes and edges
        but with the directions of the edges reversed.

        Parameters
        ----------
        copy : bool optional (default=True)
            If True, return a new DiGraph holding the reversed edges.
            If False, the reverse graph is created using a view of
            the original graph.
        """
        if copy:
            H = self.__class__()
            H.graph.update(deepcopy(self.graph))
            H.add_nodes_from((n, deepcopy(d)) for n, d in self._node.items())
            H.add_edges_from(
                (v, u, k, deepcopy(d))
                for u, v, k, d in self.edges(keys=True, data=True)
            )
            return H
        return nx.reverse_view(self)
