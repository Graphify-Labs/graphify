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


def _write_recency_graph(tmp_path):
    """Two equal-length 'widget' matches differing only in age.

    captured_at values are decades apart (2000 vs 2999), so recency ranking is
    stable for any real wall-clock `now` — the CLI has no now-injection, so the
    test must not depend on the exact current date. The far-past node keeps the
    alphabetically-smaller id ('a_old') so the recency-off node-id tie-break puts
    it first, making the recency-on flip to 'z_new' unambiguous.
    """
    G = nx.Graph()
    G.add_node("a_old", label="widget aaa", source_file="a.py", source_location="L1",
               community=0, captured_at="2000-01-01T00:00:00+00:00")
    G.add_node("z_new", label="widget bbb", source_file="b.py", source_location="L1",
               community=0, captured_at="2999-01-01T00:00:00+00:00")
    G.add_edge("a_old", "z_new", relation="calls", confidence="EXTRACTED", context="call")
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(json_graph.node_link_data(G, edges="links")))
    return graph_path


def _run_query(monkeypatch, capsys, argv):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    mainmod.main()
    return capsys.readouterr().out


def test_query_cli_recency_off_by_default(monkeypatch, tmp_path, capsys):
    """Without --recency the age is ignored: older node seeds first (node-id order)."""
    graph_path = _write_recency_graph(tmp_path)
    out = _run_query(
        monkeypatch, capsys,
        ["graphify", "query", "widget", "--graph", str(graph_path)],
    )
    header = out.splitlines()[0]
    assert header.index("widget aaa") < header.index("widget bbb")


def test_query_cli_recency_flag_shifts_to_newer(monkeypatch, tmp_path, capsys):
    """--recency promotes the newer node ahead of an equally-matching older one."""
    graph_path = _write_recency_graph(tmp_path)
    out = _run_query(
        monkeypatch, capsys,
        ["graphify", "query", "widget", "--recency", "--graph", str(graph_path)],
    )
    header = out.splitlines()[0]
    assert header.index("widget bbb") < header.index("widget aaa")


def test_query_cli_half_life_days_parsed(monkeypatch, tmp_path, capsys):
    """--half-life-days is accepted alongside --recency (and doesn't crash)."""
    graph_path = _write_recency_graph(tmp_path)
    out = _run_query(
        monkeypatch, capsys,
        ["graphify", "query", "widget", "--recency", "--half-life-days", "7", "--graph", str(graph_path)],
    )
    header = out.splitlines()[0]
    assert header.index("widget bbb") < header.index("widget aaa")


def test_query_cli_half_life_days_rejects_non_number(monkeypatch, tmp_path, capsys):
    import pytest
    graph_path = _write_recency_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "query", "widget", "--half-life-days", "soon", "--graph", str(graph_path)],
    )
    with pytest.raises(SystemExit):
        mainmod.main()
    assert "--half-life-days must be a number" in capsys.readouterr().err


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
