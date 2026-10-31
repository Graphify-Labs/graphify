"""Admit rejected unnamed pointer defaults without a synthetic parameter name.

The pinned parser accepts abstract-reference defaults but rejects plain abstract
pointer defaults. An equal-byte `*` to `&` view admits syntax only. Original
bytes own signatures/types; the default and optional arity remain in the AST.
Compound pointer/CV/callback shapes stay outside this compatibility profile.
"""
from __future__ import annotations

import re

from graphify.extractors.cpp_declarators import callable_declarator

_POINTER_DEFAULT = re.compile(rb"\*(?P<space>[ \t\r\n]+)=")


def needs_unnamed_pointer_recovery(code):
    return bool(_POINTER_DEFAULT.search(code))


def _actual_parameter(parameter, source):
    params = parameter.parent
    function = params.parent if params is not None and params.type == "parameter_list" else None
    if function is None or function.type != "function_declarator" or function.has_error:
        return False
    declaration = function.parent
    while declaration is not None and declaration.type not in {"declaration", "field_declaration", "function_definition"}:
        if declaration.type in {"parameter_list", "argument_list", "init_declarator"}:
            return False
        declaration = declaration.parent
    if declaration is None or not any(callable_declarator(item, source) == function
                                     for item in declaration.children_by_field_name("declarator")):
        return False
    if declaration.type == "function_definition":
        body = declaration.child_by_field_name("body")
        return not any(child.has_error for child in declaration.children if child != body)
    return not declaration.has_error


def _candidate_owner(tree, position):
    """Raw optional syntax or the known most-vexing-parse initializer owns recovery."""
    current = tree.descendant_for_byte_range(position, position + 1)
    while current is not None:
        if current.type == "optional_parameter_declaration" and current.has_error:
            if current.child_by_field_name("declarator") is None:
                return current.start_byte, current.end_byte
            return None
        if current.type == "argument_list":
            init = current.parent
            declaration = init.parent if init is not None else None
            if (init is not None and init.type == "init_declarator" and init.child_by_field_name("value") == current
                    and declaration is not None and declaration.type == "declaration"
                    and declaration.child_by_field_name("type") is not None):
                child = next((node for node in current.named_children
                              if node.start_byte <= position < node.end_byte), None)
                if child is not None and child.has_error:
                    return child.start_byte, child.end_byte
            return None
        if current.type in {"expression_statement", "compound_statement", "translation_unit", "preproc_arg"}:
            return None
        current = current.parent
    return None


def recover_unnamed_pointer_defaults(source, code, *, parse, walk):
    """Prove each local parameter independently; final admission still requires a clean file."""
    if not needs_unnamed_pointer_recovery(code):
        return source
    tree = parse(source)
    list(walk(tree))
    candidates = []
    for match in _POINTER_DEFAULT.finditer(code):
        start = match.start()
        # A lexer may mask a comment as whitespace, but this initial profile
        # admits actual whitespace only and never erases an unknown token.
        if source[start:start + 1] != b"*" or source[match.start("space"):match.end("space")].strip():
            continue
        owner = _candidate_owner(tree, start)
        if owner is not None:
            candidates.append((start, match.end() - 1, owner))
    if not candidates:
        return source
    parsed = bytearray(source)
    for start, _, _ in candidates:
        parsed[start] = 38
    recovered = parse(bytes(parsed))
    parameters = {(node.start_byte, node.end_byte): node for node in walk(recovered)
                  if node.type == "optional_parameter_declaration"}
    for start, equal, bounds in candidates:
        parameter = parameters.get(bounds)
        declarator = parameter.child_by_field_name("declarator") if parameter is not None else None
        default = parameter.child_by_field_name("default_value") if parameter is not None else None
        type_node = parameter.child_by_field_name("type") if parameter is not None else None
        if (parameter is None or parameter.has_error or declarator is None or default is None or type_node is None
                or declarator.type != "abstract_reference_declarator" or declarator.has_error
                or (declarator.start_byte, declarator.end_byte) != (start, start + 1)
                or type_node.end_byte > start or code[type_node.end_byte:start].strip()
                or not any(child.type == "=" and child.start_byte == equal for child in parameter.children)
                or not _actual_parameter(parameter, bytes(parsed))):
            parsed[start] = 42
    return bytes(parsed)
