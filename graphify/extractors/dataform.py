"""Deterministic extractor for Dataform ``.sqlx`` model files."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from graphify.extractors.base import _make_id

__all__ = ["extract_dataform"]

_MAX_DATAFORM_BYTES = 2_000_000
_CONFIG_FIELDS = frozenset(
    {
        "type",
        "schema",
        "database",
        "description",
        "tags",
        "dependencies",
    }
)
_CONFIG_HEADER_RE = re.compile(r"(?im)^\s*config\s*\{")
_CONFIG_KEY_RE = re.compile(
    r"(?m)(?:^|,)\s*(?P<key>type|schema|database|description|tags|dependencies)\s*:"
)
_CALL_RE = re.compile(
    r"(?<![\w$.])(?P<kind>ref|self)\s*\((?P<args>[^()\r\n]*)\)",
    re.IGNORECASE,
)
_STRING_RE = re.compile(r"(?P<quote>['\"])(?P<body>(?:\\.|(?!\1).)*)\1", re.DOTALL)


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _literal_string(raw: str) -> str | None:
    raw = raw.strip()
    if len(raw) < 2 or raw[0] not in "'\"" or raw[-1] != raw[0]:
        return None
    try:
        value = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        value = raw[1:-1]
    return value if isinstance(value, str) else None


def _matching_delimiter(
    text: str,
    start: int,
    opening: str,
    closing: str,
    *,
    limit: int | None = None,
) -> int | None:
    depth = 0
    quote: str | None = None
    escaped = False
    end = len(text) if limit is None else min(limit, len(text))
    index = start
    while index < end:
        char = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in "'\"`":
            quote = char
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index
        elif text.startswith("--", index) or text.startswith("//", index):
            newline = text.find("\n", index + 2, end)
            index = end if newline < 0 else newline
            continue
        elif text.startswith("/*", index):
            comment_end = text.find("*/", index + 2, end)
            index = end if comment_end < 0 else min(comment_end + 2, end)
            continue
        index += 1
    return None


def _config_body(text: str) -> tuple[str, int] | None:
    comment_masked = _mask_comments(text)
    header_source = _mask_string_contents(comment_masked)
    match = _CONFIG_HEADER_RE.search(header_source)
    if match is None:
        return None
    opening = header_source.find("{", match.start(), match.end())
    closing = _matching_delimiter(comment_masked, opening, "{", "}")
    if closing is None:
        return None
    return text[opening + 1 : closing], opening + 1


def _value_end(text: str, start: int, opening: str, closing: str, limit: int) -> int:
    end = _matching_delimiter(text, start, opening, closing, limit=limit)
    return limit if end is None else end + 1


def _mask_string_contents(text: str) -> str:
    """Blank quoted contents while preserving offsets for config-key scans."""
    chars = list(text)
    quote: str | None = None
    escaped = False
    for index, char in enumerate(chars):
        if quote is not None:
            if char == "\n":
                escaped = False
                continue
            chars[index] = " "
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "'\"`":
            quote = char
            chars[index] = " "
    return "".join(chars)


def _parse_config(body: str) -> dict[str, Any]:
    config: dict[str, Any] = {}
    key_source = _mask_string_contents(_mask_comments(body))
    matches = list(_CONFIG_KEY_RE.finditer(key_source))
    for index, match in enumerate(matches):
        key = match.group("key")
        if key not in _CONFIG_FIELDS:
            continue
        start = match.end()
        limit = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        while start < limit and body[start].isspace():
            start += 1
        if start >= limit:
            continue
        if body[start] == "[":
            end = _value_end(body, start, "[", "]", limit)
            values = [
                value
                for string_match in _STRING_RE.finditer(_mask_comments(body[start:end]))
                if (value := _literal_string(string_match.group(0))) is not None
            ]
            config[key] = values
            continue
        if body[start] in "'\"":
            quote = body[start]
            end = start + 1
            escaped = False
            while end < limit:
                char = body[end]
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    end += 1
                    break
                end += 1
            value = _literal_string(body[start:end])
        else:
            end = start
            while end < limit and body[end] not in ",\r\n":
                end += 1
            value = body[start:end].strip()
        if isinstance(value, str) and value:
            config[key] = value
    return config


def _mask_comments(text: str) -> str:
    """Blank SQL/JavaScript comments while preserving offsets and strings."""
    chars = list(text)
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(chars):
        char = chars[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in "'\"`":
            quote = char
            index += 1
            continue
        if text.startswith("--", index) or text.startswith("//", index):
            while index < len(chars) and chars[index] != "\n":
                chars[index] = " "
                index += 1
            continue
        if text.startswith("/*", index):
            chars[index] = " "
            if index + 1 < len(chars):
                chars[index + 1] = " "
            index += 2
            while index < len(chars) and not text.startswith("*/", index):
                if chars[index] != "\n":
                    chars[index] = " "
                index += 1
            if index < len(chars):
                chars[index] = " "
                if index + 1 < len(chars):
                    chars[index + 1] = " "
                index += 2
            continue
        index += 1
    return "".join(chars)


def _call_target(kind: str, args: str, model_name: str) -> str | None:
    values = [
        value for match in _STRING_RE.finditer(args) if (value := _literal_string(match.group(0)))
    ]
    if kind.casefold() == "self":
        return model_name if not values else ".".join(values[:2])
    if len(values) == 1:
        return values[0].strip() or None
    if len(values) == 2:
        first, second = (value.strip() for value in values)
        return f"{first}.{second}" if first and second else None
    return None


def _quoted_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    quote: str | None = None
    escaped = False
    start = 0
    for index, char in enumerate(text):
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                spans.append((start, index + 1))
                quote = None
            continue
        if char in "'\"`":
            quote = char
            start = index
    if quote is not None:
        spans.append((start, len(text)))
    return spans


def _calls_outside_strings(text: str):
    spans = _quoted_spans(text)
    span_index = 0
    for match in _CALL_RE.finditer(text):
        while span_index < len(spans) and spans[span_index][1] <= match.start():
            span_index += 1
        if span_index < len(spans) and spans[span_index][0] <= match.start() < spans[span_index][1]:
            continue
        yield match


def extract_dataform(path: Path) -> dict:
    """Extract one Dataform model, its config, and explicit model dependencies.

    Dataform SQLX combines SQL with JavaScript and is not a SQL grammar input.
    This extractor intentionally handles only the stable structural signals:
    the ``config { ... }`` block and literal ``ref(...)``/``self(...)`` calls.
    SQL expressions and JavaScript are left untouched rather than guessed at.
    """
    try:
        if path.stat().st_size > _MAX_DATAFORM_BYTES:
            return {"nodes": [], "edges": [], "error": "sqlx file too large to index"}
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"nodes": [], "edges": [], "error": f"sqlx read error: {exc}"}

    model_name = path.stem
    model_nid = _make_id("dataform", model_name)
    str_path = str(path)
    node: dict[str, Any] = {
        "id": model_nid,
        "label": model_name,
        "file_type": "code",
        "type": "dataform_model",
        "source_file": str_path,
        "source_location": "L1",
    }
    config_info = _config_body(text)
    config_body_offset = 0
    if config_info is not None:
        config, config_body_offset = config_info
        parsed_config = _parse_config(config)
        if parsed_config:
            node["dataform_config"] = parsed_config

    nodes = [node]
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()

    def add_dependency(target_name: str, line: int, context: str) -> None:
        target_nid = _make_id("dataform", target_name)
        if not target_nid or target_nid == model_nid:
            return
        key = (model_nid, target_nid, "depends_on")
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append(
            {
                "source": model_nid,
                "target": target_nid,
                "relation": "depends_on",
                "context": context,
                "confidence": "EXTRACTED",
                "source_file": str_path,
                "source_location": f"L{line}",
                "weight": 1.0,
            }
        )

    for dependency in node.get("dataform_config", {}).get("dependencies", []):
        if isinstance(dependency, str) and dependency.strip():
            dependency_offset = text.find(dependency)
            if dependency_offset < 0:
                dependency_offset = config_body_offset
            add_dependency(
                dependency.strip(),
                _line_number(text, dependency_offset),
                "dataform_config",
            )

    masked = _mask_comments(text)
    for match in _calls_outside_strings(masked):
        target_name = _call_target(match.group("kind"), match.group("args"), model_name)
        if target_name:
            add_dependency(target_name, _line_number(text, match.start()), "dataform_ref")

    return {"nodes": nodes, "edges": edges}
