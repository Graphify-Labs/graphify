"""Tests for file truncation warning in _read_files when exceeding _FILE_CHAR_CAP (#3773)."""
from pathlib import Path

import pytest

from graphify import llm


@pytest.fixture(autouse=True)
def _reset_warn_flag(monkeypatch):
    # The warn-once flag is process-global; reset it per test so each test
    # starts from an un-warned state.
    monkeypatch.setattr(llm, "_file_truncation_warned", False)


def test_read_files_exceeding_char_cap_warns(tmp_path: Path, capsys):
    doc = tmp_path / "oversized.txt"
    doc.write_text("a" * (llm._FILE_CHAR_CAP + 500), encoding="utf-8")

    result = llm._read_files([doc], tmp_path)
    assert len(result) > 0

    captured = capsys.readouterr()
    assert f"[graphify] WARNING: file {doc.name} exceeds {llm._FILE_CHAR_CAP} characters and was truncated" in captured.err


def test_read_files_under_char_cap_does_not_warn(tmp_path: Path, capsys):
    doc = tmp_path / "small.txt"
    doc.write_text("a" * 1000, encoding="utf-8")

    result = llm._read_files([doc], tmp_path)
    assert len(result) > 0

    captured = capsys.readouterr()
    assert captured.err == ""


def test_read_files_warns_once_across_multiple_oversized_files(tmp_path: Path, capsys):
    """A run with multiple files exceeding the cap must produce exactly one warning,
    not spam stderr per file."""
    docs = []
    for i in range(3):
        doc = tmp_path / f"large_{i}.txt"
        doc.write_text("x" * (llm._FILE_CHAR_CAP + 1000), encoding="utf-8")
        docs.append(doc)

    result = llm._read_files(docs, tmp_path)
    assert len(result) > 0

    captured = capsys.readouterr()
    assert captured.err.count("was truncated") == 1
