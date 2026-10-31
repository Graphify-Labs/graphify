"""`path` reports the path's overall confidence: its weakest hop (#4885).

Each hop was labelled on its own, so a path with one INFERRED or AMBIGUOUS hop
among EXTRACTED ones read as a list of independent tags. The CLI and the MCP
`shortest_path` tool now end with one summary line naming the weakest hop,
ranked by `_CONFIDENCE_RANK` and then by the lowest `confidence_score`.
"""
from __future__ import annotations

import json

from networkx.readwrite import json_graph

import graphify.__main__ as mainmod
from graphify.build import build_from_json
from graphify.serve import _path_confidence_line, _shortest_path_text

REPORT_SUMMARY = "Path confidence: INFERRED (weakest hop 2: dispatches_to, score 0.75)"


def _node(nid, label):
    return {"id": nid, "label": label, "file_type": "code", "source_file": "Report.cs"}


def _report_graph():
    """The graph `graphify update` builds for the issue's Report.cs repro."""
    return build_from_json({
        "nodes": [
            _node("report_exporter_run", ".Run()"),
            _node("report_ireport_build", ".Build()"),
            _node("report_pdfreport_build", ".Build()"),
        ],
        "edges": [
            {"source": "report_exporter_run", "target": "report_ireport_build",
             "relation": "calls", "confidence": "INFERRED", "confidence_score": 0.85,
             "source_file": "Report.cs", "source_location": "L7"},
            {"source": "report_ireport_build", "target": "report_pdfreport_build",
             "relation": "dispatches_to", "confidence": "INFERRED", "confidence_score": 0.75,
             "source_file": "Report.cs", "source_location": "L2"},
        ],
        "hyperedges": [],
    })


def test_cli_path_prints_weakest_hop(monkeypatch, tmp_path, capsys):
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(json_graph.node_link_data(_report_graph(), edges="links")))
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", [
        "graphify", "path", "report_exporter_run", "report_pdfreport_build", "--graph", str(p)])
    mainmod.main()
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "Shortest path (2 hops):"
    assert lines[2] == REPORT_SUMMARY


def test_mcp_shortest_path_prints_weakest_hop():
    out = _shortest_path_text(_report_graph(), {"source": "report_exporter_run",
                                                "target": "report_pdfreport_build"})
    assert out.splitlines()[-1] == REPORT_SUMMARY


def _e(rel, conf=None, score=None, **kw):
    d = {"relation": rel, **kw}
    if conf is not None:
        d["confidence"] = conf
    if score is not None:
        d["confidence_score"] = score
    return d


def test_tier_outranks_score():
    hops = [[_e("calls", "EXTRACTED", 1.0)], [_e("uses", "AMBIGUOUS", 0.9)],
            [_e("calls", "INFERRED", 0.5)]]
    assert _path_confidence_line(hops) == "Path confidence: AMBIGUOUS (weakest hop 2: uses, score 0.9)"


def test_lowest_score_breaks_a_tier_tie_and_missing_score_is_not_weaker():
    hops = [[_e("calls", "INFERRED")], [_e("calls", "INFERRED", 0.6)], [_e("calls", "INFERRED", 0.8)]]
    assert _path_confidence_line(hops) == "Path confidence: INFERRED (weakest hop 2: calls, score 0.6)"


def test_all_extracted_without_scores_names_first_hop():
    hops = [[_e("imports", "EXTRACTED")], [_e("calls", "EXTRACTED")]]
    assert _path_confidence_line(hops) == "Path confidence: EXTRACTED (weakest hop 1: imports)"


def test_extracted_score_is_neither_printed_nor_ranked():
    """EXTRACTED stays bare, like the hop tags; a stored 1.0 must not pick the hop."""
    hops = [[_e("imports", "EXTRACTED")], [_e("calls", "EXTRACTED", 1.0)]]
    assert _path_confidence_line(hops) == "Path confidence: EXTRACTED (weakest hop 1: imports)"


def test_extracted_path_from_built_graph_prints_no_score():
    G = build_from_json({
        "nodes": [_node("report_exporter", "Exporter"), _node("report_exporter_run", ".Run()")],
        "edges": [{"source": "report_exporter", "target": "report_exporter_run",
                   "relation": "method", "confidence": "EXTRACTED", "confidence_score": 1.0,
                   "source_file": "Report.cs", "source_location": "L7"}],
        "hyperedges": [],
    })
    out = _shortest_path_text(G, {"source": "report_exporter", "target": "report_exporter_run"})
    assert out.splitlines()[-1] == "Path confidence: EXTRACTED (weakest hop 1: method)"


def test_non_finite_score_is_treated_as_missing():
    hops = [[_e("calls", "INFERRED", float("nan"))], [_e("calls", "INFERRED", 0.7)]]
    assert _path_confidence_line(hops) == "Path confidence: INFERRED (weakest hop 2: calls, score 0.7)"


def test_parallel_edges_and_also_seen_count_toward_their_hop():
    hops = [
        [_e("calls", "EXTRACTED"), _e("references", "INFERRED", 0.7)],
        [_e("calls", "EXTRACTED", also_seen=[{"confidence": "AMBIGUOUS", "confidence_score": 0.2}])],
    ]
    assert _path_confidence_line(hops) == "Path confidence: AMBIGUOUS (weakest hop 2: calls, score 0.2)"


def test_hop_without_confidence_makes_path_unknown():
    hops = [[_e("calls", "EXTRACTED")], [_e("calls")]]
    assert _path_confidence_line(hops) == "Path confidence: unknown (hop 2: calls has no confidence tag)"


def _two_route_graph():
    """Two equal-length (2-hop) routes A -> C: a strong one via B1 (all
    EXTRACTED) and a weak one via B2 (an AMBIGUOUS hop). #4881 second half:
    the reported confidence must reflect the weakest route, not whichever one
    networkx returns first."""
    def n(nid):
        return {"id": nid, "label": nid, "file_type": "code", "source_file": "m.py"}
    return build_from_json({
        "nodes": [n("A"), n("B1"), n("C"), n("B2")],
        "edges": [
            {"source": "A", "target": "B1", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "m.py", "source_location": "L1"},
            {"source": "B1", "target": "C", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "m.py", "source_location": "L2"},
            {"source": "A", "target": "B2", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "m.py", "source_location": "L3"},
            {"source": "B2", "target": "C", "relation": "dispatches_to",
             "confidence": "AMBIGUOUS", "confidence_score": 0.3,
             "source_file": "m.py", "source_location": "L4"},
        ],
        "hyperedges": [],
    })


def test_multiple_routes_report_the_weakest_route():
    """Among equal-length routes, the weakest route's confidence is surfaced."""
    G = _two_route_graph()
    out = _shortest_path_text(G, {"source": "A", "target": "C"})
    last = out.splitlines()[-1]
    # Must report the AMBIGUOUS (weak) route, not the EXTRACTED (strong) one,
    # and say it chose the weakest of the equal-length routes.
    assert "AMBIGUOUS" in last, out
    assert "weakest of 2 equal-length routes" in last, out


def test_single_route_has_no_equal_length_note():
    """A unique shortest path must not carry the multi-route suffix."""
    G = _report_graph()
    out = _shortest_path_text(G, {"source": "report_exporter_run", "target": "report_pdfreport_build"})
    assert "equal-length routes" not in out, out
