"""Tests for Graph State Inspection Layer (Issue #2841 - Phase 3)."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
import pytest

from graphify.detect import (
    GraphState,
    StalenessReason,
    GraphStateResult,
    LockResult,
    BuildLockStatus,
    acquire_build_lock,
    release_build_lock,
    inspect_graph_state,
    _mutex_lock,
)


def _init_git_repo(path: Path) -> str:
    """Initialize a git repo at path, commit an initial file, and return HEAD SHA."""
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=str(path), check=True, capture_output=True)

    (path / "main.py").write_text("print('hello')\n", encoding="utf-8")
    subprocess.run(["git", "add", "main.py"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=str(path), check=True, capture_output=True)

    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(path), check=True, capture_output=True, text=True)
    return r.stdout.strip()


def _write_graph(path: Path, built_at_commit: str | None = None) -> Path:
    out = path / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    graph_file = out / "graph.json"
    data = {"nodes": [], "links": []}
    if built_at_commit is not None:
        data["built_at_commit"] = built_at_commit
    graph_file.write_text(json.dumps(data), encoding="utf-8")
    return graph_file


# ── 1. Basic State Tests ──────────────────────────────────────────────────

def test_state_absent_when_no_graph_json(tmp_path):
    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.ABSENT
    assert res.graph_path == tmp_path / "graphify-out" / "graph.json"
    assert res.to_dict()["state"] == "ABSENT"


def test_state_fresh_when_clean_and_head_matches(tmp_path):
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.FRESH
    assert res.built_at_commit == head
    assert res.current_head == head
    assert res.staleness_reasons == ()
    assert res.dirty_files == ()


def test_state_stale_on_head_mismatch(tmp_path):
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit="0" * 40)

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.STALE
    assert res.staleness_reasons == (StalenessReason.HEAD_MISMATCH,)
    assert res.built_at_commit == "0" * 40
    assert res.current_head == head


def test_state_unverifiable_on_missing_built_at_commit(tmp_path):
    _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=None)

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.UNVERIFIABLE
    assert res.unverifiable_reason == "missing_built_at_commit"
    assert res.built_at_commit is None


def test_state_unverifiable_on_non_git_corpus(tmp_path):
    # Directory without git repo
    _write_graph(tmp_path, built_at_commit="a" * 40)

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.UNVERIFIABLE
    assert res.unverifiable_reason == "not_a_git_repo"
    assert res.current_head is None


# ── 2. Dirty Working Tree Tests ──────────────────────────────────────────

def test_state_stale_on_staged_modification(tmp_path):
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    (tmp_path / "main.py").write_text("print('staged edit')\n", encoding="utf-8")
    subprocess.run(["git", "add", "main.py"], cwd=str(tmp_path), check=True, capture_output=True)

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.STALE
    assert res.staleness_reasons == (StalenessReason.DIRTY_WORKTREE,)
    assert "main.py" in res.dirty_files


def test_state_stale_on_unstaged_modification(tmp_path):
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    (tmp_path / "main.py").write_text("print('unstaged edit')\n", encoding="utf-8")

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.STALE
    assert res.staleness_reasons == (StalenessReason.DIRTY_WORKTREE,)
    assert "main.py" in res.dirty_files


def test_state_stale_on_tracked_deletion(tmp_path):
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    (tmp_path / "main.py").unlink()

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.STALE
    assert res.staleness_reasons == (StalenessReason.DIRTY_WORKTREE,)
    assert "main.py" in res.dirty_files


def test_state_stale_on_tracked_rename(tmp_path):
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    subprocess.run(["git", "mv", "main.py", "renamed.py"], cwd=str(tmp_path), check=True, capture_output=True)

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.STALE
    assert res.staleness_reasons == (StalenessReason.DIRTY_WORKTREE,)
    assert any("renamed.py" in f or "main.py" in f for f in res.dirty_files)


def test_state_stale_on_supported_untracked_file(tmp_path):
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    (tmp_path / "new_module.py").write_text("def foo(): pass\n", encoding="utf-8")

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.STALE
    assert res.staleness_reasons == (StalenessReason.DIRTY_WORKTREE,)
    assert "new_module.py" in res.dirty_files


def test_state_fresh_ignores_unsupported_untracked_file(tmp_path):
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    (tmp_path / "scratch.log").write_text("log data\n", encoding="utf-8")
    (tmp_path / "temp.tmp").write_text("temp data\n", encoding="utf-8")
    (tmp_path / ".DS_Store").write_text("junk\n", encoding="utf-8")

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.FRESH
    assert res.staleness_reasons == ()
    assert res.dirty_files == ()


def test_state_fresh_ignores_graphifyignored_untracked_file(tmp_path):
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    (tmp_path / ".graphifyignore").write_text("vendor/\n", encoding="utf-8")
    vendor_dir = tmp_path / "vendor"
    vendor_dir.mkdir()
    (vendor_dir / "lib.py").write_text("code\n", encoding="utf-8")

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.FRESH
    assert res.staleness_reasons == ()


def test_state_stale_on_head_mismatch_and_dirty_tree(tmp_path):
    _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit="0" * 40)

    (tmp_path / "main.py").write_text("edit\n", encoding="utf-8")

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.STALE
    assert StalenessReason.HEAD_MISMATCH in res.staleness_reasons
    assert StalenessReason.DIRTY_WORKTREE in res.staleness_reasons
    assert "main.py" in res.dirty_files


# ── 3. Path Boundaries Tests ─────────────────────────────────────────────

def test_path_boundary_filtering_subdirectory_target(tmp_path):
    head = _init_git_repo(tmp_path)

    # Structure:
    # services/auth/
    # services/auth2/
    # services/billing/
    auth_dir = tmp_path / "services" / "auth"
    auth2_dir = tmp_path / "services" / "auth2"
    billing_dir = tmp_path / "services" / "billing"

    auth_dir.mkdir(parents=True)
    auth2_dir.mkdir(parents=True)
    billing_dir.mkdir(parents=True)

    (auth_dir / "auth.py").write_text("# auth\n", encoding="utf-8")
    (auth2_dir / "auth2.py").write_text("# auth2\n", encoding="utf-8")
    (billing_dir / "billing.py").write_text("# billing\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add services"], cwd=str(tmp_path), check=True, capture_output=True)
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(tmp_path), check=True, capture_output=True, text=True)
    new_head = r.stdout.strip()

    _write_graph(auth_dir, built_at_commit=new_head)

    # Modify auth2 and billing (outside auth_dir)
    (auth2_dir / "auth2.py").write_text("# auth2 modified\n", encoding="utf-8")
    (billing_dir / "billing.py").write_text("# billing modified\n", encoding="utf-8")

    res = inspect_graph_state(auth_dir)
    assert res.state == GraphState.FRESH
    assert res.staleness_reasons == ()
    assert res.dirty_files == ()


def test_path_boundary_filtering_nested_target(tmp_path):
    head = _init_git_repo(tmp_path)

    auth_dir = tmp_path / "services" / "auth"
    sub_dir = auth_dir / "sub"
    sub_dir.mkdir(parents=True)

    (sub_dir / "bar.ts").write_text("export const x = 1;\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add sub"], cwd=str(tmp_path), check=True, capture_output=True)
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(tmp_path), check=True, capture_output=True, text=True)
    new_head = r.stdout.strip()

    _write_graph(auth_dir, built_at_commit=new_head)

    # Modify nested file
    (sub_dir / "bar.ts").write_text("export const x = 2;\n", encoding="utf-8")

    res = inspect_graph_state(auth_dir)
    assert res.state == GraphState.STALE
    assert res.staleness_reasons == (StalenessReason.DIRTY_WORKTREE,)
    assert any("sub/bar.ts" in f or "bar.ts" in f for f in res.dirty_files)


# ── 4. Intermediate State Tests ──────────────────────────────────────────

def test_state_incomplete_on_intermediate_artifact(tmp_path):
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    # Add leftover .graphify_extract.json
    out = tmp_path / "graphify-out"
    (out / ".graphify_extract.json").write_text("{}", encoding="utf-8")

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.INCOMPLETE
    assert ".graphify_extract.json" in res.intermediate_artifacts
    assert res.active_build is False


def test_state_incomplete_multiple_artifacts_reported(tmp_path):
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    out = tmp_path / "graphify-out"
    (out / ".graphify_ast.json").write_text("{}", encoding="utf-8")
    (out / ".graphify_chunk_00.json").write_text("{}", encoding="utf-8")
    (out / ".graphify_detect.json").write_text("{}", encoding="utf-8")

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.INCOMPLETE
    assert ".graphify_ast.json" in res.intermediate_artifacts
    assert ".graphify_chunk_00.json" in res.intermediate_artifacts
    assert ".graphify_detect.json" in res.intermediate_artifacts


def test_state_persistent_sidecars_do_not_trigger_incomplete(tmp_path):
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    out = tmp_path / "graphify-out"
    (out / ".graphify_labels.json").write_text("{}", encoding="utf-8")
    (out / ".graphify_labels.json.sig").write_text("{}", encoding="utf-8")
    (out / ".graphify_python").write_text("/usr/bin/python\n", encoding="utf-8")
    (out / ".graphify_root").write_text(".\n", encoding="utf-8")
    (out / "manifest.json").write_text("{}", encoding="utf-8")
    (out / "cost.json").write_text("{}", encoding="utf-8")
    (out / "graph.html").write_text("<html></html>", encoding="utf-8")

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.FRESH
    assert res.intermediate_artifacts == ()


def test_state_building_when_active_lock_pid_alive(tmp_path):
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    out = tmp_path / "graphify-out"
    # Write current process PID (definitely alive)
    (out / ".rebuild.lock").write_text(f"{os.getpid()}\n", encoding="utf-8")
    (out / ".graphify_extract.json").write_text("{}", encoding="utf-8")

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.BUILDING
    assert res.active_build is True
    assert res.active_pid == os.getpid()


def test_state_incomplete_when_lock_pid_dead(tmp_path, monkeypatch):
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    out = tmp_path / "graphify-out"
    # Write arbitrary PID and mock _is_pid_alive to False
    (out / ".rebuild.lock").write_text("99999999\n", encoding="utf-8")
    (out / ".graphify_ast.json").write_text("{}", encoding="utf-8")

    from graphify import detect
    monkeypatch.setattr(detect, "_is_pid_alive", lambda pid: False)

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.INCOMPLETE
    assert res.active_build is False
    assert ".graphify_ast.json" in res.intermediate_artifacts


def test_precedence_incomplete_over_stale_commit(tmp_path):
    _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit="0" * 40)

    out = tmp_path / "graphify-out"
    (out / ".graphify_extract.json").write_text("{}", encoding="utf-8")

    res = inspect_graph_state(tmp_path)
    # Must be INCOMPLETE, not STALE
    assert res.state == GraphState.INCOMPLETE
    assert ".graphify_extract.json" in res.intermediate_artifacts


# ── 5. Serialization & Dict Details ──────────────────────────────────────

def test_result_to_dict_structure(tmp_path):
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)
    (tmp_path / "main.py").write_text("edit\n", encoding="utf-8")

    res = inspect_graph_state(tmp_path)
    d = res.to_dict()
    assert d["state"] == "STALE"
    assert d["built_at_commit"] == head
    assert d["current_head"] == head
    assert "DIRTY_WORKTREE" in d["staleness_reasons"]
    assert "main.py" in d["dirty_files"]
    assert d["intermediate_artifacts"] == []
    assert d["active_build"] is False
    assert d["graph_path"] == str(tmp_path / "graphify-out" / "graph.json")


# ── 6. Legacy / Missing .graphify_python Tests ────────────────────────────

def test_legacy_graph_missing_graphify_python_returns_fresh(tmp_path):
    """A legacy graph with clean tree and matching HEAD works without .graphify_python."""
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)
    # Ensure .graphify_python does NOT exist
    assert not (tmp_path / "graphify-out" / ".graphify_python").exists()

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.FRESH
    assert res.built_at_commit == head
    assert res.current_head == head


def test_legacy_graph_missing_graphify_python_returns_stale_on_diverged_head(tmp_path):
    """A legacy graph with diverged HEAD detects STALE without .graphify_python."""
    _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit="old" + "0" * 37)
    assert not (tmp_path / "graphify-out" / ".graphify_python").exists()

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.STALE
    assert res.staleness_reasons == (StalenessReason.HEAD_MISMATCH,)


def test_legacy_graph_missing_graphify_python_returns_incomplete_on_artifacts(tmp_path):
    """A legacy graph with leftover artifacts detects INCOMPLETE without .graphify_python."""
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)
    (tmp_path / "graphify-out" / ".graphify_ast.json").write_text("{}", encoding="utf-8")
    assert not (tmp_path / "graphify-out" / ".graphify_python").exists()

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.INCOMPLETE
    assert ".graphify_ast.json" in res.intermediate_artifacts


def test_legacy_graph_missing_graphify_python_returns_unverifiable_on_non_git(tmp_path):
    """A legacy graph in non-git repo detects UNVERIFIABLE without .graphify_python."""
    _write_graph(tmp_path, built_at_commit="abc" * 13 + "a")
    assert not (tmp_path / "graphify-out" / ".graphify_python").exists()

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.UNVERIFIABLE
    assert res.unverifiable_reason == "not_a_git_repo"


# ── 7. Phase 4B: Build Lock Lifecycle Tests ──────────────────────────────

def test_acquire_lock_fresh(tmp_path):
    """Acquiring lock on fresh directory returns ACQUIRED and creates .rebuild.lock."""
    res = acquire_build_lock(tmp_path)
    assert res.result == LockResult.ACQUIRED
    assert res.token is not None
    assert res.active_pid == os.getpid()

    lock_file = tmp_path / "graphify-out" / ".rebuild.lock"
    assert lock_file.exists()
    lines = lock_file.read_text(encoding="utf-8").splitlines()
    assert lines[0] == str(os.getpid())
    assert f"token={res.token}" in lines
    assert (tmp_path / "graphify-out" / ".graphify_build_token").read_text(encoding="utf-8") == res.token


def test_acquire_lock_active_contender(tmp_path):
    """Acquiring lock when another live process owns it returns ALREADY_ACTIVE."""
    first = acquire_build_lock(tmp_path)
    assert first.result == LockResult.ACQUIRED

    # Second contender attempts to acquire
    second = acquire_build_lock(tmp_path, pid=999999)
    assert second.result == LockResult.ALREADY_ACTIVE
    assert second.active_pid == os.getpid()
    assert second.token is None


def test_acquire_lock_dead_pid_reclaimed(tmp_path, monkeypatch):
    """Acquiring lock when owner PID is dead returns RECLAIMED_STALE."""
    out = tmp_path / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    # Write dead PID lock
    (out / ".rebuild.lock").write_text("99999999\ntoken=dead-token\n", encoding="utf-8")

    from graphify import detect
    monkeypatch.setattr(detect, "_is_pid_alive", lambda pid: False)

    res = acquire_build_lock(tmp_path)
    assert res.result == LockResult.RECLAIMED_STALE
    assert res.token != "dead-token"
    assert res.active_pid == os.getpid()


def test_acquire_lock_pid_reuse_detected(tmp_path, monkeypatch):
    """Acquiring lock when PID is alive but create_time does not match returns RECLAIMED_STALE."""
    out = tmp_path / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / ".rebuild.lock").write_text(f"{os.getpid()}\ntoken=old-token\ncreate_time=1000.0\n", encoding="utf-8")

    from graphify import detect
    monkeypatch.setattr(detect, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(detect, "_get_process_create_time", lambda pid: 2000.0)

    res = acquire_build_lock(tmp_path)
    assert res.result == LockResult.RECLAIMED_STALE
    assert res.token != "old-token"


def test_concurrent_lock_contention(tmp_path, monkeypatch):
    """Concurrent threads contending for a fresh lock result in exactly 1 ACQUIRED."""
    from graphify import detect
    monkeypatch.setattr(detect, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(detect, "_get_process_create_time", lambda pid: 1000.0)

    from concurrent.futures import ThreadPoolExecutor
    outcomes = []

    def try_acquire(pid):
        return acquire_build_lock(tmp_path, pid=pid)

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(try_acquire, 10000 + i) for i in range(8)]
        for f in futures:
            outcomes.append(f.result().result)

    assert outcomes.count(LockResult.ACQUIRED) == 1
    assert outcomes.count(LockResult.ALREADY_ACTIVE) == 7


def test_concurrent_stale_takeover_race(tmp_path, monkeypatch):
    """Concurrent threads contending for a dead lock result in exactly 1 RECLAIMED_STALE."""
    out = tmp_path / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / ".rebuild.lock").write_text("999999\ntoken=stale-1\n", encoding="utf-8")

    from graphify import detect
    # First time checking 999999 -> dead; once new PID is written -> alive
    def mock_alive(pid):
        return pid != 999999

    monkeypatch.setattr(detect, "_is_pid_alive", mock_alive)
    monkeypatch.setattr(detect, "_get_process_create_time", lambda pid: 1000.0)

    from concurrent.futures import ThreadPoolExecutor
    outcomes = []

    def try_acquire(pid):
        return acquire_build_lock(tmp_path, pid=pid)

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(try_acquire, 20000 + i) for i in range(8)]
        for f in futures:
            outcomes.append(f.result().result)

    assert outcomes.count(LockResult.RECLAIMED_STALE) == 1
    assert outcomes.count(LockResult.ALREADY_ACTIVE) == 7


def test_release_matching_token(tmp_path):
    """Release with matching token unlinks .rebuild.lock and removes build token."""
    res = acquire_build_lock(tmp_path)
    assert res.result == LockResult.ACQUIRED
    lock_file = tmp_path / "graphify-out" / ".rebuild.lock"
    token_file = tmp_path / "graphify-out" / ".graphify_build_token"
    assert lock_file.exists()
    assert token_file.exists()

    released = release_build_lock(tmp_path, token=res.token)
    assert released is True
    assert not lock_file.exists()
    assert not token_file.exists()


def test_release_wrong_token_rejected(tmp_path):
    """Release with wrong token does not unlink .rebuild.lock."""
    res = acquire_build_lock(tmp_path)
    assert res.result == LockResult.ACQUIRED
    lock_file = tmp_path / "graphify-out" / ".rebuild.lock"

    released = release_build_lock(tmp_path, token="wrong-token")
    assert released is False
    assert lock_file.exists()


def test_release_superseded_token_does_not_delete_new_owner(tmp_path):
    """A stale owner releasing an old token does not delete a newer owner's lock."""
    first = acquire_build_lock(tmp_path)
    old_token = first.token

    # Simulate takeover by writing new owner lock
    out = tmp_path / "graphify-out"
    (out / ".rebuild.lock").write_text(f"{os.getpid()}\ntoken=new-token-123\n", encoding="utf-8")

    # Old owner attempts to release with old token
    released = release_build_lock(tmp_path, token=old_token)
    assert released is False
    # Newer owner's lock must remain untouched
    assert (out / ".rebuild.lock").exists()
    assert "token=new-token-123" in (out / ".rebuild.lock").read_text(encoding="utf-8")


