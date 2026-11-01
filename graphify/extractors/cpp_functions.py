"""Source-owned free C++ definitions before generic name deduplication.

Ordinary unique global IDs remain compatible. Namespace, overload and spelling
collisions use exact scope/signature identity. These source facts never merge a
prototype into a body or lend a QObject/class role to a namespace function.
"""
from __future__ import annotations

import base64
from collections import defaultdict
import hashlib
import json
import re

from graphify.extractors.base import _make_id, _read_text
from graphify.extractors.cpp_constructors import _signature, _span, _walk
from graphify.extractors.cpp_declarators import callable_declarator, member_declarator
from graphify.extractors.cpp_function_signature import parameter_facts, valid_parameter_facts
from graphify.extractors.cpp_include_guards import IncludeGuardIndex
from graphify.extractors.cpp_anonymous_namespaces import namespace_witness
from graphify.extractors.cpp_source_views import span_contains, valid_span


def encoded(value):
    raw = value.encode("utf-8")
    return base64.b64encode(raw).decode("ascii") if len(raw) <= 384 else ""


def decoded(value):
    if not isinstance(value, str) or len(value) > 512:
        return None
    try:
        return base64.b64decode(value, validate=True).decode("utf-8")
    except (ValueError, UnicodeError):
        return None


def bounded_scope(parts):
    """Large lexical nesting keeps exact identity without copying growing keys."""
    digest, chunks, size = hashlib.sha256(), [], 0
    for chunk in json.JSONEncoder(ensure_ascii=False, separators=(",", ":")).iterencode(parts):
        raw = chunk.encode()
        digest.update(raw)
        size += len(raw)
        if size <= 384:
            chunks.append(chunk)
    return ("".join(chunks) if size <= 384 else "oversize:" + digest.hexdigest()), digest.hexdigest()


def occurrence_suffix(span, role):
    """A second source occurrence needs identity distinct from its shared signature."""
    digest = hashlib.sha256(f"{span['start_byte']}:{span['end_byte']}".encode()).hexdigest()
    return "::" + role + "-occurrence::" + digest


def namespace_scope(node, source):
    """Original named namespaces govern scope; anonymous namespaces remain opaque."""
    parts, proof, parent = [], [], node.parent
    member = False
    while parent is not None:
        if parent.type in {"class_specifier", "struct_specifier", "union_specifier"}:
            member = True
        elif parent.type == "ERROR":
            member = True  # An unknown enclosing declaration cannot prove a free function.
        elif parent.type == "namespace_definition":
            name = parent.child_by_field_name("name")
            if name is None:
                parts.append({"anonymous": parent.start_byte})
            else:
                text = _read_text(name, source)
                parts.append(text)
                proof.append({"name_b64": encoded(text), "span": _span(parent)})
        parent = parent.parent
    return list(reversed(parts)), list(reversed(proof)), member


def scope_proof_parts(fact):
    """Validate bounded lexical namespace witnesses against their owned declaration."""
    proof = fact.get("namespace_proof")
    if (type(proof) is not list or len(proof) > 50 or type(fact.get("scope_complete")) is not bool
            or not valid_span(fact.get("span"))):
        return None
    parts, enclosing = [], None
    for witness in proof:
        if not isinstance(witness, dict) or not valid_span(witness.get("span")):
            return None
        spelling, span = decoded(witness.get("name_b64")), witness["span"]
        if not spelling or not span_contains(span, fact["span"]) or enclosing and not span_contains(enclosing, span):
            return None
        parts.append(spelling)
        enclosing = span
    return parts


