"""Source-local declaration identities for Qt loaders, providers and handles.

One index belongs to one accepted C++ syntax/mapping pair. Identities prove a
lexical declaration, not runtime object equality, aliases or pointer dataflow.
"""
from __future__ import annotations

import hashlib
import json
import re

from graphify.extractors.qt_cpp_facts import scope_owner
from graphify.extractors.qt_cpp_syntax import source_span, walk

_SCOPES = {"compound_statement", "for_statement", "for_range_loop", "if_statement",
           "switch_statement", "while_statement", "catch_clause", "lambda_expression"}
_CONDITIONS = {"if_statement", "switch_statement", "conditional_expression", "for_statement",
               "for_range_loop", "while_statement", "do_statement", "catch_clause",
               "lambda_expression", "preproc_if", "preproc_ifdef", "preproc_else"}
_DECLARATIONS = {"declaration", "parameter_declaration", "optional_parameter_declaration",
                 "variadic_parameter_declaration", "for_range_loop"}


def _identifier(node):
    """Unwrap declarators only; fields, factories and structured bindings stay opaque."""
    while node is not None and node.type in {"pointer_declarator", "reference_declarator",
                                            "parenthesized_declarator", "init_declarator"}:
        node = node.child_by_field_name("declarator") or next(iter(node.named_children), None)
    return node if node is not None and node.type == "identifier" else None


def _ancestors(node):
    while node is not None:
        yield node
        node = node.parent


def _inside(node, position):
    return node.start_byte <= position < node.end_byte


def _answer(status, reason="", identity="", declaration_span=None, scope_span=None):
    return {"declaration_id": identity, "status": status, "reason": reason,
            "declaration_span": declaration_span or {}, "scope_span": scope_span or {}}


