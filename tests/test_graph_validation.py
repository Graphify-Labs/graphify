"""Tests for the post-build validation gate: canonical node identity, citation-
edge direction, hyperedge schema, and deterministic graph generation.

This closes a real gap found while running /graphify on a 48-file docs corpus:
extraction independently produced `docs_architecture` and
`docs_architecture_document` for one file (ARCHITECTURE.md), inflating its
apparent "god node" degree and misattributing which document was doing the
citing. `diagnose_extraction`'s `canonical` verdict is meant to make that kind
of defect visible and machine-checkable instead of requiring a by-hand trace.
"""
from __future__ import annotations

import json
from pathlib import Path

import graphify.__main__ as mainmod
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.diagnostics import diagnose_extraction, format_diagnostic_report
from graphify.export import to_json
from graphify.validate import validate_extraction


def _doc_node(node_id: str, label: str, source_file: str, file_type: str = "document") -> dict:
    return {"id": node_id, "label": label, "file_type": file_type, "source_file": source_file}


def _edge(source: str, target: str, source_file: str, relation: str = "references") -> dict:
    return {
        "source": source,
        "target": target,
        "relation": relation,
        "confidence": "EXTRACTED",
        "source_file": source_file,
    }


# --- hyperedge schema validation -------------------------------------------


def test_validate_extraction_accepts_wellformed_hyperedge():
    data = {
        "nodes": [
            _doc_node("a", "A", "a.md"),
            _doc_node("b", "B", "b.md"),
            _doc_node("c", "C", "c.md"),
        ],
        "edges": [],
        "hyperedges": [
            {
                "id": "grp",
                "label": "Group",
                "nodes": ["a", "b", "c"],
                "relation": "participate_in",
                "confidence": "INFERRED",
                "confidence_score": 0.75,
                "source_file": "a.md",
            }
        ],
    }
    assert validate_extraction(data) == []


def test_validate_extraction_rejects_hyperedge_missing_fields():
    data = {
        "nodes": [_doc_node("a", "A", "a.md")],
        "edges": [],
        "hyperedges": [{"id": "grp", "nodes": ["a"]}],
    }
    errors = validate_extraction(data)
    assert any("missing required field" in e for e in errors)


def test_validate_extraction_rejects_hyperedge_under_three_nodes():
    data = {
        "nodes": [_doc_node("a", "A", "a.md"), _doc_node("b", "B", "b.md")],
        "edges": [],
        "hyperedges": [
            {
                "id": "grp",
                "label": "Group",
                "nodes": ["a", "b"],
                "relation": "participate_in",
                "confidence": "EXTRACTED",
                "source_file": "a.md",
            }
        ],
    }
    errors = validate_extraction(data)
    assert any("at least 3" in e for e in errors)


def test_validate_extraction_rejects_hyperedge_dangling_member():
    data = {
        "nodes": [_doc_node("a", "A", "a.md"), _doc_node("b", "B", "b.md")],
        "edges": [],
        "hyperedges": [
            {
                "id": "grp",
                "label": "Group",
                "nodes": ["a", "b", "ghost"],
                "relation": "participate_in",
                "confidence": "EXTRACTED",
                "source_file": "a.md",
            }
        ],
    }
    errors = validate_extraction(data)
    assert any("does not match any node id" in e for e in errors)


def test_validate_extraction_still_passes_without_hyperedges_key():
    """Older extractions that predate hyperedges must still validate clean."""
    data = {
        "nodes": [_doc_node("a", "A", "a.md")],
        "edges": [],
    }
    assert validate_extraction(data) == []


# --- canonical node identity (duplicate whole-file nodes) -------------------


def test_diagnose_flags_document_suffix_split_as_hard_duplicate():
    """Direct regression for the ARCHITECTURE.md split found in the wild."""
    extraction = {
        "nodes": [
            _doc_node("docs_architecture", "ARCHITECTURE.md", "ARCHITECTURE.md"),
            _doc_node(
                "docs_architecture_document",
                "ARCHITECTURE.md - Avenoria Technical Architecture",
                "adr/001-example.md",
            ),
        ],
        "edges": [],
        "hyperedges": [],
    }
    summary = diagnose_extraction(extraction, directed=False)
    assert summary["canonical"] is False
    assert summary["duplicate_node_candidates"] == [
        {
            "node_a": "docs_architecture",
            "node_b": "docs_architecture_document",
            "reason": "id suffix '_document'",
        }
    ]
    assert any("duplicate whole-file" in issue for issue in summary["canonical_issues"])


