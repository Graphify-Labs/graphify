"""Session-scoped throttle on the hook-guard soft nudge (#2984).

The PreToolUse nudge is orientation, not information: once an agent has been told
an in-project graph exists it has either used it or decided not to, so repeating
the identical line on every later matching call only spends its context window.
The guard now emits at most one nudge per session per kind (search / read). Both
escape hatches stay wide open: a session the host does not identify, or a cache
that cannot hold markers, keeps the historical nudge-every-call behaviour, and
GRAPHIFY_HOOK_NUDGE_ONCE=0 turns the throttle off outright.
"""
import io
import json
import sys
import time

import pytest

import graphify.cli as cli


@pytest.fixture(autouse=True)
def _no_ambient_throttle_env(monkeypatch):
    """A GRAPHIFY_HOOK_NUDGE_ONCE inherited from the developer's or CI's
    environment would silently turn the default-behaviour cases into kill-switch
    cases. Tests that want the switch set it themselves."""
    monkeypatch.delenv("GRAPHIFY_HOOK_NUDGE_ONCE", raising=False)


def _project(tmp_path):
    """A project with one indexed source file and a graph that is fresh for it."""
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


def _invoke(kind, payload, tmp_path, monkeypatch, *, env=None):
    monkeypatch.chdir(tmp_path)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)

    class _Stdin:
        buffer = io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(sys, "stdin", _Stdin())
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    cli._run_hook_guard(kind)
    return buf.getvalue()


def _read(fpath, sid="s1"):
    return {"session_id": sid, "tool_name": "Read", "tool_input": {"file_path": str(fpath)}}


def _search(sid="s1"):
    return {"session_id": sid, "tool_name": "Bash", "tool_input": {"command": "grep -rn foo ."}}


def test_read_nudges_once_per_session(tmp_path, monkeypatch):
    f = _project(tmp_path)
    assert "MANDATORY" in _invoke("read", _read(f), tmp_path, monkeypatch)
    assert _invoke("read", _read(f), tmp_path, monkeypatch) == ""
    assert _invoke("read", _read(f), tmp_path, monkeypatch) == ""


def test_search_nudges_once_per_session(tmp_path, monkeypatch):
    _project(tmp_path)
    assert "MANDATORY" in _invoke("search", _search(), tmp_path, monkeypatch)
    assert _invoke("search", _search(), tmp_path, monkeypatch) == ""


def test_search_and_read_budgets_are_independent(tmp_path, monkeypatch):
    f = _project(tmp_path)
    assert "MANDATORY" in _invoke("search", _search(), tmp_path, monkeypatch)
    assert "MANDATORY" in _invoke("read", _read(f), tmp_path, monkeypatch)


def test_each_session_gets_its_own_nudge(tmp_path, monkeypatch):
    f = _project(tmp_path)
    assert "MANDATORY" in _invoke("read", _read(f, "s1"), tmp_path, monkeypatch)
    assert _invoke("read", _read(f, "s1"), tmp_path, monkeypatch) == ""
    assert "MANDATORY" in _invoke("read", _read(f, "s2"), tmp_path, monkeypatch)


def test_untrackable_session_keeps_nudging(tmp_path, monkeypatch):
    """No session id means no key to throttle on — never go silent instead."""
    f = _project(tmp_path)
    payload = _read(f)
    payload.pop("session_id")
    assert "MANDATORY" in _invoke("read", payload, tmp_path, monkeypatch)
    assert "MANDATORY" in _invoke("read", payload, tmp_path, monkeypatch)


def test_unusable_marker_dir_keeps_nudging(tmp_path, monkeypatch):
    """A cache path that cannot hold markers must not silence the nudge either —
    and must not be mistaken for an already-claimed marker."""
    f = _project(tmp_path)
    (tmp_path / "graphify-out" / "cache").write_text("not a directory", encoding="utf-8")
    assert "MANDATORY" in _invoke("read", _read(f), tmp_path, monkeypatch)
    assert "MANDATORY" in _invoke("read", _read(f), tmp_path, monkeypatch)


def test_kill_switch_restores_the_nudge_on_every_call(tmp_path, monkeypatch):
    f = _project(tmp_path)
    env = {"GRAPHIFY_HOOK_NUDGE_ONCE": "0"}
    assert "MANDATORY" in _invoke("read", _read(f), tmp_path, monkeypatch, env=env)
    assert "MANDATORY" in _invoke("read", _read(f), tmp_path, monkeypatch, env=env)


def test_an_out_of_scope_read_does_not_spend_the_nudge(tmp_path, monkeypatch):
    """#1840's scoping stays orthogonal to the throttle: a call the guard declines
    to nudge for must not consume the session's one nudge."""
    f = _project(tmp_path)
    outside = tmp_path.parent / "outside_the_project.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    assert _invoke("read", _read(outside), tmp_path, monkeypatch) == ""
    assert "MANDATORY" in _invoke("read", _read(f), tmp_path, monkeypatch)


def test_stale_nudge_spends_the_same_read_budget(tmp_path, monkeypatch):
    """The stale variant is the same reminder in softer words — one per session."""
    f = _project(tmp_path)
    time.sleep(0.02)
    f.write_text("def x():\n    return 2\n", encoding="utf-8")  # source newer -> stale
    first = _invoke("read", _read(f), tmp_path, monkeypatch)
    assert "STALE" in first and "MANDATORY" not in first
    assert _invoke("read", _read(f), tmp_path, monkeypatch) == ""


def test_an_ineligible_read_does_not_burn_the_strict_claim(tmp_path, monkeypatch):
    """_strict_denies claims the session marker in its last term, so the
    short-circuit order is load-bearing: a read that is not strict-eligible (here,
    a file the graph does not index) must not spend the session's single block."""
    f = _project(tmp_path)
    unindexed = f.parent / "other.py"
    unindexed.write_text("y = 2\n", encoding="utf-8")
    time.sleep(0.02)  # keep the graph newer than both files, so neither is stale
    (tmp_path / "graphify-out" / "graph.json").write_text('{"nodes":[],"links":[]}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def _run(path):
        class _Stdin:
            buffer = io.BytesIO(json.dumps(_read(path)).encode())
        monkeypatch.setattr(sys, "stdin", _Stdin())
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        cli._run_hook_guard("read", strict=True)
        return buf.getvalue()

    assert "MANDATORY" in _run(unindexed)  # nudge, not a deny
    assert not (tmp_path / "graphify-out" / "cache" / "hook_sessions" / "s1.denied").exists()
    assert json.loads(_run(f))["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_the_strict_deny_keeps_its_own_budget(tmp_path, monkeypatch):
    """The strict block already fires once per session off its own marker; it must
    not also eat the soft nudge that follows it."""
    f = _project(tmp_path)
    monkeypatch.chdir(tmp_path)

    def _run(strict):
        class _Stdin:
            buffer = io.BytesIO(json.dumps(_read(f)).encode())
        monkeypatch.setattr(sys, "stdin", _Stdin())
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        cli._run_hook_guard("read", strict=strict)
        return buf.getvalue()

    denied = _run(True)
    assert json.loads(denied)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "MANDATORY" in _run(True)
    assert _run(True) == ""
