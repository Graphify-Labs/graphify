"""Shared primitives for per-language extractors.

Moved verbatim from graphify/extract.py as part of the incremental split
(see MIGRATION.md in this directory). This module must not import from
graphify.extract — import direction is strictly extract.py -> extractors/.
"""
from __future__ import annotations

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
})


def _make_id(*parts: str) -> str:
    r"""Build a stable node ID from one or more name parts.

    Thin wrapper over :func:`graphify.ids.make_id`, the single source of truth
    shared with ``build._normalize_id`` so the two can no longer drift (#811).
    Preserves Unicode letters/digits (CJK, Cyrillic, Arabic, accented Latin,
    etc.) so non-ASCII identifiers produce distinct IDs and don't collapse to a
    single per-file node; NFKC normalization collapses composed/decomposed forms
    of the same character (e.g. é vs e+combining-acute) to one ID.
    """
    return make_id(*parts)


def _file_stem(path: Path) -> str:
    """Return a stem qualified with the parent directory name to avoid ID collisions
    when multiple files share the same filename in different directories (#550)."""
    parent = path.parent.name
    if parent and parent not in (".", ""):
        return f"{parent}.{path.stem}"
    return path.stem


def _read_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
