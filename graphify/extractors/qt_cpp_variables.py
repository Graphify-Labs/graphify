"""Bounded source-local C++ type evidence; no arbitrary pointer/value dataflow."""
from __future__ import annotations

import re

from graphify.extractors.qt_cpp_syntax import walk


def simple_reference(value):
    value = value.strip()
    if value.startswith("&"):
        value = value[1:].strip()
    return value if re.fullmatch(r"this|[A-Za-z_]\w*", value) else ""


def type_name(value):
    return re.sub(r"\b(?:const|volatile|struct|class)\b|[&*]", "", value).strip()


def _name(unit, syntax):
    if syntax is None:
        return ""
    while syntax.type in {"pointer_declarator", "reference_declarator", "init_declarator"}:
        syntax = syntax.child_by_field_name("declarator") or next(iter(syntax.named_children), None)
        if syntax is None:
            return ""
    return unit.text(syntax) if syntax.type == "identifier" else ""


def variables_at(unit, mapping, position):
    """Parameters/local explicit types are authoritative only within their owner."""
    owner = mapping.owner_at(position)
    if not owner:
        return {}
    variables = {parameter["name"]: type_name(parameter["type"])
                 for parameter in owner.get("parameters", []) if parameter.get("name")}
    enclosing = mapping.class_at(position)
    # A source-proven constructor callable may still lack an authorized class
    # join; its spelling alone cannot give `this` a definite native type.
    variables["this"] = "" if owner.get("native_owner_unavailable") else (
        enclosing.get("qualified_name") if enclosing else owner.get("class_name")) or ""
    body = owner.get("body")
    if body is None:
        return variables
    for syntax in walk(body):
        if syntax.start_byte >= position:
            continue
        ancestor, visible = syntax.parent, True
        while ancestor and ancestor != body:
            if ancestor.type in {"compound_statement", "lambda_expression", "for_statement", "for_range_loop", "catch_clause"}:
                if not ancestor.start_byte <= position < ancestor.end_byte:
                    visible = False
                    break
            ancestor = ancestor.parent
        if not visible:
            continue
        if syntax.type in {"parameter_declaration", "optional_parameter_declaration"}:
            parameter = _name(unit, syntax.child_by_field_name("declarator"))
            if parameter:
                variables[parameter] = type_name(unit.field(syntax, "type"))
        if syntax.type == "declaration":
            name, value = _name(unit, syntax.child_by_field_name("declarator")), unit.field(syntax, "type")
            if not name:
                continue
            declared = type_name(value)
            if declared == "auto":
                declarator = syntax.child_by_field_name("declarator")
                initial = unit.field(declarator, "value") if declarator else ""
                match = re.fullmatch(r"new\s+([A-Za-z_]\w*(?:::\w+)*)\s*(?:\([^;]*\)|\{[^;]*\})?", initial)
                declared = match[1] if match else ""
            variables[name] = declared
        elif syntax.type in {"assignment_expression", "update_expression"}:
            left = syntax.child_by_field_name("left") or syntax.child_by_field_name("argument")
            name = unit.text(left) if left else ""
            if name in variables:
                # Even an explicitly typed pointer may now refer to another
                # runtime instance; retain no handle identity across reassignment.
                variables[name] = ""
    return variables
