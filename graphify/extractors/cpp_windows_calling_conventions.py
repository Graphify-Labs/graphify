"""Source-only Windows convention slots for the bounded C++ parse view.

Literal SDK includes establish an explicit syntax profile, not an installed SDK,
ABI, callback registration or runtime guarantee. Only a proven declaration slot
may omit its macro token; original declaration bytes remain authoritative.
"""
from __future__ import annotations

import re
from bisect import bisect_left

from graphify.extractors.cpp_include_guards import IncludeGuardIndex
from graphify.extractors.cpp_lexical_tokens import identifier_fragment

_TOKEN = re.compile(rb"\b(?:CALLBACK|WINAPI|APIENTRY)\b")
_WRITE = re.compile(rb"(?m)^[ \t]*#[ \t]*(?:define|undef)[ \t]+(CALLBACK|WINAPI|APIENTRY|Q_OS_WIN)\b")
_HEADERS = {b"<windows.h>", b"<Windows.h>", b"<qt_windows.h>", b"<QtCore/qt_windows.h>"}
_DECLARATIONS = {"function_definition", "declaration", "field_declaration"}
_CONDITIONS = {"preproc_if", "preproc_ifdef", "preproc_else", "preproc_elif"}


def needs_windows_convention_recovery(code):
    """Keep unrelated C++ inputs off the additional bounded parse path."""
    return bool(_TOKEN.search(code))


def _branch(node, source, guards):
    """Accept only a simple positive Windows branch; no expression evaluation."""
    branch = ()
    current = node.parent
    while current is not None:
        if current.type in _CONDITIONS and not guards.accepts(current):
            name = current.child_by_field_name("name")
            opening = current.child(0)
            closing = current.child(current.child_count - 1)
            if (branch or current.type != "preproc_ifdef" or name is None
                    or source[name.start_byte:name.end_byte] != b"Q_OS_WIN"
                    or opening is None or opening.type != "#ifdef"
                    or current.child_by_field_name("alternative") is not None
                    or closing is None or closing.type != "#endif" or closing.is_missing):
                return None
            branch = (current.id,)
        current = current.parent
    return branch


def _function(declaration):
    function = declaration.child_by_field_name("declarator")
    if function is None or function.type != "function_declarator":
        return None
    name = function.child_by_field_name("declarator")
    parameters = function.child_by_field_name("parameters")
    if (name is None or name.type not in {"identifier", "field_identifier", "qualified_identifier"}
            or name.has_error or parameters is None or parameters.has_error or function.has_error):
        return None
    return function, name, parameters


def _convention_slot(declaration, code):
    """Both ERROR siblings and sized-type misclassification need the same proof."""
    shape = _function(declaration)
    result_type = declaration.child_by_field_name("type")
    if shape is None or result_type is None or result_type.is_missing or result_type.has_error:
        return None
    function, name, parameters = shape
    matches = list(_TOKEN.finditer(code, result_type.start_byte, function.start_byte))
    if len(matches) != 1:
        return None
    match = matches[0]
    # A macro cannot stand in for the entire return type. Between its end and
    # the actual function name, only whitespace may remain.
    if (not code[result_type.start_byte:match.start()].strip()
            or code[match.end():function.start_byte].strip()):
        return None
    if match.start() < result_type.end_byte:
        if result_type.type != "sized_type_specifier" or match.end() != result_type.end_byte:
            return None
    elif code[result_type.end_byte:match.start()].strip():
        return None
    body = declaration.child_by_field_name("body")
    identity = (declaration.start_byte, declaration.end_byte, name.start_byte, name.end_byte,
                parameters.start_byte, parameters.end_byte,
                (body.start_byte, body.end_byte) if body is not None else None)
    return match, identity


