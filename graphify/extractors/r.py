"""R extractor (zero-dependency, regex-based).

R has no standalone ``tree-sitter-r`` distribution on PyPI (unlike every other
language graphify depends on), so — mirroring the regex fallback already used for
Pascal (#781) — this extractor recognises R's surface syntax directly and emits
the same node/edge schema as the tree-sitter extractors. No new dependency is
added.

Recognised constructs:
  * function definitions bound by assignment (R has no ``def`` keyword)::

        f <- function(x) { ... }     # standard
        g = function(x) x            # single-expression body, ``=`` binding
        h <<- function() { ... }     # super-assignment
        k <- \(x) x + 1              # R 4.1 backslash-lambda shorthand

  * package imports: ``library(pkg)`` / ``require(pkg)`` /
    ``requireNamespace("pkg")`` / ``loadNamespace("pkg")``
  * file includes: ``source("helpers.R")``
  * S4 / reference OOP: ``setClass("C", contains = "Base")``,
    ``setGeneric("g")``, ``setMethod("g", "C", function(...) ...)``
  * intra-file call edges between locally-defined functions.

Closes the actionable half of #1689 (``.r``/``.R`` was classified as code but
had no extractor, so R files silently contributed zero nodes to the graph).
"""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id

# R identifiers: letters/digits/'.'/'_'; may not start with a digit or '_'; may
# be backtick-quoted for otherwise-illegal names (`my fn`).
_R_NAME = r"`[^`]+`|[A-Za-z.][A-Za-z0-9._]*"

# name <- function(...) | name = function(...) | name <<- function(...)
# and the R 4.1 lambda  name <- \(...) .
# Anchored to statement start (optional indent) so a default-argument closure
# like foo(cb = function() ...) is not mistaken for a top-level definition.
_R_FUNC_RE = re.compile(
    r"(?m)^[ \t]*(?P<name>" + _R_NAME + r")[ \t]*"
    r"(?:<<-|<-|=)[ \t\r\n]*"
    r"(?:function\b|\\[ \t]*\()"
)

# S4 / reference-class constructors whose first string arg names the new type.
_R_SETCLASS_RE = re.compile(
    r"\b(?P<ctor>setClass|setRefClass)[ \t]*\([ \t\r\n]*[\"'](?P<name>[^\"']+)[\"']"
)
# S4 inheritance:  contains = "Base"  (or contains = c("A", "B")).
_R_CONTAINS_RE = re.compile(r"contains[ \t]*=[ \t]*(?:c\([ \t\r\n]*)?[\"'](?P<base>[^\"']+)[\"']")

_R_SETGENERIC_RE = re.compile(
    r"\bsetGeneric[ \t]*\([ \t\r\n]*[\"'](?P<name>[^\"']+)[\"']"
)
_R_SETMETHOD_RE = re.compile(
    r"\bsetMethod[ \t]*\([ \t\r\n]*[\"'](?P<gname>[^\"']+)[\"'][ \t\r\n]*,[ \t\r\n]*"
    r"(?:c\([ \t\r\n]*)?[\"'](?P<cls>[^\"']+)[\"']"
)

# Imports.
_R_LIBRARY_RE = re.compile(
    r"\b(?P<fn>library|require|requireNamespace|loadNamespace)[ \t]*\([ \t\r\n]*"
    r"(?P<pkg>`[^`]+`|\"[^\"]+\"|'[^']+'|[A-Za-z.][A-Za-z0-9._]*)"
)
_R_SOURCE_RE = re.compile(r"\bsource[ \t]*\([ \t\r\n]*(?P<path>\"[^\"]+\"|'[^']+')")

# A bare call: an identifier immediately followed by '('.
_R_CALL_RE = re.compile(r"(?P<name>" + _R_NAME + r")[ \t]*\(")

# R reserved words + graphify's own recognised constructor/import builtins that
# _R_CALL_RE would otherwise treat as local calls.
_R_KEYWORDS = frozenset({
    "function", "if", "for", "while", "repeat", "return", "break", "next",
    "switch", "tryCatch", "try", "invisible", "on.exit", "stop", "warning",
    "message", "print", "cat", "paste", "paste0", "sprintf", "c", "list",
    "vector", "new", "library", "require", "requireNamespace", "loadNamespace",
    "source", "setClass", "setRefClass", "setGeneric", "setMethod",
    "setValidity", "setRefClass", "standardGeneric", "UseMethod",
})