def free_definition_fact(node):
    """Validate source/role/transport agreement; this supplies no body-join authority."""
    metadata = node.get("metadata", {})
    fact = metadata.get("cpp_function") if isinstance(metadata, dict) else None
    if (not isinstance(fact, dict) or type(fact.get("contract_version")) is not int or fact["contract_version"] != 1
            or fact.get("role") != "definition" or fact.get("function_kind") != "free"
            or node.get("_callable") is not True or node.get("_callable_class") is True
            or not isinstance(node.get("source_file"), str) or not node["source_file"] or not valid_span(fact.get("span"))
            or node.get("source_location") != f"L{fact['span']['start_row'] + 1}"):
        return {}
    raw_name, name = decoded(fact.get("raw_name_b64")), decoded(fact.get("name_b64"))
    if (not raw_name or not name or node.get("label") != raw_name + "()"
            or raw_name.rsplit("::", 1)[-1] != name
            or type(fact.get("ambiguous")) is not bool or type(fact.get("template")) is not bool
            or type(fact.get("static")) is not bool or type(fact.get("conditional")) is not bool
            or type(fact.get("signature_status")) is not str or fact["signature_status"] not in {"normalized", "opaque"}
            or not re.fullmatch(r"[0-9a-f]{64}", str(fact.get("signature", "")))
            or not re.fullmatch(r"[0-9a-f]{64}", str(fact.get("scope_fingerprint", "")))):
        return {}
    parts = scope_proof_parts(fact)
    if parts is None:
        return {}
    if fact.get("namespace_status") == "available":
        namespace, qualified = decoded(fact.get("namespace_b64")), decoded(fact.get("qualified_name_b64"))
        expected = "::".join(filter(None, (namespace, name)))
        if namespace is None or qualified != expected:
            return {}
        if "::" in raw_name:
            qualifier = raw_name.rsplit("::", 1)[0].removeprefix("::")
            if qualifier != namespace:
                return {}
            parts = [qualifier] if qualifier else []
        elif "::".join(parts) != namespace:
            return {}
        scope_key = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
        if hashlib.sha256(scope_key.encode()).hexdigest() != fact["scope_fingerprint"]:
            return {}
        # Scope witnesses and the producer's role-specific ID must agree. The
        # hash is only an identity check, never parameter/type equivalence.
        digest = hashlib.sha256("\0".join((scope_key, name, fact["signature"])).encode()).hexdigest()
        suffix = _make_id("cppfn", digest, name[:32])
        identity = node.get("id", "")
        occurrence = occurrence_suffix(fact["span"], "definition")
        if isinstance(identity, str) and "::definition-occurrence::" in identity:
            if not identity.endswith(occurrence):
                return {}
            identity = identity[:-len(occurrence)]
        if not isinstance(identity, str) or not (identity.endswith("_" + suffix)
                or not parts and (identity.endswith("_" + _make_id(name))
                                  or identity.endswith("::free-definition::" + digest))):
            return {}
    elif type(fact.get("namespace_status")) is not str or fact["namespace_status"] not in {"anonymous", "oversize"}:
        return {}
    if not valid_parameter_facts(fact):
        return {}
    return fact


