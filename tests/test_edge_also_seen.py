"""A same-relation edge collision must not erase the losing edge's provenance (#4881).

`build_from_json` keeps one edge per pair and relation, and since #3711 the
higher-confidence edge wins. The loser used to vanish: an AMBIGUOUS semantic
duplicate of an INFERRED dispatch edge left no trace in graph.json. The winner
now carries the loser's confidence / score / file / line in `also_seen`, and
`path` unions those tags into the hop label the way it already does for
parallel edges.
"""
from __future__ import annotations

import json

import pytest
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod
from graphify.build import build_from_json, edge_data
from graphify.serve import _shortest_path_text

REPORT_CS = """\
public interface IReport { string Build(); }
public class PdfReport : IReport { public string Build() { return "pdf"; } }
public class CsvReport : IReport { public string Build() { return "csv"; } }
public class Exporter {
  private readonly IReport _report;
  public Exporter(IReport report) { _report = report; }
  public string Run() { return _report.Build(); }
}
"""


def _node(nid, label):
    return {"id": nid, "label": label, "file_type": "code", "source_file": "Report.cs"}


def _report_extraction(extra_edges=()):
    """The AST extraction of REPORT_CS (call + dispatch edges), plus extras."""
    return {
        "nodes": [
            _node("report_exporter_run", ".Run()"),
            _node("report_ireport_build", ".Build()"),
            _node("report_pdfreport_build", ".Build()"),
            _node("report_csvreport_build", ".Build()"),
        ],
        "edges": [
            {"source": "report_exporter_run", "target": "report_ireport_build",
             "relation": "calls", "confidence": "INFERRED", "confidence_score": 0.85,
             "source_file": "Report.cs", "source_location": "L7"},
            {"source": "report_ireport_build", "target": "report_pdfreport_build",
             "relation": "dispatches_to", "confidence": "INFERRED", "confidence_score": 0.75,
             "source_file": "Report.cs", "source_location": "L2"},
            {"source": "report_ireport_build", "target": "report_csvreport_build",
             "relation": "dispatches_to", "confidence": "INFERRED", "confidence_score": 0.75,
             "source_file": "Report.cs", "source_location": "L3"},
            *extra_edges,
        ],
        "hyperedges": [],
    }


WEAK_DISPATCH = {
    "source": "report_ireport_build", "target": "report_pdfreport_build",
    "relation": "dispatches_to", "confidence": "AMBIGUOUS", "confidence_score": 0.4,
    "source_file": "notes.md", "source_location": "L12",
}
WEAK_EVIDENCE = {"confidence": "AMBIGUOUS", "confidence_score": 0.4,
                 "source_file": "notes.md", "source_location": "L12"}


def _dispatch(G):
    return edge_data(G, "report_ireport_build", "report_pdfreport_build")


@pytest.mark.parametrize("weak_first", [False, True])
def test_weaker_duplicate_is_recorded_on_the_winner(weak_first):
    ext = _report_extraction([dict(WEAK_DISPATCH)])
    if weak_first:
        ext["edges"].insert(0, ext["edges"].pop())
    d = _dispatch(build_from_json(ext))
    assert d["confidence"] == "INFERRED"
    assert d["confidence_score"] == 0.75
    assert d["source_location"] == "L2"
    assert d["also_seen"] == [WEAK_EVIDENCE]


def test_displaced_winner_is_recorded_and_its_score_does_not_leak():
    """A stronger edge with no score replaces a scored INFERRED one."""
    strong = {"source": "report_ireport_build", "target": "report_pdfreport_build",
              "relation": "dispatches_to", "confidence": "EXTRACTED",
              "source_file": "Report.cs", "source_location": "L9"}
    d = _dispatch(build_from_json(_report_extraction([strong])))
    assert d["confidence"] == "EXTRACTED"
    assert d["source_location"] == "L9"
    assert "confidence_score" not in d
    assert d["also_seen"] == [{"confidence": "INFERRED", "confidence_score": 0.75,
                               "source_file": "Report.cs", "source_location": "L2"}]


def test_equal_confidence_second_site_is_recorded():
    other_site = {"source": "report_exporter_run", "target": "report_ireport_build",
                  "relation": "calls", "confidence": "INFERRED", "confidence_score": 0.85,
                  "source_file": "Report.cs", "source_location": "L9"}
    d = edge_data(build_from_json(_report_extraction([other_site])),
                  "report_exporter_run", "report_ireport_build")
    sites = {d["source_location"], *(e["source_location"] for e in d["also_seen"])}
    assert sites == {"L7", "L9"}


def test_identical_duplicate_adds_nothing():
    same = dict(_report_extraction()["edges"][1])
    d = _dispatch(build_from_json(_report_extraction([same])))
    assert "also_seen" not in d


def test_rebuild_from_written_graph_is_idempotent():
    """An update re-feeds graph.json links through the build with fresh edges."""
    G = build_from_json(_report_extraction([dict(WEAK_DISPATCH)]))
    data = json_graph.node_link_data(G, edges="links")
    for link in data["links"]:
        link.pop("_src", None)
        link.pop("_tgt", None)
    again = _report_extraction([dict(WEAK_DISPATCH)])
    again["edges"] = data["links"] + again["edges"]
    assert _dispatch(build_from_json(again))["also_seen"] == [WEAK_EVIDENCE]


