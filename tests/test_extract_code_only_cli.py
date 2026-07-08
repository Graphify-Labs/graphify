"""`graphify extract --code-only` indexes code without an LLM key (#1734).

A mixed repo (code + docs) with no API key configured used to hard-fail on the
doc/paper/image files. `--code-only` skips the semantic pass so the code graph
still builds, and the no-key error now points users at the flag.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable
_KEY_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL",
             "ANTHROPIC_API_KEY", "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY")


def _mixed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 1\n")
    (repo / "README.md").write_text("# Design\n\nHow it works.\n")
    (repo / "NOTES.txt").write_text("Architecture notes and rationale.\n")
    return repo


def _run(repo: Path, *extra: str):
    env = {k: v for k, v in os.environ.items() if k not in _KEY_VARS}
    env["GRAPHIFY_OUT"] = str(repo / "graphify-out")
    return subprocess.run(
        [PYTHON, "-m", "graphify", "extract", ".", *extra],
        cwd=repo, capture_output=True, text=True, env=env,
    )


def test_code_only_succeeds_without_key(tmp_path):
    repo = _mixed_repo(tmp_path)
    r = _run(repo, "--code-only")
    assert r.returncode == 0, f"--code-only should succeed with no key: {r.stderr}"
    out = r.stdout + r.stderr
    assert "--code-only: skipping" in out
    graph = repo / "graphify-out" / "graph.json"
    assert graph.exists(), "code graph must still be written"
    import json
    g = json.loads(graph.read_text())
    labels = [n.get("label") for n in g["nodes"]]
    assert any(str(l).startswith("hello") for l in labels), "code was indexed"


def test_mixed_repo_without_key_errors_and_points_at_code_only(tmp_path):
    repo = _mixed_repo(tmp_path)
    r = _run(repo)  # no --code-only, no key
    assert r.returncode != 0, "mixed repo with no key should still error without the flag"
    assert "--code-only" in r.stderr, "the no-key error must point users at --code-only"
