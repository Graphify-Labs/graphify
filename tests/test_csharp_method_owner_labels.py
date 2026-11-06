"""C# method nodes display their owning type (#4883).

Every method used to be labeled `.Build()`, so `IReport.Build()`,
`PdfReport.Build()` and `CsvReport.Build()` printed identically and only the
line told them apart. The graph build now gives each C# method an
`Owner.Name()` display label. Ids and edges are unchanged, and extraction
still emits the bare `.Name()` form that call resolution matches on; a
persisted graph handed back as incremental resolution context is normalized
back to it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphify.extract import extract
from graphify.extractors.csharp import (
    bare_csharp_method_label,
    csharp_method_label_reassignments,
)

_ISSUE_REPRO = (
    "public interface IReport { string Build(); }\n"
    "public class PdfReport : IReport { public string Build() { return \"pdf\"; } }\n"
    "public class CsvReport : IReport { public string Build() { return \"csv\"; } }\n"
    "public class Exporter {\n"
    "  private readonly IReport _report;\n"
    "  public Exporter(IReport report) { _report = report; }\n"
    "  public string Run() { return _report.Build(); }\n"
    "}\n"
)

_SPLIT = {
    "Report.cs": (
        "public interface IReport { string Build(); }\n"
        "public class PdfReport : IReport { public string Build() { return \"pdf\"; } }\n"
        "public class CsvReport : IReport { public string Build() { return \"csv\"; } }\n"
    ),
    "Exporter.cs": (
        "public class Exporter {\n"
        "  private readonly IReport _report;\n"
        "  public Exporter(IReport report) { _report = report; }\n"
        "  public string Run() { return _report.Build(); }\n"
        "}\n"
    ),
}


def _write(root: Path, files: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (root / name).write_text(body, encoding="utf-8")


def _graph(root: Path) -> dict:
    return json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))


def _labels(graph: dict) -> dict[str, str]:
    return {n["id"]: n["label"] for n in graph["nodes"]}


def _edges(graph: dict, relations: tuple[str, ...]) -> set[tuple[str, str, str]]:
    return {
        (e["source"], e["relation"], e["target"])
        for e in graph.get("links", graph.get("edges", []))
        if e["relation"] in relations
    }


@pytest.mark.parametrize("no_cluster", [False, True])
def test_issue_repro_methods_display_their_owning_type(tmp_path, no_cluster):
    from graphify.watch import _rebuild_code

    _write(tmp_path, {"Report.cs": _ISSUE_REPRO})
    assert _rebuild_code(tmp_path, no_cluster=no_cluster, acquire_lock=False, force=True)
    labels = _labels(_graph(tmp_path))

    assert labels["report_ireport_build"] == "IReport.Build()"
    assert labels["report_pdfreport_build"] == "PdfReport.Build()"
    assert labels["report_csvreport_build"] == "CsvReport.Build()"
    assert labels["report_exporter_run"] == "Exporter.Run()"
    assert labels["report_ireport"] == "IReport"
    assert labels["report"] == "Report.cs"


def test_ids_and_edges_match_the_raw_extraction(tmp_path):
    from graphify.watch import _rebuild_code

    _write(tmp_path, {"Report.cs": _ISSUE_REPRO})
    raw = extract([tmp_path / "Report.cs"], root=tmp_path)
    assert _rebuild_code(tmp_path, acquire_lock=False, force=True)
    graph = _graph(tmp_path)

    assert {n["id"] for n in graph["nodes"]} == {n["id"] for n in raw["nodes"]}
    structural = ("method", "calls", "dispatches_to", "implements", "contains")
    assert _edges(graph, structural) == {
        (e["source"], e["relation"], e["target"])
        for e in raw["edges"] if e["relation"] in structural
    }
    assert ("report_exporter_run", "calls", "report_ireport_build") in _edges(graph, ("calls",))


def test_extraction_keeps_the_bare_resolver_label(tmp_path):
    _write(tmp_path, {"Report.cs": _ISSUE_REPRO})
    raw = extract([tmp_path / "Report.cs"], root=tmp_path)
    methods = sorted(n["label"] for n in raw["nodes"] if n["label"].endswith("()"))
    assert methods == [".Build()", ".Build()", ".Build()", ".Run()"]


def test_incremental_rebuild_binds_into_an_unchanged_file(tmp_path):
    """Only the caller is re-extracted; the callee's persisted label is already
    `IReport.Build()`. The call and the dispatch edges must match a full build."""
    from graphify.watch import _rebuild_code

    inc, full = tmp_path / "inc", tmp_path / "full"
    for root in (inc, full):
        _write(root, _SPLIT)
    assert _rebuild_code(inc, no_cluster=True, acquire_lock=False, force=True)
    assert _labels(_graph(inc))["report_ireport_build"] == "IReport.Build()"
    for root in (inc, full):
        p = root / "Exporter.cs"
        p.write_text(p.read_text(encoding="utf-8") + "// touched\n", encoding="utf-8")
    assert _rebuild_code(
        inc, changed_paths=[inc / "Exporter.cs"], no_cluster=True, acquire_lock=False,
    )
    assert _rebuild_code(full, no_cluster=True, acquire_lock=False, force=True)

    relations = ("calls", "dispatches_to")
    assert _edges(_graph(inc), relations) == _edges(_graph(full), relations)
    assert ("exporter_exporter_run", "calls", "report_ireport_build") in _edges(_graph(full), relations)
    inc_labels, full_labels = _labels(_graph(inc)), _labels(_graph(full))
    assert {nid: inc_labels.get(nid) for nid in full_labels} == full_labels


def test_resolution_context_labels_are_normalized_without_mutating_the_caller(tmp_path):
    _write(tmp_path, _SPLIT)
    context = [
        {"id": "report_ireport", "label": "IReport", "source_file": "Report.cs",
         "file_type": "code", "type": None},
        {"id": "report_ireport_build", "label": "IReport.Build()", "source_file": "Report.cs",
         "file_type": "code", "type": None, "_callable": True,
         "metadata": {"arity": 0, "signature": ""}},
    ]
    context_edges = [
        {"source": "report", "target": "report_ireport", "relation": "contains",
         "source_file": "Report.cs"},
        {"source": "report_ireport", "target": "report_ireport_build", "relation": "method",
         "source_file": "Report.cs"},
    ]
    r = extract(
        [tmp_path / "Exporter.cs"], root=tmp_path,
        resolution_context_nodes=context, resolution_context_edges=context_edges,
    )
    assert ("exporter_exporter_run", "report_ireport_build") in {
        (e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"
    }
    assert context[1]["label"] == "IReport.Build()"


def test_rebuilding_from_qualified_labels_does_not_stack_the_owner():
    from graphify.build import build_from_json

    extraction = {
        "nodes": [
            {"id": "r_pdfreport", "label": "PdfReport", "file_type": "code",
             "source_file": "Report.cs", "source_location": "L2", "_origin": "ast"},
            {"id": "r_pdfreport_build", "label": "PdfReport.Build()", "file_type": "code",
             "source_file": "Report.cs", "source_location": "L2", "_origin": "ast"},
        ],
        "edges": [
            {"source": "r_pdfreport", "target": "r_pdfreport_build", "relation": "method",
             "confidence": "EXTRACTED", "source_file": "Report.cs"},
        ],
    }
    G = build_from_json(extraction)
    assert G.nodes["r_pdfreport_build"]["label"] == "PdfReport.Build()"
    G2 = build_from_json({
        "nodes": [{"id": n, **d} for n, d in G.nodes(data=True)],
        "edges": extraction["edges"],
    })
    assert G2.nodes["r_pdfreport_build"]["label"] == "PdfReport.Build()"


def test_qualified_methods_stay_out_of_god_nodes(tmp_path):
    from graphify.analyze import _is_file_node
    from graphify.build import build_from_json

    _write(tmp_path, {"Report.cs": _ISSUE_REPRO})
    G = build_from_json(extract([tmp_path / "Report.cs"], root=tmp_path))
    assert G.nodes["report_pdfreport_build"]["label"] == "PdfReport.Build()"
    assert _is_file_node(G, "report_pdfreport_build")
    assert not _is_file_node(G, "report_pdfreport")


def test_semantic_method_ghost_still_collapses_onto_a_qualified_method():
    """#3705 parity: an LLM ghost `Build()` in the same file remaps onto the one
    AST method even when that method's persisted label is `PdfReport.Build()`."""
    from graphify.build import build_from_json

    extraction = {
        "nodes": [
            {"id": "report_pdfreport_build", "label": "PdfReport.Build()", "file_type": "code",
             "source_file": "Report.cs", "source_location": "L2", "_origin": "ast"},
            {"id": "report_build", "label": "Build()", "file_type": "code",
             "source_file": "Report.cs"},
            {"id": "doc", "label": "Doc", "file_type": "document", "source_file": "d.md"},
        ],
        "edges": [
            {"source": "doc", "target": "report_build", "relation": "references",
             "confidence": "INFERRED", "confidence_score": 0.85, "source_file": "d.md"},
        ],
    }
    G = build_from_json(extraction)
    assert "report_build" not in G.nodes
    assert G.has_edge("doc", "report_pdfreport_build")


