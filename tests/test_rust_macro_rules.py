"""Rust `macro_rules!` definitions and their invocations.

A `macro_rules! name { ... }` is a named, invocable item, but its node type
(`macro_definition`) had no branch in the extractor, so the macro was dropped
entirely: it never became a node and a `name!(...)` invocation of it (a
`macro_invocation`, never a `call_expression`) had nothing to resolve to.
"""
from __future__ import annotations

from pathlib import Path

import pytest

tsr = pytest.importorskip("tree_sitter_rust")

from graphify.extractors.rust import extract_rust


def _extract(tmp_path: Path, body: str) -> dict:
    f = tmp_path / "lib.rs"
    f.write_text(body, encoding="utf-8")
    return extract_rust(f)


def test_macro_rules_definition_becomes_a_node(tmp_path):
    r = _extract(
        tmp_path,
        "macro_rules! my_vec {\n"
        "    ($($x:expr),*) => { vec![$($x),*] };\n"
        "}\n",
    )
    assert "error" not in r
    labels = {n["label"] for n in r["nodes"]}
    # Pre-fix the macro_definition was dropped: no node at all.
    assert "my_vec!" in labels, f"macro_rules! definition dropped: {sorted(labels)}"


def test_macro_invocation_resolves_to_local_macro(tmp_path):
    r = _extract(
        tmp_path,
        "macro_rules! my_vec {\n"
        "    ($($x:expr),*) => { vec![$($x),*] };\n"
        "}\n"
        "fn build() -> Vec<i32> {\n"
        "    my_vec!(1, 2, 3)\n"
        "}\n",
    )
    id_to_label = {n["id"]: n["label"] for n in r["nodes"]}
    calls = {
        (id_to_label.get(e["source"], e["source"]),
         id_to_label.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == "calls"
    }
    assert ("build()", "my_vec!") in calls


def test_macro_does_not_collide_with_same_named_function(tmp_path):
    """A macro and a function may share a name (`vec!` vs `vec`). The macro id is
    macro-qualified, so both coexist and the invocation binds to the macro only."""
    r = _extract(
        tmp_path,
        "macro_rules! thing {\n"
        "    () => { 0 };\n"
        "}\n"
        "fn thing() -> i32 { 1 }\n"
        "fn run() -> i32 {\n"
        "    thing!()\n"
        "}\n",
    )
    labels = sorted(n["label"] for n in r["nodes"])
    assert "thing!" in labels
    assert "thing()" in labels
    id_to_label = {n["id"]: n["label"] for n in r["nodes"]}
    calls = {
        (id_to_label.get(e["source"], e["source"]),
         id_to_label.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == "calls"
    }
    # The `thing!()` invocation binds to the macro, not the function.
    assert ("run()", "thing!") in calls
    assert ("run()", "thing()") not in calls


def test_scoped_macro_invocation_stays_unresolved(tmp_path):
    """A `log::info!(..)` invocation is cross-module/crate; it must not bind to any
    local node (fail-closed), matching how scoped calls are handled."""
    r = _extract(
        tmp_path,
        "fn run() {\n"
        "    log::info!(\"hi\");\n"
        "}\n",
    )
    assert not [e for e in r["edges"] if e["relation"] == "calls"]
