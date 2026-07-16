"""
*******
GraphML
*******
Read and write graphs in GraphML format.

.. warning::

    This parser uses the standard xml library present in Python, which is
    insecure - see :external+python:mod:`xml` for additional information.
    Only parse GraphML files you trust.

This implementation does not support mixed graphs (directed and unidirected
edges together), hyperedges, nested graphs, or ports.

"GraphML is a comprehensive and easy-to-use file format for graphs. It
consists of a language core to describe the structural properties of a
graph and a flexible extension mechanism to add application-specific
data. Its main features include support of

    * directed, undirected, and mixed graphs,
    * hypergraphs,
    * hierarchical graphs,
    * graphical representations,
    * references to external data,
    * application-specific attribute data, and
    * light-weight parsers.

Unlike many other file formats for graphs, GraphML does not use a
custom syntax. Instead, it is based on XML and hence ideally suited as
a common denominator for all kinds of services generating, archiving,
or processing graphs."

http://graphml.graphdrawing.org/

Format
------
GraphML is an XML format.  See
http://graphml.graphdrawing.org/specification.html for the specification and
http://graphml.graphdrawing.org/primer/graphml-primer.html
for examples.
"""

import warnings
from collections import defaultdict

import networkx as nx
from networkx.utils import open_file

__all__ = [
    "write_graphml",
    "read_graphml",
    "generate_graphml",
    "write_graphml_xml",
    "write_graphml_lxml",
    "parse_graphml",
    "GraphMLWriter",
    "GraphMLReader",
]


@open_file(1, mode="wb")
def write_graphml_xml(
    G,
    path,
    encoding="utf-8",
    prettyprint=True,
    infer_numeric_types=False,
    named_key_ids=False,
    edge_id_from_attribute=None,
):
    """Write G in GraphML XML format to path

    Parameters
    ----------
    G : graph
       A networkx graph
    path : file or string
       File or filename to write.
       Filenames ending in .gz or .bz2 will be compressed.
    encoding : string (optional)
       Encoding for text data.
    prettyprint : bool (optional)
       If True use line breaks and indenting in output XML.
    infer_numeric_types : boolean
       Determine if numeric types should be generalized.
       For example, if edges have both int and float 'weight' attributes,
       we infer in GraphML that both are floats.
    named_key_ids : bool (optional)
       If True use attr.name as value for key elements' id attribute.
    edge_id_from_attribute : dict key (optional)
        If provided, the graphml edge id is set by looking up the corresponding
        edge data attribute keyed by this parameter. If `None` or the key does not exist in edge data,
        the edge id is set by the edge key if `G` is a MultiGraph, else the edge id is left unset.

    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> nx.write_graphml(G, "test.graphml")

    Notes
    -----
    This implementation does not support mixed graphs (directed
    and unidirected edges together) hyperedges, nested graphs, or ports.
    """
    writer = GraphMLWriter(
        encoding=encoding,
        prettyprint=prettyprint,
        infer_numeric_types=infer_numeric_types,
        named_key_ids=named_key_ids,
        edge_id_from_attribute=edge_id_from_attribute,
    )
    writer.add_graph_element(G)
    writer.dump(path)


@open_file(1, mode="wb")
def write_graphml_lxml(
    G,
    path,
    encoding="utf-8",
    prettyprint=True,
    infer_numeric_types=False,
    named_key_ids=False,
    edge_id_from_attribute=None,
):
    """Write G in GraphML XML format to path

    This function uses the LXML framework and should be faster than
    the version using the xml library.

    Parameters
    ----------
    G : graph
       A networkx graph
    path : file or string
       File or filename to write.
       Filenames ending in .gz or .bz2 will be compressed.
    encoding : string (optional)
       Encoding for text data.
    prettyprint : bool (optional)
       If True use line breaks and indenting in output XML.
    infer_numeric_types : boolean
       Determine if numeric types should be generalized.
       For example, if edges have both int and float 'weight' attributes,
       we infer in GraphML that both are floats.
    named_key_ids : bool (optional)
       If True use attr.name as value for key elements' id attribute.
    edge_id_from_attribute : dict key (optional)
        If provided, the graphml edge id is set by looking up the corresponding
        edge data attribute keyed by this parameter. If `None` or the key does not exist in edge data,
        the edge id is set by the edge key if `G` is a MultiGraph, else the edge id is left unset.

    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> nx.write_graphml_lxml(G, "fourpath.graphml")

    Notes
    -----
    This implementation does not support mixed graphs (directed
    and unidirected edges together) hyperedges, nested graphs, or ports.
    """
    try:
        import lxml.etree as lxmletree
    except ImportError:
        return write_graphml_xml(
            G,
            path,
            encoding,
            prettyprint,
            infer_numeric_types,
            named_key_ids,
            edge_id_from_attribute,
        )

    writer = GraphMLWriterLxml(
        path,
        graph=G,
        encoding=encoding,
        prettyprint=prettyprint,
        infer_numeric_types=infer_numeric_types,
        named_key_ids=named_key_ids,
        edge_id_from_attribute=edge_id_from_attribute,
    )
    writer.dump()


