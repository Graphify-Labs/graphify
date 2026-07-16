"""Read and write graphs in GEXF format.

.. warning::
    This parser uses the standard xml library present in Python, which is
    insecure - see :external+python:mod:`xml` for additional information.
    Only parse GEFX files you trust.

GEXF (Graph Exchange XML Format) is a language for describing complex
network structures, their associated data and dynamics.

This implementation does not support mixed graphs (directed and
undirected edges together).

Format
------
GEXF is an XML format.  See http://gexf.net/schema.html for the
specification and http://gexf.net/basic.html for examples.
"""

import itertools
import time
from xml.etree.ElementTree import (
    Element,
    ElementTree,
    SubElement,
    register_namespace,
    tostring,
)

import networkx as nx
from networkx.utils import open_file

__all__ = ["write_gexf", "read_gexf", "relabel_gexf_graph", "generate_gexf"]


@open_file(1, mode="wb")
def write_gexf(G, path, encoding="utf-8", prettyprint=True, version="1.2draft"):
    """Write G in GEXF format to path.

    "GEXF (Graph Exchange XML Format) is a language for describing
    complex networks structures, their associated data and dynamics" [1]_.

    Node attributes are checked according to the version of the GEXF
    schemas used for parameters which are not user defined,
    e.g. visualization 'viz' [2]_. See example for usage.

    Parameters
    ----------
    G : graph
       A NetworkX graph
    path : file or string
       File or file name to write.
       File names ending in .gz or .bz2 will be compressed.
    encoding : string (optional, default: 'utf-8')
       Encoding for text data.
    prettyprint : bool (optional, default: True)
       If True use line breaks and indenting in output XML.
    version: string (optional, default: '1.2draft')
       The version of GEXF to be used for nodes attributes checking

    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> nx.write_gexf(G, "test.gexf")

    # visualization data
    >>> G.nodes[0]["viz"] = {"size": 54}
    >>> G.nodes[0]["viz"]["position"] = {"x": 0, "y": 1}
    >>> G.nodes[0]["viz"]["color"] = {"r": 0, "g": 0, "b": 256}


    Notes
    -----
    This implementation does not support mixed graphs (directed and undirected
    edges together).

    The node id attribute is set to be the string of the node label.
    If you want to specify an id use set it as node data, e.g.
    node['a']['id']=1 to set the id of node 'a' to 1.

    References
    ----------
    .. [1] GEXF File Format, http://gexf.net/
    .. [2] GEXF schema, http://gexf.net/schema.html
    """
    writer = GEXFWriter(encoding=encoding, prettyprint=prettyprint, version=version)
    writer.add_graph(G)
    writer.write(path)


def generate_gexf(G, encoding="utf-8", prettyprint=True, version="1.2draft"):
    """Generate lines of GEXF format representation of G.

    "GEXF (Graph Exchange XML Format) is a language for describing
    complex networks structures, their associated data and dynamics" [1]_.

    Parameters
    ----------
    G : graph
    A NetworkX graph
    encoding : string (optional, default: 'utf-8')
    Encoding for text data.
    prettyprint : bool (optional, default: True)
    If True use line breaks and indenting in output XML.
    version : string (default: 1.2draft)
    Version of GEFX File Format (see http://gexf.net/schema.html)
    Supported values: "1.1draft", "1.2draft"


    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> linefeed = chr(10)  # linefeed=\n
    >>> s = linefeed.join(nx.generate_gexf(G))
    >>> for line in nx.generate_gexf(G):  # doctest: +SKIP
    ...     print(line)

    Notes
    -----
    This implementation does not support mixed graphs (directed and undirected
    edges together).

    The node id attribute is set to be the string of the node label.
    If you want to specify an id use set it as node data, e.g.
    node['a']['id']=1 to set the id of node 'a' to 1.

    References
    ----------
    .. [1] GEXF File Format, https://gephi.org/gexf/format/
    """
    writer = GEXFWriter(encoding=encoding, prettyprint=prettyprint, version=version)
    writer.add_graph(G)
    yield from str(writer).splitlines()


