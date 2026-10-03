"""Narrow parse-view recovery for empty parameter defaults and Qt Q_UNUSED."""
from __future__ import annotations

import re

_UNUSED = re.compile(rb"\bQ_UNUSED\s*\(")
_EMPTY = re.compile(rb"=\s*\{\s*\}")
_LOCAL_UNUSED = re.compile(rb"(?m)^\s*#\s*(?:define|undef)\s+Q_UNUSED\b")


def needs_recovery(code: bytes) -> bool:
    """Cheap admission avoids extra parse work for unrelated C++ syntax."""
    return bool(_UNUSED.search(code) or _EMPTY.search(code))


def _statement_code(code):
    # Directive continuations are not function-body statements. Keep every
    # byte/newline while excluding their tokens from candidate discovery.
    result, continued, offset = bytearray(code), False, 0
    for line in code.splitlines(keepends=True):
        directive = continued or line.lstrip().startswith(b"#")
        if directive:
            result[offset:offset + len(line)] = re.sub(rb"[^\r\n]", b" ", line)
        continued = directive and line.rstrip(b"\r\n").endswith(b"\\")
        offset += len(line)
    return bytes(result)


def _declares_unused(tree, source, walk):
    for node in walk(tree):
        if node.type != "function_declarator":
            continue
        name = node.child_by_field_name("declarator")
        if name and source[name.start_byte:name.end_byte] == b"Q_UNUSED":
            return True
    return False


def _arguments_end(code, opening):
    """Require balanced single-argument syntax; the AST validates expression content."""
    depth = 1
    for index in range(opening + 1, len(code)):
        token = code[index]
        if token == 40:
            depth += 1
        elif token == 41:
            depth -= 1
            if not depth:
                return index
        elif token == 44 and depth == 1:
            return None
    return None


def _in_callable(node):
    # The parser walk bounds depth before this ancestry check. Lambdas own
    # executable bodies too; global initializers and signatures do not.
    current = node.parent
    while current:
        if current.type in {"function_definition", "lambda_expression"}:
            return True
        current = current.parent
    return False


def _unused_statements(source, code, tree, *, parse, walk):
    if _LOCAL_UNUSED.search(code) or _declares_unused(tree, source, walk):
        return source
    statement_code = _statement_code(code)
    parsed, candidates = bytearray(source), {}
    for match in _UNUSED.finditer(statement_code):
        start, opening = match.start(), match.end() - 1
        before = start - 1
        while before >= 0 and statement_code[before] in b" \t\r\n":
            before -= 1
        if statement_code[max(0, before - 1):before + 1].endswith((b".", b"->", b"::")):
            continue
        closing = _arguments_end(statement_code, opening)
        if closing is None:
            continue
        # Qt 6 defines Q_UNUSED(x) as (void)x;. Reuse the macro-name space and
        # its closing parenthesis for the cast/semicolon. Argument bytes remain
        # untouched, preserving evaluated nested calls and their original spans.
        parsed[start:start + 8] = b"(void)  "
        parsed[opening], parsed[closing] = 32, 59
        candidates[start] = closing + 1
    if not candidates:
        return source
    accepted = set()
    for node in walk(parse(bytes(parsed))):
        statement = node.parent
        if (node.type == "cast_expression" and not node.has_error and statement
                and statement.type == "expression_statement" and not statement.has_error
                and candidates.get(node.start_byte) == statement.end_byte
                and statement.start_byte == node.start_byte and _in_callable(statement)):
            accepted.add(node.start_byte)
    # A proposed view is authoritative only for standalone executable macro
    # statements. Restore declarations, return/value contexts and damaged uses.
    for start, end in candidates.items():
        if start not in accepted:
            parsed[start:end] = source[start:end]
    return bytes(parsed)


def _empty_parameter_defaults(source, code, tree, walk):
    parsed = bytearray(source)
    for node in walk(tree):
        if node.type != "optional_parameter_declaration":
            continue
        default = node.child_by_field_name("default_value")
        if default is None or default.type != "compound_literal_expression":
            continue
        missing = default.child_by_field_name("type")
        value = default.child_by_field_name("value")
        equal = next((child for child in node.children if child.type == "="), None)
        if (missing is None or not missing.is_missing or missing.type != "type_identifier"
                or value is None or value.type != "initializer_list" or equal is None
                or any(child.type != "comment" for child in value.named_children)
                or not re.fullmatch(rb"\{\s*\}", code[value.start_byte:value.end_byte])):
            continue
        # The bundled grammar invents a missing compound-literal type for a
        # valid empty default. Omitting only that default in the parse view
        # preserves its declaration/signature and creates no expression fact.
        parsed[equal.start_byte:default.end_byte] = re.sub(
            rb"[^\r\n]", b" ", source[equal.start_byte:default.end_byte]
        )
    return bytes(parsed)


def recover_cpp_syntax(source: bytes, code: bytes, *, parse, walk) -> bytes:
    """Return an equal-length view using the caller's bounded parser/traversal.

    Source is already annotation-normalized; code retains the original lexical
    ownership view. No files are read, discovered or executed by this helper.
    """
    if not needs_recovery(code):
        return source
    tree = parse(source)
    recovered = _unused_statements(source, code, tree, parse=parse, walk=walk)
    if recovered != source:
        tree = parse(recovered)
    return _empty_parameter_defaults(recovered, code, tree, walk)
