"""R extractor. Regex-based: no tree-sitter grammar for R on PyPI (cf. apex.py)."""
from __future__ import annotations

import re as _re
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id, _symbol_safe_name

# R reserved words and the base/stats/utils callables that appear in nearly every
# script. Without this filter each becomes a god-node accumulating an edge from
# every call site, which is the same failure _LANGUAGE_BUILTIN_GLOBALS guards
# against for JS/Python in base.py (#726).
_R_KEYWORDS: frozenset[str] = frozenset({
    "if", "else", "for", "while", "repeat", "function", "return", "break",
    "next", "in", "switch", "invisible", "on.exit", "missing", "TRUE", "FALSE",
    "NULL", "NA", "Inf", "NaN",
})

_R_BUILTINS: frozenset[str] = frozenset({
    # constructors / coercion
    "c", "list", "vector", "character", "numeric", "integer", "logical",
    "double", "complex", "factor", "data.frame", "matrix", "array",
    "as.character", "as.numeric", "as.integer", "as.logical", "as.vector",
    "as.factor", "as.data.frame", "as.matrix", "as.list",
    "is.null", "is.na", "is.numeric", "is.character", "is.function",
    "is.list", "is.data.frame", "is.finite", "is.element",
    # sequence / structure
    "length", "nrow", "ncol", "dim", "names", "colnames", "rownames",
    "seq", "seq_len", "seq_along", "rep", "rev", "sort", "order", "unique",
    "head", "tail", "which", "which.max", "which.min", "range", "setdiff",
    "union", "intersect", "append", "unlist", "do.call", "Reduce", "Filter",
    "Map", "lapply", "sapply", "vapply", "mapply", "apply", "tapply",
    "rbind", "cbind", "merge", "split", "subset", "transform", "with",
    "setNames", "unname", "pmax", "pmin", "strrep",
    # math / stats
    "sum", "mean", "median", "min", "max", "abs", "round", "signif", "floor",
    "ceiling", "sqrt", "exp", "log", "log2", "log10", "var", "sd", "quantile",
    "cumsum", "prod", "diff", "scale", "density", "approx", "table",
    # strings
    "paste", "paste0", "sprintf", "format", "formatC", "nchar", "substr",
    "substring", "strsplit", "sub", "gsub", "grepl", "grep", "regmatches",
    "regexpr", "gregexpr", "trimws", "tolower", "toupper", "startsWith",
    "endsWith", "make.names", "shQuote", "sQuote", "dQuote", "encodeString",
    # io / control
    "cat", "print", "message", "warning", "stop", "stopifnot", "tryCatch",
    "try", "suppressWarnings", "suppressMessages", "readline", "readLines",
    "writeLines", "file", "file.path", "file.exists", "basename", "dirname",
    "normalizePath", "path.expand", "dir.create", "list.files", "tempfile",
    "unlink", "readRDS", "saveRDS", "readBin", "Sys.time", "Sys.getenv",
    "Sys.setenv", "date", "format.Date", "nlevels", "levels",
    # environment / meta
    "exists", "get", "assign", "rm", "environment", "sys.function",
    "sys.frames", "sys.call", "match.arg", "match.call", "nargs", "identity",
    "inherits", "class", "attr", "attributes", "structure", "setattr",
    "requireNamespace", "library", "require", "source", "options", "getOption",
    "set.seed", "identical", "all", "any", "isTRUE", "isFALSE", "xor",
    "ifelse", "nzchar", "Negate", "Vectorize",
})

_EXCLUDED = _R_KEYWORDS | _R_BUILTINS

# R identifiers may start with a dot or letter and contain dots/underscores.
_IDENT = r"[.A-Za-z][A-Za-z0-9._]*"
# A definition name may also be backtick-quoted, which is how infix operators are
# declared: `%||%` <- function(a, b) ...
_DEF_NAME = rf"(?:`([^`\n]+)`|({_IDENT}))"


def _mask_literals(source: str) -> str:
    """Blank out comments and string bodies, preserving length and newlines.

    Offsets in the masked text map 1:1 onto the original, so line numbers and
    span arithmetic stay correct. A `#` inside a string is not a comment, and a
    quote inside a comment does not open a string — tracking both in one pass is
    what keeps those cases straight.
    """
    out = list(source)
    i, n = 0, len(source)
    quote: str | None = None
    in_comment = False
    while i < n:
        ch = source[i]
        if in_comment:
            if ch == "\n":
                in_comment = False
            else:
                out[i] = " "
        elif quote is not None:
            if ch == "\\" and i + 1 < n:
                out[i] = " "
                if source[i + 1] != "\n":
                    out[i + 1] = " "
                i += 2
                continue
            if ch == quote:
                quote = None
            elif ch != "\n":
                out[i] = " "
        else:
            if ch == "#":
                in_comment = True
                out[i] = " "
            elif ch in "\"'":
                # Backticks are identifier quoting in R (`%||%` <- ...), not
                # string literals — masking them would erase the operator name.
                quote = ch
        i += 1
    return "".join(out)