def test_malformed_also_seen_on_disk_is_sanitized():
    edge = dict(_report_extraction()["edges"][1])
    edge["also_seen"] = ["junk", None, {"confidence": "AMBIGUOUS", "confidence_score": "nan",
                                        "source_location": ["L1"]}]
    ext = _report_extraction()
    ext["edges"][1] = edge
    assert _dispatch(build_from_json(ext))["also_seen"] == [{"confidence": "AMBIGUOUS"}]


def _path_graph(tmp_path):
    G = build_from_json(_report_extraction([dict(WEAK_DISPATCH)]))
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(json_graph.node_link_data(G, edges="links")))
    return p, G


def test_cli_path_surfaces_weakest_tag(monkeypatch, tmp_path, capsys):
    p, _ = _path_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", [
        "graphify", "path", "report_exporter_run", "report_pdfreport_build", "--graph", str(p)])
    mainmod.main()
    out = capsys.readouterr().out
    assert "--dispatches_to [AMBIGUOUS 0.40/INFERRED 0.75]-->" in out
    assert "--calls [INFERRED 0.85]-->" in out


def test_mcp_path_surfaces_weakest_tag(tmp_path):
    _, G = _path_graph(tmp_path)
    out = _shortest_path_text(G, {"source": "report_exporter_run",
                                  "target": "report_pdfreport_build"})
    assert "--dispatches_to [AMBIGUOUS 0.40/INFERRED 0.75]-->" in out


def test_report_cs_extraction_keeps_semantic_duplicate(tmp_path):
    """End to end on the issue's repro: real C# AST edges + a weaker semantic duplicate."""
    pytest.importorskip("tree_sitter_c_sharp")
    from graphify.extract import extract

    src = tmp_path / "Report.cs"
    src.write_text(REPORT_CS)
    ext = extract([src], cache_root=tmp_path)
    ext["edges"].append(dict(WEAK_DISPATCH))
    d = _dispatch(build_from_json(ext, root=tmp_path))
    assert d["confidence"] == "INFERRED"
    assert [e["confidence"] for e in d["also_seen"]] == ["AMBIGUOUS"]


def _module(nid, source_file):
    return {"id": nid, "label": source_file, "file_type": "code", "source_file": source_file}


def test_different_relation_replacing_an_edge_does_not_inherit_its_also_seen():
    """`export * from './x'` and `export { a as b } from './x'` emit an imports_from
    edge per line and one file-level re_exports edge for the same pair. The
    re_exports edge replaces the folded imports_from edge; the stored dict used to
    keep the imports_from sites as also_seen, one of them a repeat of the winner's
    own line, which the next build reading graph.json drops (cold != incremental)."""
    def site(relation, line):
        return {"source": "lib_index", "target": "lib_x", "relation": relation,
                "confidence": "EXTRACTED", "source_file": "lib/index.ts", "source_location": line}

    ext = {
        "nodes": [_module("lib_index", "lib/index.ts"), _module("lib_x", "lib/x.ts")],
        "edges": [site("imports_from", "L1"), site("imports_from", "L2"), site("re_exports", "L1")],
        "hyperedges": [],
    }
    d = edge_data(build_from_json(ext), "lib_index", "lib_x")
    assert d["relation"] == "re_exports"
    assert d["source_location"] == "L1"
    assert "also_seen" not in d


def test_ts_barrel_reexport_edge_is_a_fixed_point_of_the_build(tmp_path):
    """End to end: the barrel's re_exports edge carries no imports_from sites, and a
    written graph re-fed through the build gives the same edge."""
    pytest.importorskip("tree_sitter_typescript")
    from graphify.extract import extract

    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "x.ts").write_text("export function alpha() { return 1 }\n")
    (tmp_path / "lib" / "index.ts").write_text(
        "export * from './x';\nexport { alpha as first } from './x';\n")
    ext = extract([tmp_path / "lib" / "x.ts", tmp_path / "lib" / "index.ts"], cache_root=tmp_path)
    G = build_from_json(ext, root=tmp_path)
    pairs = [(u, v) for u, v, d in G.edges(data=True)
             if d.get("relation") == "re_exports" and d.get("context") == "export"]
    assert len(pairs) == 1, f"expected one file-level re_exports edge, got {pairs}"
    pair = pairs[0]
    def evidence(graph):
        # _src/_tgt are stripped below, so the rebuild re-derives them
        return {k: v for k, v in edge_data(graph, *pair).items() if k not in ("_src", "_tgt")}

    first = evidence(G)
    assert "also_seen" not in first
    data = json_graph.node_link_data(G, edges="links")
    for link in data["links"]:
        link.pop("_src", None)
        link.pop("_tgt", None)
    again = build_from_json({"nodes": data["nodes"], "edges": data["links"], "hyperedges": []}, root=tmp_path)
    assert evidence(again) == first


def test_different_relation_replacing_an_edge_does_not_inherit_its_score_or_location():
    """The winner keeps only its own evidence: a score or line it lacks is not
    taken from the replaced edge of another relation."""
    ext = {
        "nodes": [_module("a", "a.py"), _module("b", "b.py")],
        "edges": [
            {"source": "a", "target": "b", "relation": "imports_from", "confidence": "EXTRACTED",
             "confidence_score": 0.4, "source_file": "a.py", "source_location": "L7"},
            {"source": "a", "target": "b", "relation": "re_exports", "confidence": "EXTRACTED",
             "source_file": "a.py"},
        ],
        "hyperedges": [],
    }
    d = edge_data(build_from_json(ext), "a", "b")
    assert d["relation"] == "re_exports"
    assert "confidence_score" not in d
    assert "source_location" not in d
