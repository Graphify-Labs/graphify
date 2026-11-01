"""Classify a named C++ member by its actual declarator binding.

The nearest pointer/reference/array/function binding to a name decides whether it
declares data or a method. Parentheses change that order, so a callback field is
not callable merely because its outer AST node is a function declarator. These
facts provide structural source locations, never Qt exposure or join authority.
"""
from __future__ import annotations

from graphify.extractors.base import _read_text


_NAMES = {"identifier", "field_identifier", "destructor_name", "operator_name"}
_BINDINGS = {
    "pointer_declarator", "reference_declarator",
    "array_declarator", "function_declarator",
}
_WRAPPERS = _BINDINGS | {
    "parenthesized_declarator", "init_declarator", "attributed_declarator",
}


def _declarator_shape(node, source):
    """Return one complete name and its nearest actual binding node.

    Parameters, initializers, type qualifiers and array bounds are not name
    candidates. A missing field on reference/parenthesized wrappers is handled
    by a sole declarator child, not by searching arbitrary descendants.
    """
    binding = None
    current = node
    # Follow one child of the immutable parser tree at a time. Constant state
    # handles deeply parenthesized valid declarations without a silent cutoff.
    while current is not None:
        if current.is_missing:
            return None
        kind = current.type
        if kind in _NAMES:
            name = _read_text(current, source)
            if not name:
                return None
            return name, binding
        if kind == "qualified_identifier":
            name = _read_text(current, source)
            return (name, binding) if name else None
        if kind not in _WRAPPERS:
            return None
        if kind in _BINDINGS:
            binding = current
        child = current.child_by_field_name("declarator")
        if child is None:
            children = [item for item in current.named_children
                        if item.type in _NAMES | _WRAPPERS | {"qualified_identifier"}]
            if len(children) != 1:
                return None
            child = children[0]
        current = child
    return None


def member_declarator(node, source):
    """Return ``(name, is_method)`` without confusing a return/callback wrapper."""
    shape = _declarator_shape(node, source)
    if shape is None:
        return None
    name, binding = shape
    return name, binding is not None and binding.type == "function_declarator"


def callable_declarator(node, source):
    """The nearest actual function owns its parameters, not an outer return type."""
    shape = _declarator_shape(node, source)
    return shape[1] if shape is not None and shape[1] is not None and shape[1].type == "function_declarator" else None


def is_destructor_prototype(node, source):
    """Recognize the typed-less declaration shape inside an accepted class.

    Constructor recovery keeps its existing signature/owner proof boundary.
    This helper cannot admit free prototypes or supply cross-file ownership.
    """
    if node.type != "declaration" or node.child_by_field_name("type") is not None:
        return False
    declarator = node.child_by_field_name("declarator")
    if declarator is None or declarator.type != "function_declarator":
        return False
    name = declarator.child_by_field_name("declarator")
    return name is not None and name.type == "destructor_name" and member_declarator(declarator, source) is not None


def declarator_metadata(node, kind):
    """Record bounded original AST coordinates without copying source text."""
    return {"cpp_declarator": {"contract_version": 1, "kind": kind, "span": {
        "start_byte": node.start_byte, "end_byte": node.end_byte,
        "start_row": node.start_point.row, "end_row": node.end_point.row,
        "start_column": node.start_point.column, "end_column": node.end_point.column,
    }}}
