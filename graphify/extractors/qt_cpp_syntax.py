"""Bounded C++ source views for Qt overlays; no preprocessing or corpus execution."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from tree_sitter import Language, Node, Parser
import tree_sitter_cpp

MAX_CPP_BYTES = 5_000_000
_MACRO = re.compile(rb"\b(?:QML_[A-Z_]+|Q_(?:OBJECT|GADGET|PROPERTY|INVOKABLE|SIGNAL|SLOT|SIGNALS|SLOTS|ENUM(?:_NS)?|FLAG(?:_NS)?|REVISION|CLASSINFO|INTERFACES|DECLARE_METATYPE|EMIT)|SIGNAL|SLOT)\b")
_RAW_STRING = re.compile(rb'(?:u8|u|U|L)?R"([^\s()\\]{0,16})\(')
_MEMBER_CAST = re.compile(rb"\bstatic_cast\s*<[\w:\s*&<>]+\(\s*[\w:]+\s*::\s*\*\s*\)\s*\([\w:\s*&<>,]*\)\s*(?:const\s*)?>\s*\(\s*(&\s*[\w:]+\s*::\s*[A-Za-z_]\w*)\s*\)")


class QtCppError(Exception):
    """A bounded stage code is safe to publish instead of backend exception text."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def blank(source: bytes) -> bytes:
    return re.sub(rb"[^\r\n]", b" ", source)


def lexical_code(source: bytes) -> bytes:
    """Mask comments/quoted/raw literals in place, including continued comments."""
    result, index = bytearray(source), 0
    while index < len(source):
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

    @property
    def root(self):
        return self.tree

    def text(self, node) -> str:
        return self.source[node.start_byte:node.end_byte].decode() if node else ""

    def field(self, node, name: str) -> str:
        return self.text(node.child_by_field_name(name)) if node else ""


def _normalized(source: bytes, code: bytes):
    """Known Qt annotation spellings become whitespace, preserving every offset."""
    parsed, macros = bytearray(source), []
    # The bundled grammar rejects valid explicit member-pointer overload casts.
    # Keep only the inner pointer in its original byte position for AST recovery;
    # native selectors consume the unchanged source/code views and full signature.
    for match in _MEMBER_CAST.finditer(code):
        start, end = match.span()
        parsed[start:end] = blank(source[start:end])
        parsed[match.start(1):match.end(1)] = source[match.start(1):match.end(1)]
    for match in _MACRO.finditer(code):
        start, end = match.span()
        line_start = code.rfind(b"\n", 0, start) + 1
        if code[line_start:start].lstrip().startswith(b"#"):
            continue
        cursor = end
        while cursor < len(code) and code[cursor] in b" \t\r\n":
            cursor += 1
        args = []
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
        macros.append({"name": name, "start_byte": start, "end_byte": end,
                       "args": args, "span": source_span(source, start, end)})
        parsed[start:end] = blank(source[start:end])
        if name in {"Q_SIGNALS", "Q_SLOTS"} and code[end:].lstrip().startswith(b":"):
            if name == "Q_SIGNALS" or not re.search(rb"\b(?:public|protected|private)\s*$", code[line_start:start]):
                parsed[start:start + 6] = b"public"
        elif name in {"SIGNAL", "SLOT"} and args:
            parsed[start:start + 1] = b"0"
    # Native section keywords and emissions are syntax annotations, not calls.
    for match in re.finditer(rb"\b(signals|slots|emit)\b", code):
        start, end = match.span()
        after = code[end:].lstrip()
        if match[0] == b"signals" and after.startswith(b":"):
            parsed[start:end] = b"public "
        elif match[0] == b"slots" and after.startswith(b":"):
            parsed[start:end] = b" " * (end - start)
        elif match[0] == b"emit" and re.match(rb"[A-Za-z_]", after):
            parsed[start:end] = b" " * (end - start)
    return bytes(parsed), macros


def normalize_qt_cpp(source: bytes) -> bytes | None:
    """Generic C++ parsing shares offset-preserving recovery without Qt overlays.

    Invalid annotation recovery remains the overlay's explicit safety failure;
    the generic extractor retains its existing malformed-input behavior.
    """
    if len(source) > MAX_CPP_BYTES:
        return None
    code = lexical_code(source)
    if not _MACRO.search(code) and not re.search(rb"\b(?:signals|slots)\s*:|\bemit\s+[A-Za-z_]|\bQObject\s*::\s*(?:connect|disconnect)\s*\(", code):
        return None
    try:
        normalized, _ = _normalized(source, code)
    except QtCppError:
        return None
    return normalized if normalized != source else None


def read_cpp(path: Path, root: Path) -> CppUnit:
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
    code = lexical_code(source)
    normalized, macros = _normalized(source, code)
    try:
        tree = Parser(Language(tree_sitter_cpp.language())).parse(normalized).root_node
    except Exception as exc:
        raise QtCppError("QT_CPP_PARSER", "Cannot parse Qt C++ source") from exc
    list(walk(tree))
    if tree.has_error:
        raise QtCppError("QT_CPP_SYNTAX", "Qt C++ syntax is incomplete or outside the supported profile")
    return CppUnit(path, relative, source, code, normalized, tree, macros)
