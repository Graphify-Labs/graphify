"""Tests for project-membership gating in `graphify hook-guard search` (#3882).

The search PreToolUse guard suppresses the search nudge only when every
executed search is provably targeting paths outside the current project root.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import graphify.cli as cli


def _setup_project(tmp_path: Path) -> tuple[Path, Path]:
    """Creates a project root with a valid graphify-out/graph.json and a source file,
    plus an outside directory for external file tests."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    src = project_dir / "src"
    src.mkdir()
    (src / "app.py").write_text("def hello(): pass\n", encoding="utf-8")
    out = project_dir / "graphify-out"
    out.mkdir()
    (out / "graph.json").write_text('{"nodes":[],"links":[]}', encoding="utf-8")

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "ext.py").write_text("def ext(): pass\n", encoding="utf-8")
    (outside_dir / "ext2.py").write_text("def ext2(): pass\n", encoding="utf-8")
    return project_dir, outside_dir


def _invoke(payload: dict | bytes | str | None, project_dir: Path, monkeypatch, *, env: dict | None = None) -> str:
    """Invokes _run_hook_guard in-process with stdin redirected."""
    monkeypatch.chdir(project_dir)
    if env:
        for k, v in env.items():
            monkeypatch.setenv(k, v)
    graph_out = os.environ.get("GRAPHIFY_OUT", "graphify-out")
    monkeypatch.setattr("graphify.paths.GRAPHIFY_OUT", graph_out)
    monkeypatch.setattr("graphify.paths.GRAPHIFY_OUT_NAME", os.path.basename(os.path.normpath(graph_out)))

    if isinstance(payload, (bytes, bytearray)):
        data = bytes(payload)
    elif payload is None:
        data = b""
    elif isinstance(payload, str):
        data = payload.encode("utf-8")
    else:
        data = json.dumps(payload).encode("utf-8")

    class _Stdin:
        buffer = io.BytesIO(data)

    monkeypatch.setattr(sys, "stdin", _Stdin())
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    cli._run_hook_guard("search")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 1. Grep tool
# ---------------------------------------------------------------------------

def test_grep_tool_inside_or_missing_path_nudges(tmp_path, monkeypatch):
    proj, _ = _setup_project(tmp_path)
    # Missing path -> nudges
    out_missing = _invoke({"tool_input": {"pattern": "hello"}}, proj, monkeypatch)
    assert "graphify query" in out_missing

    # Relative inside path -> nudges
    out_rel = _invoke({"tool_input": {"pattern": "hello", "path": "src"}}, proj, monkeypatch)
    assert "graphify query" in out_rel

    # Dot path -> nudges
    out_dot = _invoke({"tool_input": {"pattern": "hello", "path": "."}}, proj, monkeypatch)
    assert "graphify query" in out_dot


def test_grep_tool_outside_path_silent(tmp_path, monkeypatch):
    proj, outside = _setup_project(tmp_path)
    # Absolute outside path -> silent
    out_abs = _invoke({"tool_input": {"pattern": "hello", "path": str(outside)}}, proj, monkeypatch)
    assert out_abs.strip() == ""

    # Relative outside path -> silent
    out_rel = _invoke({"tool_input": {"pattern": "hello", "path": "../outside"}}, proj, monkeypatch)
    assert out_rel.strip() == ""


# ---------------------------------------------------------------------------
# 2. Direct Bash searches
# ---------------------------------------------------------------------------

def test_bash_inside_target_nudges(tmp_path, monkeypatch):
    proj, _ = _setup_project(tmp_path)
    for cmd in ("grep foo src/app.py", "rg foo src/", "find src/ -name '*.py'"):
        out = _invoke({"tool_input": {"command": cmd}}, proj, monkeypatch)
        assert "graphify query" in out, f"{cmd!r} should nudge"


def test_bash_outside_target_silent(tmp_path, monkeypatch):
    proj, outside = _setup_project(tmp_path)
    ext_file = str(outside / "ext.py").replace("\\", "/")
    ext_dir = str(outside).replace("\\", "/")
    for cmd in (
        f"grep foo {ext_file}",
        f"rg foo {ext_dir}",
        f"find {ext_dir} -name '*.py'",
        f"fd foo {ext_dir}",
    ):
        out = _invoke({"tool_input": {"command": cmd}}, proj, monkeypatch)
        assert out.strip() == "", f"{cmd!r} should be silent"


# ---------------------------------------------------------------------------
# 3. Compound commands
# ---------------------------------------------------------------------------

def test_bash_compound_mixed_searches_nudge(tmp_path, monkeypatch):
    proj, outside = _setup_project(tmp_path)
    ext_file = str(outside / "ext.py").replace("\\", "/")
    cmd = f"grep foo {ext_file}; rg bar src/"
    out = _invoke({"tool_input": {"command": cmd}}, proj, monkeypatch)
    assert "graphify query" in out


def test_bash_compound_all_outside_silent(tmp_path, monkeypatch):
    proj, outside = _setup_project(tmp_path)
    ext1 = str(outside / "ext.py").replace("\\", "/")
    ext2 = str(outside / "ext2.py").replace("\\", "/")
    cmd = f"grep foo {ext1} && rg bar {ext2}"
    out = _invoke({"tool_input": {"command": cmd}}, proj, monkeypatch)
    assert out.strip() == ""


# ---------------------------------------------------------------------------
# 4. Working directory tracking (cd)
# ---------------------------------------------------------------------------

def test_bash_cd_inside_nudges(tmp_path, monkeypatch):
    proj, _ = _setup_project(tmp_path)
    out = _invoke({"tool_input": {"command": "cd src && grep foo app.py"}}, proj, monkeypatch)
    assert "graphify query" in out


