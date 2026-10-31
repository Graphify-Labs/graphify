"""Source-only C# data binders for rejecting guessed callable targets.

Names come from parser declaration fields and pattern roles, never initializer
identifiers. The caller owns lexical scopes and all mutable per-file indexes.
"""
from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True)
class ReceiverBinding:
    """Source eligibility only; the existing receiver collector owns all types."""

    name: str
    owner: int
    scope: tuple[int, int]
    type_windows: tuple[tuple[int, int], ...]
    declared: int
    supported: bool
    conditional: bool


def receiver_bindings(node, source, owner, scope, *, conditional=False):
    """Retain actual parameter/local scopes without inventing variable nodes.

    Other data forms still claim their spelling as rejection-only shadows. A
    complete, preceding parameter/local declaration may borrow a type solely
    from the existing collector's matching source window, never an initializer
    name or an unrelated same-spelled declaration.
    """
    names = binding_names(node, source)
    if not names or scope is None:
        return ()
    supported = node.type == "parameter"
    if supported:
        declaration = node.parent
        if declaration is not None and declaration.type == "parameter_list":
            declaration = declaration.parent
        scope = (declaration if declaration is not None and declaration.type == "lambda_expression"
                 else owner.child_by_field_name("body") or owner)
    elif node.type == "variable_declarator":
        parent = node.parent
        supported = (node.child_by_field_name("name") is not None
                     and parent is not None and parent.type == "variable_declaration"
                     and parent.parent is not None and parent.parent.type == "local_declaration_statement")
    window = scope.start_byte, scope.end_byte
    windows = ((window, (owner.start_byte, owner.end_byte))
               if node.type == "parameter" and scope.type != "lambda_expression" else (window,))
    return tuple(ReceiverBinding(name.removeprefix("@"), owner.id, window, windows,
                                 node.end_byte, supported and not node.has_error, conditional)
                 for name in names)
