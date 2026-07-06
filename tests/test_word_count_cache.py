"""#1656 — word counts are cached against each file's stat signature so
detect() doesn't re-parse every unchanged PDF/docx on each run just to size
the corpus.
"""
from __future__ import annotations

from pathlib import Path

from graphify import cache


def test_word_count_cached_until_file_changes(tmp_path, monkeypatch):
    # Isolate the stat index to this tmp root.
    monkeypatch.setattr(cache, "_stat_index", {})
    monkeypatch.setattr(cache, "_stat_index_root", None)

    f = tmp_path / "doc.txt"
    f.write_text("one two three four five")

    calls = {"n": 0}
    def compute(p: Path) -> int:
        calls["n"] += 1
        return len(p.read_text().split())

    assert cache.cached_word_count(f, tmp_path, compute) == 5
    assert calls["n"] == 1
    # Second call, file unchanged → served from cache, compute NOT re-run.
    assert cache.cached_word_count(f, tmp_path, compute) == 5
    assert calls["n"] == 1

    # Change the file → recompute.
    f.write_text("only three words now")  # 4 words
    assert cache.cached_word_count(f, tmp_path, compute) == 4
    assert calls["n"] == 2


def test_word_count_augments_existing_hash_entry(tmp_path, monkeypatch):
    # cached_word_count must not clobber a hash already stored for the file.
    monkeypatch.setattr(cache, "_stat_index", {})
    monkeypatch.setattr(cache, "_stat_index_root", None)

    f = tmp_path / "m.py"
    f.write_text("x = 1\n")  # -> ["x", "=", "1"] == 3 tokens
    h = cache.file_hash(f, tmp_path)
    assert h
    wc = cache.cached_word_count(f, tmp_path, lambda p: len(p.read_text().split()))
    assert wc == 3
    # The hash entry survives alongside the word_count.
    assert cache.file_hash(f, tmp_path) == h
    key = str(cache._normalize_path(f).resolve())
    entry = cache._stat_index[key]
    assert entry.get("hash") == h and entry.get("word_count") == 3
