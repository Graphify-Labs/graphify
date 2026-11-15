"""Regression tests for relationships in the generated query fallback."""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import networkx as nx
import pytest
from networkx.readwrite import json_graph


REPO_ROOT = Path(__file__).resolve().parent.parent
QUERY_FRAGMENT = REPO_ROOT / "tools/skillgen/fragments/references/query/default.md"
FALLBACK_OPEN = '$(cat graphify-out/.graphify_python) -c "\n'
FALLBACK_LOCATOR = (
    FALLBACK_OPEN
    + "import sys, json\nfrom networkx.readwrite import json_graph\n"
)
FALLBACK_END = '\n"\n```'


def _fallback_script() -> str:
    fragment = QUERY_FRAGMENT.read_text(encoding="utf-8")
    start = fragment.index(FALLBACK_LOCATOR) + len(FALLBACK_OPEN)
    end = fragment.index(FALLBACK_END, start)
    return fragment[start:end]


def _run_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    graph: nx.Graph,
    *,
    question: str,
    mode: str,
    token_budget: int = 2000,
) -> str:
    try:
        data = json_graph.node_link_data(graph, edges="links")
    except TypeError:  # NetworkX before the ``edges`` keyword.
        data = json_graph.node_link_data(graph)
    output_dir = tmp_path / "graphify-out"
    output_dir.mkdir()
    (output_dir / "graph.json").write_text(json.dumps(data), encoding="utf-8")

    script = _fallback_script()
    # The payload is embedded in a double-quoted shell argument. Unescape the
    # quotes that the shell would remove before compiling its Python body.
    script = script.replace(chr(92) + '"', '"')
    script = script.replace("question = 'QUESTION'", f"question = {question!r}")
    script = script.replace("mode = 'MODE'  # 'bfs' or 'dfs'", f"mode = {mode!r}")
    script = script.replace(
        "token_budget = BUDGET  # default 2000",
        f"token_budget = {token_budget}",
    )
    assert "'QUESTION'" not in script
    assert "'MODE'" not in script
    assert "BUDGET" not in script

    monkeypatch.chdir(tmp_path)
    output = io.StringIO()
    with redirect_stdout(output):
        exec(compile(script, str(QUERY_FRAGMENT), "exec"), {"__name__": "__main__"})
    return output.getvalue()


@pytest.mark.parametrize("mode", ["bfs", "dfs"])
def test_fallback_keeps_edges_between_seed_nodes(tmp_path, monkeypatch, mode):
    """Traversal visits all seeds, but must still render edges among them."""
    graph = nx.DiGraph()
    graph.add_node("a", label="Alpha")
    graph.add_node("b", label="Beta")
    graph.add_node("c", label="Gamma")
    graph.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    graph.add_edge("b", "c", relation="imports", confidence="INFERRED")
    graph.add_edge("a", "c", relation="uses", confidence="AMBIGUOUS")

    output = _run_fallback(
        tmp_path, monkeypatch, graph, question="alpha beta gamma", mode=mode
    )

    assert "  EDGE Alpha --calls [EXTRACTED]--> Beta" in output
    assert "  EDGE Beta --imports [INFERRED]--> Gamma" in output
    assert "  EDGE Alpha --uses [AMBIGUOUS]--> Gamma" in output


@pytest.mark.parametrize("mode", ["bfs", "dfs"])
def test_fallback_keeps_cycle_and_cross_links(tmp_path, monkeypatch, mode):
    graph = nx.DiGraph()
    for node, label in [
        ("a", "Alpha"),
        ("b", "Beta"),
        ("c", "Gamma"),
        ("d", "Delta"),
    ]:
        graph.add_node(node, label=label)
    graph.add_edge("a", "b", relation="ab", confidence="EXTRACTED")
    graph.add_edge("b", "c", relation="bc", confidence="EXTRACTED")
    graph.add_edge("c", "a", relation="ca", confidence="INFERRED")
    graph.add_edge("b", "d", relation="bd", confidence="EXTRACTED")
    graph.add_edge("c", "d", relation="cd", confidence="AMBIGUOUS")

    output = _run_fallback(
        tmp_path, monkeypatch, graph, question="alpha", mode=mode
    )

    assert output.count("  EDGE ") == 5
    assert "  EDGE Gamma --ca [INFERRED]--> Alpha" in output
    assert "  EDGE Gamma --cd [AMBIGUOUS]--> Delta" in output


def test_fallback_avoids_duplicate_edges_in_undirected_graph(tmp_path, monkeypatch):
    graph = nx.Graph()
    for node, label in [("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")]:
        graph.add_node(node, label=label)
    graph.add_edge("a", "b", relation="ab", confidence="EXTRACTED")
    graph.add_edge("b", "c", relation="bc", confidence="EXTRACTED")
    graph.add_edge("c", "a", relation="ca", confidence="EXTRACTED")

    output = _run_fallback(
        tmp_path, monkeypatch, graph, question="alpha beta gamma", mode="bfs"
    )

    assert output.count("  EDGE ") == 3


def test_fallback_keeps_parallel_relationship_attributes(tmp_path, monkeypatch):
    graph = nx.MultiDiGraph()
    graph.add_node("a", label="Alpha")
    graph.add_node("b", label="Beta")
    graph.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    graph.add_edge("a", "b", relation="imports", confidence="INFERRED")
    graph.add_edge("b", "a", relation="references", confidence="AMBIGUOUS")

    output = _run_fallback(
        tmp_path, monkeypatch, graph, question="alpha beta", mode="bfs"
    )

    assert output.count("  EDGE ") == 3
    assert "  EDGE Alpha --calls [EXTRACTED]--> Beta" in output
    assert "  EDGE Alpha --imports [INFERRED]--> Beta" in output
    assert "  EDGE Beta --references [AMBIGUOUS]--> Alpha" in output


@pytest.mark.parametrize(
    ("mode", "last_included", "first_excluded", "edge_count"),
    [("bfs", 3, 4, 3), ("dfs", 6, 7, 6)],
)
def test_fallback_does_not_include_edges_beyond_depth(
    tmp_path,
    monkeypatch,
    mode,
    last_included,
    first_excluded,
    edge_count,
):
    graph = nx.DiGraph()
    graph.add_node("n0", label="Alpha")
    for index in range(1, first_excluded + 1):
        graph.add_node(f"n{index}", label=f"Node {index}")
    for index in range(first_excluded):
        graph.add_edge(
            f"n{index}",
            f"n{index + 1}",
            relation="next",
            confidence="EXTRACTED",
        )

    output = _run_fallback(
        tmp_path, monkeypatch, graph, question="alpha", mode=mode
    )

    assert f"NODE Node {last_included}" in output
    assert f"NODE Node {first_excluded}" not in output
    assert output.count("  EDGE ") == edge_count
    assert (
        f"  EDGE Node {last_included} --next [EXTRACTED]--> "
        f"Node {first_excluded}"
    ) not in output


def test_fallback_output_budget_still_truncates(tmp_path, monkeypatch):
    graph = nx.Graph()
    graph.add_node("a", label="Alpha")
    graph.add_node("b", label="Beta")
    graph.add_edge("a", "b", relation="calls", confidence="EXTRACTED")

    output = _run_fallback(
        tmp_path,
        monkeypatch,
        graph,
        question="alpha beta",
        mode="bfs",
        token_budget=1,
    )

    assert "truncated at ~1 token budget" in output
