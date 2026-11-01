"""Literal QtTest/QuickTest TU launchers, without generated main or execution.

An inert, equal-byte empty declaration admits surrounding source only after the
final AST proves TU ownership. Hints remain source-only; no test object, setup
callback, engine, load, provider or runtime success is invented.
"""
from __future__ import annotations

import re

from graphify.extractors.cpp_include_guards import IncludeGuardIndex
from graphify.extractors.cpp_lexical_tokens import identifier_fragment
from graphify.extractors.cpp_test_macro_roles import ordinary_test_callable
from graphify.extractors.qt_cpp_compat import _statement_code
from graphify.extractors.qt_cpp_test_syntax import _HEADERS, _arguments, _context, annotation_payloads

LAUNCHER_PATTERN = rb"QTEST_(?:MAIN|GUILESS_MAIN|APPLESS_MAIN)|QUICK_TEST_MAIN(?:_WITH_SETUP)?"
_NAME = re.compile(rb"\b(" + LAUNCHER_PATTERN + rb")\s*\(")
_OVERRIDE = re.compile(rb"(?m)^(?:\xef\xbb\xbf)?[ \t]*#[ \t]*(?:define|undef)[ \t]+(" + LAUNCHER_PATTERN + rb")\b")
_TYPE = re.compile(rb"(?:::)?[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*")


def needs_launcher_recovery(code):
    return bool(_NAME.search(_statement_code(code)))


def launcher_candidates(source, code, tree, *, context, parse, walk, macro, error):
    """Select SDK-family-owned literal macro occurrences, before annotation recovery."""
    if not needs_launcher_recovery(code):
        return []
    contexts = {"qt_test": _context(source, tree, walk, context, _HEADERS),
                "qt_quick_test": _context(source, tree, walk, context, {b"QtQuickTest"})}
    ordinary = {}
    for node in walk(tree):
        parent, name = node.parent, node.child_by_field_name("declarator")
        if ordinary_test_callable(node, source) and name is not None and parent is not None:
            ordinary.setdefault(source[name.start_byte:name.end_byte], []).append(parent.start_byte)
    overrides = [(match[1].decode(), match.start()) for match in _OVERRIDE.finditer(code)
                 if not identifier_fragment(tree, *match.span(1))]
    payloads, cursor, consumed, records = annotation_payloads(code, tree, macro), 0, -1, []
    for match in _NAME.finditer(_statement_code(code)):
        if match.start() < consumed or identifier_fragment(tree, *match.span(1)):
            continue
        while cursor < len(payloads) and payloads[cursor][1] <= match.start():
            cursor += 1
        if cursor < len(payloads) and payloads[cursor][0] < match.start() < payloads[cursor][1]:
            continue
        name, position = match[1].decode(), match.start()
        family = "qt_quick_test" if name.startswith("QUICK_") else "qt_test"
        visible = [item for item in contexts[family] if item[0] <= position]
        if (not visible or any(value == name and start < position for value, start in overrides)
                or any(start <= position for start in ordinary.get(match[1], ()))
                or name in visible[-1][3] or "*" in visible[-1][3]
                or context is not None and any(item.after <= position and {"*", name} & set(item.names) for item in context.denials)):
            continue
        closing, args = _arguments(code, match.end() - 1)
        needed = 2 if name.endswith("_WITH_SETUP") else 1
        values = [re.sub(rb"\s+", b"", code[start:end]) for start, end in args]
        if (closing is None or len(args) != needed or any(not _TYPE.fullmatch(value) for value in values)
                or family == "qt_quick_test" and b"::" in values[0]):
            raise error("QT_CPP_SYNTAX", "Qt test launcher requires literal type/suite arguments")
        if any(len(source[start:end]) > 384 for start, end in args):
            raise error("QT_CPP_LIMIT", "Qt test launcher argument exceeds the semantic bound")
        record = {"name": name, "kind": "test_launcher", "start": position, "end": closing + 1,
                  "framework": family, "arguments": args, "sdk_header": visible[-1][1],
                  "class_hint": values[-1].decode() if family == "qt_test" or needed == 2 else "",
                  "suite_name": values[0].decode() if family == "qt_quick_test" else ""}
        if visible[-1][2]:
            record["include_witnesses"] = [witness.fields() for witness in visible[-1][2]]
        if context is not None and context.build_witnesses:
            record["build_include_witnesses"] = [witness.fields() for witness in context.build_witnesses]
        records.append(record)
        consumed = closing + 1
    return records


def recover_launchers(source, records):
    """Empty declarations contribute no generic symbols or callable targets."""
    parsed = bytearray(source)
    for record in records:
        start, end = record["start"], record["end"]
        parsed[start:end] = re.sub(rb"[^\r\n]", b" ", source[start:end])
        parsed[start] = 59
    return bytes(parsed)


def finish_launchers(source, parsed, records, *, parse, walk, span, error):
    """Validate exact recovered TU scope only after all neighboring syntax recovery."""
    if not records:
        return ()
    tree = parse(parsed)
    guards = IncludeGuardIndex(tree)
    statements = {(node.start_byte, node.end_byte): node for node in walk(tree) if node.type == "expression_statement"}
    for record in records:
        node = statements.get((record["start"], record["start"] + 1))
        if (tree.has_error or node is None or node.parent is None or not
                (node.parent.type == "translation_unit" or guards.accepts(node.parent))):
            raise error("QT_CPP_SYNTAX", "Qt test launcher is not a standalone translation-unit declaration")
        record.update(span=span(source, record["start"], record["end"]),
                      argument_spans=[span(source, start, end) for start, end in record["arguments"]])
    return tuple(records)


def add_test_launcher_facts(mapping, facts):
    """Only source occurrences/hints are published; file containment is a later join."""
    for record in mapping.unit.test_launchers:
        fields = {key: record[key] for key in ("framework", "class_hint", "suite_name", "sdk_header", "argument_spans")}
        if record.get("include_witnesses"):
            fields["include_witnesses"] = record["include_witnesses"]
        if record.get("build_include_witnesses"):
            fields["build_include_witnesses"] = record["build_include_witnesses"]
        facts.add("test_launcher", record["name"], record["span"], mechanism=record["name"],
                  status="source_only", runtime_status="unverified", class_hint_status="unverified",
                  reason="test_launcher_runtime_and_generated_main_unverified", **fields)