@open_file(0, mode="rb")
@nx._dispatchable(graphs=None, returns_graph=True)
def read_gexf(path, node_type=None, relabel=False, version="1.2draft"):
    """Read graph in GEXF format from path.

    "GEXF (Graph Exchange XML Format) is a language for describing
    complex networks structures, their associated data and dynamics" [1]_.

    Parameters
    ----------
    path : file or string
       File or file name to read.
       File names ending in .gz or .bz2 will be decompressed.
    node_type: Python type (default: None)
       Convert node ids to this type if not None.
    relabel : bool (default: False)
       If True relabel the nodes to use the GEXF node "label" attribute
       instead of the node "id" attribute as the NetworkX node label.
    version : string (default: 1.2draft)
    Version of GEFX File Format (see http://gexf.net/schema.html)
       Supported values: "1.1draft", "1.2draft"

    Returns
    -------
    graph: NetworkX graph
        If no parallel edges are found a Graph or DiGraph is returned.
        Otherwise a MultiGraph or MultiDiGraph is returned.

    Notes
    -----
    This implementation does not support mixed graphs (directed and undirected
    edges together).

    References
    ----------
    .. [1] GEXF File Format, http://gexf.net/
    """
    reader = GEXFReader(node_type=node_type, version=version)
    if relabel:
        G = relabel_gexf_graph(reader(path))
    else:
        G = reader(path)
    return G


class GEXF:
    versions = {
        "1.1draft": {
            "NS_GEXF": "http://www.gexf.net/1.1draft",
            "NS_VIZ": "http://www.gexf.net/1.1draft/viz",
            "NS_XSI": "http://www.w3.org/2001/XMLSchema-instance",
            "SCHEMALOCATION": " ".join(
                [
                    "http://www.gexf.net/1.1draft",
                    "http://www.gexf.net/1.1draft/gexf.xsd",
                ]
            ),
            "VERSION": "1.1",
        },
        "1.2draft": {
            "NS_GEXF": "http://www.gexf.net/1.2draft",
            "NS_VIZ": "http://www.gexf.net/1.2draft/viz",
            "NS_XSI": "http://www.w3.org/2001/XMLSchema-instance",
            "SCHEMALOCATION": " ".join(
                [
                    "http://www.gexf.net/1.2draft",
                    "http://www.gexf.net/1.2draft/gexf.xsd",
                ]
            ),
            "VERSION": "1.2",
        },
    }

    def construct_types(self):
        types = [
            (int, "integer"),
            (float, "float"),
            (float, "double"),
            (bool, "boolean"),
            (list, "string"),
            (dict, "string"),
            (int, "long"),
            (str, "liststring"),
            (str, "anyURI"),
            (str, "string"),
        ]

        # These additions to types allow writing numpy types
        try:
            import numpy as np
        except ImportError:
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

    # http://www.w3.org/TR/xmlschema-2/#boolean
    convert_bool = {
        "true": True,
        "false": False,
        "True": True,
        "False": False,
        "0": False,
        0: False,
        "1": True,
        1: True,
    }

    def set_version(self, version):
        d = self.versions.get(version)
        if d is None:
            raise nx.NetworkXError(f"Unknown GEXF version {version}.")
        self.NS_GEXF = d["NS_GEXF"]
        self.NS_VIZ = d["NS_VIZ"]
        self.NS_XSI = d["NS_XSI"]
        self.SCHEMALOCATION = d["SCHEMALOCATION"]
        self.VERSION = d["VERSION"]
        self.version = version


