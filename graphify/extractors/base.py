# DO NOT import from graphify.extract here — direction is extract.py → extractors/ only.
from __future__ import annotations

import sys
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


_UTF32_BOMS = (b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")
_UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")
# Fixed, not the host locale: extraction must give the same graph on every
# machine (CONTRIBUTING: deterministic extraction).
_SOURCE_FALLBACK_ENCODINGS = ("cp1252", "latin-1")
_warned_source_encodings: set[str] = set()


def _read_source_bytes(path: Path, *, warn: bool = True) -> bytes:
    """Read a source file as the UTF-8 bytes tree-sitter parses.

    tree-sitter treats its input as UTF-8. Raw bytes in another encoding were
    parsed as-is: a UTF-16 file (interleaved NUL bytes) produced no nodes at
    all, and a Windows-1252 identifier was cut at its first non-UTF-8 byte
    (``CaféOrder`` came out as ``Order``) — both silently.

    Valid UTF-8, with or without a BOM, is returned byte-for-byte, so node ids,
    byte offsets and cache keys for those files are unchanged. A UTF-16 or
    UTF-32 file with a BOM is decoded exactly and re-encoded as UTF-8. Anything
    else is decoded as cp1252, then latin-1 (which cannot fail), so names come
    out whole; line numbers are unchanged in every case. ``warn`` names the file
    once per process on that last, guessed path — pass ``warn=False`` from
    secondary passes that re-read a file the extractor already read.
    """
    raw = path.read_bytes()
    if raw.isascii():
        return raw
    try:
        raw.decode("utf-8")
        return raw
    except UnicodeDecodeError:
        pass
    for boms, encoding in ((_UTF32_BOMS, "utf-32"), (_UTF16_BOMS, "utf-16")):
        if raw.startswith(boms):
            try:
                return raw.decode(encoding).encode("utf-8")
            except UnicodeDecodeError:
                continue  # FF FE 00 00 is also UTF-16-LE: BOM + U+0000
    for encoding in _SOURCE_FALLBACK_ENCODINGS:
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        key = str(path)
        if warn and key not in _warned_source_encodings:
            _warned_source_encodings.add(key)
            print(
                f"[graphify] WARNING: {path} is not valid UTF-8; read it as {encoding}. "
                "Re-save it as UTF-8 if names in the graph look wrong.",
                file=sys.stderr,
            )
        return text.encode("utf-8")
    return raw  # unreachable: latin-1 decodes every byte


def _read_source_text(path: Path, *, warn: bool = True) -> str:
    """``_read_source_bytes`` as text, for extractors that work on ``str``.

    Matches ``path.read_text(encoding="utf-8")`` exactly for every valid UTF-8
    file, including its universal-newline translation (``\\r\\n`` and a lone
    ``\\r`` both become ``\\n``) and a kept BOM, so regex extractors see the same
    text they always did.
    """
    text = _read_source_bytes(path, warn=warn).decode("utf-8")
    return text.replace("\r\n", "\n").replace("\r", "\n")
