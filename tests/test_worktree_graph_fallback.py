"""`_default_graph_path` falls back to the main checkout's graph from a git
worktree (#2008).

A worktree shares history with the main checkout but has no graphify-out/ of
its own, so a bare `graphify explain`/`query`/etc. run from inside one used
to fail with "graph file not found" even though the graph exists one git
worktree away. These tests build real git repos and worktrees under tmp_path
rather than mocking subprocess, since the whole point is git's own
`--git-common-dir` resolution behaving as expected.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from graphify.cli import _default_graph_path, _worktree_graph_fallback

pytestmark = pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git not available",
)


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _make_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", cwd=root)
    _git("config", "user.email", "test@test.com", cwd=root)
    _git("config", "user.name", "test", cwd=root)
    (root / "README.md").write_text("x")
    _git("add", ".", cwd=root)
    _git("commit", "-q", "-m", "init", cwd=root)
    return root


@pytest.fixture
def cwd_guard():
    old = os.getcwd()
    yield
    os.chdir(old)


def test_worktree_falls_back_to_main_checkout_graph(tmp_path, cwd_guard):
    main = _make_repo(tmp_path / "main")
    (main / "graphify-out").mkdir()
    graph = main / "graphify-out" / "graph.json"
    graph.write_text('{"nodes": [], "links": []}')

    worktree = tmp_path / "wt"
    _git("worktree", "add", "--detach", str(worktree), "HEAD", cwd=main)

    os.chdir(worktree)
    result = _worktree_graph_fallback()
    assert result is not None
    assert result.resolve() == graph.resolve()
    assert _default_graph_path() == str(result)


def test_main_checkout_with_no_graph_returns_plain_default(tmp_path, cwd_guard):
    """Not a worktree scenario at all: no graphify-out/ anywhere. Must not
    crash, and must return the ordinary (non-existent) default path."""
    main = _make_repo(tmp_path / "solo")
    os.chdir(main)
    assert _worktree_graph_fallback() is None
    assert _default_graph_path() == str(Path("graphify-out") / "graph.json")


def test_worktree_with_no_graph_anywhere_returns_none(tmp_path, cwd_guard):
    main = _make_repo(tmp_path / "main2")
    worktree = tmp_path / "wt2"
    _git("worktree", "add", "--detach", str(worktree), "HEAD", cwd=main)

    os.chdir(worktree)
    assert _worktree_graph_fallback() is None
    assert _default_graph_path() == str(Path("graphify-out") / "graph.json")


def test_not_a_git_repo_returns_none(tmp_path, cwd_guard):
    plain = tmp_path / "not_a_repo"
    plain.mkdir()
    os.chdir(plain)
    assert _worktree_graph_fallback() is None
    assert _default_graph_path() == str(Path("graphify-out") / "graph.json")


def test_worktree_with_its_own_graph_prefers_it(tmp_path, cwd_guard):
    """If the worktree DOES have its own graphify-out/graph.json (built
    there directly), _default_graph_path must use that one, not fall back --
    the fallback only fires when the local candidate is absent."""
    main = _make_repo(tmp_path / "main3")
    (main / "graphify-out").mkdir()
    (main / "graphify-out" / "graph.json").write_text('{"nodes": [], "links": []}')

    worktree = tmp_path / "wt3"
    _git("worktree", "add", "--detach", str(worktree), "HEAD", cwd=main)
    (worktree / "graphify-out").mkdir()
    own_graph = worktree / "graphify-out" / "graph.json"
    own_graph.write_text('{"nodes": [], "links": []}')

    os.chdir(worktree)
    assert _default_graph_path() == str(Path("graphify-out") / "graph.json")
