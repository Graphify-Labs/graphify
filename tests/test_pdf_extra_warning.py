"""Tests for PDF text extraction warning when pypdf is missing (#3702)."""
import sys
from pathlib import Path
from graphify import detect


def test_extract_pdf_text_missing_pypdf_warns(tmp_path: Path, monkeypatch, capsys):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy content")

    # Simulate missing pypdf
    monkeypatch.setitem(sys.modules, "pypdf", None)

    result = detect.extract_pdf_text(pdf)
    assert result == ""

    captured = capsys.readouterr()
    assert "[graphify] WARNING: sample.pdf: PDF text extraction skipped: 'pypdf' is not installed." in captured.err
    assert "uv tool install 'graphifyy[pdf]'" in captured.err
