"""#1656 — word counts are cached against each file's stat signature so
detect() doesn't re-parse every unchanged PDF/docx on each run just to size
the corpus.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify import cache


def test_word_count_cached_until_file_changes(tmp_path, monkeypatch):
    # Isolate the stat index to this tmp root.
    monkeypatch.setattr(cache, "_stat_index", {})
    monkeypatch.setattr(cache, "_stat_index_root", None)

    f = tmp_path / "doc.txt"
    f.write_text("one two three four five")
    st = f.stat()
    monkeypatch.setattr(
        cache.time,
        "time_ns",
        lambda: st.st_mtime_ns + cache._STAT_STABILITY_WINDOW_NS + 1,
    )

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


def test_word_count_rechecks_stat_before_warm_return(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_stat_index", {})
    monkeypatch.setattr(cache, "_stat_index_root", None)
    f = tmp_path / "hit-race.txt"
    f.write_text("one two")
    monkeypatch.setattr(cache.time, "time_ns", lambda: 10**30)
    calls = {"n": 0}

    def compute(path: Path) -> int:
        calls["n"] += 1
        return len(path.read_text().split())

    assert cache.cached_word_count(f, tmp_path, compute) == 2
    new_mtime_ns = f.stat().st_mtime_ns + 1
    real_stat = Path.stat
    stat_calls = 0

    def rewrite_after_hit_stat(path, *args, **kwargs):
        nonlocal stat_calls
        result = real_stat(path, *args, **kwargs)
        if path == f:
            stat_calls += 1
            if stat_calls == 1:
                path.write_text("seventh")
                os.utime(path, ns=(new_mtime_ns, new_mtime_ns))
        return result

    monkeypatch.setattr(Path, "stat", rewrite_after_hit_stat)
    assert cache.cached_word_count(f, tmp_path, compute) == 1
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
    # #1989: digests are now stored per salt under "hashes" (salt = path relative
    # to root == "m.py" here), co-located with the word_count.
    assert entry.get("hashes", {}).get("m.py") == h and entry.get("word_count") == 3


def test_file_hash_is_order_independent_across_roots(tmp_path, monkeypatch):
    """#1989: the stat-index memo must be keyed by the salt (path relative to
    root) that enters the digest, so the same (file, root) returns the same
    digest regardless of what root was hashed first."""
    import hashlib
    from graphify import cache
    monkeypatch.setattr(cache, "_stat_index", {})
    monkeypatch.setattr(cache, "_stat_index_root", None)

    root_a = tmp_path / "a"; root_a.mkdir()
    f = root_a / "doc.txt"; f.write_text("hello world\n")
    root_b = tmp_path / "b"; root_b.mkdir()  # f is NOT under root_b -> abs-path salt

    content = f.read_bytes()
    exp_rel = hashlib.sha256(content + b"\x00" + b"doc.txt").hexdigest()
    exp_abs = hashlib.sha256(
        content + b"\x00" + str(cache._normalize_path(f).resolve()).replace("\\", "/").lower().encode()
    ).hexdigest()

    # rel-first order
    assert cache.file_hash(f, root_a) == exp_rel
    assert cache.file_hash(f, root_b) == exp_abs      # not served the rel digest
    assert cache.file_hash(f, root_a) == exp_rel      # still stable

    # abs-first order, fresh index
    monkeypatch.setattr(cache, "_stat_index", {})
    monkeypatch.setattr(cache, "_stat_index_root", None)
    assert cache.file_hash(f, root_b) == exp_abs
    assert cache.file_hash(f, root_a) == exp_rel      # not served the abs digest


def test_file_hash_ignores_legacy_unsalted_entry(tmp_path, monkeypatch):
    """A pre-#1989 entry carrying a bare "hash" (no salt) is never trusted."""
    import hashlib
    from graphify import cache
    monkeypatch.setattr(cache, "_stat_index", {})
    monkeypatch.setattr(cache, "_stat_index_root", None)
    f = tmp_path / "m.py"; f.write_text("x = 1\n")
    st = f.stat()
    key = str(cache._normalize_path(f).resolve())
    cache._stat_index[key] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "hash": "deadbeef"}
    exp = hashlib.sha256(f.read_bytes() + b"\x00" + b"m.py").hexdigest()
    assert cache.file_hash(f, tmp_path) == exp        # recomputed, not "deadbeef"
    entry = cache._stat_index[key]
    assert "hash" not in entry and entry["hashes"]["m.py"] == exp


