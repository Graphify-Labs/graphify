"""Declaration-position API type facts for factory results and QObject properties.

These facts establish declared C++ APIs, never allocation or runtime alias identity.
Only admitted canonical complete classes can own an API endpoint.
"""
from __future__ import annotations

from graphify.extractors.qt_cpp_mapping import _name, _roles
from graphify.extractors.qt_cpp_api_shape import api_shape, declared_spelling, declarator_identifier, return_spelling
from graphify.extractors.qt_cpp_registration import conditional_offset
from graphify.extractors.qt_cpp_syntax import walk, source_span
from graphify.extractors.cpp_declarators import callable_declarator


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
    declarators = [(item, callable_declarator(item, unit.parsed_source))
                   for item in declaration.children_by_field_name("declarator")]
    own = [(item, node) for item, node in declarators if node is not None
           and _name(unit, node.child_by_field_name("declarator")).split("::")[-1] == record["name"]]
    node = own[0][1].parent if len(own) == 1 else None
    while node is not None and node != declaration:
        if node.type not in {"pointer_declarator", "reference_declarator"}:
            # A returned callback retains its complete abstract source shape.
            # Its pointee's return type is not an object-pointer factory API.
            raw = declared_spelling(unit, declaration, own[0][0], own[0][1])
            return {"api_type_target_id": "", "api_type_status": "unsupported",
                    "api_type_reason": "return_declarator_unsupported", "api_type_spelling": raw,
                    "api_type_position": declaration.start_byte}
        node = node.parent
    raw = return_spelling(unit, declaration, own[0][1]) if len(own) == 1 else ""
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
        member_pointers = [record for record in unit.member_pointers
                           if record["declaration_span"]["start_byte"] == declaration.start_byte
                           and record["declaration_span"]["end_byte"] == declaration.end_byte]
        for declarator in declaration.children_by_field_name("declarator"):
            name = _name(unit, declarator)
            if not name:
                continue
            raw = declared_spelling(unit, declaration, declarator, declarator_identifier(declarator))
            # A newly admitted mixed declaration may contain both a member
            # pointer and an ordinary pointer. Each sibling borrows only its
            # shared base type/CV, never the preceding sibling's qualifier/name.
            if member_pointers:
                identifier = declarator_identifier(declarator)
                type_node = declaration.child_by_field_name("type")
                qualifiers = [item for item in declaration.named_children if item.type == "type_qualifier"]
                if identifier is not None and type_node is not None:
                    start = min([type_node.start_byte] + [item.start_byte for item in qualifiers])
                    end = max([type_node.end_byte] + [item.end_byte for item in qualifiers])
                    shape = unit.source[declarator.start_byte:identifier.start_byte] + unit.source[identifier.end_byte:declarator.end_byte]
                    raw = (unit.source[start:end] + b" " + shape).decode().strip()
            fields = api_type_fields(types, raw, declaration.start_byte,
                                     conditional=conditional_offset(unit, declaration.start_byte))
            # Parse compatibility cannot turn a pointer-to-member into an
            # ordinary QObject pointer. Preserve source type/qualification,
            # but keep it outside the typed provider/member traversal seam.
            pointers = [record for record in member_pointers if record["parsed_span"]["start_byte"] == declarator.start_byte
                        and record["parsed_span"]["end_byte"] == declarator.end_byte]
            if len(pointers) == 1:
                record = pointers[0]
                raw = (unit.field(declaration, "type") + " " + unit.source[record["span"]["start_byte"]:record["name_span"]["start_byte"]].decode()).strip()
                fields.update(api_type_target_id="", api_type_status="unsupported",
                              api_type_reason="member_pointer_is_not_object_pointer", api_type_spelling=raw)
            facts.add("api_field", name, source_span(unit.source, declarator.start_byte, declarator.end_byte),
                      owner=class_record["node_id"] or None, class_id=class_record["node_id"],
                      class_name=class_record["qualified_name"], access=access,
                      status=class_record["status"], raw_type=raw, **fields)
