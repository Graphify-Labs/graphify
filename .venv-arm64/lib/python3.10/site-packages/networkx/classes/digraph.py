"""Base class for directed graphs."""

from copy import deepcopy
from functools import cached_property

import networkx as nx
from networkx import convert
from networkx.classes.coreviews import AdjacencyView
from networkx.classes.graph import Graph
from networkx.classes.reportviews import (
    DiDegreeView,
    InDegreeView,
    InEdgeView,
    OutDegreeView,
    OutEdgeView,
)
from networkx.exception import NetworkXError

__all__ = ["DiGraph"]


class _CachedPropertyResetterAdjAndSucc:
    """Data Descriptor class that syncs and resets cached properties adj and succ

    The cached properties `adj` and `succ` are reset whenever `_adj` or `_succ`
    are set to new objects. In addition, the attributes `_succ` and `_adj`
    are synced so these two names point to the same object.

    Warning: most of the time, when ``G._adj`` is set, ``G._pred`` should also
    be set to maintain a valid data structure. They share datadicts.

    This object sits on a class and ensures that any instance of that
    class clears its cached properties "succ" and "adj" whenever the
    underlying instance attributes "_succ" or "_adj" are set to a new object.
    It only affects the set process of the obj._adj and obj._succ attribute.
    All get/del operations act as they normally would.

    For info on Data Descriptors see: https://docs.python.org/3/howto/descriptor.html
    """

    def __set__(self, obj, value):
        od = obj.__dict__
        od["_adj"] = value
        od["_succ"] = value
        # reset cached properties
        props = [
            "adj",
            "succ",
            "edges",
            "out_edges",
            "degree",
            "out_degree",
            "in_degree",
        ]
        for prop in props:
            if prop in od:
                del od[prop]


class _CachedPropertyResetterPred:
    """Data Descriptor class for _pred that resets ``pred`` cached_property when needed

    This assumes that the ``cached_property`` ``G.pred`` should be reset whenever
    ``G._pred`` is set to a new value.

    Warning: most of the time, when ``G._pred`` is set, ``G._adj`` should also
    be set to maintain a valid data structure. They share datadicts.

    This object sits on a class and ensures that any instance of that
    class clears its cached property "pred" whenever the underlying
    instance attribute "_pred" is set to a new object. It only affects
    the set process of the obj._pred attribute. All get/del operations
    act as they normally would.

    For info on Data Descriptors see: https://docs.python.org/3/howto/descriptor.html
    """

    def __set__(self, obj, value):
        od = obj.__dict__
        od["_pred"] = value
        # reset cached properties
        props = ["pred", "in_edges", "degree", "out_degree", "in_degree"]
        for prop in props:
            if prop in od:
                del od[prop]


