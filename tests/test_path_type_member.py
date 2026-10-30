"""`Type.Member` endpoints name the member, not the type (#4884).

A member's label is `.Build()`, so `PdfReport.Build` matched no exact tier and
token scoring picked the `PdfReport` class. `path "Exporter.Run" "PdfReport.Build"`
then printed a class-to-class route through the file as if it joined the two
methods, and `path "Run" "PdfReport.Build"` found no route at all, since nothing
leads from a method back up to a class. The query now resolves through the
type's membership edges, refuses several matches with their ids, and fails
closed when the type exists but declares no such member.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod
from graphify.cli import EXIT_AMBIGUOUS, EXIT_NOT_FOUND
from graphify.extract import extract
from graphify.serve import _resolve_path_endpoint, _resolve_single_node, _shortest_path_text

_REPORT_CS = (
    "public interface IReport { string Build(); }\n"
    "public class PdfReport : IReport { public string Build() { return \"pdf\"; } }\n"
    "public class CsvReport : IReport { public string Build() { return \"csv\"; } }\n"
    "public class Exporter {\n"
    "  private readonly IReport _report;\n"
    "  public Exporter(IReport report) { _report = report; }\n"
    "  public string Run() { return _report.Build(); }\n"
    "}\n"
)


@pytest.fixture(scope="module")
def report_graph(tmp_path_factory) -> Path:
    tmp_path = tmp_path_factory.mktemp("report")
    src = tmp_path / "src"
    src.mkdir()
    (src / "Report.cs").write_text(_REPORT_CS)
    old = os.getcwd()
    try:
        os.chdir(src)
        r = extract([Path("Report.cs")], cache_root=tmp_path / "cache")
    finally:
        os.chdir(old)
    gp = tmp_path / "graph.json"
    gp.write_text(json.dumps({
        "directed": False, "multigraph": False, "graph": {},
        "nodes": r["nodes"], "links": r["edges"],
    }))
    return gp


def _write_nodes(tmp_path, nodes, links) -> Path:
    gp = tmp_path / "graph.json"
    gp.write_text(json.dumps({
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": i, "label": lbl, "source_file": sf, "source_location": loc}
            for i, lbl, sf, loc in nodes
        ],
        "links": [
            {"source": a, "target": b, "relation": rel, "confidence": "EXTRACTED"}
            for a, b, rel in links
        ],
    }))
    return gp


def _load(gp: Path):
    return json_graph.node_link_graph(
        {**json.loads(gp.read_text()), "directed": True}, edges="links")


def _path(monkeypatch, capsys, gp, src, tgt):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
                        ["graphify", "path", src, tgt, "--graph", str(gp)])
    code = 0
    try:
        mainmod.main()
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.mark.parametrize("source", ["Exporter.Run", "Run", "Exporter.Run()"])
def test_type_member_endpoint_routes_to_the_method(monkeypatch, capsys, report_graph, source):
    code, out, err = _path(monkeypatch, capsys, report_graph, source, "PdfReport.Build")
    assert code == 0, err
    assert "Shortest path (2 hops):" in out
    assert ".Run() --calls [INFERRED]--> .Build() --dispatches_to [INFERRED]--> .Build()" in out
    assert "contains" not in out


def test_type_member_endpoint_resolves_each_implementer(report_graph):
    G = _load(report_graph)
    resolved = {q: _resolve_path_endpoint(G, q)[0]
                for q in ("PdfReport.Build", "CsvReport.Build()", "IReport.Build", "Exporter.Run")}
    assert resolved == {
        "PdfReport.Build": "report_pdfreport_build",
        "CsvReport.Build()": "report_csvreport_build",
        "IReport.Build": "report_ireport_build",
        "Exporter.Run": "report_exporter_run",
    }


def test_explain_resolves_type_member_to_the_method(report_graph):
    G = _load(report_graph)
    assert _resolve_single_node(G, "PdfReport.Build") == ("report_pdfreport_build", None)


def test_type_without_the_member_fails_closed(monkeypatch, capsys, report_graph):
    """Scoring `PdfReport.Missing` would land on the class and print a route to it."""
    code, out, err = _path(monkeypatch, capsys, report_graph, "Exporter.Run", "PdfReport.Missing")
    assert code == EXIT_NOT_FOUND
    assert "Shortest path" not in out
    assert "no type 'PdfReport' declares 'Missing'" in err


def test_shortest_path_tool_shares_type_member_resolution(report_graph):
    G = _load(report_graph)
    out = _shortest_path_text(G, {"source": "Exporter.Run", "target": "PdfReport.Build"})
    assert "Shortest path (2 hops):" in out
    assert "dispatches_to" in out and "contains" not in out
    out = _shortest_path_text(G, {"source": "Exporter.Run", "target": "PdfReport.Missing"})
    assert "Shortest path" not in out
    assert "no type 'PdfReport' declares 'Missing'" in out


def test_type_member_in_two_files_is_refused(monkeypatch, tmp_path, capsys):
    gp = _write_nodes(tmp_path, [
        ("a_run", ".Run()", "a/Exporter.cs", "L3"),
        ("a_pdf", "PdfReport", "a/Pdf.cs", "L1"),
        ("a_pdf_build", ".Build()", "a/Pdf.cs", "L2"),
        ("b_pdf", "PdfReport", "b/Pdf.cs", "L1"),
        ("b_pdf_build", ".Build()", "b/Pdf.cs", "L2"),
    ], [
        ("a_pdf", "a_pdf_build", "method"),
        ("b_pdf", "b_pdf_build", "method"),
        ("a_run", "a_pdf_build", "calls"),
    ])
    code, out, err = _path(monkeypatch, capsys, gp, "Run", "PdfReport.Build")
    assert code == EXIT_AMBIGUOUS
    assert "Shortest path" not in out
    assert "Ambiguous: 'PdfReport.Build' matches 2 nodes in different files." in err
    assert "a_pdf_build" in err and "b_pdf_build" in err


def test_overloaded_member_is_refused_with_ids(monkeypatch, tmp_path, capsys):
    gp = _write_nodes(tmp_path, [
        ("pdf", "PdfReport", "Pdf.cs", "L1"),
        ("pdf_build", ".Build()", "Pdf.cs", "L2"),
        ("pdf_build_1", ".Build()", "Pdf.cs", "L3"),
        ("other_build", ".Build()", "Other.cs", "L1"),
    ], [
        ("pdf", "pdf_build", "method"),
        ("pdf", "pdf_build_1", "method"),
    ])
    code, _out, err = _path(monkeypatch, capsys, gp, "PdfReport.Build", "pdf")
    assert code == EXIT_AMBIGUOUS
    assert "Ambiguous: 'PdfReport.Build' matches 2 nodes in Pdf.cs." in err
    assert "pdf_build_1" in err and "other_build" not in err


def _nested_graph(tmp_path) -> Path:
    return _write_nodes(tmp_path, [
        ("a", "A.cs", "A.cs", "L1"),
        ("ns", "Acme.Io", "A.cs", "L1"),
        ("outer", "Outer", "A.cs", "L2"),
        ("outer_go", ".Go()", "A.cs", "L3"),
        ("inner", "Inner", "A.cs", "L4"),
        ("inner_go", ".Go()", "A.cs", "L5"),
    ], [
        ("a", "ns", "contains"),
        ("a", "outer", "contains"),
        ("outer", "inner", "contains"),
        ("outer", "outer_go", "method"),
        ("inner", "inner_go", "method"),
    ])


def test_enclosing_types_qualify_a_nested_member(tmp_path):
    G = _load(_nested_graph(tmp_path))
    assert _resolve_path_endpoint(G, "Outer.Inner.Go")[0] == "inner_go"
    assert _resolve_path_endpoint(G, "Inner.Go")[0] == "inner_go"
    assert _resolve_path_endpoint(G, "Outer.Go")[0] == "outer_go"
    assert _resolve_path_endpoint(G, "Outer.Inner")[0] == "inner"
    # Direction counts: Inner owns no Outer.
    nid, _, err = _resolve_path_endpoint(G, "Inner.Outer")
    assert nid is None and err is not None
    assert "no type 'Inner' declares 'Outer'" in err


def test_namespace_qualifier_is_refused_with_the_bare_type_members(tmp_path):
    """The file owns the type, not the namespace node, so a namespace qualifier
    resolves nothing; the members of the bare type name are offered instead."""
    G = _load(_nested_graph(tmp_path))
    nid, _, err = _resolve_path_endpoint(G, "Acme.Io.Outer.Go")
    assert nid is None and err is not None
    assert "no type 'Acme.Io.Outer' declares 'Go'" in err
    assert "id: outer_go" in err and "inner_go" not in err


def test_dotted_label_and_non_type_owner_keep_their_old_resolution(tmp_path):
    G = _load(_write_nodes(tmp_path, [
        ("cfg", "Config", "app.ts", "L1"),
        ("cfg_load", ".load()", "app.ts", "L2"),
        ("literal", "Config.load", "routes.ts", "L9"),
        ("helper", "release notes helper", "notes.md", "L1"),
    ], [
        ("cfg", "cfg_load", "method"),
    ]))
    # A node literally labelled `Config.load` is the one named.
    assert _resolve_path_endpoint(G, "Config.load")[0] == "literal"
    # No type called `release` owns members, so the query still scores.
    nid, scored, err = _resolve_path_endpoint(G, "release.notes")
    assert (nid, err) == ("helper", None) and scored
