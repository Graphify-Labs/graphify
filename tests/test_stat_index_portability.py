"""#2199 — stat-index.json must be portable and self-pruning.

The on-disk stat index used to key entries by resolved ABSOLUTE path, so a
corpus reached via a different absolute path (clone, move, second mount) got
0% cache hits (100% re-extraction), and entries for deleted files were never
pruned (unbounded growth). In-memory keys stay absolute; only the on-disk
form is relativized against the key anchor — mirroring the detect manifest's
_to_relative_for_storage/_to_absolute_from_storage round-trip.

Also covers #2197 (cache.py portion): save_semantic_cache must normalize each
item's source_file (backslashes -> forward slashes, relativize when in-root)
before persisting, so a fragment carrying an absolute path (Windows detect()
output) cannot poison the cache.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from graphify import cache


def _reset_stat_index():
    """The stat-index location/anchor are chosen once per process via module
    globals (#1747/#2199). Reset them so each test sees a fresh-process
    decision — same pattern as tests/test_extract_cache_location.py."""
    cache._stat_index_root = None
    cache._stat_index_anchor = None
    cache._stat_index = {}
    cache._stat_index_dirty = False


def _stat_index_path(root: Path) -> Path:
    return root / "graphify-out" / "cache" / "stat-index.json"


def _read_index(root: Path) -> dict:
    return json.loads(_stat_index_path(root).read_text(encoding="utf-8"))


def _count_read_bytes(monkeypatch):
    """Wrap Path.read_bytes with a call counter (file_hash's content read)."""
    calls = {"n": 0}
    orig = Path.read_bytes

    def counting(self):
        calls["n"] += 1
        return orig(self)

    monkeypatch.setattr(Path, "read_bytes", counting)
    return calls


def _fail_compute(p: Path) -> int:
    raise AssertionError(f"word-count compute invoked for {p}; expected a warm stat hit")


def test_cache_hits_survive_corpus_move(tmp_path, monkeypatch):
    """Run A under tmp/a, copy the corpus (with graphify-out/) to tmp/b: run B
    must be 100% warm — zero content reads, zero word-count computes, digests
    identical to run A."""
    _reset_stat_index()
    a = tmp_path / "a"
    a.mkdir()
    (a / "f1.py").write_text("x = 1\n")
    sub = a / "sub"
    sub.mkdir()
    (sub / "f2.md").write_text("hello world one two\n")

    digests_a = {
        "f1.py": cache.file_hash(a / "f1.py", a),
        "sub/f2.md": cache.file_hash(sub / "f2.md", a),
    }
    wc_a = cache.cached_word_count(a / "f1.py", a, lambda p: len(p.read_text().split()))
    cache._flush_stat_index()

    on_disk = _read_index(a)
    assert on_disk, "flush should have written entries"
    for k in on_disk:
        assert not os.path.isabs(k), f"absolute key leaked to disk: {k}"
        assert "\\" not in k, f"non-portable separator in key: {k}"
    assert set(on_disk) == {"f1.py", "sub/f2.md"}

    # Move the corpus (graphify-out/ rides along; copy2 preserves mtime_ns).
    b = tmp_path / "b"
    shutil.copytree(a, b, copy_function=shutil.copy2)

    _reset_stat_index()
    reads = _count_read_bytes(monkeypatch)
    assert cache.file_hash(b / "f1.py", b) == digests_a["f1.py"]
    assert cache.file_hash(b / "sub" / "f2.md", b) == digests_a["sub/f2.md"]
    assert cache.cached_word_count(b / "f1.py", b, _fail_compute) == wc_a
    assert reads["n"] == 0, "moved corpus should be served entirely from the stat index"


def test_deleted_entries_are_pruned_on_flush(tmp_path):
    _reset_stat_index()
    a = tmp_path / "a"
    a.mkdir()
    f1 = a / "f1.py"
    f1.write_text("x = 1\n")
    f2 = a / "f2.py"
    f2.write_text("y = 2\n")
    cache.file_hash(f1, a)
    cache.file_hash(f2, a)
    cache._flush_stat_index()
    assert set(_read_index(a)) == {"f1.py", "f2.py"}

    f2.unlink()
    _reset_stat_index()
    # Bump f1's mtime so the re-hash dirties the index and a flush is written.
    os.utime(f1, ns=(f1.stat().st_atime_ns, f1.stat().st_mtime_ns + 1_000_000))
    cache.file_hash(f1, a)
    cache._flush_stat_index()

    on_disk = _read_index(a)
    assert set(on_disk) == {"f1.py"}, "deleted f2.py should have been pruned"
    assert not os.path.isabs(next(iter(on_disk)))


def test_legacy_absolute_index_migrates_gracefully(tmp_path, monkeypatch):
    """A pre-#2199 index keyed by absolute paths still HITS on the unmoved
    root, and the first flush prunes dead entries and rewrites live keys
    relative (self-heals)."""
    _reset_stat_index()
    a = tmp_path / "a"
    a.mkdir()
    f1 = a / "f1.py"
    f1.write_text("x = 1\n")
    st = f1.stat()
    salt = "f1.py"
    digest = hashlib.sha256(f1.read_bytes() + b"\x00" + salt.encode()).hexdigest()

    dead = tmp_path / "dead"  # never created
    legacy = {
        str(f1.resolve()): {"size": st.st_size, "mtime_ns": st.st_mtime_ns,
                            "hashes": {salt: digest}},
        str(dead / "x.py"): {"size": 1, "mtime_ns": 1, "hashes": {"x.py": "aa"}},
        str(dead / "y.py"): {"size": 2, "mtime_ns": 2, "hashes": {"y.py": "bb"}},
    }
    p = _stat_index_path(a)
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(legacy), encoding="utf-8")

    reads = _count_read_bytes(monkeypatch)
    assert cache.file_hash(f1, a) == digest
    assert reads["n"] == 0, "legacy absolute key should still serve a warm hit"

    # Force a write so the self-heal is observable (a pure warm run leaves the
    # index clean and flush is a no-op by design).
    cache._stat_index_dirty = True
    cache._flush_stat_index()

    on_disk = _read_index(a)
    assert set(on_disk) == {"f1.py"}, "dead absolute keys should be pruned"
    assert on_disk["f1.py"]["hashes"][salt] == digest


def test_out_of_root_key_round_trips_absolute(tmp_path, monkeypatch):
    _reset_stat_index()
    a = tmp_path / "a"
    a.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("out of root\n")

    d1 = cache.file_hash(outside, a)
    cache._flush_stat_index()

    on_disk = _read_index(a)
    assert set(on_disk) == {str(outside.resolve())}, "out-of-root key must stay absolute"

    _reset_stat_index()
    reads = _count_read_bytes(monkeypatch)
    assert cache.file_hash(outside, a) == d1
    assert reads["n"] == 0, "second call should be a stat hit"


def test_relative_key_wins_over_colliding_legacy_absolute(tmp_path):
    """When an old absolute key and a new relative key resolve to the same
    file, the relative (new-format) entry wins on load."""
    _reset_stat_index()
    a = tmp_path / "a"
    a.mkdir()
    f1 = a / "f1.py"
    f1.write_text("x = 1\n")
    p = _stat_index_path(a)
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({
        str(f1.resolve()): {"size": 1, "mtime_ns": 1, "hashes": {"f1.py": "legacy"}},
        "f1.py": {"size": 2, "mtime_ns": 2, "hashes": {"f1.py": "fresh"}},
    }), encoding="utf-8")

    cache._ensure_stat_index(a)
    assert cache._stat_index[str(f1.resolve())]["hashes"]["f1.py"] == "fresh"


