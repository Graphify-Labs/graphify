"""DeepSeek Harness hook-guard: lowercase tool names, deny modes, session start.

DSH registers its tools as ``read``/``grep``/``glob``/``bash`` and mounts the
guard through its Claude-Code hook bridge, so the guard must recognise the
lowercase vocabulary or a functioning install silently never fires. These tests
drive the guard with DSH's real payload shape.

They also pin the deny-mode contract: ``once`` (the Claude Code default) is
unchanged, and ``until-query`` keeps redirecting while no recent graph query
exists, bounded by a cap so a session can never be stranded.
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


def _invoke(kind, payload, tmp_path, monkeypatch, *, strict=False, deny_mode=None, env=None):
    monkeypatch.chdir(tmp_path)
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    data = json.dumps(payload).encode() if not isinstance(payload, (bytes, bytearray)) else bytes(payload)

    class _Stdin:
        buffer = io.BytesIO(data)

    monkeypatch.setattr(sys, "stdin", _Stdin())
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    cli._run_hook_guard(kind, strict=strict, deny_mode=deny_mode)
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


def test_claude_cased_names_still_work(tmp_path, monkeypatch):
    f = _project(tmp_path)
    payload = {"session_id": "cc-1", "tool_name": "Read", "tool_input": {"file_path": str(f)}}
    out = _invoke("read", payload, tmp_path, monkeypatch, strict=True)
    assert _is_deny(out), out


# --- deny modes -----------------------------------------------------------

def test_once_mode_denies_exactly_once(tmp_path, monkeypatch):
    f = _project(tmp_path)
    first = _invoke("read", _dsh_read(f), tmp_path, monkeypatch, strict=True, deny_mode="once")
    second = _invoke("read", _dsh_read(f), tmp_path, monkeypatch, strict=True, deny_mode="once")
    assert _is_deny(first), first
    assert not _is_deny(second), second
    assert _is_nudge(second), second


def test_until_query_denies_up_to_the_cap_then_advises(tmp_path, monkeypatch):
    f = _project(tmp_path)
    outs = [
        _invoke("read", _dsh_read(f), tmp_path, monkeypatch, strict=True, deny_mode="until-query")
        for _ in range(3)
    ]
    assert _is_deny(outs[0]), outs[0]
    assert _is_deny(outs[1]), outs[1]
    assert not _is_deny(outs[2]), outs[2]
    assert _is_nudge(outs[2]), outs[2]


def test_until_query_releases_after_a_graph_query(tmp_path, monkeypatch):
    f = _project(tmp_path)
    first = _invoke("read", _dsh_read(f), tmp_path, monkeypatch, strict=True, deny_mode="until-query")
    assert _is_deny(first), first
    _stamp_query(tmp_path)
    second = _invoke("read", _dsh_read(f), tmp_path, monkeypatch, strict=True, deny_mode="until-query")
    assert not _is_deny(second), second


def test_deny_cap_environment_override(tmp_path, monkeypatch):
    f = _project(tmp_path)
    env = {"GRAPHIFY_HOOK_DENY_CAP": "1"}
    first = _invoke(
        "read", _dsh_read(f), tmp_path, monkeypatch, strict=True, deny_mode="until-query", env=env
    )
    second = _invoke(
        "read", _dsh_read(f), tmp_path, monkeypatch, strict=True, deny_mode="until-query", env=env
    )
    assert _is_deny(first), first
    assert not _is_deny(second), second


def test_deny_mode_environment_override_wins(tmp_path, monkeypatch):
    f = _project(tmp_path)
    # Installed as `until-query`, but the environment forces the one-shot policy.
    env = {"GRAPHIFY_HOOK_DENY_MODE": "once"}
    first = _invoke(
        "read", _dsh_read(f), tmp_path, monkeypatch, strict=True, deny_mode="until-query", env=env
    )
    second = _invoke(
        "read", _dsh_read(f), tmp_path, monkeypatch, strict=True, deny_mode="until-query", env=env
    )
    assert _is_deny(first), first
    assert not _is_deny(second), second


def test_unknown_deny_mode_falls_back_to_once(tmp_path, monkeypatch):
    f = _project(tmp_path)
    first = _invoke("read", _dsh_read(f), tmp_path, monkeypatch, strict=True, deny_mode="nonsense")
    second = _invoke("read", _dsh_read(f), tmp_path, monkeypatch, strict=True, deny_mode="nonsense")
    assert _is_deny(first), first
    assert not _is_deny(second), second


def test_unindexed_file_is_never_denied_in_until_query_mode(tmp_path, monkeypatch):
    f = _project(tmp_path, indexed=False)
    out = _invoke("read", _dsh_read(f), tmp_path, monkeypatch, strict=True, deny_mode="until-query")
    assert not _is_deny(out), out


def test_out_of_project_target_is_never_denied_in_either_mode(tmp_path, monkeypatch):
    _project(tmp_path)
    outside = tmp_path.parent / "elsewhere.py"
    for mode in ("once", "until-query"):
        out = _invoke("read", _dsh_read(outside), tmp_path, monkeypatch, strict=True, deny_mode=mode)
        assert not _is_deny(out), (mode, out)


def test_graph_output_target_is_never_denied_in_either_mode(tmp_path, monkeypatch):
    _project(tmp_path)
    inside_out = tmp_path / "graphify-out" / "report.py"
    inside_out.write_text("x = 1\n", encoding="utf-8")
    for mode in ("once", "until-query"):
        out = _invoke("read", _dsh_read(inside_out), tmp_path, monkeypatch, strict=True, deny_mode=mode)
        assert not _is_deny(out), (mode, out)


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
        return _is_deny(
            _invoke(
                "read", _dsh_read(f), tmp_path, monkeypatch,
                strict=True, deny_mode="until-query",
            )
        )

    assert _read_denied()
    assert _read_denied()
    assert not _read_denied()
    payload = {"session_id": "dsh-1", "hook_event_name": "SessionStart", "source": "compact"}
    _invoke("session", payload, tmp_path, monkeypatch)
    assert _read_denied()


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
