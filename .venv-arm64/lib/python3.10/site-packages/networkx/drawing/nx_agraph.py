"""
***************
Graphviz AGraph
***************

Interface to pygraphviz AGraph class.

Examples
--------
>>> G = nx.complete_graph(5)
>>> A = nx.nx_agraph.to_agraph(G)
>>> H = nx.nx_agraph.from_agraph(A)

See Also
--------
 - Pygraphviz: http://pygraphviz.github.io/
 - Graphviz:      https://www.graphviz.org
 - DOT Language:  http://www.graphviz.org/doc/info/lang.html
"""

import os
import tempfile

import networkx as nx

__all__ = [
    "from_agraph",
    "to_agraph",
    "write_dot",
    "read_dot",
    "graphviz_layout",
    "pygraphviz_layout",
    "view_pygraphviz",
]


@nx._dispatchable(graphs=None, returns_graph=True)
def from_agraph(A, create_using=None):
    """Returns a NetworkX Graph or DiGraph from a PyGraphviz graph.

    Parameters
    ----------
    A : PyGraphviz AGraph
      A graph created with PyGraphviz

    create_using : NetworkX graph constructor, optional (default=None)
       Graph type to create. If graph instance, then cleared before populated.
       If `None`, then the appropriate Graph type is inferred from `A`.

    Examples
    --------
    >>> K5 = nx.complete_graph(5)
    >>> A = nx.nx_agraph.to_agraph(K5)
    >>> G = nx.nx_agraph.from_agraph(A)

    Notes
    -----
    The Graph G will have a dictionary G.graph_attr containing
    the default graphviz attributes for graphs, nodes and edges.

    Default node attributes will be in the dictionary G.node_attr
    which is keyed by node.

    Edge attributes will be returned as edge data in G.  With
    edge_attr=False the edge data will be the Graphviz edge weight
    attribute or the value 1 if no edge weight attribute is found.

    """
    if create_using is None:
        if A.is_directed():
            if A.is_strict():
                create_using = nx.DiGraph
            else:
                create_using = nx.MultiDiGraph
        else:
            if A.is_strict():
                create_using = nx.Graph
            else:
                create_using = nx.MultiGraph

    # assign defaults
    N = nx.empty_graph(0, create_using)
    if A.name is not None:
        N.name = A.name

    # add graph attributes
    N.graph.update(A.graph_attr)

    # add nodes, attributes to N.node_attr
    for n in A.nodes():
        str_attr = {str(k): v for k, v in n.attr.items()}
        N.add_node(str(n), **str_attr)

    # add edges, assign edge data as dictionary of attributes
    for e in A.edges():
        u, v = str(e[0]), str(e[1])
        attr = dict(e.attr)
        str_attr = {str(k): v for k, v in attr.items()}
        if not N.is_multigraph():
            if e.name is not None:
                str_attr["key"] = e.name
            N.add_edge(u, v, **str_attr)
        else:
            N.add_edge(u, v, key=e.name, **str_attr)

    # add default attributes for graph, nodes, and edges
    # hang them on N.graph_attr
    N.graph["graph"] = dict(A.graph_attr)
    N.graph["node"] = dict(A.node_attr)
    N.graph["edge"] = dict(A.edge_attr)
    return N


def to_agraph(N):
    """Returns a pygraphviz graph from a NetworkX graph N.

    Parameters
    ----------
    N : NetworkX graph
      A graph created with NetworkX

    Examples
    --------
    >>> K5 = nx.complete_graph(5)
    >>> A = nx.nx_agraph.to_agraph(K5)

    Notes
    -----
    If N has an dict N.graph_attr an attempt will be made first
    to copy properties attached to the graph (see from_agraph)
    and then updated with the calling arguments if any.

    """
    try:
        import pygraphviz
    except ImportError as err:
        raise ImportError("requires pygraphviz http://pygraphviz.github.io/") from err
    directed = N.is_directed()
    strict = nx.number_of_selfloops(N) == 0 and not N.is_multigraph()

    A = pygraphviz.AGraph(name=N.name, strict=strict, directed=directed)

    # default graph attributes
    A.graph_attr.update(N.graph.get("graph", {}))
    A.node_attr.update(N.graph.get("node", {}))
    A.edge_attr.update(N.graph.get("edge", {}))

    A.graph_attr.update(
        (k, v) for k, v in N.graph.items() if k not in ("graph", "node", "edge")
    )

    # add nodes
    for n, nodedata in N.nodes(data=True):
        A.add_node(n)
        # Add node data
        a = A.get_node(n)
        for key, val in nodedata.items():
            if key == "pos":
                a.attr["pos"] = f"{val[0]},{val[1]}!"
            else:
                a.attr[key] = str(val)

    # loop over edges
    if N.is_multigraph():
        for u, v, key, edgedata in N.edges(data=True, keys=True):
            str_edgedata = {k: str(v) for k, v in edgedata.items() if k != "key"}
            A.add_edge(u, v, key=str(key))
            # Add edge data
            a = A.get_edge(u, v)
            a.attr.update(str_edgedata)

    else:
        for u, v, edgedata in N.edges(data=True):
            str_edgedata = {k: str(v) for k, v in edgedata.items()}
            A.add_edge(u, v)
            # Add edge data
            a = A.get_edge(u, v)
            a.attr.update(str_edgedata)

    return A


