"""A nested Swift type id never takes the id of a declaration of another scope.

A nested type's id joins its parent's id and its name, so `Outer.State`, a
file-level `Outer_State` or `outer_state()`, and `Outer.A.B` / `Outer.A_B` slug
to one id each. `add_node` kept the first node and dropped the second, and the
dropped declaration's methods hung under the survivor. The shallower declaration
(or the function) now keeps the plain id and the nested type is salted.
"""
from __future__ import annotations

from pathlib import Path

import graphify.cache as cache
from graphify.extract import _make_id, extract, extract_swift


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _one(result: dict, label: str) -> str:
    ids = [n["id"] for n in result["nodes"] if n.get("label") == label]
    assert len(ids) == 1, (label, ids)
    return ids[0]


def _sources(result: dict, target: str, relation: str) -> set[str]:
    return {
        e["source"] for e in result["edges"]
        if e.get("relation") == relation and e.get("target") == target
    }


_OUTER_AND_TOPLEVEL_TYPE = (
    "struct Outer {\n"
    "    struct State {\n"
    "        func inner() {}\n"
    "    }\n"
    "}\n"
    "struct Outer_State {\n"
    "    func top() {}\n"
    "}\n"
)


def test_nested_type_does_not_swallow_toplevel_underscore_type(tmp_path: Path):
    result = extract_swift(_write(tmp_path / "Outer.swift", _OUTER_AND_TOPLEVEL_TYPE))

    outer = _one(result, "Outer")
    state = _one(result, "State")
    top_type = _one(result, "Outer_State")
    assert state != top_type
    assert top_type == _make_id(outer, "State"), "the file-level type keeps the plain id"
    assert _sources(result, state, "contains") == {outer}
    assert outer not in _sources(result, top_type, "contains")
    assert _sources(result, _one(result, ".top()"), "method") == {top_type}
    assert _sources(result, _one(result, ".inner()"), "method") == {state}


def test_nested_type_does_not_swallow_toplevel_function(tmp_path: Path):
    result = extract_swift(_write(tmp_path / "Outer.swift", (
        "struct Outer {\n"
        "    struct State {}\n"
        "}\n"
        "func outer_state() {}\n"
    )))

    outer = _one(result, "Outer")
    state = _one(result, "State")
    func = _one(result, "outer_state()")
    assert state != func
    assert func == _make_id(outer, "State"), "the file-level function keeps the plain id"
    assert _sources(result, state, "contains") == {outer}


def test_nested_type_in_extension_before_declaration(tmp_path: Path):
    # The extension that declares the nested type comes first in the file.
    result = extract_swift(_write(tmp_path / "Outer.swift", (
        "extension Outer {\n"
        "    struct State {\n"
        "        func inner() {}\n"
        "    }\n"
        "}\n"
        "struct Outer {}\n"
        "struct Outer_State {\n"
        "    func top() {}\n"
        "}\n"
    )))

    outer = _one(result, "Outer")
    state = _one(result, "State")
    top_type = _one(result, "Outer_State")
    assert state != top_type
    assert top_type == _make_id(outer, "State")
    assert _sources(result, _one(result, ".top()"), "method") == {top_type}
    assert _sources(result, _one(result, ".inner()"), "method") == {state}


def test_extension_of_nested_type_before_declaration_takes_salted_id(tmp_path: Path):
    # `extension Outer.State` above the declarations hangs its member under the
    # salted nested type, not under the file-level `Outer_State`.
    result = extract_swift(_write(tmp_path / "Outer.swift", (
        "extension Outer.State {\n"
        "    func extra() {}\n"
        "}\n"
        + _OUTER_AND_TOPLEVEL_TYPE
    )))

    # The extension may mint the nested type's node first, under its own label, so
    # the type is found through the member its declaration holds.
    (state,) = _sources(result, _one(result, ".inner()"), "method")
    top_type = _one(result, "Outer_State")
    assert state != top_type
    assert _sources(result, _one(result, ".extra()"), "method") == {state}
    assert _sources(result, _one(result, ".top()"), "method") == {top_type}