class DiGraph(Graph):
    """
    Base class for directed graphs.

    A DiGraph stores nodes and edges with optional data, or attributes.

    DiGraphs hold directed edges.  Self loops are allowed but multiple
    (parallel) edges are not.

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

    attr : keyword arguments, optional (default= no attributes)
        Attributes to add to graph as key=value pairs.

    See Also
    --------
    Graph
    MultiGraph
    MultiDiGraph

    Examples
    --------
    Create an empty graph structure (a "null graph") with no nodes and
    no edges.

    >>> G = nx.DiGraph()

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

    >>> G.add_edge(1, 2)

    a list of edges,

    >>> G.add_edges_from([(1, 2), (1, 3)])

    or a collection of edges,

    >>> G.add_edges_from(H.edges)

    If some edges connect nodes not yet in the graph, the nodes
    are added automatically.  There are no errors when adding
    nodes or edges that already exist.

    **Attributes:**

    Each graph, node, and edge can hold key/value attribute pairs
    in an associated attribute dictionary (the keys must be hashable).
    By default these are empty, but can be added or changed using
    add_edge, add_node or direct manipulation of the attribute
    dictionaries named graph, node and edge respectively.

    >>> G = nx.DiGraph(day="Friday")
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

    >>> G.add_edge(1, 2, weight=4.7)
    >>> G.add_edges_from([(3, 4), (4, 5)], color="red")
    >>> G.add_edges_from([(1, 2, {"color": "blue"}), (2, 3, {"weight": 8})])
    >>> G[1][2]["weight"] = 4.7
    >>> G.edges[1, 2]["weight"] = 4

    Warning: we protect the graph data structure by making `G.edges[1, 2]` a
    read-only dict-like structure. However, you can assign to attributes
    in e.g. `G.edges[1, 2]`. Thus, use 2 sets of brackets to add/change
    data attributes: `G.edges[1, 2]['weight'] = 4`
    (For multigraphs: `MG.edges[u, v, key][name] = value`).

    **Shortcuts:**

    Many common graph features allow python syntax to speed reporting.

    >>> 1 in G  # check if node in graph
    True
    >>> [n for n in G if n < 3]  # iterate through nodes
    [1, 2]
    >>> len(G)  # number of nodes in graph
    5

    Often the best way to traverse all edges of a graph is via the neighbors.
    The neighbors are reported as an adjacency-dict `G.adj` or `G.adjacency()`

    >>> for n, nbrsdict in G.adjacency():
    ...     for nbr, eattr in nbrsdict.items():
    ...         if "weight" in eattr:
    ...             # Do something useful with the edges
    ...             pass

    But the edges reporting object is often more convenient:

    >>> for u, v, weight in G.edges(data="weight"):
    ...     if weight is not None:
    ...         # Do something useful with the edges
    ...         pass

    **Reporting:**

    Simple graph information is obtained using object-attributes and methods.
    Reporting usually provides views instead of containers to reduce memory
    usage. The views update as the graph is updated similarly to dict-views.
    The objects `nodes`, `edges` and `adj` provide access to data attributes
    via lookup (e.g. `nodes[n]`, `edges[u, v]`, `adj[u][v]`) and iteration
    (e.g. `nodes.items()`, `nodes.data('color')`,
    `nodes.data('color', default='blue')` and similarly for `edges`)
    Views exist for `nodes`, `edges`, `neighbors()`/`adj` and `degree`.

    For details on these and other miscellaneous methods, see below.

    **Subclasses (Advanced):**

    The Graph class uses a dict-of-dict-of-dict data structure.
    The outer dict (node_dict) holds adjacency information keyed by node.
    The next dict (adjlist_dict) represents the adjacency information and holds
    edge data keyed by neighbor.  The inner dict (edge_attr_dict) represents
    the edge data and holds edge attribute values keyed by attribute names.

    Each of these three dicts can be replaced in a subclass by a user defined
    dict-like object. In general, the dict-like features should be
    maintained but extra features can be added. To replace one of the
    dicts create a new graph class by changing the class(!) variable
    holding the factory for that dict-like structure. The variable names are
    node_dict_factory, node_attr_dict_factory, adjlist_inner_dict_factory,
    adjlist_outer_dict_factory, edge_attr_dict_factory and graph_attr_dict_factory.

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

    adjlist_inner_dict_factory : function, optional (default: dict)
        Factory function to be used to create the adjacency list
        dict which holds edge data keyed by neighbor.
        It should require no arguments and return a dict-like object

    edge_attr_dict_factory : function, optional (default: dict)
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

    _adj = _CachedPropertyResetterAdjAndSucc()  # type: ignore[assignment]
    _succ = _adj  # type: ignore[has-type]
    _pred = _CachedPropertyResetterPred()

    def __init__(self, incoming_graph_data=None, **attr):
        """Initialize a graph with edges, name, or graph attributes.

        Parameters
        ----------
        incoming_graph_data : input graph (optional, default: None)
            Data to initialize graph.  If None (default) an empty
            graph is created.  The data can be an edge list, or any
            NetworkX graph object.  If the corresponding optional Python
            packages are installed the data can also be a 2D NumPy array, a
            SciPy sparse array, or a PyGraphviz graph.

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
        self.graph = self.graph_attr_dict_factory()  # dictionary for graph attributes
        self._node = self.node_dict_factory()  # dictionary for node attr
        # We store two adjacency lists:
        # the predecessors of node n are stored in the dict self._pred
        # the successors of node n are stored in the dict self._succ=self._adj
        self._adj = self.adjlist_outer_dict_factory()  # empty adjacency dict successor
        self._pred = self.adjlist_outer_dict_factory()  # predecessor
        # Note: self._succ = self._adj  # successor

        self.__networkx_cache__ = {}
        # attempt to load graph with data
        if incoming_graph_data is not None:
            convert.to_networkx_graph(incoming_graph_data, create_using=self)
        # load graph attributes (must be after convert)
        self.graph.update(attr)

    @cached_property
    def adj(self):
        """Graph adjacency object holding the neighbors of each node.

        This object is a read-only dict-like structure with node keys
        and neighbor-dict values.  The neighbor-dict is keyed by neighbor
        to the edge-data-dict.  So `G.adj[3][2]['color'] = 'blue'` sets
        the color of the edge `(3, 2)` to `"blue"`.

        Iterating over G.adj behaves like a dict. Useful idioms include
        `for nbr, datadict in G.adj[n].items():`.

        The neighbor information is also provided by subscripting the graph.
        So `for nbr, foovalue in G[node].data('foo', default=1):` works.

        For directed graphs, `G.adj` holds outgoing (successor) info.
        """
        return AdjacencyView(self._succ)

    @cached_property
    def succ(self):
        """Graph adjacency object holding the successors of each node.

        This object is a read-only dict-like structure with node keys
        and neighbor-dict values.  The neighbor-dict is keyed by neighbor
        to the edge-data-dict.  So `G.succ[3][2]['color'] = 'blue'` sets
        the color of the edge `(3, 2)` to `"blue"`.

        Iterating over G.succ behaves like a dict. Useful idioms include
        `for nbr, datadict in G.succ[n].items():`.  A data-view not provided
        by dicts also exists: `for nbr, foovalue in G.succ[node].data('foo'):`
        and a default can be set via a `default` argument to the `data` method.

        The neighbor information is also provided by subscripting the graph.
        So `for nbr, foovalue in G[node].data('foo', default=1):` works.

        For directed graphs, `G.adj` is identical to `G.succ`.
        """
        return AdjacencyView(self._succ)

    @cached_property
    def pred(self):
        """Graph adjacency object holding the predecessors of each node.

        This object is a read-only dict-like structure with node keys
        and neighbor-dict values.  The neighbor-dict is keyed by neighbor
        to the edge-data-dict.  So `G.pred[2][3]['color'] = 'blue'` sets
        the color of the edge `(3, 2)` to `"blue"`.

        Iterating over G.pred behaves like a dict. Useful idioms include
        `for nbr, datadict in G.pred[n].items():`.  A data-view not provided
        by dicts also exists: `for nbr, foovalue in G.pred[node].data('foo'):`
        A default can be set via a `default` argument to the `data` method.
        """
        return AdjacencyView(self._pred)

    def add_node(self, node_for_adding, **attr):
        """Add a single node `node_for_adding` and update node attributes.

        Parameters
        ----------
        node_for_adding : node
            A node can be any hashable Python object except None.
        attr : keyword arguments, optional
            Set or change node attributes using key=value.

        See Also
        --------
        add_nodes_from

        Examples
        --------
        >>> G = nx.Graph()  # or DiGraph, MultiGraph, MultiDiGraph, etc
        >>> G.add_node(1)
        >>> G.add_node("Hello")
        >>> K3 = nx.Graph([(0, 1), (1, 2), (2, 0)])
        >>> G.add_node(K3)
        >>> G.number_of_nodes()
        3

        Use keywords set/change node attributes:

        >>> G.add_node(1, size=10)
        >>> G.add_node(3, weight=0.4, UTM=("13S", 382871, 3972649))

        Notes
        -----
        A hashable object is one that can be used as a key in a Python
        dictionary. This includes strings, numbers, tuples of strings
        and numbers, etc.

        On many platforms hashable items also include mutables such as
        NetworkX Graphs, though one should be careful that the hash
        doesn't change on mutables.
        """
        if node_for_adding not in self._succ:
            if node_for_adding is None:
                raise ValueError("None cannot be a node")
            self._succ[node_for_adding] = self.adjlist_inner_dict_factory()
            self._pred[node_for_adding] = self.adjlist_inner_dict_factory()
            attr_dict = self._node[node_for_adding] = self.node_attr_dict_factory()
            attr_dict.update(attr)
        else:  # update attr even if node already exists
            self._node[node_for_adding].update(attr)
        nx._clear_cache(self)

    def add_nodes_from(self, nodes_for_adding, **attr):
        """Add multiple nodes.

        Parameters
        ----------
        nodes_for_adding : iterable container
            A container of nodes (list, dict, set, etc.).
            OR
            A container of (node, attribute dict) tuples.
            Node attributes are updated using the attribute dict.
        attr : keyword arguments, optional (default= no attributes)
            Update attributes for all nodes in nodes.
            Node attributes specified in nodes as a tuple take
            precedence over attributes specified via keyword arguments.

        See Also
        --------
        add_node

        Notes
        -----
        When adding nodes from an iterator over the graph you are changing,
        a `RuntimeError` can be raised with message:
        `RuntimeError: dictionary changed size during iteration`. This
        happens when the graph's underlying dictionary is modified during
        iteration. To avoid this error, evaluate the iterator into a separate
        object, e.g. by using `list(iterator_of_nodes)`, and pass this
        object to `G.add_nodes_from`.

        Examples
        --------
        >>> G = nx.Graph()  # or DiGraph, MultiGraph, MultiDiGraph, etc
        >>> G.add_nodes_from("Hello")
        >>> K3 = nx.Graph([(0, 1), (1, 2), (2, 0)])
        >>> G.add_nodes_from(K3)
        >>> sorted(G.nodes(), key=str)
        [0, 1, 2, 'H', 'e', 'l', 'o']

        Use keywords to update specific node attributes for every node.

        >>> G.add_nodes_from([1, 2], size=10)
        >>> G.add_nodes_from([3, 4], weight=0.4)

        Use (node, attrdict) tuples to update attributes for specific nodes.

        >>> G.add_nodes_from([(1, dict(size=11)), (2, {"color": "blue"})])
        >>> G.nodes[1]["size"]
        11
        >>> H = nx.Graph()
        >>> H.add_nodes_from(G.nodes(data=True))
        >>> H.nodes[1]["size"]
        11

        Evaluate an iterator over a graph if using it to modify the same graph

        >>> G = nx.DiGraph([(0, 1), (1, 2), (3, 4)])
        >>> # wrong way - will raise RuntimeError
        >>> # G.add_nodes_from(n + 1 for n in G.nodes)
        >>> # correct way
        >>> G.add_nodes_from(list(n + 1 for n in G.nodes))
        """
        for n in nodes_for_adding:
            try:
                newnode = n not in self._node
                newdict = attr
            except TypeError:
                n, ndict = n
                newnode = n not in self._node
                newdict = attr.copy()
                newdict.update(ndict)
            if newnode:
                if n is None:
                    raise ValueError("None cannot be a node")
                self._succ[n] = self.adjlist_inner_dict_factory()
                self._pred[n] = self.adjlist_inner_dict_factory()
                self._node[n] = self.node_attr_dict_factory()
            self._node[n].update(newdict)
        nx._clear_cache(self)

    def remove_node(self, n):
        """Remove node n.

        Removes the node n and all adjacent edges.
        Attempting to remove a nonexistent node will raise an exception.

        Parameters
        ----------
        n : node
           A node in the graph

        Raises
        ------
        NetworkXError
           If n is not in the graph.

        See Also
        --------
        remove_nodes_from

        Examples
        --------
        >>> G = nx.path_graph(3)  # or DiGraph, MultiGraph, MultiDiGraph, etc
        >>> list(G.edges)
        [(0, 1), (1, 2)]
        >>> G.remove_node(1)
        >>> list(G.edges)
        []

        """
        try:
            nbrs = self._succ[n]
            del self._node[n]
        except KeyError as err:  # NetworkXError if n not in self
            raise NetworkXError(f"The node {n} is not in the digraph.") from err
        for u in nbrs:
            del self._pred[u][n]  # remove all edges n-u in digraph
        del self._succ[n]  # remove node from succ
        for u in self._pred[n]:
            del self._succ[u][n]  # remove all edges n-u in digraph
        del self._pred[n]  # remove node from pred
        nx._clear_cache(self)

    def remove_nodes_from(self, nodes):
        """Remove multiple nodes.

        Parameters
        ----------
        nodes : iterable container
            A container of nodes (list, dict, set, etc.).  If a node
            in the container is not in the graph it is silently ignored.

        See Also
        --------
        remove_node

        Notes
        -----
        When removing nodes from an iterator over the graph you are changing,
        a `RuntimeError` will be raised with message:
        `RuntimeError: dictionary changed size during iteration`. This
        happens when the graph's underlying dictionary is modified during
        iteration. To avoid this error, evaluate the iterator into a separate
        object, e.g. by using `list(iterator_of_nodes)`, and pass this
        object to `G.remove_nodes_from`.

        Examples
        --------
        >>> G = nx.path_graph(3)  # or DiGraph, MultiGraph, MultiDiGraph, etc
        >>> e = list(G.nodes)
        >>> e
        [0, 1, 2]
        >>> G.remove_nodes_from(e)
        >>> list(G.nodes)
        []

        Evaluate an iterator over a graph if using it to modify the same graph

        >>> G = nx.DiGraph([(0, 1), (1, 2), (3, 4)])
        >>> # this command will fail, as the graph's dict is modified during iteration
        >>> # G.remove_nodes_from(n for n in G.nodes if n < 2)
        >>> # this command will work, since the dictionary underlying graph is not modified
        >>> G.remove_nodes_from(list(n for n in G.nodes if n < 2))
        """
        for n in nodes:
            try:
                succs = self._succ[n]
                del self._node[n]
                for u in succs:
                    del self._pred[u][n]  # remove all edges n-u in digraph
                del self._succ[n]  # now remove node
                for u in self._pred[n]:
                    del self._succ[u][n]  # remove all edges n-u in digraph
                del self._pred[n]  # now remove node
            except KeyError:
                pass  # silent failure on remove
        nx._clear_cache(self)

    def add_edge(self, u_of_edge, v_of_edge, **attr):
        """Add an edge between u and v.

        The nodes u and v will be automatically added if they are
        not already in the graph.

        Edge attributes can be specified with keywords or by directly
        accessing the edge's attribute dictionary. See examples below.

        Parameters
        ----------
        u_of_edge, v_of_edge : nodes
            Nodes can be, for example, strings or numbers.
            Nodes must be hashable (and not None) Python objects.
        attr : keyword arguments, optional
            Edge data (or labels or objects) can be assigned using
            keyword arguments.

        See Also
        --------
        add_edges_from : add a collection of edges

        Notes
        -----
        Adding an edge that already exists updates the edge data.

        Many NetworkX algorithms designed for weighted graphs use
        an edge attribute (by default `weight`) to hold a numerical value.

        Examples
        --------
        The following all add the edge e=(1, 2) to graph G:

        >>> G = nx.Graph()  # or DiGraph, MultiGraph, MultiDiGraph, etc
        >>> e = (1, 2)
        >>> G.add_edge(1, 2)  # explicit two-node form
        >>> G.add_edge(*e)  # single edge as tuple of two nodes
        >>> G.add_edges_from([(1, 2)])  # add edges from iterable container

        Associate data to edges using keywords:

        >>> G.add_edge(1, 2, weight=3)
        >>> G.add_edge(1, 3, weight=7, capacity=15, length=342.7)

        For non-string attribute keys, use subscript notation.

        >>> G.add_edge(1, 2)
        >>> G[1][2].update({0: 5})
        >>> G.edges[1, 2].update({0: 5})
        """
        u, v = u_of_edge, v_of_edge
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
        # add the edge
        datadict = self._adj[u].get(v, self.edge_attr_dict_factory())
        datadict.update(attr)
        self._succ[u][v] = datadict
        self._pred[v][u] = datadict
        nx._clear_cache(self)

    def add_edges_from(self, ebunch_to_add, **attr):
        """Add all the edges in ebunch_to_add.

        Parameters
        ----------
        ebunch_to_add : container of edges
            Each edge given in the container will be added to the
            graph. The edges must be given as 2-tuples (u, v) or
            3-tuples (u, v, d) where d is a dictionary containing edge data.
        attr : keyword arguments, optional
            Edge data (or labels or objects) can be assigned using
            keyword arguments.

        See Also
        --------
        add_edge : add a single edge
        add_weighted_edges_from : convenient way to add weighted edges

        Notes
        -----
        Adding the same edge twice has no effect but any edge data
        will be updated when each duplicate edge is added.

        Edge attributes specified in an ebunch take precedence over
        attributes specified via keyword arguments.

        When adding edges from an iterator over the graph you are changing,
        a `RuntimeError` can be raised with message:
        `RuntimeError: dictionary changed size during iteration`. This
        happens when the graph's underlying dictionary is modified during
        iteration. To avoid this error, evaluate the iterator into a separate
        object, e.g. by using `list(iterator_of_edges)`, and pass this
        object to `G.add_edges_from`.

        Examples
        --------
        >>> G = nx.Graph()  # or DiGraph, MultiGraph, MultiDiGraph, etc
        >>> G.add_edges_from([(0, 1), (1, 2)])  # using a list of edge tuples
        >>> e = zip(range(0, 3), range(1, 4))
        >>> G.add_edges_from(e)  # Add the path graph 0-1-2-3

        Associate data to edges

        >>> G.add_edges_from([(1, 2), (2, 3)], weight=3)
        >>> G.add_edges_from([(3, 4), (1, 4)], label="WN2898")

        Evaluate an iterator over a graph if using it to modify the same graph

        >>> G = nx.DiGraph([(1, 2), (2, 3), (3, 4)])
        >>> # Grow graph by one new node, adding edges to all existing nodes.
        >>> # wrong way - will raise RuntimeError
        >>> # G.add_edges_from(((5, n) for n in G.nodes))
        >>> # right way - note that there will be no self-edge for node 5
        >>> G.add_edges_from(list((5, n) for n in G.nodes))
        """
        for e in ebunch_to_add:
            ne = len(e)
            if ne == 3:
                u, v, dd = e
            elif ne == 2:
                u, v = e
                dd = {}
            else:
                raise NetworkXError(f"Edge tuple {e} must be a 2-tuple or 3-tuple.")
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
            datadict = self._adj[u].get(v, self.edge_attr_dict_factory())
            datadict.update(attr)
            datadict.update(dd)
            self._succ[u][v] = datadict
            self._pred[v][u] = datadict
        nx._clear_cache(self)

    def remove_edge(self, u, v):
        """Remove the edge between u and v.

        Parameters
        ----------
        u, v : nodes
            Remove the edge between nodes u and v.

        Raises
        ------
        NetworkXError
            If there is not an edge between u and v.

        See Also
        --------
        remove_edges_from : remove a collection of edges

        Examples
        --------
        >>> G = nx.Graph()  # or DiGraph, etc
        >>> nx.add_path(G, [0, 1, 2, 3])
        >>> G.remove_edge(0, 1)
        >>> e = (1, 2)
        >>> G.remove_edge(*e)  # unpacks e from an edge tuple
        >>> e = (2, 3, {"weight": 7})  # an edge with attribute data
        >>> G.remove_edge(*e[:2])  # select first part of edge tuple
        """
        try:
            del self._succ[u][v]
            del self._pred[v][u]
        except KeyError as err:
            raise NetworkXError(f"The edge {u}-{v} not in graph.") from err
        nx._clear_cache(self)

    def remove_edges_from(self, ebunch):
        """Remove all edges specified in ebunch.

        Parameters
        ----------
        ebunch: list or container of edge tuples
            Each edge given in the list or container will be removed
            from the graph. The edges can be:

                - 2-tuples (u, v) edge between u and v.
                - 3-tuples (u, v, k) where k is ignored.

        See Also
        --------
        remove_edge : remove a single edge

        Notes
        -----
        Will fail silently if an edge in ebunch is not in the graph.

        Examples
        --------
        >>> G = nx.path_graph(4)  # or DiGraph, MultiGraph, MultiDiGraph, etc
        >>> ebunch = [(1, 2), (2, 3)]
        >>> G.remove_edges_from(ebunch)
        """
        for e in ebunch:
            u, v = e[:2]  # ignore edge data
            if u in self._succ and v in self._succ[u]:
                del self._succ[u][v]
                del self._pred[v][u]
        nx._clear_cache(self)

    def has_successor(self, u, v):
        """Returns True if node u has successor v.

        This is true if graph has the edge u->v.
        """
        return u in self._succ and v in self._succ[u]

    def has_predecessor(self, u, v):
        """Returns True if node u has predecessor v.

        This is true if graph has the edge u<-v.
        """
        return u in self._pred and v in self._pred[u]

    def successors(self, n):
        """Returns an iterator over successor nodes of n.

        A successor of n is a node m such that there exists a directed
        edge from n to m.

        Parameters
        ----------
        n : node
           A node in the graph

        Raises
        ------
        NetworkXError
           If n is not in the graph.

        See Also
        --------
        predecessors

        Notes
        -----
        neighbors() and successors() are the same.
        """
        try:
            return iter(self._succ[n])
        except KeyError as err:
            raise NetworkXError(f"The node {n} is not in the digraph.") from err

    # digraph definitions
    neighbors = successors

    def predecessors(self, n):
        """Returns an iterator over predecessor nodes of n.

        A predecessor of n is a node m such that there exists a directed
        edge from m to n.

        Parameters
        ----------
        n : node
           A node in the graph

        Raises
        ------
        NetworkXError
           If n is not in the graph.

        See Also
        --------
        successors
        """
        try:
            return iter(self._pred[n])
        except KeyError as err:
            raise NetworkXError(f"The node {n} is not in the digraph.") from err

    @cached_property
    def edges(self):
        """An OutEdgeView of the DiGraph as G.edges or G.edges().

        edges(self, nbunch=None, data=False, default=None)

        The OutEdgeView provides set-like operations on the edge-tuples
        as well as edge attribute lookup. When called, it also provides
        an EdgeDataView object which allows control of access to edge
        attributes (but does not provide set-like operations).
        Hence, `G.edges[u, v]['color']` provides the value of the color
        attribute for edge `(u, v)` while
        `for (u, v, c) in G.edges.data('color', default='red'):`
        iterates through all the edges yielding the color attribute
        with default `'red'` if no color attribute exists.

        Parameters
        ----------
        nbunch : single node, container, or all nodes (default= all nodes)
            The view will only report edges from these nodes.
        data : string or bool, optional (default=False)
            The edge attribute returned in 3-tuple (u, v, ddict[data]).
            If True, return edge attribute dict in 3-tuple (u, v, ddict).
            If False, return 2-tuple (u, v).
        default : value, optional (default=None)
            Value used for edges that don't have the requested attribute.
            Only relevant if data is not True or False.

        Returns
        -------
        edges : OutEdgeView
            A view of edge attributes, usually it iterates over (u, v)
            or (u, v, d) tuples of edges, but can also be used for
            attribute lookup as `edges[u, v]['foo']`.

        See Also
        --------
        in_edges, out_edges

        Notes
        -----
        Nodes in nbunch that are not in the graph will be (quietly) ignored.
        For directed graphs this returns the out-edges.

        Examples
        --------
        >>> G = nx.DiGraph()  # or MultiDiGraph, etc
        >>> nx.add_path(G, [0, 1, 2])
        >>> G.add_edge(2, 3, weight=5)
        >>> [e for e in G.edges]
        [(0, 1), (1, 2), (2, 3)]
        >>> G.edges.data()  # default data is {} (empty dict)
        OutEdgeDataView([(0, 1, {}), (1, 2, {}), (2, 3, {'weight': 5})])
        >>> G.edges.data("weight", default=1)
        OutEdgeDataView([(0, 1, 1), (1, 2, 1), (2, 3, 5)])
        >>> G.edges([0, 2])  # only edges originating from these nodes
        OutEdgeDataView([(0, 1), (2, 3)])
        >>> G.edges(0)  # only edges from node 0
        OutEdgeDataView([(0, 1)])

        """
        return OutEdgeView(self)

    # alias out_edges to edges
    @cached_property
    def out_edges(self):
        return OutEdgeView(self)

    out_edges.__doc__ = edges.__doc__

    @cached_property
    def in_edges(self):
        """A view of the in edges of the graph as G.in_edges or G.in_edges().

        in_edges(self, nbunch=None, data=False, default=None):

        Parameters
        ----------
        nbunch : single node, container, or all nodes (default= all nodes)
            The view will only report edges incident to these nodes.
        data : string or bool, optional (default=False)
            The edge attribute returned in 3-tuple (u, v, ddict[data]).
            If True, return edge attribute dict in 3-tuple (u, v, ddict).
            If False, return 2-tuple (u, v).
        default : value, optional (default=None)
            Value used for edges that don't have the requested attribute.
            Only relevant if data is not True or False.

        Returns
        -------
        in_edges : InEdgeView or InEdgeDataView
            A view of edge attributes, usually it iterates over (u, v)
            or (u, v, d) tuples of edges, but can also be used for
            attribute lookup as `edges[u, v]['foo']`.

        Examples
        --------
        >>> G = nx.DiGraph()
        >>> G.add_edge(1, 2, color="blue")
        >>> G.in_edges()
        InEdgeView([(1, 2)])
        >>> G.in_edges(nbunch=2)
        InEdgeDataView([(1, 2)])

        See Also
        --------
        edges
        """
        return InEdgeView(self)

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
        DiDegreeView or int
            If multiple nodes are requested (the default), returns a `DiDegreeView`
            mapping nodes to their degree.
            If a single node is requested, returns the degree of the node as an integer.

        See Also
        --------
        in_degree, out_degree

        Examples
        --------
        >>> G = nx.DiGraph()  # or MultiDiGraph
        >>> nx.add_path(G, [0, 1, 2, 3])
        >>> G.degree(0)  # node 0 with degree 1
        1
        >>> list(G.degree([0, 1, 2]))
        [(0, 1), (1, 2), (2, 2)]

        """
        return DiDegreeView(self)

    @cached_property
    def in_degree(self):
        """An InDegreeView for (node, in_degree) or in_degree for single node.

        The node in_degree is the number of edges pointing to the node.
        The weighted node degree is the sum of the edge weights for
        edges incident to that node.

        This object provides an iteration over (node, in_degree) as well as
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
        If a single node is requested
        deg : int
            In-degree of the node

        OR if multiple nodes are requested
        nd_iter : iterator
            The iterator returns two-tuples of (node, in-degree).

        See Also
        --------
        degree, out_degree

        Examples
        --------
        >>> G = nx.DiGraph()
        >>> nx.add_path(G, [0, 1, 2, 3])
        >>> G.in_degree(0)  # node 0 with degree 0
        0
        >>> list(G.in_degree([0, 1, 2]))
        [(0, 0), (1, 1), (2, 1)]

        """
        return InDegreeView(self)

    @cached_property
    def out_degree(self):
        """An OutDegreeView for (node, out_degree)

        The node out_degree is the number of edges pointing out of the node.
        The weighted node degree is the sum of the edge weights for
        edges incident to that node.

        This object provides an iterator over (node, out_degree) as well as
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
        If a single node is requested
        deg : int
            Out-degree of the node

        OR if multiple nodes are requested
        nd_iter : iterator
            The iterator returns two-tuples of (node, out-degree).

        See Also
        --------
        degree, in_degree

        Examples
        --------
        >>> G = nx.DiGraph()
        >>> nx.add_path(G, [0, 1, 2, 3])
        >>> G.out_degree(0)  # node 0 with degree 1
        1
        >>> list(G.out_degree([0, 1, 2]))
        [(0, 1), (1, 1), (2, 1)]

        """
        return OutDegreeView(self)

    def clear(self):
        """Remove all nodes and edges from the graph.

        This also removes the name, and all graph, node, and edge attributes.

        Examples
        --------
        >>> G = nx.path_graph(4)  # or DiGraph, MultiGraph, MultiDiGraph, etc
        >>> G.clear()
        >>> list(G.nodes)
        []
        >>> list(G.edges)
        []

        """
        self._succ.clear()
        self._pred.clear()
        self._node.clear()
        self.graph.clear()
        nx._clear_cache(self)

    def clear_edges(self):
        """Remove all edges from the graph without altering nodes.

        Examples
        --------
        >>> G = nx.path_graph(4)  # or DiGraph, MultiGraph, MultiDiGraph, etc
        >>> G.clear_edges()
        >>> list(G.nodes)
        [0, 1, 2, 3]
        >>> list(G.edges)
        []

        """
        for predecessor_dict in self._pred.values():
            predecessor_dict.clear()
        for successor_dict in self._succ.values():
            successor_dict.clear()
        nx._clear_cache(self)

    def is_multigraph(self):
        """Returns True if graph is a multigraph, False otherwise."""
        return False

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
        G : Graph
            An undirected graph with the same name and nodes and
            with edge (u, v, data) if either (u, v, data) or (v, u, data)
            is in the digraph.  If both edges exist in digraph and
            their edge data is different, only one edge is created
            with an arbitrary choice of which edge data to use.
            You must check and correct for this manually if desired.

        See Also
        --------
        Graph, copy, add_edge, add_edges_from

        Notes
        -----
        If edges in both directions (u, v) and (v, u) exist in the
        graph, attributes for the new undirected edge will be a combination of
        the attributes of the directed edges.  The edge data is updated
        in the (arbitrary) order that the edges are encountered.  For
        more customized control of the edge attributes use add_edge().

        This returns a "deepcopy" of the edge, node, and
        graph attributes which attempts to completely copy
        all of the data and references.

        This is in contrast to the similar G=DiGraph(D) which returns a
        shallow copy of the data.

        See the Python copy module for more information on shallow
        and deep copies, https://docs.python.org/3/library/copy.html.

        Warning: If you have subclassed DiGraph to use dict-like objects
        in the data structure, those changes do not transfer to the
        Graph created by this method.

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
                (u, v, deepcopy(d))
                for u, nbrs in self._adj.items()
                for v, d in nbrs.items()
                if v in self._pred[u]
            )
        else:
            G.add_edges_from(
                (u, v, deepcopy(d))
                for u, nbrs in self._adj.items()
                for v, d in nbrs.items()
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
            H.add_nodes_from((n, deepcopy(d)) for n, d in self.nodes.items())
            H.add_edges_from((v, u, deepcopy(d)) for u, v, d in self.edges(data=True))
            return H
        return nx.reverse_view(self)
