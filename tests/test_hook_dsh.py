"""DeepSeek Harness hook-guard: lowercase tool names, deny modes, session start.

DSH registers its tools as ``read``/``grep``/``glob``/``bash`` and mounts the
guard through its Claude-Code hook bridge, so the guard must recognise the
lowercase vocabulary or a functioning install silently never fires. These tests
drive the guard with DSH's real payload shape.

They also pin the deny contract: the same one-shot block Claude Code gets, then
advice - dsh is deliberately never stricter than the reference host.
"""
import io
import json
import sys
import time

import graphify.cli as cli


def _project(tmp_path, *, indexed=True):
    """A project with a fresh graph, a manifest, and one readable source file."""
    src = tmp_path / "src"
    src.mkdir()
    f = src / "mod.py"
    f.write_text("def x():\n    return 1\n", encoding="utf-8")
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "manifest.json").write_text(
        json.dumps({"src/mod.py": {"ast_hash": "h"}} if indexed else {"other/z.py": {"ast_hash": "h"}}),
        encoding="utf-8",
    )
    time.sleep(0.02)
    (out / "graph.json").write_text('{"nodes":[],"links":[]}', encoding="utf-8")
    return f


def _invoke(kind, payload, tmp_path, monkeypatch, *, strict=False, env=None):
    monkeypatch.chdir(tmp_path)
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    data = json.dumps(payload).encode() if not isinstance(payload, (bytes, bytearray)) else bytes(payload)

    class _Stdin:
        buffer = io.BytesIO(data)

    monkeypatch.setattr(sys, "stdin", _Stdin())
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    cli._run_hook_guard(kind, strict=strict)
    return buf.getvalue()


def _dsh_read(fpath, sid="dsh-1"):
    """DSH's `read` tool payload: lowercase name, Claude-shaped arguments."""
    return {"session_id": sid, "tool_name": "read", "tool_input": {"file_path": str(fpath)}}


def _dsh_grep(sid="dsh-1", path="."):
    return {"session_id": sid, "tool_name": "grep", "tool_input": {"pattern": "def x", "path": path}}


def _dsh_bash(command, sid="dsh-1"):
    return {"session_id": sid, "tool_name": "bash", "tool_input": {"command": command}}


def _is_deny(out):
    try:
        d = json.loads(out)
    except json.JSONDecodeError:
        return False
    hso = d.get("hookSpecificOutput", {})
    return hso.get("permissionDecision") == "deny" and bool(hso.get("permissionDecisionReason"))


def _is_nudge(out):
    try:
        d = json.loads(out)
    except json.JSONDecodeError:
        return False
    hso = d.get("hookSpecificOutput", {})
    return "additionalContext" in hso and "permissionDecision" not in hso


def _stamp_query(tmp_path):
    """Record a graph query the way `graphify query` does."""
    cache = tmp_path / "graphify-out" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "last_query_stamp").write_text(str(time.time()), encoding="utf-8")


# --- lowercase vocabulary -------------------------------------------------

def test_dsh_read_payload_gets_the_read_nudge(tmp_path, monkeypatch):
    f = _project(tmp_path)
    out = _invoke("read", _dsh_read(f), tmp_path, monkeypatch)
    assert _is_nudge(out), out
    assert "graphify query" in out


def test_dsh_read_payload_is_denied_in_strict_mode(tmp_path, monkeypatch):
    f = _project(tmp_path)
    out = _invoke("read", _dsh_read(f), tmp_path, monkeypatch, strict=True)
    assert _is_deny(out), out


def test_dsh_grep_payload_gets_the_search_nudge(tmp_path, monkeypatch):
    _project(tmp_path)
    out = _invoke("search", _dsh_grep(), tmp_path, monkeypatch)
    assert _is_nudge(out), out


def test_dsh_bash_search_gets_the_search_nudge(tmp_path, monkeypatch):
    _project(tmp_path)
    out = _invoke("search", _dsh_bash("rg 'def x' src"), tmp_path, monkeypatch)
    assert _is_nudge(out), out


def test_dsh_bash_file_reader_is_routed_through_the_read_policy(tmp_path, monkeypatch):
    f = _project(tmp_path)
    out = _invoke("search", _dsh_bash(f"cat {f}"), tmp_path, monkeypatch)
    assert _is_nudge(out), out
    # A shell read is advisory: the read policy never denies a bash command.
    out = _invoke("search", _dsh_bash(f"cat {f}"), tmp_path, monkeypatch, strict=True)
    assert not _is_deny(out), out


