"""Edge confidence scores in `path`, `explain` and neighbor output (#4882).

graph.json stores `confidence_score` next to `confidence` (interface dispatch
writes 0.85 / 0.75 / 0.65 by implementer count), but the text renderers only
printed the bare tag, so `[INFERRED]` hid whether an edge was a strong or a
weak inference. A scored non-EXTRACTED edge now renders as `[INFERRED 0.75]`;
EXTRACTED and unscored edges keep the bare tag.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.serve import _confidence_tag, _neighbor_lines, _shortest_path_text

_REPORT_CS = (
    "public interface IReport { string Build(); }\n"
    'public class PdfReport : IReport { public string Build() { return "pdf"; } }\n'
    'public class CsvReport : IReport { public string Build() { return "csv"; } }\n'
    "public class Exporter {\n"
    "  private readonly IReport _report;\n"
    "  public Exporter(IReport report) { _report = report; }\n"
    "  public string Run() { return _report.Build(); }\n"
    "}\n"
)


@pytest.mark.parametrize("edge, expected", [
    ({"confidence": "INFERRED", "confidence_score": 0.75}, "INFERRED 0.75"),
    ({"confidence": "INFERRED", "confidence_score": 0.8}, "INFERRED 0.80"),
    ({"confidence": "AMBIGUOUS", "confidence_score": 0.2}, "AMBIGUOUS 0.20"),
    ({"confidence": "INFERRED"}, "INFERRED"),
    ({"confidence": "INFERRED", "confidence_score": None}, "INFERRED"),
    ({"confidence": "INFERRED", "confidence_score": "0.75"}, "INFERRED"),
    ({"confidence": "INFERRED", "confidence_score": True}, "INFERRED"),
    ({"confidence": "INFERRED", "confidence_score": float("nan")}, "INFERRED"),
    ({"confidence": "EXTRACTED", "confidence_score": 1.0}, "EXTRACTED"),
    ({"confidence_score": 0.75}, ""),
    ({}, ""),
])
def test_confidence_tag(edge, expected):
    assert _confidence_tag(edge) == expected


@pytest.fixture
def report_graph(tmp_path):
    """The issue's Report.cs repro, extracted and written as graph.json."""
    (tmp_path / "Report.cs").write_text(_REPORT_CS)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        extraction = extract([Path("Report.cs")], cache_root=Path(tempfile.mkdtemp()))
    finally:
        os.chdir(old)
    scores = {(e["source"], e["relation"], e["target"]): e.get("confidence_score")
              for e in extraction["edges"] if e.get("confidence") == "INFERRED"}
    assert scores == {
        ("report_exporter_run", "calls", "report_ireport_build"): 0.85,
        ("report_ireport_build", "dispatches_to", "report_pdfreport_build"): 0.75,
        ("report_ireport_build", "dispatches_to", "report_csvreport_build"): 0.75,
    }
    G = build_from_json(extraction, root=tmp_path)
    out = tmp_path / "graph.json"
    to_json(G, {0: list(G.nodes)}, str(out))
    return out


def _cli(monkeypatch, capsys, *argv):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", *argv])
    mainmod.main()
    return capsys.readouterr().out


def _load(graph_path):
    raw = json.loads(graph_path.read_text())
    return json_graph.node_link_graph({**raw, "directed": True}, edges="links")


def test_explain_prints_scores(report_graph, monkeypatch, capsys):
    out = _cli(monkeypatch, capsys, "explain", "report_ireport_build",
               "--graph", str(report_graph))
    assert out.count("[dispatches_to] [INFERRED 0.75]") == 2
    assert "<-- Exporter.Run() [calls] [INFERRED 0.85]" in out
    assert "[method] [EXTRACTED]" in out
    assert "[INFERRED]" not in out


def test_cli_path_prints_scores(report_graph, monkeypatch, capsys):
    out = _cli(monkeypatch, capsys, "path", "report_exporter_run",
               "report_pdfreport_build", "--graph", str(report_graph))
    assert ("--calls [INFERRED 0.85]--> IReport.Build() "
            "--dispatches_to [INFERRED 0.75]--> PdfReport.Build()") in out


def test_mcp_path_prints_scores(report_graph):
    out = _shortest_path_text(_load(report_graph), {
        "source": "report_exporter_run", "target": "report_pdfreport_build",
    })
    assert ("--calls [INFERRED 0.85]--> IReport.Build() "
            "--dispatches_to [INFERRED 0.75]--> PdfReport.Build()") in out


def test_mcp_neighbors_print_scores(report_graph):
    lines = _neighbor_lines(_load(report_graph), "report_ireport_build")
    assert sum("[dispatches_to] [INFERRED 0.75]" in ln for ln in lines) == 2
    assert any(ln.startswith("  <-- Exporter.Run() [calls] [INFERRED 0.85]") for ln in lines)
    assert any("[method] [EXTRACTED] " in ln for ln in lines)
