from __future__ import annotations

import json

import networkx as nx
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod


def test_affected_cli_production_only_excludes_test_results(monkeypatch, tmp_path, capsys) -> None:
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
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        [
            "graphify",
            "affected",
            "Target",
            "--production-only",
            "--graph",
            str(graph_path),
        ],
    )

    mainmod.main()

    output = capsys.readouterr().out
    assert "src/caller.ts" in output
    assert "src/__tests__/caller.test.ts" not in output


def test_help_lists_affected_production_only(monkeypatch, capsys) -> None:
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "--help"])

    mainmod.main()

    assert "--production-only" in capsys.readouterr().out
