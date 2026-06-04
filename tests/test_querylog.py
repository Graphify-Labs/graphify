"""Tests for graphify.querylog."""
import json
import os
import pytest
from pathlib import Path

from graphify.querylog import log_query, nodes_from_result


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