def test_dsh_string_tool_input_still_denies_in_strict_mode(tmp_path, monkeypatch):
    """The bridge passes `tool_input` as the model's raw JSON argument text.

    Reading only dicts made every DSH call look targetless, so a strict install
    fired its hooks and silently did nothing (caught by a live session, not by
    the dict-shaped fixtures above).
    """
    f = _project(tmp_path)
    payload = {
        "session_id": "dsh-str-1",
        "tool_name": "read",
        "tool_input": json.dumps({"file_path": str(f), "limit": 200}),
    }
    out = _invoke("read", payload, tmp_path, monkeypatch, strict=True)
    assert _is_deny(out), out

    advised = _invoke("read", {**payload, "session_id": "dsh-str-2"}, tmp_path, monkeypatch)
    assert _is_nudge(advised), advised


def test_dsh_string_tool_input_drives_the_search_policy(tmp_path, monkeypatch):
    _project(tmp_path)
    payload = {
        "session_id": "dsh-str-3",
        "tool_name": "grep",
        "tool_input": json.dumps({"pattern": "def x", "path": "."}),
    }
    out = _invoke("search", payload, tmp_path, monkeypatch)
    assert _is_nudge(out), out


def test_unparseable_string_tool_input_fails_open(tmp_path, monkeypatch):
    _project(tmp_path)
    for broken in ("{not json", ""):
        payload = {"session_id": "dsh-str-4", "tool_name": "read", "tool_input": broken}
        assert _invoke("read", payload, tmp_path, monkeypatch, strict=True) == ""


def test_claude_cased_names_still_work(tmp_path, monkeypatch):
    f = _project(tmp_path)
    payload = {"session_id": "cc-1", "tool_name": "Read", "tool_input": {"file_path": str(f)}}
    out = _invoke("read", payload, tmp_path, monkeypatch, strict=True)
    assert _is_deny(out), out


# --- the one-shot deny contract -------------------------------------------

def test_strict_denies_exactly_once_per_session(tmp_path, monkeypatch):
    """The whole policy, identical to Claude Code's: one deny, then advice."""
    f = _project(tmp_path)
    first = _invoke("read", _dsh_read(f), tmp_path, monkeypatch, strict=True)
    second = _invoke("read", _dsh_read(f), tmp_path, monkeypatch, strict=True)
    assert _is_deny(first), first
    assert not _is_deny(second), second
    assert _is_nudge(second), second


def test_a_graph_query_releases_the_next_read(tmp_path, monkeypatch):
    f = _project(tmp_path)
    assert _is_deny(_invoke("read", _dsh_read(f), tmp_path, monkeypatch, strict=True))
    _stamp_query(tmp_path)
    assert not _is_deny(_invoke("read", _dsh_read(f), tmp_path, monkeypatch, strict=True))


def test_unindexed_file_is_never_denied(tmp_path, monkeypatch):
    f = _project(tmp_path, indexed=False)
    out = _invoke("read", _dsh_read(f), tmp_path, monkeypatch, strict=True)
    assert not _is_deny(out), out


def test_out_of_project_target_is_never_denied(tmp_path, monkeypatch):
    _project(tmp_path)
    outside = tmp_path.parent / "elsewhere.py"
    out = _invoke("read", _dsh_read(outside), tmp_path, monkeypatch, strict=True)
    assert not _is_deny(out), out


def test_graph_output_target_is_never_denied(tmp_path, monkeypatch):
    _project(tmp_path)
    inside_out = tmp_path / "graphify-out" / "report.py"
    inside_out.write_text("x = 1\n", encoding="utf-8")
    out = _invoke("read", _dsh_read(inside_out), tmp_path, monkeypatch, strict=True)
    assert not _is_deny(out), out


# --- session start --------------------------------------------------------

