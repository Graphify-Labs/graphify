"""Tests for graphify.chronicle — structural diff between two graph snapshots."""
from __future__ import annotations

import json

from graphify.chronicle import diff_graphs, format_diff, load_graph_from_text


def _snapshot(nodes, links, *, edges_key="links") -> str:
    return json.dumps({"directed": False, "multigraph": False, "graph": {}, "nodes": nodes, edges_key: links})


def _old() -> str:
    return _snapshot(
        [
            {"id": "a", "label": "a()", "community": 0, "community_name": "core"},
            {"id": "b", "label": "b()", "community": 0, "community_name": "core"},
            {"id": "c", "label": "c()", "community": 1, "community_name": "legacy"},
        ],
        [
            {"source": "a", "target": "b", "relation": "calls"},
            {"source": "b", "target": "c", "relation": "calls"},
        ],
    )


def _new() -> str:
    return _snapshot(
        [
            {"id": "a", "label": "a()", "community": 0, "community_name": "core"},
            {"id": "b", "label": "b()", "community": 0, "community_name": "core"},
            {"id": "d", "label": "d()", "community": 2, "community_name": "auth"},
            {"id": "e", "label": "e()", "community": 0, "community_name": "core"},
        ],
        [
            {"source": "a", "target": "b", "relation": "calls"},
            {"source": "a", "target": "d", "relation": "calls"},
            {"source": "a", "target": "e", "relation": "calls"},
        ],
    )


def test_load_graph_from_text_edges_key():
    G = load_graph_from_text(_snapshot(
        [{"id": "x", "label": "x"}], [{"source": "x", "target": "x", "relation": "self"}], edges_key="edges"
    ))
    assert G.number_of_nodes() == 1


def test_diff_node_counts_and_membership():
    diff = diff_graphs(load_graph_from_text(_old()), load_graph_from_text(_new()))
    assert diff["nodes"]["old_count"] == 3
    assert diff["nodes"]["new_count"] == 4
    assert diff["nodes"]["delta"] == 1
    added = {d["id"] for d in diff["nodes"]["added"]}
    removed = {d["id"] for d in diff["nodes"]["removed"]}
    assert added == {"d", "e"}
    assert removed == {"c"}


def test_diff_edges():
    diff = diff_graphs(load_graph_from_text(_old()), load_graph_from_text(_new()))
    assert any("--calls-->" in s and s.startswith("a ") for s in diff["edges"]["added"])
    # b->c existed before and is gone now.
    assert any(s.startswith("b ") for s in diff["edges"]["removed"])


def test_diff_communities():
    diff = diff_graphs(load_graph_from_text(_old()), load_graph_from_text(_new()))
    c = diff["communities"]
    assert "auth" in c["appeared"]
    assert "legacy" in c["disappeared"]
    core = next(r for r in c["resized"] if r["name"] == "core")
    assert core["old"] == 2 and core["new"] == 3 and core["delta"] == 1


def test_diff_god_nodes_emerged():
    # In _new, 'a' has degree 3 (a hub); in _old the top hub is different.
    diff = diff_graphs(load_graph_from_text(_old()), load_graph_from_text(_new()), top_god=1)
    emerged = {d["id"] for d in diff["god_nodes"]["emerged"]}
    vanished = {d["id"] for d in diff["god_nodes"]["vanished"]}
    assert "a" in emerged
    assert "b" in vanished  # b was the top-degree node in _old (degree 2), not in _new top-1


def test_diff_identical_is_empty():
    diff = diff_graphs(load_graph_from_text(_old()), load_graph_from_text(_old()))
    assert diff["nodes"]["delta"] == 0
    assert diff["nodes"]["added"] == [] and diff["nodes"]["removed"] == []
    assert diff["edges"]["added"] == [] and diff["edges"]["removed"] == []
    assert diff["god_nodes"]["emerged"] == [] and diff["god_nodes"]["vanished"] == []
    assert diff["communities"]["appeared"] == [] and diff["communities"]["disappeared"] == []


def test_format_diff_readable():
    diff = diff_graphs(load_graph_from_text(_old()), load_graph_from_text(_new()), top_god=1)
    text = format_diff(diff)
    assert "structural diff" in text
    assert "God-nodes emerged" in text
    assert "auth" in text  # appeared community named
