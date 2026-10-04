"""Declaration-position API type facts for factory results and QObject properties.

These facts establish declared C++ APIs, never allocation or runtime alias identity.
Only admitted canonical complete classes can own an API endpoint.
"""
from __future__ import annotations

from graphify.extractors.qt_cpp_mapping import _name, _roles
from graphify.extractors.qt_cpp_api_shape import api_shape, declared_spelling, declarator_identifier, return_spelling
from graphify.extractors.qt_cpp_registration import conditional_offset
from graphify.extractors.qt_cpp_syntax import walk, source_span


def api_type_fields(types, raw_type, position, *, conditional=False):
    """Resolve original declaration spelling before any later lexical alias."""
    shape = api_shape(raw_type)
    ids, reason = types.resolve_class(shape[0], position) if shape else ([], "api_type_shape_unsupported")
    resolved = len(ids) == 1 and not reason and not conditional
    return {"api_type_target_id": ids[0] if resolved else "",
            "api_type_status": "resolved" if resolved else "dynamic" if conditional else "unsupported" if not shape else "unavailable",
            "api_type_reason": "conditional_api_type" if conditional else reason,
            "api_type_spelling": raw_type, "api_type_position": position}


def return_fields(unit, record, types):
    """Pointer/reference return syntax belongs to ancestors of the callable AST."""
    declaration = record["syntax"]
    declarators = [node for node in walk(declaration) if node.type == "function_declarator"]
    own = [node for node in declarators if _name(unit, node.child_by_field_name("declarator"))
           .split("::")[-1] == record["name"]]
    node = own[0].parent if len(own) == 1 else None
    while node is not None and node != declaration:
        if node.type not in {"pointer_declarator", "reference_declarator"}:
            return {"api_type_status": "unsupported", "api_type_reason": "return_declarator_unsupported"}
        node = node.parent
    raw = return_spelling(unit, declaration, own[0]) if len(own) == 1 else ""
    return api_type_fields(types, raw, declaration.start_byte,
                           conditional=conditional_offset(unit, declaration.start_byte))


def add_api_fields(mapping, facts, class_record, types):
    """Public pointer fields retain their source role independently of Qt macros."""
    unit = mapping.unit
    body = class_record["syntax"].child_by_field_name("body")
    for declaration in body.named_children if body else ():
        if declaration.type != "field_declaration" or any(
                node.type == "function_declarator" for node in walk(declaration)):
            continue
        _, access = _roles(unit, declaration, class_record["syntax"])
        for declarator in declaration.children_by_field_name("declarator"):
            name = _name(unit, declarator)
            if not name:
                continue
            raw = declared_spelling(unit, declaration, declarator, declarator_identifier(declarator))
            fields = api_type_fields(types, raw, declaration.start_byte,
                                     conditional=conditional_offset(unit, declaration.start_byte))
            facts.add("api_field", name, source_span(unit.source, declarator.start_byte, declarator.end_byte),
                      owner=class_record["node_id"] or None, class_id=class_record["node_id"],
                      class_name=class_record["qualified_name"], access=access,
                      status=class_record["status"], raw_type=raw, **fields)
