"""The Bash PreToolUse guard nudges toward the graph before grep/find searches.

Since #522 it runs as the shell-agnostic `graphify hook-guard search` subcommand
(not inline bash), so it works on Windows too. These tests invoke the subcommand
with crafted stdin JSON and assert it nudges only for a search command when a
graph exists, and otherwise stays silent and fails open.
"""
import json
import os
import subprocess
import sys

from graphify.__main__ import _claude_pretooluse_hooks


def _search_matcher():
    hooks = _claude_pretooluse_hooks()
    return next(h for h in hooks if h["matcher"] == "Bash|Grep")


def _env():
    e = dict(os.environ)
    e.pop("GRAPHIFY_OUT", None)
    return e


def _run(command, cwd, *, graph: bool):
    if graph:
        (cwd / "graphify-out").mkdir(parents=True, exist_ok=True)
        (cwd / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
    stdin = json.dumps({"tool_input": {"command": command}})
    return subprocess.run(
        [sys.executable, "-m", "graphify", "hook-guard", "search"],
        input=stdin, capture_output=True, text=True, cwd=cwd, env=_env(),
    )


def _run_grep_tool(tool_input, cwd, *, graph: bool):
    """Feed a Grep-tool-shaped payload (pattern/path/glob, no command) to the guard."""
    if graph:
        (cwd / "graphify-out").mkdir(parents=True, exist_ok=True)
        (cwd / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
    stdin = json.dumps({"tool_name": "Grep", "tool_input": tool_input})
    return subprocess.run(
        [sys.executable, "-m", "graphify", "hook-guard", "search"],
        input=stdin, capture_output=True, text=True, cwd=cwd, env=_env(),
    )


def test_matcher_targets_bash_and_grep():
    # #1986: content search goes through Claude Code's dedicated Grep tool, so
    # the matcher must cover it alongside Bash.
    assert _search_matcher()["matcher"] == "Bash|Grep"


def test_hook_command_has_no_backslashes(monkeypatch):
    # On Windows the resolved exe is a backslash path; Claude Code runs command
    # hooks through Git Bash by default, which treats an unquoted backslash as an
    # escape character and strips it (C:\Users\me\graphify.EXE -> C:Usersme...),
    # breaking every guard. The emitted command must use forward slashes.
    from graphify.__main__ import _resolve_graphify_exe
    monkeypatch.setattr("shutil.which", lambda _name: r"C:\Users\me\graphify.EXE")
    assert _resolve_graphify_exe() == "C:/Users/me/graphify.EXE"
    for h in _claude_pretooluse_hooks():
        assert "\\" not in h["hooks"][0]["command"]


def test_command_has_no_shell_syntax():
    # #522: no POSIX bash that Windows cmd.exe/PowerShell can't parse.
    cmd = _search_matcher()["hooks"][0]["command"]
    for token in ("$(", "case ", "[ -f", "&&", "||", ";;", "echo '"):
        assert token not in cmd, f"shell syntax {token!r} leaked into the hook"
    assert "graphify" in cmd and "hook-guard search" in cmd


def test_nudges_on_search_commands_with_graph(tmp_path):
    for command in (
        "grep -rn foo .",
        "rg pattern src/",
        "ripgrep thing",
        "find . -name '*.py'",
        "fd bar",
        "ack needle",
        "ag needle",
    ):
        out = _run(command, tmp_path, graph=True).stdout
        assert "graphify query" in out, f"{command!r} should nudge"


def test_silent_without_graph(tmp_path):
    out = _run("grep -rn foo .", tmp_path, graph=False).stdout
    assert out.strip() == ""


def test_silent_on_non_search_commands(tmp_path):
    for command in ("ls -la", "git status", "cat README.md", "python app.py"):
        out = _run(command, tmp_path, graph=True).stdout
        assert out.strip() == "", f"{command!r} should not nudge"


def test_nudge_payload_is_valid_pretooluse_json(tmp_path):
    out = _run("grep -rn foo .", tmp_path, graph=True).stdout
    payload = json.loads(out)
    assert payload["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "graphify query" in payload["hookSpecificOutput"]["additionalContext"]


def test_fails_open_on_malformed_stdin(tmp_path):
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "graphify", "hook-guard", "search"],
        input="not json", capture_output=True, text=True, cwd=tmp_path, env=_env(),
    )
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_never_blocks(tmp_path):
    r = _run("grep -rn foo .", tmp_path, graph=True)
    assert r.returncode == 0
    assert '"permissionDecision"' not in r.stdout
    assert '"deny"' not in r.stdout


def test_honors_graphify_out_override(tmp_path):
    """The guard resolves the graph via GRAPHIFY_OUT, not a hardcoded path."""
    custom = tmp_path / "custom-out"
    custom.mkdir()
    (custom / "graph.json").write_text("{}", encoding="utf-8")
    env = dict(os.environ, GRAPHIFY_OUT=str(custom))
    stdin = json.dumps({"tool_input": {"command": "grep -rn foo ."}})
    r = subprocess.run(
        [sys.executable, "-m", "graphify", "hook-guard", "search"],
        input=stdin, capture_output=True, text=True, cwd=tmp_path, env=env,
    )
    assert "graphify query" in r.stdout


# ---------------------------------------------------------------------------
# #1986: the dedicated Grep tool (pattern/path/glob, no command) must nudge too
# ---------------------------------------------------------------------------


def test_grep_tool_input_nudges_with_graph(tmp_path):
    for tool_input in (
        {"pattern": "extract_corpus", "path": "."},
        {"pattern": "TODO"},
        {"pattern": "def main", "glob": "*.py"},
        {"pattern": "foo", "path": "src/", "glob": "**/*.ts"},
    ):
        out = _run_grep_tool(tool_input, tmp_path, graph=True).stdout
        assert "graphify query" in out, f"Grep input {tool_input!r} should nudge"


def test_grep_tool_input_silent_without_graph(tmp_path):
    out = _run_grep_tool({"pattern": "foo", "path": "."}, tmp_path, graph=False).stdout
    assert out.strip() == ""


def test_grep_tool_nudge_is_valid_pretooluse_json(tmp_path):
    out = _run_grep_tool({"pattern": "foo", "path": "."}, tmp_path, graph=True).stdout
    payload = json.loads(out)
    assert payload["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "graphify query" in payload["hookSpecificOutput"]["additionalContext"]


def test_grep_tool_never_blocks(tmp_path):
    r = _run_grep_tool({"pattern": "foo", "path": "."}, tmp_path, graph=True)
    assert r.returncode == 0
    assert '"permissionDecision"' not in r.stdout
    assert '"deny"' not in r.stdout


def test_bash_non_search_with_stray_pattern_key_does_not_nudge(tmp_path):
    """A Bash tool_input carries `command`; the Grep-shape detection must not
    fire when a command is present but is not a search."""
    (tmp_path / "graphify-out").mkdir(parents=True, exist_ok=True)
    (tmp_path / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
    stdin = json.dumps({"tool_input": {"command": "ls -la", "pattern": "x"}})
    r = subprocess.run(
        [sys.executable, "-m", "graphify", "hook-guard", "search"],
        input=stdin, capture_output=True, text=True, cwd=tmp_path, env=_env(),
    )
    assert r.stdout.strip() == ""
