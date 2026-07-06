from __future__ import annotations

from pathlib import Path

import pytest

from graphify import llm
from graphify.file_slice import (
    FileSlice,
    bisect_slice,
    expand_oversized_files,
    is_splittable_text,
    read_slice_text,
    slice_boundaries,
    unit_path,
)


# ── slice_boundaries: coverage + bounds invariants ──────────────────────────

def test_slice_boundaries_small_text_is_one_range():
    text = "short doc"
    assert slice_boundaries(text, 100) == [(0, len(text))]


@pytest.mark.parametrize("max_chars", [50, 100, 500, 1000])
def test_slice_boundaries_full_coverage_and_bounds(max_chars):
    text = ("# Heading\n\n" + "lorem ipsum " * 40 + "\n\n") * 20
    bounds = slice_boundaries(text, max_chars)
    # contiguous, gap-free, non-overlapping, covering the whole text
    assert bounds[0][0] == 0
    assert bounds[-1][1] == len(text)
    for (s0, e0), (s1, e1) in zip(bounds, bounds[1:]):
        assert e0 == s1
    # concatenation reproduces the text exactly (no dropped content)
    assert "".join(text[s:e] for s, e in bounds) == text
    # every slice respects the budget
    assert all((e - s) <= max_chars for s, e in bounds)


def test_slice_boundaries_single_huge_line_still_progresses():
    # No newline at all → must hard-cut and still cover everything.
    text = "x" * 5000
    bounds = slice_boundaries(text, 1000)
    assert "".join(text[s:e] for s, e in bounds) == text
    assert all((e - s) <= 1000 for s, e in bounds)


def test_slice_boundaries_prefers_heading_boundary():
    a = "# A\n" + "a" * 30 + "\n"
    b = "# B\n" + "b" * 30 + "\n"
    text = a + b
    bounds = slice_boundaries(text, len(a) + 5)  # forces a split near the A/B seam
    # the second slice should start at the "# B" heading
    second_start = bounds[1][0]
    assert text[second_start:second_start + 3] == "# B"


# ── expand_oversized_files ──────────────────────────────────────────────────

def _write(p: Path, text: str) -> Path:
    p.write_text(text, encoding="utf-8")
    return p


def test_expand_small_file_stays_whole(tmp_path):
    f = _write(tmp_path / "small.md", "# Tiny\n\nhi\n")
    units = expand_oversized_files([f], max_chars=1000)
    assert units == [f]


def test_expand_oversized_markdown_is_sliced_with_full_coverage(tmp_path):
    text = ("# Section\n\n" + "word " * 200 + "\n\n") * 30
    f = _write(tmp_path / "big.md", text)
    units = expand_oversized_files([f], max_chars=2000)
    slices = [u for u in units if isinstance(u, FileSlice)]
    assert len(slices) >= 2
    assert all(isinstance(u, FileSlice) for u in units)
    # slices reconstruct the whole file
    assert "".join(read_slice_text(s) for s in slices) == text
    assert all((s.end - s.start) <= 2000 for s in slices)
    # every slice points back at the parent file (anti-fragmentation)
    assert all(s.path == f for s in slices)
    assert slices[0].total == len(slices)


def test_expand_does_not_slice_code_even_when_oversized(tmp_path):
    f = _write(tmp_path / "mod.py", "x = 1\n" * 6000)  # >> max_chars but code
    assert not is_splittable_text(f)
    units = expand_oversized_files([f], max_chars=2000)
    assert units == [f]  # stays whole — code needs whole-symbol context


def test_expand_unreadable_file_passes_through(tmp_path):
    missing = tmp_path / "nope.md"
    units = expand_oversized_files([missing], max_chars=10)
    assert units == [missing]


# ── anti-fragmentation: slices share one source_file in the prompt ──────────

def test_read_files_keys_every_slice_to_parent_path(tmp_path):
    import re
    text = ("# H\n\n" + "lorem " * 300 + "\n\n") * 20
    f = _write(tmp_path / "doc.md", text)
    units = expand_oversized_files([f], max_chars=llm._FILE_CHAR_CAP)
    slices = [u for u in units if isinstance(u, FileSlice)]
    assert len(slices) >= 2
    prompt = llm._read_files(units, tmp_path)
    rels = re.findall(r'<untrusted_source path="([^"]+)"', prompt)
    # one block per slice, all pointing at the same parent path
    assert rels == ["doc.md"] * len(slices)


# ── unit helpers, estimation, partition, packing ────────────────────────────

def test_unit_path_resolves_slice_and_path(tmp_path):
    f = tmp_path / "a.md"
    fs = FileSlice(path=f, start=0, end=5, index=0, total=1)
    assert unit_path(fs) == f
    assert unit_path(f) == f


def test_estimate_tokens_for_slice_scales_with_range(tmp_path):
    f = _write(tmp_path / "a.md", "z" * 10_000)
    small = FileSlice(f, 0, 100, 0, 2)
    big = FileSlice(f, 0, 8000, 1, 2)
    assert llm._estimate_file_tokens(small) < llm._estimate_file_tokens(big)


def test_partition_keeps_slices_as_text(tmp_path):
    f = tmp_path / "a.md"
    fs = FileSlice(f, 0, 5, 0, 1)
    img = tmp_path / "pic.png"
    text_units, image_files = llm._partition_semantic_files([fs, img])
    assert fs in text_units
    assert image_files == [img]


def test_pack_chunks_handles_slices(tmp_path):
    text = ("# H\n\n" + "word " * 300 + "\n\n") * 20
    f = _write(tmp_path / "big.md", text)
    units = expand_oversized_files([f], max_chars=llm._FILE_CHAR_CAP)
    chunks = llm._pack_chunks_by_tokens(units, token_budget=2000)
    # all units land in some chunk; flattening recovers them all
    flat = [u for ch in chunks for u in ch]
    assert len(flat) == len(units)


# ── bisect_slice (adaptive-retry path) ──────────────────────────────────────

def test_bisect_slice_splits_at_newline(tmp_path):
    f = _write(tmp_path / "a.md", "alpha\n" * 100)
    fs = FileSlice(f, 0, 600, 0, 1)
    halves = bisect_slice(fs)
    assert halves is not None
    left, right = halves
    assert left.start == fs.start and right.end == fs.end
    assert left.end == right.start  # contiguous, no gap
    assert fs.start < left.end < fs.end


def test_bisect_slice_returns_none_for_tiny(tmp_path):
    f = _write(tmp_path / "a.md", "ab")
    assert bisect_slice(FileSlice(f, 0, 1, 0, 1)) is None
