"""A fresh orientation stamp silences the soft search/read nudges.

Both nudges promise "only grep/read raw files after graphify has oriented you",
and `graphify query|explain|path` records that orientation in
cache/last_query_stamp — but until now only the strict read *deny* consulted the
stamp, so an agent that obeyed the nudge kept receiving the identical MANDATORY
demand on every subsequent search or read. While the stamp is fresh
(GRAPHIFY_HOOK_STRICT_TTL, default 1800s) the agent IS oriented and the guard
has nothing new to say. The stale-graph nudge is different information (the
graph lags the file) and keeps firing regardless.
"""
import io
import json
import os
import sys
import time

import pytest

from graphify import __main__ as m


def _invoke(kind, payload, tmp_path, monkeypatch, *, stamp_age=None, graph_age=None):
    monkeypatch.setattr("graphify.paths.GRAPHIFY_OUT", "graphify-out")
    monkeypatch.setattr("graphify.paths.GRAPHIFY_OUT_NAME", "graphify-out")
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "graph.json").write_text("{}", encoding="utf-8")
    if graph_age is not None:
        t = time.time() - graph_age
        os.utime(out / "graph.json", (t, t))
    if stamp_age is not None:
        stamp = out / "cache" / "last_query_stamp"
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(str(time.time()), encoding="utf-8")
        t = time.time() - stamp_age
        os.utime(stamp, (t, t))

    class _Stdin:
        def __init__(self, b):
            self.buffer = io.BytesIO(b)

    monkeypatch.setattr(sys, "stdin", _Stdin(json.dumps(payload).encode("utf-8")))
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    m._run_hook_guard(kind)
    return buf.getvalue()


_SEARCHES = [
    {"tool_name": "Bash", "tool_input": {"command": "grep -rn foo src/"}},
    {"tool_name": "Grep", "tool_input": {"pattern": "foo", "glob": "*.py"}},
]


@pytest.mark.parametrize("payload", _SEARCHES)
def test_fresh_stamp_silences_search_nudge(payload, tmp_path, monkeypatch):
    assert _invoke("search", payload, tmp_path, monkeypatch, stamp_age=10).strip() == ""


@pytest.mark.parametrize("payload", _SEARCHES)
def test_expired_stamp_still_nudges_search(payload, tmp_path, monkeypatch):
    out = _invoke("search", payload, tmp_path, monkeypatch, stamp_age=4000)
    assert "graphify query" in out


def test_no_stamp_still_nudges_search(tmp_path, monkeypatch):
    out = _invoke("search", {"tool_input": {"command": "grep x"}}, tmp_path, monkeypatch)
    assert "graphify query" in out


def test_fresh_stamp_silences_read_nudge(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_text("x = 1", encoding="utf-8")
    payload = {"tool_name": "Read", "tool_input": {"file_path": "app.py"}}
    # graph.json is written after app.py, so the graph is fresh for the file
    assert _invoke("read", payload, tmp_path, monkeypatch, stamp_age=10).strip() == ""


def test_no_stamp_still_nudges_read(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_text("x = 1", encoding="utf-8")
    payload = {"tool_name": "Read", "tool_input": {"file_path": "app.py"}}
    assert "MANDATORY" in _invoke("read", payload, tmp_path, monkeypatch)


def test_fresh_stamp_keeps_stale_graph_read_nudge(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_text("x = 2", encoding="utf-8")
    payload = {"tool_name": "Read", "tool_input": {"file_path": "app.py"}}
    # graph older than the file: the stale nudge carries new information
    # (the graph lags this file) and is not silenced by orientation
    out = _invoke("read", payload, tmp_path, monkeypatch, stamp_age=10, graph_age=60)
    assert "STALE" in out