def test_legacy_pid_only_live_lock(tmp_path):
    """Legacy lock with single PID line of current process reports ALREADY_ACTIVE."""
    out = tmp_path / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / ".rebuild.lock").write_text(f"{os.getpid()}\n", encoding="utf-8")

    res = acquire_build_lock(tmp_path)
    assert res.result == LockResult.ALREADY_ACTIVE
    assert res.active_pid == os.getpid()


def test_legacy_pid_only_dead_lock_reclaimed(tmp_path, monkeypatch):
    """Legacy lock with single dead PID line is safely reclaimed."""
    out = tmp_path / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / ".rebuild.lock").write_text("99999999\n", encoding="utf-8")

    from graphify import detect
    monkeypatch.setattr(detect, "_is_pid_alive", lambda pid: False)

    res = acquire_build_lock(tmp_path)
    assert res.result == LockResult.RECLAIMED_STALE


def test_acquire_lock_reclaims_empty_file(tmp_path):
    """An empty lock file is safely reclaimed."""
    out = tmp_path / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / ".rebuild.lock").write_text("", encoding="utf-8")

    res = acquire_build_lock(tmp_path)
    assert res.result == LockResult.RECLAIMED_STALE


def test_acquire_lock_reclaims_invalid_pid(tmp_path):
    """A lock file with invalid non-numeric PID is safely reclaimed."""
    out = tmp_path / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / ".rebuild.lock").write_text("not-a-number\n", encoding="utf-8")

    res = acquire_build_lock(tmp_path)
    assert res.result == LockResult.RECLAIMED_STALE


