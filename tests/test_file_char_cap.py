"""Regression tests for the per-file semantic extraction character cap."""

from graphify import llm
from graphify.file_slice import FileSlice, expand_oversized_files


def test_file_char_cap_default_stays_at_twenty_thousand(monkeypatch, tmp_path):
    source = tmp_path / "long.md"
    source.write_text("x" * 25_000, encoding="utf-8")
    monkeypatch.delenv("GRAPHIFY_FILE_CHAR_CAP", raising=False)

    prompt = llm._read_files([source], tmp_path)

    assert prompt.count("x") == 20_000


def test_file_char_cap_env_controls_reading_and_token_estimate(monkeypatch, tmp_path):
    source = tmp_path / "long.md"
    source.write_text("x" * 25_000, encoding="utf-8")
    monkeypatch.setenv("GRAPHIFY_FILE_CHAR_CAP", "30000")
    monkeypatch.setattr(llm, "_TOKENIZER", None)

    prompt = llm._read_files([source], tmp_path)

    assert prompt.count("x") == 25_000
    assert llm._estimate_file_tokens(source) == (
        25_000 + llm._PER_FILE_OVERHEAD_CHARS
    ) // llm._CHARS_PER_TOKEN


def test_resolve_file_char_cap_falls_back_for_invalid_values(monkeypatch):
    for value in ("", "invalid", "0", "-1"):
        monkeypatch.setenv("GRAPHIFY_FILE_CHAR_CAP", value)
        assert llm._resolve_file_char_cap(20_000) == 20_000


def test_env_cap_doubles_as_slice_size(monkeypatch, tmp_path):
    """The resolved cap is the slice size: raising it merges slices back."""
    source = tmp_path / "long.md"
    source.write_text("x" * 25_000, encoding="utf-8")

    monkeypatch.delenv("GRAPHIFY_FILE_CHAR_CAP", raising=False)
    units = expand_oversized_files([source], llm._resolve_file_char_cap())
    assert all(isinstance(u, FileSlice) for u in units)
    assert len(units) == 2

    monkeypatch.setenv("GRAPHIFY_FILE_CHAR_CAP", "30000")
    units = expand_oversized_files([source], llm._resolve_file_char_cap())
    assert units == [source]


def test_estimate_slice_tokens_uses_resolved_cap(monkeypatch, tmp_path):
    source = tmp_path / "long.md"
    source.write_text("x" * 25_000, encoding="utf-8")
    monkeypatch.setenv("GRAPHIFY_FILE_CHAR_CAP", "30000")
    monkeypatch.setattr(llm, "_TOKENIZER", None)

    fs = FileSlice(path=source, start=0, end=25_000, index=0, total=1)
    assert llm._estimate_file_tokens(fs) == (
        25_000 + llm._PER_FILE_OVERHEAD_CHARS
    ) // llm._CHARS_PER_TOKEN
