"""Bounded AST constructor declarations and exact accepted class ownership.

Constructor IDs retain exact bounded signatures before generic deduplication.
This seam supplies prototypes and source proof; unsupported signatures stay unknown.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re

from graphify.extractors.base import _file_stem, _read_text
from graphify.extractors.cpp_identity import CppIdentity, qualified_function_id
from graphify.extractors.cpp_constructor_signature import constructor_id, signature_authorized, signature_fact
from graphify.extractors.cpp_constructor_binding import id_authorized
from graphify.extractors.cpp_constructor_type_authority import ConstructorTypeAuthority, source_facts


def _walk(root):
    pending = [root]
    while pending:
        node = pending.pop()
        yield node
        pending.extend(reversed(node.named_children))


def _span(node):
    return {"start_byte": node.start_byte, "end_byte": node.end_byte,
            "start_row": node.start_point.row, "end_row": node.end_point.row,
            "start_column": node.start_point.column, "end_column": node.end_point.column}


def _identifier(value):
    return bool(value and len(value.encode("utf-8")) <= 384
                and all(part.isidentifier() for part in value.split("::")))


def _encoded(value):
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _decoded(value):
    if not isinstance(value, str) or len(value) > 512:
        return ""
    try:
        result = base64.b64decode(value, validate=True).decode("utf-8")
    except (ValueError, UnicodeError, binascii.Error):
        return ""
    return result if _identifier(result) else ""


def _scope(node, source):
    """Only lexical named namespace/class scopes authorize qualified ownership."""
    parts = []
    parent = node.parent
    while parent:
        if parent.type in {"function_definition", "lambda_expression"}:
            return None
        if parent.type in {"namespace_definition", "class_specifier", "struct_specifier"}:
            name_node = parent.child_by_field_name("name")
            name = _read_text(name_node, source) if name_node else ""
            if not _identifier(name):
                return None
            parts.append(name)
        parent = parent.parent
    return "::".join(reversed(parts))


def _signature(declarator, source):
    params = declarator.child_by_field_name("parameters")
    if params is None or len(params.named_children) > 64 or any(child.type == "..." for child in params.children):
        return ""
    values = []
    for parameter in params.named_children:
        if parameter.type not in {"parameter_declaration", "optional_parameter_declaration", "variadic_parameter_declaration"}:
            return ""
        end = parameter.end_byte
        default = parameter.child_by_field_name("default_value")
        if default:
            end = source.rfind(b"=", parameter.start_byte, default.start_byte)
        if end < parameter.start_byte or end - parameter.start_byte > 512:
            return ""
        name = parameter.child_by_field_name("declarator")
        while name and name.type not in {"identifier", "field_identifier"}:
            name = name.child_by_field_name("declarator") or next(
                (child for child in name.named_children if child.type in {"identifier", "field_identifier", "reference_declarator", "pointer_declarator", "parenthesized_declarator", "function_declarator"}), None)
        text = source[parameter.start_byte:end]
        if name:
            offset = name.start_byte - parameter.start_byte
            text = text[:offset] + text[offset + name.end_byte - name.start_byte:]
        # Preserve word boundaries: `unsigned int` is not the alias `unsignedint`.
        text = re.sub(rb"\s+", b" ", text).strip()
        values.append(re.sub(rb"\s*([*&<>,:\[\]()])\s*", rb"\1", text))
    if values == [b"void"]:
        values = []
    return hashlib.sha256(b"\0".join(values)).hexdigest()


def _fact(node, key):
    metadata = node.get("metadata")
    value = metadata.get(key) if isinstance(metadata, dict) else None
    if (not isinstance(value, dict) or type(value.get("contract_version")) is not int
            or value["contract_version"] != 1 or type(value.get("ambiguous")) is not bool):
        return {}
    span = value.get("span")
    fields = ("start_byte", "end_byte", "start_row", "end_row", "start_column", "end_column")
    if (not isinstance(span, dict) or any(type(span.get(field)) is not int or span[field] < 0 for field in fields)
            or span["end_byte"] <= span["start_byte"] or span["end_row"] < span["start_row"]
            or (span["end_row"] == span["start_row"] and span["end_column"] - span["start_column"] != span["end_byte"] - span["start_byte"])):
        return {}
    if not node.get("source_file") or node.get("source_location") != f"L{span['start_row'] + 1}":
        return {}
    scope_value = value.get("scope_b64")
    scope = "" if scope_value == "" else _decoded(scope_value)
    if not isinstance(scope_value, str) or (scope_value and not scope):
        return {}
    if key == "cpp_class":
        valid = type(value.get("is_definition")) is bool and _decoded(value.get("qualified_name_b64"))
        expected = f"{scope}::{node.get('label')}" if scope else node.get("label")
        valid = valid and _decoded(value["qualified_name_b64"]) == expected
    else:
        valid = (isinstance(value.get("role"), str) and value["role"] in {"declaration", "definition"} and _decoded(value.get("owner_b64"))
                 and node.get("_callable") is True and node.get("_callable_class") is not True
                 and isinstance(value.get("signature"), str) and re.fullmatch(r"[0-9a-f]{64}", value["signature"]))
        name = _decoded(value.get("name_b64"))
        label = str(node.get("label", "")).removesuffix("()").removeprefix(".")
        owner = _decoded(value.get("owner_b64"))
        original_owner, _, short = name.rpartition("::")
        expected = f"{scope}::{original_owner}" if scope and original_owner else original_owner or scope
        valid = (valid and name == label and owner.split("::")[-1] == (short if original_owner else name)
                 and owner == expected)
    if key == "cpp_constructor":
        valid = valid and (value["ambiguous"] or signature_authorized(node, value)) and id_authorized(node, owner, value["signature"])
    return value if valid else {}


def _store(node, key, fact):
    metadata = dict(node.get("metadata") or {})
    previous = metadata.get(key)
    if previous:
        fact["ambiguous"] = True
    metadata[key] = fact
    node["metadata"] = metadata


def augment_cpp_constructors(root, source, nodes, edges, path):
    """Produce bounded exact source facts; never execute or reparse the corpus."""
    if root.has_error:
        return
    source_facts(root, source, nodes, path)
    by_id = {node["id"]: node for node in nodes}
    identities = CppIdentity(root, source, _file_stem(path))
    classes = {}
    syntax = list(_walk(root))
    for item in syntax:
        if item.type not in {"class_specifier", "struct_specifier"}:
            continue
        name_node = item.child_by_field_name("name")
        name = _read_text(name_node, source) if name_node else ""
        scope = _scope(item, source)
        if scope is None or not _identifier(name):
            continue
        record = identities.record(item)
        owner = by_id.get(record["id"]) if record else None
        if owner is None or owner.get("_callable_class") is not True:
            continue
        qualified = f"{scope}::{name}" if scope else name
        if not _identifier(qualified):
            continue
        if identities.preferred(record) is record:
            fact = {"contract_version": 1, "qualified_name_b64": _encoded(qualified),
                    "scope_b64": _encoded(scope),
                    "is_definition": item.child_by_field_name("body") is not None,
                    "span": _span(item), "ambiguous": identities.ambiguous(record)}
            _store(owner, "cpp_class", fact)
        classes[item.id] = (owner, qualified)
    for item in syntax:
        if item.type not in {"declaration", "function_definition"} or item.child_by_field_name("type") is not None:
            continue
        declarator = item.child_by_field_name("declarator")
        if declarator is None or declarator.type != "function_declarator":
            continue
        name_node = declarator.child_by_field_name("declarator")
        name = _read_text(name_node, source) if name_node else ""
        if not _identifier(name):
            continue
        scope = _scope(item, source)
        if scope is None:
            continue
        parent = item.parent
        while parent and parent.type not in {"class_specifier", "struct_specifier", "translation_unit", "namespace_definition"}:
            parent = parent.parent
        owner_info = classes.get(parent.id) if parent else None
        if owner_info and name == owner_info[1].split("::")[-1]:
            owner, qualified = owner_info
            nid = constructor_id(owner["id"], name, item, source, qualified)
            if nid not in by_id:
                node = {"id": nid, "label": f".{name}()", "file_type": "code",
                        "source_file": str(path), "source_location": f"L{item.start_point.row + 1}", "_callable": True}
                nodes.append(node)
                by_id[nid] = node
                edges.append({"source": owner["id"], "target": nid, "relation": "method",
                              "confidence": "EXTRACTED", "source_file": str(path),
                              "source_location": node["source_location"], "weight": 1.0})
            role = "definition" if item.type == "function_definition" else "declaration"
        elif not owner_info and item.type == "function_definition" and "::" in name:
            qualified, short = name.rsplit("::", 1)
            if qualified.split("::")[-1] != short or item.child_by_field_name("body") is None:
                continue
            qualified = f"{scope}::{qualified}" if scope else qualified
            nid = qualified_function_id(_file_stem(path), item, name, source)
            if nid not in by_id or not _identifier(qualified):
                continue
            role = "definition"
        else:
            continue
        _store(by_id[nid], "cpp_constructor", {"contract_version": 1, "owner_b64": _encoded(qualified),
               "scope_b64": _encoded(scope),
               "name_b64": _encoded(name), "role": role, "span": _span(item),
               "owner_bound": bool(owner_info and role == "definition"), **signature_fact(item, source, qualified)})
    type_authority = ConstructorTypeAuthority(nodes)
    for node in nodes:
        fact = _fact(node, "cpp_constructor")
        if fact:
            fact["type_authorized"] = type_authority.authorized(node, fact)
            if not fact["type_authorized"]:
                fact["owner_bound"] = False


def bind_cpp_constructors(nodes, edges):
    """Public constructor seam delegates to the single corpus binding owner."""
    from graphify.extractors.cpp_constructor_binding import bind_constructors
    bind_constructors(nodes, edges)


def constructor_merge_allowed(group):
    """A header prototype cannot hide an unmatched or ambiguous implementation."""
    facts = [_fact(node, "cpp_constructor") for node in group]
    if any(isinstance(node.get("metadata"), dict) and "cpp_constructor" in node["metadata"] and not fact
           for node, fact in zip(group, facts)):
        return False
    return not (any(fact.get("ambiguous") for fact in facts)
                or sum(fact.get("role") == "definition" for fact in facts) > 1
                or any(fact.get("role") == "definition" and fact.get("owner_bound") is not True for fact in facts))


def constructor_class_authorized(node):
    """A Qt consumer may retain the callable while rejecting its class authority."""
    metadata = node.get("metadata")
    if not isinstance(metadata, dict) or "cpp_constructor" not in metadata:
        return True
    fact = _fact(node, "cpp_constructor")
    return bool(fact and not fact["ambiguous"] and fact.get("type_authorized") is True
                and (fact["role"] == "declaration" or fact.get("owner_bound") is True))
