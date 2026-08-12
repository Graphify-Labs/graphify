"""Pine Script (TradingView) extractor.

Pine has no tree-sitter grammar, so this is a line-oriented extractor in the
same family as the regex fallback in `pascal.py`. Pine is a small, highly
regular language -- declarations live at column 0, blocks are indentation
scoped, and there is no macro layer -- so a lexer over comment/string-stripped
lines recovers the structure an AST would give us.

Nodes: the script declaration (`indicator`/`strategy`/`library` + its title),
user functions and methods, user-defined types and enums, inputs, and imported
libraries. Inputs are first-class nodes because in Pine they *are* the tunable
surface of a strategy -- "which function reads `slBuf`" is the question people
actually ask of a trading script.

Edges: `contains` (file -> declaration), `calls` (function -> user function),
`references` (function -> input it reads), `uses` (script -> notable Pine
built-in such as `strategy.entry` or `box.new`), and `imports` (file ->
library).

Node IDs are scoped by file path: a .pine file is a self-contained script and
Pine has no cross-file symbol resolution outside explicit library imports, so
two scripts each defining `calcQty()` are genuinely different functions and must
not merge into one node.
"""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _make_id


# Built-ins worth surfacing as shared nodes. Deliberately a curated whitelist
# rather than "every dotted call": Pine's namespace is huge and edges to
# `math.*`/`ta.*` would produce god nodes that drown the real structure. These
# are the calls that change what a script *does* -- it places orders, it draws,
# it alerts, it pulls another timeframe -- so they answer cross-script questions
# ("which strategies request a higher timeframe?") without hubbing the graph.
_PINE_NOTABLE_BUILTINS: frozenset[str] = frozenset({
    "strategy.entry", "strategy.exit", "strategy.close", "strategy.close_all",
    "strategy.order", "strategy.cancel", "strategy.cancel_all",
    "alertcondition", "alert",
    "request.security", "request.security_lower_tf",
    "plot", "plotshape", "plotchar", "plotcandle", "plotbar", "hline", "fill",
    "box.new", "line.new", "label.new", "table.new", "polyline.new",
    "array.new", "matrix.new", "map.new",
    "input.source", "input.timeframe",
    "runtime.error",
})

# Pine keywords that can precede a `(` and would otherwise be read as calls.
_PINE_KEYWORDS: frozenset[str] = frozenset({
    "if", "else", "for", "to", "by", "while", "switch", "and", "or", "not",
    "var", "varip", "import", "export", "method", "type", "enum", "series",
    "simple", "const", "input", "return", "continue", "break", "na",
    "int", "float", "bool", "string", "color", "line", "label", "box", "table",
})

_RE_SCRIPT_DECL = re.compile(r"^(indicator|strategy|library)\s*\(")
_RE_VERSION = re.compile(r"^//@version\s*=\s*(\d+)")
_RE_IMPORT = re.compile(r"^\s*import\s+([\w./]+)(?:\s+as\s+(\w+))?")
_RE_TYPE = re.compile(r"^\s*(?:export\s+)?type\s+(\w+)")
_RE_ENUM = re.compile(r"^\s*(?:export\s+)?enum\s+(\w+)")
_RE_FUNC = re.compile(
    r"^(?P<indent>[ \t]*)(?:export\s+)?(?P<method>method\s+)?(?P<name>[A-Za-z_]\w*)\s*\("
)
_RE_INPUT = re.compile(
    r"^(?:var\s+|varip\s+)?(?:\w+\s+)?(?P<name>[A-Za-z_]\w*)\s*=\s*input\b"
)
_RE_IDENT_CALL = re.compile(r"\b([A-Za-z_]\w*(?:\.\w+)*)\s*\(")
_RE_IDENT = re.compile(r"\b[A-Za-z_]\w*\b")


def _strip_line(line: str) -> str:
    """Blank out string literals and drop the trailing `//` comment.

    Done character-wise rather than with a regex so that a `//` inside a string
    (common in Pine alert payloads carrying URLs) is not mistaken for the start
    of a comment. String bodies are replaced by spaces instead of being removed
    so that every column index in the result still lines up with the original
    line -- indentation, which is what delimits Pine blocks, must survive.
    """
    out: list[str] = []
    quote: str | None = None
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if quote is not None:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == quote:
                quote = None
            out.append(" ")
            i += 1
            continue
        if ch in ('"', "'"):
            quote = ch
            out.append(" ")
            i += 1
            continue
        if ch == "/" and i + 1 < n and line[i + 1] == "/":
            break
        out.append(ch)
        i += 1
    return "".join(out)


def _indent_of(line: str) -> int:
    """Visual indent width, tabs expanded to 4 columns (TradingView's editor)."""
    width = 0
    for ch in line:
        if ch == " ":
            width += 1
        elif ch == "\t":
            width += 4 - (width % 4)
        else:
            break
    return width


def _first_string_arg(raw: str) -> str | None:
    """Return the first string literal on the line, e.g. the script title."""
    m = re.search(r'"([^"]*)"', raw) or re.search(r"'([^']*)'", raw)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return None


def _balanced_end(code_lines: list[str], start: int) -> int:
    """Index of the line where the paren opened on `start` finally closes.

    Pine allows a signature to wrap across lines, so `f(a,\n b) =>` must be
    stitched back together before we can tell a function definition from a plain
    call. Bounded to 40 lines so an unbalanced paren in a malformed file cannot
    walk the whole script.
    """
    depth = 0
    limit = min(len(code_lines), start + 40)
    for i in range(start, limit):
        for ch in code_lines[i]:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i
    return start


