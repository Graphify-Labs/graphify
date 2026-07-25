from __future__ import annotations

from pathlib import Path

from graphify.extract import _normalize_edge_occurrences, extract
from graphify.build import build_from_json, canonical_edge_key, edge_datas
from graphify.diagnostics import diagnose_extraction


def test_python_type_occurrences_use_real_spans_and_parameters(tmp_path: Path):
    source = tmp_path / "sample.py"
    source.write_text(
        "class Thing: pass\n"
        "def same(a: Thing, b: Thing, c: list[Thing]): pass\n"
        "def split(\n"
        "    a: Thing,\n"
        "    b: Thing,\n"
        "): pass\n"
    )

    result = extract([source], cache_root=tmp_path / "cache", parallel=False)
    refs = [
        edge for edge in result["edges"]
        if edge.get("relation") == "references"
        and edge.get("target", "").endswith("thing")
    ]
    same = [edge for edge in refs if edge["source"].endswith("_same")]
    split = [edge for edge in refs if edge["source"].endswith("_split")]

    parameter_edge = next(edge for edge in same if edge["context"] == "parameter_type")
    assert parameter_edge["source_location"] == "L2"
    assert parameter_edge["occurrence_count"] == 2
    assert {item["parameter"] for item in parameter_edge["occurrences"]} == {"a", "b"}
    assert all(":C" in item["source_span"] for item in parameter_edge["occurrences"])
    assert {edge["source_location"] for edge in split} == {"L4", "L5"}


def test_post_resolver_normalization_suppresses_same_span_only():
    base = {
        "source": "a",
        "target": "b",
        "relation": "calls",
        "context": "call",
        "confidence": "EXTRACTED",
        "source_file": "a.py",
        "source_location": "L10",
        "source_span": "L10:C5-L10:C8",
    }
    edges = [dict(base), dict(base)]
    diagnostics = _normalize_edge_occurrences(edges)

    assert len(edges) == 1
    assert edges[0]["occurrence_count"] == 1
    assert diagnostics["suppressed_producer_duplicate_occurrences"] == 1
    assert diagnostics["post_normalization_unclassified_duplicates"] == 0


def test_occurrence_evidence_does_not_change_stable_edge_key():
    attrs = {
        "relation": "references",
        "context": "parameter_type",
        "source_file": "a.py",
        "source_location": "L2",
    }
    first = {
        **attrs,
        "occurrences": [{"source_span": "L2:C10-L2:C15", "parameter": "a"}],
        "occurrence_count": 1,
    }
    second = {
        **attrs,
        "occurrences": [{"source_span": "L2:C20-L2:C25", "parameter": "b"}],
        "occurrence_count": 1,
    }
    assert canonical_edge_key("a", "b", first) == canonical_edge_key("a", "b", second)

    graph = build_from_json(
        {
            "nodes": [{"id": "a"}, {"id": "b"}],
            "edges": [
                {"source": "a", "target": "b", **first},
                {"source": "a", "target": "b", **second},
            ],
        },
        multigraph=True,
    )
    edge = edge_datas(graph, "a", "b")[0]
    assert edge["occurrence_count"] == 2
    assert len(edge["occurrences"]) == 2


def test_diagnostic_classifies_occurrences_and_zero_node_outcomes():
    extraction = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [{
            "source": "a",
            "target": "b",
            "relation": "calls",
            "occurrence_count": 2,
            "occurrences": [
                {"source_span": "L1:C1-L1:C2"},
                {"source_span": "L1:C4-L1:C5"},
            ],
        }],
        "extraction_diagnostics": {
            "legitimate_repeated_source_occurrences": 1,
            "suppressed_producer_duplicate_occurrences": 1,
            "unlocated_duplicate_occurrences": 0,
            "post_normalization_exact_duplicate_edges": 0,
            "post_normalization_unclassified_duplicates": 0,
        },
        "file_outcomes": [
            {"source_file": "data.json", "status": "skipped_intentional", "reason": "data"},
            {"source_file": "bad.py", "status": "failed", "reason": "parse"},
        ],
    }
    summary = diagnose_extraction(extraction, multigraph=True)
    assert summary["exact_duplicate_occurrences"] == 2
    assert summary["legitimate_repeated_source_occurrences"] == 1
    assert summary["suppressed_producer_duplicate_occurrences"] == 1
    assert summary["intentionally_skipped_files"] == 1
    assert summary["failed_extraction_files"] == 1
