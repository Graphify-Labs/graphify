"""Grok Build PreToolUse hooks.

`graphify grok install` registers Claude Code's `graphify hook-guard` entries in
``.grok/hooks/graphify.json``, installed the way the Codex hook is installed
(``.codex/hooks.json``). Grok sends the hook event with camelCase keys and its
own tool names, so the guard reads those when the snake_case keys are absent.

The payloads below follow Grok Build's documented hook input schema. They were
not captured from a live session:
- Envelope: https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/10-hooks.md#input
  (``hookEventName``, ``hook_event_name``, ``sessionId``, ``cwd``,
  ``workspaceRoot``, ``toolName``, ``toolInput``, ``toolUseId``, ...).
- Tool input field names (``path``, ``command``, ``pattern``):
  https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-tools/src/tool_taxonomy.rs
- Matcher aliases (Bash -> run_terminal_command, Read -> read_file, Grep -> grep,
  Glob -> list_dir) and CLAUDE_PROJECT_DIR being set for every hook: the same
  10-hooks.md, "Tool Name Aliases" and "Environment Variables".
"""
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import graphify.cli as cli
import graphify.install as install


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    # Tests must not depend on the contributor's shell (CONTRIBUTING #11).
    for k in ("CLAUDE_PROJECT_DIR", "GRAPHIFY_HOOK_STRICT", "GRAPHIFY_HOOK_STRICT_TTL",
              "GRAPHIFY_OUT", "GROK_HOME"):
        monkeypatch.delenv(k, raising=False)


def _grok_event(tool_name, tool_input, root, sid="0b8f3c1e-sess"):
    """A Grok Build PreToolUse event as documented (10-hooks.md, "Input")."""
    return {
        "hookEventName": "pre_tool_use",
        "hook_event_name": "PreToolUse",
        "sessionId": sid,
        "cwd": str(root),
        "workspaceRoot": str(root),
        "permissionMode": "default",
        "toolName": tool_name,
        "toolInput": tool_input,
        "toolUseId": "call-0001",
        "toolInputTruncated": False,
        "timestamp": "2026-10-03T00:00:00Z",
    }


def _project(tmp_path, *, indexed=True, graph=True):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    f = src / "a.py"
    f.write_text("def foo():\n    return 1\n", encoding="utf-8")
    out = tmp_path / "graphify-out"
    out.mkdir(exist_ok=True)
    (out / "manifest.json").write_text(
        json.dumps({"src/a.py": {"mtime": 1}} if indexed else {"other/z.py": {"mtime": 1}}),
        encoding="utf-8",
    )
    if graph:
        time.sleep(0.02)
        (out / "graph.json").write_text('{"nodes":[],"links":[]}', encoding="utf-8")
    return f


def _invoke(kind, payload, tmp_path, monkeypatch, *, strict=False, env=None):
    monkeypatch.chdir(tmp_path)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    data = json.dumps(payload).encode() if not isinstance(payload, (bytes, bytearray)) else bytes(payload)

    class _Stdin:
        buffer = io.BytesIO(data)
    monkeypatch.setattr(sys, "stdin", _Stdin())
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    cli._run_hook_guard(kind, strict=strict)
    return buf.getvalue()


def _decision(out):
    return json.loads(out).get("hookSpecificOutput", {}).get("permissionDecision") if out.strip() else None


# --- search (matcher Bash|Grep -> run_terminal_command, grep) --------------------


def test_grok_shell_search_nudges(tmp_path, monkeypatch):
    _project(tmp_path)
    p = _grok_event("run_terminal_command", {"command": "grep -r foo ."}, tmp_path)
    assert _invoke("search", p, tmp_path, monkeypatch) == cli._SEARCH_NUDGE


def test_grok_grep_tool_nudges(tmp_path, monkeypatch):
    _project(tmp_path)
    p = _grok_event("grep", {"pattern": "foo", "path": "."}, tmp_path)
    assert _invoke("search", p, tmp_path, monkeypatch) == cli._SEARCH_NUDGE


