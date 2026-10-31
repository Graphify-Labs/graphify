"""Declarations of different kinds whose names differ only in case keep their own nodes (#4904)."""
import pytest

from graphify.extract import extract
from graphify.ids import DeclIdRegistry

CASES = {
    "a.js": "class Foo {\n  run() { return 1 }\n}\n\nfunction foo() {\n  return new Foo().run()\n}\n",
    "a.ts": "class Foo {\n  run(): number { return 1 }\n}\n\nfunction foo(): number {\n  return new Foo().run()\n}\n",
    "a.kt": "class Foo { fun run(): Int = 1 }\n\nfun foo(): Int = Foo().run()\n",
    "a.cpp": "class Foo { public: int run() { return 1; } };\n\nint foo() { Foo f; return f.run(); }\n",
    "a.php": "<?php\nclass Foo { function run() { return 1; } }\n\nfunction foo() { return (new Foo())->run(); }\n",
    "a.rb": "class Foo\n  def run; 1; end\nend\n\ndef foo; Foo.new.run; end\n",
    "a.swift": "struct Foo { func run() -> Int { 1 } }\n\nfunc foo() -> Int { Foo().run() }\n",
}


def _extract(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return extract([path], cache_root=tmp_path, root=tmp_path)


@pytest.mark.parametrize("name", sorted(CASES))
def test_type_and_function_differing_in_case_are_two_nodes(tmp_path, name):
    result = _extract(tmp_path, name, CASES[name])

    labels = {n["label"] for n in result["nodes"]}
    assert {"Foo", "foo()"} <= labels
    by_label = {n["label"]: n["id"] for n in result["nodes"]}
    assert by_label["Foo"] != by_label["foo()"]


def test_the_call_belongs_to_the_function_not_the_class(tmp_path):
    result = _extract(tmp_path, "a.js", CASES["a.js"])

    by_label = {n["label"]: n["id"] for n in result["nodes"]}
    assert not [e for e in result["edges"] if e["relation"] == "calls" and e["source"] == e["target"]]
    assert by_label["foo()"] in {e["source"] for e in result["edges"] if e["relation"] == "calls"}


def test_same_spelling_across_kinds_stays_one_declaration(tmp_path):
    result = _extract(
        tmp_path,
        "a.ts",
        "export class Foo { x = 1 }\nexport namespace Foo { export const y = 2 }\n",
    )

    assert sum(1 for n in result["nodes"] if n["label"] == "Foo") == 1


def test_registry_reuses_only_same_kind_or_same_spelling():
    taken = set()
    registry = DeclIdRegistry()
    assert registry.resolve("a_foo", "Foo", "type", taken) == "a_foo"
    taken.add("a_foo")

    assert registry.resolve("a_foo", "FOO", "type", taken) == "a_foo"
    assert registry.resolve("a_foo", "Foo", "ns", taken) == "a_foo"
    salted = registry.resolve("a_foo", "foo", "fn", taken)
    assert salted != "a_foo"
    assert registry.resolve("a_foo", "foo", "fn", taken) == salted
