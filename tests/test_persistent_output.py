"""Persistent per-project output outside the Git working tree (#4063)."""

from __future__ import annotations

import shutil
from pathlib import Path

from graphify import paths


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / ".git").mkdir()
    return path


def test_persistent_graph_survives_worktree_cleanup(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path / "workspace" / "repo")
    home = tmp_path / "external-store"
    monkeypatch.chdir(repo)
    monkeypatch.delenv("GRAPHIFY_OUT", raising=False)
    monkeypatch.setenv("GRAPHIFY_HOME", str(home))

    out = Path(paths._out_from_env())
    assert out.parent.parent == home / "projects"
    assert out.name == "graphify-out"
    assert not out.is_relative_to(repo)

    out.mkdir(parents=True)
    (out / "graph.json").write_text('{"nodes":[]}', encoding="utf-8")
    (out / "cache").mkdir()
    (out / "cache" / "entry").write_text("cached", encoding="utf-8")
    scratch = repo / "generated"
    scratch.mkdir()
    shutil.rmtree(scratch)  # simulates cleaning the working tree

    assert Path(paths._out_from_env()) == out
    assert (out / "graph.json").exists()
    assert (out / "cache" / "entry").read_text(encoding="utf-8") == "cached"


def test_same_name_repositories_have_separate_stores(tmp_path, monkeypatch):
    first = _git_repo(tmp_path / "alpha" / "repo")
    second = _git_repo(tmp_path / "beta" / "repo")
    monkeypatch.delenv("GRAPHIFY_OUT", raising=False)
    monkeypatch.setenv("GRAPHIFY_HOME", str(tmp_path / "store"))

    monkeypatch.chdir(first)
    first_out = paths._out_from_env()
    monkeypatch.chdir(second)
    assert paths._out_from_env() != first_out
    monkeypatch.chdir(first)
    assert paths._out_from_env() == first_out


def test_git_subfolder_and_git_worktree_marker_use_same_store(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: /some/worktree/metadata", encoding="utf-8")
    subfolder = repo / "nested" / "src"
    subfolder.mkdir(parents=True)
    monkeypatch.setenv("GRAPHIFY_HOME", str(tmp_path / "store"))
    monkeypatch.delenv("GRAPHIFY_OUT", raising=False)

    monkeypatch.chdir(repo)
    out = paths._out_from_env()
    monkeypatch.chdir(subfolder)
    assert paths._out_from_env() == out


def test_existing_override_takes_priority_and_default_is_unchanged(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path / "repo")
    monkeypatch.chdir(repo)
    monkeypatch.setenv("GRAPHIFY_HOME", str(tmp_path / "store"))
    monkeypatch.setenv("GRAPHIFY_OUT", str(tmp_path / "manual"))
    assert paths._out_from_env() == str(tmp_path / "manual")
    monkeypatch.delenv("GRAPHIFY_OUT")
    monkeypatch.delenv("GRAPHIFY_HOME")
    assert paths._out_from_env() == "graphify-out"


def test_home_inside_repo_is_rejected(tmp_path, monkeypatch, capsys):
    repo = _git_repo(tmp_path / "repo")
    monkeypatch.chdir(repo)
    monkeypatch.delenv("GRAPHIFY_OUT", raising=False)
    monkeypatch.setenv("GRAPHIFY_HOME", str(repo / "cache"))
    assert paths._out_from_env() == "graphify-out"
    assert "outside the repository" in capsys.readouterr().err


def test_external_graph_uses_persisted_source_root(tmp_path, monkeypatch):
    from graphify import cli
    from graphify.cli import _graph_root_for

    repo = _git_repo(tmp_path / "repo")
    out = tmp_path / "store" / "projects" / "repo-hash" / "graphify-out"
    out.mkdir(parents=True)
    graph = out / "graph.json"
    graph.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli, "_GRAPHIFY_OUT", str(out))
    (out / ".graphify_root").write_text(str(repo), encoding="utf-8")

    assert _graph_root_for(graph) == repo.resolve()
    (out / ".graphify_root").write_text("not-an-absolute-path", encoding="utf-8")
    assert _graph_root_for(graph) == out.parent
    (out / ".graphify_root").unlink()
    assert _graph_root_for(graph) == out.parent

def test_local_graph_ignores_stale_absolute_marker(tmp_path, monkeypatch):
    from graphify import cli
    from graphify.cli import _graph_root_for

    repo = _git_repo(tmp_path / "repo")
    old_repo = _git_repo(tmp_path / "old-location")
    out = repo / "graphify-out"
    out.mkdir()
    (out / ".graphify_root").write_text(str(old_repo), encoding="utf-8")
    monkeypatch.setattr(cli, "_GRAPHIFY_OUT", "graphify-out")

    assert _graph_root_for(out / "graph.json") == repo


def test_imported_default_output_is_external(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    repo = _git_repo(tmp_path / "repo")
    monkeypatch.chdir(repo)
    env = dict(os.environ)
    env.pop("GRAPHIFY_OUT", None)
    env["GRAPHIFY_HOME"] = str(tmp_path / "store")
    code_root = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = str(code_root) + os.pathsep + env.get("PYTHONPATH", "")
    run = subprocess.run(
        [sys.executable, "-c", "from graphify.paths import GRAPHIFY_OUT; print(GRAPHIFY_OUT)"],
        cwd=repo, env=env, text=True, capture_output=True, check=True,
    )

    assert Path(run.stdout.strip()) == Path(paths._out_from_env())