def test_grok_search_silent_without_graph(tmp_path, monkeypatch):
    _project(tmp_path, graph=False)
    p = _grok_event("run_terminal_command", {"command": "grep -r foo ."}, tmp_path)
    assert _invoke("search", p, tmp_path, monkeypatch) == ""


def test_grok_non_search_command_is_silent(tmp_path, monkeypatch):
    _project(tmp_path)
    p = _grok_event("run_terminal_command", {"command": 'git commit -m "add flag support"'}, tmp_path)
    assert _invoke("search", p, tmp_path, monkeypatch) == ""


# --- read (matcher Read|Glob -> read_file, list_dir) -----------------------------


def test_grok_read_file_relative_path_nudges(tmp_path, monkeypatch):
    _project(tmp_path)
    p = _grok_event("read_file", {"path": "src/a.py"}, tmp_path)
    assert _invoke("read", p, tmp_path, monkeypatch) == cli._READ_NUDGE


def test_grok_read_file_outside_project_is_ignored(tmp_path, monkeypatch):
    # Grok sets CLAUDE_PROJECT_DIR (= workspace root) for every hook.
    _project(tmp_path)
    other = tmp_path.parent / (tmp_path.name + "-other")
    other.mkdir()
    (other / "z.py").write_text("x = 1\n", encoding="utf-8")
    p = _grok_event("read_file", {"path": str(other / "z.py")}, tmp_path)
    out = _invoke("read", p, tmp_path, monkeypatch, env={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert out == ""


def test_grok_list_dir_of_a_directory_is_silent(tmp_path, monkeypatch):
    _project(tmp_path)
    p = _grok_event("list_dir", {"path": "src"}, tmp_path)
    assert _invoke("read", p, tmp_path, monkeypatch) == ""


def test_grok_read_file_stale_target_softens(tmp_path, monkeypatch):
    f = _project(tmp_path)
    time.sleep(0.02)
    f.write_text("def foo():\n    return 2\n", encoding="utf-8")
    p = _grok_event("read_file", {"path": str(f)}, tmp_path)
    assert _invoke("read", p, tmp_path, monkeypatch, strict=True) == cli._READ_NUDGE_STALE


def test_grok_strict_denies_once_per_session(tmp_path, monkeypatch):
    _project(tmp_path)
    p = _grok_event("read_file", {"path": "src/a.py"}, tmp_path, sid="grok-s1")
    first = _invoke("read", p, tmp_path, monkeypatch, env={"GRAPHIFY_HOOK_STRICT": "1"})
    assert first == cli._READ_DENY and _decision(first) == "deny"
    assert (tmp_path / "graphify-out" / "cache" / "hook_sessions" / "grok-s1.denied").exists()
    assert _invoke("read", p, tmp_path, monkeypatch, env={"GRAPHIFY_HOOK_STRICT": "1"}) == cli._READ_NUDGE
    other = _grok_event("read_file", {"path": "src/a.py"}, tmp_path, sid="grok-s2")
    assert _decision(_invoke("read", other, tmp_path, monkeypatch, strict=True)) == "deny"


def test_grok_strict_empty_session_id_fails_open(tmp_path, monkeypatch):
    _project(tmp_path)
    p = _grok_event("read_file", {"path": "src/a.py"}, tmp_path, sid="")
    assert _invoke("read", p, tmp_path, monkeypatch, strict=True) == cli._READ_NUDGE


def test_grok_strict_marker_write_failure_fails_open(tmp_path, monkeypatch):
    _project(tmp_path)
    p = _grok_event("read_file", {"path": "src/a.py"}, tmp_path)

    def _boom(*a, **k):
        raise PermissionError("read-only filesystem")
    monkeypatch.setattr(cli.os, "open", _boom)
    assert _invoke("read", p, tmp_path, monkeypatch, strict=True) == cli._READ_NUDGE


@pytest.mark.parametrize("raw", [b"not json", b"[]", b"", json.dumps(
    {"toolName": "read_file", "toolInput": "src/a.py", "sessionId": "s"}).encode()])
def test_grok_malformed_payload_is_silent(tmp_path, monkeypatch, raw):
    _project(tmp_path)
    assert _invoke("read", raw, tmp_path, monkeypatch, strict=True) == ""
    assert _invoke("search", raw, tmp_path, monkeypatch) == ""


def test_grok_payload_through_cli_exits_zero(tmp_path):
    _project(tmp_path)
    p = json.dumps(_grok_event("run_terminal_command", {"command": "rg foo"}, tmp_path)).encode()
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "GRAPHIFY_OUT")}
    r = subprocess.run([sys.executable, "-m", "graphify", "hook-guard", "search"],
                       input=p, cwd=tmp_path, env=env, capture_output=True, timeout=60)
    assert r.returncode == 0
    assert json.loads(r.stdout) == json.loads(cli._SEARCH_NUDGE)


