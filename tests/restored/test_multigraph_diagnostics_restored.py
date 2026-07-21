"""Retained diagnostics for transient extraction DTOs."""

from __future__ import annotations

from copy import deepcopy
import json

from graphify.diagnostics import (
    diagnose_extraction,
    format_diagnostic_json,
    format_diagnostic_report,
    scan_producer_suppression_sites,
)


def _diagnostic_fixture() -> dict:
    nodes = [
        {"id": value, "label": value.upper(), "file_type": "code", "source_file": f"{value}.py"}
        for value in ("a", "b", "c")
    ]
    edges = [
        {"source": "a", "target": "b", "relation": "calls", "confidence": "EXTRACTED", "source_file": "a.py", "source_location": "L1", "context": "call"},
        {"source": "a", "target": "b", "relation": "imports", "confidence": "EXTRACTED", "source_file": "a.py", "source_location": "L2", "context": "import"},
        {"source": "a", "target": "b", "relation": "calls", "confidence": "INFERRED", "source_file": "a.py", "source_location": "L3", "context": "call"},
        {"source": "a", "target": "b", "relation": "calls", "confidence": "EXTRACTED", "source_file": "a.py", "source_location": "L1", "context": "call"},
        {"source": "a", "target": "missing", "relation": "calls", "source_file": "a.py"},
        {"source": "a", "relation": "calls", "source_file": "a.py"},
        {"source": "c", "target": "c", "relation": "references", "source_file": "c.py"},
    ]
    return {"nodes": nodes, "edges": edges}


def test_diagnose_extraction_categorizes_same_endpoint_collapse() -> None:
    summary = diagnose_extraction(_diagnostic_fixture(), directed=True)
    assert summary["node_count"] == 3
    assert summary["raw_edge_count"] == 7
    assert summary["valid_candidate_edges"] == 5
    assert summary["missing_endpoint_edges"] == 1
    assert summary["dangling_endpoint_edges"] == 1
    assert summary["self_loop_edges"] == 1
    assert summary["exact_duplicate_edges"] == 1
    assert summary["directed_unique_endpoint_pairs"] == 2
    assert summary["directed_same_endpoint_collapsed_edges"] == 3
    assert summary["relation_variant_groups"] == 1
    assert summary["post_build_graph_type"] == "digraph"
    assert summary["post_build_edge_count"] == 2


def test_diagnose_extraction_accepts_node_link_links_key() -> None:
    extraction = _diagnostic_fixture()
    extraction["links"] = extraction.pop("edges")
    summary = diagnose_extraction(extraction, directed=True)
    assert summary["raw_edge_count"] == 7
    assert summary["directed_same_endpoint_collapsed_edges"] == 3


def test_diagnose_extraction_does_not_mutate_input() -> None:
    extraction = _diagnostic_fixture()
    original = deepcopy(extraction)
    diagnose_extraction(extraction, directed=True)
    assert extraction == original


def test_diagnose_extraction_handles_malformed_shapes_without_crashing() -> None:
    extraction = {
        "nodes": [{"id": "a"}, ["bad"], {"id": "b"}],
        "edges": [
            None,
            ["bad"],
            {"from": "a", "to": "b", "relation": "legacy"},
            {"source": "a", "target": {"bad": "target"}},
            {"source": "a", "target": "missing"},
            {"source": "", "target": "b"},
        ],
    }
    summary = diagnose_extraction(extraction, directed=True)
    assert summary["node_count"] == 2
    assert summary["raw_edge_count"] == 6
    assert summary["non_object_edges"] == 2
    assert summary["missing_endpoint_edges"] == 1
    assert summary["dangling_endpoint_edges"] == 2
    assert summary["valid_candidate_edges"] == 1
    assert summary["post_build_error"].startswith(("TypeError:", "AttributeError:"))


def test_diagnose_extraction_handles_non_list_nodes_and_edges() -> None:
    summary = diagnose_extraction(
        {"nodes": {"id": "a"}, "edges": {"source": "a", "target": "b"}},
        directed=True,
    )
    assert summary["node_count"] == 0
    assert summary["raw_edge_count"] == 0
    assert summary["valid_candidate_edges"] == 0


def test_diagnose_extraction_bounds_examples() -> None:
    summary = diagnose_extraction(_diagnostic_fixture(), directed=True, max_examples=0)
    assert summary["directed_same_endpoint_collapsed_edges"] == 3
    assert summary["examples"] == []


def test_diagnose_extraction_stops_examples_at_requested_limit() -> None:
    extraction = _diagnostic_fixture()
    extraction["nodes"].append({"id": "d", "source_file": "d.py"})
    extraction["edges"].extend([
        {"source": "b", "target": "d", "relation": "imports"},
        {"source": "b", "target": "d", "relation": "calls"},
    ])
    summary = diagnose_extraction(extraction, directed=True, max_examples=1)
    assert summary["same_endpoint_group_count"] == 2
    assert len(summary["examples"]) == 1


def test_format_diagnostic_report_includes_build_and_suppression_errors(tmp_path) -> None:
    summary = diagnose_extraction(
        {"nodes": [{"id": "a"}, ["bad"]], "edges": []},
        extract_path=tmp_path / "missing-extract.py",
    )
    report = format_diagnostic_report(summary)
    assert "post_build_error:" in report
    assert "producer_suppression_error: file not found" in report


def test_diagnostic_json_report_is_serializable() -> None:
    payload = format_diagnostic_json(
        diagnose_extraction(_diagnostic_fixture(), directed=True)
    )
    assert payload["schema_version"] == 1
    assert payload["summary"]["raw_edge_count"] == 7
    assert "producer_suppression" in payload
    json.dumps(payload)


def test_scan_producer_suppression_sites_finds_seen_sets(tmp_path) -> None:
    source = tmp_path / "extract.py"
    source.write_text(
        "seen_call_pairs: set[tuple[str, str]] = set()\n"
        "seen_static_ref_pairs: set[tuple[str, str, str]] = set()\n"
        "other = set()\n"
    )
    result = scan_producer_suppression_sites(source)
    assert result["total_sites"] == 2
    assert [site["tuple_arity"] for site in result["sites"]] == [2, 3]


def test_scan_producer_suppression_sites_handles_unknown_tuple_arity(tmp_path) -> None:
    source = tmp_path / "extract.py"
    source.write_text("seen_blank: set[tuple[ ]] = set()\n")
    result = scan_producer_suppression_sites(source)
    assert result["total_sites"] == 1
    assert result["sites"][0]["tuple_arity"] == 0


def test_scan_producer_suppression_sites_reports_missing_file(tmp_path) -> None:
    result = scan_producer_suppression_sites(tmp_path / "missing-extract.py")
    assert result == {
        "path": str(tmp_path / "missing-extract.py"),
        "total_sites": 0,
        "sites": [],
        "error": "file not found",
    }