def write_dot(G, path):
    """Write NetworkX graph G to Graphviz dot format on path.

    Parameters
    ----------
    G : graph
       A networkx graph
    path : filename
       Filename or file handle to write

    Notes
    -----
    To use a specific graph layout, call ``A.layout`` prior to `write_dot`.
    Note that some graphviz layouts are not guaranteed to be deterministic,
    see https://gitlab.com/graphviz/graphviz/-/issues/1767 for more info.
    """
    A = to_agraph(G)
    A.write(path)
    A.clear()
    return


@nx._dispatchable(name="agraph_read_dot", graphs=None, returns_graph=True)
def read_dot(path):
    """Returns a NetworkX graph from a dot file on path.

    Parameters
    ----------
    path : file or string
       File name or file handle to read.
    """
    try:
        import pygraphviz
    except ImportError as err:
        raise ImportError(
            "read_dot() requires pygraphviz http://pygraphviz.github.io/"
        ) from err
    A = pygraphviz.AGraph(file=path)
    gr = from_agraph(A)
    A.clear()
    return gr


def graphviz_layout(G, prog="neato", root=None, args=""):
    """Create node positions for G using Graphviz.

    Parameters
    ----------
    G : NetworkX graph
      A graph created with NetworkX
    prog : string
      Name of Graphviz layout program
    root : string, optional
      Root node for twopi layout
    args : string, optional
      Extra arguments to Graphviz layout program

    Returns
    -------
    Dictionary of x, y, positions keyed by node.

    Examples
    --------
    >>> G = nx.petersen_graph()
    >>> pos = nx.nx_agraph.graphviz_layout(G)
    >>> pos = nx.nx_agraph.graphviz_layout(G, prog="dot")

    Notes
    -----
    This is a wrapper for pygraphviz_layout.

    Note that some graphviz layouts are not guaranteed to be deterministic,
    see https://gitlab.com/graphviz/graphviz/-/issues/1767 for more info.
    """
    return pygraphviz_layout(G, prog=prog, root=root, args=args)


def pygraphviz_layout(G, prog="neato", root=None, args=""):
    """Create node positions for G using Graphviz.

    Parameters
    ----------
    G : NetworkX graph
      A graph created with NetworkX
    prog : string
      Name of Graphviz layout program
    root : string, optional
      Root node for twopi layout
    args : string, optional
      Extra arguments to Graphviz layout program

    Returns
    -------
    node_pos : dict
      Dictionary of x, y, positions keyed by node.

    Examples
    --------
    >>> G = nx.petersen_graph()
    >>> pos = nx.nx_agraph.graphviz_layout(G)
    >>> pos = nx.nx_agraph.graphviz_layout(G, prog="dot")

    Notes
    -----
    If you use complex node objects, they may have the same string
    representation and GraphViz could treat them as the same node.
    The layout may assign both nodes a single location. See Issue #1568
    If this occurs in your case, consider relabeling the nodes just
    for the layout computation using something similar to::

        >>> H = nx.convert_node_labels_to_integers(G, label_attribute="node_label")
        >>> H_layout = nx.nx_agraph.pygraphviz_layout(G, prog="dot")
        >>> G_layout = {H.nodes[n]["node_label"]: p for n, p in H_layout.items()}

    Note that some graphviz layouts are not guaranteed to be deterministic,
    see https://gitlab.com/graphviz/graphviz/-/issues/1767 for more info.
    """
    try:
        import pygraphviz
    except ImportError as err:
        raise ImportError("requires pygraphviz http://pygraphviz.github.io/") from err
    if root is not None:
        args += f"-Groot={root}"
    A = to_agraph(G)
    A.layout(prog=prog, args=args)
    node_pos = {}
    for n in G:
        node = pygraphviz.Node(A, n)
        try:
            xs = node.attr["pos"].split(",")
            node_pos[n] = tuple(float(x) for x in xs)
        except:
            print("no position for node", n)
            node_pos[n] = (0.0, 0.0)
    return node_pos


