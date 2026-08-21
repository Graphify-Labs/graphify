"""A PDF over the character cap must be sliced, not truncated.

`_read_files` caps every unit at `_FILE_CHAR_CAP` (20,000 characters).
`expand_oversized_files` slices oversized documents so the whole file still
reaches the model — but it read candidates with `path.read_text()` and
`read_slice_text` sliced the same way, while `llm._file_to_text` routes a PDF
through `extract_pdf_text`. Slicing a PDF would therefore have indexed the
container's bytes rather than its text, so PDFs were excluded from slicing
altogether and simply lost everything past 20,000 characters.

Papers are the longest documents anyone points graphify at, and a compressed
PDF gives no hint of its text length: the fixture here is 3,094 bytes on disk
and 55,690 characters of text (#2906).

`unit_source_text` is the fix: one reader that returns the string the prompt
will carry, used by both the boundary pass and the slice reader, so the offsets
a `FileSlice` holds always index the same string.
"""
import zlib
from pathlib import Path

import pytest

from graphify.file_slice import (
    FileSlice,
    bisect_slice,
    expand_oversized_files,
    is_splittable_text,
    read_slice_text,
)
from graphify.llm import _FILE_CHAR_CAP, _file_to_text, _read_files

try:  # the reader this fix introduces
    from graphify.file_slice import unit_source_text
except ImportError:  # pre-fix tree — describe the expected text the same way
    unit_source_text = _file_to_text  # type: ignore[assignment]

LINES = [f"Section {i}: the parser calls the tokenizer and emits a node."
         for i in range(900)]


def _make_pdf(path: Path, lines, *, compress: bool = True):
    ops = "BT /F1 10 Tf 20 780 Td 12 TL\n" + "".join(f"({ln}) Tj T*\n" for ln in lines) + "ET"
    raw = ops.encode("latin-1", "replace")
    stream = zlib.compress(raw) if compress else raw
    filt = b" /Filter /FlateDecode" if compress else b""
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + filt + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    path.write_bytes(bytes(out))


@pytest.fixture
def big_pdf(tmp_path):
    p = tmp_path / "paper.pdf"
    _make_pdf(p, LINES)
    if not _file_to_text(p).strip():
        pytest.skip("pypdf not available or cannot read the fixture")
    return tmp_path, p


def test_the_fixture_is_the_shape_the_bug_needs(big_pdf):
    """Precondition: small on disk, large in text — which is why file size never
    revealed the problem."""
    _, p = big_pdf
    text = unit_source_text(p)
    assert len(text) > 2 * _FILE_CHAR_CAP
    assert p.stat().st_size < len(text) / 4


def test_a_pdf_is_splittable(big_pdf):
    _, p = big_pdf
    assert is_splittable_text(p)


def test_an_oversized_pdf_is_sliced(big_pdf):
    _, p = big_pdf
    units = expand_oversized_files([p], _FILE_CHAR_CAP)
    assert len(units) > 1
    assert all(isinstance(u, FileSlice) for u in units)


def test_the_slices_tile_the_extracted_text_exactly(big_pdf):
    """Gap-free and non-overlapping: rejoining reproduces the document."""
    _, p = big_pdf
    units = expand_oversized_files([p], _FILE_CHAR_CAP)
    assert "".join(read_slice_text(u) for u in units) == unit_source_text(p)


def test_no_slice_exceeds_the_cap(big_pdf):
    _, p = big_pdf
    for u in expand_oversized_files([p], _FILE_CHAR_CAP):
        assert len(read_slice_text(u)) <= _FILE_CHAR_CAP


def test_a_slice_indexes_text_not_bytes(big_pdf):
    """The bug in one assertion: slicing used to address the container. A slice
    must not contain PDF structure."""
    _, p = big_pdf
    first = expand_oversized_files([p], _FILE_CHAR_CAP)[0]
    body = read_slice_text(first)
    assert "%PDF" not in body
    assert "endstream" not in body
    assert "Section 0" in body


def test_the_tail_reaches_the_prompt(big_pdf):
    """The symptom a user would notice: content past 20k could never become a
    node because the model never saw it."""
    root, p = big_pdf
    text = unit_source_text(p)
    tail = text[-80:].strip()[:40]
    units = expand_oversized_files([p], _FILE_CHAR_CAP)
    joined = "".join(_read_files([u], root) for u in units)
    assert tail and tail in joined


# ---------------------------------------------------------------------------
# What must NOT change
# ---------------------------------------------------------------------------

def test_a_small_pdf_still_passes_through_whole(tmp_path):
    p = tmp_path / "note.pdf"
    _make_pdf(p, LINES[:20])
    if not _file_to_text(p).strip():
        pytest.skip("pypdf not available")
    assert expand_oversized_files([p], _FILE_CHAR_CAP) == [p]


def test_plain_text_slicing_is_unchanged(tmp_path):
    f = tmp_path / "doc.md"
    body = "# H\n\n" + ("word " * 12000)
    f.write_text(body, encoding="utf-8")
    units = expand_oversized_files([f], _FILE_CHAR_CAP)
    assert len(units) > 1
    assert "".join(read_slice_text(u) for u in units) == body


def test_images_and_code_are_still_not_sliced(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 40_000)
    code = tmp_path / "m.py"
    code.write_text("def f():\n    pass\n" * 4000, encoding="utf-8")
    assert not is_splittable_text(img)
    assert not is_splittable_text(code)
    assert expand_oversized_files([img, code], _FILE_CHAR_CAP) == [img, code]


def test_a_corrupt_pdf_does_not_break_the_pass(tmp_path):
    bad = tmp_path / "corrupt.pdf"
    bad.write_bytes(b"%PDF-1.4\nnot really a pdf\n")
    assert expand_oversized_files([bad], _FILE_CHAR_CAP) == [bad]


def test_a_rewritten_pdf_is_re_read(tmp_path):
    """The reader memoises on (path, size, mtime), so a paper replaced mid-run
    must not be sliced against the previous text."""
    p = tmp_path / "growing.pdf"
    _make_pdf(p, LINES[:60])
    if not _file_to_text(p).strip():
        pytest.skip("pypdf not available")
    before = len(unit_source_text(p))
    _make_pdf(p, LINES[:600])
    after = len(unit_source_text(p))
    assert after > before * 5, f"stale text served: {before} -> {after}"


def test_repeated_reads_agree(big_pdf):
    _, p = big_pdf
    assert len({unit_source_text(p) for _ in range(3)}) == 1


def test_bisect_slice_of_a_pdf_indexes_extracted_text_not_bytes(big_pdf):
    """The adaptive-retry path (a lone oversized slice that still overflows) calls
    bisect_slice. For a PDF it must split the EXTRACTED text, not the raw
    container: the cut has to land on a newline boundary in the extracted text and
    the two halves must tile the original slice exactly. Reading container bytes
    (the pre-fix behavior) searched for the newline in binary coordinates, so the
    cut would not align to a text line."""
    _, p = big_pdf
    text = unit_source_text(p)
    whole = FileSlice(p, 0, len(text), 0, 1)
    halves = bisect_slice(whole)
    assert halves is not None, "a multi-line PDF slice must be splittable"
    left, right = halves
    # cut lands just after a newline in the EXTRACTED text (byte-coordinate search
    # on the compressed container could not produce a text-aligned cut here)
    assert text[left.end - 1] == "\n", "cut did not land on an extracted-text line boundary"
    # halves tile the original slice exactly, in text coordinates
    assert read_slice_text(left) + read_slice_text(right) == text
    assert left.start == 0 and right.end == len(text) and left.end == right.start
