"""`graphify cycles` CLI subcommand tests."""
from __future__ import annotations

import json

import networkx as nx
import pytest
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod


def _write_cycle_graph(tmp_path):
    g = nx.DiGraph()
    g.add_node("a", label="a.py", file_type="code", source_file="a.py")
    g.add_node("b", label="b.py", file_type="code", source_file="b.py")
    g.add_node("c", label="c.py", file_type="code", source_file="c.py")
    g.add_node("d", label="d.py", file_type="code", source_file="d.py")
    # 2-file cycle: a.py <-> b.py
    g.add_edge("a", "b", relation="imports_from", source_file="a.py", confidence="EXTRACTED")
    g.add_edge("b", "a", relation="imports_from", source_file="b.py", confidence="EXTRACTED")
    # 3-file cycle: b.py -> c.py -> d.py -> b.py
    g.add_edge("b", "c", relation="imports_from", source_file="b.py", confidence="EXTRACTED")
    g.add_edge("c", "d", relation="imports_from", source_file="c.py", confidence="EXTRACTED")
    g.add_edge("d", "b", relation="imports_from", source_file="d.py", confidence="EXTRACTED")
    gp = tmp_path / "graph.json"
    gp.write_text(json.dumps(json_graph.node_link_data(g, edges="links")), encoding="utf-8")
    return gp


def _write_acyclic_graph(tmp_path):
    g = nx.DiGraph()
    g.add_node("a", label="a.py", file_type="code", source_file="a.py")
    g.add_node("b", label="b.py", file_type="code", source_file="b.py")
    g.add_edge("a", "b", relation="imports_from", source_file="a.py", confidence="EXTRACTED")
    gp = tmp_path / "acyclic.json"
    gp.write_text(json.dumps(json_graph.node_link_data(g, edges="links")), encoding="utf-8")
    return gp


def _run(monkeypatch, argv):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    mainmod.main()


def test_cycles_cli_text_output(monkeypatch, tmp_path, capsys):
    gp = _write_cycle_graph(tmp_path)
    _run(monkeypatch, ["graphify", "cycles", "--graph", str(gp)])
    out = capsys.readouterr().out
    assert "Import cycles (2 found):" in out
    assert "a.py -> b.py -> a.py (length 2)" in out
    assert "b.py -> c.py -> d.py -> b.py (length 3)" in out


def test_cycles_cli_aliases_and_empty_graph(monkeypatch, tmp_path, capsys):
    gp = _write_acyclic_graph(tmp_path)
    _run(monkeypatch, ["graphify", "import-cycles", "--graph", str(gp)])
    assert "No circular import dependencies detected." in capsys.readouterr().out


def test_cycles_cli_max_length_and_top(monkeypatch, tmp_path, capsys):
    gp = _write_cycle_graph(tmp_path)
    _run(monkeypatch, ["graphify", "cycles", "--graph", str(gp), "--max-length", "2"])
    out = capsys.readouterr().out
    assert "Import cycles (1 found):" in out
    assert "length 2" in out
    assert "length 3" not in out

    _run(monkeypatch, ["graphify", "cycles", "--graph", str(gp), "--top=1"])
    out_top = capsys.readouterr().out
    assert "Import cycles (1 found):" in out_top


def test_cycles_cli_json(monkeypatch, tmp_path, capsys):
    gp = _write_cycle_graph(tmp_path)
    _run(monkeypatch, ["graphify", "cycles", "--graph", str(gp), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list) and len(data) == 2
    assert data[0] == {"cycle": ["a.py", "b.py"], "length": 2, "why": "circular dependency"}


def test_cycles_cli_missing_graph_errors(monkeypatch, tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, ["graphify", "cycles", "--graph", str(tmp_path / "missing.json")])
    assert exc.value.code == 1
    assert "graph file not found" in capsys.readouterr().err
