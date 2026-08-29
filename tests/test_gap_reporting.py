"""Focused report tests for actionable versus benign graph gaps."""

import networkx as nx

from graphify.report import generate


def _generate(graph: nx.Graph, communities: dict[int, list[str]]) -> str:
    return generate(
        graph,
        communities,
        {community_id: 0.0 for community_id in communities},
        {community_id: f"Community {community_id}" for community_id in communities},
        [],
        [],
        {
            "total_files": 3,
            "total_words": 30,
            "needs_graph": True,
            "warning": None,
        },
        {"input": 0, "output": 0},
        "./project",
    )


def test_report_separates_actionable_and_benign_isolated_nodes():
    graph = nx.Graph()
    graph.add_node(
        "local",
        label="LocalService",
        file_type="code",
        source_file="src/local.py",
    )
    graph.add_node("external", label="Flask", file_type="code", external=True)
    graph.add_node(
        "reason",
        label="Decision",
        file_type="rationale",
        source_file="src/local.py",
    )

    report = _generate(
        graph,
        communities={0: ["local"], 1: ["external"], 2: ["reason"]},
    )

    assert "1 actionable isolated node(s)" in report
    assert "external: 1" in report
    assert "rationale: 1" in report
    assert "`LocalService`" in report


def test_report_marks_all_benign_thin_community_non_actionable():
    graph = nx.Graph()
    graph.add_node(
        "external",
        label="parametrize",
        file_type="code",
        external=True,
    )

    report = _generate(graph, communities={0: ["external"]})

    assert "benign thin communities: 1" in report
    assert "actionable thin communities: 0" in report