def test_acquire_lock_reclaims_truncated_metadata(tmp_path, monkeypatch):
    """A lock file with invalid create_time or truncated lines is safely handled."""
    out = tmp_path / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / ".rebuild.lock").write_text("99999999\ntoken=\ncreate_time=bad\n", encoding="utf-8")

    from graphify import detect
    monkeypatch.setattr(detect, "_is_pid_alive", lambda pid: False)

    res = acquire_build_lock(tmp_path)
    assert res.result == LockResult.RECLAIMED_STALE


def test_mutex_unwedges_after_exception(tmp_path):
    """An exception inside _mutex_lock releases the lock immediately."""
    out = tmp_path / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)

    with pytest.raises(RuntimeError):
        with _mutex_lock(out):
            raise RuntimeError("crash inside critical section")

    # Next attempt must succeed immediately
    res = acquire_build_lock(tmp_path)
    assert res.result == LockResult.ACQUIRED


def test_reinspect_protocol_aborts_if_fresh(tmp_path):
    """Acquiring lock followed by re-inspection seeing FRESH avoids rebuilding."""
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    # Initial state is FRESH
    initial_res = inspect_graph_state(tmp_path)
    assert initial_res.state == GraphState.FRESH

    # Acquire lock
    status = acquire_build_lock(tmp_path)
    assert status.result == LockResult.ACQUIRED

    # External inspector (no token) sees BUILDING
    external_res = inspect_graph_state(tmp_path)
    assert external_res.state == GraphState.BUILDING

    # Re-inspecting with caller's token sees underlying FRESH state
    re_res = inspect_graph_state(tmp_path, current_token=status.token)
    assert re_res.state == GraphState.FRESH

    # Release lock
    release_build_lock(tmp_path, token=status.token)


