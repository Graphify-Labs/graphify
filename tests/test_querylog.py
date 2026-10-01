"""Tests for graphify.querylog."""
import json
import os
import threading
import pytest
from pathlib import Path

from graphify.querylog import _archive_path, log_query, nodes_from_result


# ---------------------------------------------------------------------------
# nodes_from_result
# ---------------------------------------------------------------------------

def test_nodes_from_result_parses_header():
    result = "Traversal: BFS depth=2 | Start: ['foo'] | 7 nodes found\n\nNODE foo"
    assert nodes_from_result(result) == 7


def test_nodes_from_result_singular():
    assert nodes_from_result("1 node found") == 1


def test_nodes_from_result_missing():
    assert nodes_from_result("no match here") is None


def test_nodes_from_result_empty():
    assert nodes_from_result("") is None


# ---------------------------------------------------------------------------
# log_query — basic write
# ---------------------------------------------------------------------------

def test_log_query_writes_jsonl(tmp_path, monkeypatch):
    log_file = tmp_path / "q.log"
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG", str(log_file))
    monkeypatch.delenv("GRAPHIFY_QUERY_LOG_DISABLE", raising=False)

    log_query(kind="query", question="what is X", corpus="/some/graph.json",
              result="3 nodes found\nNODE a", duration_ms=12.5, mode="bfs", depth=2)

    lines = log_file.read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["kind"] == "query"
    assert rec["question"] == "what is X"
    assert rec["corpus"] == "/some/graph.json"
    assert rec["nodes_returned"] == 3
    assert rec["result_chars"] > 0
    assert rec["duration_ms"] == pytest.approx(12.5, abs=0.01)
    assert rec["mode"] == "bfs"
    assert "ts" in rec


def test_log_query_appends(tmp_path, monkeypatch):
    log_file = tmp_path / "q.log"
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG", str(log_file))
    monkeypatch.delenv("GRAPHIFY_QUERY_LOG_DISABLE", raising=False)

    log_query(kind="query", question="q1", corpus="/g.json")
    log_query(kind="query", question="q2", corpus="/g.json")

    lines = log_file.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["question"] == "q1"
    assert json.loads(lines[1])["question"] == "q2"


# ---------------------------------------------------------------------------
# opt-out / opt-in
# ---------------------------------------------------------------------------

def test_disable_env(tmp_path, monkeypatch):
    log_file = tmp_path / "q.log"
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG", str(log_file))
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG_DISABLE", "1")

    log_query(kind="query", question="q", corpus="/g.json")

    assert not log_file.exists()


def test_disable_env_true(tmp_path, monkeypatch):
    log_file = tmp_path / "q.log"
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG", str(log_file))
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG_DISABLE", "true")

    log_query(kind="query", question="q", corpus="/g.json")

    assert not log_file.exists()


def test_responses_not_logged_by_default(tmp_path, monkeypatch):
    log_file = tmp_path / "q.log"
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG", str(log_file))
    monkeypatch.delenv("GRAPHIFY_QUERY_LOG_DISABLE", raising=False)
    monkeypatch.delenv("GRAPHIFY_QUERY_LOG_RESPONSES", raising=False)

    log_query(kind="query", question="q", corpus="/g.json", result="NODE foo")

    rec = json.loads(log_file.read_text())
    assert "response" not in rec


def test_responses_optin(tmp_path, monkeypatch):
    log_file = tmp_path / "q.log"
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG", str(log_file))
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG_RESPONSES", "1")
    monkeypatch.delenv("GRAPHIFY_QUERY_LOG_DISABLE", raising=False)

    log_query(kind="query", question="q", corpus="/g.json", result="NODE foo bar")

    rec = json.loads(log_file.read_text())
    assert rec["response"] == "NODE foo bar"


# ---------------------------------------------------------------------------
# robustness — never raises
# ---------------------------------------------------------------------------

def test_log_never_raises(tmp_path, monkeypatch):
    # Point at a directory — open() for append will fail
    bad_path = tmp_path / "is_a_dir"
    bad_path.mkdir()
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG", str(bad_path))
    monkeypatch.delenv("GRAPHIFY_QUERY_LOG_DISABLE", raising=False)

    # Must not raise
    log_query(kind="query", question="q", corpus="/g.json")


