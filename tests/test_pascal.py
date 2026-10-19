"""Tests for the Pascal/Delphi extractor."""
from __future__ import annotations
import importlib.util as _ilu
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

_needs_pascal = pytest.mark.skipif(
    _ilu.find_spec("tree_sitter_pascal") is None,
    reason="tree-sitter-pascal not installed (enum types need the AST path)",
)


def _labels(r):
    return [n["label"] for n in r["nodes"]]


def _relations(r):
    return {e["relation"] for e in r["edges"]}


def _edges_with_relation(r, *relations):
    return [e for e in r["edges"] if e["relation"] in relations]


def test_pascal_no_error():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    assert "error" not in r


def test_pascal_finds_unit():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    assert any("SampleUnit" in l for l in _labels(r))


def test_pascal_finds_classes():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    labels = _labels(r)
    assert any("TBaseProcessor" in l for l in labels)
    assert any("TDataProcessor" in l for l in labels)


def test_pascal_finds_interface():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    assert any("IProcessor" in l for l in _labels(r))


def test_pascal_finds_methods():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    labels = _labels(r)
    assert any("Process" in l for l in labels)
    assert any("Initialize" in l for l in labels)
    assert any("GetCount" in l for l in labels)
    assert any("Reset" in l for l in labels)


def test_pascal_finds_imports():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    assert "imports" in _relations(r)


def test_pascal_import_edges_have_import_context():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    import_edges = _edges_with_relation(r, "imports")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_pascal_finds_inherits():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    assert "inherits" in _relations(r)


def test_pascal_inherits_from_base():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    inherits = [e for e in r["edges"] if e["relation"] == "inherits"]
    found = any(
        "TDataProcessor" in node_by_id.get(e["source"], "")
        for e in inherits
    )
    assert found, "TDataProcessor should have at least one inherits edge"


@_needs_pascal
def test_pascal_enum_type_and_values_are_extracted(tmp_path):
    """A Pascal enumerated type becomes a node with a `case_of` edge per value.

    `declType` matched only class/interface/helper kinds, so an enumerated type
    (`TColor = (clRed, clGreen, clBlue);`) and all of its values fell through and
    were dropped — the whole type vanished. An enum's values are its cases, so
    each becomes a node with a `case_of` edge to the type, matching every other
    language with enums (Java #1719 / C# / Swift / Scala).
    """
    from graphify.extract import extract_pascal
    p = tmp_path / "colors.pas"
    p.write_text(
        "unit Colors;\n"
        "interface\n"
        "type\n"
        "  TColor = (clRed, clGreen, clBlue);\n"
        "  TNum = Integer;\n"
        "implementation\n"
        "end.\n",
        encoding="utf-8",
    )
    r = extract_pascal(p)
    assert "error" not in r
    labels = {n["label"] for n in r["nodes"]}
    # Pre-fix the whole `TColor = (...)` declaration vanished.
    assert {"TColor", "clRed", "clGreen", "clBlue"} <= labels
    ids = {n["id"]: n["label"] for n in r["nodes"]}
    case_of = {
        (ids.get(e["source"]), ids.get(e["target"]))
        for e in r["edges"]
        if e["relation"] == "case_of"
    }
    assert ("TColor", "clRed") in case_of
    assert ("TColor", "clGreen") in case_of
    assert ("TColor", "clBlue") in case_of


@_needs_pascal
def test_pascal_valued_enum_literals_are_not_nodes(tmp_path):
    """The valued form (`clRed = 1`) yields the same graph as the plain form.

    An explicit ordinal nests under declEnumValue -> defaultValue, beside the
    value's identifier. Only the identifier names the case: the literal must not
    leak into the value's label or become a node of its own (#4071).
    """
    from graphify.extract import extract_pascal
    p = tmp_path / "colors.pas"
    p.write_text(
        "unit Colors;\n"
        "interface\n"
        "type\n"
        "  TColor = (clRed = 1, clGreen = 2);\n"
        "implementation\n"
        "end.\n",
        encoding="utf-8",
    )
    r = extract_pascal(p)
    assert "error" not in r
    labels = {n["label"] for n in r["nodes"]}
    assert {"TColor", "clRed", "clGreen"} <= labels
    assert not {"1", "2"} & labels
    ids = {n["id"]: n["label"] for n in r["nodes"]}
    cases = {
        ids.get(e["target"])
        for e in r["edges"]
        if e["relation"] == "case_of" and ids.get(e["source"]) == "TColor"
    }
    # Exactly the two bare names: not `clRed = 1`, and no edge to a literal.
    assert cases == {"clRed", "clGreen"}