def test_diagnose_flags_label_prefix_as_soft_duplicate_only():
    """A label-prefix match without the id-suffix pattern is informational
    (soft) and must not, on its own, flip canonical to False - it is a
    plausible signal, not proof (e.g. it could legitimately be two distinct,
    unrelated files whose titles happen to share a prefix)."""
    extraction = {
        "nodes": [
            _doc_node("docs_api_v1", "API.md", "api-v1/API.md"),
            _doc_node("docs_api_v2", "API.md - v2 addendum", "api-v2/API.md"),
        ],
        "edges": [],
        "hyperedges": [],
    }
    summary = diagnose_extraction(extraction, directed=False)
    assert summary["duplicate_node_candidates"] == []
    assert len(summary["duplicate_node_candidates_soft"]) == 1
    assert summary["canonical"] is True


def test_diagnose_does_not_flag_heading_node_of_same_file_as_duplicate():
    """A heading node deliberately shares source_file with its parent
    whole-file node and often repeats/extends its label - this must never be
    mistaken for a cross-file duplicate."""
    extraction = {
        "nodes": [
            _doc_node("docs_readme", "README.md", "README.md"),
            _doc_node("docs_readme_overview", "README.md Overview", "README.md"),
        ],
        "edges": [],
        "hyperedges": [],
    }
    summary = diagnose_extraction(extraction, directed=False)
    assert summary["duplicate_node_candidates"] == []
    assert summary["duplicate_node_candidates_soft"] == []
    assert summary["canonical"] is True


def test_diagnose_does_not_flag_unrelated_documents():
    extraction = {
        "nodes": [
            _doc_node("docs_api", "API.md", "API.md"),
            _doc_node("docs_database", "DATABASE.md", "DATABASE.md"),
        ],
        "edges": [],
        "hyperedges": [],
    }
    summary = diagnose_extraction(extraction, directed=False)
    assert summary["duplicate_node_candidates"] == []
    assert summary["duplicate_node_candidates_soft"] == []
    assert summary["canonical"] is True


# --- citation edge direction -------------------------------------------


def test_diagnose_flags_reversed_citation_edge():
    """The edge's own source_file matches the TARGET's file, not the
    SOURCE's - the extraction-spec.md self-check for a reversed references/
    cites edge between two whole-file document nodes."""
    extraction = {
        "nodes": [
            _doc_node("docs_architecture_document", "ARCHITECTURE.md - long form", "adr/001.md"),
            _doc_node("docs_adr_012", "ADR-012", "adr/012.md"),
        ],
        "edges": [_edge("docs_architecture_document", "docs_adr_012", "adr/012.md")],
        "hyperedges": [],
    }
    summary = diagnose_extraction(extraction, directed=False)
    assert summary["canonical"] is False
    assert len(summary["edge_direction_suspects"]) == 1
    suspect = summary["edge_direction_suspects"][0]
    assert suspect["source"] == "docs_architecture_document"
    assert suspect["target"] == "docs_adr_012"


def test_diagnose_does_not_flag_correctly_directed_citation_edge():
    extraction = {
        "nodes": [
            _doc_node("docs_adr_012", "ADR-012", "adr/012.md"),
            _doc_node("docs_architecture", "ARCHITECTURE.md", "ARCHITECTURE.md"),
        ],
        "edges": [_edge("docs_adr_012", "docs_architecture", "adr/012.md")],
        "hyperedges": [],
    }
    summary = diagnose_extraction(extraction, directed=False)
    assert summary["edge_direction_suspects"] == []
    assert summary["canonical"] is True


