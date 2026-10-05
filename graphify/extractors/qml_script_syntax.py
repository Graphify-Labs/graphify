"""Bounded JS parsing with byte-preserving Qt directives; no evaluation/import IO."""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.qml_ast import QmlInputError

_PRAGMA = re.compile(rb'\s*\.pragma\s+library\s*(?://[^\r\n]*)?$')
_IMPORT = re.compile(rb'\s*\.import\s+["\']([^"\'\r\n]+)["\']\s+as\s+([A-Za-z_$][\w$]*)\s*(?://[^\r\n]*)?$')


def _next_state(line: bytes, state: str) -> str:
    """Directives inside comments/templates/continued strings are ordinary text."""
    position = 0
    while position < len(line):
        char = line[position:position + 1]
        pair = line[position:position + 2]
        if state == "comment":
            if pair == b"*/":
                state, position = "", position + 2
            else:
                position += 1
        elif state:
            if char == b"\\":
                position += 2
            elif char == state.encode():
                state, position = "", position + 1
            else:
                position += 1
        elif pair == b"//":
            break
        elif pair == b"/*":
            state, position = "comment", position + 2
        elif char in {b'"', b"'", b"`"}:
            state, position = char.decode(), position + 1
        else:
            position += 1
    return state


def parse_script(path: Path):
    """Return original bytes, a same-offset tree and literal Qt directive facts."""
    try:
        if path.stat().st_size > 5_000_000:
            raise QmlInputError("QML_SCRIPT_LIMIT", "QML imported script exceeds 5 MB")
        with path.open("rb") as stream:
            source = stream.read(5_000_001)
        source.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise QmlInputError("QML_SCRIPT_READ", "Cannot read UTF-8 QML imported script") from exc
    if len(source) > 5_000_000:
        raise QmlInputError("QML_SCRIPT_LIMIT", "QML imported script exceeds 5 MB")
    masked, directives, state, offset = [], [], "", 0
    for row, line in enumerate(source.splitlines(keepends=True)):
        body = line.rstrip(b"\r\n")
        pragma, imported = (_PRAGMA.fullmatch(body), _IMPORT.fullmatch(body)) if not state else (None, None)
        if pragma or imported:
            directives.append({"kind": "pragma" if pragma else "import", "start_byte": offset,
                               "end_byte": offset + len(body), "row": row,
                               "value": imported[1].decode() if imported else "library",
                               "qualifier": imported[2].decode() if imported else ""})
            masked.append(b" " * len(body) + line[len(body):])
        else:
            masked.append(line)
            state = _next_state(line, state)
        offset += len(line)
    if path.suffix.lower() == ".mjs" and directives:
        raise QmlInputError("QML_SCRIPT_UNSUPPORTED", "Qt directives belong to classic .js scripts, not ECMAScript modules")
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_javascript
        tree = Parser(Language(tree_sitter_javascript.language())).parse(b"".join(masked))
    except Exception as exc:
        raise QmlInputError("QML_SCRIPT_PARSER", "Cannot load the JavaScript parser for a QML import") from exc
    if tree.root_node.has_error:
        raise QmlInputError("QML_SCRIPT_SYNTAX", "QML imported script syntax is incomplete or invalid")
    pending, count = [(tree.root_node, 0)], 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > 100_000 or depth > 256:
            raise QmlInputError("QML_SCRIPT_LIMIT", "QML imported script exceeds AST size/depth bounds")
        pending.extend((child, depth + 1) for child in node.named_children)
    return source, tree.root_node, directives
