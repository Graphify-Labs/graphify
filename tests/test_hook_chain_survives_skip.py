"""A graphify skip must not end the whole hook (#2986).

The generated block is appended to whatever post-commit / post-checkout a
repo already has, and other tools chain their logic after it. Every skip
condition in the block is a bare `exit 0`, which in a flat script ends the
entire hook process — so anything after graphify's end marker was silently
dropped on every root commit (HEAD~1 does not exist), every rebase/merge,
every linked worktree and every GRAPHIFY_SKIP_HOOK=1.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from graphify.hooks import _CHECKOUT_MARKER_END, _HOOK_MARKER_END, install

pytestmark = pytest.mark.skipif(shutil.which("sh") is None, reason="sh required to run the hook")


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


def _install_with_trailer(repo: Path, name: str, marker_end: str) -> Path:
    install(repo)
    hook = repo / ".git" / "hooks" / name
    text = hook.read_text(encoding="utf-8")
    assert marker_end in text
    hook.write_text(text.rstrip() + "\necho AFTER_GRAPHIFY\n", encoding="utf-8", newline="\n")
    return hook


def _run(hook: Path, repo: Path, *args: str, **env_extra: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(env_extra)
    return subprocess.run(["sh", str(hook), *args], capture_output=True, text=True,
                          cwd=str(repo), env=env)


def test_a_skipped_post_commit_still_runs_what_follows(tmp_path):
    repo = _repo(tmp_path)
    hook = _install_with_trailer(repo, "post-commit", _HOOK_MARKER_END)
    r = _run(hook, repo, GRAPHIFY_SKIP_HOOK="1")
    assert r.returncode == 0, r.stderr
    assert "AFTER_GRAPHIFY" in r.stdout
    assert "launching background rebuild" not in r.stdout  # the skip itself still holds


def test_a_rebase_in_progress_still_runs_what_follows(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".git" / "rebase-merge").mkdir()
    hook = _install_with_trailer(repo, "post-commit", _HOOK_MARKER_END)
    r = _run(hook, repo)
    assert r.returncode == 0, r.stderr
    assert "AFTER_GRAPHIFY" in r.stdout


def test_an_empty_diff_still_runs_what_follows(tmp_path):
    """A repo with no commits: `git diff HEAD~1 HEAD` and the fallback both
    yield nothing, the block exits on the empty CHANGED — the root-commit
    shape every repository hits once."""
    repo = _repo(tmp_path)
    hook = _install_with_trailer(repo, "post-commit", _HOOK_MARKER_END)
    r = _run(hook, repo)
    assert r.returncode == 0, r.stderr
    assert "AFTER_GRAPHIFY" in r.stdout


def test_a_non_branch_checkout_still_runs_what_follows(tmp_path):
    repo = _repo(tmp_path)
    hook = _install_with_trailer(repo, "post-checkout", _CHECKOUT_MARKER_END)
    r = _run(hook, repo, "abc", "def", "0")  # a file checkout, not a branch switch
    assert r.returncode == 0, r.stderr
    assert "AFTER_GRAPHIFY" in r.stdout


def test_a_skipped_checkout_hook_still_runs_what_follows(tmp_path):
    repo = _repo(tmp_path)
    hook = _install_with_trailer(repo, "post-checkout", _CHECKOUT_MARKER_END)
    r = _run(hook, repo, "abc", "def", "1", GRAPHIFY_SKIP_HOOK="1")
    assert r.returncode == 0, r.stderr
    assert "AFTER_GRAPHIFY" in r.stdout


def test_a_preexisting_hook_before_the_block_still_runs_first(tmp_path):
    repo = _repo(tmp_path)
    hook = repo / ".git" / "hooks" / "post-commit"
    hook.write_text("#!/bin/sh\necho BEFORE_GRAPHIFY\n", encoding="utf-8", newline="\n")
    install(repo)
    r = _run(hook, repo, GRAPHIFY_SKIP_HOOK="1")
    assert r.returncode == 0, r.stderr
    assert "BEFORE_GRAPHIFY" in r.stdout


def test_the_block_is_still_recognised_and_updated_in_place(tmp_path):
    """Markers stay outside the subshell so reinstall/uninstall/status keep
    finding the block."""
    repo = _repo(tmp_path)
    install(repo)
    hook = repo / ".git" / "hooks" / "post-commit"
    first = hook.read_text(encoding="utf-8")
    assert "already installed" in install(repo)
    assert hook.read_text(encoding="utf-8") == first
