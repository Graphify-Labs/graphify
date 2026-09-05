"""Tier-1 (pure, DB-free) unit tests for graphify.age_snapshots
(docs/AGE_PLAN.md Phase 3): payload conversion, diff application, and
checkpoint/delta chain replay. No psycopg import needed -- these functions
only touch the database inside record_snapshot()/latest_snapshot_graph(),
which are exercised live in tests/test_age_snapshots_integration.py.
"""
from __future__ import annotations

import networkx as nx

from graphify import age_snapshots as snap
from graphify.analyze import graph_diff


def _graph(nodes, edges):
    G = nx.Graph()
    for node_id, attrs in nodes:
        G.add_node(node_id, **attrs)
    for src, tgt, attrs in edges:
        G.add_edge(src, tgt, **attrs)
    return G


# ---------------------------------------------------------------------------
# graph_to_payload / payload_to_graph round trip
# ---------------------------------------------------------------------------

def test_graph_to_payload_captures_all_scalar_props():
    G = _graph([("a", {"label": "A", "file_type": "code", "community": 3})], [])
    payload = snap.graph_to_payload(G)
    assert payload["nodes"] == [{"id": "a", "label": "A", "file_type": "code", "community": 3}]
    assert payload["edges"] == []


def test_graph_to_payload_excludes_private_and_non_scalar_keys():
    G = _graph([("a", {"label": "A", "_internal": object(), "tags": ["x", "y"]})], [])
    payload = snap.graph_to_payload(G)
    assert payload["nodes"] == [{"id": "a", "label": "A"}]


def test_payload_to_graph_round_trips():
    G_orig = _graph(
        [("a", {"label": "A"}), ("b", {"label": "B"})],
        [("a", "b", {"relation": "calls", "confidence": "EXTRACTED"})],
    )
    payload = snap.graph_to_payload(G_orig)
    G_back = snap.payload_to_graph(payload)
    assert set(G_back.nodes()) == {"a", "b"}
    assert G_back.nodes["a"]["label"] == "A"
    assert G_back.has_edge("a", "b")
    assert G_back.edges["a", "b"]["relation"] == "calls"


# ---------------------------------------------------------------------------
# apply_diff_to_payload
# ---------------------------------------------------------------------------

def test_apply_diff_to_payload_adds_new_node():
    payload = {"nodes": [{"id": "a", "label": "A"}], "edges": []}
    diff = {
        "new_nodes": [{"id": "b", "label": "B", "properties": {"label": "B"}}],
        "changed_nodes": [], "removed_nodes": [],
        "new_edges": [], "removed_edges": [], "changed_edges": [],
    }
    result = snap.apply_diff_to_payload(payload, diff)
    assert {n["id"] for n in result["nodes"]} == {"a", "b"}


