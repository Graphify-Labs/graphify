"""#1711: an edge from an UNCHANGED file into a RE-EXTRACTED file's node must
survive an incremental merge even when the re-extraction mints a different id
for the same symbol (extraction is not id-stable across runs, #1695).

build_merge's and merge_raw_extraction's replace-per-source step correctly
drops a re-extracted file's own stale nodes/edges, but an edge owned by a
file that was NOT re-extracted survives that filter untouched — pointing at
an id that the replace step just removed. Left alone, that dangling
reference either gets silently swallowed by build_from_json's generic
dangling-edge drop (build_merge) or is carried forward as a raw,
unresolvable reference (merge_raw_extraction). Both functions now re-resolve
such an endpoint by (source_file, label) against the fresh chunk, rewriting
the edge onto the new id when exactly one fresh node claims that pair.
"""
from __future__ import annotations

import json
from pathlib import Path

from graphify.build import build, build_merge, merge_raw_extraction
from graphify.export import to_json


def _seed_doc_and_code(tmp_path: Path) -> Path:
    doc_chunk = {
        "nodes": [
            {"id": "payment_flow", "label": "Payment Flow", "file_type": "document",
             "source_file": "doc/payments.md"},
            {"id": "charge_card", "label": "charge_card", "file_type": "code",
             "source_file": "src/pay.py"},
        ],
        "edges": [
            {"source": "payment_flow", "target": "charge_card", "relation": "references",
             "source_file": "doc/payments.md", "confidence": "EXTRACTED"},
        ],
    }
    G = build([doc_chunk])
    graph_path = tmp_path / "graph.json"
    to_json(G, {}, str(graph_path), force=True)
    return graph_path


def _edges(G) -> set[tuple[frozenset, str]]:
    return {(frozenset((str(u), str(v))), str(d.get("relation"))) for u, v, d in G.edges(data=True)}


def _node_by_label(G, label: str) -> str:
    matches = [n for n, d in G.nodes(data=True) if d.get("label") == label]
    assert len(matches) == 1, f"expected exactly one {label!r} node, found {matches}"
    return matches[0]


def test_build_merge_rewires_edge_onto_requalified_endpoint(tmp_path):
    graph_path = _seed_doc_and_code(tmp_path)
    # Re-extract only src/pay.py; same symbol, requalified id (AST now
    # prefixes with the file stem, LLM non-determinism, etc. — #1695).
    new_chunk = {
        "nodes": [{"id": "pay_charge_card", "label": "charge_card", "file_type": "code",
                    "source_file": "src/pay.py"}],
        "edges": [],
    }
    G2 = build_merge([new_chunk], graph_path=graph_path, root=tmp_path)
    fresh_id = _node_by_label(G2, "charge_card")
    assert fresh_id != "charge_card"  # genuinely requalified, not a no-op rename
    assert (frozenset(("payment_flow", fresh_id)), "references") in _edges(G2)


def test_merge_raw_extraction_rewires_edge_onto_requalified_endpoint(tmp_path):
    graph_path = _seed_doc_and_code(tmp_path)
    new_extraction = {
        "nodes": [{"id": "pay_charge_card", "label": "charge_card", "file_type": "code",
                    "source_file": "src/pay.py"}],
        "edges": [],
    }
    merged = merge_raw_extraction(new_extraction, graph_path, root=tmp_path)
    node_ids = {n["id"] for n in merged["nodes"]}
    assert node_ids == {"payment_flow", "pay_charge_card"}
    assert {(e["source"], e["target"]) for e in merged["edges"]} == {("payment_flow", "pay_charge_card")}


def test_ambiguous_replacement_is_left_to_drop(tmp_path):
    # Two fresh nodes under the SAME re-extracted file share the dropped
    # node's (source_file, label) — unique-candidate-only must refuse to
    # guess which one the old edge meant, so it stays dangling exactly as
    # it did before this fix (the ordinary dangling-edge drop still applies).
    graph_path = _seed_doc_and_code(tmp_path)
    new_chunk = {
        "nodes": [
            {"id": "pay_charge_card_a", "label": "charge_card", "file_type": "code",
             "source_file": "src/pay.py"},
            {"id": "pay_charge_card_b", "label": "charge_card", "file_type": "code",
             "source_file": "src/pay.py"},
        ],
        "edges": [],
    }
    G2 = build_merge([new_chunk], graph_path=graph_path, root=tmp_path)
    assert _edges(G2) == set()
    labels = [d.get("label") for _, d in G2.nodes(data=True)]
    assert labels.count("charge_card") == 2


def test_genuinely_deleted_endpoint_is_still_pruned(tmp_path):
    # src/pay.py is DELETED (prune_sources), not re-extracted: no fresh node
    # exists to rewire onto, so the edge must still disappear — rewiring
    # only ever applies to the replace case, never to a real deletion.
    graph_path = _seed_doc_and_code(tmp_path)
    G2 = build_merge([], graph_path=graph_path, prune_sources=["src/pay.py"], root=tmp_path)
    assert "charge_card" not in G2.nodes
    assert "payment_flow" in G2.nodes
    assert _edges(G2) == set()


def test_unrelated_unchanged_edge_is_untouched(tmp_path):
    # A control with no re-extraction at all: nothing should be rewired or
    # dropped — an ordinary no-op incremental update.
    graph_path = _seed_doc_and_code(tmp_path)
    before = json.loads(graph_path.read_text())
    G2 = build_merge([], graph_path=graph_path, root=tmp_path)
    assert _edges(G2) == {(frozenset(("payment_flow", "charge_card")), "references")}
    after = json.loads(graph_path.read_text())
    assert before == after  # build_merge never writes; this is a read-only check