class GEXFWriter(GEXF):
    # class for writing GEXF format files
    # use write_gexf() function
    def __init__(
        self, graph=None, encoding="utf-8", prettyprint=True, version="1.2draft"
    ):
        self.construct_types()
        self.prettyprint = prettyprint
        self.encoding = encoding
        self.set_version(version)
        self.xml = Element(
            "gexf",
            {
                "xmlns": self.NS_GEXF,
                "xmlns:xsi": self.NS_XSI,
                "xsi:schemaLocation": self.SCHEMALOCATION,
                "version": self.VERSION,
            },
        )

        # Make meta element a non-graph element
        # Also add lastmodifieddate as attribute, not tag
        meta_element = Element("meta")
        subelement_text = f"NetworkX {nx.__version__}"
        SubElement(meta_element, "creator").text = subelement_text
        meta_element.set("lastmodifieddate", time.strftime("%Y-%m-%d"))
        self.xml.append(meta_element)

        register_namespace("viz", self.NS_VIZ)

        # counters for edge and attribute identifiers
        self.edge_id = itertools.count()
        self.attr_id = itertools.count()
        self.all_edge_ids = set()
        # default attributes are stored in dictionaries
        self.attr = {}
        self.attr["node"] = {}
        self.attr["edge"] = {}
        self.attr["node"]["dynamic"] = {}
        self.attr["node"]["static"] = {}
        self.attr["edge"]["dynamic"] = {}
        self.attr["edge"]["static"] = {}

        if graph is not None:
            self.add_graph(graph)

    def __str__(self):
        if self.prettyprint:
            self.indent(self.xml)
        s = tostring(self.xml).decode(self.encoding)
        return s

    def add_graph(self, G):
        # first pass through G collecting edge ids
        for u, v, dd in G.edges(data=True):
            eid = dd.get("id")
            if eid is not None:
                self.all_edge_ids.add(str(eid))
        # set graph attributes
        if G.graph.get("mode") == "dynamic":
            mode = "dynamic"
        else:
            mode = "static"
        # Add a graph element to the XML
        if G.is_directed():
            default = "directed"
        else:
            default = "undirected"
        name = G.graph.get("name", "")
        graph_element = Element("graph", defaultedgetype=default, mode=mode, name=name)
        self.graph_element = graph_element
        self.add_nodes(G, graph_element)
        self.add_edges(G, graph_element)
        self.xml.append(graph_element)

    def add_nodes(self, G, graph_element):
        nodes_element = Element("nodes")
        for node, data in G.nodes(data=True):
            node_data = data.copy()
            node_id = str(node_data.pop("id", node))
            kw = {"id": node_id}
            label = str(node_data.pop("label", node))
            kw["label"] = label
            try:
                pid = node_data.pop("pid")
                kw["pid"] = str(pid)
            except KeyError:
                pass
            try:
                start = node_data.pop("start")
                kw["start"] = str(start)
                self.alter_graph_mode_timeformat(start)
            except KeyError:
                pass
            try:
                end = node_data.pop("end")
                kw["end"] = str(end)
                self.alter_graph_mode_timeformat(end)
            except KeyError:
                pass
            # add node element with attributes
            node_element = Element("node", **kw)
            # add node element and attr subelements
            default = G.graph.get("node_default", {})
            node_data = self.add_parents(node_element, node_data)
            if self.VERSION == "1.1":
                node_data = self.add_slices(node_element, node_data)
            else:
                node_data = self.add_spells(node_element, node_data)
            node_data = self.add_viz(node_element, node_data)
            node_data = self.add_attributes("node", node_element, node_data, default)
            nodes_element.append(node_element)
        graph_element.append(nodes_element)

    def add_edges(self, G, graph_element):
        def edge_key_data(G):
            # helper function to unify multigraph and graph edge iterator
            if G.is_multigraph():
                for u, v, key, data in G.edges(data=True, keys=True):
                    edge_data = data.copy()
                    edge_data.update(key=key)
                    edge_id = edge_data.pop("id", None)
                    if edge_id is None:
                        edge_id = next(self.edge_id)
                        while str(edge_id) in self.all_edge_ids:
                            edge_id = next(self.edge_id)
                        self.all_edge_ids.add(str(edge_id))
                    yield u, v, edge_id, edge_data
            else:
                for u, v, data in G.edges(data=True):
                    edge_data = data.copy()
                    edge_id = edge_data.pop("id", None)
                    if edge_id is None:
                        edge_id = next(self.edge_id)
                        while str(edge_id) in self.all_edge_ids:
                            edge_id = next(self.edge_id)
                        self.all_edge_ids.add(str(edge_id))
                    yield u, v, edge_id, edge_data

        edges_element = Element("edges")
        for u, v, key, edge_data in edge_key_data(G):
            kw = {"id": str(key)}
            try:
                edge_label = edge_data.pop("label")
                kw["label"] = str(edge_label)
            except KeyError:
                pass
            try:
                edge_weight = edge_data.pop("weight")
                kw["weight"] = str(edge_weight)
            except KeyError:
                pass
            try:
                edge_type = edge_data.pop("type")
                kw["type"] = str(edge_type)
            except KeyError:
                pass
            try:
                start = edge_data.pop("start")
                kw["start"] = str(start)
                self.alter_graph_mode_timeformat(start)
            except KeyError:
                pass
            try:
                end = edge_data.pop("end")
                kw["end"] = str(end)
                self.alter_graph_mode_timeformat(end)
            except KeyError:
                pass
            source_id = str(G.nodes[u].get("id", u))
            target_id = str(G.nodes[v].get("id", v))
            edge_element = Element("edge", source=source_id, target=target_id, **kw)
            default = G.graph.get("edge_default", {})
            if self.VERSION == "1.1":
                edge_data = self.add_slices(edge_element, edge_data)
            else:
                edge_data = self.add_spells(edge_element, edge_data)
            edge_data = self.add_viz(edge_element, edge_data)
            edge_data = self.add_attributes("edge", edge_element, edge_data, default)
            edges_element.append(edge_element)
        graph_element.append(edges_element)

    def add_attributes(self, node_or_edge, xml_obj, data, default):
        # Add attrvalues to node or edge
        attvalues = Element("attvalues")
        if len(data) == 0:
            return data
        mode = "static"
        for k, v in data.items():
            # rename generic multigraph key to avoid any name conflict
            if k == "key":
                k = "networkx_key"
            val_type = type(v)
            if val_type not in self.xml_type:
                raise TypeError(f"attribute value type is not allowed: {val_type}")
            if isinstance(v, list):
                # dynamic data
                for val, start, end in v:
                    val_type = type(val)
                    if start is not None or end is not None:
                        mode = "dynamic"
                        self.alter_graph_mode_timeformat(start)
                        self.alter_graph_mode_timeformat(end)
                        break
                attr_id = self.get_attr_id(
                    str(k), self.xml_type[val_type], node_or_edge, default, mode
                )
                for val, start, end in v:
                    e = Element("attvalue")
                    e.attrib["for"] = attr_id
                    e.attrib["value"] = str(val)
                    # Handle nan, inf, -inf differently
                    if val_type == float:
                        if e.attrib["value"] == "inf":
                            e.attrib["value"] = "INF"
                        elif e.attrib["value"] == "nan":
                            e.attrib["value"] = "NaN"
                        elif e.attrib["value"] == "-inf":
                            e.attrib["value"] = "-INF"
                    if start is not None:
                        e.attrib["start"] = str(start)
                    if end is not None:
                        e.attrib["end"] = str(end)
                    attvalues.append(e)
            else:
                # static data
                mode = "static"
                attr_id = self.get_attr_id(
                    str(k), self.xml_type[val_type], node_or_edge, default, mode
                )
                e = Element("attvalue")
                e.attrib["for"] = attr_id
                if isinstance(v, bool):
                    e.attrib["value"] = str(v).lower()
                else:
                    e.attrib["value"] = str(v)
                    # Handle float nan, inf, -inf differently
                    if val_type == float:
                        if e.attrib["value"] == "inf":
                            e.attrib["value"] = "INF"
                        elif e.attrib["value"] == "nan":
                            e.attrib["value"] = "NaN"
                        elif e.attrib["value"] == "-inf":
                            e.attrib["value"] = "-INF"
                attvalues.append(e)
        xml_obj.append(attvalues)
        return data

    def get_attr_id(self, title, attr_type, edge_or_node, default, mode):
        # find the id of the attribute or generate a new id
        try:
            return self.attr[edge_or_node][mode][title]
        except KeyError:
            # generate new id
            new_id = str(next(self.attr_id))
            self.attr[edge_or_node][mode][title] = new_id
            attr_kwargs = {"id": new_id, "title": title, "type": attr_type}
            attribute = Element("attribute", **attr_kwargs)
            # add subelement for data default value if present
            default_title = default.get(title)
            if default_title is not None:
                default_element = Element("default")
                default_element.text = str(default_title)
                attribute.append(default_element)
            # new insert it into the XML
            attributes_element = None
            for a in self.graph_element.findall("attributes"):
                # find existing attributes element by class and mode
                a_class = a.get("class")
                a_mode = a.get("mode", "static")
                if a_class == edge_or_node and a_mode == mode:
                    attributes_element = a
            if attributes_element is None:
                # create new attributes element
                attr_kwargs = {"mode": mode, "class": edge_or_node}
                attributes_element = Element("attributes", **attr_kwargs)
                self.graph_element.insert(0, attributes_element)
            attributes_element.append(attribute)
        return new_id

    def add_viz(self, element, node_data):
        viz = node_data.pop("viz", False)
        if viz:
            color = viz.get("color")
            if color is not None:
                if self.VERSION == "1.1":
                    e = Element(
                        f"{{{self.NS_VIZ}}}color",
                        r=str(color.get("r")),
                        g=str(color.get("g")),
                        b=str(color.get("b")),
                    )
                else:
                    e = Element(
                        f"{{{self.NS_VIZ}}}color",
                        r=str(color.get("r")),
                        g=str(color.get("g")),
                        b=str(color.get("b")),
                        a=str(color.get("a", 1.0)),
                    )
                element.append(e)

            size = viz.get("size")
            if size is not None:
                e = Element(f"{{{self.NS_VIZ}}}size", value=str(size))
                element.append(e)

            thickness = viz.get("thickness")
            if thickness is not None:
                e = Element(f"{{{self.NS_VIZ}}}thickness", value=str(thickness))
                element.append(e)

            shape = viz.get("shape")
            if shape is not None:
                if shape.startswith("http"):
                    e = Element(
                        f"{{{self.NS_VIZ}}}shape", value="image", uri=str(shape)
                    )
                else:
                    e = Element(f"{{{self.NS_VIZ}}}shape", value=str(shape))
                element.append(e)

            position = viz.get("position")
            if position is not None:
                e = Element(
                    f"{{{self.NS_VIZ}}}position",
                    x=str(position.get("x")),
                    y=str(position.get("y")),
                    z=str(position.get("z")),
                )
                element.append(e)
        return node_data

    def add_parents(self, node_element, node_data):
        parents = node_data.pop("parents", False)
        if parents:
            parents_element = Element("parents")
            for p in parents:
                e = Element("parent")
                e.attrib["for"] = str(p)
                parents_element.append(e)
            node_element.append(parents_element)
        return node_data

    def add_slices(self, node_or_edge_element, node_or_edge_data):
        slices = node_or_edge_data.pop("slices", False)
        if slices:
            slices_element = Element("slices")
            for start, end in slices:
                e = Element("slice", start=str(start), end=str(end))
                slices_element.append(e)
            node_or_edge_element.append(slices_element)
        return node_or_edge_data

    def add_spells(self, node_or_edge_element, node_or_edge_data):
        spells = node_or_edge_data.pop("spells", False)
        if spells:
            spells_element = Element("spells")
            for start, end in spells:
                e = Element("spell")
                if start is not None:
                    e.attrib["start"] = str(start)
                    self.alter_graph_mode_timeformat(start)
                if end is not None:
                    e.attrib["end"] = str(end)
                    self.alter_graph_mode_timeformat(end)
                spells_element.append(e)
            node_or_edge_element.append(spells_element)
        return node_or_edge_data

    def alter_graph_mode_timeformat(self, start_or_end):
        # If 'start' or 'end' appears, alter Graph mode to dynamic and
        # set timeformat
        if self.graph_element.get("mode") == "static":
            if start_or_end is not None:
                if isinstance(start_or_end, str):
                    timeformat = "date"
                elif isinstance(start_or_end, float):
                    timeformat = "double"
                elif isinstance(start_or_end, int):
                    timeformat = "long"
                else:
                    raise nx.NetworkXError(
                        "timeformat should be of the type int, float or str"
                    )
                self.graph_element.set("timeformat", timeformat)
                self.graph_element.set("mode", "dynamic")

    def write(self, fh):
        # Serialize graph G in GEXF to the open fh
        if self.prettyprint:
            self.indent(self.xml)
        document = ElementTree(self.xml)
        document.write(fh, encoding=self.encoding, xml_declaration=True)

    def indent(self, elem, level=0):
        # in-place prettyprint formatter
        i = "\n" + "  " * level
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