def test_class_segment_less_method_alias_still_resolves_a_qualified_method():
    """The raw --no-cluster writer finalizes endpoints after relabeling, so the
    `<file stem>_<method>` alias must still be read off `PdfReport.Build()`."""
    from graphify.build import finalize_raw_graph_endpoints

    data = {
        "nodes": [
            {"id": "report_pdfreport_build", "label": "PdfReport.Build()", "file_type": "code",
             "source_file": "Report.cs", "source_location": "L2", "_origin": "ast"},
            {"id": "doc", "label": "Doc", "file_type": "document", "source_file": "d.md"},
        ],
        "edges": [
            {"source": "doc", "target": "report_build", "relation": "references"},
        ],
    }
    finalize_raw_graph_endpoints(data)
    assert [(e["source"], e["target"]) for e in data["edges"]] == [
        ("doc", "report_pdfreport_build"),
    ]


def test_other_languages_keep_bare_method_labels(tmp_path):
    from graphify.build import build_from_json

    _write(tmp_path, {
        "Report.java": "class PdfReport { String build() { return \"pdf\"; } }\n",
        "Report.swift": "class PdfReport { func build() -> String { return \"pdf\" } }\n",
    })
    G = build_from_json(extract(
        [tmp_path / "Report.java", tmp_path / "Report.swift"], root=tmp_path,
    ))
    method_labels = {
        d["label"] for _, d in G.nodes(data=True) if str(d.get("label", "")).endswith("()")
    }
    assert method_labels == {".build()"}


