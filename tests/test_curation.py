"""Curation overlay: human corrections must survive every rebuild.

Two failure modes this locks down, both observed in the wild on a 3.4k-node graph:

1. `build_merge` replaces per source_file, so a pinned edge whose `source_file`
   names a re-extracted file is dropped and no extractor re-emits it. The node
   count *grows* while this happens, so no guard fires.
2. The semantic cache is keyed by file content, not graph state, so an unchanged
   doc keeps its cached edges and `extract` re-injects an edge that was deleted
   from graph.json.

The overlay is applied at the end of build_from_json — the funnel every path
(build, build_merge, watch, skill) goes through — so both are neutralized.
"""
from __future__ import annotations

import json

import networkx as nx
import pytest

from graphify.build import build, build_from_json, build_merge
from graphify.curation import (
    CURATION_SCHEMA_VERSION,
    apply_curation,
    apply_curation_to_payload,
    empty_curation,
    load_curation,
    save_curation,
)


def _chunk(nodes, edges):
    return {"nodes": nodes, "edges": edges, "hyperedges": []}


def _n(nid, sf):
    return {"id": nid, "label": nid, "file_type": "code", "source_file": sf}


def _e(src, tgt, rel="references", sf="a.py"):
    return {
        "source": src, "target": tgt, "relation": rel,
        "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": sf,
    }


# --- deny -------------------------------------------------------------------

def test_deny_removes_edge_on_build():
    ext = _chunk([_n("a", "a.py"), _n("b", "b.py")], [_e("a", "b", "calls")])
    cur = {"version": 1, "deny_edges": [{"source": "a", "target": "b", "relation": "calls"}]}
    G = build_from_json(ext, curation=cur)
    assert not G.has_edge("a", "b"), "denied edge must not survive the build"
    assert "a" in G and "b" in G, "deny removes the edge, not the nodes"


def test_deny_is_order_insensitive():
    """Undirected storage canonicalizes endpoint order; a deny written (a,b) must
    still match an edge stored (b,a)."""
    ext = _chunk([_n("a", "a.py"), _n("b", "b.py")], [_e("b", "a", "calls")])
    cur = {"deny_edges": [{"source": "a", "target": "b", "relation": "calls"}]}
    G = build_from_json(ext, curation=cur)
    assert not G.has_edge("a", "b")


def test_deny_without_relation_denies_every_edge_between_pair():
    ext = _chunk([_n("a", "a.py"), _n("b", "b.py")], [_e("a", "b", "calls")])
    cur = {"deny_edges": [{"source": "a", "target": "b"}]}
    G = build_from_json(ext, curation=cur)
    assert not G.has_edge("a", "b")


def test_deny_leaves_other_relations_alone():
    ext = _chunk(
        [_n("a", "a.py"), _n("b", "b.py"), _n("c", "c.py")],
        [_e("a", "b", "calls"), _e("a", "c", "calls")],
    )
    cur = {"deny_edges": [{"source": "a", "target": "b", "relation": "calls"}]}
    G = build_from_json(ext, curation=cur)
    assert not G.has_edge("a", "b")
    assert G.has_edge("a", "c"), "an unrelated edge must be untouched"


# --- pin --------------------------------------------------------------------

def test_pin_adds_verified_edge():
    ext = _chunk([_n("a", "a.py"), _n("b", "b.py")], [])
    cur = {"add_edges": [{
        "source": "a", "target": "b", "relation": "shares_data_with",
        "confidence": "INFERRED", "confidence_score": 0.95,
    }]}
    G = build_from_json(ext, curation=cur)
    assert G.has_edge("a", "b")
    attrs = G.get_edge_data("a", "b")
    assert attrs["relation"] == "shares_data_with"
    assert attrs["confidence_score"] == 0.95
    assert attrs["curated"] is True, "pinned edges must be attributable"


def test_pin_skips_missing_endpoint_rather_than_inventing_nodes():
    """The overlay corrects the graph; it must not fabricate nodes, or the edge
    dangles and is silently swallowed by the dangling-edge drop."""
    ext = _chunk([_n("a", "a.py")], [])
    cur = {"add_edges": [{"source": "a", "target": "ghost", "relation": "calls"}]}
    G = build_from_json(ext, curation=cur)
    assert "ghost" not in G
    assert not G.has_edge("a", "ghost")


def test_pin_is_idempotent():
    ext = _chunk([_n("a", "a.py"), _n("b", "b.py")], [])
    cur = {"add_edges": [{"source": "a", "target": "b", "relation": "calls"}]}
    G = build_from_json(ext, curation=cur)
    stats = apply_curation(G, cur)  # re-apply on the same graph
    assert stats["added"] == 0, "re-applying must not duplicate a pinned edge"
    assert G.number_of_edges() == 1


def test_deny_runs_before_pin_so_a_mistyped_edge_can_be_retyped():
    ext = _chunk([_n("a", "a.py"), _n("b", "b.py")],
                 [_e("a", "b", "conceptually_related_to")])
    cur = {
        "deny_edges": [{"source": "a", "target": "b", "relation": "conceptually_related_to"}],
        "add_edges": [{"source": "a", "target": "b", "relation": "shares_data_with"}],
    }
    G = build_from_json(ext, curation=cur)
    assert G.get_edge_data("a", "b")["relation"] == "shares_data_with"


# --- the two regressions ----------------------------------------------------