def _source_code(code, tree):
    """Separate actual own writes from opaque directive continuations/payload."""
    result, offset, continued, first_write = bytearray(code), 0, False, len(code)
    for line in code.splitlines(keepends=True):
        directive = continued or line.lstrip().startswith(b"#")
        write = _WRITE.match(line) if directive and not continued else None
        if write is not None and not identifier_fragment(tree, offset + write.start(1), offset + write.end(1)):
            first_write = min(first_write, offset + write.start())
        if directive:
            result[offset:offset + len(line)] = re.sub(rb"[^\r\n]", b" ", line)
        continued = directive and line.rstrip(b"\r\n").endswith(b"\\")
        offset += len(line)
    return bytes(result), first_write


def recover_windows_calling_conventions(source, code, *, parse, walk):
    """Omit only SDK-backed macro slots proven again in the resulting AST.

All source/parse dependencies come from the caller. Unknown includes after the
SDK witness, own macro/guard writes and ordinary macro-name uses deny recovery;
the helper never opens or discovers a header or executes preprocessor code.
"""
    if not needs_windows_convention_recovery(code):
        return source
    tree = parse(source)
    nodes = list(walk(tree))
    guards = IncludeGuardIndex(tree)
    includes = sorted((node for node in nodes if node.type == "preproc_include"), key=lambda node: node.start_byte)
    include_starts = [node.start_byte for node in includes]
    witnesses = {}
    for include in includes:
        path = include.child_by_field_name("path")
        branch = _branch(include, code, guards)
        if path is not None and code[path.start_byte:path.end_byte] in _HEADERS and branch is not None:
            witnesses[include.id] = branch
    if not witnesses:
        return source
    candidates = []
    for node in nodes:
        if node.type in _DECLARATIONS:
            slot = _convention_slot(node, code)
            if slot is not None and not identifier_fragment(tree, slot[0].start(), slot[0].end()):
                candidates.append((node, *slot))
    slots = {match.span() for _node, match, _identity in candidates}
    statement_code, first_write = _source_code(code, tree)
    ordinary = {}
    for match in _TOKEN.finditer(statement_code):
        # An earlier accepted Qt annotation owns its stringified payload;
        # a token already omitted by that stage is not an ordinary C++ binder.
        if (source[match.start():match.end()] == match[0] and match.span() not in slots
                and not identifier_fragment(tree, match.start(), match.end())):
            ordinary.setdefault(match[0], match.start())
    proposed, accepted = bytearray(source), {}
    for declaration, match, identity in candidates:
        start, end = match.span()
        branch = _branch(declaration, code, guards)
        if branch is None or ordinary.get(match[0], start) < start or first_write < start:
            continue
        # Distinct simple positive Q_OS_WIN guards share a source profile only
        # after the SDK branch closes. Their truth remains explicitly unknown.
        preceding = bisect_left(include_starts, start) - 1
        if preceding < 0:
            continue
        witness = includes[preceding]
        context = witnesses.get(witness.id)
        if (context is None or witness.end_byte > start
                or not (not context or context == branch or branch and witness.parent.end_byte <= start)):
            continue
        proposed[start:end] = b" " * (end - start)
        accepted[identity] = (start, end)
    if not accepted:
        return source
    recovered = parse(bytes(proposed))
    proven = set()
    for declaration in walk(recovered):
        if declaration.type not in _DECLARATIONS:
            continue
        shape = _function(declaration)
        result_type = declaration.child_by_field_name("type")
        if shape is None or result_type is None or result_type.has_error:
            continue
        _function_node, name, parameters = shape
        body = declaration.child_by_field_name("body")
        identity = (declaration.start_byte, declaration.end_byte, name.start_byte, name.end_byte,
                    parameters.start_byte, parameters.end_byte,
                    (body.start_byte, body.end_byte) if body is not None else None)
        if identity in accepted and result_type.end_byte <= accepted[identity][0]:
            proven.add(identity)
    for identity, (start, end) in accepted.items():
        if identity not in proven:
            proposed[start:end] = source[start:end]
    return bytes(proposed)
