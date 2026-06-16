"""Shared utilities for all extractors."""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Callable

_RECURSION_LIMIT = 10_000

_LANGUAGE_BUILTIN_GLOBALS: frozenset[str] = frozenset(
    {
        "String",
        "Number",
        "Boolean",
        "Object",
        "Array",
        "Symbol",
        "BigInt",
        "Date",
        "RegExp",
        "Error",
        "TypeError",
        "RangeError",
        "SyntaxError",
        "ReferenceError",
        "EvalError",
        "URIError",
        "Promise",
        "Map",
        "Set",
        "WeakMap",
        "WeakSet",
        "JSON",
        "Math",
        "Reflect",
        "Proxy",
        "Intl",
        "parseInt",
        "parseFloat",
        "isNaN",
        "isFinite",
        "encodeURIComponent",
        "decodeURIComponent",
        "encodeURI",
        "decodeURI",
        "URL",
        "URLSearchParams",
        "FormData",
        "Blob",
        "File",
        "Headers",
        "Request",
        "Response",
        "AbortController",
        "AbortSignal",
        "TextEncoder",
        "TextDecoder",
        "console",
        "str",
        "int",
        "float",
        "bool",
        "list",
        "dict",
        "set",
        "tuple",
        "bytes",
        "len",
        "range",
        "enumerate",
        "zip",
        "map",
        "filter",
        "sum",
        "min",
        "max",
        "print",
        "open",
        "isinstance",
        "type",
        "super",
        "sorted",
        "reversed",
        "any",
        "all",
        "abs",
        "round",
        "next",
        "iter",
        "hash",
        "id",
        "repr",
        "callable",
        "getattr",
        "setattr",
        "hasattr",
        "delattr",
        "vars",
        "dir",
    }
)


def raise_recursion_limit() -> None:
    if sys.getrecursionlimit() < _RECURSION_LIMIT:
        sys.setrecursionlimit(_RECURSION_LIMIT)


def safe_extract(extractor: Callable, path: Path) -> dict:
    try:
        return extractor(path)
    except RecursionError:
        print(f"  warning: skipped {path} (recursion limit exceeded)", file=sys.stderr, flush=True)
        return {"nodes": [], "edges": [], "error": "recursion_limit_exceeded"}
    except Exception as e:
        if os.environ.get("GRAPHIFY_DEBUG"):
            import traceback

            traceback.print_exc(file=sys.stderr)
        print(f"  warning: skipped {path} ({type(e).__name__}: {e})", file=sys.stderr, flush=True)
        return {"nodes": [], "edges": [], "error": f"{type(e).__name__}: {e}"}


def make_id(*parts: str) -> str:
    r"""Build a stable node ID from one or more name parts.

    Preserves Unicode letters/digits (CJK, Cyrillic, Arabic, accented Latin,
    etc.) so non-ASCII identifiers produce distinct IDs and don't collapse to
    a single per-file node (#811). NFKC normalization ensures composed and
    decomposed forms of the same character (e.g. é vs e+combining-acute)
    produce the same ID. Must stay in sync with build._normalize_id.
    """
    combined = "_".join(p.strip("_.") for p in parts if p)
    combined = unicodedata.normalize("NFKC", combined)
    cleaned = re.sub(r"[^\w]+", "_", combined, flags=re.UNICODE)
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("_").casefold()


def file_stem(path: Path) -> str:
    """Return a stem qualified with the parent directory name to avoid ID collisions
    when multiple files share the same filename in different directories (#550)."""
    parent = path.parent.name
    if parent and parent not in (".", ""):
        return f"{parent}.{path.stem}"
    return path.stem


def file_node_id(rel_path: Path) -> str:
    """File-level node ID matching the skill.md spec: ``{parent_dir}_{stem}`` —
    one parent directory level, no extension. ``rel_path`` MUST be relative to
    the project root so top-level files collapse to a bare stem (``setup.py`` ->
    ``setup``) instead of picking up the root directory name. This must equal the
    ID semantic subagents generate, or AST and semantic extraction split a file
    into two disconnected ghost nodes (#1033)."""
    return make_id(file_stem(rel_path))
