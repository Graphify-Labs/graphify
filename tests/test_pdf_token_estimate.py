"""A PDF's token estimate must measure the text the prompt actually carries.

`_read_files` sends a PDF through `_file_to_text` -> `extract_pdf_text`, but
`_estimate_file_tokens` read the file with `read_text` and tokenised *that*. A
PDF's bytes are not its text: every real PDF Flate-compresses its content
streams, so the estimate measured a compressed binary and came out several times
too small.

`_pack_chunks_by_tokens` sizes chunks from that estimate, so an undercount
overfills the chunk, the request blows the model's context window, and
`_extract_with_adaptive_retry` bisects — paying for the same content two, four
or eight times before it fits (#2903).

Measured on one 400-line fixture, same text, stored both ways:

    uncompressed              est=5559  actual=4598  actual/est=0.83x
    FlateDecode (real PDFs)   est=1334  actual=4599  actual/est=3.45x
"""
import zlib
from pathlib import Path

import pytest

from graphify.llm import (
    _FILE_CHAR_CAP,
    _estimate_file_tokens,
    _file_to_text,
    _get_tokenizer,
    _read_files,
)

LINES = [f"Section {i}: the parser calls the tokenizer and emits a node."
         for i in range(400)]


def _make_pdf(path: Path, lines, *, compress: bool):
    """A minimal one-page PDF with a real text layer, stored raw or FlateDecode."""
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


def _actual_tokens(prompt: str) -> int:
    tok = _get_tokenizer()
    return len(tok.encode(prompt, disallowed_special=())) if tok else len(prompt) // 4


@pytest.fixture
def pdfs(tmp_path):
    raw = tmp_path / "raw.pdf"
    flate = tmp_path / "flate.pdf"
    _make_pdf(raw, LINES, compress=False)
    _make_pdf(flate, LINES, compress=True)
    if not _file_to_text(flate).strip():
        pytest.skip("pypdf not available or cannot read the fixture")
    return tmp_path, raw, flate


def test_the_two_encodings_hold_the_same_text(pdfs):
    """Precondition: only the storage differs, so any estimate gap is the bug."""
    _, raw, flate = pdfs
    assert _file_to_text(raw) == _file_to_text(flate)
    assert flate.stat().st_size < raw.stat().st_size / 4, "fixture is not really compressed"


@pytest.mark.parametrize("which", ["raw", "flate"])
def test_estimate_tracks_the_prompt_it_will_build(pdfs, which):
    root, raw, flate = pdfs
    p = raw if which == "raw" else flate
    est = _estimate_file_tokens(p)
    actual = _actual_tokens(_read_files([p], root))
    assert est > 0
    ratio = actual / est
    assert 0.7 <= ratio <= 1.4, (
        f"{which}: estimate {est} vs actual {actual} ({ratio:.2f}x) — packing "
        f"will size chunks from a number that does not describe the prompt"
    )


def test_compression_does_not_change_the_estimate(pdfs):
    """The tell: identical text stored two ways must estimate the same. It used
    to differ by 4x purely because one was compressed."""
    _, raw, flate = pdfs
    e_raw, e_flate = _estimate_file_tokens(raw), _estimate_file_tokens(flate)
    assert abs(e_raw - e_flate) <= max(8, e_raw * 0.02), (
        f"raw={e_raw} flate={e_flate} — the estimate is reading the container, "
        f"not the text"
    )


def test_estimate_is_not_derived_from_file_size(pdfs):
    """A compressed PDF is a fraction of its text's size; the estimate must not
    follow the byte count."""
    _, _, flate = pdfs
    assert _estimate_file_tokens(flate) > flate.stat().st_size / 4


def test_repeated_estimates_agree(pdfs):
    """Packing probes the same file repeatedly; the memo must not drift."""
    _, _, flate = pdfs
    assert len({_estimate_file_tokens(flate) for _ in range(4)}) == 1


def test_a_rewritten_pdf_is_re_estimated(tmp_path):
    """The memo keys on size and mtime, so editing a paper mid-run must not
    serve the previous estimate.

    Both fixtures stay well under `_FILE_CHAR_CAP` on purpose: past the cap
    `_read_files` truncates, so a bigger file legitimately estimates the same
    and the test would prove nothing about the memo.
    """
    p = tmp_path / "growing.pdf"
    _make_pdf(p, LINES[:80], compress=True)
    if not _file_to_text(p).strip():
        pytest.skip("pypdf not available")
    before = _estimate_file_tokens(p)
    _make_pdf(p, LINES[:160], compress=True)
    after = _estimate_file_tokens(p)
    assert after > before * 1.5, f"stale estimate served: {before} -> {after}"


def test_an_unreadable_pdf_estimates_zero_instead_of_raising(tmp_path):
    """Packing must not blow up on a corrupt file."""
    bad = tmp_path / "corrupt.pdf"
    bad.write_bytes(b"%PDF-1.4\nnot really a pdf\n")
    assert _estimate_file_tokens(bad) >= 0


def test_non_pdf_estimates_are_unchanged(tmp_path):
    """The fix is scoped to PDFs; a text file still measures its own bytes."""
    f = tmp_path / "notes.md"
    f.write_text("# Heading\n\n" + ("word " * 2000), encoding="utf-8")
    est = _estimate_file_tokens(f)
    actual = _actual_tokens(_read_files([f], tmp_path))
    assert 0.7 <= actual / est <= 1.4


def test_the_cap_still_applies(tmp_path):
    """A very long PDF is truncated at _FILE_CHAR_CAP by _read_files, so the
    estimate must not exceed what that cap allows."""
    p = tmp_path / "huge.pdf"
    _make_pdf(p, LINES * 12, compress=True)
    if not _file_to_text(p).strip():
        pytest.skip("pypdf not available")
    tok = _get_tokenizer()
    ceiling = (_FILE_CHAR_CAP if tok is None else _FILE_CHAR_CAP) + 1000
    assert _estimate_file_tokens(p) <= ceiling
