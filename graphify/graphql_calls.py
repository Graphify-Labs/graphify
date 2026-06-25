"""GraphQL operation *call-site* extractor for graphify.

The SDL extractor (``graphql_sdl.py``) captures the operations a service
*defines* in its ``.graphqls`` schema. This module captures the other side: the
places that *call* those operations from application code — GraphQL documents
embedded in TS/JS as ``gql`...` `` / ``graphql`...` `` tagged template literals,
and Go client structs that name an operation in a ``graphql:"..."`` struct tag.

Those call sites live inside *string literals*, which tree-sitter indexes as
opaque text — so without this pass the contract layer (SDL operations) is an
island with no link to its real consumers. Each call site becomes a ``gql_call``
node; a later stitch pass (per-repo in ``extract.py``, cross-repo in
``global_graph.py``) links ``gql_call --calls--> gql_operation`` by operation
name, so reverse traversal (``graphify affected "<operation>"``) surfaces every
frontend/service that a backend change would affect.

Pure-text and dependency-free: a codebase with no GraphQL literals yields no
nodes, so there is zero behavior change unless GraphQL is actually present.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Suffixes whose source can embed gql`...` tagged template literals.
_TS_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts"}

# A gql/graphql tagged template literal: the tag identifier then a backtick.
# GraphQL document bodies don't contain raw backticks, so a non-greedy scan to
# the next backtick safely bounds the document.
_GQL_TAG = re.compile(r"\b(?:gql|graphql)\s*`", re.IGNORECASE)

# An operation block opener inside a document: `query|mutation|subscription ... {`.
_OP_OPEN = re.compile(r"\b(query|mutation|subscription)\b[^{}]*\{")

# Go client operation tag: `graphql:"storeProductVersion(id: $id)"`.
_GO_TAG = re.compile(r'graphql:"([^"]*)"')

# Leading operation identifier of a Go tag / GraphQL field head.
_IDENT_CALL = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(")

_IDENT_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def _root_fields(block: str) -> list[tuple[str, int]]:
    """Yield ``(field_name, offset_in_block)`` for each *root* selection of every
    operation in a GraphQL document body.

    Root selections of a ``query``/``mutation``/``subscription`` are exactly the
    operation calls (a mutation's root field is the mutation it invokes). Nested
    fields, fragment spreads, aliases and inline-object arguments are skipped, so
    the result is the set of operations this document actually calls.
    """
    out: list[tuple[str, int]] = []
    for opener in _OP_OPEN.finditer(block):
        i = opener.end() - 1  # position of the operation's opening '{'
        depth = 0
        paren = 0
        n = len(block)
        while i < n:
            c = block[i]
            if paren > 0:
                # Inside (...) arguments — ignore braces (inline object values).
                if c == "(":
                    paren += 1
                elif c == ")":
                    paren -= 1
                i += 1
                continue
            if c == "(":
                paren += 1
                i += 1
                continue
            if c == "{":
                depth += 1
                i += 1
                continue
            if c == "}":
                depth -= 1
                i += 1
                if depth == 0:
                    break  # end of this operation
                continue
            if depth == 1 and (c.isalpha() or c == "_"):
                # Skip fragment spreads: "...Name".
                if block[max(0, i - 3):i] == "...":
                    i += 1
                    continue
                j = i
                while j < n and block[j] in _IDENT_CHARS:
                    j += 1
                ident = block[i:j]
                k = j
                while k < n and block[k] in " \t\r\n":
                    k += 1
                nxt = block[k] if k < n else ""
                if nxt == ":":
                    # "alias: field" — skip the alias, the real field follows.
                    i = k + 1
                    continue
                if ident not in ("on",):
                    out.append((ident, i))
                i = j
                continue
            i += 1
    return out


def find_gql_operation_calls(text: str, suffix: str) -> list[tuple[str, int]]:
    """Find GraphQL operation call sites in one source file.

    Returns ``(operation_name, line_number)`` pairs. Covers TS/JS ``gql`...` ``
    template literals (root selections) and Go ``graphql:"..."`` struct tags.
    """
    results: list[tuple[str, int]] = []

    def line_at(pos: int) -> int:
        return text.count("\n", 0, pos) + 1

    if suffix == ".go":
        for m in _GO_TAG.finditer(text):
            body = m.group(1)
            mm = _IDENT_CALL.match(body)
            if mm:
                results.append((mm.group(1), line_at(m.start(1))))
        return results

    if suffix in _TS_SUFFIXES:
        for m in _GQL_TAG.finditer(text):
            start = m.end()  # just past the opening backtick
            end = text.find("`", start)
            if end == -1:
                continue
            block = text[start:end]
            for name, off in _root_fields(block):
                results.append((name, line_at(start + off)))
    return results


def extract_gql_calls(path: Path) -> dict[str, Any]:
    """Per-file extractor: emit a ``gql_call`` node per operation call site.

    Node shape mirrors the SDL extractor's: ``file_type='code'``, a
    ``gql_call`` ``type``, and an ``op_name`` carrying the called operation so the
    stitch passes can match it to the owning ``gql_operation`` by name.
    """
    suffix = path.suffix
    if suffix != ".go" and suffix not in _TS_SUFFIXES:
        return {"nodes": [], "edges": []}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"nodes": [], "edges": []}
    # Cheap reject: skip files with no GraphQL marker at all.
    if "graphql" not in text.lower() and "gql`" not in text.replace(" ", ""):
        return {"nodes": [], "edges": []}

    sp = str(path)
    nodes: list[dict] = []
    seen: set[str] = set()
    for name, line in find_gql_operation_calls(text, suffix):
        nid = f"gqlcall_{name}_{sp}:{line}"
        if nid in seen:
            continue
        seen.add(nid)
        nodes.append({
            "id": nid,
            "label": name,
            "file_type": "code",
            "type": "gql_call",
            "op_name": name,
            "source_file": sp,
            "source_location": f"L{line}",
        })
    return {"nodes": nodes, "edges": []}
