"""Regression tests for linking a Delphi form to the unit that implements it.

A Delphi form is two files the IDE keeps in lockstep: the design-time form
(`Sample.dfm`) and the unit implementing it (`Sample.pas`). The form names its
class and binds events by method name (`OnClick = btnOkClick`); the unit
declares that class and implements those methods. Neither file references the
other by path -- the pairing is the compiler's, via `{$R *.dfm}` and the shared
base name.

Extracted per file, the form's class node and its handler nodes are stubs local
to the form file, so no path leads from a control to the code behind it.
``graphify.dfm_resolution`` pairs the two files and links them; see its module
docstring for the rationale and the limits.

Static fixtures rather than tmp_path, for the reason given in
tests/test_pascal_resolution.py.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract

FIXTURES = Path(__file__).parent / "fixtures" / "delphi_form"
UNIT = FIXTURES / "Sample.pas"
FORM = FIXTURES / "Sample.dfm"


def _labels(nodes: list[dict]) -> dict[str, str]:
    return {n["id"]: str(n.get("label", "")) for n in nodes}


def _node(graph: dict, label: str, suffix: str) -> dict | None:
    for n in graph["nodes"]:
        if str(n.get("label")) == label and str(n.get("source_file", "")).endswith(suffix):
            return n
    return None


def _edges_from(graph: dict, node_id: str, context: str) -> list[dict]:
    return [
        e for e in graph["edges"]
        if e.get("source") == node_id and e.get("context") == context
    ]


def test_form_only_extraction_has_no_path_to_the_code(tmp_path):
    """Sanity check for the gap: with the unit absent from the corpus the form
    keeps exactly the graph it has today -- stubs, and no invented link."""
    graph = extract([FORM], cache_root=tmp_path, parallel=False)
    assert not [e for e in graph["edges"] if e.get("context") in ("event impl", "form class")]


def test_handler_links_to_its_implementation(tmp_path):
    graph = extract([UNIT, FORM], cache_root=tmp_path, parallel=False)
    stub = _node(graph, "btnOkClick()", "Sample.dfm")
    assert stub is not None
    linked = _edges_from(graph, stub["id"], "event impl")
    assert len(linked) == 1
    labels = _labels(graph["nodes"])
    target = next(n for n in graph["nodes"] if n["id"] == linked[0]["target"])
    assert labels[target["id"]] == "btnOkClick()"
    assert str(target["source_file"]).endswith("Sample.pas")


def test_form_class_links_to_the_unit_class(tmp_path):
    graph = extract([UNIT, FORM], cache_root=tmp_path, parallel=False)
    form_class = _node(graph, "TSampleF", "Sample.dfm")
    assert form_class is not None
    linked = _edges_from(graph, form_class["id"], "form class")
    assert len(linked) == 1
    target = next(n for n in graph["nodes"] if n["id"] == linked[0]["target"])
    assert str(target["source_file"]).endswith("Sample.pas")


def test_handler_on_a_nested_component_also_links(tmp_path):
    """`OnShow` sits on the form, `OnClick` on a button inside it: every
    handler is a method of the form class regardless of nesting."""
    graph = extract([UNIT, FORM], cache_root=tmp_path, parallel=False)
    stub = _node(graph, "FormShow()", "Sample.dfm")
    assert stub is not None
    assert len(_edges_from(graph, stub["id"], "event impl")) == 1


def test_resolution_is_additive(tmp_path):
    """The pass must not disturb what the extractors produced: the form's own
    `event` edges from component to handler stub stay exactly as they were."""
    graph = extract([UNIT, FORM], cache_root=tmp_path, parallel=False)
    labels = _labels(graph["nodes"])
    event_edges = [e for e in graph["edges"] if e.get("context") == "event"]
    assert {labels[e["target"]] for e in event_edges} == {"FormShow()", "btnOkClick()"}