# ── 8. Phase 4B Verification Gate Tests ──────────────────────────────────

def test_current_token_owner_inspecting_itself_is_not_building(tmp_path):
    """Case A: Owner inspecting with current_token evaluates underlying graph state."""
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    status = acquire_build_lock(tmp_path)
    assert status.result == LockResult.ACQUIRED

    res = inspect_graph_state(tmp_path, current_token=status.token)
    assert res.state == GraphState.FRESH
    assert res.active_build is False


def test_current_token_other_process_sees_building(tmp_path):
    """Case B: External process without token sees BUILDING."""
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    status = acquire_build_lock(tmp_path)
    assert status.result == LockResult.ACQUIRED

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.BUILDING
    assert res.active_build is True
    assert res.active_pid == os.getpid()


def test_current_token_superseded_owner_sees_building(tmp_path):
    """Case C: Superseded owner with old token sees BUILDING owned by new owner."""
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    out = tmp_path / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / ".rebuild.lock").write_text(f"{os.getpid()}\ntoken=token-B\n", encoding="utf-8")

    # Caller passes old token-A
    res = inspect_graph_state(tmp_path, current_token="token-A")
    assert res.state == GraphState.BUILDING
    assert res.active_build is True
    assert res.active_pid == os.getpid()


def test_persistent_sidecars_lock_and_mutex_do_not_trigger_incomplete(tmp_path):
    """The presence of .rebuild.lock.mutex and .graphify_build_token does not trigger INCOMPLETE."""
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    out = tmp_path / "graphify-out"
    (out / ".rebuild.lock.mutex").write_text("", encoding="utf-8")
    (out / ".graphify_build_token").write_text("tok-123", encoding="utf-8")

    res = inspect_graph_state(tmp_path)
    assert res.state == GraphState.FRESH
    assert res.intermediate_artifacts == ()


