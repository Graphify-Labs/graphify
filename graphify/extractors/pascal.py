"""pascal — moved verbatim from graphify/extract.py."""
from __future__ import annotations

import re
from graphify.extractors.base import _file_stem, _make_id, _read_source_bytes, _read_source_text
from graphify.extractors.resolution import _pascal_resolve_class, _pascal_resolve_unit
from pathlib import Path
from typing import Any, Callable


_PAS_TOKEN_RE = re.compile(
    r"'(?:''|[^'])*'"
    r"|\{[^}]*\}"
    r"|\(\*.*?\*\)"
    r"|//[^\n]*",
    re.DOTALL,
)

_PAS_MODULE_RE = re.compile(
    r"\b(unit|program|library)\s+([A-Za-z_][\w.]*)\s*;",
    re.IGNORECASE,
)

_PAS_USES_RE = re.compile(
    r"\buses\b\s*([^;]+);",
    re.IGNORECASE | re.DOTALL,
)

_PAS_TYPE_HEADER_RE = re.compile(
    r"\b(?P<name>[A-Za-z_]\w*)(?:\s*<[^>]+>)?\s*=\s*(?:packed\s+)?"
    r"(?P<kind>class|interface|record)\b"
    r"(?:\s*\(\s*(?P<bases>[^)]*)\s*\))?",
    re.IGNORECASE,
)

_PAS_END_SEMI_RE = re.compile(r"\bend\s*;", re.IGNORECASE)

_PAS_METHOD_DECL_RE = re.compile(
    r"\b(?:procedure|function|constructor|destructor|operator)\s+"
    r"(?P<name>[A-Za-z_]\w*)"
    r"(?:\s*\([^)]*\))?"
    r"(?:\s*:\s*[\w<>,\s.]+)?"
    r"\s*;",
    re.IGNORECASE,
)

_PAS_IMPL_HEADER_RE = re.compile(
    r"\b(?:procedure|function|constructor|destructor|operator)\s+"
    r"(?P<qual>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)"
    r"(?:\s*<[^>]+>)?"
    r"(?:\s*\([^)]*\))?"
    r"(?:\s*:\s*[\w<>,\s.]+)?"
    r"\s*;",
    re.IGNORECASE,
)

_PAS_BEGIN_END_TOKEN_RE = re.compile(
    r"\b(begin|end|case|try|asm|record)\b", re.IGNORECASE
)

_PAS_CALL_RE = re.compile(r"\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*[(;]")

_PAS_KEYWORDS = frozenset({
    "begin", "end", "if", "then", "else", "while", "do", "for", "to",
    "downto", "repeat", "until", "case", "of", "try", "finally", "except",
    "with", "inherited", "result", "var", "const", "type", "nil", "true",
    "false", "exit", "break", "continue", "uses", "unit", "program",
    "library", "interface", "implementation", "initialization", "finalization",
    "procedure", "function", "constructor", "destructor", "operator", "class",
    "record", "object", "array", "string", "integer", "boolean", "real", "char",
    "writeln", "write", "readln", "read", "assigned", "length", "high",
    "low", "inc", "dec", "new", "dispose", "setlength", "copy", "pos",
    "trim", "format", "inttostr", "strtoint", "ord", "chr", "sizeof",
    "create", "free", "destroy",
})

def _pascal_strip_comments(text: str) -> str:
    """Strip Pascal comments ({}, (* *), //) while preserving newlines."""
    def _sub(m: re.Match) -> str:
        tok = m.group(0)
        if tok.startswith("'"):
            return tok
        return "".join(c if c == "\n" else " " for c in tok)
    return _PAS_TOKEN_RE.sub(_sub, text)

def _pascal_split_sections(text: str) -> tuple[str, int, str, int]:
    """Split into (iface_text, iface_offset, impl_text, impl_offset).
    Files without interface/implementation sections (dpr/lpr/inc) return
    the whole text as impl with offset 0.
    """
    iface_m = re.search(r"\binterface\b", text, re.IGNORECASE)
    impl_m = re.search(r"\bimplementation\b", text, re.IGNORECASE)
    if iface_m and impl_m:
        iface_off = iface_m.end()
        impl_off = impl_m.end()
        end_m = re.search(
            r"\b(initialization|finalization)\b", text[impl_off:], re.IGNORECASE
        )
        impl_end = impl_off + end_m.start() if end_m else len(text)
        return text[iface_off:impl_m.start()], iface_off, text[impl_off:impl_end], impl_off
    return "", 0, text, 0

def _pascal_split_uses(s: str) -> list[str]:
    """Split a uses list string, handling 'Foo in ''bar.pas''' syntax."""
    out = []
    for chunk in s.split(","):
        name = re.split(r"\s+in\s+", chunk.strip(), maxsplit=1, flags=re.IGNORECASE)[0]
        name = name.strip().strip(";")
        if name and re.match(r"[A-Za-z_][\w.]*$", name):
            out.append(name)
    return out

