"""Pascal/Delphi calls through a global singleton resolve across files (#3101).

`var mm: TMainModule;` in one unit's interface, `mm.ServerReport(...)` from
another unit: the shared "main module" shape most Delphi codebases have. The
per-file pass discarded the receiver (`mm.ServerReport` -> `serverreport`)
before resolution started, and the cross-file resolver only walked the
CALLER's ancestor chain — so the edge was silently absent whenever caller and
callee lived in different files, and "who calls X" was empty for exactly the
most-used class in the project.

Static fixtures under tests/fixtures/pascal_singleton/ for the same reason
test_pascal_resolution.py uses them (the extractor's project-root walk).
"""
from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from graphify.extract import extract, extract_pascal
from graphify.extractors.pascal import _extract_pascal_regex

try:
    from graphify.extractors.pascal import _pascal_call_parts, _pascal_interface_globals
except ImportError:  # pre-fix tree
    _pascal_call_parts = _pascal_interface_globals = None

needs_helpers = pytest.mark.skipif(_pascal_call_parts is None, reason="pre-fix tree")

FIXTURES = Path(__file__).parent / "fixtures" / "pascal_singleton"
MAIN = FIXTURES / "MainModule.pas"
OTHER = FIXTURES / "OtherModule.pas"
FORM = FIXTURES / "Form1.pas"


def _labels(nodes):
    return {n["id"]: str(n.get("label", "")) for n in nodes}


def _calls(graph):
    labels = _labels(graph["nodes"])
    return {(labels.get(e["source"]), labels.get(e["target"]))
            for e in graph["edges"] if e.get("relation") == "calls"}


@pytest.fixture
def corpus(tmp_path):
    """Cache into tmp_path: a cache under the fixture dir would outlive a
    change to the extractor and serve stale per-file results."""
    with redirect_stdout(io.StringIO()):
        return extract([MAIN, OTHER, FORM], cache_root=tmp_path, root=FIXTURES, parallel=False)


# ---------------------------------------------------------------------------
# The per-file side: keep the receiver, export the interface globals
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("mm.ServerReport", ("serverreport", "mm")),
    ("ServerReport", ("serverreport", None)),
    ("Self.Local", ("local", None)),
    ("inherited Create", ("inherited create", None)),
    ("Unit1.mm.Run", ("run", "mm")),
    ("", ("", None)),
])
@needs_helpers
def test_call_parts_keep_the_receiver_but_not_self(text, expected):
    assert _pascal_call_parts(text) == expected


@needs_helpers
def test_interface_globals_are_collected_with_their_types():
    text = MAIN.read_text(encoding="utf-8")
    assert _pascal_interface_globals(text) == {"mm": "tmainmodule", "counter": "integer", "total": "integer"}


@needs_helpers
def test_implementation_and_procedure_local_vars_are_not_exported():
    text = (
        "unit U;\ninterface\nprocedure P(var Arg: Integer);\nimplementation\n"
        "var hidden: TThing;\nprocedure P(var Arg: Integer);\nvar local: TOther;\nbegin\nend;\nend.\n"
    )
    assert _pascal_interface_globals(text) == {}


@needs_helpers
def test_a_name_declared_twice_with_different_types_is_dropped():
    text = "unit U;\ninterface\nvar\n  x: TA;\nvar\n  x: TB;\n  y: TC;\nimplementation\nend.\n"
    assert _pascal_interface_globals(text) == {"y": "tc"}


@needs_helpers
def test_a_program_without_an_interface_exports_nothing():
    assert _pascal_interface_globals("program P;\nvar g: TThing;\nbegin\nend.\n") == {}


@pytest.mark.parametrize("extractor", [extract_pascal, _extract_pascal_regex])
def test_the_per_file_pass_reports_the_qualified_call_with_its_receiver(extractor):
    result = extractor(FORM)
    rcs = {rc["callee"]: rc for rc in result["raw_calls"]}
    assert rcs["serverreport"]["receiver"] == "mm"
    assert rcs["flush"]["receiver"] == "om"
    assert "receiver" not in rcs["orphan"]  # unqualified stays as it was
    assert result["pascal_globals"] == {}  # Form1 declares no globals


