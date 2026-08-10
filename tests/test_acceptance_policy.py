"""The Graphify acceptance policy (#2311).

The value of a gate is entirely in what it does NOT fail on. Expected external
imports, intentionally non-graph-bearing files and deterministic edge
consolidation are permanent properties of an honest graph over a real corpus; a
gate that fails on those gets ignored, and then the real defects ride through.
"""
from graphify.diagnostics import (
    evaluate_acceptance,
    format_acceptance_report,
)


def _clean(**overrides):
    summary = {
        "non_object_edges": 0,
        "missing_endpoint_edges": 0,
        "dangling_endpoint_edges": 0,
        "external_import_edges": 0,
        "external_import_targets": [],
        "unexpected_dangling_edges": 0,
        "unverified_node_count": 0,
        "self_loop_edges": 0,
        "post_build_error": "",
        "undirected_same_endpoint_collapsed_edges": 0,
        "same_endpoint_group_count": 0,
        "provenance_edge_count": 0,
    }
    summary.update(overrides)
    return summary


def test_clean_summary_passes():
    verdict = evaluate_acceptance(_clean())
    assert verdict["passed"]
    assert verdict["failures"] == []


def test_external_imports_and_collapses_report_without_failing():
    verdict = evaluate_acceptance(_clean(
        dangling_endpoint_edges=43,
        external_import_edges=43,
        external_import_targets=["json", "os", "pathlib"],
        undirected_same_endpoint_collapsed_edges=1112,
        same_endpoint_group_count=526,
    ))
    assert verdict["passed"], "expected externals must never fail the build"
    assert any("43 verified external imports" in n for n in verdict["informational"])
    assert any("1112 deterministic" in n for n in verdict["informational"])


def test_unexpected_semantic_dangling_fails():
    verdict = evaluate_acceptance(_clean(
        dangling_endpoint_edges=74, external_import_edges=43,
        unexpected_dangling_edges=31,
    ))
    assert not verdict["passed"]
    assert any("31 unexpected dangling" in f for f in verdict["failures"])


def test_malformed_and_missing_endpoints_fail():
    verdict = evaluate_acceptance(_clean(non_object_edges=2, missing_endpoint_edges=3))
    assert not verdict["passed"]
    assert any("malformed" in f for f in verdict["failures"])
    assert any("missing endpoint fields" in f for f in verdict["failures"])


def test_unverified_code_nodes_fail():
    verdict = evaluate_acceptance(_clean(unverified_node_count=7))
    assert not verdict["passed"]
    assert any("7 unverified code nodes" in f for f in verdict["failures"])


def test_build_error_fails():
    verdict = evaluate_acceptance(_clean(post_build_error="ValueError: boom"))
    assert not verdict["passed"]
    assert any("graph build error" in f for f in verdict["failures"])


def test_self_loops_fail_unless_explicitly_allowed():
    assert not evaluate_acceptance(_clean(self_loop_edges=4))["passed"]

    allowed = evaluate_acceptance(_clean(self_loop_edges=4), allow_self_loops=True)
    assert allowed["passed"]
    assert any("explicitly allowed" in n for n in allowed["informational"])


def test_provenance_loss_fails_only_when_pinned():
    # Unpinned: provenance count is informational, not a gate.
    assert evaluate_acceptance(_clean(provenance_edge_count=100))["passed"]

    # Pinned and matching -> pass.
    assert evaluate_acceptance(
        _clean(provenance_edge_count=536), expected_provenance_edges=536
    )["passed"]

    # Pinned and drifted -> fail: provenance vanished between rebuilds.
    drifted = evaluate_acceptance(
        _clean(provenance_edge_count=12), expected_provenance_edges=536
    )
    assert not drifted["passed"]
    assert any("nondeterministically" in f for f in drifted["failures"])


def test_report_marks_failures_and_final_verdict():
    failing = format_acceptance_report(
        evaluate_acceptance(_clean(unexpected_dangling_edges=1))
    )
    assert "FAIL" in failing
    assert failing.strip().endswith("FAIL")

    passing = format_acceptance_report(
        evaluate_acceptance(_clean(external_import_edges=43))
    )
    assert passing.strip().endswith("PASS")
    assert "  info  " in passing