def test_watch_rebuild_lock_lifecycle_normal(tmp_path):
    """_rebuild_lock context manager creates lock and removes it upon clean exit."""
    from graphify.watch import _rebuild_lock
    out = tmp_path / "graphify-out"
    lock_file = out / ".rebuild.lock"

    with _rebuild_lock(out) as acquired:
        assert acquired is True
        assert lock_file.exists()
        lines = lock_file.read_text(encoding="utf-8").splitlines()
        assert lines[0] == str(os.getpid())

    assert not lock_file.exists()


def test_watch_rebuild_lock_lifecycle_exception(tmp_path):
    """_rebuild_lock context manager removes lock even when an exception is raised."""
    from graphify.watch import _rebuild_lock
    out = tmp_path / "graphify-out"
    lock_file = out / ".rebuild.lock"

    with pytest.raises(ValueError):
        with _rebuild_lock(out) as acquired:
            assert acquired is True
            assert lock_file.exists()
            raise ValueError("boom")

    assert not lock_file.exists()


def test_watch_rebuild_lock_non_blocking_does_not_clobber_holder(tmp_path):
    """A non-blocking second caller to _rebuild_lock does not clobber the primary holder."""
    from graphify.watch import _rebuild_lock
    out = tmp_path / "graphify-out"
    lock_file = out / ".rebuild.lock"

    with _rebuild_lock(out) as outer:
        assert outer is True
        held_content = lock_file.read_text(encoding="utf-8")

        with _rebuild_lock(out, blocking=False) as inner:
            assert inner is False
            # Holder lock file unchanged
            assert lock_file.read_text(encoding="utf-8") == held_content

        # Outer holder still intact
        assert lock_file.exists()

    assert not lock_file.exists()