@nx.utils.open_file(5, "w+b")
def view_pygraphviz(
    G, edgelabel=None, prog="dot", args="", suffix="", path=None, show=True
):
    """Views the graph G using the specified layout algorithm.

    Parameters
    ----------
    G : NetworkX graph
        The machine to draw.
    edgelabel : str, callable, None
        If a string, then it specifies the edge attribute to be displayed
        on the edge labels. If a callable, then it is called for each
        edge and it should return the string to be displayed on the edges.
        The function signature of `edgelabel` should be edgelabel(data),
        where `data` is the edge attribute dictionary.
    prog : string
        Name of Graphviz layout program.
    args : str
        Additional arguments to pass to the Graphviz layout program.
    suffix : str
        If `filename` is None, we save to a temporary file.  The value of
        `suffix` will appear at the tail end of the temporary filename.
    path : str, None
        The filename used to save the image.  If None, save to a temporary
        file.  File formats are the same as those from pygraphviz.agraph.draw.
    show : bool, default = True
        Whether to display the graph with :mod:`PIL.Image.show`,
        default is `True`. If `False`, the rendered graph is still available
        at `path`.

    Returns
    -------
    path : str
        The filename of the generated image.
    A : PyGraphviz graph
        The PyGraphviz graph instance used to generate the image.

    Notes
    -----
    If this function is called in succession too quickly, sometimes the
    image is not displayed. So you might consider time.sleep(.5) between
    calls if you experience problems.

    Note that some graphviz layouts are not guaranteed to be deterministic,
    see https://gitlab.com/graphviz/graphviz/-/issues/1767 for more info.

    """
    if not len(G):
        raise nx.NetworkXException("An empty graph cannot be drawn.")

    # If we are providing default values for graphviz, these must be set
    # before any nodes or edges are added to the PyGraphviz graph object.
    # The reason for this is that default values only affect incoming objects.
    # If you change the default values after the objects have been added,
    # then they inherit no value and are set only if explicitly set.

    # to_agraph() uses these values.
    attrs = ["edge", "node", "graph"]
    for attr in attrs:
        if attr not in G.graph:
            G.graph[attr] = {}

    # These are the default values.
    edge_attrs = {"fontsize": "10"}
    node_attrs = {
        "style": "filled",
        "fillcolor": "#0000FF40",
        "height": "0.75",
        "width": "0.75",
        "shape": "circle",
    }
    graph_attrs = {}

    def update_attrs(which, attrs):
        # Update graph attributes. Return list of those which were added.
        added = []
        for k, v in attrs.items():
            if k not in G.graph[which]:
                G.graph[which][k] = v
                added.append(k)

    def clean_attrs(which, added):
        # Remove added attributes
        for attr in added:
            del G.graph[which][attr]
        if not G.graph[which]:
            del G.graph[which]

    # Update all default values
    update_attrs("edge", edge_attrs)
    update_attrs("node", node_attrs)
    update_attrs("graph", graph_attrs)

    # Convert to agraph, so we inherit default values
    A = to_agraph(G)

    # Remove the default values we added to the original graph.
    clean_attrs("edge", edge_attrs)
    clean_attrs("node", node_attrs)
    clean_attrs("graph", graph_attrs)

    # If the user passed in an edgelabel, we update the labels for all edges.
    if edgelabel is not None:
        if not callable(edgelabel):

            def func(data):
                return "".join(["  ", str(data[edgelabel]), "  "])

        else:
            func = edgelabel

        # update all the edge labels
        if G.is_multigraph():
            for u, v, key, data in G.edges(keys=True, data=True):
                # PyGraphviz doesn't convert the key to a string. See #339
                edge = A.get_edge(u, v, str(key))
                edge.attr["label"] = str(func(data))
        else:
            for u, v, data in G.edges(data=True):
                edge = A.get_edge(u, v)
                edge.attr["label"] = str(func(data))

    if path is None:
        ext = "png"
        if suffix:
            suffix = f"_{suffix}.{ext}"
        else:
            suffix = f".{ext}"
        path = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    else:
        # Assume the decorator worked and it is a file-object.
        pass

    # Write graph to file
    A.draw(path=path, format=None, prog=prog, args=args)
    path.close()

    # Show graph in a new window (depends on platform configuration)
    if show:
        from PIL import Image

        Image.open(path.name).show()

    return path.name, A
