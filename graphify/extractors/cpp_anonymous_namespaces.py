"""Bounded original namespace roles for same-TU anonymous helper lookup.

An anonymous status or scope hash is insufficient lookup authority. The source
producer records actual namespace spans once; this reader checks their order,
the existing function identity, and the named enclosing namespace. It reads no
files, invents no namespace/class node, and never joins translation units.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re

from graphify.extractors.base import _make_id, _read_text
from graphify.extractors.cpp_constructors import _identifier, _span
from graphify.extractors.cpp_source_views import span_contains, valid_span
from graphify.extractors.cpp_function_signature import valid_parameter_facts


def namespace_witness(syntax, source):
    """Capture all original namespace roles without truncating positive proof."""
    scopes, complete, parent = [], True, syntax.parent
    while parent is not None:
        if parent.type == "namespace_definition":
            name_node = parent.child_by_field_name("name")
            name = _read_text(name_node, source) if name_node is not None else None
            complete &= name is None or _identifier(name) and len(name.encode()) <= 384
            scopes.append({"kind": "anonymous" if name is None else "namespace",
                           "name_b64": None if name is None else base64.b64encode(name.encode()).decode(),
                           "span": _span(parent)})
        elif parent.type in {"class_specifier", "struct_specifier", "union_specifier", "function_definition", "lambda_expression", "ERROR"}:
            complete = False
        parent = parent.parent
    scopes.reverse()
    if len(scopes) > 50 or sum(len(item["name_b64"] or "") for item in scopes) > 512:
        complete, scopes = False, []
    return {"contract_version": 1, "complete": bool(complete), "scopes": scopes}


def _name(value):
    if not isinstance(value, str) or len(value) > 512:
        return None
    try:
        raw = base64.b64decode(value, validate=True)
        name = raw.decode()
        return name if len(raw) <= 384 and base64.b64encode(raw).decode() == value and _identifier(name) else None
    except (ValueError, UnicodeError):
        return None


def _anonymous_scope(node, fact, *, declaration_name=None):
    """Validate complete roles before deriving positive or rejection-only host evidence."""
    value = fact.get("anonymous_scope_proof")
    if (not isinstance(value, dict) or type(value.get("contract_version")) is not int
            or value["contract_version"] != 1 or value.get("complete") is not True
            or not isinstance(value.get("scopes"), list) or not 0 < len(value["scopes"]) <= 50):
        return None
    parts, named, proof, parent, anonymous = [], [], [], None, 0
    for scope in value["scopes"]:
        if not isinstance(scope, dict) or type(scope.get("kind")) is not str:
            return None
        span = scope.get("span")
        if (not isinstance(span, dict) or not valid_span(span) or not span_contains(span, fact.get("span"))
                or span == fact.get("span") or parent is not None and (span == parent or not span_contains(parent, span))):
            return None
        if scope["kind"] == "anonymous" and scope.get("name_b64") is None:
            anonymous += 1
            parts.append({"anonymous": span["start_byte"]})
        elif scope["kind"] == "namespace" and (name := _name(scope.get("name_b64"))) is not None:
            parts.append(name)
            named.append(name)
            proof.append({"name_b64": scope["name_b64"], "span": span})
        else:
            return None
        parent = span
    if not anonymous or fact.get("namespace_proof") != proof or fact.get("scope_complete") is not True:
        return None
    scope_key = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    if len(scope_key.encode()) > 384 or hashlib.sha256(scope_key.encode()).hexdigest() != fact.get("scope_fingerprint"):
        return None
    # The same original role sequence must own the existing function ID. A
    # textual host name/hash cannot repurpose another declaration's transport.
    name = declaration_name if declaration_name is not None else _name(fact.get("name_b64"))
    signature, identity = fact.get("signature"), node.get("id")
    if not name or not isinstance(signature, str) or not isinstance(identity, str):
        return None
    identity_parts = (scope_key, name, signature, fact["template_fingerprint"]) if declaration_name is not None else (scope_key, name, signature)
    digest = hashlib.sha256("\0".join(identity_parts).encode()).hexdigest()
    role = "declaration" if declaration_name is not None else "definition"
    if "::" + role + "-occurrence::" in identity:
        span = fact["span"]
        occurrence = "::" + role + "-occurrence::" + hashlib.sha256(f"{span['start_byte']}:{span['end_byte']}".encode()).hexdigest()
        if not identity.endswith(occurrence):
            return None
        identity = identity[:-len(occurrence)]
    suffix = "_" + _make_id("cppproto" if declaration_name is not None else "cppfn", digest, name[:32])
    if not (identity.endswith(suffix) or declaration_name is None and identity.endswith(suffix + "::free-definition::" + digest)):
        return None
    host = []
    for part in parts:
        host.extend(part.split("::") if isinstance(part, str) else [("anonymous", part["anonymous"])])
    while host and isinstance(host[-1], tuple):
        host.pop()  # Terminal anonymous using-directives inject into this containing scope.
    return tuple(host), anonymous == 1 and value["scopes"][-1]["kind"] == "anonymous", "::".join(named)


def anonymous_namespace(node, fact):
    """Only the single terminal anonymous namespace supplies positive lookup."""
    scope = _anonymous_scope(node, fact)
    return scope[2] if scope is not None and scope[1] else None


class AnonymousFunctions:
    """One invocation's immutable source cohort supplies negative and positive choices."""

    def __init__(self):
        self.records = {}

    def add(self, node, fact, name):
        if fact.get("namespace_status") == "anonymous":
            self.records.setdefault((node["source_file"], name), []).append((node, fact, _anonymous_scope(node, fact)))

    def add_declaration(self, node, definitions):
        """A real anonymous prototype can reject lookup, never supply a body/default."""
        metadata = node.get("metadata")
        fact = metadata.get("cpp_prototype") if isinstance(metadata, dict) else None
        if not isinstance(fact, dict) or fact.get("scope_status") != "anonymous":
            return None
        label, source = node.get("label"), node.get("source_file")
        if (not isinstance(label, str) or not label.endswith("()") or not label[:-2].isidentifier()
                or len(label[:-2].encode()) > 384 or not isinstance(source, str) or not source
                or not isinstance(node.get("id"), str)
                or node.get("_callable") is not True or node.get("_callable_class") is True
                or not valid_span(fact.get("span")) or node.get("source_location") != f"L{fact['span']['start_row'] + 1}"
                or (source, node["source_location"]) not in definitions.get(node.get("id"), ())
                or type(fact.get("contract_version")) is not int or fact["contract_version"] != 1
                or fact.get("role") != "declaration" or fact.get("qualified_name_status") != "anonymous"
                or any(type(fact.get(key)) is not bool for key in ("template", "conditional", "static", "scope_complete"))
                or not isinstance(fact.get("signature_status"), str) or fact["signature_status"] not in {"normalized", "opaque"}
                or not isinstance(fact.get("signature"), str) or not re.fullmatch(r"[0-9a-f]{64}", fact["signature"])
                or not isinstance(fact.get("template_fingerprint"), str)
                or fact["template_fingerprint"] and not re.fullmatch(r"[0-9a-f]{64}", fact["template_fingerprint"])
                or fact["template"] != bool(fact["template_fingerprint"]) or not valid_parameter_facts(fact)):
            return None
        name = label[:-2]
        self.records.setdefault((source, name), []).append((node, fact, _anonymous_scope(node, fact, declaration_name=name)))
        return name

    def at(self, source_file, namespace, name, position):
        """Only preceding definitions are visible; unknown witnesses cannot lend a target."""
        if not isinstance(source_file, str):
            return [], True
        records = [(node, fact, scope) for node, fact, scope in self.records.get((source_file, name), ())
                   if fact["span"]["end_byte"] <= position]
        # Intervening anonymous roles distinguish anonymous::Public from the
        # ordinary ::Public even when their named display paths are identical.
        host = tuple(namespace.split("::")) if namespace else ()
        unknown = any(scope is None or scope[0] == host and not scope[1] for _, _, scope in records)
        values = [(node, fact) for node, fact, scope in records
                  if scope is not None and scope[0] == host and scope[1] and fact.get("role") == "definition"]
        declarations = [fact for _, fact, scope in records
                        if scope is not None and scope[0] == host and scope[1] and fact.get("role") == "declaration"]
        if declarations:
            # A known primitive same-entity declaration does not compete with
            # its already visible body. It lends no defaults, target or ID join.
            body = values[0][1] if len(values) == 1 else {}
            unknown |= any(value.get("conditional") or value.get("template")
                           or value.get("canonical_status") != "available" or body.get("canonical_status") != "available"
                           or value.get("canonical_parameters") != body.get("canonical_parameters")
                           or value.get("signature") != body.get("signature") for value in declarations)
        return values, unknown