class CppFunctions:
    """One immutable syntax index plus actual producer-allocated IDs for this file."""

    def __init__(self, root, source, stem, *, alias_names=None, reserved_ids=()):
        self.root, self.source, self.stem = root, source, stem
        self.records, self.callers = {}, {}
        guards = IncludeGuardIndex(root)
        namespaces, reserved = set(), set(reserved_ids)
        for node in _walk(root):
            if alias_names is not None and node.type in {"alias_declaration", "type_definition"}:
                reserved.update(_make_id(stem, name) for name in alias_names(node, source))
            if node.type == "enum_specifier" and not namespace_scope(node, source)[2]:
                declared = node.child_by_field_name("name")
                if declared is not None:
                    reserved.add(_make_id(stem, _read_text(declared, source)))
            if node.type == "namespace_definition" and node.child_by_field_name("name") is not None:
                parts, _, member = namespace_scope(node, source)
                if not member and all(isinstance(part, str) for part in parts):
                    names = [*parts, _read_text(node.child_by_field_name("name"), source)]
                    if sum(len(part.encode()) + 2 for part in names) <= 384:
                        namespaces.add("::".join(names))
        for node in _walk(root):
            if node.type != "function_definition" or node.has_error:
                continue
            declarator = node.child_by_field_name("declarator")
            shape = member_declarator(declarator, source) if declarator else None
            function = callable_declarator(declarator, source) if declarator else None
            if shape is None or not shape[1] or function is None:
                continue
            parts, proof, member = namespace_scope(node, source)
            raw_name, _ = shape
            name = raw_name.rsplit("::", 1)[-1]
            if "::" in raw_name:
                qualifier = raw_name.rsplit("::", 1)[0].removeprefix("::")
                if qualifier not in namespaces:
                    continue  # Existing class/member qualification retains its owner.
                parts = [qualifier] if qualifier else []
            if member:
                continue
            params = function.child_by_field_name("parameters")
            if params is None:
                continue
            values = [child for child in params.named_children if "parameter_declaration" in child.type]
            signature = _signature(function, source)
            status = "normalized" if signature else "opaque"
            if not signature:
                signature = hashlib.sha256(source[params.start_byte:params.end_byte]).hexdigest()
            parent, template, conditional = node.parent, False, False
            while parent is not None:
                template |= parent.type == "template_declaration"
                conditional |= parent.type.startswith("preproc_") and not guards.accepts(parent)
                parent = parent.parent
            template |= any(value.child_by_field_name("type") is not None
                            and value.child_by_field_name("type").type == "placeholder_type_specifier" for value in values)
            scope_key, scope_fingerprint = bounded_scope(parts)
            named = all(isinstance(part, str) for part in parts)
            scope_oversize = named and sum(len(part.encode()) + 2 for part in parts) > 384
            namespace = "::".join(parts) if named and not scope_oversize else ""
            record = {"syntax": node, "name": name, "raw_name": raw_name, "parts": parts, "namespace": namespace,
                      "scope_key": scope_key, "scope_fingerprint": scope_fingerprint, "scope_oversize": scope_oversize,
                      "scope_proof": proof[:50], "scope_proof_complete": len(proof) <= 50, "signature": signature, "signature_status": status,
                      "template": template, "conditional": conditional,
                      "static": any(child.type == "storage_class_specifier" and _read_text(child, source) == "static" for child in node.children)}
            record.update(parameter_facts(function, source))
            # Anonymous lookup needs original role/range evidence, not a digest
            # or a later source reread after the producer has released its AST.
            if not named:
                record["anonymous_scope_proof"] = namespace_witness(node, source)
            self.records[node.id] = record
        plain = defaultdict(list)
        exact = defaultdict(list)
        for record in self.records.values():
            if not record["parts"]:
                plain[_make_id(stem, record["name"])].append(record)
            exact[(record["scope_key"], record["name"], record["signature"])].append(record)
        for group in exact.values():
            for position, record in enumerate(group):
                record["occurrence"] = position
        collision_counts = {normal: len({(entry["name"], entry["signature"]) for entry in group}) for normal, group in plain.items()}
        for record in self.records.values():
            normal = _make_id(stem, record["name"])
            digest = hashlib.sha256("\0".join((record["scope_key"], record["name"], record["signature"])).encode()).hexdigest()
            record["id"] = (_make_id(stem, "cppfn", digest, record["name"][:32])
                            if record["parts"] or collision_counts.get(normal, 0) > 1 else normal)
            if record["id"] in reserved:
                record["id"] += "::free-definition::" + digest
            if record["occurrence"]:
                record["id"] += occurrence_suffix(_span(record["syntax"]), "definition")
            record["ambiguous"] = len(exact[(record["scope_key"], record["name"], record["signature"])]) > 1

    def identity(self, node):
        record = self.records.get(node.id)
        return record["id"] if record else None

    def bind(self, node, identity):
        self.callers[node.id] = (node, identity)
        if node.id in self.records:
            self.records[node.id]["actual_id"] = identity

    def annotate(self, nodes):
        by_id = {node["id"]: node for node in nodes}
        for record in self.records.values():
            node = by_id.get(record.get("actual_id"))
            if node is None or "cpp_function" in node.get("metadata", {}):
                continue
            namespace = record["namespace"]
            status = "available" if all(isinstance(part, str) for part in record["parts"]) else "anonymous"
            if record["scope_oversize"]:
                status = "oversize"
            qualified = "::".join(filter(None, (namespace, record["name"])))
            if not encoded(namespace) and namespace or not encoded(qualified):
                status = "oversize"
            fact = {key: record[key] for key in ("signature", "signature_status", "min_args", "max_args", "template", "static", "ambiguous", "conditional",
                                                "canonical_parameters", "canonical_status", "arity_status", "arity_reason",
                                                "erased_default_parameters", "ast_required_args") if key in record}
            fact.update(contract_version=1, role="definition", function_kind="free", raw_name_b64=encoded(record["raw_name"]),
                        name_b64=encoded(record["name"]), namespace_b64=encoded(namespace) if status == "available" else "",
                        qualified_name_b64=encoded(qualified) if status == "available" else "", namespace_status=status,
                        scope_fingerprint=record["scope_fingerprint"],
                        namespace_proof=record["scope_proof"], scope_complete=record["scope_proof_complete"] and not record["scope_oversize"],
                        span=_span(record["syntax"]))
            # Direct graph assembly must retain this actual AST declaration,
            # independently of the facade's later extraction-tier stamp.
            node["_origin"] = "ast"
            node.setdefault("metadata", {})["cpp_function"] = fact
            if "anonymous_scope_proof" in record:
                fact["anonymous_scope_proof"] = record["anonymous_scope_proof"]
