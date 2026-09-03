"""Hyperedges must survive the dual-slot persistence round-trip (#2485).

to_json writes hyperedges to BOTH a top-level ``hyperedges`` key and the
nested ``graph.hyperedges`` (node_link_data graph attrs), but build_from_json
used to read only the top-level slot — a nested-only graph.json silently lost
its whole hyperedge set, and export then persisted the wipeout as a durable
``[]``. build_from_json now folds the nested slot onto the top-level key, and
a full member-revalidation wipeout announces itself with one aggregate WARNING
instead of vanishing quietly.
"""
from __future__ import annotations

import json

from graphify.build import build_from_json
from graphify.export import to_json


def _node(nid: str) -> dict:
    return {"id": nid, "label": nid, "file_type": "code", "source_file": f"{nid}.py"}


def _roundtrip(G, tmp_path):
    out = tmp_path / "graph.json"
    assert to_json(G, {}, str(out)) is True
    return json.loads(out.read_text(encoding="utf-8"))


def test_nested_only_slot_is_read_and_reexported_to_both_slots(tmp_path):
    """A nested-only input is read and re-exported to both persistence slots (#2485)."""
    # node_link_data-only writers emit hyperedges solely under graph attrs.
    extraction = {
        "directed": True,
        "multigraph": False,
        "graph": {"hyperedges": [{"id": "h1", "nodes": ["a", "b", "c"]}]},
        "nodes": [_node("a"), _node("b"), _node("c")],
        "links": [],
    }
    G = build_from_json(extraction, directed=True)
    assert G.graph["hyperedges"] == [{"id": "h1", "nodes": ["a", "b", "c"]}]

    data = _roundtrip(G, tmp_path)
    assert data["hyperedges"] == [{"id": "h1", "nodes": ["a", "b", "c"]}]
    assert data["graph"]["hyperedges"] == data["hyperedges"], (
        "re-export must carry the set in BOTH slots"
    )
    # Full round-trip: rebuilding from the exported file preserves the set exactly.
    G2 = build_from_json(json.loads(json.dumps(data)), directed=True)
    assert G2.graph["hyperedges"] == [{"id": "h1", "nodes": ["a", "b", "c"]}]


def test_top_level_slot_roundtrips_unchanged(tmp_path):
    """Control arm: the canonical to_json shape still round-trips."""
    # Control arm: the canonical to_json shape keeps working as before.
    extraction = {
        "nodes": [_node("a"), _node("b"), _node("c")],
        "edges": [],
        "hyperedges": [{"id": "h_top", "nodes": ["a", "b", "c"]}],
    }
    G = build_from_json(extraction, directed=True)
    assert G.graph["hyperedges"] == [{"id": "h_top", "nodes": ["a", "b", "c"]}]

    data = _roundtrip(G, tmp_path)
    assert data["hyperedges"] == [{"id": "h_top", "nodes": ["a", "b", "c"]}]
    assert data["graph"]["hyperedges"] == data["hyperedges"]
    G2 = build_from_json(json.loads(json.dumps(data)), directed=True)
    assert G2.graph["hyperedges"] == [{"id": "h_top", "nodes": ["a", "b", "c"]}]


def test_full_wipeout_emits_one_aggregate_warning(tmp_path, capsys):
    # Every member dangles, so the #1916 revalidation drops every hyperedge.
    # The wipeout must be loud (one aggregate warning naming the count) and
    # explicit (an empty list, not a missing key).
    extraction = {
        "nodes": [_node("a")],
        "edges": [],
        "hyperedges": [
            {"id": "h1", "nodes": ["ghost1"]},
            {"id": "h2", "nodes": ["ghost2"]},
        ],
    }
    G = build_from_json(extraction, directed=True)
    err = capsys.readouterr().err
    aggregate = [
        line for line in err.splitlines()
        if "all 2 hyperedge(s)" in line and "emptied" in line
    ]
    assert len(aggregate) == 1, f"expected one aggregate warning, got: {err!r}"
    assert G.graph["hyperedges"] == []

    data = _roundtrip(G, tmp_path)
    assert data["hyperedges"] == []
    assert data["graph"]["hyperedges"] == []