class CppDeclarationIdentity:
    """Bounded AST index reused by every reference in a single extraction pass."""

    def __init__(self, unit, mapping):
        self.unit, self.mapping = unit, mapping
        self.declarations, self.writes, self.conditions = {}, [], []
        for syntax in walk(unit.tree):
            if syntax.type in _CONDITIONS:
                self.conditions.append(syntax)
            if syntax.type in {"assignment_expression", "update_expression"}:
                left = syntax.child_by_field_name("left") or syntax.child_by_field_name("argument")
                if left is not None and left.type == "identifier":
                    self.writes.append((unit.text(left), syntax))
            if syntax.type not in _DECLARATIONS:
                continue
            for index, child in enumerate(syntax.named_children):
                if syntax.field_name_for_named_child(index) != "declarator":
                    continue
                name = _identifier(child)
                if name is None:
                    continue
                owner = mapping.owner_at(name.start_byte)
                if not owner or owner.get("body") is None:
                    continue
                scope = next((parent for parent in _ancestors(syntax.parent)
                              if parent.type in _SCOPES), None)
                if syntax.type == "for_range_loop":
                    scope = syntax
                # Function parameters and top-level locals share the function
                # body's scope; illegal same-scope duplicates remain ambiguous.
                scope = scope or owner["body"]
                if not (owner["span"]["start_byte"] <= scope.start_byte
                        and scope.end_byte <= owner["span"]["end_byte"]):
                    scope = owner["body"]
                record = {"name": unit.text(name), "name_end": name.end_byte, "syntax": child,
                          "scope": scope, "owner": owner,
                          "conditional": any(parent.type in _CONDITIONS for parent in _ancestors(syntax)),
                          "depth": sum(1 for _ in _ancestors(scope))}
                self.declarations.setdefault(record["name"], []).append(record)

    def _select(self, name, position, owner):
        candidates = [record for record in self.declarations.get(name, [])
                      if record["owner"] is owner and record["name_end"] <= position
                      and _inside(record["scope"], position)]
        if not candidates:
            return None, "declaration_unavailable"
        depth = max(record["depth"] for record in candidates)
        nearest = [record for record in candidates if record["depth"] == depth]
        return (nearest[0], "") if len(nearest) == 1 else (None, "declaration_ambiguous")

    def _identity(self, name, owner, declaration, scope):
        key = [self.unit.relative_file, owner.get("qualified_name"), owner.get("signature"),
               owner["span"]["start_byte"], owner["span"]["end_byte"], name,
               declaration.start_byte, declaration.end_byte, scope.start_byte, scope.end_byte]
        return hashlib.sha256(json.dumps(key, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()

    def type_binding(self, name, position):
        """Original declaration spelling owns type authority, before use-site aliases.

        A normalized variable type loses an explicit global qualifier. Resolve
        its source binding instead of treating that display spelling as a new
        type expression at the later call site.
        """
        # Runtime lifetime/assignment uncertainty is reported separately by
        # resolve(); it must not erase the observed SDK operation itself.
        if name == "this":
            return "", position
        owner = self.mapping.owner_at(position)
        record, _ = self._select(name, position, owner)
        if record is None:
            return "", position
        declaration = record["syntax"].parent
        if declaration is None or declaration.type not in _DECLARATIONS:
            return "", position
        return self.unit.field(declaration, "type"), declaration.start_byte

    def declared_type_binding(self, name, position):
        """API roots retain original declarator shape without changing SDK lookup."""
        from graphify.extractors.qt_cpp_api_shape import declared_spelling
        owner = self.mapping.owner_at(position)
        record, _ = self._select(name, position, owner)
        if record is None:
            return "", position
        declarator = record["syntax"]
        declaration = declarator.parent
        if declaration is None or declaration.type not in _DECLARATIONS:
            return "", position
        return declared_spelling(self.unit, declaration, declarator, _identifier(declarator)), declaration.start_byte

    def resolve(self, name, position):
        """Return a portable 64-hex ID or explicit uncertainty, never a name fallback."""
        if not isinstance(name, str) or not re.fullmatch(r"this|[A-Za-z_]\w*", name):
            return _answer("unsupported", "reference_expression_unsupported")
        owner = self.mapping.owner_at(position)
        if not owner or owner.get("body") is None or not _inside(owner["body"], position):
            return _answer("unavailable", "source_function_unavailable")
        if any(_inside(condition, position) for condition in self.conditions):
            return _answer("dynamic", "conditional_declaration_use")
        if name == "this":
            if not owner.get("class_id") or owner.get("native_owner_unavailable"):
                return _answer("unavailable", "this_class_unavailable")
            declaration, scope = owner["syntax"], owner["body"]
            return _answer("resolved", identity=self._identity(name, owner, declaration, scope),
                           declaration_span=owner["span"],
                           scope_span=source_span(self.unit.source, scope.start_byte, scope.end_byte))
        record, reason = self._select(name, position, owner)
        if record is None:
            return _answer("ambiguous" if reason == "declaration_ambiguous" else "unavailable", reason)
        if record["conditional"]:
            return _answer("dynamic", "conditional_declaration")
        # A write belongs to the declaration visible at that write, not every
        # variable with the same spelling elsewhere in this function.
        for written, syntax in self.writes:
            if written == name and record["name_end"] <= syntax.start_byte < position:
                selected, _ = self._select(name, syntax.start_byte, owner)
                if selected is record:
                    return _answer("dynamic", "reassigned_declaration")
        declaration, scope = record["syntax"], record["scope"]
        return _answer("resolved", identity=self._identity(name, owner, declaration, scope),
                       declaration_span=source_span(self.unit.source, declaration.start_byte, declaration.end_byte),
                       scope_span=source_span(self.unit.source, scope.start_byte, scope.end_byte))


def reference_identity(unit, mapping, name, position):
    """Convenience seam; collectors should reuse CppDeclarationIdentity per file."""
    return CppDeclarationIdentity(unit, mapping).resolve(name, position)


def source_reference_key(metadata, role="receiver"):
    """Accepted fact transport must carry an identity; legacy names cannot join."""
    if role not in {"receiver", "assigned", "engine", "provider", "sender"}:
        return None
    identity, owner = metadata.get(role + "_declaration_id"), scope_owner(metadata)
    if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{64}", identity):
        return None
    return (owner, identity) if isinstance(owner, str) and owner else None
