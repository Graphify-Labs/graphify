"""The atexit stat-index flush must not resurrect a deleted directory (#2974).

A post-commit hook runs `graphify update . &` in a short-lived worktree; the
branch merges and `git worktree remove` deletes the tree while the rebuild
is still running. The exit-time flush then `mkdir -p`'d the dead path back
into existence, leaving a husk holding nothing but
`graphify-out/cache/stat-index.json` — 81 of them over a few weeks.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from graphify import cache


@pytest.fixture(autouse=True)
def _fresh_index():
    def reset():
        cache._stat_index_root = None
        cache._stat_index_anchor = None
        cache._stat_index = {}
        cache._stat_index_dirty = False
    reset()
    yield
    reset()


def _dirty(corpus: Path) -> Path:
    f = corpus / "a.md"
    f.write_text("# hello\nbody\n", encoding="utf-8")
    cache.file_hash(f, corpus)  # loads + dirties the index for this corpus
    assert cache._stat_index_dirty
    return f


def test_a_corpus_deleted_mid_run_stays_deleted(tmp_path):
    corpus = tmp_path / "husk-race-corpus"
    corpus.mkdir()
    _dirty(corpus)
    shutil.rmtree(corpus)
    cache._flush_stat_index()  # what atexit does
    assert not corpus.exists(), "the flush resurrected the deleted corpus"
    assert not cache._stat_index_dirty  # nothing left pending for a second attempt


def test_a_redirected_cache_root_that_vanished_is_not_recreated(tmp_path):
    corpus = tmp_path / "c"
    corpus.mkdir()
    elsewhere = tmp_path / "out"
    elsewhere.mkdir()
    f = corpus / "a.md"
    f.write_text("x\n", encoding="utf-8")
    cache.file_hash(f, corpus, cache_root=elsewhere)
    shutil.rmtree(elsewhere)
    cache._flush_stat_index()
    assert not elsewhere.exists()


def test_the_index_is_still_written_for_a_live_run(tmp_path):
    """A first run writes the index before graphify-out/ exists at all; that
    stays as it was — the root is live, so creating cache/ under it is fine."""
    corpus = tmp_path / "c"
    corpus.mkdir()
    _dirty(corpus)
    cache._flush_stat_index()
    assert (corpus / "graphify-out" / "cache" / "stat-index.json").is_file()
