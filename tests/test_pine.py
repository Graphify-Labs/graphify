"""Tests for the Pine Script extractor (graphify/extractors/pine.py)."""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract_pine


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def _labels(r) -> list[str]:
    return [n["label"] for n in r["nodes"]]


def _rel_pairs(r, relation: str) -> set[tuple[str, str]]:
    lab = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (lab.get(e["source"], e["source"]), lab.get(e["target"], e["target"]))
        for e in r["edges"]
        if e["relation"] == relation
    }


SAMPLE = """\
//@version=6
strategy("My Strat", overlay=true,
     pyramiding=2)

// Inputs
rr = input.float(1.0, "R:R", minval=0.1)
slBuf = input.float(10.0, "Buffer SL")
enableX = input.bool(true, "Enable X")

type Zone
    float top
    float bot

pips(p) => p * slBuf

calcQty(float slDist) =>
    risk = strategy.equity * rr / 100.0
    qty = risk / pips(slDist)
    qty

if barstate.isconfirmed
    strategy.entry("L", strategy.long, qty=calcQty(slBuf))

plot(close)
"""


def test_declarations(tmp_path):
    r = extract_pine(_write(tmp_path, "s.pine", SAMPLE))
    labels = _labels(r)
    assert 'strategy "My Strat"' in labels
    assert "pips()" in labels and "calcQty()" in labels
    assert "Zone" in labels
    for name in ("rr", "slBuf", "enableX"):
        assert name in labels


def test_version_recorded_on_file_node(tmp_path):
    r = extract_pine(_write(tmp_path, "s.pine", SAMPLE))
    assert r["nodes"][0]["pine_version"] == "6"


def test_calls_between_user_functions(tmp_path):
    r = extract_pine(_write(tmp_path, "s.pine", SAMPLE))
    assert ("calcQty()", "pips()") in _rel_pairs(r, "calls")


def test_top_level_calls_are_owned_by_the_script(tmp_path):
    r = extract_pine(_write(tmp_path, "s.pine", SAMPLE))
    assert ('strategy "My Strat"', "calcQty()") in _rel_pairs(r, "calls")


def test_function_references_input(tmp_path):
    r = extract_pine(_write(tmp_path, "s.pine", SAMPLE))
    refs = _rel_pairs(r, "references")
    assert ("pips()", "slBuf") in refs
    assert ("calcQty()", "rr") in refs


def test_notable_builtins_are_shared_nodes(tmp_path):
    """Built-in nodes are unscoped so two scripts share them."""
    a = extract_pine(_write(tmp_path, "a.pine", SAMPLE))
    b = extract_pine(_write(tmp_path, "b.pine", SAMPLE))
    ids = {n["label"]: n["id"] for n in a["nodes"]}
    ids_b = {n["label"]: n["id"] for n in b["nodes"]}
    assert ids["strategy.entry"] == ids_b["strategy.entry"]
    assert ("strategy.entry" in ids) and ("plot" in ids)


def test_user_functions_are_file_scoped(tmp_path):
    """Same function name in two scripts must not collapse into one node."""
    a = extract_pine(_write(tmp_path, "a.pine", SAMPLE))
    b = extract_pine(_write(tmp_path, "b.pine", SAMPLE))
    id_a = next(n["id"] for n in a["nodes"] if n["label"] == "calcQty()")
    id_b = next(n["id"] for n in b["nodes"] if n["label"] == "calcQty()")
    assert id_a != id_b


def test_comment_and_string_content_is_not_parsed(tmp_path):
    src = """\
//@version=5
indicator("T")
// ghost(x) => x
msg = "call notReal() // not a comment"
real(x) => x
"""
    r = extract_pine(_write(tmp_path, "s.pine", src))
    labels = _labels(r)
    assert "real()" in labels
    assert "ghost()" not in labels
    assert "notReal()" not in labels


def test_call_is_not_mistaken_for_definition(tmp_path):
    src = """\
//@version=5
indicator("T")
ma = ta.sma(close, 14)
helper(x) => x + 1
"""
    r = extract_pine(_write(tmp_path, "s.pine", src))
    assert "helper()" in _labels(r)
    assert "ma()" not in _labels(r)


def test_multiline_signature(tmp_path):
    src = """\
//@version=6
indicator("T")
wide(float a,
     float b) =>
    a + b
"""
    r = extract_pine(_write(tmp_path, "s.pine", src))
    assert "wide()" in _labels(r)


def test_imports_are_shared_library_nodes(tmp_path):
    src = """\
//@version=6
import TradingView/Strategy/5 as st
indicator("T")
"""
    r = extract_pine(_write(tmp_path, "s.pine", src))
    assert ("s.pine", "st") in _rel_pairs(r, "imports")


def test_empty_file_yields_only_the_file_node(tmp_path):
    r = extract_pine(_write(tmp_path, "s.pine", ""))
    assert len(r["nodes"]) == 1
    assert r["edges"] == []


def test_no_self_edges(tmp_path):
    r = extract_pine(_write(tmp_path, "s.pine", SAMPLE))
    assert all(e["source"] != e["target"] for e in r["edges"])