def test_is_pid_alive_permission_error_treated_as_alive(monkeypatch):
    """PermissionError from os.kill(pid, 0) means the process is alive under another user."""
    from graphify import detect
    def mock_kill(pid, sig):
        raise PermissionError("Access denied")

    monkeypatch.setattr(os, "kill", mock_kill)
    if os.name == "nt":
        monkeypatch.setattr(os, "name", "posix")
    assert detect._is_pid_alive(12345) is True


def test_is_pid_alive_windows_access_denied_treated_as_alive(monkeypatch):
    """ERROR_ACCESS_DENIED (5) on Windows OpenProcess means the process is alive."""
    import sys
    from unittest.mock import MagicMock
    from graphify import detect

    mock_kernel32 = MagicMock()
    mock_kernel32.OpenProcess.return_value = 0
    mock_kernel32.GetLastError.return_value = 5
    mock_ctypes = MagicMock()
    mock_ctypes.windll.kernel32 = mock_kernel32

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setitem(sys.modules, "ctypes", mock_ctypes)
    assert detect._is_pid_alive(12345) is True


def test_release_mismatched_token_does_not_delete_other_owner_token_file(tmp_path):
    """A stale owner calling release with an old token must NOT delete active owner's token file."""
    out = tmp_path / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    lock_file = out / ".rebuild.lock"
    token_file = out / ".graphify_build_token"

    # Active owner B writes its lock and token
    lock_file.write_text(f"{os.getpid()}\ntoken=token_B\n", encoding="utf-8")
    token_file.write_text("token_B", encoding="utf-8")

    # Stale owner A tries to release token_A
    released = release_build_lock(tmp_path, token="token_A")
    assert released is False

    # BOTH .rebuild.lock and .graphify_build_token must remain owned by token_B
    assert lock_file.exists()
    assert "token=token_B" in lock_file.read_text(encoding="utf-8")
    assert token_file.exists()
    assert token_file.read_text(encoding="utf-8").strip() == "token_B"


def test_release_matching_token_unlinks_both_files(tmp_path):
    """A matching owner calling release removes both .rebuild.lock and .graphify_build_token."""
    status = acquire_build_lock(tmp_path)
    assert status.result == LockResult.ACQUIRED
    out = tmp_path / "graphify-out"
    assert (out / ".rebuild.lock").exists()
    assert (out / ".graphify_build_token").exists()

    released = release_build_lock(tmp_path, token=status.token)
    assert released is True
    assert not (out / ".rebuild.lock").exists()
    assert not (out / ".graphify_build_token").exists()


def test_step2_fresh_reinspection_releases_lock(tmp_path):
    """Step 2 protocol: acquiring lock followed by FRESH re-inspection releases lock before exit."""
    head = _init_git_repo(tmp_path)
    _write_graph(tmp_path, built_at_commit=head)

    out = tmp_path / "graphify-out"
    status = acquire_build_lock(tmp_path)
    assert status.result == LockResult.ACQUIRED
    assert (out / ".rebuild.lock").exists()

    re_state = inspect_graph_state(tmp_path, current_token=status.token)
    assert re_state.state == GraphState.FRESH

    # Step 2 releases lock when FRESH
    released = release_build_lock(tmp_path, token=status.token)
    assert released is True
    assert not (out / ".rebuild.lock").exists()
    assert not (out / ".graphify_build_token").exists()


def test_step2_total_files_zero_releases_lock(tmp_path):
    """Step 2 protocol: detect() with 0 files releases lock."""
    out = tmp_path / "graphify-out"
    status = acquire_build_lock(tmp_path)
    assert status.result == LockResult.ACQUIRED
    assert (out / ".rebuild.lock").exists()

    from graphify.detect import detect
    res = detect(tmp_path)
    if res["total_files"] == 0:
        release_build_lock(tmp_path, token=status.token)

    assert not (out / ".rebuild.lock").exists()
    assert not (out / ".graphify_build_token").exists()


def test_release_without_token_rejected_on_token_lock(tmp_path):
    """Calling release_build_lock() without a token on a token-protected lock returns False."""
    status = acquire_build_lock(tmp_path)
    assert status.result == LockResult.ACQUIRED
    out = tmp_path / "graphify-out"
    assert (out / ".rebuild.lock").exists()

    # Attempt to release without token
    released = release_build_lock(tmp_path)
    assert released is False
    # Lock and token must remain intact
    assert (out / ".rebuild.lock").exists()
    assert (out / ".graphify_build_token").exists()

    # Releasing with correct token succeeds
    released_with_token = release_build_lock(tmp_path, token=status.token)
    assert released_with_token is True
    assert not (out / ".rebuild.lock").exists()
    assert not (out / ".graphify_build_token").exists()


