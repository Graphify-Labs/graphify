"""#4940: the #479 write guard must tell a node that entity dedup folded into a
twin from a node that was lost.

The tests assert on what reaches graph.json and on whether ``to_json`` wrote,
never on how the guard is wired, so they hold for any fix of the same bug.
"""
from __future__ import annotations

import json

import networkx as nx

from graphify.build import build_merge
from graphify.cluster import cluster
from graphify.export import to_json


def _node(nid: str, label: str, source_file: str) -> dict:
    return {"id": nid, "label": label, "file_type": "concept",
            "source_file": source_file, "_origin": "semantic"}


def _edge(source: str, target: str, source_file: str) -> dict:
    return {"source": source, "target": target, "relation": "references",
            "confidence": "EXTRACTED", "source_file": source_file, "_origin": "semantic"}


def _seed(path, nodes, edges=()):
    G = nx.Graph()
    for n in nodes:
        G.add_node(n["id"], **{k: v for k, v in n.items() if k != "id"})
    for e in edges:
        G.add_edge(e["source"], e["target"],
                   **{k: v for k, v in e.items() if k not in ("source", "target")})
    to_json(G, {0: [n["id"] for n in nodes]}, str(path), force=True)


def _merge_and_write(tmp_path, saved, fresh, saved_edges=(), tamper=None):
    """Seed graph.json, merge ``fresh`` into it the way ``--update`` does, then
    write with the default (guarded) ``to_json``. ``tamper`` edits the merged
    graph to stand in for a loss that happens after dedup."""
    graph_path = tmp_path / "graph.json"
    _seed(graph_path, saved, saved_edges)
    G = build_merge([{"nodes": fresh, "edges": [], "hyperedges": []}],
                    graph_path=graph_path, root=str(tmp_path))
    if tamper is not None:
        tamper(G)
    written = to_json(G, cluster(G), str(graph_path))
    return written, json.loads(graph_path.read_text())


ALPHA = _node("claude_a", "Alpha concept", "CLAUDE.md")
BRAVO = _node("glossary_b", "Bravo concept", "GLOSSARY.md")


# The guard's existing job. These pass before the fix and must keep passing.

def test_update_with_nothing_merged_or_lost_is_written(tmp_path):
    written, disk = _merge_and_write(tmp_path, [ALPHA, BRAVO], [BRAVO])
    assert written is True
    assert {n["id"] for n in disk["nodes"]} == {"claude_a", "glossary_b"}


def test_a_saved_node_that_is_gone_is_still_refused(tmp_path, capsys):
    written, disk = _merge_and_write(
        tmp_path, [ALPHA, BRAVO], [BRAVO], tamper=lambda G: G.remove_node("claude_a"),
    )
    assert written is False
    assert "claude_a" in capsys.readouterr().err
    assert {n["id"] for n in disk["nodes"]} == {"claude_a", "glossary_b"}


def test_a_re_extracted_node_dropped_after_the_merge_is_still_refused(tmp_path):
    written, disk = _merge_and_write(
        tmp_path, [ALPHA, BRAVO], [BRAVO], tamper=lambda G: G.remove_node("glossary_b"),
    )
    assert written is False
    assert "glossary_b" in {n["id"] for n in disk["nodes"]}