def _strip_comments(text: str) -> str:
    """Blank ``#`` comments to spaces (newlines kept) while respecting string
    literals, so a ``#`` inside "..." / '...' / `...` is not treated as a
    comment. Character offsets and line numbers are preserved."""
    out = list(text)
    i, n = 0, len(text)
    quote = ""
    while i < n:
        ch = text[i]
        if quote:
            if ch == "\\" and quote in ("\"", "'"):
                i += 2
                continue
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
            i += 1
            continue
        if ch == "#":
            j = i
            while j < n and text[j] != "\n":
                out[j] = " "
                j += 1
            i = j
            continue
        i += 1
    return "".join(out)


def _blank_strings(text: str) -> str:
    """Replace string-literal *contents* with spaces (delimiters kept), offsets
    preserved, so brace/paren matching and call detection ignore braces, parens
    and identifiers that live inside strings. Assumes comments already stripped."""
    out = list(text)
    i, n = 0, len(text)
    quote = ""
    while i < n:
        ch = text[i]
        if quote:
            if ch == "\\" and quote in ("\"", "'"):
                if i + 1 < n and text[i + 1] != "\n":
                    out[i + 1] = " "
                out[i] = " "
                i += 2
                continue
            if ch == quote:
                quote = ""
                i += 1
                continue
            if ch != "\n":
                out[i] = " "
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
            i += 1
            continue
        i += 1
    return "".join(out)