def test_pinned_edge_survives_build_merge_replace_per_source(tmp_path):
    """Regression: build_merge drops every edge whose source_file is re-extracted.
    A pinned edge on a re-extracted file must come back."""
    root = tmp_path / "corpus"
    root.mkdir()
    graph_path = tmp_path / "graph.json"

    cur = {"add_edges": [{
        "source": "a", "target": "b", "relation": "shares_data_with",
        "source_file": "a.py",  # the file that gets re-extracted
    }]}

    base = _chunk([_n("a", "a.py"), _n("b", "b.py")], [])
    G0 = build_from_json(base, curation=cur)
    assert G0.has_edge("a", "b")
    graph_path.write_text(
        json.dumps(nx.node_link_data(G0, edges="edges")), encoding="utf-8"
    )

    # a.py changes and is re-extracted — its prior contribution is replaced wholesale
    new_chunk = _chunk([_n("a", "a.py")], [])
    G1 = build_merge([new_chunk], graph_path, dedup=False, root=root, curation=cur)

    assert G1.has_edge("a", "b"), (
        "pinned edge was destroyed by replace-per-source — the exact bug this fixes"
    )


def test_denied_edge_stays_denied_when_extraction_reasserts_it():
    """Regression: the content-keyed semantic cache re-injects a deleted edge on
    every extract. Denying it must hold even though the extraction still carries it."""
    cur = {"deny_edges": [{"source": "a", "target": "b", "relation": "semantically_similar_to"}]}
    # the extractor (or its cache) keeps asserting the edge, run after run
    for _ in range(3):
        ext = _chunk(
            [_n("a", "a.py"), _n("b", "b.py")],
            [_e("a", "b", "semantically_similar_to")],
        )
        G = build_from_json(ext, curation=cur)
        assert not G.has_edge("a", "b"), "a disproved edge must not keep coming back"


def test_curation_applies_through_build():
    ext = _chunk([_n("a", "a.py"), _n("b", "b.py")], [_e("a", "b", "calls")])
    cur = {"deny_edges": [{"source": "a", "target": "b"}]}
    G = build([ext], dedup=False, curation=cur)
    assert not G.has_edge("a", "b"), "build() must funnel curation through build_from_json"


# --- payload path (--no-cluster) --------------------------------------------

def test_apply_curation_to_payload_denies_and_pins():
    data = {
        "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
        "links": [
            {"source": "a", "target": "b", "relation": "calls"},
            {"source": "a", "target": "c", "relation": "calls"},
        ],
    }
    cur = {
        "deny_edges": [{"source": "a", "target": "b", "relation": "calls"}],
        "add_edges": [{"source": "b", "target": "c", "relation": "shares_data_with"}],
    }
    stats = apply_curation_to_payload(data, cur)
    assert stats["denied"] == 1
    assert stats["added"] == 1
    pairs = {(e["source"], e["target"]) for e in data["links"]}
    assert ("a", "b") not in pairs
    assert ("a", "c") in pairs
    assert ("b", "c") in pairs


def test_apply_curation_to_payload_handles_raw_extraction_edges_key():
    data = {"nodes": [{"id": "a"}, {"id": "b"}],
            "edges": [{"source": "a", "target": "b", "relation": "calls"}]}
    apply_curation_to_payload(data, {"deny_edges": [{"source": "a", "target": "b"}]})
    assert data["edges"] == []


# --- file I/O ---------------------------------------------------------------

def test_load_curation_absent_returns_none(tmp_path):
    assert load_curation(tmp_path) is None


def test_save_then_load_roundtrip(tmp_path):
    cur = empty_curation()
    cur["deny_edges"].append({"source": "a", "target": "b", "reason": "lexical collision"})
    save_curation(cur, tmp_path)
    loaded = load_curation(tmp_path)
    assert loaded["version"] == CURATION_SCHEMA_VERSION
    assert loaded["deny_edges"][0]["reason"] == "lexical collision"


def test_malformed_curation_is_ignored_not_fatal(tmp_path, capsys):
    (tmp_path / "curation.json").write_text("{not json", encoding="utf-8")
    assert load_curation(tmp_path) is None
    assert "warning" in capsys.readouterr().out.lower()


def test_future_schema_version_is_ignored(tmp_path, capsys):
    (tmp_path / "curation.json").write_text(
        json.dumps({"version": 99, "deny_edges": []}), encoding="utf-8"
    )
    assert load_curation(tmp_path) is None
    assert "version" in capsys.readouterr().out.lower()


def test_env_var_disables_curation(tmp_path, monkeypatch):
    save_curation({"version": 1, "deny_edges": [{"source": "a", "target": "b"}]}, tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_CURATION", "1")
    assert load_curation(tmp_path) is None


def test_build_from_json_without_curation_is_unchanged():
    """The overlay must be inert when absent — no behavior change for existing users."""
    ext = _chunk([_n("a", "a.py"), _n("b", "b.py")], [_e("a", "b", "calls")])
    G = build_from_json(ext, curation={})
    assert G.has_edge("a", "b")


@pytest.mark.parametrize("bad", [
    {"deny_edges": [{"source": "a"}]},              # no target
    {"deny_edges": [{"target": "b"}]},              # no source
    {"deny_edges": ["not-a-dict"]},                 # wrong type
    {"add_edges": [{"source": "", "target": "b"}]},  # empty id
])
def test_malformed_entries_are_skipped_not_fatal(bad):
    ext = _chunk([_n("a", "a.py"), _n("b", "b.py")], [_e("a", "b", "calls")])
    G = build_from_json(ext, curation=bad)
    assert G.has_edge("a", "b"), "a malformed entry must be skipped, not crash the build"
