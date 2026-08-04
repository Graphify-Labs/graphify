"""A same-size edit inside one filesystem tick must not reuse a stale digest.

``file_hash`` memoises on ``(size, mtime_ns)`` to skip re-reading unchanged
files. That assumes a content change always moves one of the two, which is
false: an edit keeping the file the same length and landing inside a single
timestamp tick is invisible to stat, so the old digest is served and every
consumer — the semantic cache, incremental extraction, ``prune_semantic_cache``
— keeps treating the new content as the old.

The fastpath itself must survive: a corpus copied with ``copy2`` (mtimes
preserved) has to stay 100% warm, or every relocated checkout re-bills a full
extraction.
"""
import os
import time
from pathlib import Path

import pytest

from graphify import cache


@pytest.fixture(autouse=True)
def _fresh_index():
    cache._stat_index = {}
    cache._stat_index_root = None
    yield
    cache._stat_index = {}
    cache._stat_index_root = None


def _count_reads(monkeypatch, name):
    hits = {"n": 0}
    real = Path.read_bytes

    def counting(self, *a, **k):
        if self.name == name:
            hits["n"] += 1
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_bytes", counting)
    return hits


def test_same_size_rewrite_in_one_tick_changes_the_digest(tmp_path):
    """The bug: two different documents, same length, one timestamp tick."""
    f = tmp_path / "doc.md"
    f.write_text("# A\n\nContent A.\n", encoding="utf-8")
    first = cache.file_hash(f, tmp_path)

    f.write_text("# B\n\nContent B.\n", encoding="utf-8")
    second = cache.file_hash(f, tmp_path)

    assert len("# A\n\nContent A.\n") == len("# B\n\nContent B.\n")
    assert first != second, "a same-size rewrite must not reuse the old digest"


def test_semantic_prune_sees_the_orphaned_entry(tmp_path):
    """Downstream consequence: an orphan is unprunable if the hash never moves."""
    f = tmp_path / "doc.md"
    f.write_text("# A\n\nContent A.\n", encoding="utf-8")
    cache.save_cached(f, {"nodes": [{"id": "a"}], "edges": []},
                      root=tmp_path, kind="semantic")

    f.write_text("# B\n\nContent B.\n", encoding="utf-8")
    live = cache.file_hash(f, tmp_path)
    cache.save_cached(f, {"nodes": [{"id": "b"}], "edges": []},
                      root=tmp_path, kind="semantic")

    assert cache.prune_semantic_cache(tmp_path, {live}) == 1


def test_an_untouched_older_file_still_uses_the_fastpath(tmp_path, monkeypatch):
    """The fastpath must survive: no re-read for a file that has not moved."""
    f = tmp_path / "settled.md"
    f.write_text("# Old\n\nSettled content.\n", encoding="utf-8")
    cache.file_hash(f, tmp_path)

    old = time.time() - 3600
    os.utime(f, (old, old))
    cache.file_hash(f, tmp_path)          # re-prime after the utime change

    hits = _count_reads(monkeypatch, "settled.md")
    cache.file_hash(f, tmp_path)
    assert hits["n"] == 0, "an unchanged, aged file must not be re-read"


def test_a_memo_restored_from_disk_is_trusted(tmp_path, monkeypatch):
    """An index flushed by a completed run keeps a moved corpus warm."""
    f = tmp_path / "f1.py"
    f.write_text("x = 1\n", encoding="utf-8")
    digest = cache.file_hash(f, tmp_path)
    cache._flush_stat_index()

    cache._stat_index = {}
    cache._stat_index_root = None

    hits = _count_reads(monkeypatch, "f1.py")
    assert cache.file_hash(f, tmp_path) == digest
    assert hits["n"] == 0, "a persisted memo must serve a warm hit"


def test_a_growing_file_still_invalidates(tmp_path):
    """Control: the ordinary size-change path is untouched."""
    f = tmp_path / "grow.md"
    f.write_text("# A\n\nShort.\n", encoding="utf-8")
    first = cache.file_hash(f, tmp_path)
    f.write_text("# A\n\nA considerably longer body than before.\n", encoding="utf-8")
    assert cache.file_hash(f, tmp_path) != first