def test_apply_diff_to_payload_removes_node():
    payload = {"nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}], "edges": []}
    diff = {
        "removed_nodes": [{"id": "b", "label": "B", "properties": {"label": "B"}}],
        "new_nodes": [], "changed_nodes": [],
        "new_edges": [], "removed_edges": [], "changed_edges": [],
    }
    result = snap.apply_diff_to_payload(payload, diff)
    assert [n["id"] for n in result["nodes"]] == ["a"]


def test_apply_diff_to_payload_applies_changed_node_properties():
    payload = {"nodes": [{"id": "a", "label": "A", "community": 1}], "edges": []}
    diff = {
        "changed_nodes": [{"id": "a", "old": {"label": "A", "community": 1},
                            "new": {"label": "A", "community": 2}}],
        "new_nodes": [], "removed_nodes": [],
        "new_edges": [], "removed_edges": [], "changed_edges": [],
    }
    result = snap.apply_diff_to_payload(payload, diff)
    assert result["nodes"] == [{"id": "a", "label": "A", "community": 2}]


def test_apply_diff_to_payload_handles_edges():
    payload = {"nodes": [], "edges": [{"source": "a", "target": "b", "relation": "calls"}]}
    diff = {
        "new_nodes": [], "removed_nodes": [], "changed_nodes": [],
        "removed_edges": [{"source": "a", "target": "b", "relation": "calls"}],
        "new_edges": [{"source": "b", "target": "c", "relation": "uses",
                        "properties": {"relation": "uses", "confidence": "INFERRED"}}],
        "changed_edges": [],
    }
    result = snap.apply_diff_to_payload(payload, diff)
    assert len(result["edges"]) == 1
    assert result["edges"][0]["source"] == "b" and result["edges"][0]["target"] == "c"


def test_apply_diff_to_payload_matches_graph_diff_output():
    """End-to-end sanity: applying graph_diff(old, new) to old's own
    payload reproduces new's payload."""
    G_old = _graph([("a", {"label": "A"}), ("b", {"label": "B"})],
                    [("a", "b", {"relation": "calls", "confidence": "EXTRACTED"})])
    G_new = _graph([("a", {"label": "A", "community": 5}), ("c", {"label": "C"})],
                    [("a", "c", {"relation": "uses", "confidence": "INFERRED"})])
    diff = graph_diff(G_old, G_new)
    old_payload = snap.graph_to_payload(G_old)
    new_payload = snap.graph_to_payload(G_new)
    reconstructed = snap.apply_diff_to_payload(old_payload, diff)
    assert {n["id"] for n in reconstructed["nodes"]} == {n["id"] for n in new_payload["nodes"]}
    assert sorted(reconstructed["nodes"], key=lambda n: n["id"]) == sorted(
        new_payload["nodes"], key=lambda n: n["id"]
    )
    reconstructed_edges = {(e["source"], e["target"]) for e in reconstructed["edges"]}
    new_edges = {(e["source"], e["target"]) for e in new_payload["edges"]}
    assert reconstructed_edges == new_edges


# ---------------------------------------------------------------------------
# _reconstruct_payload_from_rows: checkpoint/delta chain replay
# ---------------------------------------------------------------------------

def test_reconstruct_from_no_rows_returns_none():
    payload, commit_sha, snapshot_id = snap._reconstruct_payload_from_rows([])
    assert payload is None and commit_sha is None and snapshot_id is None


def test_reconstruct_from_single_checkpoint():
    rows = [("s1", "c1", "checkpoint", {"nodes": [{"id": "a"}], "edges": []})]
    payload, commit_sha, snapshot_id = snap._reconstruct_payload_from_rows(rows)
    assert payload == {"nodes": [{"id": "a"}], "edges": []}
    assert commit_sha == "c1"
    assert snapshot_id == "s1"


def test_reconstruct_replays_deltas_after_checkpoint():
    checkpoint_payload = {"nodes": [{"id": "a", "label": "A"}], "edges": []}
    delta = {
        "new_nodes": [{"id": "b", "label": "B", "properties": {"label": "B"}}],
        "changed_nodes": [], "removed_nodes": [],
        "new_edges": [], "removed_edges": [], "changed_edges": [],
    }
    rows = [
        ("s1", "c1", "checkpoint", checkpoint_payload),
        ("s2", "c2", "delta", delta),
    ]
    payload, commit_sha, snapshot_id = snap._reconstruct_payload_from_rows(rows)
    assert {n["id"] for n in payload["nodes"]} == {"a", "b"}
    assert commit_sha == "c2"
    assert snapshot_id == "s2"


def test_reconstruct_prefers_checkpoint_over_earlier_delta_for_same_commit():
    """Checkpoint-preferred resolution: a checkpoint row is a complete
    restatement, so rows before it (even a delta at the same commit_sha)
    must never be replayed once a later checkpoint exists."""
    stale_delta = {
        "new_nodes": [{"id": "z", "label": "Z", "properties": {"label": "Z"}}],
        "changed_nodes": [], "removed_nodes": [],
        "new_edges": [], "removed_edges": [], "changed_edges": [],
    }
    checkpoint_payload = {"nodes": [{"id": "a", "label": "A"}], "edges": []}
    rows = [
        ("s1", "c1", "delta", stale_delta),
        ("s2", "c1", "checkpoint", checkpoint_payload),
    ]
    payload, commit_sha, snapshot_id = snap._reconstruct_payload_from_rows(rows)
    assert {n["id"] for n in payload["nodes"]} == {"a"}
    assert commit_sha == "c1"
    assert snapshot_id == "s2"


def test_reconstruct_accepts_json_string_payloads():
    """psycopg may hand back JSONB as an already-parsed dict or (depending
    on adapter config) a raw string -- both must work."""
    import json
    rows = [("s1", "c1", "checkpoint", json.dumps({"nodes": [{"id": "a"}], "edges": []}))]
    payload, _, _ = snap._reconstruct_payload_from_rows(rows)
    assert payload == {"nodes": [{"id": "a"}], "edges": []}


def test_reconstruct_with_no_checkpoint_replays_from_empty_graph():
    delta = {
        "new_nodes": [{"id": "a", "label": "A", "properties": {"label": "A"}}],
        "changed_nodes": [], "removed_nodes": [],
        "new_edges": [], "removed_edges": [], "changed_edges": [],
    }
    rows = [("s1", "c1", "delta", delta)]
    payload, commit_sha, snapshot_id = snap._reconstruct_payload_from_rows(rows)
    assert {n["id"] for n in payload["nodes"]} == {"a"}
    assert commit_sha == "c1"
    assert snapshot_id == "s1"