def generate_graphml(
    G,
    encoding="utf-8",
    prettyprint=True,
    named_key_ids=False,
    edge_id_from_attribute=None,
):
    """Generate GraphML lines for G

    Parameters
    ----------
    G : graph
       A networkx graph
    encoding : string (optional)
       Encoding for text data.
    prettyprint : bool (optional)
       If True use line breaks and indenting in output XML.
    named_key_ids : bool (optional)
       If True use attr.name as value for key elements' id attribute.
    edge_id_from_attribute : dict key (optional)
        If provided, the graphml edge id is set by looking up the corresponding
        edge data attribute keyed by this parameter. If `None` or the key does not exist in edge data,
        the edge id is set by the edge key if `G` is a MultiGraph, else the edge id is left unset.

    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> linefeed = chr(10)  # linefeed = \n
    >>> s = linefeed.join(nx.generate_graphml(G))
    >>> for line in nx.generate_graphml(G):  # doctest: +SKIP
    ...     print(line)

    Notes
    -----
    This implementation does not support mixed graphs (directed and unidirected
    edges together) hyperedges, nested graphs, or ports.
    """
    writer = GraphMLWriter(
        encoding=encoding,
        prettyprint=prettyprint,
        named_key_ids=named_key_ids,
        edge_id_from_attribute=edge_id_from_attribute,
    )
    writer.add_graph_element(G)
    yield from str(writer).splitlines()


@open_file(0, mode="rb")
@nx._dispatchable(graphs=None, returns_graph=True)
def read_graphml(path, node_type=str, edge_key_type=int, force_multigraph=False):
    """Read graph in GraphML format from path.

    Parameters
    ----------
    path : file or string
       File or filename to write.
       Filenames ending in .gz or .bz2 will be compressed.

    node_type: Python type (default: str)
       Convert node ids to this type

    edge_key_type: Python type (default: int)
       Convert graphml edge ids to this type. Multigraphs use id as edge key.
       Non-multigraphs add to edge attribute dict with name "id".

    force_multigraph : bool (default: False)
       If True, return a multigraph with edge keys. If False (the default)
       return a multigraph when multiedges are in the graph.

    Returns
    -------
    graph: NetworkX graph
        If parallel edges are present or `force_multigraph=True` then
        a MultiGraph or MultiDiGraph is returned. Otherwise a Graph/DiGraph.
        The returned graph is directed if the file indicates it should be.

    Notes
    -----
    Default node and edge attributes are not propagated to each node and edge.
    They can be obtained from `G.graph` and applied to node and edge attributes
    if desired using something like this:

    >>> default_color = G.graph["node_default"]["color"]  # doctest: +SKIP
    >>> for node, data in G.nodes(data=True):  # doctest: +SKIP
    ...     if "color" not in data:
    ...         data["color"] = default_color
    >>> default_color = G.graph["edge_default"]["color"]  # doctest: +SKIP
    >>> for u, v, data in G.edges(data=True):  # doctest: +SKIP
    ...     if "color" not in data:
    ...         data["color"] = default_color

    This implementation does not support mixed graphs (directed and unidirected
    edges together), hypergraphs, nested graphs, or ports.

    For multigraphs the GraphML edge "id" will be used as the edge
    key.  If not specified then they "key" attribute will be used.  If
    there is no "key" attribute a default NetworkX multigraph edge key
    will be provided.

    Files with the yEd "yfiles" extension can be read. The type of the node's
    shape is preserved in the `shape_type` node attribute.

    yEd compressed files ("file.graphmlz" extension) can be read by renaming
    the file to "file.graphml.gz".

    """
    reader = GraphMLReader(node_type, edge_key_type, force_multigraph)
    # need to check for multiple graphs
    glist = list(reader(path=path))
    if len(glist) == 0:
        # If no graph comes back, try looking for an incomplete header
        header = b'<graphml xmlns="http://graphml.graphdrawing.org/xmlns">'
        path.seek(0)
        old_bytes = path.read()
        new_bytes = old_bytes.replace(b"<graphml>", header)
        glist = list(reader(string=new_bytes))
        if len(glist) == 0:
            raise nx.NetworkXError("file not successfully read as graphml")
    return glist[0]


