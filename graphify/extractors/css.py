"""CSS and SCSS design-token extractor.

Extracts design-token definitions (--name: value;) declared within root or
theme contexts (:root, :host, html, body, [data-theme...], [data-mode...],
.dark, .theme-*, @theme, including when enclosed by @media/@layer/@supports),
and collects var(--name) references for post-extraction cross-file resolution.
"""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id

_ROOT_START_RE = re.compile(
    r'^(?::(?:root|host)(?![a-zA-Z0-9_-])|html(?![a-zA-Z0-9_-])|body(?![a-zA-Z0-9_-])|@theme(?![a-zA-Z0-9_-])|\[data-(?:theme|mode)[^\]]*\]|\.dark(?![a-zA-Z0-9_-])|\.theme-[a-zA-Z0-9_-]+)',
    re.IGNORECASE,
)
_SCSS_NESTED_ROOT_RE = re.compile(
    r'^&(?:(?::(?:root|host)(?![a-zA-Z0-9_-]))|(?:\[data-(?:theme|mode)[^\]]*\])|\.dark(?![a-zA-Z0-9_-])|\.theme-[a-zA-Z0-9_-]+)',
    re.IGNORECASE,
)
_TRANSPARENT_AT_RULES = ("@media", "@layer", "@supports")
_URL_START_RE = re.compile(r"^url\s*\(", re.IGNORECASE)
_VAR_RE = re.compile(r"var\(\s*(--[a-zA-Z0-9_-]+)")
_DECL_RE = re.compile(r"^\s*(--[a-zA-Z0-9_-]+)\s*:\s*([^;]+?)\s*(?:;|\Z)")


def _strip_comments_preserving_lines(text: str) -> str:
    """Replace comment characters with spaces, preserving newlines so line numbers remain exact."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_str: str | None = None
    in_url: bool = False
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            elif c == in_str:
                in_str = None
            i += 1
            continue

        if c in ('"', "'"):
            in_str = c
            out.append(c)
            i += 1
            continue

        # Track unquoted url(...) so protocol slashes (http://, https://) don't trigger SCSS comments
        if not in_url and c in ("u", "U") and _URL_START_RE.match(text[i:]):
            in_url = True
            out.append(c)
            i += 1
            continue

        if in_url and (c == ")" or c == "\n"):
            in_url = False
            out.append(c)
            i += 1
            continue

        # Block comment /* ... */
        if c == "/" and nxt == "*":
            out.append(" ")
            out.append(" ")
            i += 2
            while i < n:
                if text[i] == "*" and i + 1 < n and text[i + 1] == "/":
                    out.append(" ")
                    out.append(" ")
                    i += 2
                    break
                else:
                    out.append("\n" if text[i] == "\n" else " ")
                    i += 1
            continue

        # SCSS single-line comment // ... (only outside unquoted url(...))
        if not in_url and c == "/" and nxt == "/":
            out.append(" ")
            out.append(" ")
            i += 2
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue

        out.append(c)
        i += 1

    return "".join(out)


def _blank_strings_preserving_lines(text: str) -> str:
    """Replace characters inside quoted string literals with spaces, preserving newlines."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_str: str | None = None
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\" and i + 1 < n:
                out.append(" ")
                out.append("\n" if text[i + 1] == "\n" else " ")
                i += 2
                continue
            elif c == in_str:
                in_str = None
                out.append(c)
                i += 1
                continue
            else:
                out.append("\n" if c == "\n" else " ")
                i += 1
                continue

        if c in ('"', "'"):
            in_str = c
            out.append(c)
            i += 1
            continue

        out.append(c)
        i += 1

    return "".join(out)


def _is_root_branch(branch: str) -> bool:
    """Check whether a single selector branch is rooted and contains only root/theme selectors."""
    segments = [seg.strip() for seg in re.split(r'[\s>]+', branch) if seg.strip()]
    if not segments:
        return False
    return all(_ROOT_START_RE.match(seg) for seg in segments)


