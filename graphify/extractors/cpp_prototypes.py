"""Source-only free/namespace function prototypes with independent identity.

Prototype evidence is retained after the generic body's call pass. It does not
authorize a guessed definition, Qt provider or overload target. Exact named scope
and signature govern IDs; anonymous scopes retain opaque source identity.
"""
from __future__ import annotations

import base64
import hashlib

from graphify.extractors.base import _file_stem, _make_id, _read_text
from graphify.extractors.cpp_constructors import _signature, _span, _walk
from graphify.extractors.cpp_declarators import callable_declarator, member_declarator
from graphify.extractors.cpp_function_signature import parameter_facts
from graphify.extractors.cpp_functions import bounded_scope, namespace_scope, occurrence_suffix
from graphify.extractors.cpp_include_guards import IncludeGuardIndex
from graphify.extractors.cpp_anonymous_namespaces import namespace_witness


def _scope(node, source):
    parts, parent = [], node.parent
    template = ""
    while parent is not None:
        if parent.type in {"function_definition", "lambda_expression", "class_specifier", "struct_specifier", "union_specifier"}:
            return None
        if parent.type == "namespace_definition":
            name = parent.child_by_field_name("name")
            parts.append(_read_text(name, source) if name is not None else {"anonymous": parent.start_byte})
        elif parent.type == "template_declaration":
            parameters = parent.child_by_field_name("parameters")
            if parameters is not None:
                template = hashlib.sha256(source[parameters.start_byte:parameters.end_byte]).hexdigest()
        parent = parent.parent
    return list(reversed(parts)), template


def augment_cpp_prototypes(root, source, nodes, edges, path):
    """Use actual declaration ASTs; never reparse, execute or invent a body join."""
    seen = {node["id"] for node in nodes}
    guards = IncludeGuardIndex(root)
    file_id, stem = _make_id(str(path)), _file_stem(path)
    for declaration in _walk(root):
        if declaration.type != "declaration" or declaration.has_error or declaration.child_by_field_name("type") is None:
            continue
        scope = _scope(declaration, source)
        if scope is None:
            continue
        parts, template = scope
        _, proof, _ = namespace_scope(declaration, source)
        ancestor, conditional = declaration.parent, False
        while ancestor is not None:
            conditional |= ancestor.type.startswith("preproc_") and not guards.accepts(ancestor)
            ancestor = ancestor.parent
        scope_key, scope_fingerprint = bounded_scope(parts)
        named = all(isinstance(part, str) for part in parts)
        for declarator in declaration.children_by_field_name("declarator"):
            shape = member_declarator(declarator, source)
            if shape is None or not shape[1]:
                continue
            name, _ = shape
            current = callable_declarator(declarator, source)
            if current is None:
                continue
            signature = _signature(current, source)
            status = "normalized" if signature else "opaque"
            if not signature:
                signature = hashlib.sha256(source[declarator.start_byte:declarator.end_byte]).hexdigest()
            digest = hashlib.sha256("\0".join((scope_key, name, signature, template)).encode()).hexdigest()
            identity = _make_id(stem, "cppproto", digest, name[:32])
            if identity in seen:
                identity += occurrence_suffix(_span(declaration), "declaration")
                if identity in seen:
                    continue
            seen.add(identity)
            oversize = named and sum(len(part.encode()) + 2 for part in [*parts, name]) > 384
            qualified = "::".join([*parts, name]) if named and not oversize else ""
            qualified_status = "available" if named else "anonymous"
            if oversize:
                # Generic metadata bounds cannot truncate a lookup transport
                # into a different name. The exact identity hash remains valid.
                qualified, qualified_status = "", "oversize"
            metadata = {"cpp_prototype": {
                "contract_version": 1, "role": "declaration", "signature": signature,
                "signature_status": status, "scope_status": "named" if named else "anonymous",
                "scope_fingerprint": scope_fingerprint,
                "namespace_b64": base64.b64encode("::".join(parts).encode()).decode() if named and not oversize else "",
                "namespace_proof": proof[:50], "scope_complete": len(proof) <= 50 and not oversize,
                "template": bool(template), "template_fingerprint": template, "conditional": conditional,
                "static": any(child.type == "storage_class_specifier" and _read_text(child, source) == "static" for child in declaration.children),
                "qualified_name_status": qualified_status,
                "qualified_name_b64": base64.b64encode(qualified.encode()).decode(),
                "span": _span(declaration),
                **parameter_facts(current, source),
            }}
            if not named:
                metadata["cpp_prototype"]["anonymous_scope_proof"] = namespace_witness(declaration, source)
            line = declaration.start_point.row + 1
            # Mark only this actual declaration; a prototype stays independent
            # of definitions and gains no body/native resolution authority.
            nodes.append({"id": identity, "label": f"{name}()", "file_type": "code",
                          "source_file": str(path), "source_location": f"L{line}",
                          "_callable": True, "_origin": "ast", "metadata": metadata})
            edges.append({"source": file_id, "target": identity, "relation": "contains",
                          "confidence": "EXTRACTED", "source_file": str(path),
                          "source_location": f"L{line}", "weight": 1.0})