class GEXFReader(GEXF):
    # Class to read GEXF format files
    # use read_gexf() function
    def __init__(self, node_type=None, version="1.2draft"):
        self.construct_types()
        self.node_type = node_type
        # assume simple graph and test for multigraph on read
        self.simple_graph = True
        self.set_version(version)

    def __call__(self, stream):
        self.xml = ElementTree(file=stream)
        g = self.xml.find(f"{{{self.NS_GEXF}}}graph")
        if g is not None:
            return self.make_graph(g)
        # try all the versions
        for version in self.versions:
            self.set_version(version)
            g = self.xml.find(f"{{{self.NS_GEXF}}}graph")
            if g is not None:
                return self.make_graph(g)
        raise nx.NetworkXError("No <graph> element in GEXF file.")

    def make_graph(self, graph_xml):
        # start with empty DiGraph or MultiDiGraph
        edgedefault = graph_xml.get("defaultedgetype", None)
        if edgedefault == "directed":
            G = nx.MultiDiGraph()
        else:
            G = nx.MultiGraph()

        # graph attributes
        graph_name = graph_xml.get("name", "")
        if graph_name != "":
            G.graph["name"] = graph_name
        graph_start = graph_xml.get("start")
        if graph_start is not None:
            G.graph["start"] = graph_start
        graph_end = graph_xml.get("end")
        if graph_end is not None:
            G.graph["end"] = graph_end
        graph_mode = graph_xml.get("mode", "")
        if graph_mode == "dynamic":
            G.graph["mode"] = "dynamic"
        else:
            G.graph["mode"] = "static"

        # timeformat
        self.timeformat = graph_xml.get("timeformat")
        if self.timeformat == "date":
            self.timeformat = "string"

        # node and edge attributes
        attributes_elements = graph_xml.findall(f"{{{self.NS_GEXF}}}attributes")
        # dictionaries to hold attributes and attribute defaults
        node_attr = {}
        node_default = {}
        edge_attr = {}
        edge_default = {}
        for a in attributes_elements:
            attr_class = a.get("class")
            if attr_class == "node":
                na, nd = self.find_gexf_attributes(a)
                node_attr.update(na)
                node_default.update(nd)
                G.graph["node_default"] = node_default
            elif attr_class == "edge":
                ea, ed = self.find_gexf_attributes(a)
                edge_attr.update(ea)
                edge_default.update(ed)
                G.graph["edge_default"] = edge_default
            else:
                raise  # unknown attribute class

        # Hack to handle Gephi0.7beta bug
        # add weight attribute
        ea = {"weight": {"type": "double", "mode": "static", "title": "weight"}}
        ed = {}
        edge_attr.update(ea)
        edge_default.update(ed)
        G.graph["edge_default"] = edge_default

        # add nodes
        nodes_element = graph_xml.find(f"{{{self.NS_GEXF}}}nodes")
        if nodes_element is not None:
            for node_xml in nodes_element.findall(f"{{{self.NS_GEXF}}}node"):
                self.add_node(G, node_xml, node_attr)

        # add edges
        edges_element = graph_xml.find(f"{{{self.NS_GEXF}}}edges")
        if edges_element is not None:
            for edge_xml in edges_element.findall(f"{{{self.NS_GEXF}}}edge"):
                self.add_edge(G, edge_xml, edge_attr)

        # switch to Graph or DiGraph if no parallel edges were found.
        if self.simple_graph:
            if G.is_directed():
                G = nx.DiGraph(G)
            else:
                G = nx.Graph(G)
        return G

    def add_node(self, G, node_xml, node_attr, node_pid=None):
        # add a single node with attributes to the graph

        # get attributes and subattributues for node
        data = self.decode_attr_elements(node_attr, node_xml)
        data = self.add_parents(data, node_xml)  # add any parents
        if self.VERSION == "1.1":
            data = self.add_slices(data, node_xml)  # add slices
        else:
            data = self.add_spells(data, node_xml)  # add spells
        data = self.add_viz(data, node_xml)  # add viz
        data = self.add_start_end(data, node_xml)  # add start/end

        # find the node id and cast it to the appropriate type
        node_id = node_xml.get("id")
        if self.node_type is not None:
            node_id = self.node_type(node_id)

        # every node should have a label
        node_label = node_xml.get("label")
        data["label"] = node_label

        # parent node id
        node_pid = node_xml.get("pid", node_pid)
        if node_pid is not None:
            data["pid"] = node_pid

        # check for subnodes, recursive
        subnodes = node_xml.find(f"{{{self.NS_GEXF}}}nodes")
        if subnodes is not None:
            for node_xml in subnodes.findall(f"{{{self.NS_GEXF}}}node"):
                self.add_node(G, node_xml, node_attr, node_pid=node_id)

        G.add_node(node_id, **data)

    def add_start_end(self, data, xml):
        # start and end times
        ttype = self.timeformat
        node_start = xml.get("start")
        if node_start is not None:
            data["start"] = self.python_type[ttype](node_start)
        node_end = xml.get("end")
        if node_end is not None:
            data["end"] = self.python_type[ttype](node_end)
        return data

    def add_viz(self, data, node_xml):
        # add viz element for node
        viz = {}
        color = node_xml.find(f"{{{self.NS_VIZ}}}color")
        if color is not None:
            if self.VERSION == "1.1":
                viz["color"] = {
                    "r": int(color.get("r")),
                    "g": int(color.get("g")),
                    "b": int(color.get("b")),
                }
            else:
                viz["color"] = {
                    "r": int(color.get("r")),
                    "g": int(color.get("g")),
                    "b": int(color.get("b")),
                    "a": float(color.get("a", 1)),
                }

        size = node_xml.find(f"{{{self.NS_VIZ}}}size")
        if size is not None:
            viz["size"] = float(size.get("value"))

        thickness = node_xml.find(f"{{{self.NS_VIZ}}}thickness")
        if thickness is not None:
            viz["thickness"] = float(thickness.get("value"))

        shape = node_xml.find(f"{{{self.NS_VIZ}}}shape")
        if shape is not None:
            viz["shape"] = shape.get("shape")
            if viz["shape"] == "image":
                viz["shape"] = shape.get("uri")

        position = node_xml.find(f"{{{self.NS_VIZ}}}position")
        if position is not None:
            viz["position"] = {
                "x": float(position.get("x", 0)),
                "y": float(position.get("y", 0)),
                "z": float(position.get("z", 0)),
            }

        if len(viz) > 0:
            data["viz"] = viz
        return data

    def add_parents(self, data, node_xml):
        parents_element = node_xml.find(f"{{{self.NS_GEXF}}}parents")
        if parents_element is not None:
            data["parents"] = []
            for p in parents_element.findall(f"{{{self.NS_GEXF}}}parent"):
                parent = p.get("for")
                data["parents"].append(parent)
        return data

    def add_slices(self, data, node_or_edge_xml):
        slices_element = node_or_edge_xml.find(f"{{{self.NS_GEXF}}}slices")
        if slices_element is not None:
            data["slices"] = []
            for s in slices_element.findall(f"{{{self.NS_GEXF}}}slice"):
                start = s.get("start")
                end = s.get("end")
                data["slices"].append((start, end))
        return data

    def add_spells(self, data, node_or_edge_xml):
        spells_element = node_or_edge_xml.find(f"{{{self.NS_GEXF}}}spells")
        if spells_element is not None:
            data["spells"] = []
            ttype = self.timeformat
            for s in spells_element.findall(f"{{{self.NS_GEXF}}}spell"):
                start = self.python_type[ttype](s.get("start"))
                end = self.python_type[ttype](s.get("end"))
                data["spells"].append((start, end))
        return data

    def add_edge(self, G, edge_element, edge_attr):
        # add an edge to the graph

        # raise error if we find mixed directed and undirected edges
        edge_direction = edge_element.get("type")
        if G.is_directed() and edge_direction == "undirected":
            raise nx.NetworkXError("Undirected edge found in directed graph.")
        if (not G.is_directed()) and edge_direction == "directed":
            raise nx.NetworkXError("Directed edge found in undirected graph.")

        # Get source and target and recast type if required
        source = edge_element.get("source")
        target = edge_element.get("target")
        if self.node_type is not None:
            source = self.node_type(source)
            target = self.node_type(target)

        data = self.decode_attr_elements(edge_attr, edge_element)
        data = self.add_start_end(data, edge_element)

        if self.VERSION == "1.1":
            data = self.add_slices(data, edge_element)  # add slices
        else:
            data = self.add_spells(data, edge_element)  # add spells

        # GEXF stores edge ids as an attribute
        # NetworkX uses them as keys in multigraphs
        # if networkx_key is not specified as an attribute
        edge_id = edge_element.get("id")
        if edge_id is not None:
            data["id"] = edge_id

        # check if there is a 'multigraph_key' and use that as edge_id
        multigraph_key = data.pop("networkx_key", None)
        if multigraph_key is not None:
            edge_id = multigraph_key

        weight = edge_element.get("weight")
        if weight is not None:
            data["weight"] = float(weight)

        edge_label = edge_element.get("label")
        if edge_label is not None:
            data["label"] = edge_label

        if G.has_edge(source, target):
            # seen this edge before - this is a multigraph
            self.simple_graph = False
        G.add_edge(source, target, key=edge_id, **data)
        if edge_direction == "mutual":
            G.add_edge(target, source, key=edge_id, **data)

    def decode_attr_elements(self, gexf_keys, obj_xml):
        # Use the key information to decode the attr XML
        attr = {}
        # look for outer '<attvalues>' element
        attr_element = obj_xml.find(f"{{{self.NS_GEXF}}}attvalues")
        if attr_element is not None:
            # loop over <attvalue> elements
            for a in attr_element.findall(f"{{{self.NS_GEXF}}}attvalue"):
                key = a.get("for")  # for is required
                try:  # should be in our gexf_keys dictionary
                    title = gexf_keys[key]["title"]
                except KeyError as err:
                    raise nx.NetworkXError(f"No attribute defined for={key}.") from err
                atype = gexf_keys[key]["type"]
                value = a.get("value")
                if atype == "boolean":
                    value = self.convert_bool[value]
                else:
                    value = self.python_type[atype](value)
                if gexf_keys[key]["mode"] == "dynamic":
                    # for dynamic graphs use list of three-tuples
                    # [(value1,start1,end1), (value2,start2,end2), etc]
                    ttype = self.timeformat
                    start = self.python_type[ttype](a.get("start"))
                    end = self.python_type[ttype](a.get("end"))
                    if title in attr:
                        attr[title].append((value, start, end))
                    else:
                        attr[title] = [(value, start, end)]
                else:
                    # for static graphs just assign the value
                    attr[title] = value
        return attr

    def find_gexf_attributes(self, attributes_element):
        # Extract all the attributes and defaults
        attrs = {}
        defaults = {}
        mode = attributes_element.get("mode")
        for k in attributes_element.findall(f"{{{self.NS_GEXF}}}attribute"):
            attr_id = k.get("id")
            title = k.get("title")
            atype = k.get("type")
            attrs[attr_id] = {"title": title, "type": atype, "mode": mode}
            # check for the 'default' subelement of key element and add
            default = k.find(f"{{{self.NS_GEXF}}}default")
            if default is not None:
                if atype == "boolean":
                    value = self.convert_bool[default.text]
                else:
                    value = self.python_type[atype](default.text)
                defaults[title] = value
        return attrs, defaults


