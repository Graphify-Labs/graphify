"""Deterministic R extraction for Graphify.

R is intentionally source-driven so Graphify does not require an optional R
grammar at runtime. The extractor preserves useful R relationships for package
imports, named functions, containment, and direct calls between local functions.
"""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id

_FUNCTION = re.compile(
    r"(?m)^[ \t]*([A-Za-z.][A-Za-z0-9._]*)[ \t]*(?:<<-|<-|=)[ \t]*function[ \t]*\("
)
_IMPORT = re.compile(
    r"(?m)^[ \t]*(?:library|require|requireNamespace)[ \t]*\("
)
_PACKAGE = re.compile(
    r"\s*(?:package\s*=\s*)?[\"']?([A-Za-z][A-Za-z0-9._-]*)"
)
_CALL = re.compile(
    r"([A-Za-z.][A-Za-z0-9._]*(?:(?:::|\$)[A-Za-z.][A-Za-z0-9._]*)?)[ \t]*\("
)
_NON_CALLS = frozenset({"function", "if", "for", "while", "repeat", "switch", "return"})


def _mask_non_code(source: str) -> str:
    """Blank comments and strings without changing byte offsets or line numbers."""
    out = list(source)
    quote: str | None = None
    escaped = False
    comment = False
    for index, char in enumerate(source):
        if comment:
            if char == "\n":
                comment = False
            else:
                out[index] = " "
            continue
        if quote is not None:
            if char == "\n":
                continue
            if escaped:
                escaped = False
                out[index] = " "
            elif char == "\\":
                escaped = True
                out[index] = " "
            elif char == quote:
                quote = None
            else:
                out[index] = " "
            continue
        if char == "#":
            comment = True
            out[index] = " "
        elif char in ("'", '"'):
            quote = char
    return "".join(out)


def _matching_delimiter(text: str, start: int, opening: str, closing: str) -> int | None:
    depth = 1
    for index in range(start, len(text)):
        if text[index] == opening:
            depth += 1
        elif text[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


def extract_r(path: Path) -> dict:
    """Extract R package imports, named functions, and local direct calls."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    masked = _mask_non_code(source)
    str_path = str(path)
    stem = _file_stem(path)
    file_nid = _make_id(str_path)
    nodes: list[dict] = []
    edges: list[dict] = []
    raw_calls: list[dict] = []
    seen_ids: set[str] = set()

    def line_at(offset: int) -> int:
        return source.count("\n", 0, offset) + 1

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_edge(src: str, tgt: str, relation: str, line: int) -> None:
        edges.append({"source": src, "target": tgt, "relation": relation,
                      "confidence": "EXTRACTED", "source_file": str_path,
                      "source_location": f"L{line}", "weight": 1.0})

    add_node(file_nid, path.name, 1)

    for match in _IMPORT.finditer(masked):
        arguments_end = _matching_delimiter(masked, match.end(), "(", ")")
        if arguments_end is None:
            continue
        tail = source[match.end():arguments_end]
        package = _PACKAGE.match(tail)
        if package:
            add_edge(file_nid, _make_id(package.group(1)), "imports", line_at(match.start()))

    function_specs: list[tuple[int, int, str]] = []
    for match in _FUNCTION.finditer(masked):
        parameters_end = _matching_delimiter(masked, match.end(), "(", ")")
        if parameters_end is None:
            continue
        body_start = parameters_end + 1
        while body_start < len(masked) and masked[body_start] in " \t\r\n":
            body_start += 1
        if body_start < len(masked) and masked[body_start] == "{":
            end = _matching_delimiter(masked, body_start + 1, "{", "}")
            if end is None:
                continue
        else:
            newline = masked.find("\n", body_start)
            end = len(masked) - 1 if newline < 0 else newline
        function_specs.append((match.start(), end, match.group(1)))

    functions: list[dict] = []
    for start, end, name in function_specs:
        parent = min(
            (
                function
                for function in functions
                if function["start"] < start and end <= function["end"]
            ),
            key=lambda function: function["end"] - function["start"],
            default=None,
        )
        parent_id = parent["id"] if parent else None
        nid = _make_id(parent_id or stem, name)
        line = line_at(start)
        add_node(nid, f"{name}()", line)
        add_edge(parent_id or file_nid, nid, "contains", line)
        functions.append({
            "start": start,
            "end": end,
            "id": nid,
            "name": name,
            "parent": parent_id,
        })

    labels: dict[str, list[dict]] = {}
    for function in functions:
        labels.setdefault(function["name"], []).append(function)

    def call_target(callee: str, caller: dict) -> str | None:
        candidates = [
            candidate
            for candidate in labels.get(callee, [])
            if candidate["id"] != caller["id"]
        ]
        children = [
            candidate for candidate in candidates
            if candidate["parent"] == caller["id"]
        ]
        if len(children) == 1:
            return children[0]["id"]
        same_scope = [
            candidate for candidate in candidates
            if candidate["parent"] == caller["parent"]
        ]
        if len(same_scope) == 1:
            return same_scope[0]["id"]
        if len(candidates) == 1:
            return candidates[0]["id"]
        return None

    seen_calls: set[tuple[str, str]] = set()
    for function in functions:
        start = function["start"]
        end = function["end"]
        caller = function["id"]
        body = list(masked[start:end + 1])
        for nested in functions:
            nested_start = nested["start"]
            nested_end = nested["end"]
            if start < nested_start and nested_end <= end:
                for index in range(nested_start, nested_end + 1):
                    if body[index - start] != "\n":
                        body[index - start] = " "
        body_text = "".join(body)
        for call in _CALL.finditer(body_text):
            expression = call.group(1)
            callee = re.split(r"::|\$", expression)[-1]
            if callee in _NON_CALLS:
                continue
            absolute = start + call.start(1)
            target = call_target(callee, function)
            if target:
                pair = (caller, target)
                if pair not in seen_calls:
                    seen_calls.add(pair)
                    add_edge(caller, target, "calls", line_at(absolute))
            elif callee:
                raw_calls.append({"caller_nid": caller, "callee": callee,
                                  "is_member_call": "$" in expression,
                                  "source_file": str_path,
                                  "source_location": f"L{line_at(absolute)}"})

    clean_edges = [edge for edge in edges if edge["source"] in seen_ids and
                   (edge["target"] in seen_ids or edge["relation"] == "imports")]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
