"""Lexical JavaScript bindings for QML subtrees; no value evaluation/dataflow."""
from __future__ import annotations

from graphify.extractors.qml_facts import text

FUNCTIONS = {"function_declaration", "function_expression", "arrow_function", "generator_function_declaration"}


def bound_names(node, source: bytes) -> set[str]:
    """Collect binding positions only; object keys and type names are not locals."""
    if node is None:
        return set()
    if node.type in {"identifier", "shorthand_property_identifier_pattern"}:
        return {text(node, source)}
    if node.type in {"required_parameter", "optional_parameter", "assignment_pattern", "pair_pattern"}:
        child = (node.child_by_field_name("pattern") or node.child_by_field_name("left")
                 or node.child_by_field_name("value"))
        return bound_names(child, source)
    return set().union(*(bound_names(c, source) for c in node.named_children
                         if c.type not in {"type_annotation", "type_identifier", "property_identifier"}))


def qualified_name(node, source: bytes) -> str | None:
    """Accept a literal identifier/member chain; computed accesses stay dynamic."""
    if node is None:
        return None
    if node.type in {"identifier", "property_identifier", "nested_identifier"}:
        value = text(node, source)
        return value if len(value) <= 256 else None
    if node.type == "member_expression":
        receiver = qualified_name(node.child_by_field_name("object"), source)
        member = node.child_by_field_name("property")
        if receiver and member and member.type == "property_identifier":
            value = receiver + "." + text(member, source)
            return value if len(value) <= 256 else None
    return None


def hoisted_names(body, source: bytes) -> set[str]:
    """var binds the function; nested functions and their vars remain isolated."""
    names, pending = set(), [body]
    while pending:
        node = pending.pop()
        if node is None or node.type in FUNCTIONS:
            continue
        if node.type == "variable_declaration":
            for child in node.named_children:
                if child.type == "variable_declarator":
                    names.update(bound_names(child.child_by_field_name("name"), source))
        if node.type == "for_in_statement" and text(node.child_by_field_name("kind"), source) == "var":
            names.update(bound_names(node.child_by_field_name("left"), source))
        pending.extend(node.named_children)
    return names


def local_declarations(block, source: bytes):
    """Block-level let/const/function bindings shadow only their lexical block."""
    for child in block.named_children:
        if child.type == "function_declaration":
            yield text(child.child_by_field_name("name"), source), child
        elif child.type in {"lexical_declaration", "variable_declaration"}:
            for declaration in child.named_children:
                if declaration.type != "variable_declarator":
                    continue
                value = declaration.child_by_field_name("value")
                for name in bound_names(declaration.child_by_field_name("name"), source):
                    yield name, value if value and value.type in FUNCTIONS else None


def reassigned_names(body, source: bytes) -> set[str]:
    """A reassigned callable has runtime value/dataflow; don't reuse its initializer."""
    names, pending = set(), [body]
    while pending:
        node = pending.pop()
        if node is None or node.type in FUNCTIONS:
            continue
        if node.type in {"assignment_expression", "augmented_assignment_expression", "update_expression"}:
            target = node.child_by_field_name("left") or node.child_by_field_name("argument")
            if target and target.type == "identifier":
                names.add(text(target, source))
        pending.extend(node.named_children)
    return names