def test_diagnose_ignores_direction_for_non_citation_relations():
    """The direction heuristic is scoped to references/cites (the relations
    extraction-spec.md gives an explicit citer->citee rule for) - it must not
    misfire on `calls`, whose direction semantics are already covered by a
    different, existing spec rule and are checked elsewhere."""
    extraction = {
        "nodes": [
            _doc_node("docs_a", "A", "a.md", file_type="document"),
            _doc_node("docs_b", "B", "b.md", file_type="document"),
        ],
        "edges": [_edge("docs_a", "docs_b", "b.md", relation="calls")],
        "hyperedges": [],
    }
    summary = diagnose_extraction(extraction, directed=False)
    assert summary["edge_direction_suspects"] == []


def test_diagnose_ignores_direction_when_endpoint_is_not_whole_file_typed():
    """Concept/rationale nodes don't carry the same "this node IS a file"
    semantics a document/paper node does, so the heuristic must not apply to
    them - only whole-file <-> whole-file citation edges are in scope."""
    extraction = {
        "nodes": [
            _doc_node("docs_a", "A", "a.md", file_type="document"),
            _doc_node("docs_a_concept", "A Concept", "b.md", file_type="concept"),
        ],
        "edges": [_edge("docs_a", "docs_a_concept", "b.md")],
        "hyperedges": [],
    }
    summary = diagnose_extraction(extraction, directed=False)
    assert summary["edge_direction_suspects"] == []


# --- overall canonical verdict + report formatting --------------------------


def test_canonical_true_for_clean_extraction():
    extraction = {
        "nodes": [
            _doc_node("docs_adr_012", "ADR-012", "adr/012.md"),
            _doc_node("docs_architecture", "ARCHITECTURE.md", "ARCHITECTURE.md"),
        ],
        "edges": [_edge("docs_adr_012", "docs_architecture", "adr/012.md")],
        "hyperedges": [],
    }
    summary = diagnose_extraction(extraction, directed=False)
    assert summary["canonical"] is True
    assert summary["canonical_issues"] == []


def test_canonical_false_for_dangling_edge_endpoint():
    """Pre-existing dangling-endpoint detection now also gates `canonical`,
    not just the edge-collapse counters it always fed."""
    extraction = {
        "nodes": [_doc_node("docs_a", "A", "a.md")],
        "edges": [_edge("docs_a", "ghost", "a.md")],
        "hyperedges": [],
    }
    summary = diagnose_extraction(extraction, directed=False)
    assert summary["canonical"] is False
    assert any("dangling" in issue for issue in summary["canonical_issues"])


def test_canonical_false_for_schema_error():
    extraction = {
        "nodes": [{"id": "a", "label": "A", "file_type": "not-a-real-type", "source_file": "a.md"}],
        "edges": [],
        "hyperedges": [],
    }
    summary = diagnose_extraction(extraction, directed=False)
    assert summary["canonical"] is False
    assert summary["schema_errors"]
    assert any("schema error" in issue for issue in summary["canonical_issues"])


def test_format_diagnostic_report_prints_noncanonical_verdict_banner():
    extraction = {
        "nodes": [
            _doc_node("docs_architecture", "ARCHITECTURE.md", "ARCHITECTURE.md"),
            _doc_node(
                "docs_architecture_document",
                "ARCHITECTURE.md - long form",
                "adr/001.md",
            ),
        ],
        "edges": [],
        "hyperedges": [],
    }
    summary = diagnose_extraction(extraction, directed=False)
    report = format_diagnostic_report(summary)
    assert "verdict: NON-CANONICAL" in report
    assert "informational only" in report
    assert "docs_architecture <-> docs_architecture_document" in report


def test_format_diagnostic_report_prints_canonical_verdict_banner():
    extraction = {
        "nodes": [_doc_node("docs_a", "A", "a.md")],
        "edges": [],
        "hyperedges": [],
    }
    summary = diagnose_extraction(extraction, directed=False)
    report = format_diagnostic_report(summary)
    assert "verdict: CANONICAL" in report
    assert "NON-CANONICAL" not in report


# --- CLI gate ----------------------------------------------------------------


