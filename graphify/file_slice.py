"""Intra-file slicing for oversized text documents (#1369).

The extraction packer (`_pack_chunks_by_tokens`) treats each file as atomic and
`_read_files` caps every file at ``_FILE_CHAR_CAP`` characters, so a document
larger than that cap had everything past the cap silently dropped — the model
never saw it, and nothing in the adaptive-retry path could recover it ("a single
file larger than the budget ... packing can't shrink one big file").

This module splits an oversized *splittable text* document (Markdown, plain
text, reStructuredText) into contiguous ``FileSlice`` units at heading /
paragraph / line boundaries so the whole file gets extracted across several
units. Every slice of a file reports the **parent file path** as its source, so
the resulting nodes are never fragmented per-slice — they merge by source_file
exactly as if the file had been extracted in one pass.

Only plain-text documents are sliced: code files need whole-symbol context, and
PDFs/images are read through their own extractors and have no char-offset model.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Plain-text document types where boundary-based slicing is meaningful and where
# `_file_to_text` is a straight ``read_text`` (so a char range matches the bytes
# the model is shown). Deliberately excludes code (.py, .ts, ...) and binary
# docs (.pdf) — those are never sliced.
_SPLITTABLE_TEXT_SUFFIXES = frozenset({".md", ".mdx", ".markdown", ".txt", ".rst"})

# Boundary preferences, strongest first. A Markdown heading (``\n#``) keeps a
# section with its title; a blank line keeps a paragraph intact; a bare newline
# avoids cutting mid-line. If none is found in the window we hard-cut.
_BOUNDARY_SEPARATORS = ("\n#", "\n\n", "\n")


@dataclass(frozen=True)
class FileSlice:
    """A contiguous ``[start, end)`` character range of a splittable text file.

    ``index``/``total`` are for logging only. ``path`` is the real file on disk;
    the slice always reports ``path`` as its source so slices don't fragment the
    graph.
    """

    path: Path
    start: int
    end: int
    index: int
    total: int


# A unit of extraction work: either a whole file (``Path``) or one slice of one.
Unit = "Path | FileSlice"


def unit_path(unit: "Path | FileSlice") -> Path:
    """The on-disk path a unit belongs to (the parent file for a slice)."""
    return unit.path if isinstance(unit, FileSlice) else unit


def is_splittable_text(path: Path) -> bool:
    """True for plain-text document types that may be sliced."""
    return path.suffix.lower() in _SPLITTABLE_TEXT_SUFFIXES


def _best_cut(text: str, start: int, end: int) -> int:
    """Return a cut index in ``(start, end]`` at the strongest nearby boundary.

    Searches the window ``text[start:end]`` for the latest heading, then blank
    line, then newline, and returns the index just *after* it (a heading cuts
    just *before* the ``#`` so the heading leads the next slice). Falls back to a
    hard cut at ``end`` when the window has no usable boundary, which still makes
    forward progress because ``end > start``.
    """
    window = text[start:end]
    for sep in _BOUNDARY_SEPARATORS:
        idx = window.rfind(sep)
        if idx > 0:  # a boundary strictly inside the window (non-empty prev slice)
            if sep == "\n#":
                return start + idx + 1  # keep the newline with the previous slice
            return start + idx + len(sep)
    return end


def slice_boundaries(text: str, max_chars: int) -> list[tuple[int, int]]:
    """Contiguous ``(start, end)`` ranges covering all of ``text``, each ≤ max_chars.

    Ranges are gap-free and non-overlapping, so concatenating the slices
    reproduces ``text`` exactly — no content is dropped.
    """
    n = len(text)
    if n <= max_chars:
        return [(0, n)]
    bounds: list[tuple[int, int]] = []
    pos = 0
    while pos < n:
        hard = min(pos + max_chars, n)
        end = _best_cut(text, pos, hard) if hard < n else n
        if end <= pos:  # defensive: never stall
            end = hard
        bounds.append((pos, end))
        pos = end
    return bounds


def expand_oversized_files(
    files: list[Path], max_chars: int
) -> list["Path | FileSlice"]:
    """Replace each oversized splittable-text file with a list of ``FileSlice``s.

    Files at or below ``max_chars`` (and all non-splittable files) pass through
    unchanged as ``Path``, so behaviour is identical for everything that already
    fit. Unreadable files pass through untouched (the reader handles the error).
    """
    out: list["Path | FileSlice"] = []
    for f in files:
        if not is_splittable_text(f):
            out.append(f)
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            out.append(f)
            continue
        if len(text) <= max_chars:
            out.append(f)
            continue
        ranges = slice_boundaries(text, max_chars)
        total = len(ranges)
        for i, (s, e) in enumerate(ranges):
            out.append(FileSlice(path=f, start=s, end=e, index=i, total=total))
    return out


def read_slice_text(fs: FileSlice) -> str:
    """Read just this slice's characters from its parent file."""
    text = fs.path.read_text(encoding="utf-8", errors="replace")
    return text[fs.start:fs.end]


def bisect_slice(fs: FileSlice) -> tuple[FileSlice, FileSlice] | None:
    """Split a slice into two halves at a newline near its midpoint, or None.

    Used by the adaptive-retry path when a single slice still overflows the
    model's output: halving it produces a smaller response. Returns None when the
    slice is already too small to split meaningfully.
    """
    if fs.end - fs.start <= 1:
        return None
    try:
        text = fs.path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    mid = (fs.start + fs.end) // 2
    nl = text.find("\n", mid, fs.end)
    cut = nl + 1 if (nl != -1 and fs.start < nl + 1 < fs.end) else mid
    if not (fs.start < cut < fs.end):
        return None
    left = FileSlice(fs.path, fs.start, cut, fs.index, fs.total)
    right = FileSlice(fs.path, cut, fs.end, fs.index, fs.total)
    return left, right
