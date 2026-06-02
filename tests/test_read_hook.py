"""Behavioral tests for the query-first PreToolUse hooks (issue #1114).

The other tests assert the hooks are *present* in settings.json. These run the
hook's shell command the way Claude Code will: pipe a crafted tool_input JSON to
`sh -c "<command>"` in a tmp_path cwd with or without graphify-out/graph.json,
then assert on stdout. This is the only layer that proves the nudge/silence
behavior of the Read|Glob hook and the multi-file vs single-file discrimination
in the broadened Bash hook.
"""
from __future__ import annotations
import json
import subprocess

import pytest

from graphify.__main__ import _SETTINGS_HOOK, _READ_SETTINGS_HOOK


def _run(hook, tool_input, cwd):
    cmd = hook["hooks"][0]["command"]
    payload = json.dumps({"tool_input": tool_input})
    p = subprocess.run(
        ["sh", "-c", cmd], input=payload, capture_output=True, text=True, cwd=str(cwd)
    )
    return p.stdout


def _has_graph(tmp_path):
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "graph.json").write_text("{}")


def _nudges(out):
    return "graphify query" in out or "Before reading multiple source files" in out


# ---------------------------------------------------------------------------
# Read|Glob hook — gate on graph.json
# ---------------------------------------------------------------------------

def test_read_hook_silent_without_graph(tmp_path):
    out = _run(_READ_SETTINGS_HOOK, {"file_path": "src/app.py"}, tmp_path)
    assert "graphify" not in out


def test_read_hook_nudges_with_graph(tmp_path):
    _has_graph(tmp_path)
    out = _run(_READ_SETTINGS_HOOK, {"file_path": "src/app.py"}, tmp_path)
    assert "graphify query" in out
    # emitted text must be valid PreToolUse JSON, not just a substring match
    parsed = json.loads(out)
    ctx = parsed["hookSpecificOutput"]["additionalContext"]
    assert "graphify query" in ctx
    assert "reading raw source files" in ctx


# ---------------------------------------------------------------------------
# Read|Glob hook — source/doc targeting vs graph-output silence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["src/app.py", "lib/foo.ts", "main.go", "Server.java", "mod.rs"])
def test_read_hook_nudges_on_source_file(tmp_path, path):
    _has_graph(tmp_path)
    out = _run(_READ_SETTINGS_HOOK, {"file_path": path}, tmp_path)
    assert _nudges(out)


@pytest.mark.parametrize("path", ["README.md", "docs/guide.rst", "notes.txt", "page.mdx"])
def test_read_hook_nudges_on_doc_file(tmp_path, path):
    _has_graph(tmp_path)
    out = _run(_READ_SETTINGS_HOOK, {"file_path": path}, tmp_path)
    assert _nudges(out)


@pytest.mark.parametrize(
    "path",
    [
        "graphify-out/GRAPH_REPORT.md",
        "graphify-out/wiki/index.md",
        "graphify-out/graph.json",
    ],
)
def test_read_hook_silent_on_graphify_out_file(tmp_path, path):
    """Never nudge a Read that is already inside graphify-out/, even though the
    target is a .md/.json the allowlist would otherwise match. Otherwise the agent
    gets told to go read the graph while it is reading the graph."""
    _has_graph(tmp_path)
    out = _run(_READ_SETTINGS_HOOK, {"file_path": path}, tmp_path)
    assert "graphify" not in out


def test_read_hook_silent_on_unknown_extension(tmp_path):
    """The suffix allowlist is closed: an extension that is not source/doc and
    carries no allowlisted substring stays silent."""
    _has_graph(tmp_path)
    out = _run(_READ_SETTINGS_HOOK, {"file_path": "config.yaml"}, tmp_path)
    assert "graphify" not in out


def test_read_hook_silent_on_extensionless_file(tmp_path):
    _has_graph(tmp_path)
    out = _run(_READ_SETTINGS_HOOK, {"file_path": "Makefile"}, tmp_path)
    assert "graphify" not in out


# ---------------------------------------------------------------------------
# Glob coverage (rides the same Read|Glob matcher)
# ---------------------------------------------------------------------------

def test_glob_hook_nudges_with_graph(tmp_path):
    _has_graph(tmp_path)
    out = _run(_READ_SETTINGS_HOOK, {"pattern": "src/**/*.py"}, tmp_path)
    assert "graphify query" in out


def test_glob_hook_silent_without_graph(tmp_path):
    out = _run(_READ_SETTINGS_HOOK, {"pattern": "src/**/*.py"}, tmp_path)
    assert "graphify" not in out


# ---------------------------------------------------------------------------
# Broadened Bash hook — single-file silent vs multi-file/glob nudge
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "command",
    [
        "cat src/app.py",
        "head -n 50 README.md",
        "tail -n 50 server.log",
        "sed -n '1,20p' a.py",
        "cat /etc/hosts",
    ],
)
def test_bash_single_file_read_silent(tmp_path, command):
    _has_graph(tmp_path)
    out = _run(_SETTINGS_HOOK, {"command": command}, tmp_path)
    assert "graphify" not in out


@pytest.mark.parametrize(
    "command",
    [
        "cat src/a.py src/b.py src/c.py",
        "cat a.py b.py",
        "tail -n 20 one.log two.log",
        "sed -n '1,20p' a.py b.py",
    ],
)
def test_bash_multi_file_read_nudges(tmp_path, command):
    _has_graph(tmp_path)
    out = _run(_SETTINGS_HOOK, {"command": command}, tmp_path)
    assert "Before reading multiple source files" in out


@pytest.mark.parametrize(
    "command",
    ["cat src/*.py", "head -n 5 *.md", "cat src/**/*.ts"],
)
def test_bash_glob_read_nudges(tmp_path, command):
    _has_graph(tmp_path)
    out = _run(_SETTINGS_HOOK, {"command": command}, tmp_path)
    assert "Before reading multiple source files" in out


@pytest.mark.parametrize(
    "command",
    [
        "cat a.py b.py > merged.txt",
        "cat > out.txt",
        "cat >> log.txt",
        "cat <<EOF",
        "cat a.py | head",
        "cat graphify-out/GRAPH_REPORT.md",
        "cat graphify-out/a.json graphify-out/b.json",
    ],
)
def test_bash_read_excluded_cases_silent(tmp_path, command):
    """Redirects, heredocs, pipes and graphify-out/ reads never nudge."""
    _has_graph(tmp_path)
    out = _run(_SETTINGS_HOOK, {"command": command}, tmp_path)
    assert "graphify" not in out


# ---------------------------------------------------------------------------
# Regression: the original grep/search behavior must survive the broadening
# ---------------------------------------------------------------------------

def test_bash_grep_still_nudges(tmp_path):
    _has_graph(tmp_path)
    out = _run(_SETTINGS_HOOK, {"command": "grep -r foo src/"}, tmp_path)
    assert "graphify query" in out
    assert "instead of grepping raw files" in out


def test_bash_search_silent_without_graph(tmp_path):
    out = _run(_SETTINGS_HOOK, {"command": "grep -r foo src/"}, tmp_path)
    assert "graphify" not in out


def test_bash_pipe_into_grep_routes_to_search(tmp_path):
    """`cat foo.py | grep bar` is a search (the pipe feeds grep), so it gets the
    search nudge, not suppressed by the content-read pipe exclusion."""
    _has_graph(tmp_path)
    out = _run(_SETTINGS_HOOK, {"command": "cat foo.py | grep bar"}, tmp_path)
    assert "instead of grepping raw files" in out
