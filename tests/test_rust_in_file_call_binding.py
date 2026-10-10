"""Rust in-file call binding follows the call's shape.

A call was bound to whichever node in the same file carried the callee's bare
name, so `B::new()` reached `A::new()` when the file defined both, `Arc::new(x)`
reached the file's own `fn new`, and `drop(x)` reached `impl Drop`'s method.
`Type::f()`, `Self::f()` and `self.f()` now bind only to a method of that type,
a bare `f()` only to a free function or a constructor, and `x.f()` only to a
method.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract
from graphify.extractors.rust import extract_rust


def _edges(tmp_path: Path, source: str, relation: str = "calls") -> set[tuple[str, str, str]]:
    path = tmp_path / "lib.rs"
    path.write_text(source, encoding="utf-8")
    result = extract_rust(path)
    nodes = {n["id"]: n for n in result["nodes"]}
    return {
        (nodes[e["source"]]["label"], nodes[e["target"]]["label"], nodes[e["target"]]["source_location"])
        for e in result["edges"]
        if e["relation"] == relation and e["source"] in nodes and e["target"] in nodes
    }


def test_type_qualified_call_binds_to_that_types_method(tmp_path: Path):
    calls = _edges(tmp_path, (
        "struct A;\n"
        "struct B;\n"
        "impl A { fn new() -> A { A } }\n"            # L3
        "impl B { fn new() -> B { B } }\n"            # L4
        "fn make_a() -> A { A::new() }\n"
        "fn make_b() -> B { crate::B::new() }\n"
        "impl A { fn again() -> A { Self::new() } }\n"
    ))
    assert ("make_a()", ".new()", "L3") in calls
    assert ("make_b()", ".new()", "L4") in calls
    assert (".again()", ".new()", "L3") in calls
    assert ("make_a()", ".new()", "L4") not in calls
    assert ("make_b()", ".new()", "L3") not in calls


def test_call_on_a_type_the_file_does_not_implement_gets_no_edge(tmp_path: Path):
    calls = _edges(tmp_path, (
        "use std::sync::Arc;\n"
        "struct Builder;\n"
        "impl Builder { fn new() -> Builder { Builder } fn default() -> Builder { Builder } }\n"
        "fn shared() -> Arc<u8> { Arc::new(1) }\n"
        "fn options() -> Vec<u8> { Vec::default() }\n"
    ))
    assert not {c for c in calls if c[0] in ("shared()", "options()")}, calls


def test_self_call_binds_to_the_callers_own_type(tmp_path: Path):
    calls = _edges(tmp_path, (
        "struct A;\n"
        "struct B;\n"
        "impl A {\n"
        "    fn run(&self) { self.go(); self.stop(); }\n"
        "    fn go(&self) {}\n"                         # L5
        "}\n"
        "impl B {\n"
        "    fn go(&self) {}\n"                         # L8
        "    fn stop(&self) {}\n"                       # L9
        "}\n"
    ))
    assert (".run()", ".go()", "L5") in calls
    assert (".run()", ".go()", "L8") not in calls
    # A has no `stop`: B's is never the target (the cross-file `self` pass decides).
    assert (".run()", ".stop()", "L9") not in calls


def test_bare_call_never_binds_to_a_method_and_member_call_never_to_a_free_fn(tmp_path: Path):
    calls = _edges(tmp_path, (
        "struct Child;\n"
        "impl Drop for Child { fn drop(&mut self) {} }\n"
        "fn total() -> usize { 0 }\n"
        "fn close(c: Child) { drop(c); }\n"
        "fn count(v: &Stats) -> usize { v.total() }\n"
    ))
    assert not {c for c in calls if c[0] in ("close()", "count()")}, calls


def test_primitive_and_path_qualified_impl_types_bind(tmp_path: Path):
    calls = _edges(tmp_path, (
        "use std::io;\n"
        "struct Code;\n"
        "struct Failure;\n"
        "impl From<Code> for i32 { fn from(c: Code) -> i32 { 0 } }\n"            # L4
        "impl From<Failure> for io::Error { fn from(f: Failure) -> io::Error { todo!() } }\n"  # L5
        "fn status(c: Code) -> i32 { i32::from(c) }\n"
        "fn fail(f: Failure) -> io::Error { io::Error::from(f) }\n"
    ))
    assert ("status()", ".from()", "L4") in calls
    assert ("fail()", ".from()", "L5") in calls


def test_enum_variant_constructor_is_still_a_reference(tmp_path: Path):
    refs = _edges(tmp_path, (
        "enum Shape { Circle(u32), Square(u32) }\n"
        "fn mk() -> Shape { Shape::Circle(1) }\n"
    ), relation="references")
    assert ("mk()", "Circle", "L1") in refs


def test_self_call_to_another_files_impl_still_resolves(tmp_path: Path):
    # The caller's file defines a same-named method on another type; the call
    # must reach its own type's method in the other file, not the local one.
    for name, body in {
        "a.rs": "pub struct A;\nimpl A { pub fn launch(&self) {} }\n",
        "b.rs": (
            "use crate::a::A;\n"
            "pub struct B;\n"
            "impl B { pub fn launch(&self) {} }\n"
            "impl A { pub fn run(&self) { self.launch(); } }\n"
        ),
    }.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    result = extract([tmp_path / "a.rs", tmp_path / "b.rs"], cache_root=tmp_path / "graphify-out")
    nodes = {n["id"]: n for n in result["nodes"]}
    targets = {
        Path(str(nodes[e["target"]]["source_file"])).name
        for e in result["edges"]
        if e["relation"] == "calls" and nodes.get(e["source"], {}).get("label") == ".run()"
    }
    assert targets == {"a.rs"}, targets
