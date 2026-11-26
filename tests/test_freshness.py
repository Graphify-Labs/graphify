"""Unit tests for graphify.freshness — the opt-in MCP auto-refresh gate.

These exercise the in-process decision logic (staleness, memoisation,
fail-open, debounce). The end-to-end MCP transport is covered separately in
``test_freshness_mcp.py``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from graphify import freshness
from tests._freshness_repo import (
    build_graph,
    commit,
    graph_json,
    log_entries,
    make_repo,
)


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    freshness.reset_state()
    for key in (
        "GRAPHIFY_AUTO_REFRESH",
        "GRAPHIFY_AUTO_REFRESH_DIRTY",
        "GRAPHIFY_AUTO_REFRESH_LOG",
        "GRAPHIFY_AUTO_REFRESH_TIMEOUT",
        "GRAPHIFY_AUTO_REFRESH_DEBOUNCE",
    ):
        monkeypatch.delenv(key, raising=False)
    yield
    freshness.reset_state()


@pytest.fixture
def repo(tmp_path) -> Path:
    return make_repo(tmp_path)


# ---------------------------------------------------------------------------
# Env flags / cheap probes
# ---------------------------------------------------------------------------


def test_enabled_and_dirty_flags(monkeypatch):
    assert freshness.enabled() is False
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH", "1")
    assert freshness.enabled() is True
    assert freshness.dirty_enabled() is False
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH_DIRTY", "true")
    assert freshness.dirty_enabled() is True


def test_timeout_and_debounce_parsing(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_AUTO_REFRESH_TIMEOUT", raising=False)
    assert freshness._timeout() == 120.0
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH_TIMEOUT", "5")
    assert freshness._timeout() == 5.0
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH_TIMEOUT", "0")  # clamped to >= 1
    assert freshness._timeout() == 1.0
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH_TIMEOUT", "garbage")
    assert freshness._timeout() == 120.0


def test_parse_built_commit_basic(tmp_path):
    p = tmp_path / "graph.json"
    p.write_text(json.dumps({"nodes": [], "links": [], "built_at_commit": "abc123"}))
    assert freshness._parse_built_commit(str(p)) == "abc123"


def test_parse_built_commit_missing_key(tmp_path):
    p = tmp_path / "graph.json"
    p.write_text('{"nodes": [], "links": []}')
    assert freshness._parse_built_commit(str(p)) is None


def test_parse_built_commit_streams_multichunk(tmp_path):
    p = tmp_path / "big.json"
    filler = "x" * ((1 << 20) + 100)  # key lands in the second 1 MiB chunk
    p.write_text('{"filler": "' + filler + '", "built_at_commit": "deadbeef"}')
    assert freshness._parse_built_commit(str(p)) == "deadbeef"


def test_read_built_commit_is_cached_by_stat(tmp_path, monkeypatch):
    p = tmp_path / "graph.json"
    p.write_text(json.dumps({"built_at_commit": "c0ffee"}))
    assert freshness.read_built_commit(str(p)) == "c0ffee"

    calls = {"n": 0}
    original = freshness._parse_built_commit

    def counting(path):
        calls["n"] += 1
        return original(path)

    monkeypatch.setattr(freshness, "_parse_built_commit", counting)
    assert freshness.read_built_commit(str(p)) == "c0ffee"
    assert freshness.read_built_commit(str(p)) == "c0ffee"
    assert calls["n"] == 0  # unchanged (mtime_ns, size) served from cache


# ---------------------------------------------------------------------------
# Skip cases
# ---------------------------------------------------------------------------


def test_no_project_path_is_skipped():
    assert freshness.ensure_fresh(None).state == "skipped"
    assert freshness.ensure_fresh("").state == "skipped"


def test_non_git_project_is_skipped(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert freshness.ensure_fresh(str(plain)).state == "skipped"


# ---------------------------------------------------------------------------
# Core staleness / memoisation
# ---------------------------------------------------------------------------


def test_fresh_graph_no_rebuild(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH", "1")
    log = tmp_path / "log"
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH_LOG", str(log))
    before = graph_json(repo).stat().st_mtime_ns
    result = freshness.ensure_fresh(str(repo))
    assert result.state == "fresh"
    assert result.banner == ""
    assert log_entries(log) == []
    assert graph_json(repo).stat().st_mtime_ns == before


def test_new_commit_rebuilds_once_then_memoises(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH", "1")
    log = tmp_path / "log"
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH_LOG", str(log))
    (repo / "gamma.py").write_text("def added(x):\n    return x + 1\n", encoding="utf-8")
    commit(repo, "feat: gamma")

    first = freshness.ensure_fresh(str(repo))
    assert first.state == "refreshed"
    assert "behind HEAD" in first.banner
    assert len(log_entries(log)) == 1

    assert freshness.ensure_fresh(str(repo)).state == "fresh"
    assert freshness.ensure_fresh(str(repo)).state == "fresh"
    assert len(log_entries(log)) == 1  # memoised: no further rebuilds

    labels = {n.get("label") for n in json.loads(graph_json(repo).read_text())["nodes"]}
    assert "added()" in labels  # answer reflects the new code


def test_noop_commit_memo_prevents_rebuild_loop(repo, tmp_path, monkeypatch):
    """The KEY GOTCHA: a commit that does not change topology leaves graph.json
    untouched, so `built_at_commit` is NOT restamped. A naive check would rebuild
    forever; the memo stops after the first rebuild.

    Passes under both variants: memo-only (built stays behind HEAD) and restamp
    (watch._restamp_built_commit advances it)."""
    from graphify import watch

    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH", "1")
    log = tmp_path / "log"
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH_LOG", str(log))
    (repo / "notes.abc").write_text("unclassified data", encoding="utf-8")  # not indexed
    head = commit(repo, "chore: noop")

    built_before = freshness.read_built_commit(str(graph_json(repo)))
    assert built_before != head  # naive staleness is already true
    result = freshness.ensure_fresh(str(repo))
    assert result.state == "refreshed"
    assert len(log_entries(log)) == 1

    built_after = freshness.read_built_commit(str(graph_json(repo)))
    if hasattr(watch, "_restamp_built_commit"):
        # restamp variant: the stamp is advanced, so naive staleness clears.
        assert built_after == head
    else:
        # memo-only variant: the stamp is still behind, so a naive check would
        # rebuild again — the memo is what stops the loop.
        assert built_after != head
    assert freshness.ensure_fresh(str(repo)).state == "fresh"
    assert freshness.ensure_fresh(str(repo)).state == "fresh"
    assert len(log_entries(log)) == 1


def test_missing_graph_is_stale_and_built(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH", "1")
    log = tmp_path / "log"
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH_LOG", str(log))
    graph_json(repo).unlink()
    result = freshness.ensure_fresh(str(repo))
    assert result.state == "refreshed"
    assert graph_json(repo).exists()
    assert len(log_entries(log)) == 1


# ---------------------------------------------------------------------------
# Fail-open
# ---------------------------------------------------------------------------


def _dirty_new_commit(repo, marker: int = 1):
    (repo / "gamma.py").write_text(
        f"def added(x):\n    return x + {marker}\n", encoding="utf-8"
    )
    return commit(repo, f"feat: gamma {marker}")


def test_failure_is_fail_open_and_no_retry_storm(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH", "1")
    log = tmp_path / "log"
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH_LOG", str(log))
    monkeypatch.setattr(freshness, "_update_command", lambda root: ["/nonexistent/graphify"])
    _dirty_new_commit(repo)

    first = freshness.ensure_fresh(str(repo))
    assert first.state == "failed"
    assert "STALE" in first.banner
    assert len(log_entries(log)) == 1

    second = freshness.ensure_fresh(str(repo))
    assert second.state == "failed"
    assert len(log_entries(log)) == 1  # same HEAD -> no retry storm

    _dirty_new_commit(repo, 2)  # HEAD changes -> retry
    third = freshness.ensure_fresh(str(repo))
    assert third.state == "failed"
    assert len(log_entries(log)) == 2

def test_missing_graph_and_failure_uses_missing_style_banner(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH", "1")
    monkeypatch.setattr(freshness, "_update_command", lambda root: ["/nonexistent/graphify"])
    graph_json(repo).unlink()
    result = freshness.ensure_fresh(str(repo))
    assert result.state == "failed"
    assert "no graph.json yet" in result.banner


def test_timeout_is_fail_open(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH", "1")
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH_TIMEOUT", "0.3")
    monkeypatch.setattr(
        freshness,
        "_update_command",
        lambda root: [sys.executable, "-c", "import time; time.sleep(5)"],
    )
    _dirty_new_commit(repo)
    result = freshness.ensure_fresh(str(repo))
    assert result.state == "failed"
    assert "timeout" in result.reason


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def test_concurrent_calls_share_one_build(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH", "1")
    log = tmp_path / "log"
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH_LOG", str(log))
    _dirty_new_commit(repo)

    states: list[str] = []
    lock = threading.Lock()

    def worker():
        state = freshness.ensure_fresh(str(repo)).state
        with lock:
            states.append(state)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(log_entries(log)) == 1  # exactly one `graphify update`
    assert states.count("refreshed") == 1
    assert all(s in ("refreshed", "fresh") for s in states)


# ---------------------------------------------------------------------------
# Dirty working tree
# ---------------------------------------------------------------------------


def test_default_mode_ignores_uncommitted_edits(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH", "1")
    log = tmp_path / "log"
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH_LOG", str(log))
    (repo / "alpha.py").write_text("def greet(name):\n    return 'CHANGED'\n", encoding="utf-8")
    result = freshness.ensure_fresh(str(repo))
    assert result.state == "fresh"  # commit-only mode: HEAD unchanged
    assert log_entries(log) == []


def test_dirty_mode_rebuilds_once_then_debounces(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH", "1")
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH_DIRTY", "1")
    log = tmp_path / "log"
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH_LOG", str(log))

    (repo / "alpha.py").write_text("def greet(name):\n    return 'ONE'\n", encoding="utf-8")
    first = freshness.ensure_fresh(str(repo))
    assert first.state == "refreshed"
    assert len(log_entries(log)) == 1

    assert freshness.ensure_fresh(str(repo)).state == "fresh"
    assert len(log_entries(log)) == 1

    # A further edit inside the debounce window must not rebuild again.
    (repo / "alpha.py").write_text("def greet(name):\n    return 'TWO'\n", encoding="utf-8")
    debounced = freshness.ensure_fresh(str(repo))
    assert debounced.state == "fresh"
    assert debounced.reason == "debounce"
    assert len(log_entries(log)) == 1

    # Once the debounce window is open, the next edit rebuilds.
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH_DEBOUNCE", "0")
    (repo / "alpha.py").write_text("def greet(name):\n    return 'THREE'\n", encoding="utf-8")
    assert freshness.ensure_fresh(str(repo)).state == "refreshed"
    assert len(log_entries(log)) == 2


# ---------------------------------------------------------------------------
# Cost sample
# ---------------------------------------------------------------------------


def test_rev_parse_is_cheap(repo):
    started = __import__("time").perf_counter()
    for _ in range(20):
        freshness._git_head(repo)
    per_call = (__import__("time").perf_counter() - started) / 20
    # Loose regression guard only; real value recorded in the report.
    assert per_call < 0.5
