"""Neutral pre-6.9 tooling spellings; no native API or source-read authority."""
from graphify.extractors.qml_facts import qml_metadata


OWNERS = ("Property", "Method", "Signal", "Parameter", "Enum")


def module(owner="Method", value="true", *, extra="", name="lookup"):
    """A single literal legacy type flag stays owned by its exact tooling object."""
    member = f'{owner} {{ name: "{name}"; type: "QUrl"; isConstant: {value}; {extra} }}'
    if owner == "Parameter":
        member = 'Method { name: "invoke"; ' + member + ' }'
    return ('import QtQuick.tooling 1.2\nModule { Component { name: "Backénd"; '
            'prototype: "QObject"; file: "../outside.hpp"; '
            'exports: ["Public.Legacy/Widget 1.0"]; ' + member + ' } }\n')


def records(result, kind):
    return [(node, qml_metadata(node)) for node in result["nodes"]
            if qml_metadata(node).get("kind") == kind]


def constants(result):
    return [(node, fact) for node, fact in records(result, "qmltypes_field")
            if fact.get("field_name") == "isConstant"]


def graph_payload(graph):
    return {"nodes": [{"id": identity, **data} for identity, data in graph.nodes(data=True)],
            "edges": [{"source": data.get("_src", source), "target": data.get("_tgt", target), **data}
                      for source, target, data in graph.edges(data=True)]}


def field_owner(result, field):
    """Actual source-owned edges, including their original span, survive every transport."""
    edge, = [edge for edge in result["edges"] if edge["target"] == field["id"]
             and edge["relation"] == "contains" and edge.get("context") == "qt_metadata_declaration"]
    assert edge["confidence"] == "EXTRACTED"
    assert qml_metadata(edge)["span"] == qml_metadata(field)["span"]
    owner, = [node for node in result["nodes"] if node["id"] == edge["source"]]
    assert qml_metadata(owner)["span"] == qml_metadata(field)["span"]
    return qml_metadata(owner)


def point(raw, offset):
    prefix = raw[:offset]
    return prefix.count(b"\n"), len(prefix.rsplit(b"\n", 1)[-1])