def test_pascal_finds_calls():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    assert "calls" in _relations(r)


def test_pascal_call_edges_have_call_context():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    call_edges = _edges_with_relation(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)


def test_pascal_all_edges_extracted():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    structural = {"contains", "method", "inherits", "imports"}
    for e in r["edges"]:
        if e["relation"] in structural:
            assert e["confidence"] == "EXTRACTED", f"Expected EXTRACTED: {e}"


def test_pascal_no_dangling_edges():
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    node_ids = {n["id"] for n in r["nodes"]}
    # imports edges are cross-file by design; only check within-file edge targets
    within_file_relations = {"contains", "method", "inherits", "calls"}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e}"
        if e["relation"] in within_file_relations:
            assert e["target"] in node_ids, f"Dangling target: {e}"


def test_pascal_dispatch_registered():
    from graphify.extract import _DISPATCH
    assert ".pas" in _DISPATCH
    assert ".pp" in _DISPATCH
    assert ".dpr" in _DISPATCH
    assert ".dpk" in _DISPATCH
    assert ".lpr" in _DISPATCH
    assert ".inc" in _DISPATCH
    assert ".lfm" in _DISPATCH
    assert ".lpk" in _DISPATCH


def test_pascal_detect_extensions_registered():
    from graphify.detect import CODE_EXTENSIONS
    assert ".pas" in CODE_EXTENSIONS
    assert ".pp" in CODE_EXTENSIONS
    assert ".dpr" in CODE_EXTENSIONS
    assert ".lpr" in CODE_EXTENSIONS
    assert ".lfm" in CODE_EXTENSIONS
    assert ".lpk" in CODE_EXTENSIONS


# ── Lazarus Form (.lfm) ───────────────────────────────────────────────────────

def test_lfm_no_error():
    from graphify.extract import extract_lazarus_form
    r = extract_lazarus_form(FIXTURES / "sample.lfm")
    assert "error" not in r


def test_lfm_finds_root_form_class():
    from graphify.extract import extract_lazarus_form
    r = extract_lazarus_form(FIXTURES / "sample.lfm")
    assert any("TSampleForm" in l for l in _labels(r))


def test_lfm_finds_component_classes():
    from graphify.extract import extract_lazarus_form
    r = extract_lazarus_form(FIXTURES / "sample.lfm")
    labels = _labels(r)
    assert any("TPanel" in l for l in labels)
    assert any("TButton" in l for l in labels)
    assert any("TLabel" in l for l in labels)
    assert any("TTimer" in l for l in labels)


def test_lfm_finds_event_handlers():
    from graphify.extract import extract_lazarus_form
    r = extract_lazarus_form(FIXTURES / "sample.lfm")
    labels = _labels(r)
    assert any("ButtonOKClick" in l for l in labels)
    assert any("TimerRefreshTimer" in l for l in labels)


def test_lfm_event_edges_have_event_context():
    from graphify.extract import extract_lazarus_form
    r = extract_lazarus_form(FIXTURES / "sample.lfm")
    ref_edges = [e for e in r["edges"] if e["relation"] == "references"]
    assert ref_edges
    assert all(e.get("context") == "event" for e in ref_edges)


def test_lfm_contains_edges_form_hierarchy():
    from graphify.extract import extract_lazarus_form
    r = extract_lazarus_form(FIXTURES / "sample.lfm")
    assert "contains" in _relations(r)


def test_lfm_no_dangling_edges():
    from graphify.extract import extract_lazarus_form
    r = extract_lazarus_form(FIXTURES / "sample.lfm")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e}"


# ── Lazarus Package (.lpk) ───────────────────────────────────────────────────

def test_lpk_no_error():
    from graphify.extract import extract_lazarus_package
    r = extract_lazarus_package(FIXTURES / "sample.lpk")
    assert "error" not in r


def test_lpk_finds_package_name():
    from graphify.extract import extract_lazarus_package
    r = extract_lazarus_package(FIXTURES / "sample.lpk")
    assert any("SamplePackage" in l for l in _labels(r))


def test_lpk_finds_required_packages():
    from graphify.extract import extract_lazarus_package
    r = extract_lazarus_package(FIXTURES / "sample.lpk")
    labels = _labels(r)
    assert any("FCL" in l for l in labels)
    assert any("LCL" in l for l in labels)


