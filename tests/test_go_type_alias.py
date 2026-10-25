"""A Go type alias (`type A = B`) is a declaration, like a defined type.

tree-sitter-go parses `type A = B` as a `type_alias`, not a `type_spec`, and
extract_go walked `type_spec` only. The alias was dropped, so a field,
parameter or return typed with it, even below the declaration, resolved to a
SOURCELESS stub that the corpus rewire can grow into a cross-file hub. A method
declared on an alias receiver (`func (a Alias) M()`) minted the alias's node at
the method's line instead. An alias is now a type node on its own line, like a
defined type: the same id, the same collision census and the same conversion
semantics (`ID("x")` as `Named("y")`). Its right-hand side is not walked.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from graphify.extract import extract

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("tree_sitter_go") is None,
    reason="tree_sitter_go not installed",
)

_SOURCE = """\
package p

type Handler = func(int) int
type Pair[T any] = struct{ a, b T }
type (
	ID   = string
	Name string
)
type Base struct{}
type Alias = Base

type Holder struct {
	h  Handler
	id ID
	p  Pair[int]
}

func (a Alias) M() {}

func Use(h Handler, id ID) ID {
	_ = ID("x")
	_ = Name("y")
	return id
}
"""


def _extract_file(tmp_path: Path, source: str = _SOURCE) -> dict:
    from graphify.extractors.go import extract_go

    path = tmp_path / "p" / "a.go"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return extract_go(path)


def _labels(result: dict) -> dict[str, str]:
    return {n["id"]: n["label"] for n in result["nodes"]}


def _pairs(result: dict, relation: str) -> set[tuple[str, str]]:
    label = _labels(result)
    return {(label.get(e["source"], str(e["source"])), label.get(e["target"], str(e["target"])))
            for e in result["edges"] if e["relation"] == relation}


def test_each_alias_is_a_sourced_node_on_its_own_line(tmp_path: Path):
    result = _extract_file(tmp_path)
    for label, line in (("Handler", "L3"), ("Pair", "L4"), ("ID", "L6"), ("Alias", "L10")):
        [node] = [n for n in result["nodes"] if n["label"] == label]
        assert node["source_file"], label
        assert node["source_location"] == line, label
    assert [n["label"] for n in result["nodes"] if not n.get("source_file")] == []


def test_each_alias_is_contained_by_its_file(tmp_path: Path):
    contained = {tgt for src, tgt in _pairs(_extract_file(tmp_path), "contains")}
    assert {"Handler", "Pair", "ID", "Alias"} <= contained


def test_references_bind_to_the_local_alias(tmp_path: Path):
    refs = _pairs(_extract_file(tmp_path), "references")
    assert {("Holder", "Handler"), ("Holder", "ID"), ("Holder", "Pair"),
            ("Use()", "Handler"), ("Use()", "ID")} <= refs


def test_a_method_on_an_alias_receiver_hangs_off_the_alias_declaration(tmp_path: Path):
    result = _extract_file(tmp_path)
    assert ("Alias", ".M()") in _pairs(result, "method")
    [alias] = [n for n in result["nodes"] if n["label"] == "Alias"]
    assert alias["source_location"] == "L10"


def test_an_alias_conversion_is_treated_like_a_defined_type_conversion(tmp_path: Path):
    calls = _pairs(_extract_file(tmp_path), "calls")
    assert ("Use()", "Name") in calls
    assert ("Use()", "ID") in calls


def test_a_case_distinct_alias_and_type_stay_separate(tmp_path: Path):
    result = _extract_file(tmp_path, "package p\n\ntype ID = string\ntype Id struct{}\n")
    ids = [n for n in result["nodes"] if n["label"] in ("ID", "Id")]
    assert len(ids) == 2
    assert len({n["id"] for n in ids}) == 2


def test_a_reference_from_another_file_of_the_package_lands_on_the_alias(tmp_path: Path):
    files = {
        "p/types.go": "package p\n\ntype Handler = func(int) int\n",
        "p/use.go": "package p\n\ntype Button struct {\n\th Handler\n}\n",
    }
    for name, body in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(body, encoding="utf-8")
    result = extract([tmp_path / n for n in files], root=tmp_path,
                     cache_root=tmp_path / "graphify-out", parallel=False)
    [handler] = [n for n in result["nodes"] if n["label"] == "Handler"]
    assert handler["source_file"].endswith("types.go")
    label = _labels(result)
    targets = {e["target"] for e in result["edges"]
               if e["relation"] == "references" and label.get(e["source"]) == "Button"}
    assert targets == {handler["id"]}


def test_a_same_name_re_export_alias_resolves_to_the_original(tmp_path: Path):
    """`type Field = zapcore.Field` re-exports another package's type under its
    own name: the alias denotes that very type. It emits no node, so references
    to `Field` keep resolving to the one real `Field` instead of tying between
    the alias and the original (uber-go/zap's shape)."""
    files = {
        "core/field.go": "package core\n\ntype Field struct{ Key string }\n",
        "zap/field.go": ('package zap\n\nimport "example.com/core"\n\n'
                         "type Field = core.Field\n\nfunc String(k string) Field { return Field{Key: k} }\n"),
        "zap/logger.go": "package zap\n\nfunc Info(msg string, fields []Field) {}\n",
    }
    for name, body in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(body, encoding="utf-8")
    result = extract([tmp_path / n for n in files], root=tmp_path,
                     cache_root=tmp_path / "graphify-out", parallel=False)
    fields = [n for n in result["nodes"] if n["label"] == "Field"]
    assert [Path(n["source_file"]).as_posix().endswith("core/field.go") for n in fields] == [True]
    label = _labels(result)
    refs = {label.get(e["source"]) for e in result["edges"]
            if e["relation"] == "references" and e["target"] == fields[0]["id"]}
    assert {"String()", "Info()"} <= refs


@pytest.mark.parametrize("alias", [
    "type Field = core.Field[int]",   # generic re-export: still the same type name
    "type Field = core.Field",
])
def test_a_re_export_alias_emits_no_node(tmp_path: Path, alias: str):
    result = _extract_file(tmp_path, f"package zap\n\n{alias}\n")
    assert [n for n in result["nodes"] if n["label"] == "Field"] == []


@pytest.mark.parametrize("alias", [
    "type Field = core.Entry",        # renamed: a new name, so a declaration here
    "type Field = Entry",             # an alias of a local type
    "type Field = map[string]any",
])
def test_an_alias_that_introduces_a_new_name_is_a_node(tmp_path: Path, alias: str):
    result = _extract_file(tmp_path, f"package zap\n\n{alias}\n")
    assert [n["label"] for n in result["nodes"] if n["label"] == "Field"] == ["Field"]
