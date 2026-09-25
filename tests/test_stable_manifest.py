"""Regression tests for Issue #3643: Manifest Byte Stability & Incremental State.

Separates tracked, portable manifest.json from machine-local
cache/incremental-state.json.
"""
import json
import os
import time
from pathlib import Path

import pytest

from graphify import detect as det


def _assert_strict_manifest_schema(manifest_dict: dict) -> None:
    """Verify every manifest row contains strictly {ast_hash, semantic_hash}."""
    assert isinstance(manifest_dict, dict), "manifest must be a dictionary"
    for path_key, entry in manifest_dict.items():
        assert isinstance(path_key, str), f"key {path_key!r} must be a string path"
        assert isinstance(entry, dict), f"entry for {path_key!r} must be a dict"
        assert set(entry.keys()) == {"ast_hash", "semantic_hash"}, (
            f"Entry for {path_key!r} contains invalid keys: {set(entry.keys())}"
        )
        assert isinstance(entry["ast_hash"], str)
        assert isinstance(entry["semantic_hash"], str)


@pytest.fixture()
def sample_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def a(): return 1\n", encoding="utf-8")
    (repo / "b.py").write_text("def b(): return 2\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "guide.md").write_text("# Guide\n\nSome documentation.\n", encoding="utf-8")
    manifest_path = repo / "graphify-out" / "manifest.json"
    state_path = repo / "graphify-out" / "cache" / "incremental-state.json"
    return repo, manifest_path, state_path


def test_strict_manifest_schema(sample_repo):
    """Scenario 8: Manifest schema must strictly contain ONLY ast_hash and semantic_hash."""
    repo, manifest_path, _ = sample_repo
    files = det.detect(repo)["files"]
    det.save_manifest(files, str(manifest_path), root=repo)

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    _assert_strict_manifest_schema(data)
    assert "a.py" in data
    assert "b.py" in data
    assert "docs/guide.md" in data


def test_manifest_byte_stability_across_utime(sample_repo):
    """Scenario 1: Changing file mtimes with os.utime leaves manifest.json bytes identical."""
    repo, manifest_path, _ = sample_repo
    files = det.detect(repo)["files"]
    det.save_manifest(files, str(manifest_path), root=repo)
    bytes_before = manifest_path.read_bytes()

    # Move mtime back by 1 hour on all files
    old_time = time.time() - 3600
    for f in repo.rglob("*.py"):
        os.utime(f, (old_time, old_time))

    det.save_manifest(files, str(manifest_path), root=repo)
    bytes_after = manifest_path.read_bytes()

    assert bytes_before == bytes_after, "manifest.json bytes must remain identical when mtime moves"


def test_deterministic_ordering(sample_repo):
    """Scenario 2: Manifest key serialization order is deterministic regardless of input order."""
    repo, manifest_path, _ = sample_repo
    f_a = str(repo / "a.py")
    f_b = str(repo / "b.py")
    f_doc = str(repo / "docs" / "guide.md")

    # Order 1: a, b, doc
    files_1 = {"code": [f_a, f_b], "document": [f_doc]}
    det.save_manifest(files_1, str(manifest_path), root=repo)
    bytes_1 = manifest_path.read_bytes()

    # Order 2: reverse order
    files_2 = {"document": [f_doc], "code": [f_b, f_a]}
    det.save_manifest(files_2, str(manifest_path), root=repo)
    bytes_2 = manifest_path.read_bytes()

    assert bytes_1 == bytes_2, "manifest serialization must be strictly deterministic"


def test_fresh_checkout_cache_miss(sample_repo):
    """Scenario 3: Fresh checkout / cache miss preserves manifest.json and recreates local state."""
    repo, manifest_path, state_path = sample_repo
    files = det.detect(repo)["files"]
    det.save_manifest(files, str(manifest_path), root=repo)
    manifest_bytes_orig = manifest_path.read_bytes()

    assert state_path.is_file(), "incremental-state.json must exist after save_manifest"

    # Simulate fresh checkout on another machine: remove untracked cache
    state_path.unlink()
    assert not state_path.exists()

    # Run incremental detection
    inc = det.detect_incremental(repo, str(manifest_path))

    # All files should be recognized as unchanged (0 new files)
    queued = [f for flist in inc["new_files"].values() for f in flist]
    assert queued == [], f"expected no queued files, got {queued}"

    # Incremental state must be recreated
    assert state_path.is_file(), "cache/incremental-state.json must be recreated on cache miss"
    state_data = json.loads(state_path.read_text(encoding="utf-8"))
    assert "a.py" in state_data
    assert "size" in state_data["a.py"]
    assert "mtime_ns" in state_data["a.py"]
    assert "indexed_at_ns" in state_data["a.py"]

    # Manifest must remain completely untouched
    assert manifest_path.read_bytes() == manifest_bytes_orig


def test_real_modification(sample_repo):
    """Scenario 4: Genuinely modifying a file updates only its content hash and manifest entry."""
    repo, manifest_path, _ = sample_repo
    files = det.detect(repo)["files"]
    det.save_manifest(files, str(manifest_path), root=repo)

    manifest_before = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Modify b.py
    time.sleep(0.02)
    (repo / "b.py").write_text("def b(): return 'changed'\n", encoding="utf-8")

    inc = det.detect_incremental(repo, str(manifest_path))
    queued = [f for flist in inc["new_files"].values() for f in flist]
    assert len(queued) == 1
    assert queued[0].endswith("b.py")

    det.save_manifest(det.detect(repo)["files"], str(manifest_path), root=repo)
    manifest_after = json.loads(manifest_path.read_text(encoding="utf-8"))

    _assert_strict_manifest_schema(manifest_after)
    assert manifest_after["a.py"] == manifest_before["a.py"]
    assert manifest_after["docs/guide.md"] == manifest_before["docs/guide.md"]
    assert manifest_after["b.py"]["ast_hash"] != manifest_before["b.py"]["ast_hash"]


def test_mtime_only_change(sample_repo):
    """Scenario 5: Changing mtime without changing content causes no false modification or manifest churn."""
    repo, manifest_path, _ = sample_repo
    files = det.detect(repo)["files"]
    det.save_manifest(files, str(manifest_path), root=repo)
    manifest_bytes_orig = manifest_path.read_bytes()

    # Touch mtime of a.py to some future or past timestamp
    a_py = repo / "a.py"
    stat_before = a_py.stat()
    new_mtime = stat_before.st_mtime - 100
    os.utime(a_py, (new_mtime, new_mtime))

    inc = det.detect_incremental(repo, str(manifest_path))
    queued = [f for flist in inc["new_files"].values() for f in flist]
    assert queued == [], f"mtime-only change must not queue file: {queued}"

    det.save_manifest(det.detect(repo)["files"], str(manifest_path), root=repo)
    assert manifest_path.read_bytes() == manifest_bytes_orig, "manifest.json must not churn on mtime-only change"


def test_same_size_rapid_rewrite(sample_repo):
    """Scenario 6: Same-size rapid rewrite within racily-clean window is detected reliably."""
    repo, manifest_path, _ = sample_repo
    files = det.detect(repo)["files"]
    det.save_manifest(files, str(manifest_path), root=repo)

    target = repo / "a.py"
    stat_before = target.stat()

    # Rewrite with exact same length
    content_orig = target.read_text(encoding="utf-8")
    content_new = "def a(): return 9\n"
    assert len(content_orig) == len(content_new)
    assert content_orig != content_new

    target.write_text(content_new, encoding="utf-8")
    # Pin mtime to original stat so stat signature appears identical
    os.utime(target, ns=(stat_before.st_atime_ns, stat_before.st_mtime_ns))

    assert target.stat().st_size == stat_before.st_size
    assert target.stat().st_mtime_ns == stat_before.st_mtime_ns

    inc = det.detect_incremental(repo, str(manifest_path))
    queued = [f for flist in inc["new_files"].values() for f in flist]
    assert len(queued) == 1, f"same-size rapid rewrite must be detected; queued={queued}"
    assert queued[0].endswith("a.py")


def test_deletion(sample_repo):
    """Scenario 7: Deletion of an indexed file is accurately reported."""
    repo, manifest_path, _ = sample_repo
    files = det.detect(repo)["files"]
    det.save_manifest(files, str(manifest_path), root=repo)

    (repo / "b.py").unlink()

    inc = det.detect_incremental(repo, str(manifest_path))
    assert any(f.endswith("b.py") for f in inc["deleted_files"])
    assert inc["excluded_files"] == []


def test_exclusion(sample_repo):
    """Scenario 8: Newly excluded file is reported as excluded, not deleted."""
    repo, manifest_path, _ = sample_repo
    files = det.detect(repo)["files"]
    det.save_manifest(files, str(manifest_path), root=repo)

    # Pass extra_excludes to exclude b.py while it still exists on disk
    inc = det.detect_incremental(repo, str(manifest_path), extra_excludes=["**/b.py"])
    assert any(f.endswith("b.py") for f in inc["excluded_files"])
    assert not any(f.endswith("b.py") for f in inc["deleted_files"])


def test_legacy_manifest_migration(sample_repo):
    """Scenario 9: Legacy manifest with mtime/seen upgrades cleanly to new schema."""
    repo, manifest_path, state_path = sample_repo
    # Write a legacy manifest with mtime, seen, and single hash
    legacy_data = {
        "a.py": {
            "mtime": 1600000000.0,
            "seen": 1600000001.0,
            "hash": det._md5_file(repo / "a.py"),
        },
        "b.py": {
            "mtime": 1600000000.0,
            "seen": 1600000001.0,
            "ast_hash": det._md5_file(repo / "b.py"),
            "semantic_hash": det._md5_file(repo / "b.py"),
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(legacy_data, indent=2), encoding="utf-8")

    # Run save_manifest to migrate
    files = det.detect(repo)["files"]
    det.save_manifest(files, str(manifest_path), root=repo)

    migrated = json.loads(manifest_path.read_text(encoding="utf-8"))
    _assert_strict_manifest_schema(migrated)

    for row in migrated.values():
        assert "mtime" not in row
        assert "seen" not in row

    # Incremental state must be created with valid fields
    assert state_path.is_file()
    state_data = json.loads(state_path.read_text(encoding="utf-8"))
    for row in state_data.values():
        assert isinstance(row["size"], int)
        assert isinstance(row["mtime_ns"], int)
        assert isinstance(row["indexed_at_ns"], int)


def test_malformed_incremental_state_fallback(sample_repo):
    """Scenario 10: Corrupted incremental-state.json falls back safely to hashing."""
    repo, manifest_path, state_path = sample_repo
    files = det.detect(repo)["files"]
    det.save_manifest(files, str(manifest_path), root=repo)

    # Corrupt the incremental state
    state_path.write_text("{ this is corrupted invalid json }}}", encoding="utf-8")

    # detect_incremental should not crash, but safely fall back to hashing
    inc = det.detect_incremental(repo, str(manifest_path))
    queued = [f for flist in inc["new_files"].values() for f in flist]
    assert queued == [], f"expected unchanged files to remain unqueued despite corrupted state, got {queued}"


def test_save_manifest_no_op_preserves_both_files(sample_repo):
    """Scenario 11: Double save_manifest without changes skips disk writes for both files."""
    repo, manifest_path, state_path = sample_repo
    files = det.detect(repo)["files"]

    # First save
    det.save_manifest(files, str(manifest_path), root=repo)
    manifest_bytes_1 = manifest_path.read_bytes()
    manifest_mtime_1 = manifest_path.stat().st_mtime_ns

    state_bytes_1 = state_path.read_bytes()
    state_mtime_1 = state_path.stat().st_mtime_ns

    # Small sleep to ensure mtime moves if rewritten
    time.sleep(0.02)

    # Second save (no-op)
    det.save_manifest(files, str(manifest_path), root=repo)
    manifest_bytes_2 = manifest_path.read_bytes()
    manifest_mtime_2 = manifest_path.stat().st_mtime_ns

    state_bytes_2 = state_path.read_bytes()
    state_mtime_2 = state_path.stat().st_mtime_ns

    assert manifest_bytes_1 == manifest_bytes_2, "manifest.json bytes must be identical"
    assert manifest_mtime_1 == manifest_mtime_2, "manifest.json disk write must be skipped"

    assert state_bytes_1 == state_bytes_2, "incremental-state.json bytes must be identical"
    assert state_mtime_1 == state_mtime_2, "incremental-state.json disk write must be skipped"
