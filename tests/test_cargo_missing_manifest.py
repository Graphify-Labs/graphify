"""`graphify extract --cargo` must degrade, not abort, when no Cargo.toml
exists at the scan root (#3677).

A missing root manifest is an ordinary condition (e.g. a Tauri app keeps its
manifest under src-tauri/), not a failure. Before the fix, FileNotFoundError
(a subclass of OSError) was caught by a handler meant for ImportError/
ConnectionError and the whole process exited, discarding the AST pass that
had already completed and never writing graph.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable
_KEY_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL",
             "ANTHROPIC_API_KEY", "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY")


def _run(repo: Path, *extra: str):
    env = {k: v for k, v in os.environ.items() if k not in _KEY_VARS}
    env["GRAPHIFY_OUT"] = str(repo / "graphify-out")
    return subprocess.run(
        [PYTHON, "-m", "graphify", "extract", ".", "--code-only", "--cargo", *extra],
        cwd=repo, capture_output=True, text=True, env=env,
    )


def test_cargo_flag_without_a_manifest_still_writes_the_graph(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 1\n", encoding="utf-8")

    r = _run(repo)

    assert r.returncode == 0, (
        f"a missing Cargo.toml must not abort the whole extraction: {r.stderr}"
    )
    out = r.stdout + r.stderr
    assert "no Cargo.toml at scan root" in out, (
        f"the missing manifest should be reported as a skip, not silently dropped: {out}"
    )
    graph = repo / "graphify-out" / "graph.json"
    assert graph.exists(), "the AST work already done must still be written to graph.json"
    g = json.loads(graph.read_text(encoding="utf-8"))
    labels = [n.get("label") for n in g["nodes"]]
    assert any(str(l).startswith("hello") for l in labels), "code was indexed"


def test_cargo_flag_with_a_manifest_still_adds_crate_nodes(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    (repo / "Cargo.toml").write_text(
        '[package]\nname = "app"\nversion = "0.1.0"\nedition = "2021"\n',
        encoding="utf-8",
    )

    r = _run(repo)

    assert r.returncode == 0, f"a valid manifest must extract cleanly: {r.stderr}"
    graph = repo / "graphify-out" / "graph.json"
    assert graph.exists()
    g = json.loads(graph.read_text(encoding="utf-8"))
    node_ids = {n.get("id") for n in g["nodes"]}
    assert any("app" in str(i) for i in node_ids), (
        f"a real Cargo.toml should still contribute a crate node; got {sorted(node_ids)}"
    )
