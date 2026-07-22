"""`graphify extract --html-as-code` (#1230): .html is DOCUMENT (semantic/LLM
path) by default; the flag opts a project into the local AST path instead —
embedded <script> functions become graph nodes, with zero effect on any
existing default-behavior user.
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


def _html_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 1\n")
    (repo / "index.html").write_text(
        "<html><body><script>\n"
        "function greet() { return 'hi'; }\n"
        "</script></body></html>\n"
    )
    return repo


def _run(repo: Path, *extra: str):
    env = {k: v for k, v in os.environ.items() if k not in _KEY_VARS}
    env["GRAPHIFY_OUT"] = str(repo / "graphify-out")
    return subprocess.run(
        [PYTHON, "-m", "graphify", "extract", ".", "--code-only", "--no-cluster", *extra],
        cwd=repo, capture_output=True, text=True, env=env,
    )


def _labels(repo: Path) -> list[str]:
    graph = json.loads((repo / "graphify-out" / "graph.json").read_text())
    return [n.get("label") for n in graph["nodes"]]


def test_html_as_code_off_by_default(tmp_path):
    """--code-only alone: .html is a document, skipped entirely (like any other
    doc under --code-only) — no embedded JS symbol appears in the graph."""
    repo = _html_repo(tmp_path)
    r = _run(repo)
    assert r.returncode == 0, r.stderr
    labels = _labels(repo)
    assert any(str(l).startswith("hello") for l in labels), "python code was indexed"
    assert not any("greet" in str(l) for l in labels), (
        "embedded JS must not appear without --html-as-code (opt-in contract, #1230)"
    )


def test_html_as_code_flag_extracts_embedded_js(tmp_path):
    repo = _html_repo(tmp_path)
    r = _run(repo, "--html-as-code")
    assert r.returncode == 0, r.stderr
    labels = _labels(repo)
    assert any("greet" in str(l) for l in labels), "embedded JS was not extracted"


def test_extract_usage_advertises_html_as_code(tmp_path):
    r = subprocess.run(
        [PYTHON, "-m", "graphify", "extract"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "--html-as-code" in r.stdout + r.stderr, (
        "extract usage must advertise --html-as-code so the option is discoverable"
    )


def test_html_as_code_setting_persists_across_flagless_extract(tmp_path):
    """Mirrors the --no-gitignore persistence contract (#1971): once
    --html-as-code is set, a later flag-less `graphify extract` (the shape
    `graphify update`/`watch`/hooks reuse) must not silently drop .html back
    to the document path."""
    repo = _html_repo(tmp_path)

    r1 = _run(repo, "--html-as-code")
    assert r1.returncode == 0, r1.stderr
    assert any("greet" in str(l) for l in _labels(repo))

    r2 = _run(repo, "--force")  # flag-less re-extract, full rescan
    assert r2.returncode == 0, r2.stderr
    assert any("greet" in str(l) for l in _labels(repo)), (
        "flag-less re-extract clobbered the persisted --html-as-code setting"
    )


def test_html_as_code_persistence_survives_update_rebuild(tmp_path):
    """The real-world path #1971-style persistence exists for: `graphify update`
    (AST-only incremental rebuild) must also honor the persisted flag, not just
    a second `graphify extract` invocation."""
    repo = _html_repo(tmp_path)
    r1 = _run(repo, "--html-as-code")
    assert r1.returncode == 0, r1.stderr

    env = {k: v for k, v in os.environ.items() if k not in _KEY_VARS}
    env["GRAPHIFY_OUT"] = str(repo / "graphify-out")
    r2 = subprocess.run(
        [PYTHON, "-m", "graphify", "update"],
        cwd=repo, capture_output=True, text=True, env=env,
    )
    assert r2.returncode == 0, r2.stderr
    assert any("greet" in str(l) for l in _labels(repo)), (
        "graphify update dropped the persisted --html-as-code setting (#1230)"
    )
