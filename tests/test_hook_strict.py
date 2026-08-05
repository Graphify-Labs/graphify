"""Strict-mode hook-guard: opt-in block-then-nudge + #1840 gating.

The strict guard (Claude Code Read only) denies the FIRST raw read of an indexed,
in-project, fresh source file per session, then downgrades to the soft nudge — so
it can never strand an agent. #1840: out-of-project reads are ignored and a graph
that is stale for the target softens to a non-mandatory nudge. Everything defaults
to the historical soft nudge unless strict is explicitly enabled.
"""
import io
import json
import os
import sys
import time

import pytest

import graphify.cli as cli


def _fixture(tmp_path, *, indexed=True, fresh=True):
    """A project with graphify-out/graph.json + manifest and one source file.
    ``fresh`` makes the graph newer than the source (not stale)."""
    src = tmp_path / "src"
    src.mkdir()
    f = src / "mod.py"
    f.write_text("def x():\n    return 1\n", encoding="utf-8")
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "manifest.json").write_text(
        json.dumps({"src/mod.py": {"mtime": 1}} if indexed else {"other/z.py": {"mtime": 1}}),
        encoding="utf-8",
    )
    time.sleep(0.02)
    (out / "graph.json").write_text('{"nodes":[],"links":[]}', encoding="utf-8")
    if not fresh:
        time.sleep(0.02)
        f.write_text("def x():\n    return 2\n", encoding="utf-8")  # source now newer -> stale
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


def _read(fpath, sid="s1"):
    return {"session_id": sid, "tool_name": "Read", "tool_input": {"file_path": str(fpath)}}


def _is_deny(out):
    return out.strip() != "" and json.loads(out).get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def test_strict_first_read_denies_then_nudges(tmp_path, monkeypatch):
    f = _fixture(tmp_path)
    out1 = _invoke("read", _read(f), tmp_path, monkeypatch, strict=True)
    assert _is_deny(out1)
    assert "graphify query" in json.loads(out1)["hookSpecificOutput"]["permissionDecisionReason"]
    # marker created
    assert (tmp_path / "graphify-out" / "cache" / "hook_sessions" / "s1.denied").exists()
    # same session again -> soft nudge, not a second deny
    out2 = _invoke("read", _read(f), tmp_path, monkeypatch, strict=True)
    assert not _is_deny(out2) and "MANDATORY" in out2


def test_strict_new_session_denies_again(tmp_path, monkeypatch):
    f = _fixture(tmp_path)
    _invoke("read", _read(f, "sA"), tmp_path, monkeypatch, strict=True)
    out = _invoke("read", _read(f, "sB"), tmp_path, monkeypatch, strict=True)
    assert _is_deny(out)


def test_fresh_query_stamp_suppresses_deny(tmp_path, monkeypatch):
    f = _fixture(tmp_path)
    stamp = tmp_path / "graphify-out" / "cache" / "last_query_stamp"
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(str(time.time()), encoding="utf-8")
    out = _invoke("read", _read(f), tmp_path, monkeypatch, strict=True)
    assert not _is_deny(out) and "MANDATORY" in out


def test_expired_query_stamp_still_denies(tmp_path, monkeypatch):
    f = _fixture(tmp_path)
    stamp = tmp_path / "graphify-out" / "cache" / "last_query_stamp"
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text("old", encoding="utf-8")
    old = time.time() - 10_000
    os.utime(stamp, (old, old))
    out = _invoke("read", _read(f), tmp_path, monkeypatch, strict=True, env={"GRAPHIFY_HOOK_STRICT_TTL": "1800"})
    assert _is_deny(out)


def test_soft_mode_never_denies(tmp_path, monkeypatch):
    f = _fixture(tmp_path)
    out = _invoke("read", _read(f), tmp_path, monkeypatch, strict=False)
    assert not _is_deny(out) and "MANDATORY" in out


def test_env_forces_strict_on(tmp_path, monkeypatch):
    f = _fixture(tmp_path)
    out = _invoke("read", _read(f), tmp_path, monkeypatch, strict=False, env={"GRAPHIFY_HOOK_STRICT": "1"})
    assert _is_deny(out)


def test_env_kills_strict(tmp_path, monkeypatch):
    f = _fixture(tmp_path)
    out = _invoke("read", _read(f), tmp_path, monkeypatch, strict=True, env={"GRAPHIFY_HOOK_STRICT": "0"})
    assert not _is_deny(out)


