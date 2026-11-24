"""A semantic copy of an AST edge must not take the AST edge over (#5334).

An undirected graph keeps one edge per pair. When a semantic subagent repeats a
relation the AST already found, with the same confidence, the tie used to go to
whichever edge carried a source_location and arrived last. Part C appends semantic
edges after AST edges, so a copy with a line number won: the edge moved to the
document, and the next --update of that document deleted the code fact although
no code file changed. The AST edge now wins a same-relation, same-rank tie, and
the copy's provenance is kept in also_seen (#4881).
"""
from __future__ import annotations

import pytest

from graphify.build import build_from_json, build_merge, edge_data
from graphify.cluster import cluster
from graphify.export import to_json

PAIR = ("service_place", "helpers_normalize")


def _nodes():
    return [
        {"id": "service_place", "label": ".place()", "file_type": "code",
         "source_file": "src/service.py", "source_location": "L5", "_origin": "ast"},
        {"id": "helpers_normalize", "label": "normalize()", "file_type": "code",
         "source_file": "src/helpers.py", "source_location": "L1", "_origin": "ast"},
        {"id": "notes_order_flow", "label": "Order flow", "file_type": "document",
         "source_file": "docs/notes.md", "_origin": "semantic"},
    ]


AST_CALL = {"source": PAIR[0], "target": PAIR[1], "relation": "calls", "confidence": "EXTRACTED",
            "source_file": "src/service.py", "source_location": "L6", "_origin": "ast"}
# The shape a semantic subagent writes for docs/notes.md: same call, line number, score.
SEMANTIC_COPY = {"source": PAIR[0], "target": PAIR[1], "relation": "calls", "confidence": "EXTRACTED",
                 "confidence_score": 1.0, "source_file": "docs/notes.md", "source_location": "L3",
                 "_origin": "semantic"}
DOC_REF = {"source": "notes_order_flow", "target": PAIR[1], "relation": "references",
           "confidence": "EXTRACTED", "source_file": "docs/notes.md", "_origin": "semantic"}


@pytest.mark.parametrize("ast_first", [True, False])
def test_ast_edge_wins_a_tie_with_its_semantic_copy(ast_first):
    edges = [AST_CALL, SEMANTIC_COPY] if ast_first else [SEMANTIC_COPY, AST_CALL]
    G = build_from_json({"nodes": _nodes(), "edges": [dict(e) for e in edges], "hyperedges": []})

    kept = edge_data(G, *PAIR)
    assert kept["_origin"] == "ast"
    assert kept["source_file"] == "src/service.py"
    assert kept["source_location"] == "L6"
    assert {"confidence": "EXTRACTED", "confidence_score": 1.0,
            "source_file": "docs/notes.md", "source_location": "L3"} in kept["also_seen"]


def test_ast_edge_arriving_second_wins_despite_a_lower_score():
    scored_ast = {**AST_CALL, "confidence_score": 0.85}
    G = build_from_json({"nodes": _nodes(), "edges": [dict(SEMANTIC_COPY), scored_ast], "hyperedges": []})

    kept = edge_data(G, *PAIR)
    assert kept["_origin"] == "ast"
    assert kept["confidence_score"] == 0.85


def test_reextracting_the_document_keeps_the_code_edge(tmp_path):
    G = build_from_json({"nodes": _nodes(), "edges": [dict(AST_CALL), dict(SEMANTIC_COPY), dict(DOC_REF)],
                         "hyperedges": []}, root=str(tmp_path))
    graph_path = tmp_path / "graph.json"
    to_json(G, cluster(G), str(graph_path))

    # --update of docs/notes.md only: the code files are unchanged and not re-extracted.
    doc_node = next(n for n in _nodes() if n["id"] == "notes_order_flow")
    G2 = build_merge([{"nodes": [doc_node], "edges": [dict(DOC_REF)], "hyperedges": []}],
                     graph_path=str(graph_path), root=str(tmp_path))

    assert G2.has_edge(*PAIR), "the code edge was deleted with the document's edges"
    kept = edge_data(G2, *PAIR)
    assert kept["relation"] == "calls"
    assert kept["_origin"] == "ast"
    assert kept["source_file"] == "src/service.py"


def test_semantic_tie_rules_are_unchanged_within_one_tier():
    # Two semantic sites of one call: the line-numbered later copy still replaces
    # the existing one, as before this fix.
    first = {**SEMANTIC_COPY, "source_file": "docs/a.md", "source_location": "L2", "confidence_score": None}
    first.pop("confidence_score")
    second = {**SEMANTIC_COPY, "source_file": "docs/b.md", "source_location": "L9"}
    G = build_from_json({"nodes": _nodes(), "edges": [first, second], "hyperedges": []})

    assert edge_data(G, *PAIR)["source_file"] == "docs/b.md"
