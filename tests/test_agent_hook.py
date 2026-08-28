"""The Task/Agent PreToolUse guard nudges subagent spawns toward the graph (#2145).

Most code exploration happens inside spawned subagents (`Task`/`Agent`), which the
Bash|Grep and Read|Glob guards never see — the parent spawns an "Explore" agent and
that agent never sees the guard. The `graphify hook-guard agent` subcommand, wired
to matcher "Task|Agent", nudges the spawn to carry graphify orientation when a graph
exists, unless the prompt is already graphify-aware. It never blocks a spawn.
"""
import json
import os
import subprocess
import sys

from graphify.__main__ import _claude_pretooluse_hooks


def _agent_matcher():
    hooks = _claude_pretooluse_hooks()
    return next(h for h in hooks if h["matcher"] == "Task|Agent")


def _env():
    e = dict(os.environ)
    e.pop("GRAPHIFY_OUT", None)
    return e


def _run(tool_input, cwd, *, graph: bool, tool_name="Task"):
    if graph:
        (cwd / "graphify-out").mkdir(parents=True, exist_ok=True)
        (cwd / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
    stdin = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    return subprocess.run(
        [sys.executable, "-m", "graphify", "hook-guard", "agent"],
        input=stdin, capture_output=True, text=True, cwd=cwd, env=_env(),
    )


def test_matcher_targets_task_and_agent():
    assert _agent_matcher()["matcher"] == "Task|Agent"


def test_command_is_hook_guard_agent():
    cmd = _agent_matcher()["hooks"][0]["command"]
    assert "graphify" in cmd and "hook-guard agent" in cmd


def test_command_has_no_shell_syntax_or_backslashes(monkeypatch):
    from graphify.__main__ import _resolve_graphify_exe
    monkeypatch.setattr("shutil.which", lambda _name: r"C:\Users\me\graphify.EXE")
    assert _resolve_graphify_exe() == "C:/Users/me/graphify.EXE"
    cmd = next(h for h in _claude_pretooluse_hooks()
               if h["matcher"] == "Task|Agent")["hooks"][0]["command"]
    assert "\\" not in cmd
    for token in ("$(", "case ", "[ -f", "&&", "||", ";;", "echo '"):
        assert token not in cmd


def test_nudges_on_exploration_spawn_with_graph(tmp_path):
    for tool_input in (
        {"prompt": "find all callers of PaymentService"},
        {"description": "explore auth", "prompt": "trace how login works across files"},
        {"prompt": "Where is the retry logic implemented?"},
    ):
        out = _run(tool_input, tmp_path, graph=True).stdout
        assert "graphify query" in out, f"{tool_input!r} should nudge"


def test_silent_without_graph(tmp_path):
    out = _run({"prompt": "find all callers of X"}, tmp_path, graph=False).stdout
    assert out.strip() == ""


def test_silent_when_prompt_already_graphify_aware(tmp_path):
    for tool_input in (
        {"prompt": "Use `graphify query` to map the module, then summarize"},
        {"prompt": "Given these Connections (12) from the graph, refactor X"},
        {"prompt": "The [EXTRACTED] edges show a cycle; propose a fix"},
    ):
        out = _run(tool_input, tmp_path, graph=True).stdout
        assert out.strip() == "", f"{tool_input!r} already oriented; should stay quiet"


def test_silent_on_empty_brief(tmp_path):
    out = _run({"prompt": ""}, tmp_path, graph=True).stdout
    assert out.strip() == ""


def test_nudge_payload_is_valid_pretooluse_json(tmp_path):
    out = _run({"prompt": "find callers of X"}, tmp_path, graph=True).stdout
    payload = json.loads(out)
    assert payload["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "graphify" in payload["hookSpecificOutput"]["additionalContext"]


def test_never_blocks_a_spawn(tmp_path):
    r = _run({"prompt": "find callers of X"}, tmp_path, graph=True)
    assert r.returncode == 0
    assert '"permissionDecision"' not in r.stdout
    assert '"deny"' not in r.stdout


def test_fails_open_on_malformed_stdin(tmp_path):
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "graphify", "hook-guard", "agent"],
        input="not json", capture_output=True, text=True, cwd=tmp_path, env=_env(),
    )
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_uninstall_filter_removes_our_hook_but_keeps_foreign(tmp_path):
    # The uninstall/reinstall filter must strip graphify's own Task|Agent hook
    # while preserving an unrelated Task|Agent hook another tool installed.
    matcher_tuple = ("Glob|Grep", "Bash", "Bash|Grep", "Read|Glob", "Task|Agent")
    pre_tool = [
        {"matcher": "Task|Agent",
         "hooks": [{"type": "command", "command": "/x/graphify hook-guard agent"}]},
        {"matcher": "Task|Agent",
         "hooks": [{"type": "command", "command": "some-other-tool run"}]},
    ]
    filtered = [h for h in pre_tool
                if not (h.get("matcher") in matcher_tuple and "graphify" in str(h))]
    kept = [h["hooks"][0]["command"] for h in filtered]
    assert kept == ["some-other-tool run"]
