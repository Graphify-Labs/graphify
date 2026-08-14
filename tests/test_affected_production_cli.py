from __future__ import annotations

import json

import networkx as nx
import pytest
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod


def _write_graph(tmp_path):
    graph = nx.DiGraph()
    graph.add_node("target", label="Target()", source_file="src/target.ts")
    graph.add_node("caller", label="Caller()", source_file="src/caller.ts")
    graph.add_node("test", label="TestCaller()", source_file="src/__tests__/caller.test.ts")
    graph.add_edge("caller", "target", relation="calls")
    graph.add_edge("test", "target", relation="calls")
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps(json_graph.node_link_data(graph, edges="links")),
        encoding="utf-8",
    )
    return graph_path


def _run(monkeypatch, graph_path, *args: str) -> None:
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "affected", *args, "--graph", str(graph_path)],
    )

    mainmod.main()


def test_affected_cli_production_only_excludes_test_results(monkeypatch, tmp_path, capsys) -> None:
    graph_path = _write_graph(tmp_path)

    _run(monkeypatch, graph_path, "Target", "--production-only")

    output = capsys.readouterr().out
    assert "src/caller.ts" in output
    assert "src/__tests__/caller.test.ts" not in output
    assert "Scope: production only (tests, eval, docs excluded)" in output


def test_production_only_is_order_independent(monkeypatch, tmp_path, capsys) -> None:
    graph_path = _write_graph(tmp_path)

    _run(monkeypatch, graph_path, "--production-only", "Target")

    output = capsys.readouterr().out
    assert "src/caller.ts" in output
    assert "src/__tests__/caller.test.ts" not in output


@pytest.mark.parametrize("bad_flag", ["--production-onl", "--production-only=false"])
def test_unknown_production_flags_fail_closed(monkeypatch, tmp_path, capsys, bad_flag: str) -> None:
    graph_path = _write_graph(tmp_path)

    with pytest.raises(SystemExit) as error:
        _run(monkeypatch, graph_path, "Target", bad_flag)

    assert error.value.code == 2
    assert "unknown affected option" in capsys.readouterr().err


def test_affected_help_is_command_specific(monkeypatch, capsys) -> None:
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "affected", "--help"])

    mainmod.main()

    output = capsys.readouterr().out
    assert "Usage: graphify affected" in output
    assert "authorizeCollection --production-only" in output


def test_help_lists_affected_production_only(monkeypatch, capsys) -> None:
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "--help"])

    mainmod.main()

    assert "--production-only" in capsys.readouterr().out
