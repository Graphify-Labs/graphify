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


def _template_parameter(node, walk):
    """Require a named template parameter, not an ambiguous initializer argument."""
    syntax = node.child_by_field_name("type")
    declarator = node.child_by_field_name("declarator")
    if syntax is None or declarator is None:
        return False
    if not any(child.type == "template_type" for child in walk(syntax)):
        return False
    # Parenthesized/functional declarations can also spell ordinary call
    # arguments. Do not turn that grammar ambiguity into declaration authority.
    while declarator.type in {"pointer_declarator", "reference_declarator"}:
        declarator = (declarator.child_by_field_name("declarator")
                      or (declarator.named_children[-1] if declarator.named_children else None))
        if declarator is None:
            return False
    return declarator.type == "identifier" and not declarator.has_error


def _declaration_parameter(node):
    """Defaults belong to a function declaration, never nested callback types."""
    parameters = node.parent
    function = parameters.parent if parameters is not None else None
    if (parameters is None or parameters.type != "parameter_list" or function is None
            or function.type != "function_declarator"):
        return False
    name = function.child_by_field_name("declarator")
    if name is None or name.type not in {"identifier", "field_identifier", "qualified_identifier"}:
        return False
    owner = function.parent
    while owner is not None:
        if owner.type in {"parameter_list", "argument_list", "init_declarator"}:
            return False
        if owner.type in {"declaration", "field_declaration", "function_definition"}:
            return True
        owner = owner.parent
    return False


def _reclassified_template_defaults(source, code, *, parse, walk):
    """INC-QML-53: validate empty defaults whose original AST lost the declaration.

    Some template parameter defaults cause expression/init-declarator trees,
    including error-free misclassification. A speculative omission becomes an
    accepted parse view only when the recovered AST proves exact parameter
    ownership. Rejected spans are restored; final admission still owns errors.
    """
    candidates = [match for match in _EMPTY.finditer(_statement_code(code))
                  if source[match.start():match.start() + 1] == b"="]
    if not candidates:
        return source
    proposed = bytearray(source)
    for match in candidates:
        proposed[match.start():match.end()] = re.sub(rb"[^\r\n]", b" ", source[match.start():match.end()])
    tree = parse(bytes(proposed))
    if tree.has_error:
        return source
    parameters = [node for node in walk(tree)
                  if node.type == "parameter_declaration" and not node.has_error
                  and _declaration_parameter(node) and _template_parameter(node, walk)]
    # Indexing by the preceding code token keeps candidate matching linear rather
    # than comparing every default with every declaration in an untrusted file.
    by_end = {node.end_byte: node for node in parameters}
    accepted = set()
    for match in candidates:
        previous = match.start()
        while previous and code[previous - 1] in b" \t\r\n":
            previous -= 1
        parameter = by_end.get(previous)
        following = match.end()
        while following < len(code) and code[following] in b" \t\r\n":
            following += 1
        if (parameter is not None and following < parameter.parent.end_byte
                and code[following:following + 1] in {b",", b")"}):
            accepted.add(match.start())
    for match in candidates:
        if match.start() not in accepted:
            proposed[match.start():match.end()] = source[match.start():match.end()]
    return bytes(proposed)


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
    recovered = _empty_parameter_defaults(recovered, code, tree, walk)
    return _reclassified_template_defaults(recovered, code, parse=parse, walk=walk)