@pytest.mark.parametrize("extractor", [extract_pascal, _extract_pascal_regex])
def test_the_per_file_pass_exports_globals(extractor):
    assert extractor(MAIN)["pascal_globals"]["mm"] == "tmainmodule"


# ---------------------------------------------------------------------------
# The corpus side: the edge now exists, and only where it is unambiguous
# ---------------------------------------------------------------------------

def test_a_call_through_a_global_singleton_resolves_across_files(corpus):
    calls = _calls(corpus)
    assert ("ButtonClick()", "ServerReport()") in calls
    assert ("ButtonClick()", "Flush()") in calls


def test_the_receiver_picks_the_right_class_when_method_names_collide(corpus):
    """Both TMainModule and TOtherModule have ServerReport; `mm.` must land on
    TMainModule's, and nothing on TOtherModule's."""
    g = corpus
    labels = _labels(g["nodes"])
    owner = {}
    for e in g["edges"]:
        if e.get("relation") == "method":
            owner[e["target"]] = labels.get(e["source"])
    targets = {owner.get(e["target"]) for e in g["edges"]
               if e.get("relation") == "calls" and labels.get(e["source"]) == "ButtonClick()"
               and labels.get(e["target"]) == "ServerReport()"}
    assert targets == {"TMainModule"}


def test_the_edge_is_extracted_and_carries_the_call_site(corpus):
    g = corpus
    labels = _labels(g["nodes"])
    edge = next(e for e in g["edges"] if e.get("relation") == "calls"
                and labels.get(e["source"]) == "ButtonClick()" and labels.get(e["target"]) == "ServerReport()")
    assert edge["confidence"] == "EXTRACTED"
    assert edge["source_file"].endswith("Form1.pas")
    assert edge["source_location"].startswith("L")


def test_an_unqualified_unresolvable_call_still_produces_no_edge(corpus):
    calls = _calls(corpus)
    assert not any(t and t.lower().startswith("orphan") for _, t in calls)


def test_a_receiver_with_two_declared_types_yields_no_edge(tmp_path):
    from graphify.pascal_resolution import resolve_pascal_inherited_calls
    nodes = [
        {"id": "a_ta", "label": "TA"}, {"id": "a_ta_go", "label": "Go()"},
        {"id": "b_tb", "label": "TB"}, {"id": "b_tb_go", "label": "Go()"},
        {"id": "c_caller", "label": "Caller()"},
    ]
    edges = [
        {"source": "a_ta", "target": "a_ta_go", "relation": "method"},
        {"source": "b_tb", "target": "b_tb_go", "relation": "method"},
    ]
    per_file = [
        {"pascal_globals": {"x": "ta"}, "raw_calls": []},
        {"pascal_globals": {"x": "tb"}, "raw_calls": [
            {"source_file": "c.pas", "caller_nid": "c_caller", "callee": "go", "receiver": "x"}]},
    ]
    resolve_pascal_inherited_calls(per_file, nodes, edges)
    assert not any(e.get("relation") == "calls" for e in edges)


def test_a_qualified_call_does_not_fall_back_to_the_callers_ancestors():
    """`other.Prepare` is a call on `other`, not an inherited call — the
    ancestor-chain walk must not bind it to the caller's base class."""
    from graphify.pascal_resolution import resolve_pascal_inherited_calls
    nodes = [
        {"id": "base", "label": "TBase"}, {"id": "base_prepare", "label": "Prepare()"},
        {"id": "derived", "label": "TDerived"}, {"id": "derived_run", "label": "Run()"},
    ]
    edges = [
        {"source": "derived", "target": "base", "relation": "inherits"},
        {"source": "base", "target": "base_prepare", "relation": "method"},
        {"source": "derived", "target": "derived_run", "relation": "method"},
    ]
    per_file = [{"pascal_globals": {}, "raw_calls": [
        {"source_file": "d.pas", "caller_nid": "derived_run", "callee": "prepare", "receiver": "other"}]}]
    resolve_pascal_inherited_calls(per_file, nodes, edges)
    assert not any(e.get("relation") == "calls" for e in edges)
