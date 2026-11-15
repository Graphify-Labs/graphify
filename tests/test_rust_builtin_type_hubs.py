"""Rust prelude types must not become hubs, and constructions are not calls.

Two Rust-space extraction bugs:

1. ``_LANGUAGE_BUILTIN_GLOBALS`` lists ECMAScript / Python / Swift builtins but
   no Rust standard-library type. Every ``Option<T>`` / ``Vec<T>`` / ``String``
   annotation was therefore extracted as a domain type, and the language's own
   primitives resolved to a few canonical nodes carrying corpus-wide degree.
2. A tuple-struct construction (``ClientId(id)``) was emitted as ``calls``, so
   a newtype used as a key everywhere read as the top call hub.

These tests pin both: prelude types produce no node, a real function call still
produces ``calls``, and a construction produces ``references[constructor]``.
"""
from __future__ import annotations

from graphify.extract import extract


def test_rust_prelude_types_produce_no_nodes(tmp_path):
    (tmp_path / "a.rs").write_text(
        "pub fn parse(items: Vec<String>, name: Option<String>) -> Result<u32, String> {\n"
        "    let mut seen: std::collections::HashMap<String, u32> = std::collections::HashMap::new();\n"
        "    let _ = &mut seen;\n"
        "    Ok(name.map(|_| 1u32).unwrap_or(0))\n"
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "b.rs").write_text(
        "pub struct Widget {\n"
        "    pub name: String,\n"
        "    pub parts: Vec<u32>,\n"
        "}\n"
        "pub fn widget() -> Widget {\n"
        '    Widget { name: String::new(), parts: Vec::new() }\n'
        "}\n",
        encoding="utf-8",
    )
    r = extract(sorted(tmp_path.glob("*.rs")), cache_root=tmp_path / "graphify-out")

    labels = {n["label"] for n in r["nodes"]}
    for builtin in ("Option", "Vec", "String", "Result", "HashMap"):
        assert builtin not in labels, f"prelude type {builtin} must not become a node"
    assert "Widget" in labels, "a user-defined type must still become a node"


def test_rust_newtype_construction_is_reference_not_call(tmp_path):
    (tmp_path / "ids.rs").write_text(
        "pub struct ClientId(pub u32);\n", encoding="utf-8")
    (tmp_path / "use_ids.rs").write_text(
        "use crate::ids::ClientId;\n"
        "pub fn wrap(raw: u32) -> u32 {\n"
        "    let _id = ClientId(raw);\n"
        "    raw\n"
        "}\n",
        encoding="utf-8")
    r = extract(sorted(tmp_path.glob("*.rs")), cache_root=tmp_path / "graphify-out")

    cid = next(n["id"] for n in r["nodes"] if n["label"] == "ClientId")
    related = [e for e in r["edges"] if e["target"] == cid]
    assert related, "the construction edge must exist"
    assert all(e["relation"] != "calls" for e in related), related
    assert any(
        e["relation"] == "references" and e.get("context") == "constructor"
        for e in related
    ), related


def test_rust_same_file_construction_is_reference_not_call(tmp_path):
    (tmp_path / "ids.rs").write_text(
        "pub struct ClientId(pub u32);\n"
        "pub fn wrap(raw: u32) -> u32 {\n"
        "    let _id = ClientId(raw);\n"
        "    raw\n"
        "}\n",
        encoding="utf-8")
    r = extract(sorted(tmp_path.glob("*.rs")), cache_root=tmp_path / "graphify-out")

    cid = next(n["id"] for n in r["nodes"] if n["label"] == "ClientId")
    related = [e for e in r["edges"] if e["target"] == cid and str(e["source"]).endswith("wrap")]
    assert related, "the construction edge must exist"
    assert all(e["relation"] != "calls" for e in related), related
    assert any(e.get("context") == "constructor" for e in related), related


def test_rust_locally_defined_prelude_name_is_kept(tmp_path):
    # A crate may shadow a prelude name (its own `struct Result<T>`). The filter
    # must not erase references to a type the file actually defines.
    (tmp_path / "shadow.rs").write_text(
        "pub struct Result<T>(pub T);\n"
        "pub struct Holder {\n"
        "    pub value: Result<u32>,\n"
        "}\n",
        encoding="utf-8")
    r = extract(sorted(tmp_path.glob("*.rs")), cache_root=tmp_path / "graphify-out")

    result_ids = [n["id"] for n in r["nodes"] if n["label"] == "Result"]
    assert result_ids, "a locally defined Result must still become a node"
    referenced = [
        e for e in r["edges"]
        if e["target"] in result_ids and e["relation"] == "references"
    ]
    assert referenced, "references to the locally defined Result must survive"


def test_rust_function_call_still_emits_calls(tmp_path):
    (tmp_path / "lib.rs").write_text(
        "pub fn helper() -> u32 { 1 }\n"
        "pub fn run() -> u32 { helper() }\n",
        encoding="utf-8")
    r = extract(sorted(tmp_path.glob("*.rs")), cache_root=tmp_path / "graphify-out")

    rels = {e["relation"] for e in r["edges"] if str(e["target"]).endswith("helper")}
    assert "calls" in rels, f"a real function call must stay `calls`; got {rels}"