def test_deeper_nested_type_yields_to_shallower_nested_type(tmp_path: Path):
    # `Outer.A.B` and `Outer.A_B` slug to one id one level below the file.
    result = extract_swift(_write(tmp_path / "Outer.swift", (
        "struct Outer {\n"
        "    struct A {\n"
        "        struct B {\n"
        "            func deep() {}\n"
        "        }\n"
        "    }\n"
        "    struct A_B {\n"
        "        func shallow() {}\n"
        "    }\n"
        "}\n"
    )))

    outer = _one(result, "Outer")
    a = _one(result, "A")
    b = _one(result, "B")
    a_b = _one(result, "A_B")
    assert b != a_b
    assert a_b == _make_id(outer, "A_B"), "the shallower nested type keeps the plain id"
    assert _sources(result, b, "contains") == {a}
    assert _sources(result, a_b, "contains") == {outer}
    assert _sources(result, _one(result, ".deep()"), "method") == {b}
    assert _sources(result, _one(result, ".shallow()"), "method") == {a_b}


def test_written_reference_reaches_salted_nested_type(tmp_path: Path):
    # `Outer.State` slugs to the plain id the file-level `Outer_State`
    # holds; the Swift type pass must bind the references to the salted
    # nested type.
    src = tmp_path / "src"
    path = _write(src / "Outer.swift", (
        "struct Outer {\n"
        "    struct State {}\n"
        "}\n"
        "struct Outer_State {}\n"
        "func consume(_ x: Outer.State) -> Outer.State { x }\n"
    ))
    result = extract([path], cache_root=tmp_path / "cache", root=src, parallel=False)

    state = _one(result, "State")
    top_type = _one(result, "Outer_State")
    consume = _one(result, "consume()")
    targets = {
        e["target"] for e in result["edges"]
        if e.get("relation") == "references" and e.get("source") == consume
    }
    assert state in targets
    assert top_type not in targets


def test_sibling_salted_ids_do_not_salt_a_deeper_type(tmp_path: Path):
    # The sibling rule already salts `A_B` and `a_b()`, so nothing of
    # another scope holds the plain id and `Outer.A.B` keeps it (no id churn).
    result = extract_swift(_write(tmp_path / "Outer.swift", (
        "struct Outer {\n"
        "    struct A {\n"
        "        struct B {}\n"
        "    }\n"
        "    struct A_B {}\n"
        "    func a_b() {}\n"
        "}\n"
    )))

    a = _one(result, "A")
    b = _one(result, "B")
    assert b == _make_id(a, "B")
    assert b != _one(result, "A_B")
    assert b != _one(result, ".a_b()")


def test_nested_type_id_unchanged_without_collision(tmp_path: Path):
    # Not a regression test (passes before the fix): without a declaration of
    # another scope on the id, the nested type keeps its Phase 3 id.
    result = extract_swift(_write(tmp_path / "Outer.swift", (
        "struct Outer {\n"
        "    struct State {}\n"
        "}\n"
        "struct Other {}\n"
        "func helper() {}\n"
    )))

    outer = _one(result, "Outer")
    assert _one(result, "State") == _make_id(outer, "State")


def test_previous_schema_cache_entry_is_not_reused(tmp_path: Path, monkeypatch):
    # An AST entry cached by the previous schema holds the old ids; the schema
    # bump keys the cache directory, so the fixed extraction runs again.
    src = tmp_path / "src"
    path = _write(src / "Outer.swift", _OUTER_AND_TOPLEVEL_TYPE)
    cache_root = tmp_path / "cache"
    current = cache._AST_CACHE_SCHEMA

    def _run() -> dict:
        return extract([path], cache_root=cache_root, root=src, parallel=False)

    monkeypatch.setattr(cache, "_AST_CACHE_SCHEMA", current - 1)
    _run()
    entries = [
        p for p in tmp_path.rglob("*.json")
        if any(f"-s{current - 1}-" in part for part in p.parts)
    ]
    assert entries, "the previous schema wrote an AST entry"
    for entry in entries:
        text = entry.read_text(encoding="utf-8")
        entry.write_text(text.replace("Outer_State", "Stale_State"), encoding="utf-8")
    stale = _run()
    assert any(n.get("label") == "Stale_State" for n in stale["nodes"]), (
        "control: the previous schema reads its own (doctored) entry"
    )

    monkeypatch.setattr(cache, "_AST_CACHE_SCHEMA", current)
    fresh = _run()
    labels = {n.get("label") for n in fresh["nodes"]}
    assert "Stale_State" not in labels
    assert "Outer_State" in labels
