"""Tests for PDF text extraction warning when pypdf is missing (#3702)."""
import sys
from pathlib import Path

import pytest

from graphify import detect


@pytest.fixture(autouse=True)
def _reset_warn_flag(monkeypatch):
    # The warn-once flag is process-global; reset it per test so each test
    # starts from an un-warned state.
    monkeypatch.setattr(detect, "_pypdf_missing_warned", False)


def test_extract_pdf_text_missing_pypdf_warns(tmp_path: Path, monkeypatch, capsys):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy content")

    # Simulate missing pypdf
    monkeypatch.setitem(sys.modules, "pypdf", None)

    result = detect.extract_pdf_text(pdf)
    assert result == ""

    captured = capsys.readouterr()
    assert "PDF text extraction skipped: 'pypdf' is not installed." in captured.err
    assert "uv tool install 'graphifyy[pdf]'" in captured.err


def test_extract_pdf_text_missing_pypdf_warns_once_across_many_pdfs(
    tmp_path: Path, monkeypatch, capsys
):
    """A corpus of many PDFs with pypdf missing must produce exactly one warning,
    not one per file."""
    monkeypatch.setitem(sys.modules, "pypdf", None)

    for i in range(5):
        pdf = tmp_path / f"doc{i}.pdf"
        pdf.write_bytes(b"%PDF-1.4 dummy content")
        assert detect.extract_pdf_text(pdf) == ""

    captured = capsys.readouterr()
    assert captured.err.count("PDF text extraction skipped") == 1