def test_log_creates_parent_dirs(tmp_path, monkeypatch):
    log_file = tmp_path / "deep" / "nested" / "q.log"
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG", str(log_file))
    monkeypatch.delenv("GRAPHIFY_QUERY_LOG_DISABLE", raising=False)

    log_query(kind="query", question="q", corpus="/g.json")

    assert log_file.exists()


# ---------------------------------------------------------------------------
# field coverage
# ---------------------------------------------------------------------------

def test_nodes_returned_inferred_from_result(tmp_path, monkeypatch):
    log_file = tmp_path / "q.log"
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG", str(log_file))
    monkeypatch.delenv("GRAPHIFY_QUERY_LOG_DISABLE", raising=False)

    log_query(kind="query", question="q", corpus="/g.json",
              result="5 nodes found\nNODE a\nNODE b")

    rec = json.loads(log_file.read_text())
    assert rec["nodes_returned"] == 5


def test_explicit_nodes_returned_takes_precedence(tmp_path, monkeypatch):
    log_file = tmp_path / "q.log"
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG", str(log_file))
    monkeypatch.delenv("GRAPHIFY_QUERY_LOG_DISABLE", raising=False)

    log_query(kind="path", question="A -> B", corpus="/g.json", nodes_returned=3)

    rec = json.loads(log_file.read_text())
    assert rec["nodes_returned"] == 3


def test_kind_mcp_query(tmp_path, monkeypatch):
    log_file = tmp_path / "q.log"
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG", str(log_file))
    monkeypatch.delenv("GRAPHIFY_QUERY_LOG_DISABLE", raising=False)

    log_query(kind="mcp_query", question="q", corpus="/g.json")

    rec = json.loads(log_file.read_text())
    assert rec["kind"] == "mcp_query"


# ---------------------------------------------------------------------------
# #1797 — query log is opt-in (default OFF)
# ---------------------------------------------------------------------------

def _clear_log_env(monkeypatch):
    for k in ("GRAPHIFY_QUERY_LOG", "GRAPHIFY_QUERY_LOG_ENABLE", "GRAPHIFY_QUERY_LOG_DISABLE"):
        monkeypatch.delenv(k, raising=False)


def test_query_log_off_by_default(monkeypatch):
    from graphify.querylog import _log_path
    _clear_log_env(monkeypatch)
    assert _log_path() is None


def test_query_log_enabled_by_explicit_flag(monkeypatch):
    from graphify.querylog import _log_path
    _clear_log_env(monkeypatch)
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG_ENABLE", "1")
    assert str(_log_path()).endswith("graphify-queries.log")


def test_query_log_enabled_by_explicit_path(monkeypatch, tmp_path):
    from graphify.querylog import _log_path
    _clear_log_env(monkeypatch)
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG", str(tmp_path / "q.log"))
    assert _log_path() == tmp_path / "q.log"


def test_query_log_disable_wins(monkeypatch):
    from graphify.querylog import _log_path
    _clear_log_env(monkeypatch)
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG_ENABLE", "1")
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG_DISABLE", "1")
    assert _log_path() is None


def test_log_query_writes_nothing_by_default(monkeypatch, tmp_path):
    """End-to-end: with no opt-in, log_query must not create the default log."""
    _clear_log_env(monkeypatch)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    log_query(kind="query", question="secret internal ticket TICKET-123", corpus=".", result="1 node found")
    assert not (tmp_path / ".cache" / "graphify-queries.log").exists()


# ---------------------------------------------------------------------------
# #3051 — optional rotation via GRAPHIFY_QUERY_LOG_MAX_RECORDS
# ---------------------------------------------------------------------------

def _rotation_env(monkeypatch, tmp_path, max_records=None):
    log_file = tmp_path / "q.log"
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG", str(log_file))
    monkeypatch.delenv("GRAPHIFY_QUERY_LOG_DISABLE", raising=False)
    if max_records is None:
        monkeypatch.delenv("GRAPHIFY_QUERY_LOG_MAX_RECORDS", raising=False)
    else:
        monkeypatch.setenv("GRAPHIFY_QUERY_LOG_MAX_RECORDS", str(max_records))
    return log_file


def test_rotation_unset_keeps_all_lines(tmp_path, monkeypatch):
    log_file = _rotation_env(monkeypatch, tmp_path)
    for i in range(5):
        log_query(kind="query", question=f"q{i}", corpus="/g.json")
    lines = log_file.read_text().splitlines()
    assert len(lines) == 5
    assert not _archive_path(log_file).exists()


