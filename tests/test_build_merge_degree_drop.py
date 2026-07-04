"""Degree-drop alert for build_merge (#1652b, guards the #1651 collapse vector).

Incremental --update REPLACES each re-extracted file's prior nodes/edges. If a
re-extraction emits a DIFFERENT id for an entity that already exists as a hub,
the old hub and all its edges are dropped: its in-file edges go with the replaced
contribution, and its cross-file edges are DROPPED by build_from_json — which
discards an edge whose endpoint id has no node rather than orphaning it onto a
bare node. The hub silently collapses from many edges to ~0 while the node count
may not shrink, so the count-based shrink guard never fires. build_merge now
snapshots pre-merge hub degrees and WARNS (not raises) when a former hub vanishes
or loses more than DEGREE_DROP_FRAC of its degree. The alert is active on the
normal dedup=True path (the shrink guard is not), and is suppressed for a hub whose
source_file was intentionally pruned (that collapse is a requested deletion).
"""
from __future__ import annotations

import json

from graphify.build import (
    DEGREE_DROP_FRAC,
    HUB_DEGREE_MIN,
    _HUB_DROP_REPORT_LIMIT,
    _hub_degree_drops,
    _hub_degrees,
    _warn_hub_degree_drops,
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
    drops the cross-file one (its old endpoint no longer has a node) — the hub
    collapses. The warning must fire even on the default dedup=True path (which the
    shrink guard is gated out of)."""
    graph_path = tmp_path / "graph.json"
    before = _seed_hub_graph(graph_path)
    assert before >= HUB_DEGREE_MIN

    # hub.py re-extracted; the entity now carries a different id (the #1651 vector).
    new_chunk = {
        "nodes": [{"id": "hub_renamed", "label": "Hub", "file_type": "code", "source_file": "hub.py"}],
        "edges": [],
    }
    G = build_merge([new_chunk], graph_path, dedup=True)

    # The old hub id vanishes entirely: build_from_json DROPS the cross-file edge
    # (its old endpoint has no node), so "hub" is absent from the post-merge graph —
    # a total collapse, far past DEGREE_DROP_FRAC.
    post_hub_degree = G.degree("hub") if "hub" in G else 0
    assert post_hub_degree == 0

    err = capsys.readouterr().err
    assert "hub node(s) lost" in err
    assert "'Hub'" in err
    assert f"{before} -> 0" in err  # before -> after, with the true pre-merge degree
    assert "(node dropped entirely)" in err  # vanished-hub suffix


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


# ── prune interaction (#1652b: don't cry corruption on intentional deletes) ────

def test_pure_prune_of_hub_file_is_silent(tmp_path, capsys):
    """Deleting a hub's file via prune_sources (no re-extraction) collapses the hub
    to nothing, but that is the operator-requested deletion path — the degree-drop
    alert stays silent and never blames the #1651 id-drift cause."""
    graph_path = tmp_path / "graph.json"
    before = _seed_hub_graph(graph_path)  # hub in hub.py
    assert before >= HUB_DEGREE_MIN

    G = build_merge([], graph_path, prune_sources=["hub.py"], dedup=True)

    assert "hub" not in G  # pruned away entirely
    err = capsys.readouterr().err
    assert "hub node(s) lost" not in err
    assert "#1651" not in err


def test_pruned_hub_silent_but_id_drift_hub_still_warns(tmp_path, capsys):
    """Same run, two hubs: a.py is pruned (requested deletion) and b.py is
    re-extracted with a NEW id for its hub (the #1651 vector). The alert must NOT
    blame the pruned hub, but MUST still fire on the id-drift collapse — the prune
    exemption cannot mute the corruption signal it was carved out of."""
    graph_path = tmp_path / "graph.json"
    n_leaves = 25
    nodes = [
        {"id": "hubA", "label": "HubA", "file_type": "code", "source_file": "a.py"},
        {"id": "hubB", "label": "HubB", "file_type": "code", "source_file": "b.py"},
    ]
    edges = []
    for i in range(n_leaves):
        nodes.append({"id": f"a_leaf{i}", "label": f"a_leaf{i}", "file_type": "code", "source_file": "a.py"})
        edges.append({"source": "hubA", "target": f"a_leaf{i}", "relation": "calls",
                      "confidence": "EXTRACTED", "source_file": "a.py", "weight": 1.0})
        nodes.append({"id": f"b_leaf{i}", "label": f"b_leaf{i}", "file_type": "code", "source_file": "b.py"})
        edges.append({"source": "hubB", "target": f"b_leaf{i}", "relation": "calls",
                      "confidence": "EXTRACTED", "source_file": "b.py", "weight": 1.0})
    _write_graph(graph_path, nodes, edges)

    # b.py re-extracted with a NEW id for hubB (#1651); a.py deleted (pruned).
    new_chunk = {
        "nodes": [{"id": "hubB_renamed", "label": "HubB", "file_type": "code", "source_file": "b.py"}],
        "edges": [],
    }
    G = build_merge([new_chunk], graph_path, prune_sources=["a.py"], dedup=True)

    assert "hubA" not in G  # pruned
    assert "hubB" not in G  # collapsed via id-drift

    err = capsys.readouterr().err
    assert "hub node(s) lost" in err       # the alert DID fire
    assert "1 hub node(s) lost" in err     # exactly one — hubA is exempted
    assert "'HubB'" in err                 # id-drift hub reported
    assert "'HubA'" not in err             # pruned hub NOT reported


# ── report shape: truncation and the strict-> boundary ────────────────────────

def test_many_collapsing_hubs_are_truncated_in_report(capsys):
    """More than _HUB_DROP_REPORT_LIMIT collapsing hubs: the per-hub list is capped
    at the limit and a '... and N more' line summarizes the rest."""
    import networkx as nx

    n_hubs = _HUB_DROP_REPORT_LIMIT + 2
    pre = {f"h{i}": (f"Hub{i}", 30) for i in range(n_hubs)}
    G = nx.Graph()  # every hub vanished
    _warn_hub_degree_drops(pre, G)

    err = capsys.readouterr().err
    assert f"{n_hubs} hub node(s) lost" in err
    # only the first _HUB_DROP_REPORT_LIMIT per-hub lines are printed
    assert err.count("edges (node dropped entirely)") == _HUB_DROP_REPORT_LIMIT
    assert f"... and {n_hubs - _HUB_DROP_REPORT_LIMIT} more hub node(s)." in err


def test_exactly_half_degree_loss_is_below_threshold():
    """A hub losing EXACTLY DEGREE_DROP_FRAC of its degree is benign — the guard
    uses strict `>`, so 50% does not fire and 50%+one-edge does. Pins `>` (not
    `>=`) at the drop check."""
    import networkx as nx

    pre = {"h": ("Hub", 40)}
    # after = 20 -> exactly 50% lost -> NOT flagged (strict >)
    g_half = nx.Graph()
    for i in range(20):
        g_half.add_edge("h", f"n{i}")
    assert _hub_degree_drops(pre, g_half, drop_frac=DEGREE_DROP_FRAC) == []

    # after = 19 -> 52.5% lost -> flagged
    g_over = nx.Graph()
    for i in range(19):
        g_over.add_edge("h", f"n{i}")
    assert _hub_degree_drops(pre, g_over, drop_frac=DEGREE_DROP_FRAC) == [("Hub", 40, 19)]


# ── helper-level unit tests ───────────────────────────────────────────────────

def test_hub_degrees_picks_only_above_threshold():
    nodes = [{"id": "h", "label": "Hub"}] + [{"id": f"l{i}", "label": f"l{i}"} for i in range(HUB_DEGREE_MIN)]
    edges = [{"source": "h", "target": f"l{i}"} for i in range(HUB_DEGREE_MIN)]
    hubs = _hub_degrees(nodes, edges)
    assert hubs["h"] == ("Hub", HUB_DEGREE_MIN)
    assert all(nid == "h" for nid in hubs)  # leaves (degree 1) excluded


def test_hub_degrees_directed_matches_digraph_degree():
    """directed=True snapshots a DiGraph, so a bidirectional pair counts as degree 2
    — matching G.degree() on build_merge(directed=True)'s DiGraph. Undirected
    collapses the pair to 1, which would skew the before/after ratio."""
    nodes = [{"id": "h", "label": "Hub"}] + [{"id": f"l{i}", "label": f"l{i}"} for i in range(15)]
    edges = [{"source": "h", "target": f"l{i}"} for i in range(15)]
    edges += [{"source": f"l{i}", "target": "h"} for i in range(15)]  # reverse of each pair
    # undirected: 15 unique pairs -> degree 15 (< 20) -> h is not a hub
    assert _hub_degrees(nodes, edges) == {}
    # directed: in + out -> degree 30 -> h is a hub
    assert _hub_degrees(nodes, edges, directed=True)["h"] == ("Hub", 30)


def test_hub_degrees_ignores_dangling_edges():
    """An edge whose endpoint has no node is DROPPED (mirroring build_from_json),
    not counted onto an auto-created bare node — so it can't inflate a hub's
    pre-merge degree."""
    nodes = [{"id": "h", "label": "Hub"}] + [{"id": f"l{i}", "label": f"l{i}"} for i in range(HUB_DEGREE_MIN)]
    edges = [{"source": "h", "target": f"l{i}"} for i in range(HUB_DEGREE_MIN)]
    edges += [{"source": "h", "target": f"ghost{i}"} for i in range(5)]  # endpoints absent
    hubs = _hub_degrees(nodes, edges)
    assert hubs["h"] == ("Hub", HUB_DEGREE_MIN)  # dangling edges excluded, not +5
    assert "ghost0" not in hubs  # a ghost endpoint never became a node


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