def _pascal_split_bases(s: str) -> list[str]:
    """Split inheritance list, handling generics like TList<T, U>."""
    out, depth, buf = [], 0, []
    for ch in s:
        if ch == "<":
            depth += 1
            buf.append(ch)
        elif ch == ">":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            name = re.sub(r"<.*$", "", "".join(buf).strip())
            if name:
                out.append(name)
            buf = []
        else:
            buf.append(ch)
    name = re.sub(r"<.*$", "", "".join(buf).strip())
    if name:
        out.append(name)
    return [n for n in out if re.match(r"[A-Za-z_]\w*$", n)]

def _pascal_find_body(text: str, start: int) -> tuple[int, int]:
    """Find balanced begin..end after start. Returns (body_start, body_end).
    Returns (0, 0) if no begin found.
    """
    m = re.search(r"\bbegin\b", text[start:], re.IGNORECASE)
    if not m:
        return (0, 0)
    body_start = start + m.end()
    depth = 1
    for tok in _PAS_BEGIN_END_TOKEN_RE.finditer(text, body_start):
        kw = tok.group(1).lower()
        if kw in ("begin", "case", "try", "asm", "record"):
            depth += 1
        elif kw == "end":
            depth -= 1
            if depth == 0:
                return (body_start, tok.start())
    return (body_start, len(text))

def _resolve_pascal_callee_factory(
    records: list[tuple],
    edges: list[dict],
    module_nid: str,
) -> Callable[[str, str], str | None]:
    """Build a scoped call resolver for a single Pascal/Delphi file.

    ``records`` is the list of raw per-procedure tuples produced by either
    Pascal extractor; only the trailing ``(..., container, name_lower)``
    fields and the leading ``proc_nid`` are used, so both extractors' tuple
    shapes work unmodified (regex: proc_nid, line, body_text, container,
    name_lower; tree-sitter: proc_nid, body_node, container, name_lower).

    Resolution order for a call to ``name_lower`` from ``caller_nid``:
      1. A method declared on the caller's own class.
      2. A method declared on an ancestor class (BFS up ``inherits`` edges,
         which are already resolved by this point).
      3. A file-level free function (declared directly under the module).
      4. A global by-name match, but only when unambiguous (exactly one
         procedure with that name anywhere in the file).

    Returns None (no edge emitted) when the name is ambiguous at every
    level -- guessing at a same-named method on an unrelated class is worse
    than omitting the edge. Same-named methods on unrelated classes are a
    common Pascal/Delphi pattern (property accessors, generated wrapper
    classes such as TLB import units): without this scoping, a flat
    file-wide by-name lookup silently collapses onto whichever declaration
    happens to be inserted last, producing wrong cross-class edges. Mirrors
    the "god-node guard" already used by ``resolve_ruby_member_calls`` for
    the analogous Ruby ambiguous-method-name problem.
    """
    class_bases: dict[str, list[str]] = {}
    for e in edges:
        if e.get("relation") == "inherits":
            class_bases.setdefault(e["source"], []).append(e["target"])

    class_procs: dict[str, dict[str, list[str]]] = {}
    module_procs: dict[str, list[str]] = {}
    global_procs: dict[str, list[str]] = {}
    proc_owner: dict[str, str] = {}
    for rec in records:
        proc_nid, container, name_lower = rec[0], rec[-2], rec[-1]
        proc_owner[proc_nid] = container
        global_procs.setdefault(name_lower, []).append(proc_nid)
        if container == module_nid:
            module_procs.setdefault(name_lower, []).append(proc_nid)
        else:
            class_procs.setdefault(container, {}).setdefault(name_lower, []).append(proc_nid)

    def _resolve(caller_nid: str, name_lower: str) -> str | None:
        owner = proc_owner.get(caller_nid)
        if owner is not None:
            candidates = class_procs.get(owner, {}).get(name_lower)
            if candidates:
                return candidates[0] if len(candidates) == 1 else None
            seen_bases: set[str] = set()
            queue = list(class_bases.get(owner, []))
            while queue:
                base = queue.pop(0)
                if base in seen_bases:
                    continue
                seen_bases.add(base)
                candidates = class_procs.get(base, {}).get(name_lower)
                if candidates:
                    return candidates[0] if len(candidates) == 1 else None
                queue.extend(class_bases.get(base, []))
        candidates = module_procs.get(name_lower)
        if candidates:
            return candidates[0] if len(candidates) == 1 else None
        candidates = global_procs.get(name_lower)
        if candidates and len(candidates) == 1:
            return candidates[0]
        return None

    return _resolve