def test_rotation_trims_live_keeps_newest(tmp_path, monkeypatch):
    log_file = _rotation_env(monkeypatch, tmp_path, max_records=3)
    for i in range(5):
        log_query(kind="query", question=f"q{i}", corpus="/g.json")
    live = [json.loads(l)["question"] for l in log_file.read_text().splitlines()]
    archive = [json.loads(l)["question"] for l in _archive_path(log_file).read_text().splitlines()]
    assert live == ["q2", "q3", "q4"]
    assert archive == ["q0", "q1"]


def test_rotation_invalid_env_is_noop(tmp_path, monkeypatch):
    log_file = _rotation_env(monkeypatch, tmp_path, max_records="abc")
    for i in range(4):
        log_query(kind="query", question=f"q{i}", corpus="/g.json")
    assert len(log_file.read_text().splitlines()) == 4
    assert not _archive_path(log_file).exists()

    monkeypatch.setenv("GRAPHIFY_QUERY_LOG_MAX_RECORDS", "0")
    log_query(kind="query", question="extra", corpus="/g.json")
    assert len(log_file.read_text().splitlines()) == 5


def test_rotation_archive_appends_across_rotations(tmp_path, monkeypatch):
    log_file = _rotation_env(monkeypatch, tmp_path, max_records=2)
    for i in range(5):
        log_query(kind="query", question=f"q{i}", corpus="/g.json")
    archive_path = _archive_path(log_file)
    archived = [json.loads(l)["question"] for l in archive_path.read_text().splitlines()]
    assert archived == ["q0", "q1", "q2"]
    live = [json.loads(l)["question"] for l in log_file.read_text().splitlines()]
    assert live == ["q3", "q4"]


def test_rotation_never_raises(tmp_path, monkeypatch):
    bad_path = tmp_path / "is_a_dir"
    bad_path.mkdir()
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG", str(bad_path))
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG_MAX_RECORDS", "1")
    monkeypatch.delenv("GRAPHIFY_QUERY_LOG_DISABLE", raising=False)
    log_query(kind="query", question="q", corpus="/g.json")


def test_rotation_archive_after_live_replace(tmp_path, monkeypatch):
    log_file = _rotation_env(monkeypatch, tmp_path, max_records=2)
    log_query(kind="query", question="q0", corpus="/g.json")
    log_query(kind="query", question="q1", corpus="/g.json")

    def fail_replace(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    log_query(kind="query", question="q2", corpus="/g.json")

    archive = _archive_path(log_file)
    assert not archive.exists() or archive.read_text() == ""
    live = [json.loads(l)["question"] for l in log_file.read_text().splitlines()]
    assert live == ["q0", "q1", "q2"]


def test_rotation_concurrent_appends_preserved(tmp_path, monkeypatch):
    log_file = _rotation_env(monkeypatch, tmp_path, max_records=5)
    errors: list[Exception] = []

    def worker(prefix: str) -> None:
        try:
            for i in range(5):
                log_query(kind="query", question=f"{prefix}{i}", corpus="/g.json")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(p,)) for p in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors

    questions: set[str] = set()
    for path in (log_file, _archive_path(log_file)):
        if path.exists():
            for line in path.read_text().splitlines():
                questions.add(json.loads(line)["question"])
    assert len(questions) == 10


def test_rotation_lock_open_failure_still_appends(tmp_path, monkeypatch):
    log_file = _rotation_env(monkeypatch, tmp_path, max_records=3)
    real_open = open

    def selective_open(file, *args, **kwargs):
        if str(file).endswith(".lock"):
            raise OSError("simulated lock open failure")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", selective_open)
    log_query(kind="query", question="q0", corpus="/g.json")
    assert log_file.exists()
    rec = json.loads(log_file.read_text())
    assert rec["question"] == "q0"


def test_rotation_archive_failure_restores_overflow(tmp_path, monkeypatch):
    log_file = _rotation_env(monkeypatch, tmp_path, max_records=2)
    archive = _archive_path(log_file)
    real_open = Path.open

    def selective_open(self, *args, **kwargs):
        if self == archive and args and args[0] == "a":
            raise OSError("simulated archive failure")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", selective_open)
    for i in range(3):
        log_query(kind="query", question=f"q{i}", corpus="/g.json")

    live = [json.loads(l)["question"] for l in log_file.read_text().splitlines()]
    assert live == ["q1", "q2", "q0"]
    assert not archive.exists() or archive.read_text() == ""