@nx._dispatchable(graphs=None, returns_graph=True)
def parse_graphml(
    graphml_string, node_type=str, edge_key_type=int, force_multigraph=False
):
    """Read graph in GraphML format from string.

    Parameters
    ----------
    graphml_string : string
       String containing graphml information
       (e.g., contents of a graphml file).

    node_type: Python type (default: str)
       Convert node ids to this type

    edge_key_type: Python type (default: int)
       Convert graphml edge ids to this type. Multigraphs use id as edge key.
       Non-multigraphs add to edge attribute dict with name "id".

    force_multigraph : bool (default: False)
       If True, return a multigraph with edge keys. If False (the default)
       return a multigraph when multiedges are in the graph.


    Returns
    -------
    graph: NetworkX graph
        If no parallel edges are found a Graph or DiGraph is returned.
        Otherwise a MultiGraph or MultiDiGraph is returned.

    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> linefeed = chr(10)  # linefeed = \n
    >>> s = linefeed.join(nx.generate_graphml(G))
    >>> H = nx.parse_graphml(s)

    Notes
    -----
    Default node and edge attributes are not propagated to each node and edge.
    They can be obtained from `G.graph` and applied to node and edge attributes
    if desired using something like this:

    >>> default_color = G.graph["node_default"]["color"]  # doctest: +SKIP
    >>> for node, data in G.nodes(data=True):  # doctest: +SKIP
    ...     if "color" not in data:
    ...         data["color"] = default_color
    >>> default_color = G.graph["edge_default"]["color"]  # doctest: +SKIP
    >>> for u, v, data in G.edges(data=True):  # doctest: +SKIP
    ...     if "color" not in data:
    ...         data["color"] = default_color

    This implementation does not support mixed graphs (directed and unidirected
    edges together), hypergraphs, nested graphs, or ports.

    For multigraphs the GraphML edge "id" will be used as the edge
    key.  If not specified then they "key" attribute will be used.  If
    there is no "key" attribute a default NetworkX multigraph edge key
    will be provided.

    """
    reader = GraphMLReader(node_type, edge_key_type, force_multigraph)
    # need to check for multiple graphs
    glist = list(reader(string=graphml_string))
    if len(glist) == 0:
        # If no graph comes back, try looking for an incomplete header
        header = '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">'
        new_string = graphml_string.replace("<graphml>", header)
        glist = list(reader(string=new_string))
        if len(glist) == 0:
            raise nx.NetworkXError("file not successfully read as graphml")
    return glist[0]


