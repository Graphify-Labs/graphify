"""Actual ordinary callable roles protect QtTest-looking identifier spellings.

An error-free function-declarator shape alone is insufficient: the bundled
grammar also accepts macro statements as impossible return-type-less members.
Typed declarations and exact lexical constructors/destructors retain ordinary
identity; no body/framework/type authority follows from the spelling alone.
"""
from __future__ import annotations

from graphify.extractors.cpp_declarators import callable_declarator, member_declarator


def ordinary_test_callable(node, source):
    parent = node.parent
    if (node.type != "function_declarator" or node.has_error or parent is None or parent.has_error
            or parent.type not in {"declaration", "field_declaration", "function_definition"}):
        return False
    roots = parent.children_by_field_name("declarator")
    if not any(callable_declarator(item, source) == node for item in roots):
        return False
    value_type = parent.child_by_field_name("type")
    if value_type is not None:
        return not value_type.is_missing and not value_type.has_error
    owner = parent.parent
    while owner is not None and owner.type not in {"class_specifier", "struct_specifier", "translation_unit", "function_definition"}:
        owner = owner.parent
    if owner is None or owner.type not in {"class_specifier", "struct_specifier"}:
        return False
    name = owner.child_by_field_name("name")
    shape = next((member_declarator(item, source) for item in roots if callable_declarator(item, source) == node), None)
    if name is None or shape is None or not shape[1]:
        return False
    class_name = source[name.start_byte:name.end_byte].decode()
    return shape[0] in {class_name, "~" + class_name}
