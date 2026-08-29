"""Carried-forward hyperedges must follow the dedup survivor remap (#3102).

build_merge() carries hyperedges from unchanged files across an incremental
rebuild (#1574). They used to be attached to G AFTER build() and entity
dedup had finished, so while every edge endpoint was rewired onto the dedup
survivor (#2805), a carried hyperedge kept naming the merged-away node — a
dangling member in graph.json with no backing node.
"""
from __future__ import annotations

import json
from pathlib import Path

from graphify.build import build_from_json, build_merge
from graphify.export import to_json

# `alpha_a` and `alpha_concept_long_variant_id` label-dedup into one node.
NODES = [
    {"id": "alpha_a", "label": "Alpha Concept", "file_type": "concept", "source_file": "notes/a.md"},
    {"id": "alpha_concept_long_variant_id", "label": "alpha_concept", "file_type": "concept",
     "source_file": "notes/b.md"},
    {"id": "beta_node", "label": "Beta", "file_type": "concept", "source_file": "notes/group.md"},
    {"id": "gamma_node", "label": "Gamma", "file_type": "concept", "source_file": "notes/group.md"},
]
EDGES = [{"source": "alpha_concept_long_variant_id", "target": "beta_node", "relation": "references",
          "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": "notes/b.md"}]
HYPEREDGE = {"id": "the_group", "label": "The Group",
             "nodes": ["alpha_concept_long_variant_id", "beta_node", "gamma_node"],
             "relation": "participate_in", "confidence": "EXTRACTED", "confidence_score": 1.0,
             "source_file": "notes/group.md"}
UNRELATED_CHUNK = {
    "nodes": [{"id": "delta_node", "label": "Delta", "file_type": "concept", "source_file": "notes/d.md"}],
    "edges": [], "hyperedges": [],
}


def _baseline(tmp_path: Path) -> Path:
    """A graph written WITHOUT dedup, so the pair is still two nodes on disk
    and the hyperedge names the variant — the shape an older build leaves."""
    G = build_from_json({"nodes": NODES, "edges": EDGES, "hyperedges": [HYPEREDGE]})
    p = tmp_path / "graph.json"
    to_json(G, {0: list(G.nodes)}, str(p))
    return p


def _hyperedges(G):
    return {he["id"]: he for he in G.graph.get("hyperedges", [])}


def test_a_carried_hyperedge_is_remapped_onto_the_dedup_survivor(tmp_path):
    G = build_merge([UNRELATED_CHUNK], _baseline(tmp_path))
    survivors = set(G.nodes)
    assert "alpha_concept_long_variant_id" not in survivors  # merged away
    he = _hyperedges(G)["the_group"]
    assert set(he["nodes"]) <= survivors, f"dangling members: {set(he['nodes']) - survivors}"
    assert "alpha_a" in he["nodes"]  # onto the survivor, not just dropped
    assert {"beta_node", "gamma_node"} <= set(he["nodes"])


def test_the_written_graph_has_no_dangling_hyperedge_member(tmp_path):
    G = build_merge([UNRELATED_CHUNK], _baseline(tmp_path))
    out = tmp_path / "merged.json"
    to_json(G, {0: list(G.nodes)}, str(out), force=True)
    data = json.loads(out.read_text(encoding="utf-8"))
    ids = {n["id"] for n in data["nodes"]}
    for he in data.get("hyperedges", []):
        assert set(he["nodes"]) <= ids, f"{he['id']} names a node that is not in the graph"


def test_edges_and_hyperedges_agree_on_the_survivor(tmp_path):
    """The edge endpoint and the hyperedge member came from the same
    merged-away node; both must now name the same survivor."""
    G = build_merge([UNRELATED_CHUNK], _baseline(tmp_path))
    edge_ends = {u for u, v in G.edges} | {v for u, v in G.edges}
    assert "alpha_a" in edge_ends
    assert "alpha_a" in _hyperedges(G)["the_group"]["nodes"]


def test_a_hyperedge_re_emitted_by_the_new_chunk_is_not_duplicated(tmp_path):
    fresh = {"nodes": [{"id": "beta_node", "label": "Beta", "file_type": "concept",
                        "source_file": "notes/group.md"},
                       {"id": "gamma_node", "label": "Gamma", "file_type": "concept",
                        "source_file": "notes/group.md"}],
             "edges": [],
             "hyperedges": [{**HYPEREDGE, "nodes": ["beta_node", "gamma_node"], "label": "The Group v2"}]}
    G = build_merge([fresh], _baseline(tmp_path))
    hes = [he for he in G.graph.get("hyperedges", []) if he["id"] == "the_group"]
    assert len(hes) == 1
    assert hes[0]["label"] == "The Group v2"  # the re-extracted version wins


def test_a_pruned_sources_hyperedge_is_still_dropped(tmp_path):
    G = build_merge([UNRELATED_CHUNK], _baseline(tmp_path), prune_sources=["notes/group.md"])
    assert "the_group" not in _hyperedges(G)


def test_an_unchanged_hyperedge_with_no_dedup_involved_is_carried_verbatim(tmp_path):
    nodes = [n for n in NODES if n["id"] != "alpha_a"]  # nothing to dedup now
    G0 = build_from_json({"nodes": nodes, "edges": EDGES, "hyperedges": [HYPEREDGE]})
    p = tmp_path / "g.json"
    to_json(G0, {0: list(G0.nodes)}, str(p))
    G = build_merge([UNRELATED_CHUNK], p)
    assert set(_hyperedges(G)["the_group"]["nodes"]) == set(HYPEREDGE["nodes"])
