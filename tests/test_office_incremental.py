"""#1649 — a modified .docx/.xlsx must re-enter --update.

detect_incremental tracks the converted markdown SIDECAR, not the Office
source. convert_office_file used to early-return whenever the sidecar existed,
so a source edited after its first conversion never updated its sidecar and was
reported "unchanged" forever. It now re-converts when the source is newer than
the sidecar (and still skips an unchanged source so it never churns, #1226).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from graphify import detect

docx = pytest.importorskip("docx")


def _make_docx(path: Path, text: str) -> None:
    d = docx.Document()
    d.add_paragraph(text)
    d.save(str(path))


def _bump_mtime(path: Path, offset: float) -> None:
    """Set path's mtime relative to now so ordering is deterministic."""
    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + offset))


def test_modified_docx_reconverts_sidecar(tmp_path: Path):
    src = tmp_path / "doc.docx"
    out = tmp_path / "converted"
    _make_docx(src, "original alpha content")

    sidecar = detect.convert_office_file(src, out)
    assert sidecar is not None
    assert "original alpha content" in sidecar.read_text(encoding="utf-8")

    # Edit the source and make it newer than the sidecar.
    _make_docx(src, "revised beta content")
    _bump_mtime(sidecar, -10)  # sidecar older than the freshly-written source

    sidecar2 = detect.convert_office_file(src, out)
    assert sidecar2 == sidecar  # same deterministic name
    body = sidecar2.read_text(encoding="utf-8")
    assert "revised beta content" in body
    assert "original alpha content" not in body


def test_unchanged_docx_sidecar_not_rewritten(tmp_path: Path):
    src = tmp_path / "doc.docx"
    out = tmp_path / "converted"
    _make_docx(src, "stable content")

    sidecar = detect.convert_office_file(src, out)
    assert sidecar is not None
    # Make the sidecar clearly newer than the (unchanged) source.
    _bump_mtime(sidecar, 100)
    before = sidecar.stat().st_mtime

    sidecar2 = detect.convert_office_file(src, out)
    assert sidecar2 == sidecar
    # Not rewritten: mtime unchanged, so detect_incremental won't see churn (#1226).
    assert sidecar2.stat().st_mtime == before
