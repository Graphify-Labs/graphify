"""`hook-guard agy`: Google Antigravity CLI PreToolUse/PreInvocation gate.

Headless `agy -p` loads global rules but treats them as advice (measured: sonnet-4-6 and
gpt-oss-120b both grep first with an always-on graph rule active), and it sends
`workspacePaths: []`, so the gate derives the workspace from the tool call's own target
path. A recursive corpus search is denied until this conversation has called the
graphify MCP server through `call_mcp_tool`; the way out is the query. Payload keys are
camelCase (protojson). Fails open on anything unexpected.
"""
import io
import json
import os
import subprocess
import sys
import time

import graphify.cli as cli
import graphify.install as install


def _ws(tmp_path):
    ws = tmp_path / "ws"
    (ws / "src").mkdir(parents=True)
    (ws / "src" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (ws / "graphify-out").mkdir()
    (ws / "graphify-out" / "graph.json").write_text('{"nodes":[],"links":[]}', encoding="utf-8")
    return ws


def _home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def _invoke(payload, tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)  # never the workspace: agy runs hooks from the hooks.json dir
    data = json.dumps(payload).encode() if not isinstance(payload, (bytes, bytearray)) else bytes(payload)

    class _Stdin:
        buffer = io.BytesIO(data)
    monkeypatch.setattr(sys, "stdin", _Stdin())
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    cli._run_hook_guard("agy")
    return json.loads(buf.getvalue() or "{}")


def _tool(name, args=None, conv="c1", ws=None):
    return {"conversationId": conv, "workspacePaths": [str(ws)] if ws else [],
            "toolCall": {"name": name, "args": args or {}}}


def test_search_in_graph_tree_denies_until_graphify_mcp_call(tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    out = _invoke(_tool("grep_search", {"Query": "x", "SearchPath": str(ws / "src")}), tmp_path, monkeypatch)
    assert out["decision"] == "deny" and "call_mcp_tool" in out["reason"]
    assert _invoke(_tool("find_by_name", {"Pattern": "*", "SearchDirectory": str(ws)}), tmp_path, monkeypatch)["decision"] == "deny"
    assert _invoke(_tool("list_dir", {"DirectoryPath": str(ws)}), tmp_path, monkeypatch)["decision"] == "deny"
    # second attempt is denied again: not once-per-session
    assert _invoke(_tool("grep_search", {"Query": "x", "SearchPath": str(ws)}), tmp_path, monkeypatch)["decision"] == "deny"
    assert _invoke(_tool("call_mcp_tool", {"ServerName": "graphify", "ToolName": "query_graph"}), tmp_path, monkeypatch)["decision"] == "allow"
    assert _invoke(_tool("grep_search", {"Query": "x", "SearchPath": str(ws)}), tmp_path, monkeypatch)["decision"] == "allow"


def test_run_command_recursive_search_denies_bounded_allows(tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    w = str(ws)
    for cmd in (
        f'powershell -NoProfile -Command "Get-ChildItem -Path \'{w}\' -Recurse -Include *.md | Select-String -Pattern x"',
        f'rg -n "x" "{w}" -l',
        f'Select-String -Path "{w}\\*.md" -Pattern x',
        f'grep -rn x "{w}"',
    ):
        out = _invoke(_tool("run_command", {"CommandLine": cmd}), tmp_path, monkeypatch)
        assert out["decision"] == "deny", cmd
    # Cwd carries the workspace when the command uses a relative path
    assert _invoke(_tool("run_command", {"CommandLine": "grep -rn x .", "Cwd": w}), tmp_path, monkeypatch)["decision"] == "deny"
    for cmd in (f'grep -n x "{w}\\src\\mod.py"', f'Get-Content "{w}\\src\\mod.py" | Select-String x', "git status"):
        assert _invoke(_tool("run_command", {"CommandLine": cmd, "Cwd": w}), tmp_path, monkeypatch)["decision"] == "allow", cmd


def test_workspace_paths_used_when_present(tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    assert _invoke(_tool("grep_search", {"Query": "x"}, ws=ws), tmp_path, monkeypatch)["decision"] == "deny"


def test_conversations_are_isolated_and_other_servers_do_not_mark(tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    _invoke(_tool("call_mcp_tool", {"ServerName": "graphify", "ToolName": "query_graph"}, conv="a"), tmp_path, monkeypatch)
    assert _invoke(_tool("grep_search", {"Query": "x", "SearchPath": str(ws)}, conv="a"), tmp_path, monkeypatch)["decision"] == "allow"
    assert _invoke(_tool("grep_search", {"Query": "x", "SearchPath": str(ws)}, conv="b"), tmp_path, monkeypatch)["decision"] == "deny"
    _invoke(_tool("call_mcp_tool", {"ServerName": "code-review-graph", "ToolName": "x"}, conv="b"), tmp_path, monkeypatch)
    assert _invoke(_tool("grep_search", {"Query": "x", "SearchPath": str(ws)}, conv="b"), tmp_path, monkeypatch)["decision"] == "deny"


def test_expired_marker_does_not_authorize(tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    home = _home(tmp_path, monkeypatch)
    d = home / ".graphify" / "agy_sessions"
    d.mkdir(parents=True)
    old = d / "stale.queried"
    old.write_text("", encoding="utf-8")
    os.utime(old, (time.time() - 90000, time.time() - 90000))
    assert _invoke(_tool("grep_search", {"Query": "x", "SearchPath": str(ws)}, conv="stale"), tmp_path, monkeypatch)["decision"] == "deny"


def test_safety_valves_allow(tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    nograph = tmp_path / "plain"
    nograph.mkdir()
    assert _invoke(_tool("grep_search", {"Query": "x", "SearchPath": str(nograph)}), tmp_path, monkeypatch)["decision"] == "allow"
    assert _invoke(_tool("grep_search", {"Query": "x"}), tmp_path, monkeypatch)["decision"] == "allow"  # no path, no workspace
    assert _invoke(_tool("view_file", {"AbsolutePath": str(ws / "src" / "mod.py")}), tmp_path, monkeypatch)["decision"] == "allow"
    assert _invoke({"workspacePaths": [], "toolCall": {"name": "grep_search", "args": {"SearchPath": str(ws)}}}, tmp_path, monkeypatch)["decision"] == "allow"  # no conversationId
    assert _invoke(b"{not json", tmp_path, monkeypatch)["decision"] == "allow"


def test_preinvocation_injects_only_with_known_workspace_and_no_marker(tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    out = _invoke({"conversationId": "p1", "workspacePaths": [str(ws)], "invocationNum": 1, "initialNumSteps": 0}, tmp_path, monkeypatch)
    assert out["injectSteps"] and "call_mcp_tool" in out["injectSteps"][0]["ephemeralMessage"] and "decision" not in out
    _invoke(_tool("call_mcp_tool", {"ServerName": "graphify", "ToolName": "query_graph"}, conv="p1"), tmp_path, monkeypatch)
    assert _invoke({"conversationId": "p1", "workspacePaths": [str(ws)], "invocationNum": 2, "initialNumSteps": 3}, tmp_path, monkeypatch) == {}
    assert _invoke({"conversationId": "p2", "workspacePaths": [], "invocationNum": 1, "initialNumSteps": 0}, tmp_path, monkeypatch) == {}


def test_reason_is_constant_never_echoes_command(tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    out = _invoke(_tool("run_command", {"CommandLine": f'rg "$(rm -rf /)" "{ws}"'}), tmp_path, monkeypatch)
    assert out["decision"] == "deny" and "rm -rf" not in json.dumps(out)


def test_installed_command_executes(tmp_path, monkeypatch):
    """The generated command runs end to end through a shell, as agy runs it (cmd /c on Windows)."""
    ws = _ws(tmp_path)
    home = _home(tmp_path, monkeypatch)
    hooks = install._antigravity_hooks_json_entry()
    command = hooks["PreToolUse"][0]["hooks"][0]["command"]
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home))
    payload = json.dumps(_tool("grep_search", {"Query": "x", "SearchPath": str(ws)}, conv="installed"))
    result = subprocess.run(command, input=payload, text=True, capture_output=True, shell=True, cwd=tmp_path, timeout=30, env=env)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["decision"] == "deny", result.stdout or result.stderr
    assert '"' not in command.split(" -File ")[-1] if " -File " in command else True


def test_antigravity_install_strict_merges_hooks_json_and_uninstall_removes(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    cfg = home / ".gemini" / "config"
    cfg.mkdir(parents=True)
    hooks_path = cfg / "hooks.json"
    hooks_path.write_text(json.dumps({"my-linter": {"PostToolUse": [{"matcher": "run_command", "hooks": [{"command": "lint"}]}]}}), encoding="utf-8")
    install._antigravity_install(tmp_path, strict=True)
    data = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert "my-linter" in data, "a user's own hook must survive"
    entry = data["graphify-graph-first"]
    assert entry["PreToolUse"][0]["matcher"] == "grep_search|find_by_name|list_dir|run_command|call_mcp_tool"
    assert "hook-guard agy" in entry["PreToolUse"][0]["hooks"][0]["command"]
    assert "hook-guard agy" in entry["PreInvocation"][0]["command"]
    install._antigravity_install(tmp_path, strict=True)  # idempotent
    assert list(json.loads(hooks_path.read_text(encoding="utf-8")).keys()).count("graphify-graph-first") == 1
    install._antigravity_uninstall(tmp_path)
    data = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert "graphify-graph-first" not in data and "my-linter" in data


def test_antigravity_install_without_strict_writes_no_hooks(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    install._antigravity_install(tmp_path)
    assert not (home / ".gemini" / "config" / "hooks.json").exists()
