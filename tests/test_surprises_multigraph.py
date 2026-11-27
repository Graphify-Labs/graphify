"""Surprising connections on a multigraph that has no communities (#5444)."""
from __future__ import annotations

import subprocess
import sys

import networkx as nx
import pytest

from graphify.analyze import surprising_connections
from graphify.serve import _communities_from_graph, _read_graph


def _graph(cls, edges):
    """One-file graph from (source, target, relation) edges, no communities."""
    G = cls()
    for node in dict.fromkeys(n for u, v, _ in edges for n in (u, v)):
        G.add_node(node, label=node, file_type="code", source_file="m.py")
    for u, v, relation in edges:
        G.add_edge(u, v, relation=relation, confidence="EXTRACTED")
    return G


def _rows(found):
    return [(s["source"], s["target"], s["relation"], s["note"]) for s in found]


PATH = [("a", "b", "calls"), ("b", "c", "calls"), ("c", "d", "calls")]


@pytest.mark.parametrize("multi, simple", [
    (nx.MultiGraph, nx.Graph), (nx.MultiDiGraph, nx.DiGraph)])
def test_multigraph_without_parallel_edges_matches_simple_graph(multi, simple):
    assert _rows(surprising_connections(_graph(multi, PATH), {})) == _rows(
        surprising_connections(_graph(simple, PATH), {}))


@pytest.mark.parametrize("multi, simple", [
    (nx.MultiGraph, nx.Graph), (nx.MultiDiGraph, nx.DiGraph)])
def test_parallel_edges_share_the_score_of_their_pair(multi, simple):
    """b-c is the middle of the path, so it ranks first however many edges it has."""
    expected = _rows(surprising_connections(_graph(simple, PATH), {}))
    found = _rows(surprising_connections(
        _graph(multi, PATH + [("b", "c", "references")]), {}, top_n=10))
    (source, target, _, note), *rest = expected
    assert found == [(source, target, "calls", note),
                     (source, target, "references", note), *rest]


@pytest.mark.parametrize("cls", [nx.MultiGraph, nx.MultiDiGraph])
def test_top_n_counts_edges_not_pairs(cls):
    G = _graph(cls, PATH + [("b", "c", "references")])
    assert [s["relation"] for s in surprising_connections(G, {}, top_n=2)] == [
        "calls", "references"]


def test_no_cluster_graph_with_parallel_edges(tmp_path):
    """End to end: m() both references and calls B, so the pair has two edges."""
    (tmp_path / "m.py").write_text(
        "class B:\n    pass\n"
        "class A(B):\n    def m(self, x: B) -> B:\n        return B()\n",
        encoding="utf-8")
    subprocess.run(
        [sys.executable, "-m", "graphify", "extract", str(tmp_path),
         "--code-only", "--no-cluster"],
        check=True, capture_output=True, text=True, encoding="utf-8")

    G = _read_graph(str(tmp_path / "graphify-out" / "graph.json"))
    assert G.is_multigraph()
    assert _communities_from_graph(G) == {}
    relations = [s["relation"] for s in surprising_connections(G, {}, top_n=20)
                 if (s["source"], s["target"]) == (".m()", "B")]
    assert sorted(relations) == ["calls", "references"]
