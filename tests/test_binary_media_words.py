"""Binary media stays discoverable without being decoded or counted as text."""

import builtins
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from graphify import cache
from graphify import detect as detect_mod


MEDIA_SUFFIXES = [
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".PNG",
    ".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v",
    ".mp3", ".wav", ".m4a", ".ogg", ".MP3",
]


@pytest.mark.parametrize("suffix", MEDIA_SUFFIXES)
def test_count_words_does_not_read_binary_media(tmp_path, monkeypatch, suffix):
    media = tmp_path / f"sample{suffix}"
    media.write_bytes(b"\x89\x00\xff imaginary words in binary media")
    reader = Mock(wraps=builtins.open)
    monkeypatch.setattr(detect_mod, "open", reader, raising=False)

    words = detect_mod.count_words(media)

    reader.assert_not_called()
    assert words == 0


@pytest.mark.parametrize("suffix", [".svg", ".SVG", ".txt", ".md", ".py"])
def test_count_words_preserves_text(tmp_path, suffix):
    path = tmp_path / f"sample{suffix}"
    text = "<svg><text>real words</text></svg>" if suffix.lower() == ".svg" else "real words"
    path.write_text(text, encoding="utf-8")

    assert detect_mod.count_words(path) == 2


@pytest.mark.parametrize("suffix,extractor", [
    (".pdf", "extract_pdf_text"),
    (".docx", "docx_to_markdown"),
    (".xlsx", "xlsx_to_markdown"),
])
def test_count_words_preserves_document_extraction(tmp_path, monkeypatch, suffix, extractor):
    path = tmp_path / f"document{suffix}"
    path.write_bytes(b"binary document container")
    convert = Mock(return_value="three extracted words")
    monkeypatch.setattr(detect_mod, extractor, convert)

    assert detect_mod.count_words(path) == 3
    convert.assert_called_once_with(path)


@pytest.mark.parametrize("cached_counts", [False, True], ids=["cold", "legacy-cache"])
def test_detect_keeps_media_without_counting_it(tmp_path, monkeypatch, cached_counts):
    for name, value in (
        ("_stat_index", {}), ("_stat_index_root", None),
        ("_stat_index_anchor", None), ("_stat_index_path", None),
        ("_stat_index_dirty", False),
    ):
        monkeypatch.setattr(cache, name, value)
    monkeypatch.setenv("GRAPHIFY_MTIME_GRANULARITY_MS", "2000")

    media_paths = [tmp_path / f"media_{index}{suffix}"
                   for index, suffix in enumerate(MEDIA_SUFFIXES)]
    for path in media_paths:
        path.write_bytes(b"\x89\x00\xff imaginary words in binary media")
        if cached_counts:
            old = path.stat().st_mtime_ns - 10_000_000_000
            os.utime(path, ns=(old, old))
            assert cache.cached_word_count(path, tmp_path, lambda _: 999) == 999
            recompute = Mock(return_value=0)
            assert cache.cached_word_count(path, tmp_path, recompute) == 999
            recompute.assert_not_called()

    svg = tmp_path / "diagram.SVG"
    svg.write_text("<svg><text>real words</text></svg>", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("three real words", encoding="utf-8")
    word_cache = Mock(wraps=cache.cached_word_count)
    monkeypatch.setattr(cache, "cached_word_count", word_cache)

    result = detect_mod.detect(tmp_path)

    images = {Path(p) for p in result["files"]["image"]}
    videos = {Path(p) for p in result["files"]["video"]}
    assert images == {svg} | {p for p in media_paths if p.suffix.lower() in detect_mod.IMAGE_EXTENSIONS}
    assert videos == {p for p in media_paths if p.suffix.lower() in detect_mod.VIDEO_EXTENSIONS}
    assert result["total_files"] == len(media_paths) + 2
    assert result["total_words"] == 5
    assert {call.args[0] for call in word_cache.call_args_list} == {svg, tmp_path / "notes.txt"}