def test_superseded_owner_no_token_release_does_not_delete_new_owner(tmp_path):
    """If owner A is superseded by owner B, A calling release_build_lock() with no token or token_A cannot delete B."""
    out = tmp_path / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    lock_file = out / ".rebuild.lock"
    token_file = out / ".graphify_build_token"

    # Owner B holds token_B
    lock_file.write_text(f"{os.getpid()}\ntoken=token_B\n", encoding="utf-8")
    token_file.write_text("token_B", encoding="utf-8")

    # Superseded owner A calls release_build_lock with no token
    released = release_build_lock(tmp_path)
    assert released is False
    assert lock_file.exists()
    assert token_file.exists()
    assert "token=token_B" in lock_file.read_text(encoding="utf-8")
    assert token_file.read_text(encoding="utf-8").strip() == "token_B"

    # Superseded owner A calls release_build_lock with token_A
    released_token_a = release_build_lock(tmp_path, token="token_A")
    assert released_token_a is False
    assert lock_file.exists()
    assert token_file.exists()
    assert "token=token_B" in lock_file.read_text(encoding="utf-8")
    assert token_file.read_text(encoding="utf-8").strip() == "token_B"


def test_takeover_and_aborted_session_retained_token_cleanup_safety(tmp_path):
    """Owner A acquires token_A, B takes over with token_B; A's abort cleanup with token_A returns False and leaves B intact."""
    out = tmp_path / "graphify-out"
    lock_file = out / ".rebuild.lock"
    token_file = out / ".graphify_build_token"

    # Step 1: Owner A acquires lock
    status_a = acquire_build_lock(tmp_path)
    assert status_a.result == LockResult.ACQUIRED
    token_a = status_a.token
    assert token_file.read_text(encoding="utf-8").strip() == token_a

    # Step 2: Simulate A dying/stalling and B taking over
    # Write a stale lock file with an exited PID to simulate takeover conditions
    lock_file.write_text(f"999999\ntoken={token_a}\n", encoding="utf-8")
    status_b = acquire_build_lock(tmp_path)
    assert status_b.result == LockResult.RECLAIMED_STALE
    token_b = status_b.token
    assert token_b != token_a
    assert token_file.read_text(encoding="utf-8").strip() == token_b

    # Step 3: Owner A resumes its abort cleanup using its retained token_a
    released_a = release_build_lock(tmp_path, token=token_a)
    assert released_a is False

    # Verify B's lock and token remain intact
    assert lock_file.exists()
    assert f"token={token_b}" in lock_file.read_text(encoding="utf-8")
    assert token_file.exists()
    assert token_file.read_text(encoding="utf-8").strip() == token_b

    # Step 4: Owner B completes and releases with its token_b
    released_b = release_build_lock(tmp_path, token=token_b)
    assert released_b is True
    assert not lock_file.exists()
    assert not token_file.exists()


# ── 15. Advisory Findings Regression Tests ─────────────────────────────────

def test_acquire_build_lock_unlinks_symlink_and_does_not_overwrite_target(tmp_path):
    """A repo-controlled symlink at .rebuild.lock must be replaced and not overwrite target."""
    out = tmp_path / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    sensitive_file = tmp_path / "sensitive.txt"
    sensitive_file.write_text("TOP_SECRET", encoding="utf-8")

    lock_file = out / ".rebuild.lock"
    try:
        lock_file.symlink_to(sensitive_file)
    except OSError:
        pytest.skip("Symlinks not supported on this platform/privilege level")

    status = acquire_build_lock(tmp_path)
    assert status.result == LockResult.RECLAIMED_STALE
    # Target file must be untouched
    assert sensitive_file.read_text(encoding="utf-8") == "TOP_SECRET"
    # Lock file must now be a regular file, not a symlink
    assert not lock_file.is_symlink()
    assert lock_file.is_file()


def test_inspect_graph_state_detects_dirty_extensionless_shebang(tmp_path):
    """An extensionless shebang script modified in working tree must flag STALE / DIRTY_WORKTREE."""
    head = _init_git_repo(tmp_path)

    # Add extensionless shebang script to repo
    script = tmp_path / "cli_tool"
    script.write_text("#!/usr/bin/env python\ndef main(): pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "cli_tool"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add cli_tool"], cwd=str(tmp_path), check=True, capture_output=True)
    new_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(tmp_path), check=True, capture_output=True, text=True).stdout.strip()

    _write_graph(tmp_path, built_at_commit=new_head)

    # Initial state should be FRESH
    res_clean = inspect_graph_state(tmp_path)
    assert res_clean.state == GraphState.FRESH

    # Modify extensionless shebang script in working tree
    script.write_text("#!/usr/bin/env python\ndef main(): print('modified')\n", encoding="utf-8")

    res_dirty = inspect_graph_state(tmp_path)
    assert res_dirty.state == GraphState.STALE
    assert StalenessReason.DIRTY_WORKTREE in res_dirty.staleness_reasons
    assert "cli_tool" in res_dirty.dirty_files