# --- Claude Code path unchanged --------------------------------------------------


def test_claude_payload_unchanged(tmp_path, monkeypatch):
    f = _project(tmp_path)
    claude = {"session_id": "c1", "tool_name": "Read", "tool_input": {"file_path": str(f)}}
    assert _invoke("read", claude, tmp_path, monkeypatch, strict=True) == cli._READ_DENY
    bash = {"tool_name": "Bash", "tool_input": {"command": "rg foo"}}
    assert _invoke("search", bash, tmp_path, monkeypatch) == cli._SEARCH_NUDGE


def test_snake_case_keys_win_over_camel_case(tmp_path, monkeypatch):
    _project(tmp_path)
    mixed = {"tool_name": "Bash", "tool_input": {"command": "ls"},
             "toolName": "run_terminal_command", "toolInput": {"command": "grep -r foo ."}}
    assert _invoke("search", mixed, tmp_path, monkeypatch) == ""


# --- .grok/hooks/graphify.json (installed like .codex/hooks.json) ----------------


def _hooks_file(root):
    return root / ".grok" / "hooks" / "graphify.json"


def _run(cwd, argv, home):
    import graphify.__main__ as mainmod
    old = Path.cwd()
    try:
        os.chdir(cwd)
        with patch.object(sys, "argv", ["graphify", *argv]):
            with patch("graphify.__main__.Path.home", return_value=home):
                mainmod.main()
    finally:
        os.chdir(old)


def _dirs(tmp_path):
    home, cwd = tmp_path / "home", tmp_path / "proj"
    home.mkdir()
    cwd.mkdir()
    return home, cwd


def test_grok_install_registers_claude_hook_entries(tmp_path, capsys):
    home, cwd = _dirs(tmp_path)
    _run(cwd, ["grok", "install"], home)
    data = json.loads(_hooks_file(cwd).read_text(encoding="utf-8"))
    # Exactly Claude Code's entries (matchers Bash|Grep and Read|Glob, hook-guard,
    # timeout 10); a user-scope install resolves the exe like the Codex hook does.
    assert data["hooks"]["PreToolUse"] == install._claude_pretooluse_hooks(project=False)
    assert ".grok/hooks/graphify.json" in capsys.readouterr().out


