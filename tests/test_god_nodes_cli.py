"""`graphify god-nodes` CLI subcommand (#2004 part 2).

god_nodes has long been an analyzer + MCP tool + README-advertised capability
but was never wired as a CLI subcommand, so `graphify god_nodes` errored with
"unknown command". These tests pin the subcommand (both spellings), its flags,
and that file nodes are excluded from the ranking.
"""
from __future__ import annotations

import json

import pytest

import graphify.__main__ as mainmod
from tests.native_helpers import make_loaded


def _write_graph(tmp_path):
    nodes = [
        {"id": "hub", "label": "Auth", "file_type": "code", "source_file": "auth.py", "source_location": "L1"},
        {"id": "f", "label": "auth.py", "file_type": "code", "source_file": "auth.py", "source_location": None},
    ]
    edges = []
    for i in range(4):
        nodes.append({"id": f"caller{i}", "label": f"c{i}()", "file_type": "code", "source_file": f"m{i}.py", "source_location": "L1"})
        edges.append({"source": f"caller{i}", "target": "hub", "relation": "calls", "confidence": "EXTRACTED"})
    edges.append({"source": "f", "target": "hub", "relation": "contains", "confidence": "EXTRACTED"})
    return make_loaded(tmp_path, nodes=nodes, edges=edges, kind="digraph").store_path


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
        _run(monkeypatch, ["graphify", "god-nodes", "--store", str(tmp_path / "nope.helix")])
    assert exc.value.code == 1
    assert "not found" in capsys.readouterr().err