def test_reassignment_fails_closed_on_missing_or_conflicting_owners():
    nodes = [
        ("a", {"label": "A", "source_file": "x.cs"}),
        ("b", {"label": "B", "source_file": "x.cs"}),
        ("ns", {"label": "Acme.Reports", "source_file": "x.cs"}),
        ("m_two_owners", {"label": ".Two()", "source_file": "x.cs"}),
        ("m_no_owner", {"label": ".None()", "source_file": "x.cs"}),
        ("m_dotted_owner", {"label": ".Dotted()", "source_file": "x.cs"}),
        ("m_ok", {"label": ".Ok()", "source_file": "x.cs"}),
        ("m_java", {"label": ".Ok()", "source_file": "x.java"}),
    ]
    edges = [
        ("a", "m_two_owners"), ("b", "m_two_owners"),
        ("ns", "m_dotted_owner"),
        ("a", "m_ok"),
        ("a", "m_java"),
    ]
    assert csharp_method_label_reassignments(nodes, edges) == {"m_ok": "A.Ok()"}


@pytest.mark.parametrize(("label", "source_file", "expected"), [
    (".Build()", "Report.cs", ".Build()"),
    ("PdfReport.Build()", "Report.cs", ".Build()"),
    ("PdfReport.Build()", "Report.java", None),
    ("PdfReport", "Report.cs", None),
    ("Build()", "Report.cs", None),
    ("Acme.PdfReport.Build()", "Report.cs", None),
    ("Report.cs", "Report.cs", None),
])
def test_bare_label_recognizes_only_method_shapes(label, source_file, expected):
    assert bare_csharp_method_label(label, source_file) == expected
