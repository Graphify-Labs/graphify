"""Rejection-only source interference for an engine's singleton setup.

Lexical identities and literal aliases may show that arbitrary code could affect
the same engine. They never establish a positive runtime alias, invocation,
ordering, ownership or provider relationship.
"""
from __future__ import annotations

from graphify.extractors.qt_cpp_api_shape import api_shape
from graphify.extractors.qt_cpp_calls import literal_string
from graphify.extractors.qt_cpp_syntax import walk

_UNEVALUATED = {"sizeof_expression", "decltype", "noexcept", "noexcept_expression", "requires_expression"}


def executable_context(syntax, body, *, nonpolymorphic_result=False):
    parent = syntax.parent
    while parent is not None and parent != body:
        if parent.type in _UNEVALUATED | {"lambda_expression"}:
            return False
        if parent.type == "typeid_expression" and nonpolymorphic_result:
            return False
        if parent.type == "call_expression":
            function = parent.child_by_field_name("function")
            # The pinned grammar currently represents these C++ keywords as
            # ordinary call nodes. A bool/void/pointer SDK result is not the
            # polymorphic-glvalue exception in typeid; unknown helper returns
            # remain potentially evaluated and cannot prove safe ordering.
            if function is not None and function.type == "identifier" and (
                    function.text == b"noexcept" or nonpolymorphic_result and function.text == b"typeid"):
                return False
        parent = parent.parent
    return True


def _reference(node):
    while node is not None:
        if node.type == "identifier":
            return node
        if node.type == "parenthesized_expression":
            children = [child for child in node.named_children if child.type != "comment"]
            node = children[0] if len(children) == 1 else None
        elif node.type == "pointer_expression":
            node = node.child_by_field_name("argument")
        else:
            return None
    return None


def engine_escaped(unit, mapping, identities, owner, engine_id, load_position, *, setup_end, module_uri, type_name,
                   component_declaration_id=""):
    """Possible mutable aliases remain local to this source/function checkpoint."""
    aliases, source_declarations = {}, {}

    def identity(node):
        reference = _reference(node)
        return identities.potential_declaration(unit.text(reference), reference.start_byte)["declaration_id"] if reference else ""

    def alias_capable(name, position, value):
        spelling, _ = identities.declared_type_binding(name, position)
        shape = api_shape(spelling, allow_value=True)
        if shape is None:
            return False
        if shape[1] in {"pointer", "reference"}:
            return True
        reference = _reference(value)
        if shape[0] == "auto" and reference is not None:
            source, _ = identities.declared_type_binding(unit.text(reference), reference.start_byte)
            original = api_shape(source, allow_value=True)
            return bool(value.type == "pointer_expression" or original and original[1] == "pointer")
        return False

    # A literal local reference/pointer alias can invalidate ordering but cannot
    # seed any positive engine identity. Conditional writes retain all possible
    # source aliases; the AST budget bounds this finite rejection-side graph.
    for records in identities.declarations.values():
        for record in records:
            syntax = record["syntax"]
            if record["owner"] is not owner or syntax.start_byte >= load_position:
                continue
            left = identities.potential_declaration(record["name"], record["name_end"])["declaration_id"]
            source_declarations[syntax.start_byte, syntax.end_byte] = left
            value = syntax.child_by_field_name("value")
            if value is not None and alias_capable(record["name"], record["name_end"], value):
                right = identity(value)
                if left and right:
                    aliases.setdefault(left, set()).add(right)
    for name, syntax in identities.writes:
        right = syntax.child_by_field_name("right")
        if (syntax.start_byte < load_position and mapping.owner_at(syntax.start_byte) is owner
                and right is not None and alias_capable(name, syntax.start_byte, right)):
            left = identities.potential_declaration(name, syntax.start_byte)["declaration_id"]
            target = identity(right)
            if left and target:
                aliases.setdefault(left, set()).add(target)

    def reaches(node):
        pending, seen = [identity(node)], set()
        while pending:
            current = pending.pop()
            if not current or current in seen:
                continue
            if current == engine_id:
                return True
            seen.add(current)
            pending.extend(aliases.get(current, ()))
        return False

    for syntax in walk(owner["body"]):
        if syntax.start_byte >= load_position:
            continue
        if syntax.type == "lambda_expression":
            captures = syntax.child_by_field_name("captures")
            if captures is None:
                continue
            nodes = list(walk(captures))
            if any(node.type == "lambda_default_capture" for node in nodes):
                nodes.extend(walk(syntax.child_by_field_name("body")))
            if any(node.type == "identifier" and reaches(node) for node in nodes):
                return True
        if syntax.type == "init_declarator" and executable_context(syntax, owner["body"]):
            value = syntax.child_by_field_name("value")
            declaration_id = source_declarations.get((syntax.start_byte, syntax.end_byte), "")
            # The accepted QQmlComponent constructor has a separately proven
            # engine association. Arbitrary constructors/aggregate storage do
            # not borrow that exception or establish a safe singleton order.
            if (value is not None and value.type in {"argument_list", "initializer_list"}
                    and declaration_id != component_declaration_id
                    and any(reaches(node) for node in value.named_children)):
                return True
        if syntax.type == "assignment_expression" and executable_context(syntax, owner["body"]):
            left, right = syntax.child_by_field_name("left"), syntax.child_by_field_name("right")
            if left is not None and (left.type != "identifier" or not identity(left)) and reaches(right):
                return True
        if syntax.type == "call_expression" and executable_context(syntax, owner["body"]):
            arguments = syntax.child_by_field_name("arguments")
            if arguments is not None and any(reaches(node) for node in arguments.named_children):
                return True
            function = syntax.child_by_field_name("function")
            if function is not None and function.type == "field_expression":
                receiver = function.child_by_field_name("argument")
                member = function.child_by_field_name("field")
                name = unit.field(member, "name") if member is not None and member.type == "template_method" else unit.text(member)
                # Known effects through a literal runtime alias may invalidate
                # the direct receiver's ordering. The alias remains rejection
                # evidence; it cannot resolve a setup/load on its own.
                opaque_assertion = any(item["kind"] == "test_assertion"
                               and item["start"] <= syntax.start_byte < item["end"] for item in unit.qt_test_macros)
                if receiver is not None and reaches(receiver) and (identity(receiver) != engine_id or opaque_assertion):
                    if name == "clearSingletons" and syntax.start_byte > setup_end:
                        return True
                    if name == "singletonInstance" and syntax.start_byte < setup_end:
                        return True
                    if name == "setExternalSingletonInstance":
                        args = [item for item in arguments.named_children if item.type != "comment"] if arguments else []
                        names = [literal_string(unit.text(item)) if item.type == "string_literal" else None for item in args[:2]]
                        if len(names) != 2 or all(value is None or value == expected for value, expected in zip(names, (module_uri, type_name))):
                            return True
    return False
