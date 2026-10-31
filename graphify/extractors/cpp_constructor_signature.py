"""Bounded constructor signature identity before generic node deduplication.

The accepted profile covers builtin, self-class and QObject parameter types with
literal pointer/reference qualifiers. Unsupported types retain occurrence IDs;
they never authorize a declaration/definition join. No compiler or corpus runs.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re

from graphify.extractors.base import _make_id, _read_text


def _builtin(value):
    words = value.split()
    single = {"bool", "char", "wchar_t", "char8_t", "char16_t", "char32_t", "float", "double", "void"}
    if len(words) == 1 and words[0] in single:
        return words[0]
    if words and all(word in {"signed", "unsigned", "short", "long", "int", "char", "double"} for word in words):
        if (words.count("long") > 2 or any(words.count(word) > 1 for word in set(words) - {"long"})
                or {"signed", "unsigned"} <= set(words) or {"short", "long"} <= set(words)):
            return ""
        if "double" in words:
            return "long double" if sorted(words) == ["double", "long"] else ""
        if "char" in words:
            return " ".join(sorted(words)) if len(words) == 2 and set(words) <= {"signed", "unsigned", "char"} else ""
        sign = "unsigned " if "unsigned" in words else ""
        size = "short" if "short" in words else "long long" if words.count("long") == 2 else "long" if "long" in words else "int"
        return sign + size
    return ""


def _parameter(parameter, source, owner):
    """Remove value-only CV and names without erasing pointee/reference types."""
    if parameter.type not in {"parameter_declaration", "optional_parameter_declaration"}:
        return ""
    type_node = parameter.child_by_field_name("type")
    if type_node is None or parameter.end_byte - parameter.start_byte > 1024:
        return ""
    raw_type = re.sub(r"\s+", " ", _read_text(type_node, source)).strip()
    base = _builtin(raw_type)
    if not base:
        # Aliases and unrelated named types need semantic proof beyond spelling.
        if raw_type in {owner, owner.rsplit("::", 1)[-1]}:
            base = "self:" + owner
        elif raw_type == "QObject":
            base = "QObject"
        else:
            return ""
    qualifier = sorted(_read_text(child, source) for child in parameter.children if child.type == "type_qualifier")
    if any(value not in {"const", "volatile"} for value in qualifier):
        return ""
    declarator = parameter.child_by_field_name("declarator")
    layers = []
    while declarator and declarator.type not in {"identifier", "field_identifier"}:
        if declarator.type not in {"pointer_declarator", "reference_declarator", "abstract_pointer_declarator", "abstract_reference_declarator"}:
            return ""
        cv = sorted(_read_text(child, source) for child in declarator.children if child.type == "type_qualifier")
        if any(value not in {"const", "volatile"} for value in cv):
            return ""
        symbol = "*" if "pointer" in declarator.type else "&&" if any(child.type == "&&" for child in declarator.children) else "&"
        layers.append([symbol, cv])
        declarator = declarator.child_by_field_name("declarator") or next(
            (child for child in declarator.named_children if child.type != "type_qualifier"), None)
    if layers and layers[-1][0] == "*":
        layers[-1][1] = []  # Last lexical layer is the value-level pointer.
    # C++ permits a sole unnamed unqualified void as an empty parameter list;
    # value-CV normalization must not turn an invalid qualified void into it.
    if base == "void" and not layers and qualifier:
        return ""
    if not layers:
        qualifier = []
    if base == "void" and not layers and parameter.child_by_field_name("declarator") is not None:
        return ""
    if base == "void" and (layers or qualifier):
        return "" if not layers else " ".join(qualifier + [base]) + "".join(symbol + " ".join(cv) for symbol, cv in layers)
    return " ".join(qualifier + [base]) + "".join(symbol + " ".join(cv) for symbol, cv in layers)


def constructor_signature(node, source, owner):
    """Return accepted signature bytes or no authority for unsupported syntax."""
    declarator = node.child_by_field_name("declarator")
    if declarator is None or declarator.type != "function_declarator" or node.has_error:
        return b""
    parent = node.parent
    while parent:
        if parent.type == "template_declaration" or parent.type.startswith("preproc_"):
            return b""
        parent = parent.parent
    if any(child.type == "requires_clause" for child in declarator.named_children):
        return b""
    params = declarator.child_by_field_name("parameters")
    if params is None or len(params.named_children) > 64 or any(child.type == "..." for child in params.children):
        return b""
    values = [_parameter(item, source, owner) for item in params.named_children]
    if any(not value for value in values) or "void" in values and values != ["void"]:
        return b""
    # An explicit version marker distinguishes accepted zero arguments from an
    # unsupported signature, and bounds transport below metadata string limits.
    payload = ("ctor2\0" + "\0".join([] if values == ["void"] else values)).encode()
    return payload if len(payload) <= 360 else b""


def constructor_id(class_id, name, node, source, owner):
    """IDs never depend on the number or ordering of neighboring overloads."""
    payload = constructor_signature(node, source, owner)
    if not payload:
        # A source-owned unsupported occurrence must not collapse onto another
        # callable or become a plausible exact signature through normalization.
        payload = b"unsupported\0" + str(node.start_byte).encode() + b"\0" + source[node.start_byte:node.end_byte]
    digest = hashlib.sha256(payload).hexdigest()
    return _make_id(class_id, name, "cppctor", digest)


def signature_fact(node, source, owner):
    payload = constructor_signature(node, source, owner)
    return {"signature": hashlib.sha256(payload).hexdigest() if payload else hashlib.sha256(
                b"unsupported\0" + str(node.start_byte).encode() + b"\0" + source[node.start_byte:node.end_byte]).hexdigest(),
            "signature_b64": base64.b64encode(payload).decode(), "ambiguous": not bool(payload)}


def signature_authorized(node, fact):
    """Reject corrupted transport and copying another overload's signature."""
    value = fact.get("signature_b64")
    if not isinstance(value, str) or not value or len(value) > 480:
        return False
    try:
        payload = base64.b64decode(value, validate=True)
        decoded = payload.decode("utf-8")
    except (ValueError, UnicodeError, binascii.Error):
        return False
    if (not decoded.startswith("ctor2\0") or len(payload) > 360
            or hashlib.sha256(payload).hexdigest() != fact.get("signature")):
        return False
    return str(node.get("id", "")).endswith("_cppctor_" + fact["signature"])
