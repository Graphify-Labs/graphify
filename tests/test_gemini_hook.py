"""The Gemini CLI BeforeTool guard nudges toward the graph, shell-agnostically.

Since #522 it runs as `graphify hook-guard gemini` (not a `python -c` one-liner
that depended on a bare `python` on PATH and embedded PowerShell-hostile
backticks). It always returns {"decision":"allow"} so a tool is never blocked,
and appends additionalContext only when a graph exists.
"""
import json
import os
import subprocess
import sys

from graphify.__main__ import _gemini_hook


def _env():
    e = dict(os.environ)
    e.pop("GRAPHIFY_OUT", None)
    return e


def _run(cwd, *, graph: bool):
    if graph:
        (cwd / "graphify-out").mkdir(parents=True, exist_ok=True)
        (cwd / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "graphify", "hook-guard", "gemini"],
        input="", capture_output=True, text=True, cwd=cwd, env=_env(),
    )


def test_matcher_and_command_shape():
    h = _gemini_hook()
    assert h["matcher"] == "read_file|list_directory"
    cmd = h["hooks"][0]["command"]
    # #522: no bare `python` dependency, no embedded quote/backtick soup.
    assert "python -c" not in cmd
    assert "graphify" in cmd and "hook-guard gemini" in cmd


def test_allows_and_nudges_with_graph(tmp_path):
    out = _run(tmp_path, graph=True).stdout
    payload = json.loads(out)
    assert payload["decision"] == "allow"
    assert "graphify query" in payload["additionalContext"]


def test_allows_without_nudge_when_no_graph(tmp_path):
    out = _run(tmp_path, graph=False).stdout
    payload = json.loads(out)
    assert payload["decision"] == "allow"
    assert "additionalContext" not in payload


def test_never_blocks(tmp_path):
    r = _run(tmp_path, graph=True)
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    assert payload["decision"] == "allow"


def test_honors_graphify_out_override(tmp_path):
    custom = tmp_path / "custom-out"
    custom.mkdir()
    (custom / "graph.json").write_text("{}", encoding="utf-8")
    env = dict(os.environ, GRAPHIFY_OUT=str(custom))
    r = subprocess.run(
        [sys.executable, "-m", "graphify", "hook-guard", "gemini"],
        input="", capture_output=True, text=True, cwd=tmp_path, env=env,
    )
    assert "graphify query" in json.loads(r.stdout).get("additionalContext", "")