def extract_pine(path: Path) -> dict:
    """Extract the structure of a Pine Script file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    raw_lines = text.splitlines()
    code_lines = [_strip_line(ln) for ln in raw_lines]

    str_path = str(path)
    file_nid = _make_id(str_path)

    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                          "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen_ids: set[str] = {file_nid}
    seen_edges: set[tuple[str, str, str]] = set()

    def _add_node(key: str, label: str, line: int, scoped: bool = True) -> str:
        nid = _make_id(str_path, key) if scoped else _make_id(key)
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path,
                          "source_location": f"L{line}" if line else None})
        return nid

    def _add_edge(src: str, tgt: str, relation: str, line: int,
                  confidence: str = "EXTRACTED") -> None:
        if src == tgt:
            return
        key = (src, tgt, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({"source": src, "target": tgt, "relation": relation,
                      "confidence": confidence, "source_file": str_path,
                      "source_location": f"L{line}", "weight": 1.0})

    # --- pass 1: declarations -------------------------------------------------
    # Names are collected before any call resolution so that a function calling
    # a helper defined further down the file still resolves (Pine requires
    # definition-before-use, but generated scripts do not always honour it).
    funcs: dict[str, tuple[str, int, int, int]] = {}   # name -> (nid, def_line, indent, end_line)
    inputs: dict[str, str] = {}                        # name -> nid
    script_nid: str | None = None

    for idx, code in enumerate(code_lines):
        raw = raw_lines[idx]
        line_no = idx + 1

        if script_nid is None:
            m = _RE_SCRIPT_DECL.match(code)
            if m:
                kind = m.group(1)
                # The title can sit on a later line when the declaration wraps.
                end = _balanced_end(code_lines, idx)
                title = None
                for j in range(idx, end + 1):
                    title = _first_string_arg(raw_lines[j])
                    if title:
                        break
                label = f"{kind} \"{title}\"" if title else kind
                script_nid = _add_node(f"script:{kind}", label, line_no)
                _add_edge(file_nid, script_nid, "contains", line_no)
                continue

        m = _RE_IMPORT.match(code)
        if m:
            lib, alias = m.group(1), m.group(2)
            # Library nodes are unscoped: two scripts importing the same library
            # must land on the same node, that shared edge is the point.
            lib_nid = _add_node(f"pine-lib:{lib}", alias or lib, 0, scoped=False)
            _add_edge(file_nid, lib_nid, "imports", line_no)
            continue

        m = _RE_TYPE.match(code) or _RE_ENUM.match(code)
        if m:
            name = m.group(1)
            nid = _add_node(f"type:{name}", name, line_no)
            _add_edge(file_nid, nid, "contains", line_no)
            continue

        if _indent_of(raw) == 0:
            m = _RE_INPUT.match(code)
            if m:
                name = m.group("name")
                nid = _add_node(f"input:{name}", name, line_no)
                inputs[name] = nid
                _add_edge(file_nid, nid, "contains", line_no)
                continue

        m = _RE_FUNC.match(code)
        if m:
            end = _balanced_end(code_lines, idx)
            joined = " ".join(code_lines[idx:end + 1])
            if "=>" not in joined[joined.find("("):]:
                continue  # a call, not a definition
            name = m.group("name")
            if name in _PINE_KEYWORDS:
                continue
            indent = _indent_of(raw)
            nid = _add_node(f"fn:{name}", f"{name}()", line_no)
            funcs[name] = (nid, line_no, indent, end)
            _add_edge(file_nid, nid, "contains", line_no)

    # --- pass 2: function bodies ---------------------------------------------
    # A Pine function body is every following line indented deeper than the
    # `=>`, so the end of the body is the first non-blank line at or below the
    # definition's own indent.
    for name, (nid, def_line, indent, sig_end) in funcs.items():
        body_end = sig_end
        for j in range(sig_end + 1, len(code_lines)):
            if not code_lines[j].strip():
                continue
            if _indent_of(raw_lines[j]) <= indent:
                break
            body_end = j
        funcs[name] = (nid, def_line, indent, body_end)

    owner_ranges: list[tuple[int, int, str]] = [
        (def_line - 1, end, nid) for nid, def_line, _, end in funcs.values()
    ]

    def _owner_of(idx: int) -> str:
        for start, end, nid in owner_ranges:
            if start <= idx <= end:
                return nid
        return script_nid or file_nid

    for idx, code in enumerate(code_lines):
        if not code.strip():
            continue
        line_no = idx + 1
        owner = _owner_of(idx)

        for m in _RE_IDENT_CALL.finditer(code):
            callee = m.group(1)
            if callee in _PINE_KEYWORDS:
                continue
            if callee in funcs:
                target = funcs[callee][0]
                if target != owner:
                    _add_edge(owner, target, "calls", line_no)
            elif callee in _PINE_NOTABLE_BUILTINS:
                b_nid = _add_node(f"pine-builtin:{callee}", callee, 0, scoped=False)
                _add_edge(script_nid or file_nid, b_nid, "uses", line_no)

        # Input reads are only tracked inside function bodies. At top level
        # nearly every line touches an input, and those edges would say nothing
        # beyond what `contains` already says.
        if owner not in (script_nid, file_nid) and inputs:
            for m in _RE_IDENT.finditer(code):
                ident = m.group(0)
                nid_in = inputs.get(ident)
                if nid_in is not None:
                    _add_edge(owner, nid_in, "references", line_no)

    # Version is metadata on the file node, not a node of its own.
    for idx in range(min(5, len(raw_lines))):
        vm = _RE_VERSION.match(raw_lines[idx].strip())
        if vm:
            nodes[0]["pine_version"] = vm.group(1)
            break

    return {"nodes": nodes, "edges": edges}