def test_diagnose_multigraph_cli_fail_on_noncanonical_exits_nonzero(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    graph_path = tmp_path / "graph.json"
    payload = {
        "nodes": [
            _doc_node("docs_architecture", "ARCHITECTURE.md", "ARCHITECTURE.md"),
            _doc_node(
                "docs_architecture_document", "ARCHITECTURE.md - long form", "adr/001.md"
            ),
        ],
        "edges": [],
    }
    graph_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        [
            "graphify", "diagnose", "multigraph", "--graph", str(graph_path),
            "--fail-on-noncanonical",
        ],
    )

    try:
        mainmod.main()
        exited = False
        code = 0
    except SystemExit as exc:
        exited = True
        code = exc.code

    assert exited is True
    assert code == 1
    assert "verdict: NON-CANONICAL" in capsys.readouterr().out


def test_diagnose_multigraph_cli_noncanonical_still_exits_zero_by_default(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    """Backward compatibility: existing scripts/CI calling this command without
    the new flag must keep getting exit 0, even on a non-canonical graph."""
    graph_path = tmp_path / "graph.json"
    payload = {
        "nodes": [
            _doc_node("docs_architecture", "ARCHITECTURE.md", "ARCHITECTURE.md"),
            _doc_node(
                "docs_architecture_document", "ARCHITECTURE.md - long form", "adr/001.md"
            ),
        ],
        "edges": [],
    }
    graph_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "diagnose", "multigraph", "--graph", str(graph_path)],
    )

    mainmod.main()  # must not raise SystemExit

    assert "verdict: NON-CANONICAL" in capsys.readouterr().out


# --- deterministic graph generation -----------------------------------------


def _sample_extraction() -> dict:
    return {
        "nodes": [
            _doc_node("docs_a", "A.md", "A.md"),
            _doc_node("docs_b", "B.md", "B.md"),
            _doc_node("docs_c", "C.md", "C.md"),
            _doc_node("docs_d", "D.md", "D.md"),
            {
                "id": "docs_a_concept_one", "label": "Concept One", "file_type": "concept",
                "source_file": "A.md",
            },
            {
                "id": "docs_b_concept_two", "label": "Concept Two", "file_type": "concept",
                "source_file": "B.md",
            },
        ],
        "edges": [
            _edge("docs_a", "docs_b", "A.md"),
            _edge("docs_b", "docs_c", "B.md"),
            _edge("docs_c", "docs_d", "C.md"),
            _edge("docs_a", "docs_c", "A.md", relation="cites"),
            {
                "source": "docs_a", "target": "docs_a_concept_one", "relation": "references",
                "confidence": "EXTRACTED", "source_file": "A.md",
            },
            {
                "source": "docs_b", "target": "docs_b_concept_two", "relation": "references",
                "confidence": "EXTRACTED", "source_file": "B.md",
            },
            {
                "source": "docs_a_concept_one", "target": "docs_b_concept_two",
                "relation": "semantically_similar_to", "confidence": "INFERRED",
                "confidence_score": 0.75, "source_file": "A.md",
            },
        ],
        "hyperedges": [],
    }


def test_build_and_cluster_are_deterministic_across_repeated_runs(tmp_path: Path):
    """Same extraction JSON -> identical graph.json, run twice from scratch.

    Covers the property the "same repository -> identical graph" ask is really
    about: node/edge sets, and community assignment (Louvain is seeded, but
    that guarantee had no end-to-end regression test locking it in)."""
    import copy

    outputs = []
    for i in range(2):
        extraction = copy.deepcopy(_sample_extraction())
        graph = build_from_json(extraction, root=".", directed=False)
        communities = cluster(graph)
        out_path = tmp_path / f"graph_{i}.json"
        wrote = to_json(graph, communities, str(out_path), force=True, built_at_commit="test")
        assert wrote is True
        outputs.append(json.loads(out_path.read_text(encoding="utf-8")))

    def _strip_volatile(data: dict) -> dict:
        # built_at_commit is pinned above; nothing else should vary, but keep
        # this explicit so a future volatile field doesn't silently mask drift.
        return {k: v for k, v in data.items() if k != "built_at_commit"}

    assert _strip_volatile(outputs[0]) == _strip_volatile(outputs[1])
