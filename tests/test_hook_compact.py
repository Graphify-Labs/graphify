"""The nudge budget comes back after a Claude Code context compaction.

_nudge_allowed counts nudges per session (and per subagent) and stops at
GRAPHIFY_HOOK_NUDGE_CAP (#3435). Compaction keeps the session id but drops the
earlier nudges from the model's context, so with the budget spent the rest of a
long session never heard about the graph again. Claude Code fires SessionStart
with source "compact" after compaction; graphify installs a SessionStart hook
with matcher "compact" that runs `graphify hook-guard compact`, which resets the
session's counters, its subagents' counters and the strict-mode deny marker.

The guard is driven the way Claude Code drives it: a subprocess with the hook
JSON on stdin.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest

from graphify import install as install_mod

SID = "9f1c2d3e-4b5a-6789-abcd-ef0123456789"


def _project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "mod.py"
    f.write_text("def x():\n    return 1\n", encoding="utf-8")
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "manifest.json").write_text(json.dumps({"src/mod.py": {"mtime": 1}}), encoding="utf-8")
    time.sleep(0.02)
    (out / "graph.json").write_text('{"nodes":[],"links":[]}', encoding="utf-8")
    return f


def _env(tmp_path):
    e = dict(os.environ)
    for k in ("GRAPHIFY_OUT", "GRAPHIFY_HOOK_STRICT", "GRAPHIFY_HOOK_NUDGE_CAP", "GRAPHIFY_HOOK_STRICT_TTL"):
        e.pop(k, None)
    e["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    return e


def _guard(kind, payload, tmp_path, *, strict=False):
    args = [sys.executable, "-m", "graphify", "hook-guard", kind] + (["--strict"] if strict else [])
    data = payload if isinstance(payload, str) else json.dumps(payload)
    r = subprocess.run(args, input=data, capture_output=True, text=True, cwd=tmp_path, env=_env(tmp_path))
    assert r.returncode == 0, r.stderr
    return r.stdout


def _read(f, tmp_path, *, sid=SID, agent=None, strict=False):
    payload = {
        "session_id": sid,
        "transcript_path": f"/home/u/.claude/projects/p/{sid}.jsonl",
        "cwd": str(tmp_path),
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": str(f)},
        "tool_use_id": "toolu_01",
    }
    if agent:
        payload["agent_id"] = agent
        payload["agent_type"] = "Explore"
    return _guard("read", payload, tmp_path, strict=strict)


def _session_start(source, tmp_path, *, sid=SID):
    return _guard("compact", {
        "session_id": sid,
        "transcript_path": f"/home/u/.claude/projects/p/{sid}.jsonl",
        "cwd": str(tmp_path),
        "hook_event_name": "SessionStart",
        "source": source,
        "model": "claude-opus-4-1",
    }, tmp_path)


def _kind(out):
    if not out.strip():
        return "silent"
    hso = json.loads(out)["hookSpecificOutput"]
    return "deny" if hso.get("permissionDecision") == "deny" else "nudge"


def _markers(tmp_path):
    d = tmp_path / "graphify-out" / "cache" / "hook_sessions"
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


def test_compact_restores_the_nudge_budget_for_session_and_subagent(tmp_path):
    f = _project(tmp_path)
    assert [_kind(_read(f, tmp_path)) for _ in range(5)] == ["nudge"] * 5
    assert _kind(_read(f, tmp_path)) == "silent", "cap of 5 reached"
    assert [_kind(_read(f, tmp_path, agent="a1")) for _ in range(5)] == ["nudge"] * 5
    assert _kind(_read(f, tmp_path, agent="a1")) == "silent", "subagent cap reached"
    # Another session's spent budget must survive this session's compaction.
    other = "11111111-2222-3333-4444-555555555555"
    for _ in range(5):
        _read(f, tmp_path, sid=other)
    assert _kind(_read(f, tmp_path, sid=other)) == "silent"

    out = _session_start("compact", tmp_path)
    hso = json.loads(out)["hookSpecificOutput"]
    assert hso["hookEventName"] == "SessionStart"
    assert "graphify query" in hso["additionalContext"]
    assert set(hso) == {"hookEventName", "additionalContext"}

    assert _kind(_read(f, tmp_path)) == "nudge", "budget back after compaction"
    assert _kind(_read(f, tmp_path, agent="a1")) == "nudge", "subagent budget back too"
    assert _kind(_read(f, tmp_path, sid=other)) == "silent", "other session untouched"


def test_compact_rearms_the_strict_deny(tmp_path):
    f = _project(tmp_path)
    assert _kind(_read(f, tmp_path, strict=True)) == "deny"
    assert _kind(_read(f, tmp_path, strict=True)) == "nudge", "deny fires once per session"
    assert f"{SID}.denied" in _markers(tmp_path)
    _session_start("compact", tmp_path)
    assert f"{SID}.denied" not in _markers(tmp_path)
    assert _kind(_read(f, tmp_path, strict=True)) == "deny", "strict redirects once more"
    assert _kind(_read(f, tmp_path, strict=True)) == "nudge"


@pytest.mark.parametrize("source", ["startup", "resume", "clear", "fork", None])
def test_other_session_start_sources_do_not_reset(source, tmp_path):
    f = _project(tmp_path)
    assert _kind(_read(f, tmp_path, strict=True)) == "deny"
    for _ in range(5):
        _read(f, tmp_path, strict=True)
    _read(f, tmp_path, agent="a1")
    before = _markers(tmp_path)
    payload = {"session_id": SID, "hook_event_name": "SessionStart", "cwd": str(tmp_path)}
    if source is not None:
        payload["source"] = source
    assert _guard("compact", payload, tmp_path) == ""
    assert _markers(tmp_path) == before
    assert _kind(_read(f, tmp_path, strict=True)) == "silent"
    # Control: the same session does get its budget back on "compact".
    _session_start("compact", tmp_path)
    assert _kind(_read(f, tmp_path, strict=True)) == "deny"


def test_compact_on_another_event_does_nothing(tmp_path):
    f = _project(tmp_path)
    for _ in range(6):
        _read(f, tmp_path)
    before = _markers(tmp_path)
    out = _guard("compact", {"session_id": SID, "hook_event_name": "PreCompact", "source": "compact"}, tmp_path)
    assert out == "" and _markers(tmp_path) == before
    _session_start("compact", tmp_path)  # control: the real event resets
    assert _kind(_read(f, tmp_path)) == "nudge"


def test_compact_without_markers_or_graph_is_quiet(tmp_path):
    # No graph: nothing to restate. No markers: nothing to delete. Never an error.
    assert _session_start("compact", tmp_path) == ""
    _project(tmp_path)
    assert _kind(_session_start("compact", tmp_path)) == "nudge"


@pytest.mark.parametrize("stdin", ["", "not json", "[]", '"compact"', '{"source": ["compact"]}'])
def test_compact_fails_open_on_bad_input(stdin, tmp_path):
    f = _project(tmp_path)
    for _ in range(6):
        _read(f, tmp_path)
    before = _markers(tmp_path)
    assert _guard("compact", stdin, tmp_path) == ""
    assert _markers(tmp_path) == before
    _session_start("compact", tmp_path)  # control: valid input still resets
    assert _kind(_read(f, tmp_path)) == "nudge"


def test_compact_fails_open_when_the_reset_raises(tmp_path, monkeypatch):
    # Root ignores file permissions, so force the error in-process.
    import io
    import graphify.cli as cli
    f = _project(tmp_path)
    _read(f, tmp_path)
    monkeypatch.chdir(tmp_path)

    def boom(*_a, **_k):
        raise PermissionError("denied")

    def run():
        class _Stdin:
            buffer = io.BytesIO(json.dumps({"session_id": SID, "hook_event_name": "SessionStart",
                                            "source": "compact"}).encode())
        monkeypatch.setattr(sys, "stdin", _Stdin())
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        cli._run_hook_guard("compact")
        return buf.getvalue()

    with monkeypatch.context() as m:
        m.setattr(cli.os, "scandir", boom)
        assert run() == ""
    assert _kind(run()) == "nudge", "control: without the error the reminder prints"


def test_compact_respects_graphify_out(tmp_path):
    f = _project(tmp_path)
    (tmp_path / "graphify-out").rename(tmp_path / "alt-out")
    env = _env(tmp_path)
    env["GRAPHIFY_OUT"] = "alt-out"

    def run(kind, payload):
        return subprocess.run([sys.executable, "-m", "graphify", "hook-guard", kind], input=json.dumps(payload),
                              capture_output=True, text=True, cwd=tmp_path, env=env).stdout

    read = {"session_id": SID, "tool_name": "Read", "tool_input": {"file_path": str(f)}}
    for _ in range(5):
        run("read", read)
    assert run("read", read) == ""
    out = run("compact", {"session_id": SID, "hook_event_name": "SessionStart", "source": "compact"})
    assert "alt-out/graph.json" in out
    assert run("read", read) != ""


# ------------------------------------------------------------------ install


def _settings(project):
    return json.loads((project / ".claude" / "settings.json").read_text(encoding="utf-8"))


def _ours(groups):
    return [g for g in groups if any(install_mod._is_graphify_hook_entry(e) for e in g.get("hooks", []))]


def test_install_adds_one_compact_session_start_hook(tmp_path):
    install_mod._install_claude_hook(tmp_path)
    install_mod._install_claude_hook(tmp_path)  # re-install must not duplicate
    groups = _settings(tmp_path)["hooks"]["SessionStart"]
    ours = _ours(groups)
    assert len(ours) == 1
    assert ours[0]["matcher"] == "compact"
    (entry,) = ours[0]["hooks"]
    assert entry["type"] == "command" and entry["command"].endswith("hook-guard compact")
    assert 0 < entry["timeout"] <= 30


def test_project_install_uses_the_bare_command(tmp_path):
    install_mod._install_claude_hook(tmp_path, project=True)
    (group,) = _ours(_settings(tmp_path)["hooks"]["SessionStart"])
    assert group["hooks"][0]["command"] == "graphify hook-guard compact"


def test_install_and_uninstall_keep_the_users_session_start_hooks(tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    user_group = {"matcher": "startup", "hooks": [{"type": "command", "command": "echo hello"}]}
    shared = {"matcher": "compact", "hooks": [{"type": "command", "command": "./notify.sh"}]}
    settings_path.write_text(json.dumps({"hooks": {"SessionStart": [user_group, shared]}}), encoding="utf-8")

    install_mod._install_claude_hook(tmp_path)
    groups = _settings(tmp_path)["hooks"]["SessionStart"]
    assert groups[:2] == [user_group, shared]
    assert len(_ours(groups)) == 1

    install_mod._uninstall_claude_hook(tmp_path)
    hooks = _settings(tmp_path)["hooks"]
    assert hooks["SessionStart"] == [user_group, shared]
    assert _ours(hooks["PreToolUse"]) == []


def test_uninstall_removes_the_session_start_hook(tmp_path):
    install_mod._install_claude_hook(tmp_path)
    install_mod._uninstall_claude_hook(tmp_path)
    hooks = _settings(tmp_path)["hooks"]
    assert _ours(hooks["SessionStart"]) == [] and _ours(hooks["PreToolUse"]) == []


def test_uninstall_cleans_session_start_from_settings_local(tmp_path):
    local = tmp_path / ".claude" / "settings.local.json"
    local.parent.mkdir(parents=True)
    local.write_text(json.dumps({"hooks": {"SessionStart": install_mod._claude_sessionstart_hooks()}}),
                     encoding="utf-8")
    install_mod._uninstall_claude_hook(tmp_path)
    assert json.loads(local.read_text(encoding="utf-8"))["hooks"]["SessionStart"] == []