# tree-sitter-pascal 0.11.0 mis-lexes a string literal whose FIRST content
# character is an escaped apostrophe -- `'''X'`, and the degenerate `''''`
# (a literal apostrophe). The same escape in the middle (`'a''b'`) or at the
# end (`'abc'''`) parses fine, so this is a lexer edge case, not missing
# support for escapes. The grammar has no usable error recovery here: every
# symbol from the offending literal to EOF is dropped, which on a Delphi
# codebase that builds SQL by concatenation (`'where x='''+V+''' and'`)
# routinely costs an entire unit.
#
# Same remedy as the C# verbatim-interpolated-string failure (#3376): mask
# only the offending bytes, keep every byte offset identical, and discard the
# rewrite unless it parses better. The mask is applied for PARSING only --
# node text is still read from the untouched original source, so labels and
# locations are byte-for-byte what the user wrote.
def _pascal_parse_health(root) -> tuple[int, int]:
    """Return ``(bytes inside ERROR nodes, -first error byte)``; lower is better.

    Error COUNT is the wrong measure here: tree-sitter answers a failure in the
    first declaration by wrapping the entire unit in one ERROR node, which by
    count (1) would outrank a parse that recovered everything but a handful of
    statements (68). Bytes swallowed by ERROR nodes tracks what the extractor
    actually loses. Only the outermost ERROR is measured -- its children are
    already inside it -- and the first error's position breaks ties, so a plain
    ``<`` comparison means "parses better".
    """
    covered, first = 0, -1
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "ERROR" or node.is_missing:
            covered += node.end_byte - node.start_byte
            if first < 0 or node.start_byte < first:
                first = node.start_byte
            continue  # children are inside this span; do not double-count
        stack.extend(node.children)
    return (covered, 1) if covered == 0 else (covered, -first)


def _normalize_pascal_escaped_string_literals(source: bytes) -> bytes | None:
    """Blank the leading escaped apostrophe of Pascal string literals.

    Returns ``None`` when the source holds no such literal. Each replacement is
    the same byte length as what it replaces, so every downstream offset, line
    and column is preserved.
    """
    out = bytearray(source)
    i, n, changed = 0, len(source), False
    while i < n:
        byte = source[i:i + 1]
        if byte == b"/" and source[i:i + 2] == b"//":
            j = source.find(b"\n", i)
            i = n if j < 0 else j + 1
            continue
        if byte == b"{":
            j = source.find(b"}", i)
            i = n if j < 0 else j + 1
            continue
        if byte == b"(" and source[i:i + 2] == b"(*":
            j = source.find(b"*)", i)
            i = n if j < 0 else j + 2
            continue
        if byte == b"'":
            start = i
            leading = source[i + 1:i + 3] == b"''"
            i += 1
            while i < n:
                if source[i:i + 1] == b"'":
                    if source[i + 1:i + 2] == b"'":
                        i += 2
                        continue
                    i += 1
                    break
                if source[i:i + 1] == b"\n":
                    break
                i += 1
            # `i - start >= 4` keeps the empty literal `''` out of the rewrite.
            if leading and i - start >= 4:
                out[start + 1:start + 3] = b"xx"
                changed = True
            continue
        i += 1
    return bytes(out) if changed else None


# A compiler directive between a routine header and its `begin` is rejected by
# tree-sitter-pascal 0.11.0 -- even an empty `{$IFDEF X}{$ENDIF}` pair, while an
# ordinary `{ comment }` in the same position parses fine, so the directive rule
# simply is not allowed in the declaration-section position. Delphi code guards
# a routine's `var` block this way routinely:
#
#     procedure TDM.CheckUserRights;
#     {$IFDEF R2platnik}
#     var
#       i: integer;
#     {$ENDIF}
#     begin
#
# As with the string-literal mask, the whole unit is lost from that point on.
# Blanking the `$` turns the directive into an ordinary comment the grammar
# already accepts, at identical byte length. Directives do not contribute nodes
# or edges to the Pascal graph, so nothing is lost by hiding them from the
# parser -- and this runs only on the retry path, after the unmasked parse has
# already failed.
def _normalize_pascal_compiler_directives(source: bytes) -> bytes | None:
    """Disguise ``{$...}`` compiler directives as ordinary ``{...}`` comments."""
    out = bytearray(source)
    i, n, changed = 0, len(source), False
    while i < n:
        byte = source[i:i + 1]
        if byte == b"/" and source[i:i + 2] == b"//":
            j = source.find(b"\n", i)
            i = n if j < 0 else j + 1
            continue
        if byte == b"'":
            i += 1
            while i < n:
                if source[i:i + 1] == b"'":
                    if source[i + 1:i + 2] == b"'":
                        i += 2
                        continue
                    i += 1
                    break
                if source[i:i + 1] == b"\n":
                    break
                i += 1
            continue
        if byte == b"{":
            j = source.find(b"}", i)
            if source[i + 1:i + 2] == b"$":
                out[i + 1:i + 2] = b" "
                changed = True
            i = n if j < 0 else j + 1
            continue
        if byte == b"(" and source[i:i + 2] == b"(*":
            j = source.find(b"*)", i)
            i = n if j < 0 else j + 2
            continue
        i += 1
    return bytes(out) if changed else None


