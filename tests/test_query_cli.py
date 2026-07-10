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


def test_query_cli_seed_file_accepts_node_id_strings(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(tmp_path)
    seed_path = tmp_path / "seeds.json"
    seed_path.write_text(json.dumps(["n3"]))
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "extract", "--seed-file", str(seed_path), "--graph", str(graph_path)],
    )
    mainmod.main()
    out = capsys.readouterr().out
    assert "Start: ['build']" in out


def test_query_cli_seed_file_deduplicates_node_ids(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(tmp_path)
    seed_path = tmp_path / "seeds.json"
    seed_path.write_text(json.dumps(["n3", "n2", "n2"]))
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "unmatched", "--seed-file", str(seed_path), "--graph", str(graph_path)],
    )
    mainmod.main()
    out = capsys.readouterr().out
    assert "Start: ['build', 'cluster']" in out
    assert out.index("NODE build") < out.index("NODE cluster")


def test_query_cli_seed_file_rejects_unknown_node(monkeypatch, tmp_path, capsys):
    import pytest

    graph_path = _write_graph(tmp_path)
    seed_path = tmp_path / "seeds.json"
    seed_path.write_text(json.dumps(["missing"]))
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "extract", "--seed-file", str(seed_path), "--graph", str(graph_path)],
    )
    with pytest.raises(SystemExit):
        mainmod.main()
    err = capsys.readouterr().err
    assert "seed node id not found" in err
    assert "missing" in err


def test_query_cli_seed_file_rejects_non_string_entries(monkeypatch, tmp_path, capsys):
    import pytest

    graph_path = _write_graph(tmp_path)
    seed_path = tmp_path / "seeds.json"
    seed_path.write_text(json.dumps([{"id": "n2"}]))
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "extract", "--seed-file", str(seed_path), "--graph", str(graph_path)],
    )
    with pytest.raises(SystemExit):
        mainmod.main()
    err = capsys.readouterr().err
    assert "seed file entries must be string node ids" in err


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