def test_session_kind_orients_a_fresh_session(tmp_path, monkeypatch):
    _project(tmp_path)
    payload = {"session_id": "dsh-1", "hook_event_name": "SessionStart", "source": "startup"}
    out = _invoke("session", payload, tmp_path, monkeypatch)
    d = json.loads(out)
    assert d["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "graphify query" in d["hookSpecificOutput"]["additionalContext"]


def test_session_kind_is_silent_without_a_graph(tmp_path, monkeypatch):
    payload = {"session_id": "dsh-1", "hook_event_name": "SessionStart", "source": "startup"}
    out = _invoke("session", payload, tmp_path, monkeypatch)
    assert out == ""


def test_session_kind_restores_the_budget_after_compaction(tmp_path, monkeypatch):
    f = _project(tmp_path)

    def _read_denied():
        return _is_deny(_invoke("read", _dsh_read(f), tmp_path, monkeypatch, strict=True))

    assert _read_denied()
    assert not _read_denied()          # the one shot is spent
    payload = {"session_id": "dsh-1", "hook_event_name": "SessionStart", "source": "compact"}
    _invoke("session", payload, tmp_path, monkeypatch)
    assert _read_denied()              # a compaction restores the budget


def test_compact_kind_is_unchanged_for_other_sources(tmp_path, monkeypatch):
    _project(tmp_path)
    for source in ("startup", "resume", "clear"):
        payload = {"session_id": "cc-1", "hook_event_name": "SessionStart", "source": source}
        assert _invoke("compact", payload, tmp_path, monkeypatch) == ""


# --- fail open ------------------------------------------------------------

def test_malformed_payload_is_silent(tmp_path, monkeypatch):
    _project(tmp_path)
    assert _invoke("read", b"{not json", tmp_path, monkeypatch) == ""


def test_missing_graph_is_silent(tmp_path, monkeypatch):
    payload = {"session_id": "dsh-1", "tool_name": "read", "tool_input": {"file_path": "a.py"}}
    assert _invoke("read", payload, tmp_path, monkeypatch) == ""


# --- the payload the pinned bridge actually sends -------------------------

def _captured_read(rel, tmp_path, sid="dsh-live-1"):
    """PreToolUse JSON exactly as captured from dsh 0.2.3-alpha.2 + bridge 0.2.3-alpha.2.

    The bridge forwards the call's parsed arguments, and the model writes paths
    relative to the session workspace (``src/mod.py``), not absolute ones - the
    shape every other test in this file does not use.
    """
    return {
        "session_id": sid,
        "transcript_path": "",
        "hook_event_name": "PreToolUse",
        "tool_name": "read",
        "tool_input": {"file_path": rel},
        "tool_use_id": "call_00_captured",
        "cwd": str(tmp_path),
    }


def test_captured_payload_denies_with_a_workspace_relative_path(tmp_path, monkeypatch):
    _project(tmp_path)
    # A real graph has nodes for the file, so the deny names the exact command to
    # run next; the hint resolves a workspace-relative path, not an absolute one.
    (tmp_path / "graphify-out" / "graph.json").write_text(
        json.dumps({"nodes": [{"label": "x", "source_file": "src/mod.py", "source_location": "L1"}],
                    "links": []}),
        encoding="utf-8",
    )
    out = _invoke("read", _captured_read("src/mod.py", tmp_path), tmp_path, monkeypatch, strict=True)
    assert _is_deny(out), out
    reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
    assert 'graphify explain "mod.py"' in reason


def test_captured_payload_downgrades_after_one_query(tmp_path, monkeypatch):
    """The one-shot policy on the real shape: deny, then advise, never twice."""
    _project(tmp_path)
    payload = _captured_read("src/mod.py", tmp_path)
    assert _is_deny(_invoke("read", payload, tmp_path, monkeypatch, strict=True))
    second = _invoke("read", payload, tmp_path, monkeypatch, strict=True)
    assert _is_nudge(second), second


def test_grep_of_one_indexed_file_denies_once_in_strict_mode(tmp_path, monkeypatch):
    """dsh's `grep` sends a workspace-relative `path`; a single-file target needs
    the same index evidence Read does, and shares the same one-shot budget."""
    _project(tmp_path)
    payload = {
        "session_id": "dsh-grep-1",
        "tool_name": "grep",
        "tool_input": {"pattern": "def x", "path": "src/mod.py"},
        "cwd": str(tmp_path),
    }
    first = _invoke("search", payload, tmp_path, monkeypatch, strict=True)
    assert _is_deny(first), first
    second = _invoke("search", payload, tmp_path, monkeypatch, strict=True)
    assert not _is_deny(second), second


def test_the_installed_hook_command_produces_the_deny(tmp_path, monkeypatch):
    """End to end: the command `graphify dsh install` writes, run as dsh runs it.

    Every other test calls `_run_hook_guard` directly, so a hook command that
    cannot be parsed (a wrong subcommand, an unquoted path) would still pass.
    """
    import json as jsonlib
    import shutil
    import subprocess
    import sys

    from graphify.install import install

    dsh_home = tmp_path / "dsh-home"
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setenv("DSH_HOME", str(dsh_home))
    monkeypatch.chdir(project)
    _project(project)
    install("dsh", project=False, strict=True)

    hooks = jsonlib.loads((dsh_home / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    read_group = next(g for g in hooks["PreToolUse"] if g["matcher"] == "read|glob")
    command = read_group["hooks"][0]["command"]
    exe = command.split(" ", 1)[0]
    if shutil.which(exe) is None:
        import pytest

        pytest.skip(f"installed command names an unresolvable executable: {exe}")

    payload = _captured_read("src/mod.py", project)
    result = subprocess.run(
        command,
        shell=True,
        cwd=project,
        input=jsonlib.dumps(payload).encode(),
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    decision = jsonlib.loads(result.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "graphify query" in decision["permissionDecisionReason"]
