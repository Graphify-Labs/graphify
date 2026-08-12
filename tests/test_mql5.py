"""Tests for the MQL5 extractor (graphify/extractors/mql5.py + extract.extract_mql5)."""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract_mql5
from graphify.extractors.mql5 import mask_mql5_source

FIXTURES = Path(__file__).parent / "fixtures"


def _r():
    return extract_mql5(FIXTURES / "sample.mq5")


def _labels(r) -> set[str]:
    return {n["label"] for n in r["nodes"]}


def _pairs(r, relation) -> set[tuple[str, str]]:
    lab = {n["id"]: n["label"] for n in r["nodes"]}
    return {(lab.get(e["source"], e["source"]), lab.get(e["target"], e["target"]))
            for e in r["edges"] if e["relation"] == relation}


# --- masking ------------------------------------------------------------------

def test_mask_preserves_byte_offsets():
    """Line numbers come from tree-sitter byte offsets, so masking must not
    shift a single byte."""
    src = (FIXTURES / "sample.mq5").read_bytes()
    masked = mask_mql5_source(src)
    assert len(masked) == len(src)
    assert masked.count(b"\n") == src.count(b"\n")


def test_mask_removes_mql5_only_syntax():
    src = b"input group \"G\"\ninput double Lots = 0.1;\ncolor c = C'5,5,40';\n"
    masked = mask_mql5_source(src)
    assert b"input group" not in masked
    assert b"input double" not in masked
    assert b"double Lots = 0.1;" in masked
    assert b"C'5,5,40'" not in masked


def test_masked_source_parses_without_errors():
    import tree_sitter_cpp as tscpp
    from tree_sitter import Language, Parser

    parser = Parser(Language(tscpp.language()))
    tree = parser.parse(mask_mql5_source((FIXTURES / "sample.mq5").read_bytes()))

    errors = []

    def walk(n):
        if n.type == "ERROR" or n.is_missing:
            errors.append(n.start_point[0] + 1)
        for c in n.children:
            walk(c)

    walk(tree.root_node)
    assert errors == [], f"MQL5 fixture should parse clean after masking, errors at {errors}"


# --- extraction ---------------------------------------------------------------

def test_functions_and_types_come_from_the_cpp_pipeline():
    labels = _labels(_r())
    assert {"OnInit()", "OnTick()", "LotSize()", "CanOpen()"} <= labels
    assert "SZone" in labels


def test_inputs_are_recovered_after_masking():
    r = _r()
    labels = _labels(r)
    assert {"magic_number", "risk_mode", "risk_percent", "max_positions"} <= labels
    inputs = {n["label"]: n for n in r["nodes"] if n.get("type") == "input"}
    assert inputs["magic_number"]["mql5_input_type"] == "long"
    assert inputs["risk_percent"]["mql5_input_type"] == "double"


def test_input_reads_are_attributed_to_the_enclosing_function():
    refs = _pairs(_r(), "references")
    assert ("OnInit()", "magic_number") in refs
    assert ("LotSize()", "risk_percent") in refs
    assert ("LotSize()", "risk_mode") in refs


def test_single_line_body_is_attributed():
    """`bool CanOpen() { return(...); }` opens and closes on one line."""
    assert ("CanOpen()", "max_positions") in _pairs(_r(), "references")


def test_input_group_heading_is_not_a_node():
    labels = _labels(_r())
    assert "group" not in labels
    assert "GENERAL" not in labels


def test_property_header_lands_on_the_file_node():
    file_node = _r()["nodes"][0]
    assert file_node["mql5_version"] == "1.07"
    assert file_node["mql5_copyright"] == "Sample Author"


def test_includes_are_extracted():
    imports = {t for _, t in _pairs(_r(), "imports")}
    assert any("trade" in t.lower() for t in imports)


def test_no_dangling_intra_file_edges():
    """Cross-file `imports` targets resolve at build time; everything else must
    already point at a node this extractor emitted."""
    r = _r()
    ids = {n["id"] for n in r["nodes"]}
    dangling = [e for e in r["edges"] if e["relation"] != "imports"
                and (e["source"] not in ids or e["target"] not in ids)]
    assert dangling == []


def test_mqh_header_extracts_without_inputs(tmp_path):
    p = tmp_path / "helper.mqh"
    p.write_text(
        "#property strict\n"
        "class CHelper\n"
        "  {\n"
        "public:\n"
        "   double Value(void) { return(1.0); }\n"
        "  };\n",
        encoding="utf-8",
    )
    r = extract_mql5(p)
    assert "CHelper" in _labels(r)
    assert not [n for n in r["nodes"] if n.get("type") == "input"]


def test_string_braces_do_not_desync_attribution(tmp_path):
    p = tmp_path / "s.mq5"
    p.write_text(
        'input int lookback = 5;\n'
        'void Report()\n'
        '  {\n'
        '   Print("payload { unbalanced");\n'
        '   int x = lookback;\n'
        '  }\n',
        encoding="utf-8",
    )
    assert ("Report()", "lookback") in _pairs(extract_mql5(p), "references")
