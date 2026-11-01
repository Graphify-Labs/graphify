"""Explicit C# indexer source descriptions, separate from runtime accessor dispatch.

The existing engine owns nodes, type references and accepted containing types.
This helper reads only the supplied declaration/tree bytes; it does not infer
element-access targets, storage, generated accessors or a receiver named this.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib

from graphify.extractors.base import _read_text

_TYPES = {"class_declaration", "struct_declaration", "interface_declaration", "record_declaration"}
_CONDITIONS = {"preproc_if", "preproc_elif", "preproc_else"}
_LIMIT = 50


@dataclass(frozen=True)
class IndexerDescription:
    label: str
    signature_key: str
    metadata: dict
    type_nodes: tuple


def _span(node, end=None):
    end = node if end is None else end
    return {"start_byte": node.start_byte, "end_byte": end.end_byte,
            "start_row": node.start_point.row, "end_row": end.end_point.row,
            "start_column": node.start_point.column, "end_column": end.end_point.column}


def _literal(node, source):
    raw = source[node.start_byte:node.end_byte]
    if len(raw) > 384:
        return "", "", "unsupported"
    return _read_text(node, source), base64.b64encode(raw).decode("ascii"), "source_only"


def _type_fields(node, source):
    text, encoded, status = _literal(node, source)
    fields = {"declared_type": text, "declared_type_b64": encoded, "type_status": status,
              "type_span": _span(node)}
    if status != "source_only":
        fields["type_reason"] = "indexer_type_literal_limit"
    return fields


def _modifiers(node, source):
    return [_read_text(child, source) for child in node.named_children if child.type == "modifier"][:_LIMIT]


def _conditional(node):
    while node is not None:
        if node.type in _CONDITIONS:
            return True
        node = node.parent
    return False


def _direct_owner(node):
    parent = node.parent
    for _ in range(256):
        if parent is None:
            return None
        if parent.type == "declaration_list" or parent.type.startswith("preproc_"):
            parent = parent.parent
        else:
            return parent if parent.type in _TYPES else None
    return None


def _parameter_parts(parameters):
    """The pinned grammar flattens the final params parameter onto its list."""
    values = []
    for child in parameters.named_children:
        if child.type == "parameter":
            values.append((child, child.child_by_field_name("type"), child.child_by_field_name("name"), False))
    array_type = parameters.child_by_field_name("type")
    array_name = parameters.child_by_field_name("name")
    marker = next((child for child in parameters.children if child.type == "params"), None)
    if marker is not None and array_type is not None and array_name is not None:
        values.append((marker, array_type, array_name, True))
    return values


def _parameter(part, source):
    syntax, declared, name, array = part
    text, encoded, status = _literal(name, source)
    result = {"name": text, "name_b64": encoded, "name_status": status,
              "name_span": _span(name), "span": _span(syntax, name) if array else _span(syntax),
              "modifiers": ["params"] if array else _modifiers(syntax, source),
              "default_span": {}, **_type_fields(declared, source)}
    if not array:
        assigned = next((i for i, child in enumerate(syntax.children) if child.type == "="), None)
        if assigned is not None:
            tail = syntax.children[assigned + 1:]
            if tail:
                result["default_span"] = _span(tail[0], tail[-1])
    return result


def _signature(interface, parts, parameters, source):
    """Source-token identity ignores comments/names/defaults, not CLR type aliases."""
    digest, work = hashlib.sha256(), 0
    for node in [interface, *(part[1] for part in parts)]:
        digest.update(b"\x00type\x00")
        pending = [node] if node is not None else []
        while pending:
            current = pending.pop()
            work += 1
            if work > 100_000:
                # Large unsupported signatures still retain a bounded opaque
                # source identity; no partial token list is claimed complete.
                qualifier = source[interface.start_byte:interface.end_byte] if interface is not None else b""
                return hashlib.sha256(b"opaque\x00" + qualifier + b"\x00" + source[parameters.start_byte:parameters.end_byte]).hexdigest(), "unsupported"
            if current.type == "comment":
                continue
            if current.child_count:
                pending.extend(reversed(current.children))
            else:
                raw = source[current.start_byte:current.end_byte]
                digest.update(len(raw).to_bytes(8, "big"))
                digest.update(raw)
    return digest.hexdigest(), "source_only"


def _accessors(node, source):
    values, pending = [], [node] if node is not None else []
    while pending:
        current = pending.pop()
        if current.type == "accessor_declaration":
            name, body = current.child_by_field_name("name"), current.child_by_field_name("body")
            if name is None or current.has_error:
                continue
            values.append({"name": _read_text(name, source), "name_span": _span(name), "span": _span(current),
                "modifiers": _modifiers(current, source), "conditional": _conditional(current),
                "body_span": _span(body) if body is not None else {},
                "body_kind": "expression" if body is not None and body.type == "arrow_expression_clause" else
                             "block" if body is not None else "none"})
        elif current.type == "accessor_list" or current.type.startswith("preproc_"):
            pending.extend(reversed(current.named_children))
    return values


def describe_indexer(node, source):
    """Describe only an actual member declaration; no parser or file discovery occurs."""
    if node.type != "indexer_declaration" or node.has_error or _direct_owner(node) is None:
        return None
    name = next((child for child in node.children if child.type == "this" and not child.is_missing), None)
    declared, parameters = node.child_by_field_name("type"), node.child_by_field_name("parameters")
    if name is None or declared is None or parameters is None or declared.is_missing:
        return None
    parts = _parameter_parts(parameters)
    if not parts or any(t is None or n is None or t.is_missing or n.is_missing for _, t, n, _ in parts):
        return None
    interface = next((child for child in node.named_children if child.type == "explicit_interface_specifier"), None)
    signature, signature_status = _signature(interface, parts, parameters, source)
    accessor_list, expression = node.child_by_field_name("accessors"), node.child_by_field_name("value")
    accessors = _accessors(accessor_list, source)
    if not accessors and expression is None:
        return None
    metadata = {"contract_version": 1, "kind": "indexer", "status": "source_only", "runtime_status": "unverified",
        "span": _span(node), "name_span": _span(name), "modifiers": _modifiers(node, source),
        "conditional": _conditional(node), "signature_status": signature_status, **_type_fields(declared, source),
        "parameter_count": len(parts), "parameters_status": "source_only" if len(parts) <= _LIMIT else "unsupported",
        "parameters": [_parameter(part, source) for part in parts[:_LIMIT]],
        "accessor_count": len(accessors), "accessors_status": "source_only" if len(accessors) <= _LIMIT else "unsupported",
        "accessors": accessors[:_LIMIT], "expression_body_span": _span(expression) if expression is not None else {},
        "attribute_spans": [_span(child) for child in node.named_children if child.type == "attribute_list"][:_LIMIT]}
    if len(parts) > _LIMIT:
        metadata["parameters_reason"] = "indexer_parameter_metadata_limit"
    if len(accessors) > _LIMIT:
        metadata["accessors_reason"] = "indexer_accessor_metadata_limit"
    if interface is not None:
        text, encoded, status = _literal(interface, source)
        metadata.update(explicit_interface_specifier=text, explicit_interface_specifier_b64=encoded,
                        explicit_interface_span=_span(interface), explicit_interface_status=status)
    types = [(declared, "field")] if metadata["type_status"] == "source_only" else []
    types.extend((part[1], "param_type") for part in parts[:_LIMIT]
                 if part[1].end_byte - part[1].start_byte <= 384)
    labels = [_read_text(part[1], source) if part[1].end_byte - part[1].start_byte <= 384
              else "<unsupported type>" for part in parts[:_LIMIT]]
    prefix = (_read_text(interface, source) if interface.end_byte - interface.start_byte <= 384
              else "<source interface>.") if interface is not None else ""
    label = prefix + "this[" + ",".join(labels) + "]"
    if len(parts) > _LIMIT or len(label.encode()) > 384:
        label = "this[<source signature>]"
    return IndexerDescription(label, signature, metadata, tuple(types))


class IndexerOccurrences:
    """One producer run retains repeated source declarations without global state."""
    def __init__(self):
        self.counts, self.locations = {}, {}

    def identify(self, owner, description, syntax):
        key = owner, description.signature_key
        location = key, syntax.start_byte, syntax.end_byte
        if location in self.locations:
            return self.locations[location]
        occurrence = self.counts.get(key, 0)
        self.counts[key] = occurrence + 1
        identity = owner + "::indexer-declaration::" + description.signature_key
        if occurrence:
            identity += ":source:" + hashlib.sha256(f"{syntax.start_byte}:{syntax.end_byte}".encode()).hexdigest()
        result = identity, occurrence
        self.locations[location] = result
        return result