def test_bash_cd_outside_silent(tmp_path, monkeypatch):
    proj, outside = _setup_project(tmp_path)
    ext_dir = str(outside).replace("\\", "/")
    out = _invoke({"tool_input": {"command": f"cd {ext_dir} && grep foo ext.py"}}, proj, monkeypatch)
    assert out.strip() == ""


# ---------------------------------------------------------------------------
# 5. Redirections
# ---------------------------------------------------------------------------

def test_bash_input_redirection_outside_silent(tmp_path, monkeypatch):
    proj, outside = _setup_project(tmp_path)
    ext_file = str(outside / "ext.py").replace("\\", "/")
    out = _invoke({"tool_input": {"command": f"grep foo < {ext_file}"}}, proj, monkeypatch)
    assert out.strip() == ""


def test_bash_output_redirection_ignored(tmp_path, monkeypatch):
    proj, outside = _setup_project(tmp_path)
    ext_out = str(outside / "out.txt").replace("\\", "/")
    for cmd in (
        f"grep foo src/app.py > {ext_out}",
        f"grep foo src/app.py >> {ext_out}",
        f"grep foo src/app.py 2> {ext_out}",
        "grep foo src/app.py 2>&1",
    ):
        out = _invoke({"tool_input": {"command": cmd}}, proj, monkeypatch)
        assert "graphify query" in out, f"{cmd!r} should nudge"


# ---------------------------------------------------------------------------
# 6. Pipelines
# ---------------------------------------------------------------------------

def test_bash_pipeline_known_outside_silent(tmp_path, monkeypatch):
    proj, outside = _setup_project(tmp_path)
    ext_file = str(outside / "ext.py").replace("\\", "/")
    for cmd in (
        f"cat {ext_file} | grep foo",
        f"cat {ext_file} | sort | uniq | grep foo",
    ):
        out = _invoke({"tool_input": {"command": cmd}}, proj, monkeypatch)
        assert out.strip() == "", f"{cmd!r} should be silent"


def test_bash_pipeline_known_inside_nudges(tmp_path, monkeypatch):
    proj, _ = _setup_project(tmp_path)
    out = _invoke({"tool_input": {"command": "cat src/app.py | grep foo"}}, proj, monkeypatch)
    assert "graphify query" in out


def test_bash_pipeline_unknown_stream_nudges(tmp_path, monkeypatch):
    proj, _ = _setup_project(tmp_path)
    out = _invoke({"tool_input": {"command": "python script.py | grep foo"}}, proj, monkeypatch)
    assert "graphify query" in out


# ---------------------------------------------------------------------------
# 7. Option & pattern handling
# ---------------------------------------------------------------------------

def test_bash_option_regression_flags_without_args_nudge(tmp_path, monkeypatch):
    proj, _ = _setup_project(tmp_path)
    # -E and -r must not consume the pattern 'foo', so src/app.py is recognized as target
    for cmd in ("grep -E foo src/app.py", "grep -r foo src/app.py"):
        out = _invoke({"tool_input": {"command": cmd}}, proj, monkeypatch)
        assert "graphify query" in out, f"{cmd!r} should nudge"


def test_bash_option_explicit_pattern_flag_not_treated_as_path(tmp_path, monkeypatch):
    proj, outside = _setup_project(tmp_path)
    ext_file = str(outside / "ext.py").replace("\\", "/")
    # -e takes the pattern, even though the pattern string looks like an in-project file
    cmd = f"grep -e src/app.py {ext_file}"
    out = _invoke({"tool_input": {"command": cmd}}, proj, monkeypatch)
    assert out.strip() == ""


# ---------------------------------------------------------------------------
# 8. Uncertainty preservation
# ---------------------------------------------------------------------------

def test_bash_uncertainty_cases_nudge(tmp_path, monkeypatch):
    proj, outside = _setup_project(tmp_path)
    ext_file = str(outside / "ext.py").replace("\\", "/")
    ext_dir = str(outside).replace("\\", "/")
    for cmd in (
        f"grep foo \"$1\"",
        f"grep foo \"$(echo {ext_file})\"",
        "cd - && grep foo x",
        f"xargs grep foo",
        f"cat <<EOF\nhello\nEOF\ngrep foo {ext_file}",
        f"(cd {ext_dir}); grep foo src/app.py",
        f"(cd {ext_dir}) ; grep foo src/app.py",
        f"(cd {ext_dir})&&grep foo src/app.py",
        f"(cd {ext_dir} && grep foo ext.py)",
    ):
        out = _invoke({"tool_input": {"command": cmd}}, proj, monkeypatch)
        assert "graphify query" in out, f"{cmd!r} should nudge on uncertainty"


def test_windows_drive_relative_path_is_uncertain(tmp_path, monkeypatch):
    proj, _ = _setup_project(tmp_path)
    # C:x.py is drive-relative and depends on external drive C cwd
    out = _invoke({"tool_input": {"command": "grep foo C:ext.py"}}, proj, monkeypatch)
    assert "graphify query" in out


# ---------------------------------------------------------------------------
# 9. Fail-open and never block
# ---------------------------------------------------------------------------

def test_fail_open_malformed_input_never_denies(tmp_path):
    proj, _ = _setup_project(tmp_path)
    r = subprocess.run(
        [sys.executable, "-m", "graphify", "hook-guard", "search"],
        input="{malformed json", capture_output=True, text=True, cwd=proj,
    )
    assert r.returncode == 0
    assert r.stdout.strip() == ""
    assert "permissionDecision" not in r.stdout
