"""Source-owned C++ enclosing classes are lookup scopes, never namespaces.

The producer retains bounded AST scope roles without changing lexical IDs. The
run-local reader requires every promised class and actual containment edge; a
missing parent cannot silently become a namespace. It reads no corpus files and
creates no source relationship, native endpoint, or mutable ownership field.
"""
from __future__ import annotations

from collections import Counter

from graphify.extractors.base import _read_text
from graphify.extractors.cpp_class_proof import class_fact
from graphify.extractors.cpp_constructors import _encoded, _identifier, _span
from graphify.extractors.cpp_functions import decoded, valid_span


def class_scope_proof(syntax, source, guards):
    """Record original namespace/class roles while the real parser tree is owned."""
    scopes, complete, conditional, parent = [], True, False, syntax.parent
    while parent is not None:
        if parent.type in {"class_specifier", "struct_specifier", "namespace_definition"}:
            name_node = parent.child_by_field_name("name")
            name = _read_text(name_node, source) if name_node is not None else ""
            kind = "namespace" if parent.type == "namespace_definition" else "class"
            complete &= _identifier(name) and (kind == "namespace" or name.isidentifier())
            scopes.append({"kind": kind, "name_b64": _encoded(name), "span": _span(parent)})
        elif parent.type in {"function_definition", "lambda_expression", "union_specifier", "ERROR", "template_declaration"}:
            complete = False
        if parent.type.startswith("preproc_") and not guards.accepts(parent):
            conditional = True
        parent = parent.parent
    scopes.reverse()
    if len(scopes) > 50:
        complete, scopes = False, []
    return {"contract_version": 1, "complete": bool(complete), "conditional": conditional, "scopes": scopes}


def _contains(outer, inner):
    """All six original coordinates agree on strict declaration containment."""
    return (valid_span(outer) and valid_span(inner)
            and outer["start_byte"] < inner["start_byte"] < inner["end_byte"] < outer["end_byte"]
            and (outer["start_row"], outer["start_column"]) < (inner["start_row"], inner["start_column"])
            and (inner["end_row"], inner["end_column"]) < (outer["end_row"], outer["end_column"]))


def _witness(fact):
    value = fact.get("lexical_scope_proof")
    if (not isinstance(value, dict) or type(value.get("contract_version")) is not int
            or value["contract_version"] != 1 or value.get("complete") is not True
            or value.get("conditional") is not False or not isinstance(value.get("scopes"), list)
            or len(value["scopes"]) > 50):
        return None
    return value["scopes"]


class CppClassScopes:
    """A read-only entry cohort owns namespace and enclosing-class lookup proof."""

    def __init__(self, nodes, edges):
        self.counts = Counter(node.get("id") for node in nodes)
        self.nodes = tuple(node for node in nodes if node.get("_callable_class") is True)
        self.by_id, self.by_file, self.parents, self.by_name, self.cached = {}, {}, {}, {}, {}
        for node in self.nodes:
            self.by_id.setdefault(node.get("id"), []).append(node)
            source_file = node.get("source_file")
            if type(source_file) is not str or not source_file:
                continue  # A damaged promised parent remains missing, never a namespace.
            self.by_file.setdefault(source_file, []).append(node)
            fact = class_fact(node)
            if fact:
                self.by_name.setdefault((node.get("source_file"), decoded(fact["qualified_name_b64"])), []).append(node)
        for edge in edges:
            parent = self.by_id.get(edge.get("source"), ())
            if edge.get("relation") == "contains" and any(node.get("_callable_class") is True for node in parent):
                self.parents.setdefault(edge.get("target"), []).append(edge)

    def _accepted(self, node):
        if type(node.get("source_file")) is not str or not node["source_file"]:
            return {}
        fact = class_fact(node)
        return (fact if fact and fact["is_definition"] and not fact["ambiguous"]
                and self.counts[node.get("id")] == 1
                and str(node.get("label", "")).isidentifier() else {})

    def _parent_edge(self, parent, child, fact):
        expected = (parent["id"], child["id"], "EXTRACTED", child.get("source_file"),
                    f"L{fact['span']['start_row'] + 1}")
        edges = self.parents.get(child["id"], ())
        keys = ("source", "target", "confidence", "source_file", "source_location")
        if any(any(type(edge.get(key)) is not str for key in keys) for edge in edges):
            return False
        claims = {(edge.get("source"), edge.get("target"), edge.get("confidence"),
                   edge.get("source_file"), edge.get("source_location"))
                  for edge in edges}
        return parent.get("source_file") == child.get("source_file") and claims == {expected}

    def scope(self, identity):
        """Return (namespace, outer-to-inner class IDs), or unavailable authority."""
        if identity not in self.cached:
            self.cached[identity] = self._scope(identity)
        return self.cached[identity]

    def _scope(self, identity):
        nodes = self.by_id.get(identity, ())
        if len(nodes) != 1:
            return None
        node, = nodes
        fact = self._accepted(node)
        scopes = _witness(fact)
        if scopes is None:
            return None
        parts, namespace, classes, outer_span = [], [], [], None
        for position, scope in enumerate(scopes):
            if not isinstance(scope, dict) or type(scope.get("kind")) is not str or scope["kind"] not in {"class", "namespace"}:
                return None
            name, span = decoded(scope.get("name_b64")), scope.get("span")
            if (not name or not _identifier(name) or not valid_span(span)
                    or outer_span is not None and not _contains(outer_span, span)
                    or not _contains(span, fact["span"])):
                return None
            if scope["kind"] == "namespace":
                if classes:
                    return None  # A namespace declaration cannot be inside a class body.
                namespace.append(name)
            else:
                if not name.isidentifier():
                    return None
                qualified = "::".join([*parts, name])
                candidates = self.by_name.get((node.get("source_file"), qualified), ())
                if len(candidates) != 1:
                    return None
                parent, = candidates
                proof = self._accepted(parent)
                if (not proof or proof["span"] != span or _witness(proof) != scopes[:position]
                        or decoded(proof["scope_b64"]) != "::".join(parts)):
                    return None
                classes.append(parent)
            parts.append(name)
            outer_span = span
        if decoded(fact["scope_b64"]) != "::".join(parts):
            return None
        chain = [*classes, node]
        if any(not self._parent_edge(parent, child, self._accepted(child))
               for parent, child in zip(chain, chain[1:])):
            return None
        if not classes and self.parents.get(identity):
            return None
        # A contradicted namespace role or omitted source class cannot override
        # an actual same-file containing class, even when the transport is valid.
        actual = set()
        for candidate in self.by_file.get(node.get("source_file"), ()):
            metadata = candidate.get("metadata")
            raw = metadata.get("cpp_class") if isinstance(metadata, dict) else None
            if isinstance(raw, dict) and _contains(raw.get("span"), fact["span"]):
                actual.add(candidate.get("id"))
        if actual != {parent["id"] for parent in classes}:
            return None
        return "::".join(namespace), tuple(parent["id"] for parent in chain)
