"""Intra-file slicing for semantic LLM extraction.

Large markdown/text documents can exceed a model context window or graphify's
per-chunk token budget. FileSlice represents a byte range within one source
file; several slices still cache and increment under the parent file path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
import sys

# Document-like extensions eligible for intra-file splitting.
_SPLITTABLE_SUFFIXES = frozenset({".md", ".mdx", ".txt", ".rst"})

_CHARS_PER_TOKEN = 4
_PER_FILE_OVERHEAD_CHARS = 160

_HEADING_SPLIT = re.compile(r"(?=^#{1,6}\s)", re.MULTILINE)


@dataclass(frozen=True)
class FileSlice:
    """A character range within a single on-disk file."""

    path: Path
    start_char: int
    end_char: int
    slice_index: int = 0
    slice_count: int = 1

    def source_location(self) -> str:
        return f"chars:{self.start_char}-{self.end_char}"


SemanticUnit = Path | FileSlice


def is_file_slice(unit: SemanticUnit) -> bool:
    return isinstance(unit, FileSlice)


def unit_path(unit: SemanticUnit) -> Path:
    return unit.path if is_file_slice(unit) else unit


def is_splittable_text(path: Path) -> bool:
    return path.suffix.lower() in _SPLITTABLE_SUFFIXES


def read_unit_text(unit: SemanticUnit) -> str:
    if is_file_slice(unit):
        full = unit.path.read_text(encoding="utf-8", errors="replace")
        return full[unit.start_char : unit.end_char]
    return unit.read_text(encoding="utf-8", errors="replace")


def _count_tokens(text: str, tokenizer: object | None) -> int:
    if tokenizer is not None:
        return len(tokenizer.encode(text))  # type: ignore[attr-defined]
    return len(text) // _CHARS_PER_TOKEN


def estimate_unit_tokens(
    unit: SemanticUnit,
    *,
    tokenizer: object | None,
    char_cap: int | None = None,
) -> int:
    if is_file_slice(unit):
        text = read_unit_text(unit)
        return _count_tokens(text, tokenizer) + (_PER_FILE_OVERHEAD_CHARS // _CHARS_PER_TOKEN)

    path = unit
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if char_cap is not None:
            text = text[:char_cap]
    except OSError:
        return 0
    return _count_tokens(text, tokenizer) + (_PER_FILE_OVERHEAD_CHARS // _CHARS_PER_TOKEN)


def _pick_ranges(
    text: str,
    max_tokens: int,
    tokenizer: object | None,
) -> list[tuple[int, int]]:
    """Split *text* into (start, end) char ranges each <= max_tokens."""
    if not text:
        return [(0, 0)]

    total = _count_tokens(text, tokenizer)
    if total <= max_tokens:
        return [(0, len(text))]

    # Prefer markdown heading boundaries, then paragraph breaks, then newlines.
    for pattern in (_HEADING_SPLIT, re.compile(r"\n\n+"), re.compile(r"\n")):
        boundaries = [0]
        for match in pattern.finditer(text):
            pos = match.start()
            if pos > boundaries[-1]:
                boundaries.append(pos)
        boundaries.append(len(text))
        ranges = _pack_boundaries(text, boundaries, max_tokens, tokenizer)
        if ranges:
            return ranges

    # Hard split by character budget.
    ranges: list[tuple[int, int]] = []
    start = 0
    approx_chars = max(256, max_tokens * _CHARS_PER_TOKEN)
    while start < len(text):
        end = min(len(text), start + approx_chars)
        while end > start and _count_tokens(text[start:end], tokenizer) > max_tokens:
            end -= max(1, (end - start) // 8)
        if end == start:
            end = min(len(text), start + 1)
        ranges.append((start, end))
        start = end
    return ranges


def _pack_boundaries(
    text: str,
    boundaries: list[int],
    max_tokens: int,
    tokenizer: object | None,
) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    chunk_start = 0
    i = 1
    while i < len(boundaries):
        end = boundaries[i]
        if _count_tokens(text[chunk_start:end], tokenizer) <= max_tokens:
            i += 1
            continue
        if boundaries[i - 1] > chunk_start:
            ranges.append((chunk_start, boundaries[i - 1]))
            chunk_start = boundaries[i - 1]
            continue
        # Single boundary span still too large — give up on this pattern.
        return []
    if chunk_start < len(text):
        ranges.append((chunk_start, len(text)))
    return ranges


def split_file_into_slices(
    path: Path,
    max_tokens: int,
    *,
    tokenizer: object | None,
) -> list[FileSlice]:
    if max_tokens <= 0:
        raise ValueError(f"max_tokens must be positive, got {max_tokens}")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [FileSlice(path=path, start_char=0, end_char=0)]

    ranges = _pick_ranges(text, max_tokens, tokenizer)
    count = len(ranges)
    return [
        FileSlice(path=path, start_char=start, end_char=end, slice_index=idx, slice_count=count)
        for idx, (start, end) in enumerate(ranges)
    ]


def bisect_file_slice(slice_: FileSlice, *, tokenizer: object | None) -> tuple[FileSlice, FileSlice]:
    text = read_unit_text(slice_)
    if len(text) < 2:
        return slice_, slice_
    mid = len(text) // 2
    nl = text.rfind("\n", 0, mid)
    if nl > 0:
        mid = nl + 1
    left_end = slice_.start_char + mid
    return (
        FileSlice(path=slice_.path, start_char=slice_.start_char, end_char=left_end),
        FileSlice(path=slice_.path, start_char=left_end, end_char=slice_.end_char),
    )


def expand_oversized_files(
    files: list[Path],
    token_budget: int,
    *,
    tokenizer: object | None,
    char_cap: int | None = None,
) -> list[SemanticUnit]:
    """Replace oversized splittable text files with FileSlice units."""
    units: list[SemanticUnit] = []
    for path in files:
        if not is_splittable_text(path):
            units.append(path)
            continue
        cost = estimate_unit_tokens(path, tokenizer=tokenizer, char_cap=char_cap)
        if cost <= token_budget:
            units.append(path)
            continue
        slices = split_file_into_slices(path, token_budget, tokenizer=tokenizer)
        if len(slices) <= 1:
            units.append(path)
            continue
        print(
            f"[graphify] split {path.name} into {len(slices)} slices "
            f"(~{cost} tokens > budget {token_budget})",
            file=sys.stderr,
        )
        units.extend(slices)
    return units


def split_unit_for_retry(
    unit: SemanticUnit,
    token_budget: int,
    *,
    tokenizer: object | None,
) -> list[SemanticUnit]:
    """Break one unit into smaller pieces for adaptive retry."""
    if is_file_slice(unit):
        left, right = bisect_file_slice(unit, tokenizer=tokenizer)
        return [left, right]
    if is_splittable_text(unit):
        slices = split_file_into_slices(unit, max(256, token_budget // 2), tokenizer=tokenizer)
        if len(slices) > 1:
            return list(slices)
    return [unit]


def unit_label(unit: SemanticUnit) -> str:
    if is_file_slice(unit):
        return f"{unit.path} [{unit.slice_index + 1}/{unit.slice_count}]"
    return str(unit)


def split_chunk_for_retry(
    chunk: list[SemanticUnit],
    token_budget: int | None,
    *,
    tokenizer: object | None,
) -> list[list[SemanticUnit]] | None:
    """Split *chunk* into smaller retry units, or None if unrecoverable."""
    if len(chunk) > 1:
        mid = len(chunk) // 2
        return [chunk[:mid], chunk[mid:]]
    if len(chunk) == 1 and token_budget is not None:
        parts = split_unit_for_retry(chunk[0], token_budget, tokenizer=tokenizer)
        if len(parts) > 1:
            return [[part] for part in parts]
    return None