class GraphML:
    NS_GRAPHML = "http://graphml.graphdrawing.org/xmlns"
    NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
    # xmlns:y="http://www.yworks.com/xml/graphml"
    NS_Y = "http://www.yworks.com/xml/graphml"
    SCHEMALOCATION = " ".join(
        [
            "http://graphml.graphdrawing.org/xmlns",
            "http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd",
        ]
    )

    def construct_types(self):
        types = [
            (int, "integer"),  # for Gephi GraphML bug
            (str, "yfiles"),
            (str, "string"),
            (int, "int"),
            (int, "long"),
            (float, "float"),
            (float, "double"),
            (bool, "boolean"),
        ]

        # These additions to types allow writing numpy types
        try:
            import numpy as np
        except:
            pass
        else:
            # prepend so that python types are created upon read (last entry wins)
            types = [
                (np.float64, "float"),
                (np.float32, "float"),
                (np.float16, "float"),
                (np.int_, "int"),
                (np.int8, "int"),
                (np.int16, "int"),
                (np.int32, "int"),
                (np.int64, "int"),
                (np.uint8, "int"),
                (np.uint16, "int"),
                (np.uint32, "int"),
                (np.uint64, "int"),
                (np.int_, "int"),
                (np.intc, "int"),
                (np.intp, "int"),
            ] + types

        self.xml_type = dict(types)
        self.python_type = dict(reversed(a) for a in types)

    # This page says that data types in GraphML follow Java(TM).
    #  http://graphml.graphdrawing.org/primer/graphml-primer.html#AttributesDefinition
    # true and false are the only boolean literals:
    #  http://en.wikibooks.org/wiki/Java_Programming/Literals#Boolean_Literals
    convert_bool = {
        # We use data.lower() in actual use.
        "true": True,
        "false": False,
        # Include integer strings for convenience.
        "0": False,
        0: False,
        "1": True,
        1: True,
    }

    def get_xml_type(self, key):
        """Wrapper around the xml_type dict that raises a more informative
        exception message when a user attempts to use data of a type not
        supported by GraphML."""
        try:
            return self.xml_type[key]
        except KeyError as err:
            raise TypeError(
                f"GraphML does not support type {key} as data values."
            ) from err


