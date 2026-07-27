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


def _blank_spans(src: str, pattern: "re.Pattern[str]") -> str:
    """Replace every match of *pattern* with newlines and spaces of equal length.

    Used to strip comments before a regex-based extractor scans a file, without
    disturbing byte offsets — so reported ``L<n>`` locations still refer to the
    real line in the original source. Matters because component docblocks
    routinely contain example usage (``{# Usage: {% include 'theme:card' %} #}``)
    that would otherwise be extracted as a real dependency, giving the component
    a spurious edge to itself.
    """
    return pattern.sub(
        lambda m: "".join("\n" if ch == "\n" else " " for ch in m.group(0)), src
    )


def _corpus_relative_path(resolved: Path, referrer: Path) -> str:
    """Express *resolved* the same way *referrer* is, for node-ID parity.

    A file node's ID is ``_make_id(str(path))`` for whatever path form the
    extractor was handed. An extractor that resolves a cross-file reference to an
    absolute path while the corpus was scanned relatively would mint a second,
    disconnected node for a file that already has one, so match the referrer's
    form. Mirrors the inline normalization in ``extract_bash``.
    """
    target = resolved.resolve()
    if not referrer.is_absolute():
        try:
            target = target.relative_to(Path.cwd().resolve())
        except ValueError:
            pass
    return str(target)