def test_flagless_legacy_word_count_revalidates_once(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_stat_index", {})
    monkeypatch.setattr(cache, "_stat_index_root", None)
    f = tmp_path / "legacy.txt"
    f.write_text("two words")
    st = f.stat()
    monkeypatch.setattr(
        cache.time,
        "time_ns",
        lambda: st.st_mtime_ns + cache._STAT_STABILITY_WINDOW_NS + 1,
    )
    key = str(cache._normalize_path(f).resolve())
    cache._stat_index[key] = {
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "word_count": 999,
    }
    calls = {"n": 0}

    def compute(path: Path) -> int:
        calls["n"] += 1
        return len(path.read_text().split())

    assert cache.cached_word_count(f, tmp_path, compute) == 2
    assert calls["n"] == 1
    assert cache._stat_index[key]["word_count_volatile"] is False
    assert cache.cached_word_count(f, tmp_path, compute) == 2
    assert calls["n"] == 1


def test_recent_same_stat_rewrite_refreshes_shared_entry_after_reload(tmp_path, monkeypatch):
    """Hash/count volatility survives persistence and promotes independently."""
    def reset_index_state() -> None:
        monkeypatch.setattr(cache, "_stat_index", {})
        monkeypatch.setattr(cache, "_stat_index_root", None)
        monkeypatch.setattr(cache, "_stat_index_anchor", None)
        monkeypatch.setattr(cache, "_stat_index_dirty", False)

    reset_index_state()
    f = tmp_path / "shared.txt"
    mtime_ns = 1_700_000_000_000_000_000
    now_ns = mtime_ns + cache._STAT_STABILITY_WINDOW_NS // 2
    monkeypatch.setattr(cache.time, "time_ns", lambda: now_ns)

    calls = {"n": 0}

    def compute(path: Path) -> int:
        calls["n"] += 1
        return len(path.read_text().split())

    f.write_text("one two")
    os.utime(f, ns=(mtime_ns, mtime_ns))
    h1 = cache.file_hash(f, tmp_path)
    assert cache.cached_word_count(f, tmp_path, compute) == 2
    key = str(cache._normalize_path(f).resolve())
    assert cache._stat_index[key]["hashes_volatile"] is True
    assert cache._stat_index[key]["word_count_volatile"] is True
    cache._flush_stat_index()

    reset_index_state()
    f.write_text("seventh")  # same byte length, one word instead of two
    os.utime(f, ns=(mtime_ns, mtime_ns))
    h2 = cache.file_hash(f, tmp_path)
    assert h2 != h1
    assert cache.cached_word_count(f, tmp_path, compute) == 1
    assert calls["n"] == 2
    assert cache._stat_index[key]["hashes_volatile"] is True
    assert cache._stat_index[key]["word_count_volatile"] is True

    monkeypatch.setattr(
        cache.time,
        "time_ns",
        lambda: mtime_ns + cache._STAT_STABILITY_WINDOW_NS + 1,
    )
    assert cache.file_hash(f, tmp_path) == h2
    assert cache._stat_index[key]["hashes_volatile"] is False
    assert cache._stat_index[key]["word_count_volatile"] is True
    assert cache.cached_word_count(f, tmp_path, compute) == 1
    assert calls["n"] == 3
    assert cache._stat_index[key]["word_count_volatile"] is False

    def fail_read(_path: Path) -> bytes:
        raise AssertionError("promoted hash unexpectedly read file contents")

    def fail_compute(_path: Path) -> int:
        raise AssertionError("promoted word count unexpectedly recomputed")

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    assert cache.file_hash(f, tmp_path) == h2
    assert cache.cached_word_count(f, tmp_path, fail_compute) == 1
