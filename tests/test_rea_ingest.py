"""Ingest REA's JavaScript Application Graph into a Graphify graph.

REA (morluto/rea) reverse-engineers shipped apps and emits a canonical
JavaScript Application Graph (nodes + evidence-bearing edges). `ingest_rea_jag`
maps that into Graphify's node/edge model so the result is queryable with
`graphify query`/`path`/`explain`. Built against REA's documented JAG contract
plus the synthetic fixture tests/fixtures/rea_jag_sample.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from graphify.build import build_from_json
from graphify.rea_ingest import ingest_rea_jag

_FIXTURE = Path(__file__).parent / "fixtures" / "rea_jag_sample.json"


def _ingest():
    doc = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return ingest_rea_jag(doc, source_file="demo.jag.json")


def test_non_dict_input_yields_empty_result():
    assert ingest_rea_jag(None) == {"nodes": [], "edges": []}
    assert ingest_rea_jag("nope") == {"nodes": [], "edges": []}
    assert ingest_rea_jag({"schema": "x"}) == {"nodes": [], "edges": []}  # no nodes list


def test_nodes_and_edges_map_into_graphify():
    res = _ingest()
    labels = {n["label"] for n in res["nodes"]}
    assert {"example.app", "preload.js", "fts.node", "search:query"} <= labels
    # relation vocabulary is mapped to Graphify's known relations
    relations = {e["relation"] for e in res["edges"]}
    assert relations <= {"contains", "imports", "calls", "references"}
    # the original REA relation is preserved in context for traceability
    assert any(e["context"] == "rea:loads" for e in res["edges"])
    assert any(e["context"] == "rea:invokes" for e in res["edges"])


def test_kind_maps_to_file_type():
    res = _ingest()
    by_label = {n["label"]: n for n in res["nodes"]}
    # structural artifacts are code; process/IPC boundaries are concepts
    assert by_label["preload.js"]["file_type"] == "code"
    assert by_label["fts.node"]["file_type"] == "code"
    assert by_label["example.app"]["file_type"] == "concept"      # package
    assert by_label["search:query"]["file_type"] == "concept"     # ipc channel


def test_epistemic_state_drives_confidence():
    res = _ingest()
    by_ctx = {e["context"]: e for e in res["edges"]}
    assert by_ctx["rea:contains"]["confidence"] == "EXTRACTED"    # observed
    assert by_ctx["rea:loads"]["confidence"] == "INFERRED"        # inferred
    # inferred edges never claim certainty
    assert by_ctx["rea:loads"]["confidence_score"] <= 0.9


def test_unavailable_edge_is_dropped():
    res = _ingest()
    # the fixture's duplicate preload->contextBridge edge is epistemic "unavailable"
    # and must not become a relationship; the observed/inferred ones still exist.
    exposes = [e for e in res["edges"] if e["context"] == "rea:exposes"]
    assert len(exposes) == 1


def test_external_endpoint_is_stubbed_not_dangling():
    res = _ingest()
    stubs = [n for n in res["nodes"] if n["metadata"].get("rea_external")]
    assert len(stubs) == 1  # jag_node_missing_ext
    node_ids = {n["id"] for n in res["nodes"]}
    for e in res["edges"]:
        assert e["source"] in node_ids and e["target"] in node_ids


def test_root_node_carries_graph_coverage_and_limitations():
    res = _ingest()
    root = next(n for n in res["nodes"] if n["metadata"].get("rea_root"))
    assert root["metadata"]["rea_coverage"] == "partial"
    assert root["metadata"]["rea_limitations"]


def test_build_from_json_accepts_the_ingested_graph():
    res = _ingest()
    G = build_from_json(res, directed=True)
    # every edge endpoint resolves to a real node (nothing dangles)
    assert G.number_of_nodes() == len(res["nodes"])
    assert G.number_of_edges() >= 7