class GraphMLWriter(GraphML):
    def __init__(
        self,
        graph=None,
        encoding="utf-8",
        prettyprint=True,
        infer_numeric_types=False,
        named_key_ids=False,
        edge_id_from_attribute=None,
    ):
        self.construct_types()
        from xml.etree.ElementTree import Element

        self.myElement = Element

        self.infer_numeric_types = infer_numeric_types
        self.prettyprint = prettyprint
        self.named_key_ids = named_key_ids
        self.edge_id_from_attribute = edge_id_from_attribute
        self.encoding = encoding
        self.xml = self.myElement(
            "graphml",
            {
                "xmlns": self.NS_GRAPHML,
                "xmlns:xsi": self.NS_XSI,
                "xsi:schemaLocation": self.SCHEMALOCATION,
            },
        )
        self.keys = {}
        self.attributes = defaultdict(list)
        self.attribute_types = defaultdict(set)

        if graph is not None:
            self.add_graph_element(graph)

    def __str__(self):
        from xml.etree.ElementTree import tostring

        if self.prettyprint:
            self.indent(self.xml)
        s = tostring(self.xml).decode(self.encoding)
        return s

    def attr_type(self, name, scope, value):
        """Infer the attribute type of data named name. Currently this only
        supports inference of numeric types.

        If self.infer_numeric_types is false, type is used. Otherwise, pick the
        most general of types found across all values with name and scope. This
        means edges with data named 'weight' are treated separately from nodes
        with data named 'weight'.
        """
        if self.infer_numeric_types:
            types = self.attribute_types[(name, scope)]

            if len(types) > 1:
                types = {self.get_xml_type(t) for t in types}
                if "string" in types:
                    return str
                elif "float" in types or "double" in types:
                    return float
                else:
                    return int
            else:
                return list(types)[0]
        else:
            return type(value)

    def get_key(self, name, attr_type, scope, default):
        keys_key = (name, attr_type, scope)
        try:
            return self.keys[keys_key]
        except KeyError:
            if self.named_key_ids:
                new_id = name
            else:
                new_id = f"d{len(list(self.keys))}"

            self.keys[keys_key] = new_id
            key_kwargs = {
                "id": new_id,
                "for": scope,
                "attr.name": name,
                "attr.type": attr_type,
            }
            key_element = self.myElement("key", **key_kwargs)
            # add subelement for data default value if present
            if default is not None:
                default_element = self.myElement("default")
                default_element.text = str(default)
                key_element.append(default_element)
            self.xml.insert(0, key_element)
        return new_id

    def add_data(self, name, element_type, value, scope="all", default=None):
        """
        Make a data element for an edge or a node. Keep a log of the
        type in the keys table.
        """
        if element_type not in self.xml_type:
            raise nx.NetworkXError(
                f"GraphML writer does not support {element_type} as data values."
            )
        keyid = self.get_key(name, self.get_xml_type(element_type), scope, default)
        data_element = self.myElement("data", key=keyid)
        data_element.text = str(value)
        return data_element

    def add_attributes(self, scope, xml_obj, data, default):
        """Appends attribute data to edges or nodes, and stores type information
        to be added later. See add_graph_element.
        """
        for k, v in data.items():
            self.attribute_types[(str(k), scope)].add(type(v))
            self.attributes[xml_obj].append([k, v, scope, default.get(k)])

    def add_nodes(self, G, graph_element):
        default = G.graph.get("node_default", {})
        for node, data in G.nodes(data=True):
            node_element = self.myElement("node", id=str(node))
            self.add_attributes("node", node_element, data, default)
            graph_element.append(node_element)

    def add_edges(self, G, graph_element):
        if G.is_multigraph():
            for u, v, key, data in G.edges(data=True, keys=True):
                edge_element = self.myElement(
                    "edge",
                    source=str(u),
                    target=str(v),
                    id=str(data.get(self.edge_id_from_attribute))
                    if self.edge_id_from_attribute
                    and self.edge_id_from_attribute in data
                    else str(key),
                )
                default = G.graph.get("edge_default", {})
                self.add_attributes("edge", edge_element, data, default)
                graph_element.append(edge_element)
        else:
            for u, v, data in G.edges(data=True):
                if self.edge_id_from_attribute and self.edge_id_from_attribute in data:
                    # select attribute to be edge id
                    edge_element = self.myElement(
                        "edge",
                        source=str(u),
                        target=str(v),
                        id=str(data.get(self.edge_id_from_attribute)),
                    )
                else:
                    # default: no edge id
                    edge_element = self.myElement("edge", source=str(u), target=str(v))
                default = G.graph.get("edge_default", {})
                self.add_attributes("edge", edge_element, data, default)
                graph_element.append(edge_element)

    def add_graph_element(self, G):
        """
        Serialize graph G in GraphML to the stream.
        """
        if G.is_directed():
            default_edge_type = "directed"
        else:
            default_edge_type = "undirected"

        graphid = G.graph.pop("id", None)
        if graphid is None:
            graph_element = self.myElement("graph", edgedefault=default_edge_type)
        else:
            graph_element = self.myElement(
                "graph", edgedefault=default_edge_type, id=graphid
            )
        default = {}
        data = {
            k: v
            for (k, v) in G.graph.items()
            if k not in ["node_default", "edge_default"]
        }
        self.add_attributes("graph", graph_element, data, default)
        self.add_nodes(G, graph_element)
        self.add_edges(G, graph_element)

        # self.attributes contains a mapping from XML Objects to a list of
        # data that needs to be added to them.
        # We postpone processing in order to do type inference/generalization.
        # See self.attr_type
        for xml_obj, data in self.attributes.items():
            for k, v, scope, default in data:
                xml_obj.append(
                    self.add_data(
                        str(k), self.attr_type(k, scope, v), str(v), scope, default
                    )
                )
        self.xml.append(graph_element)

    def add_graphs(self, graph_list):
        """Add many graphs to this GraphML document."""
        for G in graph_list:
            self.add_graph_element(G)

    def dump(self, stream):
        from xml.etree.ElementTree import ElementTree

        if self.prettyprint:
            self.indent(self.xml)
        document = ElementTree(self.xml)
        document.write(stream, encoding=self.encoding, xml_declaration=True)

    def indent(self, elem, level=0):
        # in-place prettyprint formatter
        i = "\n" + level * "  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for elem in elem:
                self.indent(elem, level + 1)
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i


class IncrementalElement:
    """Wrapper for _IncrementalWriter providing an Element like interface.

    This wrapper does not intend to be a complete implementation but rather to
    deal with those calls used in GraphMLWriter.
    """

    def __init__(self, xml, prettyprint):
        self.xml = xml
        self.prettyprint = prettyprint

    def append(self, element):
        self.xml.write(element, pretty_print=self.prettyprint)