def _extract_pascal_regex(path: Path) -> dict:
    """Regex fallback for Pascal/Delphi extraction when tree-sitter-pascal
    is unavailable. Produces the same node/edge schema as the tree-sitter pass.
    """
    try:
        raw = _read_source_text(path, warn=False)
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    str_path = str(path)
    stem = _file_stem(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_call_pairs: set[tuple[str, str]] = set()
    seen_edges: set[tuple[str, str, str]] = set()

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

    def _add_edge(src: str, tgt: str, relation: str, line: int, context: str | None = None) -> None:
        # A class method declared in the interface section and defined in the
        # implementation section both emit a `method` edge to the same node, so
        # dedup on (src, tgt, relation) to keep the graph from carrying doubled
        # method/contains/inherits edges (mirrors _add_node's seen_ids guard).
        key = (src, tgt, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
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

    def _lineno(text: str, offset: int) -> int:
        return text.count("\n", 0, offset) + 1

    file_nid = _make_id(str_path)
    _add_node(file_nid, path.name, 1)

    stripped = _pascal_strip_comments(raw)

    # Module header
    module_nid = file_nid
    mod_m = _PAS_MODULE_RE.search(stripped)
    if mod_m:
        mod_name = mod_m.group(2)
        module_nid = _make_id(stem, mod_name)
        _add_node(module_nid, mod_name, _lineno(stripped, mod_m.start()))
        _add_edge(file_nid, module_nid, "contains", _lineno(stripped, mod_m.start()))

    iface_text, iface_off, impl_text, impl_off = _pascal_split_sections(stripped)

    # Uses clauses
    for section_text, section_off in ((iface_text, iface_off), (impl_text, impl_off)):
        for um in _PAS_USES_RE.finditer(section_text):
            line = _lineno(stripped, section_off + um.start())
            for unit_name in _pascal_split_uses(um.group(1)):
                tgt_nid = _pascal_resolve_unit(path, unit_name)
                _add_edge(module_nid, tgt_nid, "imports", line, context="import")

    # Type declarations (classes / interfaces) in interface section
    search_text = iface_text if iface_text else stripped
    search_off = iface_off if iface_text else 0
    pos = 0
    while pos < len(search_text):
        hm = _PAS_TYPE_HEADER_RE.search(search_text, pos)
        if not hm:
            break
        type_name = hm.group("name")
        bases_raw = hm.group("bases") or ""
        line = _lineno(stripped, search_off + hm.start())
        cls_nid = _make_id(stem, type_name)
        _add_node(cls_nid, type_name, line)
        _add_edge(module_nid, cls_nid, "contains", line)

        for base_name in _pascal_split_bases(bases_raw):
            same_file_nid = _make_id(stem, base_name)
            if same_file_nid in seen_ids:
                # Base class already declared earlier in this same file --
                # reuse its real node instead of the cross-file/stub lookup
                # below (which assumes one-class-per-file and would create a
                # duplicate node for a base class that shares this file).
                base_nid = same_file_nid
            else:
                resolved = _pascal_resolve_class(path, base_name)
                if resolved:
                    # Cross-file base class found on disk -- its real node
                    # arrives via THAT file's own extraction. Do not add a
                    # duplicate stub here: it would carry this file's
                    # source_file (wrong -- it belongs to the base class's
                    # own file) and collide with the real node under
                    # cross-file id disambiguation, producing two different
                    # salted ids for what should be one class (breaks
                    # cross-file `inherits`-chain resolution downstream).
                    base_nid = resolved
                else:
                    base_nid = _make_id(base_name)
                    if base_nid not in seen_ids:
                        _add_node(base_nid, base_name, line)
            _add_edge(cls_nid, base_nid, "inherits", line)

        # Find class body (up to next end;)
        end_m = _PAS_END_SEMI_RE.search(search_text, hm.end())
        body_text = search_text[hm.end():end_m.start()] if end_m else ""
        body_off = search_off + hm.end()

        # Forward method declarations inside the class body
        for mm in _PAS_METHOD_DECL_RE.finditer(body_text):
            mname = mm.group("name")
            mline = _lineno(stripped, body_off + mm.start())
            method_nid = _make_id(cls_nid, mname)
            _add_node(method_nid, f"{mname}()", mline)
            _add_edge(cls_nid, method_nid, "method", mline)

        pos = end_m.end() if end_m else len(search_text)

    # Implementation headers (procedure/function/constructor/destructor)
    impl_records: list[tuple[str, int, str, str, str]] = []
    # (proc_nid, line, body_text, container, name_lower)
    for fm in _PAS_IMPL_HEADER_RE.finditer(impl_text):
        qualified = fm.group("qual")
        line = _lineno(stripped, impl_off + fm.start())
        if "." in qualified:
            cls_part, method_part = qualified.split(".", 1)
            cls_nid = _make_id(stem, cls_part)
            container = cls_nid if cls_nid in seen_ids else module_nid
            relation = "method" if cls_nid in seen_ids else "contains"
            label = f"{method_part}()"
            name_lower = method_part.lower()
        else:
            container, relation = module_nid, "contains"
            label = f"{qualified}()"
            name_lower = qualified.lower()
        proc_nid = _make_id(stem, qualified)
        _add_node(proc_nid, label, line)
        _add_edge(container, proc_nid, relation, line)

        body_start, body_end = _pascal_find_body(impl_text, fm.end())
        body_text = impl_text[body_start:body_end] if body_start else ""
        impl_records.append((proc_nid, line, body_text, container, name_lower))

    # Intra-file call edges, scoped by the caller's own class, then its
    # ancestor chain (via `inherits` edges already emitted above), then
    # file-level free functions; fall back to a global by-name match only
    # when it is unambiguous (single owner across the file). Prevents
    # same-named methods on unrelated classes (property accessors, generated
    # wrapper classes such as TLB import units, etc. -- a common Pascal/Delphi
    # pattern) from collapsing into an arbitrary cross-class edge.
    callee_nid = _resolve_pascal_callee_factory(impl_records, edges, module_nid)
    raw_calls: list[dict] = []
    for caller_nid, caller_line, body_text, _container, _name_lower in impl_records:
        for cm in _PAS_CALL_RE.finditer(body_text):
            callee_name = cm.group(1).split(".")[-1].lower()
            if callee_name in _PAS_KEYWORDS:
                continue
            call_line = caller_line + body_text.count("\n", 0, cm.start())
            target_nid = callee_nid(caller_nid, callee_name)
            if target_nid == caller_nid:
                continue
            if not target_nid:
                # Not resolvable within this file (e.g. inherited from a base
                # class declared in another file) -- report for the
                # cross-file resolver (graphify.pascal_resolution) instead of
                # guessing or dropping it silently.
                raw_calls.append({
                    "source_file": str_path,
                    "source_location": f"L{call_line}",
                    "caller_nid": caller_nid,
                    "callee": callee_name,
                })
                continue
            pair = (caller_nid, target_nid)
            if pair in seen_call_pairs:
                continue
            seen_call_pairs.add(pair)
            _add_edge(caller_nid, target_nid, "calls", call_line, context="call")

    return {
        "nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0,
        "raw_calls": raw_calls,
    }

def extract_pascal(path: Path) -> dict:
    """Extract units, classes, procedures, uses-imports, and calls from Pascal/Delphi files.

    Produces nodes for:
    - The file itself
    - unit / program / library declarations
    - class and interface type declarations
    - procedure / function implementations (including qualified TClass.Method names)

    Produces edges for:
    - file --contains--> module
    - module --imports--> other file node (via uses clause, resolved to path-based IDs)
    - class --inherits--> base class
    - class/module --contains--> method forward declaration
    - class/module --contains--> procedure/function implementation
    - procedure --calls--> other procedure (within the same file)

    Uses tree-sitter-pascal when available; falls back to a regex-based extractor
    (_extract_pascal_regex) when it isn't installed or fails to parse, so Pascal
    extraction works out of the box without an extra pip install.
    """
    try:
        import tree_sitter_pascal as tspascal
        from tree_sitter import Language, Parser
    except ImportError:
        return _extract_pascal_regex(path)

    try:
        language = Language(tspascal.language())
        parser = Parser(language)
        source = _read_source_bytes(path)
        tree = parser.parse(source)
        root = tree.root_node
        if root.has_error:
            masked = _normalize_pascal_escaped_string_literals(source) or source
            masked = _normalize_pascal_compiler_directives(masked) or masked
            if masked != source:
                retry = parser.parse(masked)
                if _pascal_parse_health(retry.root_node) < _pascal_parse_health(root):
                    # Parse the masked bytes but keep reading node text
                    # from the original `source`: offsets are identical
                    # and only string-literal interiors differ.
                    tree, root = retry, retry.root_node
    except Exception:
        return _extract_pascal_regex(path)

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()
    proc_bodies: list[tuple[str, Any, str, str]] = []
    # (proc_nid, body_node, container, name_lower)

    def _read(node) -> str:  # type: ignore[no-untyped-def]
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid, "label": label, "file_type": "code",
                "source_file": str_path, "source_location": f"L{line}",
            })

    def add_edge(
        src: str, tgt: str, relation: str, line: int,
        confidence: str = "EXTRACTED", weight: float = 1.0,
        context: str | None = None,
    ) -> None:
        # A class method declared in the interface section and defined in the
        # implementation section both emit a `method` edge to the same node, so
        # dedup on (src, tgt, relation) to keep the graph from carrying doubled
        # method/contains/inherits edges (mirrors add_node's seen_ids guard).
        key = (src, tgt, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edge: dict[str, Any] = {
            "source": src, "target": tgt, "relation": relation,
            "confidence": confidence, "source_file": str_path,
            "source_location": f"L{line}", "weight": weight,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)
    module_nid = file_nid

    # Scope facts for `graphify.pascal_singleton_resolution`, which resolves a
    # call through a global object variable (`DM.Open`). Collected HERE rather
    # than in the resolver because scope is per-file knowledge: only this
    # extraction can see which names a routine declares locally and which
    # fields its class publishes, and those are exactly the names that shadow
    # a global of the same name.
    global_vars: dict[str, str] = {}      # unit-level var name -> type name
    fields_of: dict[str, set[str]] = {}   # class nid -> field names it declares
    shadow_by_proc: dict[str, set[str]] = {}  # proc nid -> names NOT global here

    def _plain_type_name(decl_node) -> str | None:  # type: ignore[no-untyped-def]
        """The type of a ``declVar``/``declField``, when it is a plain typeref.

        ``array[1..12] of TDateTime``, records and pointers return None on
        purpose: only a variable holding a class instance can receive a
        method call, and an array's element type is not that variable's type.
        """
        for child in decl_node.children:
            if child.type != "type":
                continue
            for grandchild in child.children:
                if grandchild.type == "typeref":
                    # `Data.TDM` -> TDM: the last identifier is the type.
                    names = [
                        _read(ident) for ident in grandchild.children
                        if ident.type == "identifier"
                    ]
                    if names:
                        return names[-1]
            return None
        return None

    def _declared_names(decl_node) -> list[str]:  # type: ignore[no-untyped-def]
        return [
            _read(child) for child in decl_node.children
            if child.type == "identifier"
        ]

    def _proc_name(header_node) -> str | None:  # type: ignore[no-untyped-def]
        name_node = header_node.child_by_field_name("name")
        if name_node:
            return _read(name_node)
        for child in header_node.children:
            if child.type in ("identifier", "genericDot", "genericTpl"):
                return _read(child)
        return None

    def walk(node, parent_nid: str) -> None:  # type: ignore[no-untyped-def]
        nonlocal module_nid
        t = node.type
        line = node.start_point[0] + 1

        if t in ("unit", "program", "library"):
            name_node = next((c for c in node.children if c.type == "moduleName"), None)
            mod_name = _read(name_node) if name_node else path.stem
            mod_nid = _make_id(stem, mod_name)
            add_node(mod_nid, mod_name, line)
            add_edge(file_nid, mod_nid, "contains", line)
            module_nid = mod_nid
            for child in node.children:
                walk(child, mod_nid)
            return

        if t == "declVars" and parent_nid == module_nid:
            # Only a var block hanging directly off the unit is global. Class
            # `var` sections arrive with the class nid as parent, and a
            # routine's own `var` block is never reached: the defProc branch
            # returns before descending.
            for decl in node.children:
                if decl.type != "declVar":
                    continue
                type_name = _plain_type_name(decl)
                if not type_name:
                    continue
                for var_name in _declared_names(decl):
                    global_vars[var_name.lower()] = type_name.lower()
            return

        if t == "declUses":
            for child in node.children:
                if child.type == "moduleName":
                    mod_name = _read(child)
                    tgt_nid = _pascal_resolve_unit(path, mod_name)
                    add_edge(parent_nid, tgt_nid, "imports", line, context="import")
            return

        if t == "declType":
            type_name = None
            kind_node = None
            enum_node = None
            for child in node.children:
                if child.type == "identifier" and type_name is None:
                    type_name = _read(child)
                elif child.type in ("declClass", "declIntf", "declHelper") and kind_node is None:
                    kind_node = child
                elif child.type == "type" and enum_node is None:
                    # An enumerated type (`TColor = (clRed, clGreen);`) nests its
                    # values under type -> declEnum -> declEnumValue.
                    enum_node = next(
                        (gc for gc in child.children if gc.type == "declEnum"), None
                    )
            if type_name and enum_node is not None:
                # A Pascal enumerated type is a named type whose values are its
                # cases. Without this branch declType matched only class/interface/
                # helper kinds, so the whole enum type AND its values fell through
                # and were dropped. Emit the type node plus a `case_of` edge per
                # value — the Pascal parity of Java #1719 / C# / Swift / Scala enums.
                enum_nid = _make_id(stem, type_name)
                add_node(enum_nid, type_name, line)
                add_edge(parent_nid, enum_nid, "contains", line)
                for value in enum_node.children:
                    if value.type != "declEnumValue":
                        continue
                    value_name_node = next(
                        (c for c in value.children if c.type == "identifier"), None
                    )
                    if value_name_node is None:
                        continue
                    value_name = _read(value_name_node)
                    if not value_name:
                        continue
                    value_line = value.start_point[0] + 1
                    value_nid = _make_id(enum_nid, value_name)
                    add_node(value_nid, value_name, value_line)
                    add_edge(enum_nid, value_nid, "case_of", value_line)
                return
            if type_name and kind_node:
                cls_nid = _make_id(stem, type_name)
                add_node(cls_nid, type_name, line)
                add_edge(parent_nid, cls_nid, "contains", line)
                # A Delphi form publishes its components as plain fields
                # (`Query: TADOQuery;`), so inside its methods `Query.Open`
                # means the component, never a global of that name. Record
                # them so the singleton resolver does not cross the two.
                field_names: set[str] = set()

                def _collect_fields(scope_node) -> None:  # type: ignore[no-untyped-def]
                    for member in scope_node.children:
                        if member.type == "declField":
                            field_names.update(
                                name.lower() for name in _declared_names(member)
                            )
                        elif member.type in ("declSection", "declVars"):
                            _collect_fields(member)

                _collect_fields(kind_node)
                fields_of[cls_nid] = field_names
                for child in kind_node.children:
                    if child.type == "typeref":
                        base_name = _read(child)
                        base_nid = _make_id(stem, base_name)
                        if base_nid not in seen_ids:
                            # Try cross-file resolution (TFooBar → FooBar.pas)
                            resolved = _pascal_resolve_class(path, base_name)
                            if resolved:
                                # Cross-file base class found on disk -- its
                                # real node arrives via THAT file's own
                                # extraction. Do not add a duplicate stub
                                # here: it would carry this file's
                                # source_file (wrong) and collide with the
                                # real node under cross-file id
                                # disambiguation, producing two different
                                # salted ids for what should be one class.
                                base_nid = resolved
                            else:
                                base_nid = _make_id(base_name)
                                if base_nid not in seen_ids:
                                    # Stub for RTL/external base classes.
                                    add_node(base_nid, base_name, line)
                        add_edge(cls_nid, base_nid, "inherits", line)
                for child in kind_node.children:
                    walk(child, cls_nid)
                return
            for child in node.children:
                walk(child, parent_nid)
            return

        if t == "declProcFwd":
            header = next((c for c in node.children if c.type == "declProc"), None)
            if header:
                name = _proc_name(header)
                if name and "." not in name:
                    method_nid = _make_id(parent_nid, name)
                    add_node(method_nid, f"{name}()", line)
                    add_edge(parent_nid, method_nid, "method", line)
            return

        if t == "defProc":
            header = next((c for c in node.children if c.type == "declProc"), None)
            body_node = next((c for c in node.children if c.type == "block"), None)
            if not header:
                for child in node.children:
                    walk(child, parent_nid)
                return
            name = _proc_name(header)
            if not name:
                for child in node.children:
                    walk(child, parent_nid)
                return
            container = parent_nid
            if "." in name:
                parts = name.split(".", 1)
                cls_nid = _make_id(stem, parts[0])
                if cls_nid in seen_ids:
                    container = cls_nid
                label = f"{parts[-1]}()"
            else:
                label = f"{name}()"
            proc_nid = _make_id(stem, name)
            add_node(proc_nid, label, line)
            add_edge(
                container, proc_nid,
                "method" if container != parent_nid else "contains",
                line,
            )
            if body_node:
                proc_bodies.append((proc_nid, body_node, container, label.removesuffix("()").lower()))
                # Parameters and locals shadow a global of the same name, and
                # so do the fields of the class this routine belongs to. `Q`,
                # `Query` and `Table` are common as both, so without this a
                # qualified call would be attributed to the wrong object.
                shadowed = set(fields_of.get(container, ()))
                for scope_node in (header, node):
                    for member in scope_node.children:
                        if member.type == "declArgs":
                            for arg in member.children:
                                if arg.type == "declArg":
                                    shadowed.update(n.lower() for n in _declared_names(arg))
                        elif member.type == "declVars":
                            for decl in member.children:
                                if decl.type == "declVar":
                                    shadowed.update(n.lower() for n in _declared_names(decl))
                shadow_by_proc[proc_nid] = shadowed
            return

        for child in node.children:
            walk(child, parent_nid)

    walk(root, file_nid)

    # Second pass: resolve calls inside procedure/function bodies, scoped by
    # the caller's own class, then its ancestor chain, then file-level free
    # functions, falling back to an unambiguous global match (see
    # _resolve_pascal_callee_factory).
    resolve_callee = _resolve_pascal_callee_factory(proc_bodies, edges, module_nid)
    seen_call_pairs: set[tuple[str, str]] = set()
    raw_calls: list[dict] = []

    def _qualified_pair(node) -> tuple[str, str] | None:  # type: ignore[no-untyped-def]
        """``(qualifier, member)`` for a plain ``Ident.Ident`` exprDot.

        Only a bare identifier on the left is accepted. A chain
        (``Grid.Columns.Add``) nests another exprDot there, and its receiver
        is an expression whose type this pass cannot know -- reporting a
        qualifier for it would invite the resolver to guess.
        """
        if node.type != "exprDot":
            return None
        parts = [c for c in node.children if c.is_named and c.type != "kDot"]
        if len(parts) != 2:
            return None
        if parts[0].type != "identifier" or parts[1].type != "identifier":
            return None
        return _read(parts[0]).lower(), _read(parts[1]).lower()

    def _visible_qualifier(caller_nid: str, qualifier: str | None) -> str | None:
        """Keep the qualifier only when it could name a global object.

        `Self` is dropped so a `Self.Foo` call keeps reaching the inherited-call
        resolver, and so is any name the routine declares itself.
        """
        if not qualifier or qualifier == "self":
            return None
        if qualifier in shadow_by_proc.get(caller_nid, ()):
            return None
        return qualifier

    def _emit_or_report(
        caller_nid: str, name_lower: str, line: int, qualifier: str | None = None,
    ) -> None:
        target = resolve_callee(caller_nid, name_lower)
        if target == caller_nid:
            return
        if not target:
            # Not resolvable within this file (e.g. inherited from a base
            # class declared in another file) -- report for the cross-file
            # resolver (graphify.pascal_resolution) instead of guessing or
            # dropping it silently.
            raw_call: dict[str, Any] = {
                "source_file": str_path,
                "source_location": f"L{line}",
                "caller_nid": caller_nid,
                "callee": name_lower,
            }
            qualifier = _visible_qualifier(caller_nid, qualifier)
            if qualifier:
                # Written as `Obj.Method`, so it is NOT a call to an inherited
                # `Method`: graphify.pascal_singleton_resolution resolves it
                # through the object instead.
                raw_call["qualifier"] = qualifier
            raw_calls.append(raw_call)
            return
        pair = (caller_nid, target)
        if pair not in seen_call_pairs:
            seen_call_pairs.add(pair)
            add_edge(caller_nid, target, "calls", line, context="call")

    def walk_calls(node, caller_nid: str) -> None:  # type: ignore[no-untyped-def]
        if node.type == "exprCall":
            callee_text = None
            qualifier = None
            for child in node.children:
                if child.is_named and child.type not in ("exprArgs",):
                    pair = _qualified_pair(child)
                    if pair:
                        qualifier, callee_text = pair
                    else:
                        callee_text = _read(child).split(".")[-1]
                    break
            if callee_text:
                _emit_or_report(
                    caller_nid, callee_text.lower(), node.start_point[0] + 1, qualifier,
                )
        elif node.type == "statement":
            # Pascal bare procedure calls with no args: `Reset;`
            # tree-sitter represents these as statement → identifier (no exprCall wrapper)
            named = [c for c in node.children if c.is_named]
            if len(named) == 1 and named[0].type == "identifier":
                callee_text = _read(named[0])
                _emit_or_report(caller_nid, callee_text.lower(), node.start_point[0] + 1)
            elif len(named) == 1 and named[0].type == "exprDot":
                # `DM.Open;` -- a parameterless qualified call. The grammar
                # gives no exprCall wrapper, so this shape was invisible to
                # the pass above and produced nothing at all. Report it for
                # the object-aware resolver rather than resolving the bare
                # member name here, which would attribute it to whatever
                # unrelated class happens to own that name in this file.
                pair = _qualified_pair(named[0])
                if pair:
                    qualifier, callee_text = pair
                    qualifier = _visible_qualifier(caller_nid, qualifier)
                    if qualifier:
                        raw_calls.append({
                            "source_file": str_path,
                            "source_location": f"L{node.start_point[0] + 1}",
                            "caller_nid": caller_nid,
                            "callee": callee_text,
                            "qualifier": qualifier,
                        })
        for child in node.children:
            walk_calls(child, caller_nid)

    for proc_nid, body_node, _container, _name_lower in proc_bodies:
        walk_calls(body_node, proc_nid)

    return {
        "nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0,
        "raw_calls": raw_calls,
        "global_vars": global_vars,
    }
