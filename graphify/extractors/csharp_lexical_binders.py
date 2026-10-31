"""Source-only C# data binders for rejecting guessed callable targets.

Names come from parser declaration fields and pattern roles, never initializer
identifiers. The caller owns lexical scopes and all mutable per-file indexes.
"""
from __future__ import annotations

from graphify.extractors.base import _read_text


def _names(node, source):
    if node is None:
        return []
    if node.type == "identifier":
        name = _read_text(node, source)
        return [] if name == "_" and node.parent is not None and node.parent.type in {
            "tuple_pattern", "declaration_pattern", "single_variable_designation"} else [name]
    if node.type in {"tuple_pattern", "declaration_expression", "declaration_pattern", "single_variable_designation"}:
        names = node.children_by_field_name("name")
        if names:
            return [name for child in names for name in _names(child, source)]
        return [name for child in node.named_children if child.type in {
            "identifier", "tuple_pattern", "declaration_expression", "single_variable_designation"
        } for name in _names(child, source)]
    return []


def binding_names(node, source):
    """Return only actual syntactic bindings; no graph-variable facts are emitted."""
    if node.type == "implicit_parameter":
        name = _read_text(node, source)
        return [name] if name.removeprefix("@").isidentifier() else []
    if node.type in {"parameter", "catch_declaration", "implicit_parameter"}:
        return _names(node.child_by_field_name("name") or node, source)
    if node.type == "variable_declarator":
        name = node.child_by_field_name("name")
        return _names(name, source) if name is not None else [name for child in node.named_children
            if child.type == "tuple_pattern" for name in _names(child, source)]
    if node.type == "foreach_statement":
        return _names(node.child_by_field_name("left"), source)
    if node.type in {"declaration_pattern", "declaration_expression"}:
        return _names(node, source)
    return []