class GraphMLWriterLxml(GraphMLWriter):
    def __init__(
        self,
        path,
        graph=None,
        encoding="utf-8",
        prettyprint=True,
        infer_numeric_types=False,
        named_key_ids=False,
        edge_id_from_attribute=None,
    ):
        self.construct_types()
        import lxml.etree as lxmletree

        self.myElement = lxmletree.Element

        self._encoding = encoding
        self._prettyprint = prettyprint
        self.named_key_ids = named_key_ids
        self.edge_id_from_attribute = edge_id_from_attribute
        self.infer_numeric_types = infer_numeric_types

        self._xml_base = lxmletree.xmlfile(path, encoding=encoding)
        self._xml = self._xml_base.__enter__()
        self._xml.write_declaration()

        # We need to have a xml variable that support insertion. This call is
        # used for adding the keys to the document.
        # We will store those keys in a plain list, and then after the graph
        # element is closed we will add them to the main graphml element.
        self.xml = []
        self._keys = self.xml
        self._graphml = self._xml.element(
            "graphml",
            {
                "xmlns": self.NS_GRAPHML,
                "xmlns:xsi": self.NS_XSI,
                "xsi:schemaLocation": self.SCHEMALOCATION,
            },
        )
        self._graphml.__enter__()
        self.keys = {}
        self.attribute_types = defaultdict(set)

        if graph is not None:
            self.add_graph_element(graph)

    def add_graph_element(self, G):
        """
        Serialize graph G in GraphML to the stream.
        """
        if G.is_directed():
            default_edge_type = "directed"
        else:
            default_edge_type = "undirected"

        graphid = G.graph.pop("id", None)
        if graphid is None:
            graph_element = self._xml.element("graph", edgedefault=default_edge_type)
        else:
            graph_element = self._xml.element(
                "graph", edgedefault=default_edge_type, id=graphid
            )

        # gather attributes types for the whole graph
        # to find the most general numeric format needed.
        # Then pass through attributes to create key_id for each.
        graphdata = {
            k: v
            for k, v in G.graph.items()
            if k not in ("node_default", "edge_default")
        }
        node_default = G.graph.get("node_default", {})
        edge_default = G.graph.get("edge_default", {})
        # Graph attributes
        for k, v in graphdata.items():
            self.attribute_types[(str(k), "graph")].add(type(v))
        for k, v in graphdata.items():
            element_type = self.get_xml_type(self.attr_type(k, "graph", v))
            self.get_key(str(k), element_type, "graph", None)
        # Nodes and data
        for node, d in G.nodes(data=True):
            for k, v in d.items():
                self.attribute_types[(str(k), "node")].add(type(v))
        for node, d in G.nodes(data=True):
            for k, v in d.items():
                T = self.get_xml_type(self.attr_type(k, "node", v))
                self.get_key(str(k), T, "node", node_default.get(k))
        # Edges and data
        if G.is_multigraph():
            for u, v, ekey, d in G.edges(keys=True, data=True):
                for k, v in d.items():
                    self.attribute_types[(str(k), "edge")].add(type(v))
            for u, v, ekey, d in G.edges(keys=True, data=True):
                for k, v in d.items():
                    T = self.get_xml_type(self.attr_type(k, "edge", v))
                    self.get_key(str(k), T, "edge", edge_default.get(k))
        else:
            for u, v, d in G.edges(data=True):
                for k, v in d.items():
                    self.attribute_types[(str(k), "edge")].add(type(v))
            for u, v, d in G.edges(data=True):
                for k, v in d.items():
                    T = self.get_xml_type(self.attr_type(k, "edge", v))
                    self.get_key(str(k), T, "edge", edge_default.get(k))

        # Now add attribute keys to the xml file
        for key in self.xml:
            self._xml.write(key, pretty_print=self._prettyprint)

        # The incremental_writer writes each node/edge as it is created
        incremental_writer = IncrementalElement(self._xml, self._prettyprint)
        with graph_element:
            self.add_attributes("graph", incremental_writer, graphdata, {})
            self.add_nodes(G, incremental_writer)  # adds attributes too
            self.add_edges(G, incremental_writer)  # adds attributes too

    def add_attributes(self, scope, xml_obj, data, default):
        """Appends attribute data."""
        for k, v in data.items():
            data_element = self.add_data(
                str(k), self.attr_type(str(k), scope, v), str(v), scope, default.get(k)
            )
            xml_obj.append(data_element)

    def __str__(self):
        return object.__str__(self)

    def dump(self, stream=None):
        self._graphml.__exit__(None, None, None)
        self._xml_base.__exit__(None, None, None)


# default is lxml is present.
write_graphml = write_graphml_lxml


