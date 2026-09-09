"""CLI-level tests for batched `graphify global add` (#3438).

Driven as a subprocess with HOME/USERPROFILE redirected, because the global store
path is resolved from Path.home() at import time.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _write_graph(path: Path, node: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "directed": False, "multigraph": False, "graph": {},
            "nodes": [{"id": node, "label": node.upper(), "source_file": f"src/{node}.py"}],
            "links": [],
        }),
        encoding="utf-8",
    )
    return path


def _run(home: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home))
    env.pop("PYTHONWARNINGS", None)
    return subprocess.run(
        [sys.executable, "-m", "graphify", "global", *args],
        capture_output=True, text=True, env=env,
        cwd=str(Path(__file__).resolve().parents[1]),
    )


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


def test_cli_adds_several_graphs_in_one_invocation(home, tmp_path):
    a = _write_graph(tmp_path / "alpha" / "graphify-out" / "graph.json", "amod")
    b = _write_graph(tmp_path / "beta" / "graphify-out" / "graph.json", "bmod")

    proc = _run(home, "add", str(a), str(b))

    assert proc.returncode == 0, proc.stderr
    assert "Added 'alpha'" in proc.stdout
    assert "Added 'beta'" in proc.stdout
    stored = json.loads((home / ".graphify" / "global-graph.json").read_text())
    assert {n["id"] for n in stored["nodes"]} == {"alpha::amod", "beta::bmod"}


def test_cli_accepts_as_before_the_graph(home, tmp_path):
    """`global add --as tag graph.json` worked before batching and still has to."""
    a = _write_graph(tmp_path / "alpha" / "graphify-out" / "graph.json", "amod")

    proc = _run(home, "add", "--as", "custom", str(a))

    assert proc.returncode == 0, proc.stderr
    assert "Added 'custom'" in proc.stdout


def test_cli_accepts_as_after_the_graph(home, tmp_path):
    a = _write_graph(tmp_path / "alpha" / "graphify-out" / "graph.json", "amod")

    proc = _run(home, "add", str(a), "--as", "custom")

    assert proc.returncode == 0, proc.stderr
    assert "Added 'custom'" in proc.stdout


def test_cli_tags_each_graph_in_a_batch(home, tmp_path):
    a = _write_graph(tmp_path / "alpha" / "graphify-out" / "graph.json", "amod")
    b = _write_graph(tmp_path / "beta" / "graphify-out" / "graph.json", "bmod")

    proc = _run(home, "add", str(a), "--as", "one", str(b), "--as", "two")

    assert proc.returncode == 0, proc.stderr
    stored = json.loads((home / ".graphify" / "global-graph.json").read_text())
    assert {n["id"] for n in stored["nodes"]} == {"one::amod", "two::bmod"}


def test_cli_trailing_as_retags_the_last_graph(home, tmp_path):
    """A --as after the last graph still tags that graph, wherever it appears."""
    a = _write_graph(tmp_path / "alpha" / "graphify-out" / "graph.json", "amod")

    proc = _run(home, "add", str(a), "--keep-going", "--as", "orphan")

    assert proc.returncode == 0, proc.stderr
    assert "Added 'orphan'" in proc.stdout


def test_cli_bare_as_with_no_graph_is_usage_error(home):
    proc = _run(home, "add", "--as", "orphan")

    assert proc.returncode == 1
    assert "Usage:" in proc.stderr


def test_cli_skipped_message_does_not_claim_the_whole_graph_is_unmodified(home, tmp_path):
    """In a batch, one unchanged repo says nothing about the other units."""
    a = _write_graph(tmp_path / "alpha" / "graphify-out" / "graph.json", "amod")
    b = _write_graph(tmp_path / "beta" / "graphify-out" / "graph.json", "bmod")

    assert _run(home, "add", str(a)).returncode == 0
    proc = _run(home, "add", str(a), str(b))

    assert proc.returncode == 0, proc.stderr
    assert "'alpha' unchanged since last add - not re-added." in proc.stdout
    assert "global graph not modified" not in proc.stdout
    assert "Added 'beta'" in proc.stdout


def test_cli_keep_going_commits_the_readable_graphs(home, tmp_path):
    a = _write_graph(tmp_path / "alpha" / "graphify-out" / "graph.json", "amod")
    bad = tmp_path / "bad" / "graphify-out" / "graph.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{ not json", encoding="utf-8")

    proc = _run(home, "add", str(a), str(bad), "--keep-going")

    # Non-zero because a repo genuinely did not land...
    assert proc.returncode == 1
    # ...but the readable one did.
    assert "Added 'alpha'" in proc.stdout
    stored = json.loads((home / ".graphify" / "global-graph.json").read_text())
    assert {n["id"] for n in stored["nodes"]} == {"alpha::amod"}


def test_cli_default_aborts_the_batch_on_a_bad_graph(home, tmp_path):
    a = _write_graph(tmp_path / "alpha" / "graphify-out" / "graph.json", "amod")
    bad = tmp_path / "bad" / "graphify-out" / "graph.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{ not json", encoding="utf-8")

    proc = _run(home, "add", str(a), str(bad))

    assert proc.returncode == 1
    assert not (home / ".graphify" / "global-graph.json").exists()


def test_cli_rejects_unknown_option(home, tmp_path):
    a = _write_graph(tmp_path / "alpha" / "graphify-out" / "graph.json", "amod")

    proc = _run(home, "add", str(a), "--bogus")

    assert proc.returncode == 1
    assert "unknown option" in proc.stderr
