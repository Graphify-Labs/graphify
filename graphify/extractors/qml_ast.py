"""Lazy offline parser loading and bounded QML input validation."""
from __future__ import annotations

from pathlib import Path
from graphify.extractors.qml_source_identity import relative_qml_source


class QmlInputError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def load_parser():
    try:
        from tree_sitter_language_pack import get_parser
    except ImportError as exc:
        raise QmlInputError("QML_PARSER_MISSING", "QML parser not installed; install graphifyy[qml]") from exc
    try:
        return get_parser("qmljs")
    except Exception as exc:
        raise QmlInputError("QML_PARSER_LOAD", "QML parser failed to load; reinstall the pinned qml extra") from exc


def parse_source(path: Path):
    try:
        if path.stat().st_size > 5_000_000:
            raise QmlInputError("QML_LIMIT", "QML input exceeds 5 MB")
        with path.open("rb") as stream:
            source = stream.read(5_000_001)
        source.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise QmlInputError("QML_READ", "Cannot read UTF-8 QML source") from exc
    if len(source) > 5_000_000:
        raise QmlInputError("QML_LIMIT", "QML input exceeds 5 MB")
    try:
        tree = load_parser().parse(source)
    except QmlInputError:
        raise
    except Exception as exc:
        raise QmlInputError("QML_PARSER_LOAD", "QML parser failed to load or parse source; reinstall the pinned extra") from exc
    # Empty editor files are explicit facts, not executable QML components.
    if not source.strip():
        return source, tree.root_node, True
    if tree.root_node.has_error:
        raise QmlInputError("QML_SYNTAX", "QML syntax is incomplete or invalid; fix source before publication")
    if any(child.type not in {"comment", "ui_pragma", "ui_import", "ui_object_definition"}
           for child in tree.root_node.named_children):
        raise QmlInputError("QML_UNSUPPORTED", "Unsupported top-level QML syntax in this profile")
    pending = [(tree.root_node, 0)]
    count = 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > 100_000 or depth > 256:
            raise QmlInputError("QML_LIMIT", "QML AST exceeds the supported size/depth bound")
        pending.extend((child, depth + 1) for child in node.named_children)
    return source, tree.root_node, False


def failure(path: Path, root: Path | None, error: Exception) -> dict:
    try:
        # Diagnostics borrow the admitted lexical label without creating facts
        # or target authority. A failed identity lookup must not rethrow here.
        name = relative_qml_source(path, root)
    except (OSError, RuntimeError, ValueError):
        name = "" if getattr(error, "code", "") == "SOURCE_INPUT_IDENTITY_FAILED" else path.name
    code = getattr(error, "code", "QML_ROOT" if str(error).startswith("QML_ROOT:") else "QML_LIMIT")
    diagnostic = {"code": code, "severity": "error", "source_file": name,
                  "owner": "qml", "message": str(error),
                  "recovery": "Correct source or install the qml extra, then retry; prior graph is preserved."}
    return {"nodes": [], "edges": [], "error": str(error),
            "diagnostics": [diagnostic], "qml_failures": [{"code": code, "source_file": name}]}