def test_semantic_cache_normalizes_absolute_source_file(tmp_path):
    """#2197: an item whose source_file is absolute is persisted root-relative
    posix, and the caller's dict is not mutated."""
    _reset_stat_index()
    root = tmp_path / "corpus"
    root.mkdir()
    f = root / "m.py"
    f.write_text("x = 1\n")

    node = {"id": "m.x", "type": "variable", "source_file": str(f.resolve())}
    saved = cache.save_semantic_cache([node], [], root=root)
    assert saved == 1
    assert node["source_file"] == str(f.resolve()), "caller's dict must not be mutated"

    entries = list((root / "graphify-out" / "cache" / "semantic").glob("*.json"))
    assert len(entries) == 1
    persisted = json.loads(entries[0].read_text(encoding="utf-8"))
    assert persisted["nodes"][0]["source_file"] == "m.py"

    # Replay resolves back to the same absolute shape a fresh extraction has.
    _, _, _, uncached = cache.check_semantic_cache([str(f)], root=root)
    assert uncached == []


def test_semantic_cache_normalizes_backslash_poisoned_source_file(tmp_path):
    """A Windows-shaped absolute source_file (backslash separators) must be
    slash-normalized and relativized instead of being skipped/persisted raw."""
    _reset_stat_index()
    root = tmp_path / "corpus"
    root.mkdir()
    sub = root / "sub"
    sub.mkdir()
    f = sub / "n.py"
    f.write_text("y = 2\n")

    poisoned = str(root.resolve()) + "\\sub\\n.py"
    node = {"id": "n.y", "type": "variable", "source_file": poisoned}
    saved = cache.save_semantic_cache([node], [], root=root)
    assert saved == 1

    entries = list((root / "graphify-out" / "cache" / "semantic").glob("*.json"))
    assert len(entries) == 1
    persisted = json.loads(entries[0].read_text(encoding="utf-8"))
    assert persisted["nodes"][0]["source_file"] == "sub/n.py"
