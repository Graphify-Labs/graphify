"""Relationships in the query traversal the skill now uses.

The split-host query flow used to carry an inline NetworkX fallback
(``references/query/default.md``); #197 replaced it with ``graphify query``,
whose traversal lives in :mod:`graphify.serve` (``_query_graph_text`` ->
``_bfs``/``_dfs`` -> ``_complete_induced_edges`` -> ``_subgraph_to_text``).
These tests pin the relationship guarantees on that code path: a traversal
records a discovery tree, so ``_complete_induced_edges`` re-adds the edges
among visited nodes (seed-to-seed, cycles, cross-links), the undirected
renderer does not double an edge, and depth/budget limits still hold.
"""
from __future__ import annotations

from pathlib import Path

import networkx as nx
import pytest

from graphify.serve import _bfs, _dfs, _subgraph_to_text

REPO_ROOT = Path(__file__).resolve().parent.parent
QUERY_FRAGMENT = REPO_ROOT / "tools/skillgen/fragments/references/query/default.md"


def test_split_host_query_fragment_has_no_inline_fallback():
    """The split hosts call ``graphify query``; the inline fallback is gone."""
    fragment = QUERY_FRAGMENT.read_text(encoding="utf-8")
    assert "graphify query" in fragment
    assert "graphify pipeline vocab" in fragment
    assert "$(cat graphify-out/.graphify_python)" not in fragment
    assert "networkx.readwrite import json_graph" not in fragment


def _render(graph: nx.Graph, starts: list[str], *, mode: str, depth: int = 3,
            token_budget: int = 2000) -> str:
    traversal = _dfs if mode == "dfs" else _bfs
    nodes, edges = traversal(graph, starts, depth)
    return _subgraph_to_text(graph, nodes, edges, token_budget, seeds=starts)


@pytest.mark.parametrize("mode", ["bfs", "dfs"])
def test_traversal_keeps_edges_between_seed_nodes(mode):
    """Traversal visits all seeds, but must still render edges among them."""
    graph = nx.DiGraph()
    graph.add_node("a", label="Alpha")
    graph.add_node("b", label="Beta")
    graph.add_node("c", label="Gamma")
    graph.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    graph.add_edge("b", "c", relation="imports", confidence="INFERRED")
    graph.add_edge("a", "c", relation="uses", confidence="AMBIGUOUS")

    output = _render(graph, ["a", "b", "c"], mode=mode)

    assert "EDGE Alpha --calls [EXTRACTED]--> Beta" in output
    assert "EDGE Beta --imports [INFERRED]--> Gamma" in output
    assert "EDGE Alpha --uses [AMBIGUOUS]--> Gamma" in output


@pytest.mark.parametrize("mode", ["bfs", "dfs"])
def test_traversal_keeps_cycle_and_cross_links(mode):
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

    output = _render(graph, ["a"], mode=mode)

    assert output.count("EDGE ") == 5
    assert "EDGE Gamma --ca [INFERRED]--> Alpha" in output
    assert "EDGE Gamma --cd [AMBIGUOUS]--> Delta" in output


def test_traversal_avoids_duplicate_edges_in_undirected_graph():
    graph = nx.Graph()
    for node, label in [("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")]:
        graph.add_node(node, label=label)
    graph.add_edge("a", "b", relation="ab", confidence="EXTRACTED")
    graph.add_edge("b", "c", relation="bc", confidence="EXTRACTED")
    graph.add_edge("c", "a", relation="ca", confidence="EXTRACTED")

    output = _render(graph, ["a", "b", "c"], mode="bfs")

    assert output.count("EDGE ") == 3


def test_undirected_traversal_dedups_an_edge_by_unordered_pair():
    """``_complete_induced_edges`` keys undirected completions by frozenset, so a
    triangle yields three distinct edges, not six ordered duplicates."""
    graph = nx.Graph()
    for node in "abc":
        graph.add_node(node, label=node.upper())
    graph.add_edges_from([("a", "b"), ("b", "c"), ("c", "a")])
    _nodes, edges = _bfs(graph, ["a", "b", "c"], 3)
    assert len(edges) == len({frozenset(e) for e in edges}) == 3


def test_traversal_keeps_parallel_relationship_attributes():
    """Every parallel relation survives, not just the first (3ab2cbab)."""
    graph = nx.MultiDiGraph()
    graph.add_node("a", label="Alpha")
    graph.add_node("b", label="Beta")
    graph.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    graph.add_edge("a", "b", relation="imports", confidence="INFERRED")
    graph.add_edge("b", "a", relation="references", confidence="AMBIGUOUS")

    output = _render(graph, ["a", "b"], mode="bfs")

    assert output.count("EDGE ") == 3
    assert "EDGE Alpha --calls [EXTRACTED]--> Beta" in output
    assert "EDGE Alpha --imports [INFERRED]--> Beta" in output
    assert "EDGE Beta --references [AMBIGUOUS]--> Alpha" in output


@pytest.mark.parametrize(
    ("mode", "depth", "last_included", "first_excluded", "edge_count"),
    [("bfs", 3, 3, 4, 3), ("dfs", 6, 6, 7, 6)],
)
def test_traversal_does_not_include_edges_beyond_depth(
    mode, depth, last_included, first_excluded, edge_count
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

    output = _render(graph, ["n0"], mode=mode, depth=depth)

    assert f"NODE Node {last_included}" in output
    assert f"NODE Node {first_excluded}" not in output
    assert output.count("EDGE ") == edge_count
    assert (
        f"EDGE Node {last_included} --next [EXTRACTED]--> "
        f"Node {first_excluded}"
    ) not in output


def test_renderer_reports_when_output_exceeds_budget():
    graph = nx.Graph()
    graph.add_node("a", label="Alpha")
    graph.add_node("b", label="Beta")
    graph.add_edge("a", "b", relation="calls", confidence="EXTRACTED")

    output = _render(graph, ["a", "b"], mode="bfs", token_budget=1)

    assert "budget" in output
