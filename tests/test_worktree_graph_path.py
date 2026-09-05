"""#2008: read commands resolve the graph from the primary checkout when they
are run from a linked git worktree that has no ``graphify-out/`` of its own.

Agent workflows (Claude Code etc.) increasingly run every task in its own
worktree, where ``graphify explain``/``query``/``path``/``affected`` used to fail
hard with "graph file not found" because the graph lives in the primary checkout.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(tmp_path) -> Path:
    primary = tmp_path / "primary"
    primary.mkdir()
    _git("init", "-q", ".", cwd=primary)
    _git("config", "user.email", "t@t.co", cwd=primary)
    _git("config", "user.name", "t", cwd=primary)
    (primary / "f.txt").write_text("x", encoding="utf-8")
    _git("add", "-A", cwd=primary)
    _git("commit", "-qm", "init", cwd=primary)
    return primary


def _write_graph(where: Path) -> Path:
    graph = where / "graphify-out" / "graph.json"
    graph.parent.mkdir(parents=True)
    graph.write_text("{}", encoding="utf-8")
    return graph


def test_default_graph_path_resolves_from_linked_worktree(tmp_path, monkeypatch):
    """From a linked worktree with no local graphify-out, the read-command default
    graph path falls back to the primary checkout's graph."""
    if shutil.which("git") is None:  # pragma: no cover
        pytest.skip("git not available")
    primary = _init_repo(tmp_path)
    graph = _write_graph(primary)
    linked = tmp_path / "linked"
    _git("worktree", "add", "-q", str(linked), "-b", "feature", cwd=primary)

    monkeypatch.chdir(linked)
    from graphify.cli import _default_graph_path
    assert Path(_default_graph_path()).resolve() == graph.resolve()


def test_default_graph_path_prefers_local_graph_in_worktree(tmp_path, monkeypatch):
    """A worktree that built its own graph keeps using it (local wins)."""
    if shutil.which("git") is None:  # pragma: no cover
        pytest.skip("git not available")
    primary = _init_repo(tmp_path)
    _write_graph(primary)
    linked = tmp_path / "linked"
    _git("worktree", "add", "-q", str(linked), "-b", "feature", cwd=primary)
    local_graph = _write_graph(linked)

    monkeypatch.chdir(linked)
    from graphify.cli import _default_graph_path
    assert Path(_default_graph_path()).resolve() == local_graph.resolve()


def test_default_graph_path_primary_checkout_unaffected(tmp_path, monkeypatch):
    """In the primary checkout the default stays the local graphify-out path, even
    when the graph does not exist yet (normal 'run extract' error path preserved)."""
    if shutil.which("git") is None:  # pragma: no cover
        pytest.skip("git not available")
    primary = _init_repo(tmp_path)

    monkeypatch.chdir(primary)
    from graphify.cli import _default_graph_path
    assert Path(_default_graph_path()) == Path("graphify-out") / "graph.json"


def test_default_graph_path_outside_git_repo_unaffected(tmp_path, monkeypatch):
    """Outside any git repo the resolver must not crash and returns the local default."""
    monkeypatch.chdir(tmp_path)
    from graphify.cli import _default_graph_path
    assert Path(_default_graph_path()) == Path("graphify-out") / "graph.json"
