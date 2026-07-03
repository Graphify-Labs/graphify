# DO NOT import from graphify.extract here — direction is extract.py → extractors/ only.
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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


# ── LanguageConfig dataclass ─────────────────────────────────────────────────

@dataclass
class LanguageConfig:
    ts_module: str                                   # e.g. "tree_sitter_python"
    ts_language_fn: str = "language"                 # attr to call: e.g. tslang.language()

    class_types: frozenset = frozenset()
    function_types: frozenset = frozenset()
    import_types: frozenset = frozenset()
    call_types: frozenset = frozenset()
    static_prop_types: frozenset = frozenset()
    helper_fn_names: frozenset = frozenset()
    container_bind_methods: frozenset = frozenset()
    event_listener_properties: frozenset = frozenset()

    # Name extraction
    name_field: str = "name"
    name_fallback_child_types: tuple = ()

    # Body detection
    body_field: str = "body"
    body_fallback_child_types: tuple = ()   # e.g. ("declaration_list", "compound_statement")

    # Call name extraction
    call_function_field: str = "function"           # field on call node for callee
    call_accessor_node_types: frozenset = frozenset()  # member/attribute nodes
    call_accessor_field: str = "attribute"          # field on accessor for method name
    call_accessor_object_field: str = ""            # field on accessor for the receiver/object

    # Stop recursion at these types in walk_calls
    function_boundary_types: frozenset = frozenset()

    # Import handler: called for import nodes instead of generic handling
    import_handler: Callable | None = None

    # Optional custom name resolver for functions (C, C++ declarator unwrapping)
    resolve_function_name_fn: Callable | None = None

    # Extra label formatting for functions: if True, functions get "name()" label
    function_label_parens: bool = True

    # Extra walk hook called after generic dispatch (for JS arrow functions, C# namespaces, etc.)
    extra_walk_fn: Callable | None = None
