"""Qt/QML graph-database payloads retain literal facts and logical direction."""
from __future__ import annotations

import hashlib
import json
import re

from graphify.graph_direction import logical_endpoints as accepted_endpoints


def has_qt_qml(graph) -> bool:
    return any(_typed(data) for _, data in graph.nodes(data=True)) or any(
        _typed(data) for _, _, data in graph.edges(data=True))


def _typed(data) -> bool:
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        return False
    return any(isinstance(value := metadata.get(name), dict)
               and type(value.get("contract_version")) is int and value["contract_version"] == 1
               for name in ("qml", "qt"))


def export_properties(data, *, preserve_metadata=False) -> dict:
    """Database properties are scalar; nested semantic payloads use exact JSON.

    The compatibility path preserves the existing scalar-only property view.
    Qt/QML graphs retain metadata/attributes as separately named JSON strings,
    including canonical endpoint evidence and lossless literal transport.
    """
    if preserve_metadata:
        _reserved(data, {"metadata_json", "attributes_json"})
    result = {key: value for key, value in data.items() if isinstance(key, str)
              and not key.startswith("_") and isinstance(value, (str, int, float, bool))}
    if preserve_metadata:
        for key in ("metadata", "attributes"):
            if isinstance(data.get(key), (dict, list)):
                result[key + "_json"] = _json(data[key])
    return result


def logical_endpoints(source, target, data, *, directed=False):
    """Exports share consumer pair validation while retaining their stable rejection code."""
    endpoints = accepted_endpoints(source, target, data, directed=directed)
    if endpoints is None:
        raise ValueError("QT_EXPORT_DIRECTION: invalid logical edge pair; re-extract or repair the graph")
    return endpoints


def edge_properties(source, target, data, *, preserve_metadata=False) -> dict:
    result = export_properties(data, preserve_metadata=preserve_metadata)
    if preserve_metadata:
        _reserved(data, {"graphify_source", "graphify_target", "graphify_fact_key"})
        result["graphify_source"], result["graphify_target"] = source, target
        result["graphify_fact_key"] = hashlib.sha256(_json([source, target, result]).encode()).hexdigest()
    return result


def _reserved(data, keys):
    if any(key in data for key in keys):
        raise ValueError("QT_EXPORT_PROPERTY_COLLISION: reserved transport property already exists")


def preflight_qt_payload(graph) -> None:
    """Validate the complete Qt transport before connecting or writing externally."""
    for _, data in graph.nodes(data=True):
        export_properties(data, preserve_metadata=True)
    for source, target, data in graph.edges(data=True):
        # External exports honor complete logical pairs on bidirectional storage
        # wrappers. JSON separately checks native directed identity when persisted.
        src, tgt = logical_endpoints(source, target, data)
        edge_properties(src, tgt, data, preserve_metadata=True)


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identifier(value, fallback):
    name = re.sub(r"[^A-Za-z0-9_]", "_", str(value)) or fallback
    return name if not name[0].isdigit() else fallback + "_" + name


def _map(values):
    # Escaped identifier keys and non-interpolated JSON string literals prevent
    # property data from becoming executable Cypher. Live pushes use parameters.
    entries = []
    for key, value in sorted(values.items()):
        quoted_key = "`" + key.replace("`", "``") + "`"
        entries.append(quoted_key + ":" + _json(value))
    return "{" + ",".join(entries) + "}"


def qt_cypher_lines(graph) -> list[str] | None:
    """Return a Qt-aware complete upsert script, or the untouched legacy path.

    Source facts remain inspectable JSON properties. Stable relationship keys
    preserve distinct mechanisms even for parallel accepted endpoint pairs.
    This writer does not execute a database or remove earlier database records.
    """
    if not has_qt_qml(graph):
        return None
    lines = ["// Qt/QML Cypher transport: metadata_json retains literal source facts.",
             "// Upsert only; stale database records need an explicit replacement policy.", ""]
    for node_id, data in graph.nodes(data=True):
        props = export_properties(data, preserve_metadata=True)
        props["id"] = node_id
        label = _identifier(str(data.get("file_type") or "Entity").capitalize(), "Entity")
        lines.append(f"MERGE (n:{label} {{id:{_json(node_id)}}}) SET n += {_map(props)};")
    for source, target, data in graph.edges(data=True):
        src, tgt = logical_endpoints(source, target, data)
        props = edge_properties(src, tgt, data, preserve_metadata=True)
        relation = _identifier(str(data.get("relation") or "RELATES_TO").upper(), "RELATES_TO")
        key = _json(props["graphify_fact_key"])
        lines.append(f"MATCH (a {{id:{_json(src)}}}), (b {{id:{_json(tgt)}}}) "
                     f"MERGE (a)-[r:{relation} {{graphify_fact_key:{key}}}]->(b) SET r += {_map(props)};")
    return lines
