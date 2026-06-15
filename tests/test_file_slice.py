"""Tests for intra-file slicing used by semantic extraction."""
from pathlib import Path
from unittest.mock import patch

import pytest

from graphify.file_slice import (
    FileSlice,
    bisect_file_slice,
    expand_oversized_files,
    is_splittable_text,
    read_unit_text,
    split_chunk_for_retry,
    split_file_into_slices,
    split_unit_for_retry,
    unit_label,
)


def test_is_splittable_text_recognises_markdown():
    assert is_splittable_text(Path("doc.md"))
    assert is_splittable_text(Path("doc.MDX"))
    assert not is_splittable_text(Path("code.py"))


def test_split_file_into_slices_respects_token_budget(tmp_path):
    doc = tmp_path / "big.md"
    doc.write_text("# One\n\n" + ("paragraph.\n\n" * 200))

    slices = split_file_into_slices(doc, max_tokens=50, tokenizer=None)
    assert len(slices) > 1
    assert all(isinstance(s, FileSlice) for s in slices)
    assert slices[0].slice_index == 0
    assert slices[-1].slice_count == len(slices)
    rejoined = "".join(read_unit_text(s) for s in slices)
    assert rejoined == doc.read_text(encoding="utf-8")


def test_expand_oversized_files_splits_markdown_only(tmp_path):
    md = tmp_path / "big.md"
    md.write_text("x" * 20_000)
    py = tmp_path / "big.py"
    py.write_text("x" * 20_000)

    with patch("graphify.file_slice._count_tokens", side_effect=lambda text, _tok: len(text) // 4):
        units = expand_oversized_files([md, py], token_budget=1_000, tokenizer=None)

    md_units = [u for u in units if getattr(u, "path", u) == md or u == md]
    py_units = [u for u in units if getattr(u, "path", u) == py or u == py]
    assert len(md_units) > 1
    assert py_units == [py]


def test_bisect_file_slice_splits_on_newline(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("line one\nline two\nline three\n")
    whole = FileSlice(path=doc, start_char=0, end_char=len(doc.read_text(encoding="utf-8")))
    left, right = bisect_file_slice(whole, tokenizer=None)
    assert read_unit_text(left) + read_unit_text(right) == doc.read_text(encoding="utf-8")
    assert left.end_char == right.start_char


def test_split_unit_for_retry_bisects_existing_slice(tmp_path):
    doc = tmp_path / "doc.md"
    text = "a" * 100
    doc.write_text(text)
    sl = FileSlice(path=doc, start_char=0, end_char=len(text))
    parts = split_unit_for_retry(sl, token_budget=2_000, tokenizer=None)
    assert len(parts) == 2


def test_split_unit_for_retry_splits_whole_markdown(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("# Title\n\n" + ("body line\n" * 800))

    with patch("graphify.file_slice._count_tokens", side_effect=lambda text, _tok: len(text) // 4):
        parts = split_unit_for_retry(doc, token_budget=100, tokenizer=None)

    assert len(parts) > 1


def test_split_chunk_for_retry_splits_multi_file_chunk(tmp_path):
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    a.write_text("# A\n")
    b.write_text("# B\n")
    sub = split_chunk_for_retry([a, b], token_budget=1000, tokenizer=None)
    assert sub is not None and len(sub) == 2


def test_unit_label_for_slice(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("# x\n")
    sl = FileSlice(path=doc, start_char=0, end_char=3, slice_index=1, slice_count=4)
    assert unit_label(sl) == f"{doc} [2/4]"
