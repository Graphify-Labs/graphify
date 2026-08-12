"""MQL5 (MetaTrader 5) support helpers.

MQL5 is C++ with a handful of trading-specific extensions, so it does not need a
bespoke extractor: masking the four constructs the C++ grammar cannot parse lets
`_extract_generic` run the normal `_CPP_CONFIG` pipeline over it and produce
real classes/functions/calls/includes. Measured on a 9,000-line corpus of live
expert advisors, masking takes tree-sitter-cpp from 196 parse errors to 0.

The constructs, all of which are MQL5-only:

- `input` / `sinput` / `extern` storage classes on a declaration
- `input group "..."` -- an inspector heading, with no type and no semicolon
- color literals `C'255,128,0'`
- datetime literals `D'2024.01.31 22:00'`

Masking replaces the offending bytes with spaces rather than deleting them, so
every byte offset in the masked source still matches the original file. The
extractor keys `source_location` off tree-sitter byte offsets, so shifting them
would silently point every node at the wrong line.

`input` declarations are then recovered separately, because masking deliberately
turns them into ordinary globals and the parameters of an expert advisor are the
first thing anyone asks about ("which function reads `magic_number`"). This
mirrors the treatment of inputs in the Pine extractor.
"""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id


# `input group "..."` carries no type and no terminator; blank the whole line.
_RE_INPUT_GROUP = re.compile(rb"^([ \t]*)(s?input[ \t]+group\b[^\r\n]*)", re.M)

# Storage classes that prefix an otherwise ordinary declaration.
_RE_STORAGE_KW = re.compile(rb"^([ \t]*)(sinput|input|extern)([ \t]+)", re.M)

# C'r,g,b' / C'clrName' and D'2024.01.31 22:00'. A C++ parser reads the leading
# identifier plus quote as a malformed character literal.
_RE_TYPED_LITERAL = re.compile(rb"\b([CD])'([^'\r\n]*)'")

# An `input`/`extern` declaration in the ORIGINAL source: storage class, type,
# name, optional array suffix, optional initializer. MQL5 requires these at file
# scope, one per statement, which is why a line regex is sufficient here.
_RE_INPUT_DECL = re.compile(
    r"^[ \t]*(?P<storage>sinput|input|extern)[ \t]+"
    r"(?:const[ \t]+)?(?P<type>[A-Za-z_]\w*(?:[ \t]*::[ \t]*\w+)?)[ \t]+"
    r"(?P<name>[A-Za-z_]\w*)[ \t]*(?:\[[^\]]*\])?[ \t]*(?:=|;)"
)

_RE_PROPERTY = re.compile(r'^[ \t]*#property[ \t]+(?P<key>\w+)[ \t]+(?P<value>[^\r\n]*)')

_RE_IDENT = re.compile(r"\b[A-Za-z_]\w*\b")


def mask_mql5_source(source: bytes) -> bytes:
    """Return `source` with MQL5-only syntax blanked, byte offsets preserved."""
    def _blank_group(m: "re.Match[bytes]") -> bytes:
        return m.group(1) + b" " * len(m.group(2))

    def _blank_kw(m: "re.Match[bytes]") -> bytes:
        return m.group(1) + b" " * len(m.group(2)) + m.group(3)

    def _blank_literal(m: "re.Match[bytes]") -> bytes:
        # `C'5,5,40'` -> `0        `: a valid integer expression of identical
        # width, so the surrounding statement still parses and still spans the
        # same byte range.
        return b"0" + b" " * (len(m.group(0)) - 1)

    source = _RE_INPUT_GROUP.sub(_blank_group, source)
    source = _RE_STORAGE_KW.sub(_blank_kw, source)
    source = _RE_TYPED_LITERAL.sub(_blank_literal, source)
    return source


def _strip_comments(line: str) -> str:
    """Drop `//` comments and blank string bodies, preserving column count.

    String contents are blanked, not kept: braces inside a literal would
    desynchronise the depth counter that attributes a line to its enclosing
    function, and identifiers inside a literal are not reads.
    """
    out: list[str] = []
    quote: str | None = None
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if quote is not None:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == quote:
                quote = None
                out.append(ch)
            else:
                out.append(" ")
            i += 1
            continue
        if ch in ('"', "'"):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and line[i + 1] == "/":
            break
        out.append(ch)
        i += 1
    return "".join(out)


