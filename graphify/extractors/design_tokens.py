"""Design-token bridge. Tailwind-preset color/shadow table, and token references in source files."""
from __future__ import annotations

import re

from pathlib import Path

_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_VAR_REF_RE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)", re.MULTILINE)
_PRESET_ENTRY_RE = re.compile(r"""['"]?([A-Za-z][A-Za-z0-9-]*|[0-9]+)['"]?[ \t]*:[ \t]*'([^']*)'""")
_UTILITY_CLASS_RE = re.compile(
    r"\b(?:bg|text|border|ring|fill|stroke|from|via|to|divide|outline|decoration|"
    r"accent|caret|placeholder|shadow)-([A-Za-z][A-Za-z0-9-]*)(?:/\d+)?\b"
)


def _strip_comments(source: str) -> str:
    source = _BLOCK_COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), source)
    return _LINE_COMMENT_RE.sub("", source)


def _balanced_block(source: str, brace_pos: int) -> str | None:
    depth = 0
    for i in range(brace_pos, len(source)):
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[brace_pos:i + 1]
    return None


def _entry_value(value: str) -> tuple[str, str]:
    m = _VAR_REF_RE.search(value)
    if not m:
        return ("literal", "")
    name = m.group(1)
    if name.endswith("-rgb"):
        name = name[:-4]
    return ("var", name)


def read_tailwind_preset(path: Path) -> dict[str, tuple[str, str, int]]:
    """Colors and boxShadow entries of a Tailwind preset, keyed by utility name."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    source = _strip_comments(source)

    table: dict[str, tuple[str, str, int]] = {}

    colors_match = re.search(r"colors[ \t]*:[ \t]*\{", source)
    if colors_match:
        brace_pos = colors_match.end() - 1
        block = _balanced_block(source, brace_pos)
        if block is not None:
            for fam_match in re.finditer(r"([A-Za-z][A-Za-z0-9]*)[ \t]*:[ \t]*\{", block):
                family = fam_match.group(1)
                fam_brace_pos = fam_match.end() - 1
                fam_block = _balanced_block(block, fam_brace_pos)
                if fam_block is None:
                    continue
                fam_offset = brace_pos + fam_match.end() - 1
                for entry in _PRESET_ENTRY_RE.finditer(fam_block):
                    key, value = entry.group(1), entry.group(2)
                    utility = family if key == "DEFAULT" else f"{family}-{key}"
                    line = source.count("\n", 0, fam_offset + entry.start()) + 1
                    kind, ref = _entry_value(value)
                    table[utility] = (kind, ref if kind == "var" else utility, line)

    shadow_match = re.search(r"boxShadow[ \t]*:[ \t]*\{", source)
    if shadow_match:
        brace_pos = shadow_match.end() - 1
        block = _balanced_block(source, brace_pos)
        if block is not None:
            for entry in _PRESET_ENTRY_RE.finditer(block):
                key, value = entry.group(1), entry.group(2)
                line = source.count("\n", 0, brace_pos + entry.start()) + 1
                kind, ref = _entry_value(value)
                table[key] = (kind, ref if kind == "var" else key, line)

    return table


def scan_token_refs(path: Path, table: dict) -> list[tuple[str, int]]:
    """Design-token references in a source file: var(--x), a utility class, or @apply, each with its line."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    source = _strip_comments(source)

    pairs: list[tuple[str, int]] = []

    for m in _VAR_REF_RE.finditer(source):
        line = source.count("\n", 0, m.start()) + 1
        pairs.append((m.group(1), line))

    for m in _UTILITY_CLASS_RE.finditer(source):
        if source[m.end():m.end() + 2] == "${":
            continue
        key = m.group(1)
        if key not in table:
            continue
        line = source.count("\n", 0, m.start()) + 1
        pairs.append((key, line))

    return pairs
