"""Rust `type` aliases and `union` items are declarations (#4285, item 5).

extract_rust emitted nodes for `struct`, `enum` and `trait` only, so a field,
parameter or return typed with an alias or a union declared in the same file
resolved through ensure_named_node to a SOURCELESS stub, which the corpus
rewire could then grow into a cross-file hub. Both are now type nodes in their
declaring file. A union's fields reference their types as a struct's do; an
alias is a bare node (its right-hand side is not walked). An associated type in
an `impl` (`type Output = Foo;`) is the same tree-sitter node but not a
file-level item, so it still emits nothing.
"""
from __future__ import annotations

import json
from pathlib import Path

from graphify.extract import extract
from graphify.extractors.rust import extract_rust

_SOURCE = """\
pub type Callback = fn(i32) -> i32;
pub type Res<T> = Result<T, Error>;
pub struct Error;
pub union Bits {
    i: u32,
    e: Error,
}
pub struct Button {
    cb: Callback,
    bits: Bits,
}
pub fn run(cb: Callback, b: Bits) -> Res<Callback> {
    Ok(cb)
}
"""


def _extract(tmp_path: Path, source: str = _SOURCE, name: str = "lib.rs") -> tuple[dict, Path]:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return extract_rust(path), path


def _by_label(result: dict, label: str) -> list[dict]:
    return [n for n in result["nodes"] if n["label"] == label]


def test_alias_and_union_are_sourced_nodes_in_their_file(tmp_path: Path):
    result, path = _extract(tmp_path)
    for label, line in (("Callback", "L1"), ("Res", "L2"), ("Bits", "L4")):
        [node] = _by_label(result, label)
        assert node["source_file"] == str(path), label
        assert node["source_location"] == line, label
    assert [n["label"] for n in result["nodes"] if not n.get("source_file")] == []


def test_alias_and_union_are_contained_by_the_file(tmp_path: Path):
    result, _ = _extract(tmp_path)
    by_id = {n["id"]: n["label"] for n in result["nodes"]}
    contained = {by_id.get(e["target"]) for e in result["edges"] if e["relation"] == "contains"}
    assert {"Callback", "Res", "Bits"} <= contained


def test_references_bind_to_the_local_declarations(tmp_path: Path):
    result, _ = _extract(tmp_path)
    by_id = {n["id"]: n["label"] for n in result["nodes"]}
    refs = {
        (by_id.get(e["source"]), by_id.get(e["target"]))
        for e in result["edges"] if e["relation"] == "references"
    }
    assert {("Button", "Callback"), ("Button", "Bits"), ("run()", "Callback"),
            ("run()", "Bits"), ("run()", "Res")} <= refs


def test_union_fields_reference_their_types(tmp_path: Path):
    result, _ = _extract(tmp_path)
    by_id = {n["id"]: n["label"] for n in result["nodes"]}
    field_refs = {
        (by_id.get(e["source"]), by_id.get(e["target"]))
        for e in result["edges"]
        if e["relation"] == "references" and e.get("context") == "field"
    }
    assert ("Bits", "Error") in field_refs


def test_an_impl_associated_type_is_not_a_file_level_node(tmp_path: Path):
    source = (
        "use std::ops::Add;\npub struct Meters(pub f64);\n"
        "impl Add for Meters {\n    type Output = Meters;\n"
        "    fn add(self, o: Meters) -> Meters { Meters(self.0 + o.0) }\n}\n"
    )
    result, _ = _extract(tmp_path, source)
    assert _by_label(result, "Output") == []


def test_a_cross_file_reference_lands_on_the_alias(tmp_path: Path):
    """The alias carries the declaration count the corpus tie-break reads, so a
    reference from another file rewires onto it instead of a stub."""
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "demo"\nversion = "0.1.0"\nedition = "2021"\n', encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "lib.rs").write_text("pub mod types;\npub mod user;\n", encoding="utf-8")
    (src / "types.rs").write_text("pub type Callback = fn(i32) -> i32;\n", encoding="utf-8")
    (src / "user.rs").write_text(
        "use crate::types::Callback;\npub struct Button {\n    cb: Callback,\n}\n", encoding="utf-8")
    paths = sorted(src.glob("*.rs"))
    result = extract(paths, root=tmp_path, cache_root=tmp_path / "graphify-out", parallel=False)
    [alias] = [n for n in result["nodes"] if n["label"] == "Callback"]
    assert alias["source_file"].endswith("types.rs")
    by_id = {n["id"]: n for n in result["nodes"]}
    targets = {
        e["target"] for e in result["edges"]
        if e["relation"] == "references" and by_id.get(e["source"], {}).get("label") == "Button"
    }
    assert targets == {alias["id"]}, json.dumps(result["edges"], indent=1)