def mql5_input_facts(path: Path, text: str) -> tuple[list[dict], list[dict], dict]:
    """Recover `input`/`extern` declarations and the `#property` header.

    Returns `(nodes, edges, file_metadata)`. Node IDs use the same
    `_make_id(stem, name)` shape the generic engine emits for file-scoped
    symbols, so an input and a function that reads it live in one namespace.

    `references` edges are attributed by brace depth rather than by parsing the
    masked tree a second time: MQL5 functions are file scope and never nested,
    so the innermost enclosing definition of any line is simply the most recent
    signature seen at depth 0. That is cheap and exact for this language.
    """
    str_path = str(path)
    # Must be the engine's stem, not path.stem: symbol IDs are keyed off the
    # full path so same-named files in different directories stay distinct
    # (#1504). Using path.stem here would put every input in a namespace the
    # function nodes do not share, and the references would dangle.
    stem = _file_stem(path)
    file_nid = _make_id(str_path)

    nodes: list[dict] = []
    edges: list[dict] = []
    metadata: dict = {}
    inputs: dict[str, str] = {}

    lines = text.splitlines()
    code = [_strip_comments(ln) for ln in lines]

    for idx, raw in enumerate(lines):
        m = _RE_PROPERTY.match(raw)
        if m:
            value = m.group("value").strip().strip('"').strip()
            if value and m.group("key") in ("version", "copyright", "link", "description"):
                metadata.setdefault(f"mql5_{m.group('key')}", value[:256])

        m = _RE_INPUT_DECL.match(code[idx])
        if not m:
            continue
        name = m.group("name")
        if name in inputs:
            continue
        nid = _make_id(stem, name)
        inputs[name] = nid
        nodes.append({"id": nid, "label": name, "file_type": "code",
                      "source_file": str_path, "source_location": f"L{idx + 1}",
                      "type": "input", "mql5_input_type": m.group("type")})
        edges.append({"source": file_nid, "target": nid, "relation": "contains",
                      "confidence": "EXTRACTED", "source_file": str_path,
                      "source_location": f"L{idx + 1}", "weight": 1.0})

    if not inputs:
        return nodes, edges, metadata

    # --- attribute reads to the enclosing function -------------------------
    # A signature is a line at brace depth 0 that looks like `type name(...)`;
    # its body runs until depth returns to 0.
    sig = re.compile(r"^[A-Za-z_][\w:<>\*&\s]*?\b(?P<name>[A-Za-z_]\w*)[ \t]*\(")
    seen_edges: set[tuple[str, str]] = set()
    depth = 0
    owner: str | None = None
    pending: str | None = None

    def _scan(line: str, holder: str, line_no: int) -> None:
        for im in _RE_IDENT.finditer(line):
            nid_in = inputs.get(im.group(0))
            if nid_in is None or (holder, nid_in) in seen_edges:
                continue
            seen_edges.add((holder, nid_in))
            edges.append({"source": holder, "target": nid_in, "relation": "references",
                          "confidence": "EXTRACTED", "source_file": str_path,
                          "source_location": f"L{line_no}", "weight": 1.0})

    for idx, line in enumerate(code):
        if depth == 0:
            m = sig.match(line)
            if m and m.group("name") not in ("if", "for", "while", "switch", "return", "sizeof"):
                # The signature is only a candidate: MetaEditor's house style
                # puts the opening brace on the next line, so the owner does not
                # become current until a block actually opens.
                pending = _make_id(stem, m.group("name"))
        if depth > 0 and owner is not None:
            _scan(line, owner, idx + 1)

        new_depth = depth + line.count("{") - line.count("}")
        if depth == 0 and new_depth > 0:
            owner, pending = pending, None
        elif depth == 0 and new_depth == 0 and "{" in line and pending is not None:
            _scan(line, pending, idx + 1)   # single-line body: `int f() { return x; }`
            pending = None
        if new_depth <= 0:
            new_depth = 0
            owner = None
        depth = new_depth

    return nodes, edges, metadata
