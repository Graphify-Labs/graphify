"""`_git_head()` must resolve from the target repo, not the caller's CWD.

`built_at_commit` is written into graph.json as the graph's provenance. Resolved from the
process CWD it records whichever repository the caller happened to be sitting in — which,
for a git hook, a watch daemon or any wrapper script, is routinely not the repository being
graphed. The result is a graph asserting a commit that does not exist in the repo it
describes, and consumers that compare the two conclude the write failed.
"""
from __future__ import annotations

import os
import subprocess

import pytest

from graphify.export import _git_head as export_git_head
from graphify.watch import _git_head as watch_git_head


def _repo(path, content="x"):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    (path / "f.txt").write_text(content)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", content], cwd=path, check=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=path,
                          capture_output=True, text=True).stdout.strip()


@pytest.mark.parametrize("git_head", [export_git_head, watch_git_head],
                         ids=["export", "watch"])
def test_root_wins_over_caller_cwd(tmp_path, monkeypatch, git_head):
    """The regression: called from an unrelated repo, `root` must still win."""
    target_head = _repo(tmp_path / "target", "target")
    _repo(tmp_path / "elsewhere", "elsewhere")

    monkeypatch.chdir(tmp_path / "elsewhere")
    assert git_head(tmp_path / "target") == target_head


@pytest.mark.parametrize("git_head", [export_git_head, watch_git_head],
                         ids=["export", "watch"])
def test_subdirectory_of_the_repo_resolves(tmp_path, git_head):
    """`root` may be any path inside the repo — git walks up to find it."""
    head = _repo(tmp_path / "target", "target")
    sub = tmp_path / "target" / "graphify-out"
    sub.mkdir()
    assert git_head(sub) == head


@pytest.mark.parametrize("git_head", [export_git_head, watch_git_head],
                         ids=["export", "watch"])
def test_omitting_root_keeps_the_previous_behaviour(tmp_path, monkeypatch, git_head):
    """Backwards compatible: no `root` still resolves from the CWD."""
    head = _repo(tmp_path / "target", "target")
    monkeypatch.chdir(tmp_path / "target")
    assert git_head() == head


@pytest.mark.parametrize("git_head", [export_git_head, watch_git_head],
                         ids=["export", "watch"])
def test_non_repo_root_returns_none(tmp_path, git_head):
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    assert git_head(plain) is None