class GraphMLReader(GraphML):
    """Read a GraphML document.  Produces NetworkX graph objects."""

    def __init__(self, node_type=str, edge_key_type=int, force_multigraph=False):
        self.construct_types()
        self.node_type = node_type
        self.edge_key_type = edge_key_type
        self.multigraph = force_multigraph  # If False, test for multiedges
        self.edge_ids = {}  # dict mapping (u,v) tuples to edge id attributes

    def __call__(self, path=None, string=None):
        from xml.etree.ElementTree import ElementTree, fromstring

        if path is not None:
            self.xml = ElementTree(file=path)
        elif string is not None:
            self.xml = fromstring(string)
        else:
            raise ValueError("Must specify either 'path' or 'string' as kwarg")
        (keys, defaults) = self.find_graphml_keys(self.xml)
        for g in self.xml.findall(f"{{{self.NS_GRAPHML}}}graph"):
            yield self.make_graph(g, keys, defaults)

    def make_graph(self, graph_xml, graphml_keys, defaults, G=None):
        # set default graph type
        edgedefault = graph_xml.get("edgedefault", None)
        if G is None:
            if edgedefault == "directed":
                G = nx.MultiDiGraph()
            else:
                G = nx.MultiGraph()
        # set defaults for graph attributes
        G.graph["node_default"] = {}
        G.graph["edge_default"] = {}
        for key_id, value in defaults.items():
            key_for = graphml_keys[key_id]["for"]
            name = graphml_keys[key_id]["name"]
            python_type = graphml_keys[key_id]["type"]
            if key_for == "node":
                G.graph["node_default"].update({name: python_type(value)})
            if key_for == "edge":
                G.graph["edge_default"].update({name: python_type(value)})
        # hyperedges are not supported
        hyperedge = graph_xml.find(f"{{{self.NS_GRAPHML}}}hyperedge")
        if hyperedge is not None:
            raise nx.NetworkXError("GraphML reader doesn't support hyperedges")
        # add nodes
        for node_xml in graph_xml.findall(f"{{{self.NS_GRAPHML}}}node"):
            self.add_node(G, node_xml, graphml_keys, defaults)
        # add edges
        for edge_xml in graph_xml.findall(f"{{{self.NS_GRAPHML}}}edge"):
            self.add_edge(G, edge_xml, graphml_keys)
        # add graph data
        data = self.decode_data_elements(graphml_keys, graph_xml)
        G.graph.update(data)

        # switch to Graph or DiGraph if no parallel edges were found
        if self.multigraph:
            return G

        G = nx.DiGraph(G) if G.is_directed() else nx.Graph(G)
        # add explicit edge "id" from file as attribute in NX graph.
        nx.set_edge_attributes(G, values=self.edge_ids, name="id")
        return G

    def add_node(self, G, node_xml, graphml_keys, defaults):
        """Add a node to the graph."""
        # warn on finding unsupported ports tag
        ports = node_xml.find(f"{{{self.NS_GRAPHML}}}port")
        if ports is not None:
            warnings.warn("GraphML port tag not supported.")
        # find the node by id and cast it to the appropriate type
        node_id = self.node_type(node_xml.get("id"))
        # get data/attributes for node
        data = self.decode_data_elements(graphml_keys, node_xml)
        G.add_node(node_id, **data)
        # get child nodes
        if node_xml.attrib.get("yfiles.foldertype") == "group":
            graph_xml = node_xml.find(f"{{{self.NS_GRAPHML}}}graph")
            self.make_graph(graph_xml, graphml_keys, defaults, G)

    def add_edge(self, G, edge_element, graphml_keys):
        """Add an edge to the graph."""
        # warn on finding unsupported ports tag
        ports = edge_element.find(f"{{{self.NS_GRAPHML}}}port")
        if ports is not None:
            warnings.warn("GraphML port tag not supported.")

        # raise error if we find mixed directed and undirected edges
        directed = edge_element.get("directed")
        if G.is_directed() and directed == "false":
            msg = "directed=false edge found in directed graph."
            raise nx.NetworkXError(msg)
        if (not G.is_directed()) and directed == "true":
            msg = "directed=true edge found in undirected graph."
            raise nx.NetworkXError(msg)

        source = self.node_type(edge_element.get("source"))
        target = self.node_type(edge_element.get("target"))
        data = self.decode_data_elements(graphml_keys, edge_element)
        # GraphML stores edge ids as an attribute
        # NetworkX uses them as keys in multigraphs too if no key
        # attribute is specified
        edge_id = edge_element.get("id")
        if edge_id:
            # self.edge_ids is used by `make_graph` method for non-multigraphs
            self.edge_ids[source, target] = edge_id
            try:
                edge_id = self.edge_key_type(edge_id)
            except ValueError:  # Could not convert.
                pass
        else:
            edge_id = data.get("key")

        if G.has_edge(source, target):
            # mark this as a multigraph
            self.multigraph = True

        # Use add_edges_from to avoid error with add_edge when `'key' in data`
        # Note there is only one edge here...
        G.add_edges_from([(source, target, edge_id, data)])

    def decode_data_elements(self, graphml_keys, obj_xml):
        """Use the key information to decode the data XML if present."""
        data = {}
        for data_element in obj_xml.findall(f"{{{self.NS_GRAPHML}}}data"):
            key = data_element.get("key")
            try:
                data_name = graphml_keys[key]["name"]
                data_type = graphml_keys[key]["type"]
            except KeyError as err:
                raise nx.NetworkXError(f"Bad GraphML data: no key {key}") from err
            text = data_element.text
            # assume anything with subelements is a yfiles extension
            if text is not None and len(list(data_element)) == 0:
                if data_type == bool:
                    # Ignore cases.
                    # http://docs.oracle.com/javase/6/docs/api/java/lang/
                    # Boolean.html#parseBoolean%28java.lang.String%29
                    data[data_name] = self.convert_bool[text.lower()]
                else:
                    data[data_name] = data_type(text)
            elif len(list(data_element)) > 0:
                # Assume yfiles as subelements, try to extract node_label
                node_label = None
                # set GenericNode's configuration as shape type
                gn = data_element.find(f"{{{self.NS_Y}}}GenericNode")
                if gn is not None:
                    data["shape_type"] = gn.get("configuration")
                for node_type in ["GenericNode", "ShapeNode", "SVGNode", "ImageNode"]:
                    pref = f"{{{self.NS_Y}}}{node_type}/{{{self.NS_Y}}}"
                    geometry = data_element.find(f"{pref}Geometry")
                    if geometry is not None:
                        data["x"] = geometry.get("x")
                        data["y"] = geometry.get("y")
                    if node_label is None:
                        node_label = data_element.find(f"{pref}NodeLabel")
                    shape = data_element.find(f"{pref}Shape")
                    if shape is not None:
                        data["shape_type"] = shape.get("type")
                if node_label is not None:
                    data["label"] = node_label.text

                # check all the different types of edges available in yEd.
                for edge_type in [
                    "PolyLineEdge",
                    "SplineEdge",
                    "QuadCurveEdge",
                    "BezierEdge",
                    "ArcEdge",
                ]:
                    pref = f"{{{self.NS_Y}}}{edge_type}/{{{self.NS_Y}}}"
                    edge_label = data_element.find(f"{pref}EdgeLabel")
                    if edge_label is not None:
                        break
                if edge_label is not None:
                    data["label"] = edge_label.text
            elif text is None:
                data[data_name] = ""
        return data

    def find_graphml_keys(self, graph_element):
        """Extracts all the keys and key defaults from the xml."""
        graphml_keys = {}
        graphml_key_defaults = {}
        for k in graph_element.findall(f"{{{self.NS_GRAPHML}}}key"):
            attr_id = k.get("id")
            attr_type = k.get("attr.type")
            attr_name = k.get("attr.name")
            yfiles_type = k.get("yfiles.type")
            if yfiles_type is not None:
                attr_name = yfiles_type
                attr_type = "yfiles"
            if attr_type is None:
                attr_type = "string"
                warnings.warn(f"No key type for id {attr_id}. Using string")
            if attr_name is None:
                raise nx.NetworkXError(f"Unknown key for id {attr_id}.")
            graphml_keys[attr_id] = {
                "name": attr_name,
                "type": self.python_type[attr_type],
                "for": k.get("for"),
            }
            # check for "default" sub-element of key element
            default = k.find(f"{{{self.NS_GRAPHML}}}default")
            if default is not None:
                # Handle default values identically to data element values
                python_type = graphml_keys[attr_id]["type"]
                if python_type == bool:
                    graphml_key_defaults[attr_id] = self.convert_bool[
                        default.text.lower()
                    ]
                else:
                    graphml_key_defaults[attr_id] = python_type(default.text)
        return graphml_keys, graphml_key_defaults