def test_lpk_imports_edges_have_import_context():
    from graphify.extract import extract_lazarus_package
    r = extract_lazarus_package(FIXTURES / "sample.lpk")
    import_edges = _edges_with_relation(r, "imports")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_lpk_contains_listed_units():
    from graphify.extract import extract_lazarus_package
    r = extract_lazarus_package(FIXTURES / "sample.lpk")
    labels = _labels(r)
    assert any("sample" in l.lower() for l in labels)
    assert any("sampleutils" in l.lower() for l in labels)


def test_lpk_no_dangling_edges():
    from graphify.extract import extract_lazarus_package
    r = extract_lazarus_package(FIXTURES / "sample.lpk")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e}"


# ── Delphi Form (.dfm) ───────────────────────────────────────────────────────

def test_dfm_no_error():
    from graphify.extract import extract_delphi_form
    r = extract_delphi_form(FIXTURES / "sample.dfm")
    assert "error" not in r


def test_dfm_finds_root_form_class():
    from graphify.extract import extract_delphi_form
    r = extract_delphi_form(FIXTURES / "sample.dfm")
    assert any("TMainForm" in l for l in _labels(r))


def test_dfm_finds_component_classes():
    from graphify.extract import extract_delphi_form
    r = extract_delphi_form(FIXTURES / "sample.dfm")
    labels = _labels(r)
    assert any("TPanel" in l for l in labels)
    assert any("TButton" in l for l in labels)
    assert any("TMemo" in l for l in labels)
    assert any("TStatusBar" in l for l in labels)


def test_dfm_finds_event_handlers():
    from graphify.extract import extract_delphi_form
    r = extract_delphi_form(FIXTURES / "sample.dfm")
    labels = _labels(r)
    assert any("FormCreate" in l for l in labels)
    assert any("ButtonOKClick" in l for l in labels)


def test_dfm_event_edges_have_event_context():
    from graphify.extract import extract_delphi_form
    r = extract_delphi_form(FIXTURES / "sample.dfm")
    ref_edges = [e for e in r["edges"] if e["relation"] == "references"]
    assert ref_edges
    assert all(e.get("context") == "event" for e in ref_edges)


def test_dfm_contains_edges_form_hierarchy():
    from graphify.extract import extract_delphi_form
    r = extract_delphi_form(FIXTURES / "sample.dfm")
    assert "contains" in _relations(r)


def test_dfm_no_dangling_edges():
    from graphify.extract import extract_delphi_form
    r = extract_delphi_form(FIXTURES / "sample.dfm")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e}"


def test_dfm_binary_returns_empty_not_crash():
    from graphify.extract import extract_delphi_form
    import tempfile, pathlib
    # Write a fake binary DFM (FF 0A magic header)
    with tempfile.NamedTemporaryFile(suffix=".dfm", delete=False) as f:
        f.write(b"\xff\x0a\x00\x00some binary data")
        tmp = pathlib.Path(f.name)
    try:
        r = extract_delphi_form(tmp)
        assert r["nodes"] == []
        assert r["edges"] == []
        assert "error" in r
    finally:
        tmp.unlink()


def test_dfm_dispatch_registered():
    from graphify.extract import _DISPATCH
    assert ".dfm" in _DISPATCH


def test_dfm_detect_extension_registered():
    from graphify.detect import CODE_EXTENSIONS
    assert ".dfm" in CODE_EXTENSIONS


def _dup_edges(r):
    from collections import Counter
    triples = Counter((e["source"], e["target"], e["relation"]) for e in r["edges"])
    return {k: v for k, v in triples.items() if v > 1}


def test_pascal_no_duplicate_method_edges_tree_sitter():
    """A class method appears in both the interface declaration and the
    implementation; each used to emit a `method` edge to the same node, so the
    graph carried doubled method/contains/inherits edges (skewing degree and
    breaking the cross-file inherited-call resolver's god-node guard). Edges are
    now deduped on (source, target, relation)."""
    from graphify.extract import extract_pascal
    r = extract_pascal(FIXTURES / "sample.pas")
    assert _dup_edges(r) == {}, f"duplicate edges: {_dup_edges(r)}"


def test_pascal_no_duplicate_method_edges_regex():
    from graphify.extract import _extract_pascal_regex
    r = _extract_pascal_regex(FIXTURES / "sample.pas")
    assert _dup_edges(r) == {}, f"duplicate edges: {_dup_edges(r)}"