def test_is_pid_alive_windows_active_process_treated_as_alive(monkeypatch):
    """1. Active running process (WAIT_TIMEOUT = 258) is ALIVE."""
    import sys
    from unittest.mock import MagicMock
    from graphify import detect

    mock_kernel32 = MagicMock()
    mock_kernel32.OpenProcess.return_value = 9999
    mock_kernel32.WaitForSingleObject.return_value = 258  # WAIT_TIMEOUT -> active
    mock_ctypes = MagicMock()
    mock_ctypes.windll.kernel32 = mock_kernel32

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setitem(sys.modules, "ctypes", mock_ctypes)

    assert detect._is_pid_alive(12345) is True
    mock_kernel32.CloseHandle.assert_called_once_with(9999)


def test_is_pid_alive_windows_signaled_process_treated_as_dead(monkeypatch):
    """2. Signaled/terminated process (WAIT_OBJECT_0 = 0) is DEAD."""
    import sys
    from unittest.mock import MagicMock
    from graphify import detect

    mock_kernel32 = MagicMock()
    mock_kernel32.OpenProcess.return_value = 9999
    mock_kernel32.WaitForSingleObject.return_value = 0  # WAIT_OBJECT_0 -> terminated
    mock_ctypes = MagicMock()
    mock_ctypes.windll.kernel32 = mock_kernel32

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setitem(sys.modules, "ctypes", mock_ctypes)

    assert detect._is_pid_alive(12345) is False
    mock_kernel32.CloseHandle.assert_called_once_with(9999)


def test_is_pid_alive_windows_exit_code_259_with_signaled_handle_treated_as_dead(monkeypatch):
    """3. Terminated process whose exit code happens to be 259 (STILL_ACTIVE) is DEAD."""
    import sys
    from unittest.mock import MagicMock
    from graphify import detect

    mock_kernel32 = MagicMock()
    mock_kernel32.OpenProcess.return_value = 9999
    mock_kernel32.WaitForSingleObject.return_value = 0  # WAIT_OBJECT_0 -> terminated
    mock_ctypes = MagicMock()
    mock_ctypes.windll.kernel32 = mock_kernel32

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setitem(sys.modules, "ctypes", mock_ctypes)

    assert detect._is_pid_alive(12345) is False
    mock_kernel32.CloseHandle.assert_called_once_with(9999)


def test_is_pid_alive_windows_access_denied_treated_as_alive_case4(monkeypatch):
    """4. ERROR_ACCESS_DENIED (5) when OpenProcess fails means PID exists / ALIVE."""
    import sys
    from unittest.mock import MagicMock
    from graphify import detect

    mock_kernel32 = MagicMock()
    mock_kernel32.OpenProcess.return_value = 0
    mock_kernel32.GetLastError.return_value = 5  # ERROR_ACCESS_DENIED
    mock_ctypes = MagicMock()
    mock_ctypes.windll.kernel32 = mock_kernel32

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setitem(sys.modules, "ctypes", mock_ctypes)

    assert detect._is_pid_alive(12345) is True


def test_is_pid_alive_windows_nonexistent_pid_treated_as_dead(monkeypatch):
    """5. Nonexistent PID (ERROR_INVALID_PARAMETER = 87) is DEAD."""
    import sys
    from unittest.mock import MagicMock
    from graphify import detect

    mock_kernel32 = MagicMock()
    mock_kernel32.OpenProcess.return_value = 0
    mock_kernel32.GetLastError.return_value = 87  # ERROR_INVALID_PARAMETER
    mock_ctypes = MagicMock()
    mock_ctypes.windll.kernel32 = mock_kernel32

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setitem(sys.modules, "ctypes", mock_ctypes)

    assert detect._is_pid_alive(12345) is False


def test_parse_porcelain_z_all_record_types():
    """_parse_porcelain_z handles all porcelain-z entry types including renames and copies."""
    from graphify.detect import _parse_porcelain_z

    raw = (
        b" M modified.py\x00"
        b"A  staged.py\x00"
        b"MM both_mod.py\x00"
        b"?? untracked.py\x00"
        b"R  new_path.py\x00old_path.py\x00"
        b"RM renamed_mod.py\x00orig_mod.py\x00"
        b"C  copy_dst.py\x00copy_src.py\x00"
        b"CM copy_dst_mod.py\x00copy_src_mod.py\x00"
        b" M path with spaces/my file.py\x00"
    )
    entries = _parse_porcelain_z(raw)
    assert len(entries) == 9
    assert entries[0] == (" M", "modified.py", None)
    assert entries[1] == ("A ", "staged.py", None)
    assert entries[2] == ("MM", "both_mod.py", None)
    assert entries[3] == ("??", "untracked.py", None)
    assert entries[4] == ("R ", "new_path.py", "old_path.py")
    assert entries[5] == ("RM", "renamed_mod.py", "orig_mod.py")
    assert entries[6] == ("C ", "copy_dst.py", "copy_src.py")
    assert entries[7] == ("CM", "copy_dst_mod.py", "copy_src_mod.py")
    assert entries[8] == (" M", "path with spaces/my file.py", None)
