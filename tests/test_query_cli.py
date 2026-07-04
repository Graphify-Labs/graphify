"""Tests for graphify query CLI context filtering."""
from __future__ import annotations

import json

import networkx as nx
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod


def _write_graph(tmp_path):
    G = nx.Graph()
    G.add_node("n1", label="extract", source_file="extract.py", source_location="L10", community=0)
    G.add_node("n2", label="cluster", source_file="cluster.py", source_location="L5", community=0)
    G.add_node("n3", label="build", source_file="build.py", source_location="L1", community=1)
    G.add_edge("n1", "n2", relation="calls", confidence="EXTRACTED", context="call")
    G.add_edge("n2", "n3", relation="imports", confidence="EXTRACTED", context="import")
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(json_graph.node_link_data(G, edges="links")))
    return graph_path


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


def _capture_query_args(monkeypatch):
    """Capture the depth/token_budget the query handler resolves.

    Stubs both consumers (``serve._query_graph_text`` and
    ``querylog.log_query``) since the handler imports them locally, and returns
    a dict the assertions read after ``main()`` runs.
    """
    import graphify.serve as servemod
    import graphify.querylog as querylogmod

    captured: dict[str, int] = {}

    def _fake_query(G, question, *, mode, depth, token_budget, context_filters):
        captured["depth"] = depth
        captured["token_budget"] = token_budget
        return "stub-result"

    def _fake_log(**kwargs):
        captured["log_depth"] = kwargs.get("depth")
        captured["log_budget"] = kwargs.get("token_budget")

    monkeypatch.setattr(servemod, "_query_graph_text", _fake_query)
    monkeypatch.setattr(querylogmod, "log_query", _fake_log)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    return captured


def test_query_cli_config_sets_budget_and_depth(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(tmp_path)
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "config.json").write_text(
        json.dumps({"query": {"default_budget": 4000, "default_depth": 3}}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    captured = _capture_query_args(monkeypatch)
    monkeypatch.setattr(
        mainmod.sys, "argv", ["graphify", "query", "extract", "--graph", str(graph_path)]
    )
    mainmod.main()
    assert captured["depth"] == 3
    assert captured["token_budget"] == 4000
    assert captured["log_depth"] == 3
    assert captured["log_budget"] == 4000


def test_query_cli_flags_override_config(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(tmp_path)
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "config.json").write_text(
        json.dumps({"query": {"default_budget": 4000, "default_depth": 3}}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    captured = _capture_query_args(monkeypatch)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "extract", "--budget", "1000", "--depth", "5", "--graph", str(graph_path)],
    )
    mainmod.main()
    assert captured["depth"] == 5
    assert captured["token_budget"] == 1000


def test_query_cli_no_config_uses_builtin_defaults(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(tmp_path)
    monkeypatch.chdir(tmp_path)  # no graphify-out/config.json here
    captured = _capture_query_args(monkeypatch)
    monkeypatch.setattr(
        mainmod.sys, "argv", ["graphify", "query", "extract", "--graph", str(graph_path)]
    )
    mainmod.main()
    assert captured["depth"] == 2
    assert captured["token_budget"] == 2000


def test_query_cli_malformed_config_falls_back(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(tmp_path)
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "config.json").write_text("{not valid", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    captured = _capture_query_args(monkeypatch)
    monkeypatch.setattr(
        mainmod.sys, "argv", ["graphify", "query", "extract", "--graph", str(graph_path)]
    )
    mainmod.main()  # must not raise
    assert captured["depth"] == 2
    assert captured["token_budget"] == 2000


def test_query_cli_rejects_oversized_graph(monkeypatch, tmp_path, capsys):
    """#F4: query CLI must refuse to parse a graph.json that exceeds the cap."""
    import pytest

    graph_path = _write_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", 16)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "extract", "--graph", str(graph_path)],
    )
    with pytest.raises(SystemExit):
        mainmod.main()
    err = capsys.readouterr().err
    assert "exceeds" in err
    assert "byte cap" in err
