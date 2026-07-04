"""Degree-drop alert for build_merge (#1652b, guards the #1651 collapse vector).

Incremental --update REPLACES each re-extracted file's prior nodes/edges. If a
re-extraction emits a DIFFERENT id for an entity that already exists as a hub,
the old hub and its in-file edges are dropped and its cross-file edges are
orphaned onto a bare node — the hub silently collapses from many edges to ~0
while the node count may not shrink, so the count-based shrink guard never fires.
build_merge now snapshots pre-merge hub degrees and WARNS (not raises) when a
former hub vanishes or loses more than DEGREE_DROP_FRAC of its degree. The alert
is active on the normal dedup=True path (the shrink guard is not).
"""
from __future__ import annotations

import json

from graphify.build import (
    DEGREE_DROP_FRAC,
    HUB_DEGREE_MIN,
    _hub_degree_drops,
    _hub_degrees,
    build_merge,
)


def _write_graph(graph_path, nodes, edges) -> None:
    graph_path.write_text(
        json.dumps({"nodes": nodes, "edges": edges, "hyperedges": []}),
        encoding="utf-8",
    )


def _seed_hub_graph(graph_path, n_leaves: int = 25):
    """A hub node in hub.py wired to n_leaves in-file leaves plus one cross-file
    caller in other.py. Hub degree = n_leaves + 1 (>= HUB_DEGREE_MIN)."""
    nodes = [{"id": "hub", "label": "Hub", "file_type": "code", "source_file": "hub.py"}]
    edges = []
    for i in range(n_leaves):
        nodes.append(
            {"id": f"leaf{i}", "label": f"leaf{i}", "file_type": "code", "source_file": "hub.py"}
        )
        edges.append(
            {"source": "hub", "target": f"leaf{i}", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "hub.py", "weight": 1.0}
        )
    nodes.append({"id": "caller", "label": "caller", "file_type": "code", "source_file": "other.py"})
    edges.append(
        {"source": "caller", "target": "hub", "relation": "calls",
         "confidence": "EXTRACTED", "source_file": "other.py", "weight": 1.0}
    )
    _write_graph(graph_path, nodes, edges)
    return n_leaves + 1  # hub's pre-merge degree


def test_collapsing_hub_triggers_warning_on_dedup_path(tmp_path, capsys):
    """Re-extracting hub.py with a NEW id for the hub drops its in-file edges and
    orphans the cross-file one — the hub collapses. The warning must fire even on
    the default dedup=True path (which the shrink guard is gated out of)."""
    graph_path = tmp_path / "graph.json"
    before = _seed_hub_graph(graph_path)
    assert before >= HUB_DEGREE_MIN

    # hub.py re-extracted; the entity now carries a different id (the #1651 vector).
    new_chunk = {
        "nodes": [{"id": "hub_renamed", "label": "Hub", "file_type": "code", "source_file": "hub.py"}],
        "edges": [],
    }
    G = build_merge([new_chunk], graph_path, dedup=True)

    # Old hub id survives only via the orphaned cross-file edge (degree ~1), or not
    # at all — either way it lost far more than DEGREE_DROP_FRAC of its degree.
    post_hub_degree = G.degree("hub") if "hub" in G else 0
    assert post_hub_degree <= 1

    err = capsys.readouterr().err
    assert "hub node(s) lost" in err
    assert "'Hub'" in err
    assert f"{before} ->" in err  # before -> after, with the true pre-merge degree


def test_benign_reextraction_does_not_warn(tmp_path, capsys):
    """Re-extracting hub.py while preserving the hub's id and all its edges keeps
    the hub intact — no degree-drop warning."""
    graph_path = tmp_path / "graph.json"
    n_leaves = 25
    _seed_hub_graph(graph_path, n_leaves)

    nodes = [{"id": "hub", "label": "Hub", "file_type": "code", "source_file": "hub.py"}]
    edges = []
    for i in range(n_leaves):
        nodes.append(
            {"id": f"leaf{i}", "label": f"leaf{i}", "file_type": "code", "source_file": "hub.py"}
        )
        edges.append(
            {"source": "hub", "target": f"leaf{i}", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "hub.py", "weight": 1.0}
        )
    G = build_merge([{"nodes": nodes, "edges": edges}], graph_path, dedup=True)

    assert G.degree("hub") == n_leaves + 1  # cross-file caller edge preserved too
    err = capsys.readouterr().err
    assert "hub node(s) lost" not in err


def test_small_degree_change_below_threshold_does_not_warn(tmp_path, capsys):
    """A hub that sheds only a couple of edges (< DEGREE_DROP_FRAC) is a benign
    edit, not a collapse — no warning."""
    graph_path = tmp_path / "graph.json"
    n_leaves = 25
    _seed_hub_graph(graph_path, n_leaves)

    # Re-extract hub.py keeping the hub id but dropping just 2 of its 25 leaves.
    nodes = [{"id": "hub", "label": "Hub", "file_type": "code", "source_file": "hub.py"}]
    edges = []
    for i in range(n_leaves - 2):
        nodes.append(
            {"id": f"leaf{i}", "label": f"leaf{i}", "file_type": "code", "source_file": "hub.py"}
        )
        edges.append(
            {"source": "hub", "target": f"leaf{i}", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "hub.py", "weight": 1.0}
        )
    build_merge([{"nodes": nodes, "edges": edges}], graph_path, dedup=True)

    err = capsys.readouterr().err
    assert "hub node(s) lost" not in err


def test_no_warning_when_no_prior_hub(tmp_path, capsys):
    """A graph whose busiest node is below HUB_DEGREE_MIN cannot collapse a hub."""
    graph_path = tmp_path / "graph.json"
    nodes = [
        {"id": "a", "label": "A", "file_type": "code", "source_file": "a.py"},
        {"id": "b", "label": "B", "file_type": "code", "source_file": "a.py"},
    ]
    edges = [{"source": "a", "target": "b", "relation": "calls",
              "confidence": "EXTRACTED", "source_file": "a.py", "weight": 1.0}]
    _write_graph(graph_path, nodes, edges)

    build_merge([{"nodes": [{"id": "a", "label": "A", "file_type": "code", "source_file": "a.py"}],
                  "edges": []}], graph_path, dedup=True)
    err = capsys.readouterr().err
    assert "hub node(s) lost" not in err


# ── helper-level unit tests ───────────────────────────────────────────────────

def test_hub_degrees_picks_only_above_threshold():
    nodes = [{"id": "h", "label": "Hub"}] + [{"id": f"l{i}", "label": f"l{i}"} for i in range(HUB_DEGREE_MIN)]
    edges = [{"source": "h", "target": f"l{i}"} for i in range(HUB_DEGREE_MIN)]
    hubs = _hub_degrees(nodes, edges)
    assert hubs["h"] == ("Hub", HUB_DEGREE_MIN)
    assert all(nid == "h" for nid in hubs)  # leaves (degree 1) excluded


def test_hub_degree_drops_flags_vanished_and_collapsed():
    import networkx as nx

    pre = {"h": ("Hub", 40), "keep": ("Keep", 30)}
    G = nx.Graph()
    G.add_node("keep")
    for i in range(30):
        G.add_edge("keep", f"n{i}")  # keep still has degree 30 — unchanged
    # "h" is absent from G entirely -> vanished
    drops = _hub_degree_drops(pre, G, drop_frac=DEGREE_DROP_FRAC)
    assert drops == [("Hub", 40, 0)]
