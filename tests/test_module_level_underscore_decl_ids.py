"""Module-level `_x` and `x` in one file keep their own nodes and calls (#2810).

Both normalize to the same id, so before the fix the second declaration reused
the first one's id: one node survived and `x()`'s call to `_x()` became a
fabricated `x -> x` self-call.
"""
import pytest

from graphify.extract import extract
from graphify.ids import DeclIdRegistry

CASES = {
    "a.js": (
        "function _save() { return 1 }\n"
        "function save() { return _save() }\n"
        "function caller() { return save() }\n"
    ),
    "a.ts": (
        "function _save(): number { return 1 }\n"
        "function save(): number { return _save() }\n"
        "function caller(): number { return save() }\n"
    ),
    "arrow.ts": (
        "const _save = (): number => 1\n"
        "const save = (): number => _save()\n"
        "const caller = (): number => save()\n"
    ),
    "a.c": (
        "int _save(void) { return 1; }\n"
        "int save(void) { return _save(); }\n"
        "int caller(void) { return save(); }\n"
    ),
    "a.cpp": (
        "int _save() { return 1; }\n"
        "int save() { return _save(); }\n"
        "int caller() { return save(); }\n"
    ),
    "a.php": (
        "<?php\n"
        "function _save() { return 1; }\n"
        "function save() { return _save(); }\n"
        "function caller() { return save(); }\n"
    ),
    "a.rb": (
        "def _save; 1; end\n"
        "def save; _save; end\n"
        "def caller; save; end\n"
    ),
    "a.kt": (
        "fun _save(): Int = 1\n"
        "fun save(): Int = _save()\n"
        "fun caller(): Int = save()\n"
    ),
    "a.swift": (
        "func _save() -> Int { 1 }\n"
        "func save() -> Int { _save() }\n"
        "func caller() -> Int { save() }\n"
    ),
    "a.lua": (
        "function _save() return 1 end\n"
        "function save() return _save() end\n"
        "function caller() return save() end\n"
    ),
}

GRAMMARS = {
    ".js": "tree_sitter_javascript", ".ts": "tree_sitter_typescript", ".c": "tree_sitter_c",
    ".cpp": "tree_sitter_cpp", ".php": "tree_sitter_php", ".rb": "tree_sitter_ruby",
    ".kt": "tree_sitter_kotlin", ".swift": "tree_sitter_swift", ".lua": "tree_sitter_lua",
}


def _extract(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return extract([path], cache_root=tmp_path, root=tmp_path)


@pytest.mark.parametrize("name", sorted(CASES))
def test_underscore_twins_are_two_nodes_with_their_own_calls(tmp_path, name):
    pytest.importorskip(GRAMMARS[name[name.rindex("."):]])
    result = _extract(tmp_path, name, CASES[name])

    by_label = {n["label"]: n["id"] for n in result["nodes"]}
    assert {"_save()", "save()", "caller()"} <= set(by_label)
    assert by_label["_save()"] != by_label["save()"]

    calls = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}
    assert not [c for c in calls if c[0] == c[1]]
    assert (by_label["save()"], by_label["_save()"]) in calls
    assert (by_label["caller()"], by_label["save()"]) in calls


def test_ids_do_not_depend_on_a_rebuild(tmp_path):
    first = _extract(tmp_path, "a.js", CASES["a.js"])
    again = extract([tmp_path / "a.js"], cache_root=tmp_path / "fresh", root=tmp_path)

    assert sorted(n["id"] for n in first["nodes"]) == sorted(n["id"] for n in again["nodes"])


def test_registry_salts_a_same_kind_underscore_respelling():
    taken = set()
    registry = DeclIdRegistry()
    assert registry.resolve("a_save", "_save", "fn", taken) == "a_save"
    taken.add("a_save")

    plain = registry.resolve("a_save", "save", "fn", taken)
    assert plain != "a_save"
    taken.add(plain)
    assert registry.resolve("a_save", "save", "fn", taken) == plain
    assert registry.resolve("a_save", "_save", "fn", taken) == "a_save"
    assert registry.lookup("save") == plain
    assert registry.lookup("_save") == "a_save"


def test_registry_still_reuses_a_same_kind_case_respelling():
    taken = set()
    registry = DeclIdRegistry()
    assert registry.resolve("a_foo", "Foo", "type", taken) == "a_foo"
    taken.add("a_foo")

    assert registry.resolve("a_foo", "FOO", "type", taken) == "a_foo"
