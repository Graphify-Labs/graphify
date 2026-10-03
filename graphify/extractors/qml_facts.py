"""Portable, bounded QML facts and lossless semantic metadata transport."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from graphify.ids import make_id

CONTRACT_VERSION = 1


def make_qml_id(relative_file: str, kind: str, semantic_key: str) -> str:
    identity = json.dumps([relative_file, kind, semantic_key], ensure_ascii=False)
    digest = hashlib.sha256(identity.encode()).hexdigest()[:16]
    return make_id("qml", relative_file, kind, semantic_key, digest)


def make_scope_key(relative_file: str, semantic_key: str) -> str:
    """Fixed-width scopes avoid multiplying parent ID length with nesting."""
    identity = json.dumps([relative_file, semantic_key], ensure_ascii=False)
    return hashlib.sha256(identity.encode()).hexdigest()


def span(node) -> dict:
    return {
        "start_byte": node.start_byte, "end_byte": node.end_byte,
        "start_row": node.start_point.row, "start_column": node.start_point.column,
        "end_row": node.end_point.row, "end_column": node.end_point.column,
    }


def text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8") if node else ""


def field(node, name: str, source: bytes) -> str:
    return text(node.child_by_field_name(name), source)


def qml_metadata(node: dict) -> dict:
    """Read literal lookup values after graph sanitation/JSON round trips.

    Display values retain Graphify's HTML escaping. Their bounded base64 copies
    preserve semantic punctuation without trusting HTML as a lookup encoding.
    """
    meta = dict(node.get("metadata", {}).get("qml", {}))
    for key, value in meta.get("raw_values", {}).items():
        meta[key] = base64.b64decode(value, validate=True).decode("utf-8")
    return meta


def encode_metadata(values: dict) -> dict:
    raw = {}
    for key, value in values.items():
        if isinstance(value, str):
            encoded = base64.b64encode(value.encode()).decode("ascii")
            if len(encoded) > 512:
                raise ValueError("QML_LIMIT: semantic field exceeds transport bound")
            raw[key] = encoded
    return {"contract_version": CONTRACT_VERSION, **values, "raw_values": raw}


class FactBuilder:
    """One source owns declarations and derived sites; roots never enter IDs."""

    def __init__(self, path: Path, root: Path | None, source: bytes):
        self.path = path
        self.source = source
        resolved = path.resolve()
        anchor = root.resolve() if root is not None else resolved.parent
        try:
            self.relative_file = resolved.relative_to(anchor).as_posix()
        except ValueError as exc:
            raise ValueError("QML_ROOT: source is outside the explicit scan root") from exc
        self.nodes: list[dict] = []
        self.edges: list[dict] = []

    def add(self, kind: str, name: str, syntax_node, owner=None, **values) -> dict:
        key = values.pop("semantic_key", name)
        identity = make_qml_id(self.relative_file, kind, key)
        meta = encode_metadata({"kind": kind, "raw_name": name,
                                "raw_type": "", "span": span(syntax_node), **values})
        node = {"id": identity, "label": name or kind, "file_type": "code", "_origin": "ast",
                "type": {"file": "file", "component": "class",
                         "inline_component": "class", "function": "function",
                         "property": "property"}.get(kind, "concept"),
                "source_file": self.relative_file,
                "source_location": f"L{syntax_node.start_point.row + 1}-L{syntax_node.end_point.row + 1}",
                "metadata": {"qml": meta}}
        self.nodes.append(node)
        if owner:
            self.edge(owner["id"] if isinstance(owner, dict) else owner,
                      identity, "contains", syntax_node, kind="declaration")
        return node

    def edge(self, source: str, target: str, relation: str, syntax_node, **values):
        self.edges.append({"source": source, "target": target, "relation": relation,
                           "_src": source, "_tgt": target,
                           "confidence": "EXTRACTED", "source_file": self.relative_file,
                           "source_location": f"L{syntax_node.start_point.row + 1}-L{syntax_node.end_point.row + 1}",
                           "metadata": {"qml": encode_metadata({"span": span(syntax_node), **values})}})
