"""Windows path normalization must not lowercase the file it opens (#4925).

The failure needs Windows path semantics and a case-sensitive filesystem.  A
Linux host with a case-sensitive temp directory can exercise that combination
by taking the win32 branch of cache._normalize_path and making normcase
lowercase, which is what ntpath.normcase does on Windows.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from graphify import cache


def _reset_stat_index() -> None:
    cache._stat_index = {}
    cache._stat_index_root = None
    cache._stat_index_anchor = None
    cache._stat_index_path = None
    cache._stat_index_dirty = False


@pytest.fixture
def win32_on_case_sensitive_fs(monkeypatch, tmp_path):
    probe = tmp_path / "CaseProbe"
    probe.mkdir()
    if (tmp_path / "caseprobe").exists():
        pytest.skip("needs a case-sensitive filesystem")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os.path, "normcase", lambda s: s.lower())
    # The temp path is short.  The extended-length prefix is not under test.
    monkeypatch.setattr(cache, "_os_long_path", lambda p: str(p))
    _reset_stat_index()
    yield tmp_path
    _reset_stat_index()


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_file_hash_accepts_uppercase_file(win32_on_case_sensitive_fs):
    root = win32_on_case_sensitive_fs / "Repo"
    f = _write(root / "README.md", "# Repro\nhello\n")
    assert cache.file_hash(f, root)


def test_file_hash_accepts_uppercase_root(win32_on_case_sensitive_fs):
    root = win32_on_case_sensitive_fs / "Repo"
    f = _write(root / "readme.md", "# Repro\nhello\n")
    assert cache.file_hash(f, root)


def test_save_and_load_roundtrip_uppercase(win32_on_case_sensitive_fs):
    root = win32_on_case_sensitive_fs / "Repo"
    f = _write(root / "README.md", "# Repro\nhello\n")
    result = {
        "nodes": [{"id": "readme", "label": "README"}],
        "edges": [],
        "hyperedges": [],
    }
    cache.save_cached(f, result, root=root, kind="semantic")
    assert cache.load_cached(f, root, kind="semantic") == result


def test_case_variants_with_same_content_have_different_hash(win32_on_case_sensitive_fs):
    root = win32_on_case_sensitive_fs / "Repo"
    upper = _write(root / "README.md", "# same\n")
    lower = _write(root / "readme.md", "# same\n")
    assert upper.read_bytes() == lower.read_bytes()
    assert cache.file_hash(upper, root) != cache.file_hash(lower, root)


def test_case_variants_do_not_cross_hit_the_semantic_cache(win32_on_case_sensitive_fs):
    root = win32_on_case_sensitive_fs / "Repo"
    upper = _write(root / "README.md", "# same\n")
    lower = _write(root / "readme.md", "# same\n")
    upper_result = {"nodes": [{"id": "upper"}], "edges": [], "hyperedges": []}
    lower_result = {"nodes": [{"id": "lower"}], "edges": [], "hyperedges": []}

    cache.save_cached(upper, upper_result, root=root, kind="semantic")

    # A case-sensitive volume has two files here.  The lower one has no entry.
    assert cache.load_cached(lower, root, kind="semantic") is None

    cache.save_cached(lower, lower_result, root=root, kind="semantic")
    assert cache.load_cached(upper, root, kind="semantic") == upper_result
    assert cache.load_cached(lower, root, kind="semantic") == lower_result


def test_hardlink_aliases_keep_distinct_hashes(win32_on_case_sensitive_fs):
    root = win32_on_case_sensitive_fs / "repo"
    target = _write(root / "target.txt", "same bytes\n")
    alias = root / "TARGET.txt"
    os.link(target, alias)
    assert os.path.samefile(target, alias)

    # #1989 keeps the walked path distinct even when two names share an inode.
    assert cache.file_hash(alias, root) != cache.file_hash(target, root)


def test_symlink_aliases_keep_distinct_hashes(win32_on_case_sensitive_fs):
    root = win32_on_case_sensitive_fs / "repo"
    target = _write(root / "target.txt", "same bytes\n")
    alias = root / "TARGET.txt"
    try:
        alias.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are not available here")
    assert os.path.samefile(target, alias)

    assert cache.file_hash(alias, root) != cache.file_hash(target, root)


def test_cached_word_count_uses_stat_index_for_uppercase(win32_on_case_sensitive_fs):
    root = win32_on_case_sensitive_fs / "Repo"
    f = _write(root / "README.md", "one two three\n")
    old = f.stat().st_mtime_ns - 10 * 1_000_000_000
    os.utime(f, ns=(old, old))

    calls = []

    def compute(p: Path) -> int:
        calls.append(p)
        return len(p.read_text().split())

    assert cache.cached_word_count(f, root, compute) == 3
    assert len(calls) == 1
    assert cache._stat_index, "word count must write a stat-index entry"

    assert cache.cached_word_count(f, root, compute) == 3
    assert len(calls) == 1, "second call must use the stat fastpath"
