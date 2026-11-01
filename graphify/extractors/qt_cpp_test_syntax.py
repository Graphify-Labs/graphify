"""Bounded literal QtTest parse views; opaque data never supplies a native type."""
from __future__ import annotations

import re

from graphify.extractors.cpp_declarators import member_declarator
from graphify.extractors.qt_cpp_compat import _statement_code
from graphify.extractors.cpp_include_guards import IncludeGuardIndex
from graphify.extractors.cpp_lexical_tokens import identifier_fragment
from graphify.extractors.qt_cpp_test_statements import implicit_data_scope, valid_statement_scope
from graphify.extractors.cpp_test_macro_roles import ordinary_test_callable

_HEADERS = {b"QTest", b"QtTest", b"QtTest/QTest", b"QtTest/QtTest"}
_SPELLING = rb"QFETCH(?:_GLOBAL)?|QTRY_(?:COMPARE(?:_(?:EQ|NE|LT|LE|GT|GE))?|VERIFY2?)(?:_WITH_TIMEOUT)?|(?:QTRY_VERIFY|QVERIFY)_ACTIVE_FOCUS"
_NAME = re.compile(rb"\b(" + _SPELLING + rb")\s*\(")
_OVERRIDE = re.compile(rb"(?m)^(?:\xef\xbb\xbf)?[ \t]*#[ \t]*(?:define|undef)[ \t]+(" + _SPELLING + rb")\b")


def needs_test_recovery(code):
    return bool(_NAME.search(_statement_code(code)))


def _context(source, tree, walk, context, headers=_HEADERS):
    if context is not None:
        return [(item.after, item.sdk_header, item.witnesses, item.denied_names) for item in context.activations
                if item.sdk_header.encode() in headers]
    includes, guards = [], IncludeGuardIndex(tree)
    for node in walk(tree):
        if node.type != "preproc_include" or node.parent is None or not (
                node.parent.type == "translation_unit" or guards.accepts(node.parent)):
            continue
        value = node.child_by_field_name("path")
        raw = source[value.start_byte:value.end_byte] if value else b""
        if raw.startswith(b"<") and raw.endswith(b">") and raw[1:-1] in headers:
            includes.append((node.end_byte, raw[1:-1].decode(), (), ()))
    return includes


def _arguments(code, opening):
    """The C++ preprocessor groups commas only with parentheses, not templates."""
    depth, start, args = 1, opening + 1, []
    for offset in range(start, min(len(code), opening + 100_000)):
        token = code[offset]
        if token == 40:
            depth += 1
        elif token == 41:
            depth -= 1
            if not depth:
                args.append((start, offset))
                return offset, args
        elif token == 44 and depth == 1:
            args.append((start, offset))
            start = offset + 1
    return None, []


def annotation_payloads(code, tree, macro):
    # A Qt annotation's payload is not an independent QtTest statement. The
    # annotation owner still performs its own scope/form validation afterwards.
    payloads, consumed = [], -1
    for match in macro.finditer(code):
        if match.start() < consumed or identifier_fragment(tree, *match.span()):
            continue
        cursor = match.end()
        while cursor < len(code) and code[cursor] in b" \t\r\n":
            cursor += 1
        if cursor < len(code) and code[cursor] == 40:
            end, _ = _arguments(code, cursor)
            if end is not None:
                payloads.append((cursor, end))
                consumed = end
    return payloads


def test_candidates(source, code, tree, *, walk, parse, error, macro, context=None):
    if not needs_test_recovery(code):
        return []
    context_profile = context
    contexts = _context(source, tree, walk, context, _HEADERS | {b"QtQuickTest"})
    if not contexts:
        return []
    overrides = [(match[1], match.start()) for match in _OVERRIDE.finditer(code)
                 if not identifier_fragment(tree, *match.span(1))]
    ordinary = {}
    for node in walk(tree):
        if node.type != "function_declarator" or node.has_error:
            continue
        name = node.child_by_field_name("declarator")
        if name is not None and ordinary_test_callable(node, source):
            ordinary.setdefault(source[name.start_byte:name.end_byte], []).append(node.start_byte)
    payloads = annotation_payloads(code, tree, macro)
    candidates, consumed, payload = [], -1, 0
    statements = _statement_code(code)
    for match in _NAME.finditer(statements):
        if identifier_fragment(tree, match.start(1), match.end(1)):
            continue
        while payload < len(payloads) and payloads[payload][1] <= match.start():
            payload += 1
        if payload < len(payloads) and payloads[payload][0] < match.start() < payloads[payload][1]:
            continue
        if match.start() < consumed:
            continue
        name = match[1].decode()
        quick = name.endswith("_ACTIVE_FOCUS")
        context = [item for item in contexts if item[0] <= match.start()
                   and (item[1] == "QtQuickTest" if quick else item[1].encode() in _HEADERS)]
        if (not context or match[1].decode() in context[-1][3] or "*" in context[-1][3]
                or context_profile is not None and any(item.after <= match.start() and
                    {"*", match[1].decode()} & set(item.names) for item in context_profile.denials)
                or any(name == match[1] and at < match.start() for name, at in overrides)
                or any(at < match.start() for at in ordinary.get(match[1], []))):
            continue
        before = statements[:match.start()].rstrip()
        if before.endswith((b".", b"->", b"::")):
            continue
        closing, args = _arguments(statements, match.end() - 1)
        needed = (1 if quick or name.startswith("QTRY_VERIFY") and not name.startswith("QTRY_VERIFY2") else 2) + int(name.endswith("_WITH_TIMEOUT"))
        if closing is None or len(args) != needed or any(not source[start:end].strip() for start, end in args):
            raise error("QT_CPP_SYNTAX", "QtTest macro arguments are outside the supported profile")
        semi = closing + 1
        while semi < len(code) and code[semi] in b" \t\r\n":
            semi += 1
        if semi >= len(code) or code[semi] != 59:
            raise error("QT_CPP_SYNTAX", "QtTest macro requires a standalone terminated statement")
        record = {"name": name, "start": match.start(), "end": closing + 1, "opening": match.end() - 1,
                  "semicolon": semi, "arguments": args, "sdk_header": context[-1][1],
                  "kind": "test_data" if name.startswith("QFETCH") else "test_assertion",
                  "framework": "qt_quick_test" if quick else "qt_test", "retry": name.startswith("QTRY_")}
        if context[-1][2]:
            record["include_witnesses"] = [witness.fields() for witness in context[-1][2]]
        if context_profile is not None and context_profile.build_witnesses:
            record["build_include_witnesses"] = [witness.fields() for witness in context_profile.build_witnesses]
        if record["kind"] == "test_data":
            first, second = args
            variable = statements[second[0]:second[1]].strip()
            dtype = source[first[0]:first[1]].strip()
            if max(len(variable), len(dtype)) > 384:
                raise error("QT_CPP_LIMIT", "QtTest type or variable exceeds the semantic bound")
            if not re.fullmatch(rb"[A-Za-z_]\w*", variable):
                raise error("QT_CPP_SYNTAX", "QtTest data requires a literal variable identifier")
            dummy = dtype + b" " + variable + b";"
            declared = parse(dummy)
            entries = [node for node in declared.named_children if node.type != "comment"]
            declarators = entries[0].children_by_field_name("declarator") if len(entries) == 1 and entries[0].type == "declaration" else []
            shape = member_declarator(declarators[0], dummy) if len(declarators) == 1 else None
            if declared.has_error or shape != (variable.decode(), False) or dtype == b"void":
                raise error("QT_CPP_SYNTAX", "QtTest data type is outside the supported profile")
            start = second[0] + len(statements[second[0]:second[1]]) - len(statements[second[0]:second[1]].lstrip())
            record.update(variable=variable.decode(), raw_type=dtype.decode(), variable_start=start, variable_end=start + len(variable))
        candidates.append(record)
        consumed = closing + 1
    return candidates


