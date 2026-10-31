"""Original declaration shapes for the bounded statically declared QObject API.

One pointer or lvalue reference is an API hop. Root objects additionally admit
values for dot access/address-of. This does not prove runtime conversion, alias
identity, const-correct invocation or allocation; CV stays in lexical transport.
"""
from __future__ import annotations

import re

_NAME = r"(?:::)?[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*"
_TYPE = re.compile(r"\s*(?:(?:const|volatile|struct|class)\s+)*(?P<name>" + _NAME
                   + r")(?:(?:\s+(?:const|volatile)\b)*)\s*(?P<shape>\*(?:\s*(?:const|volatile)\b)*(?:\s*)|&)?\s*")


def api_shape(spelling, *, allow_value=False):
    """Reject compound declarators before resolving a convenient named base class."""
    if not isinstance(spelling, str) or len(spelling.encode()) > 384:
        return None
    match = _TYPE.fullmatch(spelling)
    if not match:
        return None
    suffix = match["shape"] or ""
    kind = "pointer" if suffix.startswith("*") else "reference" if suffix == "&" else "value"
    return (match["name"], kind) if allow_value or kind != "value" else None


def _type_start(declaration):
    type_node = declaration.child_by_field_name("type")
    if type_node is None:
        return None
    return min([type_node.start_byte] + [node.start_byte for node in declaration.named_children
               if node.type == "type_qualifier" and node.start_byte < type_node.end_byte])


def return_spelling(unit, declaration, function):
    """The prefix includes original CV and every return pointer/reference token."""
    start = _type_start(declaration)
    return unit.source[start:function.start_byte].decode().strip() if start is not None else ""


def declared_spelling(unit, declaration, declarator, identifier):
    """Remove only the selected identifier; arrays and nested pointers stay visible."""
    start = _type_start(declaration)
    if start is None or identifier is None:
        return ""
    if declarator.type == "init_declarator":
        declarator = declarator.child_by_field_name("declarator")
        if declarator is None:
            return ""
    prefix = unit.source[start:declarator.start_byte]
    shape = unit.source[declarator.start_byte:identifier.start_byte] + unit.source[identifier.end_byte:declarator.end_byte]
    return (prefix + shape).decode().strip()


def declarator_identifier(node):
    """Find a declaration leaf without erasing its enclosing shape from transport."""
    while node is not None and node.type not in {"identifier", "field_identifier"}:
        node = node.child_by_field_name("declarator") or next((child for child in node.named_children
            if child.type in {"identifier", "field_identifier", "pointer_declarator", "reference_declarator",
                              "array_declarator", "parenthesized_declarator"}), None)
    return node
