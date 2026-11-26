"""Shared fixture-repo helpers for the freshness tests.

Fixtures are throwaway git repos with a couple of Python files and a graph
built by the in-checkout ``python -m graphify update``. Nothing here touches a
real repository.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_ENV_STRIP = (
    "PYTEST_CURRENT_TEST",
    "PYTHONHASHSEED",
    "GRAPHIFY_AUTO_REFRESH",
    "GRAPHIFY_AUTO_REFRESH_DIRTY",
    "GRAPHIFY_AUTO_REFRESH_LOG",
    "GRAPHIFY_AUTO_REFRESH_TIMEOUT",
    "GRAPHIFY_AUTO_REFRESH_DEBOUNCE",
)


def clean_env(**overrides: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _ENV_STRIP}
    env.update({k: str(v) for k, v in overrides.items()})
    return env


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "freshness@test.local")
    git(repo, "config", "user.name", "freshness-test")


def commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def build_graph(repo: Path) -> None:
    subprocess.run(
        [sys.executable, "-m", "graphify", "update", str(repo)],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=clean_env(),
    )


def graph_json(repo: Path) -> Path:
    return repo / "graphify-out" / "graph.json"


def make_repo(base: Path) -> Path:
    """A committed, graph-built git repo with two small Python modules."""
    repo = base / "proj"
    init_repo(repo)
    (repo / "alpha.py").write_text("def greet(name):\n    return f'hi {name}'\n", encoding="utf-8")
    (repo / "beta.py").write_text(
        "from alpha import greet\n\n\ndef run():\n    return greet('world')\n",
        encoding="utf-8",
    )
    commit(repo, "initial")
    build_graph(repo)
    return repo


def log_entries(log: Path) -> list[str]:
    if not log.exists():
        return []
    return [line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