def recover_test_macros(source, candidates, *, parse, walk, error):
    """Real scoped opaque binders or inert implicit bodies never grant native types."""
    if not candidates:
        return source
    parsed = bytearray(source)
    for record in candidates:
        if record["kind"] == "test_data":
            start, end = record["start"], record["semicolon"]
            parsed[start:record["variable_start"]] = re.sub(rb"[^\r\n]", b" ", source[start:record["variable_start"]])
            parsed[start:start + 3] = b"int"
            parsed[record["variable_end"]:end] = re.sub(rb"[^\r\n]", b" ", source[record["variable_end"]:end])
        else:
            start, end = record["start"], record["opening"]
            parsed[start:end] = re.sub(rb"[^\r\n]", b" ", source[start:end])
            parsed[start:start + 6] = b"(void)"
    tree = parse(bytes(parsed))
    # Each adapter proves only its own exact syntax. A neighboring supported
    # declaration adapter may still be pending; final Qt overlay admission still
    # requires a clean tree. Generic C++ retains its existing partial-input policy.
    statements_by_span = {(node.type, node.start_byte, node.end_byte): node for node in walk(tree)
                          if node.type in {"declaration", "expression_statement"}}
    # The pinned grammar rejects a declaration as an unbraced control body.
    # Propose an inert statement only for failed data binders, then require its
    # actual typed body role. One reparse handles the entire bounded cohort.
    implicit = []
    for record in candidates:
        if record["kind"] != "test_data":
            continue
        statement = statements_by_span.get(("declaration", record["start"], record["semicolon"] + 1))
        if statement is not None and valid_statement_scope(statement) is not None:
            continue
        start, end = record["start"], record["semicolon"]
        parsed[start:end] = re.sub(rb"[^\r\n]", b" ", source[start:end])
        parsed[start] = ord("0")
        implicit.append(record)
    if implicit:
        tree = parse(bytes(parsed))
        statements_by_span = {(node.type, node.start_byte, node.end_byte): node for node in walk(tree)
                              if node.type in {"declaration", "expression_statement"}}
        for record in implicit:
            statement = statements_by_span.get(("expression_statement", record["start"], record["semicolon"] + 1))
            if statement is None or implicit_data_scope(statement) is None:
                raise error("QT_CPP_SYNTAX", "QtTest data has no supported declaration/body scope")
            record["parsed_role"] = "opaque_statement"
    for record in candidates:
        inert = record.get("parsed_role") == "opaque_statement"
        expected = "declaration" if record["kind"] == "test_data" and not inert else "expression_statement"
        statement = statements_by_span.get((expected, record["start"], record["semicolon"] + 1))
        scope = (implicit_data_scope(statement) if inert else valid_statement_scope(statement)) if statement is not None else None
        if scope is None:
            raise error("QT_CPP_SYNTAX", "QtTest macro is not a standalone callable statement")
        record["scope_start"], record["scope_end"] = scope.start_byte, scope.end_byte
    return bytes(parsed)


def test_macro_records(source, candidates, *, span):
    """Attach original coordinates only after the final parse view is accepted."""
    return tuple({**record, "span": span(source, record["start"], record["end"]),
                  "argument_spans": [span(source, start, end) for start, end in record["arguments"]],
                  **({"variable_span": span(source, record["variable_start"], record["variable_end"]),
                       "declaration_span": span(source, record["start"], record["semicolon"] + 1)} if record["kind"] == "test_data" else {})}
                 for record in candidates)