def _match_delim(text: str, start: int, open_ch: str, close_ch: str) -> int:
    """Index just past the delimiter matching the one at `start`, or -1."""
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def extract_r(path: Path) -> dict:
    """Extract functions, calls, imports, and source() edges from an .R file.

    Regex over a comment/string-masked copy of the source. Function bodies are
    located by brace matching so nested closures nest correctly and calls are
    attributed to the innermost enclosing function. Calls in top-level script
    code are attributed to the file node — the common shape for an R driver
    script, where nearly all work happens outside any function.

    Known limitation: a closure assigned via anything other than a literal
    `name <- function(...)` / `` `%op%` <- function(...) `` RHS — e.g.
    `.inv_logicle <- tryCatch({ function(x) ... })` — is not recognized as a
    definition, so calls to it stay unresolved. Static extraction can't see
    through an arbitrary expression to know it evaluates to a function.
    """
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"nodes": [], "edges": []}

    masked = _mask_literals(source)
    str_path = str(path)
    stem = _file_stem(path)
    file_nid = _make_id(str_path)

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    line_starts = [0]
    for idx, ch in enumerate(source):
        if ch == "\n":
            line_starts.append(idx + 1)

    def line_of(offset: int) -> int:
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            })

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", context: str | None = None) -> None:
        edge = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    add_node(file_nid, path.name, 1)

    # Paren nesting depth at each offset, so a `name = function(...)` sitting
    # inside a call can be told apart from a statement-level definition. Without
    # this, every `tryCatch(..., error = function(e) ...)` handler and every
    # ggplot `labels = function(x) ...` argument is misread as a named function.
    depth_at: list[int] = []
    _d = 0
    for ch in masked:
        depth_at.append(_d)
        if ch == "(":
            _d += 1
        elif ch == ")":
            _d = max(0, _d - 1)

    # ---- function definitions -------------------------------------------------
    # name <- function(...)  |  name = function(...)  |  name <<- function(...)
    # `%op%` <- function(...) for infix operators.
    def_re = _re.compile(rf"{_DEF_NAME}\s*(<<-|<-|=)\s*function\s*\(")
    spans: list[tuple[int, int, str, str]] = []  # (start, end, name, nid)

    for m in def_re.finditer(masked):
        name = m.group(1) or m.group(2)
        op = m.group(3)
        # `=` inside an argument list binds a parameter, not a name in scope.
        if op == "=" and depth_at[m.start()] > 0:
            continue
        sig_open = masked.index("(", m.end() - 1)
        sig_end = _match_delim(masked, sig_open, "(", ")")
        if sig_end == -1:
            continue
        rest = masked[sig_end:]
        lead = len(rest) - len(rest.lstrip())
        body_start = sig_end + lead
        if body_start < len(masked) and masked[body_start] == "{":
            body_end = _match_delim(masked, body_start, "{", "}")
            if body_end == -1:
                body_end = len(masked)
        else:
            # Brace-less one-liner: body runs to end of the line.
            nl = masked.find("\n", sig_end)
            body_end = len(masked) if nl == -1 else nl
        nid = _make_id(stem, _symbol_safe_name(name))
        line = line_of(m.start())
        add_node(nid, f"{name}()", line)
        spans.append((m.start(), body_end, name, nid))

    spans.sort(key=lambda s: (s[0], -s[1]))

    def enclosing(offset: int) -> tuple[str, str] | None:
        """Innermost (nid, name) whose body contains `offset`."""
        best: tuple[int, str, str] | None = None
        for start, end, name, nid in spans:
            if start <= offset < end and (best is None or start > best[0]):
                best = (start, nid, name)
        return (best[1], best[2]) if best else None

    # contains: file -> top-level fn, outer fn -> nested fn
    for start, _end, _name, nid in spans:
        parent = None
        for s2, e2, _n2, nid2 in spans:
            if s2 < start < e2 and nid2 != nid:
                if parent is None or s2 > parent[0]:
                    parent = (s2, nid2)
        add_edge(parent[1] if parent else file_nid, nid, "contains", line_of(start))

    # ---- imports: library() / require() / pkg:: ---------------------------------
    lib_re = _re.compile(rf"\b(?:library|require)\s*\(\s*[\"']?({_IDENT})[\"']?\s*\)")
    for m in lib_re.finditer(masked):
        pkg = m.group(1)
        pkg_nid = _make_id(pkg)
        line = line_of(m.start())
        add_node(pkg_nid, pkg, line)
        add_edge(file_nid, pkg_nid, "imports", line, context="import")

    ns_re = _re.compile(rf"\b({_IDENT})::({_IDENT})")
    seen_ns: set[str] = set()
    for m in ns_re.finditer(masked):
        pkg = m.group(1)
        if pkg in seen_ns:
            continue
        seen_ns.add(pkg)
        pkg_nid = _make_id(pkg)
        line = line_of(m.start())
        add_node(pkg_nid, pkg, line)
        add_edge(file_nid, pkg_nid, "imports", line, context="import")

    # ---- source() ---------------------------------------------------------------
    # Literal path: source("R/00_utils.R"). The masking pass blanked string
    # bodies, so re-read the literal from the original text at the same offset.
    src_re = _re.compile(r"\bsource\s*\(")
    for m in src_re.finditer(masked):
        call_end = _match_delim(masked, m.end() - 1, "(", ")")
        if call_end == -1:
            continue
        raw = source[m.end():call_end - 1]
        line = line_of(m.start())
        for lit in _re.findall(r"[\"']([^\"']+\.[Rr])[\"']", raw):
            tgt = _make_id(str(Path(lit)))
            add_edge(file_nid, tgt, "sources", line, context="source")
        # Computed path over a character vector, e.g.
        #   for (mod in c("00_utils", "01_load")) source(file.path(d, paste0(mod, ".R")))
        # Recover the vector members from the enclosing for-header when the
        # source() argument interpolates the loop variable.
        if "paste0" in raw or "file.path" in raw:
            header = source[max(0, m.start() - 600):m.start()]
            fm = None
            for fm in _re.finditer(r"for\s*\(\s*(\w+)\s+in\s+c\s*\(", header):
                pass
            if fm is not None:
                vec_start = header.index("(", fm.end() - 1)
                vec_end = _match_delim(header, vec_start, "(", ")")
                if vec_end != -1 and fm.group(1) in raw:
                    # Directory components come from the literal segments of the
                    # file.path(...) call itself: file.path(dir, "R", ...) -> "R".
                    # Extension literals (".R") are not path segments.
                    prefix = [s for s in _re.findall(r"[\"']([^\"']+)[\"']", raw)
                              if not s.startswith(".")]
                    for lit in _re.findall(r"[\"']([^\"']+)[\"']", header[vec_start:vec_end]):
                        tgt = _make_id(str(Path(*prefix, f"{lit}.R")))
                        add_edge(file_nid, tgt, "sources", line,
                                 confidence="INFERRED", context="source")

    # ---- calls -------------------------------------------------------------------
    call_re = _re.compile(rf"(?:({_IDENT})::)?({_IDENT})\s*\(")
    for m in call_re.finditer(masked):
        pkg, name = m.group(1), m.group(2)
        if name in _EXCLUDED and not pkg:
            continue
        # Skip the definition site itself: `foo <- function(`  matches `foo(`.
        before = masked[:m.start()].rstrip()
        if before.endswith("function"):
            continue
        scope = enclosing(m.start())
        scope_nid, scope_name = scope if scope else (file_nid, None)
        if scope_name == name:  # direct recursion — graph keeps no self-loops
            continue
        line = line_of(m.start())
        safe_name = _symbol_safe_name(name)
        if pkg:
            tgt = _make_id(pkg, safe_name)
            add_edge(scope_nid, tgt, "calls", line, context="call")
        else:
            edge_idx = len(edges)
            add_edge(scope_nid, _make_id(stem, safe_name), "calls", line, context="call")
            # R has one flat namespace once every file is source()'d into
            # .GlobalEnv (see the typical `for (mod in modules) source(...)`
            # bootstrap loop) — a name undefined in THIS file is not necessarily
            # undefined in the corpus. Stash the bare (file-independent) target
            # alongside the same-file guess so `_resolve_r_bare_calls`
            # (extractors/resolution.py) can repoint genuinely cross-file calls
            # at their real definition once every file has been extracted.
            # Internal-only field, same convention as export.py's `_src`/`_tgt`:
            # never serialized, popped before graph.json is written.
            edges[edge_idx]["_bare_target"] = _make_id(safe_name)

    return {"nodes": nodes, "edges": edges}
