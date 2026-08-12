# DO NOT import from graphify.extract here — direction is extract.py → extractors/ only.
from __future__ import annotations

import re
from pathlib import Path

from graphify.ids import make_id

# Language built-in globals that AST may classify as call targets when used as
# constructors or coercion functions (e.g. String(x), Number(x), Boolean(x)).
# Without this filter they become god-nodes accumulating spurious edges from
# every call site. Filter applied at same-file and cross-file resolution.
# See issue #726.
_LANGUAGE_BUILTIN_GLOBALS: frozenset[str] = frozenset({
    # JavaScript / TypeScript ECMAScript built-ins
    "String", "Number", "Boolean", "Object", "Array", "Symbol", "BigInt",
    "Date", "RegExp", "Error", "TypeError", "RangeError", "SyntaxError",
    "ReferenceError", "EvalError", "URIError",
    "Promise", "Map", "Set", "WeakMap", "WeakSet", "JSON", "Math",
    "Reflect", "Proxy", "Intl",
    "parseInt", "parseFloat", "isNaN", "isFinite",
    "encodeURIComponent", "decodeURIComponent", "encodeURI", "decodeURI",
    # Browser / Node common globals
    "URL", "URLSearchParams", "FormData", "Blob", "File",
    "Headers", "Request", "Response", "AbortController", "AbortSignal",
    "TextEncoder", "TextDecoder", "console",
    # Python built-in callables
    "str", "int", "float", "bool", "list", "dict", "set", "tuple", "bytes",
    "len", "range", "enumerate", "zip", "map", "filter", "sum", "min", "max",
    "print", "open", "isinstance", "type", "super", "sorted", "reversed",
    "any", "all", "abs", "round", "next", "iter", "hash", "id", "repr",
    "callable", "getattr", "setattr", "hasattr", "delattr", "vars", "dir",
    # Swift standard library / Foundation / SwiftUI (#2147). Value-type
    # initializers (Data(x), Int(x), UUID()) and protocol conformance targets
    # appear from virtually every file of a Swift codebase, exactly like the
    # ECMAScript constructors above. String/Date/URL/Error are already listed.
    "Int", "Int8", "Int16", "Int32", "Int64",
    "UInt", "UInt8", "UInt16", "UInt32", "UInt64",
    "Double", "Float", "Bool", "Character",
    "Sendable", "Codable", "Decodable", "Encodable", "Equatable", "Hashable",
    "Identifiable", "Comparable", "CaseIterable", "RawRepresentable",
    "CustomStringConvertible", "CustomDebugStringConvertible", "AnyObject",
    "LocalizedError",
    "Data", "UUID", "Decimal", "Calendar", "Locale", "TimeZone", "Bundle",
    "IndexPath", "IndexSet", "NotificationCenter", "UserDefaults",
    "FileManager", "URLSession", "URLRequest", "URLComponents",
    "JSONDecoder", "JSONEncoder", "DateFormatter", "NumberFormatter",
    "ISO8601DateFormatter",
    "NSObject", "NSString", "NSError", "NSLock", "NSAttributedString",
    "DispatchQueue", "DispatchGroup", "OperationQueue", "RunLoop",
    "View", "Color", "Font",
})

# Languages that allow quoting an operator as an identifier (R's
# `%||%` <- function(a, b) ...) need it turned into an id-safe name before
# `make_id` sees it. `make_id`/`normalize_id` replace every non-word run with
# a single underscore, so an all-symbol name has no word characters left and
# collapses to the empty string — `make_id(stem, "%||%")` then equals
# `make_id(stem)`, i.e. the FILE node's own id, producing a same-file-vs-
# operator self-loop instead of a distinct node. Shared here (not per-
# language) because both the extractor that defines the operator and the
# cross-file resolver that looks it up by name must agree on the same id.
_OP_CHAR_NAMES: dict[str, str] = {
    "%": "pct", "|": "pipe", "&": "amp", "/": "slash", "+": "plus",
    "-": "minus", "*": "star", "^": "caret", "<": "lt", ">": "gt",
    "=": "eq", "!": "bang", "~": "tilde", "?": "qmark", ":": "colon",
    "@": "at", "$": "dollar",
}


def _symbol_safe_name(name: str) -> str:
    """ASCII-transliterate an all-symbol identifier for id-building.

    A name with at least one word character is returned unchanged — normal
    identifiers don't need this and `make_id` handles them correctly already.
    """
    if re.sub(r"\W+", "", name, flags=re.UNICODE):
        return name
    return "".join(_OP_CHAR_NAMES.get(c, "x") for c in name) or "op"


def _make_id(*parts: str) -> str:
    return make_id(*parts)


def _file_stem(path: Path) -> str:
    """Stem used as the node-ID prefix for a file and its symbols.

    The full path (extension dropped) is preserved as path segments; ``make_id``
    later collapses the separators to underscores. Using every segment — not just
    the immediate parent dir (#1504) — means same-named files in different
    directories get distinct IDs instead of colliding into one
    last-writer-wins node:

        docs/v1/api/README.md -> docs/v1/api/README -> docs_v1_api_readme
        docs/v2/api/README.md -> docs/v2/api/README -> docs_v2_api_readme

    Top-level files keep a bare stem (``setup.py`` -> ``setup``). When passed an
    absolute path the whole path is encoded; the extract() id-remap post-pass
    re-derives the canonical repo-relative form from ``source_file`` so the on-disk
    location can't leak into the persisted IDs (#502).

    Returns "" for a path with no name (``Path('.')`` — a source_file that equals
    the scan root, so it has no per-file stem). Guarding here keeps
    ``path.with_suffix("")`` from raising ``ValueError: '.' has an empty name`` and
    protects every caller, not just ``_semantic_id_remap`` (#1618)."""
    if not path.name:
        return ""
    return path.with_suffix("").as_posix()


def _read_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
