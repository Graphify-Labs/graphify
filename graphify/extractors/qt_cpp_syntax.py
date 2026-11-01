"""Bounded C++ source views for Qt overlays; no preprocessing or corpus execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

from tree_sitter import Language, Node, Parser
import tree_sitter_cpp

from graphify.extractors.qt_cpp_compat import needs_recovery, recover_cpp_syntax
from graphify.extractors.qt_cpp_test_syntax import needs_test_recovery, test_candidates, recover_test_macros, test_macro_records
from graphify.extractors.cpp_lexical_tokens import identifier_fragment
from graphify.extractors.qt_cpp_test_context import QtTestContextError, validate_test_context
from graphify.extractors.cpp_include_guards import IncludeGuardIndex
from graphify.extractors.qt_cpp_test_launchers import launcher_candidates, needs_launcher_recovery, recover_launchers, finish_launchers
from graphify.extractors.cpp_member_pointers import has_member_pointer, member_pointer_records, recover_member_pointers
from graphify.extractors.qt_cpp_annotations import (
    annotation_code, annotation_overrides, annotation_scopes, ordinary_spans, valid_annotation_scope, valid_new_annotation,
)

MAX_CPP_BYTES = 5_000_000
_MACRO = re.compile(rb"\b(?:QML_[A-Z_]+|Q_(?:OBJECT|GADGET(?:_EXPORT)?|NAMESPACE(?:_EXPORT)?|DECL_NON(?:ALLOCATING|BLOCKING)_FUNCTION|PROPERTY|INVOKABLE|SIGNAL|SLOT|SIGNALS|SLOTS|ENUM(?:_NS)?|FLAG(?:_NS)?|REVISION|CLASSINFO|INTERFACES|DECLARE_METATYPE|EMIT)|SIGNAL|SLOT)\b")
_RAW_STRING = re.compile(rb'(?:u8|u|U|L)?R"([^\s()\\]{0,16})\(')
_NUMBER = re.compile(rb"(?:[0-9]|\.[0-9])(?:[A-Za-z0-9_.]|'[A-Za-z0-9_]|(?<=[eEpP])[+-])*")
_MEMBER_CAST = re.compile(rb"\bstatic_cast\s*<[\w:\s*&<>]+\(\s*[\w:]+\s*::\s*\*\s*\)\s*\([\w:\s*&<>,]*\)\s*(?:const\s*)?>\s*\(\s*(&\s*[\w:]+\s*::\s*[A-Za-z_]\w*)\s*\)")


class QtCppError(Exception):
    """A bounded stage code is safe to publish instead of backend exception text."""

    def __init__(self, code: str, message: str, *, span: dict | None = None):
        self.code, self.span = code, span
        super().__init__(message)


def blank(source: bytes) -> bytes:
    return re.sub(rb"[^\r\n]", b" ", source)


def lexical_code(source: bytes) -> bytes:
    """Mask comments/quoted/raw literals in place, including continued comments."""
    result, index = bytearray(source), 0
    while index < len(source):
        # C++ preprocessing numbers own digit separators. Skip their complete
        # lexical token before testing apostrophes as character-literal starts;
        # the parser still validates the unchanged numeric syntax itself.
        number = _NUMBER.match(source, index)
        if number and (index == 0 or source[index - 1] not in b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"):
            index = number.end()
            continue
        start, end = index, index
        if source[index:index + 2] == b"//":
            end = index + 2
            while end < len(source):
                if source[end:end + 1] == b"\n" and source[end - 1:end] != b"\\" and source[end - 2:end] != b"\\\r":
                    break
                end += 1
        elif source[index:index + 2] == b"/*":
            close = source.find(b"*/", index + 2)
            end = len(source) if close < 0 else close + 2
        else:
            raw = _RAW_STRING.match(source, index)
            if raw:
                close = source.find(b")" + raw[1] + b'"', raw.end())
                end = len(source) if close < 0 else close + len(raw[1]) + 2
            elif source[index:index + 1] in {b'"', b"'"}:
                quote, end = source[index], index + 1
                while end < len(source):
                    if source[end] == 92:
                        end += 2
                    elif source[end] == quote:
                        end += 1
                        break
                    else:
                        end += 1
        if end > start:
            end = min(end, len(source))
            result[start:end] = blank(source[start:end])
            index = end
        else:
            index += 1
    return bytes(result)


def split_arguments(source: bytes) -> list[str]:
    """Split literal call arguments while preserving nested expressions as opaque text."""
    code, depth, start, values = lexical_code(source), 0, 0, []
    for index, char in enumerate(code):
        if char in b"([{<":
            depth += 1
        elif char in b")]}>" and depth:
            depth -= 1
        elif char == 44 and not depth:
            values.append(source[start:index].decode().strip())
            start = index + 1
    if source.strip():
        values.append(source[start:].decode().strip())
    return values


def source_span(source: bytes, start: int, end: int) -> dict:
    result = {"start_byte": start, "end_byte": end}
    for side, offset in (("start", start), ("end", end)):
        prefix = source[:offset]
        result[side + "_row"] = prefix.count(b"\n")
        result[side + "_column"] = offset - prefix.rfind(b"\n") - 1
    return result


def walk(node):
    """Iterative traversal has the same explicit work bounds as parser admission."""
    pending = [(node, 0)]
    count = 0
    while pending:
        current, depth = pending.pop()
        count += 1
        if count > 100_000 or depth > 256:
            raise QtCppError("QT_CPP_LIMIT", "Qt C++ AST exceeds size/depth bounds")
        yield current
        pending.extend((child, depth + 1) for child in reversed(current.named_children))


@dataclass
class CppUnit:
    path: Path
    relative_file: str
    source: bytes
    code: bytes
    parsed_source: bytes
    tree: Node
    macros: list[dict]
    member_pointers: tuple[dict, ...] = ()
    qt_test_macros: tuple[dict, ...] = ()
    test_launchers: tuple[dict, ...] = ()
    include_guards: IncludeGuardIndex = field(init=False, repr=False)

    def __post_init__(self):
        self.include_guards = IncludeGuardIndex(self.tree)

    @property
    def root(self):
        return self.tree

    def text(self, node) -> str:
        return self.source[node.start_byte:node.end_byte].decode() if node else ""

    def field(self, node, name: str) -> str:
        return self.text(node.child_by_field_name(name)) if node else ""


def _normalized(source: bytes, code: bytes, qt_test_context=None):
    """Known Qt annotation spellings become whitespace, preserving every offset."""
    parsed, macros = bytearray(source), []
    # Raw AST roles protect clean ordinary declarations before any annotation
    # bytes are blanked. A spelling alone never erases a field/callable name.
    raw_tree = _parse_cpp(source)
    tests = test_candidates(source, code, raw_tree, walk=walk, parse=_parse_cpp, error=QtCppError, macro=_MACRO, context=qt_test_context)
    launchers = launcher_candidates(source, code, raw_tree, context=qt_test_context, parse=_parse_cpp, walk=walk, macro=_MACRO, error=QtCppError)
    data_payloads, data_cursor = sorted([item for item in tests if item["kind"] == "test_data"] + launchers, key=lambda item: item["start"]), 0
    ordinary = ordinary_spans(source, raw_tree, walk=walk, macro=_MACRO)
    overrides = annotation_overrides(code, _MACRO)
    # The bundled grammar rejects valid explicit member-pointer overload casts.
    # Keep only the inner pointer in its original byte position for AST recovery;
    # native selectors consume the unchanged source/code views and full signature.
    for match in _MEMBER_CAST.finditer(code):
        start, end = match.span()
        parsed[start:end] = blank(source[start:end])
        parsed[match.start(1):match.end(1)] = source[match.start(1):match.end(1)]
    consumed_annotation_end = 0
    for match in _MACRO.finditer(annotation_code(code)):
        start, end = match.span()
        # Payload tokens belong to their outer annotation. For example,
        # QML_NAMED_ELEMENT stringifies Q_OBJECT as a name; rescanning that
        # argument would fabricate metaobject/access/invokable authority.
        if start < consumed_annotation_end or identifier_fragment(raw_tree, start, end):
            continue
        while data_cursor < len(data_payloads) and data_payloads[data_cursor]["end"] <= start:
            data_cursor += 1
        if data_cursor < len(data_payloads) and data_payloads[data_cursor]["start"] < start < data_payloads[data_cursor]["end"]:
            continue
        if (start, end) in ordinary:
            continue
        line_start = code.rfind(b"\n", 0, start) + 1
        if code[line_start:start].lstrip().startswith(b"#"):
            continue
        cursor = end
        while cursor < len(code) and code[cursor] in b" \t\r\n":
            cursor += 1
        args, parenthesized = [], cursor < len(code) and code[cursor] == 40
        if cursor < len(code) and code[cursor] == 40:
            depth, argument_start = 1, cursor + 1
            cursor += 1
            while cursor < len(code) and depth:
                depth += (code[cursor] == 40) - (code[cursor] == 41)
                cursor += 1
            if depth:
                raise QtCppError("QT_CPP_SYNTAX", "Qt annotation parentheses are incomplete")
            end, args = cursor, split_arguments(source[argument_start:cursor - 1])
        name = match[0].decode()
        if overrides.get(name, len(code)) < start:
            raise QtCppError("QT_CPP_SYNTAX", "Locally overridden Qt annotation is outside the supported profile",
                             span=source_span(source, start, end))
        if not valid_new_annotation(name, args, parenthesized=parenthesized):
            raise QtCppError("QT_CPP_SYNTAX", "Qt annotation form is outside the supported profile",
                             span=source_span(source, start, end))
        macros.append({"name": name, "start_byte": start, "end_byte": end,
                       "args": args, "span": source_span(source, start, end)})
        consumed_annotation_end = end
        parsed[start:end] = blank(source[start:end])
        if name in {"Q_SIGNALS", "Q_SLOTS"} and code[end:].lstrip().startswith(b":"):
            if name == "Q_SIGNALS" or not re.search(rb"\b(?:public|protected|private)\s*$", code[line_start:start]):
                parsed[start:start + 6] = b"public"
        elif name in {"SIGNAL", "SLOT"} and args:
            parsed[start:start + 1] = b"0"
    # SDK syntax preserves directives; overridden emission prefixes cannot become calls.
    emit_override = annotation_overrides(code, re.compile(rb"emit")).get("emit")
    for match in re.finditer(rb"\b(signals|slots|emit)\b", annotation_code(code)):
        start, end = match.span()
        if identifier_fragment(raw_tree, start, end):
            continue
        after = code[end:].lstrip()
        if match[0] == b"signals" and after.startswith(b":"):
            parsed[start:end] = b"public "
        elif match[0] == b"slots" and after.startswith(b":"):
            parsed[start:end] = b" " * (end - start)
        elif match[0] == b"emit" and re.match(rb"[A-Za-z_]", after):
            if emit_override is not None and emit_override < start:
                raise QtCppError("QT_CPP_SYNTAX", "Locally overridden Qt annotation is outside the supported profile",
                                 span=source_span(source, start, end))
            parsed[start:end] = b" " * (end - start)
    normalized = recover_cpp_syntax(recover_launchers(bytes(parsed), launchers), code, parse=_parse_cpp, walk=walk)
    normalized = recover_member_pointers(normalized, code, parse=_parse_cpp, walk=walk, span=source_span)
    normalized = recover_test_macros(normalized, tests, parse=_parse_cpp, walk=walk, error=QtCppError)
    launchers = finish_launchers(source, normalized, launchers, parse=_parse_cpp, walk=walk, span=source_span, error=QtCppError)
    # Annotation-heavy raw input may misparse a method as an initializer. Its
    # recovered declaration tree owns scope validation; original offsets still
    # identify every marker, including one illegally placed in a method body.
    scopes = annotation_scopes(_parse_cpp(normalized), walk=walk)
    invalid = next((item for item in macros if not valid_annotation_scope(item["name"], item["start_byte"], scopes)), None)
    if invalid:
        raise QtCppError("QT_CPP_SYNTAX", "Qt annotation scope is outside the supported profile", span=invalid["span"])
    return normalized, macros, tests, launchers


def _parse_cpp(source: bytes) -> Node:
    """Compatibility recovery and final admission share the parser diagnostic."""
    try:
        return Parser(Language(tree_sitter_cpp.language())).parse(source).root_node
    except Exception as exc:
        raise QtCppError("QT_CPP_PARSER", "Cannot parse Qt C++ source") from exc


def normalize_qt_cpp(source: bytes, *, qt_test_context=None, original_source=None) -> bytes | None:
    """Generic C++ parsing shares offset-preserving recovery without Qt overlays.

    Invalid annotation recovery remains the overlay's explicit safety failure;
    the generic extractor retains its existing malformed-input behavior.
    """
    validate_test_context(qt_test_context, source if original_source is None else original_source)
    if len(source) > MAX_CPP_BYTES:
        return None
    code = lexical_code(source)
    if not needs_recovery(code) and not has_member_pointer(code) and not needs_test_recovery(code) and not needs_launcher_recovery(code) and not _MACRO.search(code) and not re.search(rb"\b(?:signals|slots)\s*:|\bemit\s+[A-Za-z_]|\bQObject\s*::\s*(?:connect|disconnect)\s*\(", code):
        return None
    try:
        normalized, _, _, _ = _normalized(source, code, qt_test_context)
    except QtCppError:
        return None
    return normalized if normalized != source else None


def read_cpp(path: Path, root: Path, *, qt_test_context=None) -> CppUnit:
    """Read one already-admitted source; Qt overlays never discover more files."""
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise QtCppError("QT_CPP_ROOT", "Qt C++ source is outside the scan root") from exc
    try:
        if path.stat().st_size > MAX_CPP_BYTES:
            raise QtCppError("QT_CPP_LIMIT", "Qt C++ source exceeds 5 MB")
        with path.open("rb") as stream:
            source = stream.read(MAX_CPP_BYTES + 1)
        source.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise QtCppError("QT_CPP_READ", "Cannot read UTF-8 Qt C++ source") from exc
    if len(source) > MAX_CPP_BYTES:
        raise QtCppError("QT_CPP_LIMIT", "Qt C++ source exceeds 5 MB")
    try:
        validate_test_context(qt_test_context, source)
    except QtTestContextError as exc:
        raise QtCppError("QT_CPP_CONTEXT", str(exc)) from exc
    code = lexical_code(source)
    normalized, macros, tests, launchers = _normalized(source, code, qt_test_context)
    tree = _parse_cpp(normalized)
    list(walk(tree))
    if tree.has_error:
        raise QtCppError("QT_CPP_SYNTAX", "Qt C++ syntax is incomplete or outside the supported profile")
    return CppUnit(path, relative, source, code, normalized, tree, macros,
                   member_pointer_records(source, normalized, tree=tree), test_macro_records(source, tests, span=source_span), launchers)
