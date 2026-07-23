"""Tests for graphify query CLI context filtering."""
from __future__ import annotations

import graphify.__main__ as mainmod
from tests.native_helpers import make_loaded


def _write_graph(tmp_path):
    return make_loaded(
        tmp_path,
        nodes=[
            {"id": "n1", "label": "extract", "source_file": "extract.py", "source_location": "L10", "community": 0},
            {"id": "n2", "label": "cluster", "source_file": "cluster.py", "source_location": "L5", "community": 0},
            {"id": "n3", "label": "build", "source_file": "build.py", "source_location": "L1", "community": 1},
        ],
        edges=[
            {"source": "n1", "target": "n2", "relation": "calls", "confidence": "EXTRACTED", "context": "call"},
            {"source": "n2", "target": "n3", "relation": "imports", "confidence": "EXTRACTED", "context": "import"},
        ],
    ).store_path


def test_query_cli_explicit_context_filter(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "extract", "--context", "call", "--graph", str(graph_path)],
    )
    mainmod.main()
    out = capsys.readouterr().out
    assert "Context: call (explicit)" in out
    assert "cluster" in out
    assert "build" not in out


def test_query_cli_heuristic_context_filter(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "who calls extract", "--graph", str(graph_path)],
    )
    mainmod.main()
    out = capsys.readouterr().out
    assert "Context: call (heuristic)" in out
    assert "cluster" in out
    assert "build" not in out


def test_query_dfs_flag(monkeypatch, tmp_path):
    """The public CLI must forward ``--dfs`` to the native traversal."""
    graph_path = _write_graph(tmp_path)
    seen = {}

    def _query(graph, question, **kwargs):
        seen.update(question=question, **kwargs)
        return "ok"

    monkeypatch.setattr("graphify.serve._query_graph_text", _query)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "extract", "--dfs", "--graph", str(graph_path)],
    )

    mainmod.main()

    assert seen["question"] == "extract"
    assert seen["mode"] == "dfs"


def test_query_budget_flag(monkeypatch, tmp_path):
    """The public CLI must pass the requested token budget to native query."""
    graph_path = _write_graph(tmp_path)
    seen = {}

    def _query(graph, question, **kwargs):
        seen.update(question=question, **kwargs)
        return "ok"

    monkeypatch.setattr("graphify.serve._query_graph_text", _query)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        [
            "graphify", "query", "extract", "--budget", "500",
            "--graph", str(graph_path),
        ],
    )

    mainmod.main()

    assert seen["question"] == "extract"
    assert seen["token_budget"] == 500


def _write_calls_graph(tmp_path):
    return make_loaded(
        tmp_path,
        nodes=[
            {
                "id": "caller",
                "label": "caller_fn",
                "source_file": "a.py",
                "source_location": "L1",
                "community": 0,
            },
            {
                "id": "callee",
                "label": "callee_fn",
                "source_file": "b.py",
                "source_location": "L1",
                "community": 1,
            },
        ],
        edges=[{
            "source": "caller",
            "target": "callee",
            "relation": "calls",
            "confidence": "EXTRACTED",
            "context": "call",
        }],
    ).store_path


def test_query_cli_preserves_calls_direction_when_seeded_on_callee(
    monkeypatch, tmp_path, capsys
):
    graph_path = _write_calls_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "callee_fn", "--store", str(graph_path)],
    )

    mainmod.main()

    output = capsys.readouterr().out
    assert "caller_fn --calls" in output
    assert "callee_fn --calls" not in output


def test_query_cli_preserves_calls_direction_when_seeded_on_caller(
    monkeypatch, tmp_path, capsys
):
    graph_path = _write_calls_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "caller_fn", "--store", str(graph_path)],
    )

    mainmod.main()

    output = capsys.readouterr().out
    assert "caller_fn --calls" in output
    assert "callee_fn --calls" not in output
