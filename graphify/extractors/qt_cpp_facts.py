"""Portable source-owned Qt facts with literal, bounded metadata transport."""
from __future__ import annotations

import base64
import hashlib
import json

from graphify.ids import make_id


def encode_qt(values: dict) -> dict:
    """Display sanitation and semantic identity have separate representations."""
    literals = {}
    def visit(path, value):
        if isinstance(value, str):
            encoded = base64.b64encode(value.encode()).decode("ascii")
            if len(encoded) > 512:
                raise ValueError("QT_LIMIT: semantic field exceeds transport bound")
            literals["/".join(path)] = encoded
        elif isinstance(value, dict):
            for key, child in value.items():
                visit([*path, str(key)], child)
        elif isinstance(value, list):
            if len(value) > 50:
                raise ValueError("QT_LIMIT: semantic list exceeds transport bound")
            for index, child in enumerate(value):
                visit([*path, str(index)], child)
    for key, value in values.items():
        visit([key], value)
    if len(literals) > 100:
        raise ValueError("QT_LIMIT: semantic fields exceed transport bound")
    return {"contract_version": 1, **values, "raw_values": literals}


def qt_metadata(node: dict) -> dict:
    """Reject corrupted transport instead of interpreting escaped display strings."""
    value = node.get("metadata", {}).get("qt", {})
    if not isinstance(value, dict) or value.get("contract_version") != 1:
        return {}
    result = json.loads(json.dumps(value))
    literals = result.get("raw_values", {})
    if not isinstance(literals, dict) or len(literals) > 100:
        raise ValueError("QT_METADATA: malformed literal transport")
    for key, encoded in literals.items():
        if not isinstance(key, str) or not isinstance(encoded, str) or len(encoded) > 512:
            raise ValueError("QT_METADATA: malformed literal field")
        try:
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
            parts, current = key.split("/"), result
            for part in parts[:-1]:
                current = current[int(part)] if isinstance(current, list) else current[part]
            if isinstance(current, list):
                current[int(parts[-1])] = decoded
            else:
                current[parts[-1]] = decoded
        except (ValueError, UnicodeError, KeyError, IndexError, TypeError) as exc:
            raise ValueError("QT_METADATA: malformed literal field") from exc
    return result


def source_span(syntax) -> dict:
    if isinstance(syntax, dict):
        return dict(syntax)
    return {"start_byte": syntax.start_byte, "end_byte": syntax.end_byte,
            "start_row": syntax.start_point.row, "end_row": syntax.end_point.row,
            "start_column": syntax.start_point.column, "end_column": syntax.end_point.column}


def qt_id(file: str, kind: str, semantic_key) -> str:
    exact = json.dumps([file, kind, semantic_key], ensure_ascii=False, separators=(",", ":"))
    return make_id("qt", file, kind, hashlib.sha256(exact.encode()).hexdigest())


def owner_scope(unit, owner):
    return qt_id(unit.relative_file, "owner_scope", [owner.get("qualified_name"), owner.get("signature"), owner["span"]["start_byte"], owner["span"]["end_byte"]])


def scope_owner(metadata):
    return metadata.get("owner_scope_key") or metadata.get("owner_id")


class QtFacts:
    """One accepted source owns facts; canonical C++ nodes are borrowed unchanged."""

    def __init__(self, unit):
        self.unit, self.file = unit, unit.relative_file
        self.nodes, self.edges = [], []

    def add(self, kind, name, syntax, owner=None, **fields):
        span = source_span(syntax)
        owner_id = owner.get("id") if isinstance(owner, dict) else owner or ""
        semantic = fields.pop("semantic_key", [owner_id, span["start_byte"], span["end_byte"], name])
        node = {"id": qt_id(self.file, kind, semantic), "label": f"Qt {kind}: {name}",
                "type": "concept", "file_type": "code", "source_file": self.file,
                "source_location": f'L{span["start_row"] + 1}-L{span["end_row"] + 1}', "_origin": "ast",
                "metadata": {"qt": encode_qt({"kind": kind, "raw_name": name, "span": span,
                                                "owner_id": owner_id, **fields})}}
        self.nodes.append(node)
        if owner_id:
            self.edge(owner_id, node["id"], "contains", span, context="qt_source_site")
        return node

    def edge(self, source, target, relation, syntax, *, context, confidence="EXTRACTED", **fields):
        span = source_span(syntax)
        edge = {"source": source, "target": target, "_src": source, "_tgt": target,
                "relation": relation, "confidence": confidence, "context": context,
                "source_file": self.file, "source_location": f'L{span["start_row"] + 1}-L{span["end_row"] + 1}',
                "metadata": {"qt": encode_qt({"span": span, "target_id": target, **fields})}}
        self.edges.append(edge)
        return edge


def update_qt(node, **fields) -> None:
    values = {k: v for k, v in qt_metadata(node).items() if k != "raw_values"}
    node["metadata"]["qt"] = encode_qt({**values, **fields})


def qt_edge(site, target, relation, context, **fields):
    """Source direction survives Graphify's undirected graph and raw JSON reload."""
    span = qt_metadata(site).get("span", {})
    return {"source": site["id"], "target": target, "_src": site["id"], "_tgt": target,
            "relation": relation, "confidence": "INFERRED", "context": context,
            "source_file": site["source_file"], "source_location": site["source_location"],
            "metadata": {"qt": encode_qt({"span": span, "target_id": target, **fields})}}