def relabel_gexf_graph(G):
    """Relabel graph using "label" node keyword for node label.

    Parameters
    ----------
    G : graph
       A NetworkX graph read from GEXF data

    Returns
    -------
    H : graph
      A NetworkX graph with relabeled nodes

    Raises
    ------
    NetworkXError
        If node labels are missing or not unique while relabel=True.

    Notes
    -----
    This function relabels the nodes in a NetworkX graph with the
    "label" attribute.  It also handles relabeling the specific GEXF
    node attributes "parents", and "pid".
    """
    # build mapping of node labels, do some error checking
    try:
        mapping = [(u, G.nodes[u]["label"]) for u in G]
    except KeyError as err:
        raise nx.NetworkXError(
            "Failed to relabel nodes: missing node labels found. Use relabel=False."
        ) from err
    x, y = zip(*mapping)
    if len(set(y)) != len(G):
        raise nx.NetworkXError(
            "Failed to relabel nodes: "
            "duplicate node labels found. "
            "Use relabel=False."
        )
    mapping = dict(mapping)
    H = nx.relabel_nodes(G, mapping)
    # relabel attributes
    for n in G:
        m = mapping[n]
        H.nodes[m]["id"] = n
        H.nodes[m].pop("label")
        if "pid" in H.nodes[m]:
            H.nodes[m]["pid"] = mapping[G.nodes[n]["pid"]]
        if "parents" in H.nodes[m]:
            H.nodes[m]["parents"] = [mapping[p] for p in G.nodes[n]["parents"]]
    return H