def test_out_of_project_read_silenced(tmp_path, monkeypatch):
    _fixture(tmp_path)
    payload = {"session_id": "s1", "tool_name": "Read", "tool_input": {"file_path": "/somewhere/else/x.py"}}
    assert _invoke("read", payload, tmp_path, monkeypatch, strict=True).strip() == ""
    # soft mode too
    assert _invoke("read", payload, tmp_path, monkeypatch, strict=False).strip() == ""


def test_stale_graph_softens_never_denies(tmp_path, monkeypatch):
    f = _fixture(tmp_path, fresh=False)  # source newer than graph
    out = _invoke("read", _read(f), tmp_path, monkeypatch, strict=True)
    assert not _is_deny(out)
    assert "stale" in out.lower() and "MANDATORY" not in out


def test_needs_update_flag_softens(tmp_path, monkeypatch):
    f = _fixture(tmp_path)
    (tmp_path / "graphify-out" / "needs_update").write_text("1", encoding="utf-8")
    out = _invoke("read", _read(f), tmp_path, monkeypatch, strict=True)
    assert not _is_deny(out) and "stale" in out.lower()


def test_glob_never_denies(tmp_path, monkeypatch):
    _fixture(tmp_path)
    payload = {"session_id": "s1", "tool_name": "Glob",
               "tool_input": {"pattern": "**/*.py", "path": str(tmp_path)}}
    assert not _is_deny(_invoke("read", payload, tmp_path, monkeypatch, strict=True))


def test_search_never_denies(tmp_path, monkeypatch):
    _fixture(tmp_path)
    out = _invoke("search", {"session_id": "s1", "tool_input": {"command": "grep -rn foo ."}},
                  tmp_path, monkeypatch, strict=True)
    assert not _is_deny(out)  # search stays a nudge even in strict mode


def test_no_session_id_never_denies(tmp_path, monkeypatch):
    f = _fixture(tmp_path)
    payload = {"tool_name": "Read", "tool_input": {"file_path": str(f)}}  # no session_id
    assert not _is_deny(_invoke("read", payload, tmp_path, monkeypatch, strict=True))


def test_not_indexed_file_not_denied(tmp_path, monkeypatch):
    f = _fixture(tmp_path, indexed=False)  # manifest doesn't list src/mod.py
    out = _invoke("read", _read(f), tmp_path, monkeypatch, strict=True)
    assert not _is_deny(out)


def test_fail_open_on_malformed_stdin(tmp_path, monkeypatch):
    _fixture(tmp_path)
    assert _invoke("read", b"{not json", tmp_path, monkeypatch, strict=True) == ""


def test_strict_enabled_env_precedence():
    import os as _os
    saved = _os.environ.get("GRAPHIFY_HOOK_STRICT")
    try:
        _os.environ["GRAPHIFY_HOOK_STRICT"] = "1"
        assert cli._hook_strict_enabled(False) is True
        _os.environ["GRAPHIFY_HOOK_STRICT"] = "0"
        assert cli._hook_strict_enabled(True) is False
        _os.environ.pop("GRAPHIFY_HOOK_STRICT", None)
        assert cli._hook_strict_enabled(True) is True
        assert cli._hook_strict_enabled(False) is False
    finally:
        if saved is None:
            _os.environ.pop("GRAPHIFY_HOOK_STRICT", None)
        else:
            _os.environ["GRAPHIFY_HOOK_STRICT"] = saved


def test_install_hook_carries_strict_flag():
    from graphify.install import _claude_pretooluse_hooks
    soft = _claude_pretooluse_hooks(strict=False)
    strict = _claude_pretooluse_hooks(strict=True)
    read_soft = next(h for h in soft if h["matcher"] == "Read|Glob")["hooks"][0]["command"]
    read_strict = next(h for h in strict if h["matcher"] == "Read|Glob")["hooks"][0]["command"]
    assert read_soft.endswith("hook-guard read")
    assert read_strict.endswith("hook-guard read --strict")
    # search hook is unchanged either way
    for hooks in (soft, strict):
        assert next(h for h in hooks if h["matcher"] == "Bash|Grep")["hooks"][0]["command"].endswith("hook-guard search")
