"""`graphify god-nodes` CLI subcommand (#2004 part 2).

god_nodes has long been an analyzer + MCP tool + README-advertised capability
but was never wired as a CLI subcommand, so `graphify god_nodes` errored with
"unknown command". These tests pin the subcommand (both spellings), its flags,
and that file nodes are excluded from the ranking.
"""
from __future__ import annotations

import json
import os

import networkx as nx
import pytest
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod


def _write_graph(tmp_path):
    g = nx.DiGraph()
    # A high-degree real entity (not a file/concept node): label != basename.
    g.add_node("hub", label="Auth", file_type="code", source_file="auth.py", source_location="L1")
    g.add_node("f", label="auth.py", file_type="code", source_file="auth.py", source_location=None)
    for i in range(4):
        g.add_node(f"caller{i}", label=f"c{i}()", file_type="code", source_file=f"m{i}.py", source_location="L1")
        g.add_edge(f"caller{i}", "hub", relation="calls", confidence="EXTRACTED")
    g.add_edge("f", "hub", relation="contains", confidence="EXTRACTED")
    gp = tmp_path / "graph.json"
    gp.write_text(json.dumps(json_graph.node_link_data(g, edges="links")), encoding="utf-8")
    return gp


def _run(monkeypatch, argv):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    mainmod.main()


def test_god_nodes_cli_text_output(monkeypatch, tmp_path, capsys):
    gp = _write_graph(tmp_path)
    _run(monkeypatch, ["graphify", "god-nodes", "--graph", str(gp)])
    out = capsys.readouterr().out
    assert "God nodes (most connected):" in out
    assert "Auth" in out
    assert "edges" in out
    assert "auth.py" not in out  # file node excluded from the ranking


def test_god_nodes_cli_underscore_alias(monkeypatch, tmp_path, capsys):
    # The exact spelling from the issue title.
    gp = _write_graph(tmp_path)
    _run(monkeypatch, ["graphify", "god_nodes", "--graph", str(gp)])
    assert "Auth" in capsys.readouterr().out


def test_god_nodes_cli_top_limits(monkeypatch, tmp_path, capsys):
    gp = _write_graph(tmp_path)
    _run(monkeypatch, ["graphify", "god-nodes", "--graph", str(gp), "--top", "1"])
    body = capsys.readouterr().out
    assert body.count(" edges") == 1


def test_god_nodes_cli_json(monkeypatch, tmp_path, capsys):
    gp = _write_graph(tmp_path)
    _run(monkeypatch, ["graphify", "god-nodes", "--graph", str(gp), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list) and data
    assert {"id", "label", "degree"} <= set(data[0])
    assert data[0]["label"] == "Auth"


def test_god_nodes_cli_missing_graph_errors(monkeypatch, tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, ["graphify", "god-nodes", "--graph", str(tmp_path / "nope.json")])
    assert exc.value.code == 1
    assert "graph file not found" in capsys.readouterr().err


def test_god_nodes_cli_stamps_orientation_and_logs(monkeypatch, tmp_path, capsys):
    """`god-nodes` is orientation, same as query/path/explain (#3042's
    "regardless of door" reasoning applied to the CLI): a successful run must
    refresh the strict guard's freshness stamp AND write a query-ledger line.
    """
    gp = _write_graph(tmp_path)
    stamp = tmp_path / "cache" / "last_query_stamp"
    stamp.parent.mkdir(parents=True)
    stamp.write_text("0")
    os.utime(stamp, (0, 0))  # aged: the mtime must ADVANCE, not merely exist
    log_file = tmp_path / "queries.jsonl"
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG", str(log_file))
    monkeypatch.delenv("GRAPHIFY_QUERY_LOG_DISABLE", raising=False)

    _run(monkeypatch, ["graphify", "god-nodes", "--graph", str(gp), "--top", "3"])

    out = capsys.readouterr().out
    assert "God nodes (most connected):" in out
    assert stamp.stat().st_mtime > 0  # refreshed past the aged epoch mtime
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["kind"] == "god_nodes"
    assert rec["question"] == "top 3"
    assert rec["corpus"] == str(gp.resolve())
    # The ledger count is exactly the number of hubs the run printed (one
    # ranked line per hub, each ending "N edges") — not the --top ceiling.
    printed = out.count(" edges")
    assert printed >= 1
    assert rec["nodes_returned"] == printed