def _match_paren(s: str, open_idx: int) -> int:
    """Return the index just past the ')' balancing the '(' at ``open_idx``."""
    depth, i, n = 0, open_idx, len(s)
    while i < n:
        c = s[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _find_body(code_ns: str, header_end: int) -> tuple[int, int]:
    """Given the index just past a function's parameter list, return the
    ``(start, end)`` span of its body. A brace body ``{...}`` yields the
    balanced-brace span; a single-expression body yields the rest of the line.
    ``code_ns`` must be string-blanked so braces inside strings do not count."""
    n = len(code_ns)
    j = header_end
    while j < n and code_ns[j] in " \t\r\n":
        j += 1
    if j < n and code_ns[j] == "{":
        depth, k = 0, j
        while k < n:
            c = code_ns[k]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return j, k + 1
            k += 1
        return j, n
    k = code_ns.find("\n", j)
    return (j, n if k == -1 else k)


def extract_r(path: Path) -> dict:
    """Extract functions, S4 classes/generics/methods, imports and intra-file
    calls from an R (.r/.R) file. Pure-regex; no tree-sitter grammar required."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - report unreadable file as error result
        return {"nodes": [], "edges": [], "error": str(exc)}

    str_path = str(path)
    stem = _file_stem(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_call_pairs: set[tuple[str, str]] = set()

    def _add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            })

    def _add_edge(src: str, tgt: str, relation: str, line: int,
                  context: str | None = None) -> None:
        edge: dict = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    # comment-stripped (strings kept) for name-bearing patterns; additionally
    # string-blanked for structural / call scanning.
    code = _strip_comments(raw)
    code_ns = _blank_strings(code)

    def _lineno(offset: int) -> int:
        return raw.count("\n", 0, offset) + 1

    def _clean(name: str) -> str:
        return name.strip("`")

    file_nid = _make_id(str_path)
    _add_node(file_nid, path.name, 1)

    # ── imports: library()/require()/... and source() ────────────────────────
    for m in _R_LIBRARY_RE.finditer(code):
        pkg = _clean(m.group("pkg").strip("\"'"))
        if not pkg:
            continue
        line = _lineno(m.start())
        pkg_nid = _make_id(pkg)
        _add_node(pkg_nid, pkg, line)
        _add_edge(file_nid, pkg_nid, "imports", line, context="import")

    for m in _R_SOURCE_RE.finditer(code):
        target = m.group("path").strip("\"'")
        if not target:
            continue
        line = _lineno(m.start())
        base = Path(target).name
        src_nid = _make_id(target)
        _add_node(src_nid, base, line)
        _add_edge(file_nid, src_nid, "imports", line, context="import")

    # ── S4 classes + reference classes ───────────────────────────────────────
    class_nids: dict[str, str] = {}
    for m in _R_SETCLASS_RE.finditer(code):
        cname = _clean(m.group("name"))
        line = _lineno(m.start())
        cls_nid = _make_id(stem, cname)
        _add_node(cls_nid, cname, line)
        _add_edge(file_nid, cls_nid, "contains", line)
        class_nids[cname] = cls_nid
        # inheritance via contains= inside this constructor's argument list.
        # Search from m.start() so we land on setClass's own '(' (the class-name
        # string sits inside it), not the next call's paren further down.
        p_open = code_ns.find("(", m.start())
        if p_open != -1:
            p_close = _match_paren(code_ns, p_open)
            for bm in _R_CONTAINS_RE.finditer(code[p_open:p_close]):
                base = _clean(bm.group("base"))
                base_nid = _make_id(stem, base)
                if base_nid not in seen_ids:
                    _add_node(base_nid, base, line)
                _add_edge(cls_nid, base_nid, "inherits", line)

    # ── functions bound by assignment ────────────────────────────────────────
    func_records: list[tuple[str, str, int, int]] = []  # (nid, name, body_start, body_end)
    local_funcs: dict[str, str] = {}
    for m in _R_FUNC_RE.finditer(code_ns):
        name = _clean(m.group("name"))
        line = _lineno(m.start())
        fn_nid = _make_id(stem, name)
        _add_node(fn_nid, f"{name}()", line)
        _add_edge(file_nid, fn_nid, "contains", line)
        local_funcs[name] = fn_nid
        # skip past the parameter list to locate the body span.
        p_open = code_ns.find("(", m.end() - 1)
        if p_open == -1:
            continue
        p_close = _match_paren(code_ns, p_open)
        b_start, b_end = _find_body(code_ns, p_close)
        func_records.append((fn_nid, name, b_start, b_end))

    # ── S4 generics + methods ────────────────────────────────────────────────
    for m in _R_SETGENERIC_RE.finditer(code):
        gname = _clean(m.group("name"))
        line = _lineno(m.start())
        gen_nid = _make_id(stem, gname)
        _add_node(gen_nid, f"{gname}()", line)
        _add_edge(file_nid, gen_nid, "contains", line)
        local_funcs.setdefault(gname, gen_nid)

    for m in _R_SETMETHOD_RE.finditer(code):
        gname = _clean(m.group("gname"))
        cls = _clean(m.group("cls"))
        line = _lineno(m.start())
        method_nid = _make_id(stem, cls, gname)
        _add_node(method_nid, f"{gname}()", line)
        container = class_nids.get(cls)
        if container:
            _add_edge(container, method_nid, "method", line)
        else:
            _add_edge(file_nid, method_nid, "contains", line)
        # the method's body may call local functions - include the whole
        # setMethod(...) call in the pass (span from setMethod's own '(' to its
        # matching close, which encloses the function-body block).
        p_open = code_ns.find("(", m.start())
        if p_open != -1:
            p_close = _match_paren(code_ns, p_open)
            func_records.append((method_nid, gname, p_open, p_close))

    # ── 2nd pass: intra-file call edges ──────────────────────────────────────
    for caller_nid, _caller_name, b_start, b_end in func_records:
        body = code_ns[b_start:b_end]
        for cm in _R_CALL_RE.finditer(body):
            callee = _clean(cm.group("name"))
            if callee in _R_KEYWORDS:
                continue
            # skip accessor / namespace-qualified targets (obj$m(), obj@m(),
            # pkg::fn()) - not a local free-function call.
            prev = body[cm.start() - 1] if cm.start() > 0 else ""
            if prev in "$@:":
                continue
            callee_nid = local_funcs.get(callee)
            if not callee_nid or callee_nid == caller_nid:
                continue
            pair = (caller_nid, callee_nid)
            if pair in seen_call_pairs:
                continue
            seen_call_pairs.add(pair)
            _add_edge(caller_nid, callee_nid, "calls",
                      _lineno(b_start + cm.start()), context="call")

    return {"nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0}