def test_grok_install_project_uses_bare_command(tmp_path):
    home, cwd = _dirs(tmp_path)
    _run(cwd, ["grok", "install", "--project"], home)
    groups = json.loads(_hooks_file(cwd).read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert [g["matcher"] for g in groups] == ["Bash|Grep", "Read|Glob"]
    assert [g["hooks"][0]["command"] for g in groups] == [
        "graphify hook-guard search", "graphify hook-guard read"]


def test_grok_hook_install_is_idempotent_and_keeps_user_hooks(tmp_path):
    _hooks_file(tmp_path).parent.mkdir(parents=True)
    mine = {"matcher": "search_replace", "hooks": [{"type": "command", "command": "echo mine"}]}
    _hooks_file(tmp_path).write_text(json.dumps({"hooks": {"PreToolUse": [mine]}}), encoding="utf-8")
    install._install_grok_hook(tmp_path, project=True)
    first = _hooks_file(tmp_path).read_text(encoding="utf-8")
    install._install_grok_hook(tmp_path, project=True)
    assert _hooks_file(tmp_path).read_text(encoding="utf-8") == first
    groups = json.loads(first)["hooks"]["PreToolUse"]
    assert groups[0] == mine and len(groups) == 3
    install._uninstall_grok_hook(tmp_path)
    assert json.loads(_hooks_file(tmp_path).read_text(encoding="utf-8"))["hooks"]["PreToolUse"] == [mine]


def test_grok_hook_install_refuses_malformed_file(tmp_path):
    _hooks_file(tmp_path).parent.mkdir(parents=True)
    _hooks_file(tmp_path).write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit):
        install._install_grok_hook(tmp_path, project=True)
    assert _hooks_file(tmp_path).read_text(encoding="utf-8") == "{not json"


def test_grok_hook_command_quotes_exe_with_space(monkeypatch, tmp_path):
    monkeypatch.setattr(install, "_resolve_graphify_exe",
                        lambda project=False: "C:/Program Files/Python/Scripts/graphify.exe")
    install._install_grok_hook(tmp_path)
    groups = json.loads(_hooks_file(tmp_path).read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert groups[0]["hooks"][0]["command"] == \
        '"C:/Program Files/Python/Scripts/graphify.exe" hook-guard search'


def test_grok_uninstall_removes_hook_file_and_prunes(tmp_path):
    home, cwd = _dirs(tmp_path)
    _run(cwd, ["grok", "install"], home)
    _run(cwd, ["grok", "uninstall"], home)
    assert not (cwd / ".grok").exists()


def test_grok_reinstall_backup_is_cleaned_on_uninstall(tmp_path):
    # User-scope then --project install rewrites the file (absolute exe -> bare
    # command), leaving graphify.json.graphify-bak; uninstall must not strand it.
    home, cwd = _dirs(tmp_path)
    _run(cwd, ["grok", "install"], home)
    _run(cwd, ["grok", "install", "--project"], home)
    assert (cwd / ".grok" / "hooks" / "graphify.json.graphify-bak").exists()
    _run(cwd, ["grok", "uninstall", "--project"], home)
    assert not (cwd / ".grok").exists()


def test_grok_uninstall_keeps_backup_holding_user_hooks(tmp_path):
    hooks_dir = tmp_path / ".grok" / "hooks"
    hooks_dir.mkdir(parents=True)
    mine = {"matcher": "search_replace", "hooks": [{"type": "command", "command": "echo mine"}]}
    (hooks_dir / "graphify.json.graphify-bak").write_text(
        json.dumps({"hooks": {"PreToolUse": [mine]}}), encoding="utf-8")
    install._install_grok_hook(tmp_path, project=True)
    install._uninstall_grok_hook(tmp_path)
    assert not _hooks_file(tmp_path).exists()
    assert (hooks_dir / "graphify.json.graphify-bak").exists()


def test_grok_project_uninstall_removes_hook_file(tmp_path):
    home, cwd = _dirs(tmp_path)
    _run(cwd, ["grok", "install", "--project"], home)
    _run(cwd, ["grok", "uninstall", "--project"], home)
    assert not (cwd / ".grok").exists()


def test_bare_uninstall_removes_grok_hook(tmp_path):
    home, cwd = _dirs(tmp_path)
    _run(cwd, ["grok", "install"], home)
    _run(cwd, ["uninstall"], home)
    assert not _hooks_file(cwd).exists()


def test_install_platform_grok_stays_skill_only(tmp_path):
    home, cwd = _dirs(tmp_path)
    _run(cwd, ["install", "--platform", "grok"], home)
    assert not (cwd / ".grok").exists()
