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


@pytest.fixture
def _reset_failed_warned(monkeypatch):
    monkeypatch.setattr(detect, "_pdf_failed_warned", set(), raising=False)


def test_extract_pdf_text_unreadable_pdf_warns(tmp_path: Path, capsys, _reset_failed_warned):
    """#4527: a PDF pypdf cannot read still returns "", but must say so on
    stderr instead of looking exactly like a PDF with no text."""
    pytest.importorskip("pypdf")
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"this is not a pdf")

    assert detect.extract_pdf_text(pdf) == ""

    err = capsys.readouterr().err
    assert "could not extract text from" in err
    assert "broken.pdf" in err


def test_extract_pdf_text_encrypted_pdf_warns(tmp_path: Path, capsys, _reset_failed_warned):
    """An encrypted PDF opened without its password is a failed read, not an
    empty document (#4527)."""
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.encrypt(user_password="secret", algorithm="RC4-128")
    pdf = tmp_path / "locked.pdf"
    with pdf.open("wb") as fh:
        writer.write(fh)

    assert detect.extract_pdf_text(pdf) == ""

    err = capsys.readouterr().err
    assert "could not extract text from" in err
    assert "locked.pdf" in err


def test_extract_pdf_text_unreadable_pdf_warns_once_per_file(
    tmp_path: Path, capsys, _reset_failed_warned
):
    """detect() and the semantic pass both read the same PDF; one bad file
    must warn once, while a second bad file still gets its own warning."""
    pytest.importorskip("pypdf")
    first = tmp_path / "a.pdf"
    second = tmp_path / "b.pdf"
    first.write_bytes(b"garbage")
    second.write_bytes(b"garbage")

    for _ in range(3):
        assert detect.extract_pdf_text(first) == ""
    assert detect.extract_pdf_text(second) == ""

    err = capsys.readouterr().err
    assert err.count("could not extract text from") == 2


def test_extract_pdf_text_empty_but_valid_pdf_does_not_warn(
    tmp_path: Path, capsys, _reset_failed_warned
):
    """A readable PDF with no text layer is not a failure and stays silent."""
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72, height=72)
    pdf = tmp_path / "blank.pdf"
    with pdf.open("wb") as fh:
        writer.write(fh)

    assert detect.extract_pdf_text(pdf) == ""

    assert "could not extract text from" not in capsys.readouterr().err