def _is_root_context(stack: list[str]) -> bool:
    """Return True if the current selector stack represents a root or theme context."""
    non_at = [s.strip() for s in stack if not s.strip().startswith(_TRANSPARENT_AT_RULES)]
    if not non_at:
        return False
    base_branches = [b.strip() for b in non_at[0].split(",") if b.strip()]
    if not any(_is_root_branch(b) for b in base_branches):
        return False
    for s in non_at[1:]:
        branches = [b.strip() for b in s.split(",") if b.strip()]
        for b in branches:
            if not (_SCSS_NESTED_ROOT_RE.match(b) or _is_root_branch(b)):
                return False
    return True


def extract_css(path: Path) -> dict:
    """Extract design-token definitions and references from a .css or .scss file."""
    str_path = str(path)
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    clean = _strip_comments_preserving_lines(src)
    code_only = _blank_strings_preserving_lines(clean)

    file_nid = _make_id(str_path)
    stem = _file_stem(path)

    nodes: list[dict] = [
        {
            "id": file_nid,
            "label": path.name,
            "file_type": "code",
            "source_file": str_path,
            "source_location": "L1",
        }
    ]
    edges: list[dict] = []
    raw_token_uses: list[dict] = []

    # 1. Collect var(--token) references outside string literals
    seen_uses: set[tuple[str, int]] = set()
    for m in _VAR_RE.finditer(code_only):
        token_name = m.group(1)
        line = code_only[: m.start()].count("\n") + 1
        key = (token_name, line)
        if key in seen_uses:
            continue
        seen_uses.add(key)
        raw_token_uses.append(
            {
                "source_nid": file_nid,
                "token_name": token_name,
                "source_file": str_path,
                "line": line,
            }
        )

    # 2. Collect token definitions inside root/theme contexts
    seen_tokens: set[str] = set()
    stack: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(clean)
    in_str: str | None = None

    while i < n:
        c = clean[i]
        if in_str:
            buf.append(c)
            if c == "\\" and i + 1 < n:
                buf.append(clean[i + 1])
                i += 2
                continue
            elif c == in_str:
                in_str = None
            i += 1
            continue

        if c in ('"', "'"):
            in_str = c
            buf.append(c)
            i += 1
            continue

        if c == "{":
            selector = "".join(buf).strip()
            stack.append(selector)
            buf = []
            i += 1
            continue

        if c == "}":
            stmt = "".join(buf).strip()
            if stmt and stack and _is_root_context(stack):
                m = _DECL_RE.match(stmt)
                if m:
                    token_name = m.group(1)
                    if token_name not in seen_tokens:
                        seen_tokens.add(token_name)
                        pos = i - len(stmt)
                        line = clean[:pos].count("\n") + 1
                        token_nid = _make_id(stem, token_name)
                        nodes.append(
                            {
                                "id": token_nid,
                                "label": token_name,
                                "file_type": "code",
                                "node_kind": "token",
                                "source_file": str_path,
                                "source_location": f"L{line}",
                            }
                        )
                        edges.append(
                            {
                                "source": file_nid,
                                "target": token_nid,
                                "relation": "defines_token",
                                "confidence": "EXTRACTED",
                                "confidence_score": 1.0,
                                "source_file": str_path,
                                "source_location": f"L{line}",
                                "weight": 1.0,
                            }
                        )
            if stack:
                stack.pop()
            buf = []
            i += 1
            continue

        if c == ";":
            stmt = "".join(buf).strip()
            if stmt and stack and _is_root_context(stack):
                m = _DECL_RE.match(stmt)
                if m:
                    token_name = m.group(1)
                    if token_name not in seen_tokens:
                        seen_tokens.add(token_name)
                        pos = i - len(stmt)
                        line = clean[:pos].count("\n") + 1
                        token_nid = _make_id(stem, token_name)
                        nodes.append(
                            {
                                "id": token_nid,
                                "label": token_name,
                                "file_type": "code",
                                "node_kind": "token",
                                "source_file": str_path,
                                "source_location": f"L{line}",
                            }
                        )
                        edges.append(
                            {
                                "source": file_nid,
                                "target": token_nid,
                                "relation": "defines_token",
                                "confidence": "EXTRACTED",
                                "confidence_score": 1.0,
                                "source_file": str_path,
                                "source_location": f"L{line}",
                                "weight": 1.0,
                            }
                        )
            buf = []
            i += 1
            continue

        buf.append(c)
        i += 1

    return {
        "nodes": nodes,
        "edges": edges,
        "raw_token_uses": raw_token_uses,
    }
