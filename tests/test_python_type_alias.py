"""Explicit Python type aliases are declarations.

A module-level `type Vector = list[float]` (PEP 695), `Matrix: TypeAlias = ...`
and `UserId = NewType("UserId", int)` each declare a type name, but the Python
extractor emitted no node for them. Every annotation using the name, even in
the same module, resolved to a SOURCELESS stub that the corpus rewire can grow
into a cross-file hub. They are now type nodes contained by their module, in
the same collision census as module-level classes and functions.

Boundaries: only these explicit forms count. A bare `JsonValue = Union[...]`
is an alias by convention only, and treating every capitalised assignment as a
type would be a guess. A same-name re-export (`Field: TypeAlias = core.Field`,
`type Field = core.Field[int]`, `Field: TypeAlias = Field` after
`from core import Field`) denotes the original type and declares no new
name, so it emits no node: references keep resolving to the one real `Field`.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from graphify.extract import extract

_SOURCE = textwrap.dedent("""\
    import typing
    from typing import NewType, TypeAlias

    type Vector = list[float]
    type Pair[T] = tuple[T, T]
    UserId = NewType("UserId", int)
    Matrix: TypeAlias = list[Vector]
    Grid: typing.TypeAlias = list[Matrix]


    def scale(v: Vector, u: UserId, m: Matrix, p: Pair[int], g: Grid) -> Vector:
        return v
    """)


def _extract(tmp_path: Path, files: dict[str, str]) -> dict:
    for name, body in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(body, encoding="utf-8")
    return extract([tmp_path / n for n in files], root=tmp_path,
                   cache_root=tmp_path / "graphify-out", parallel=False)


def _labels(result: dict) -> dict[str, str]:
    return {n["id"]: n["label"] for n in result["nodes"]}


def _pairs(result: dict, relation: str) -> set[tuple[str, str]]:
    label = _labels(result)
    return {(label.get(e["source"], str(e["source"])), label.get(e["target"], str(e["target"])))
            for e in result["edges"] if e["relation"] == relation}


def test_each_explicit_alias_is_a_sourced_node_on_its_line(tmp_path: Path):
    result = _extract(tmp_path, {"shapes.py": _SOURCE})
    for label, line in (("Vector", "L4"), ("Pair", "L5"), ("UserId", "L6"),
                        ("Matrix", "L7"), ("Grid", "L8")):
        matches = [n for n in result["nodes"] if n["label"] == label]
        assert len(matches) == 1, label
        assert matches[0]["source_file"], label
        assert matches[0]["source_location"] == line, label
    assert [n["label"] for n in result["nodes"] if not n.get("source_file")] == []


def test_each_alias_is_contained_by_its_module(tmp_path: Path):
    contained = {tgt for _src, tgt in _pairs(_extract(tmp_path, {"shapes.py": _SOURCE}), "contains")}
    assert {"Vector", "Pair", "UserId", "Matrix", "Grid"} <= contained


def test_annotations_reference_the_local_aliases(tmp_path: Path):
    refs = _pairs(_extract(tmp_path, {"shapes.py": _SOURCE}), "references")
    assert {("scale()", "Vector"), ("scale()", "UserId"), ("scale()", "Matrix"),
            ("scale()", "Pair"), ("scale()", "Grid")} <= refs


def test_an_alias_and_a_function_that_fold_to_one_id_stay_separate(tmp_path: Path):
    """`Vector` and `vector()` slug to one id (#2810's census)."""
    result = _extract(tmp_path, {"shapes.py": "type Vector = list[float]\n\n\ndef vector():\n    pass\n"})
    labels = sorted(n["label"] for n in result["nodes"] if n["label"] in ("Vector", "vector()"))
    assert labels == ["Vector", "vector()"]
    assert len({n["id"] for n in result["nodes"] if n["label"] in ("Vector", "vector()")}) == 2


def test_a_reference_from_another_module_lands_on_the_alias(tmp_path: Path):
    result = _extract(tmp_path, {
        "types_.py": "from typing import NewType\n\nUserId = NewType(\"UserId\", int)\n",
        "users.py": "from types_ import UserId\n\n\ndef load(uid: UserId) -> None:\n    pass\n",
    })
    [uid] = [n for n in result["nodes"] if n["label"] == "UserId"]
    assert uid["source_file"].endswith("types_.py")
    label = _labels(result)
    targets = {e["target"] for e in result["edges"]
               if e["relation"] == "references" and label.get(e["source"]) == "load()"}
    assert uid["id"] in targets


@pytest.mark.parametrize("alias", [
    "from typing import TypeAlias\nimport core\n\nField: TypeAlias = core.Field\n",
    "import core\n\ntype Field = core.Field[int]\n",
])
def test_a_same_name_re_export_emits_no_node(tmp_path: Path, alias: str):
    result = _extract(tmp_path, {"api.py": alias})
    assert [n for n in result["nodes"] if n["label"] == "Field"] == []



def test_a_bare_same_name_re_export_keeps_references_on_the_original(tmp_path: Path):
    result = _extract(tmp_path, {
        "core.py": "class Field:\n    pass\n",
        "api.py": ("from typing import TypeAlias\nfrom core import Field\n\n"
                   "Field: TypeAlias = Field\n\ndef f(x: Field) -> None: ...\n"),
    })
    [field] = [n for n in result["nodes"] if n["label"] == "Field"]
    assert field["source_file"].endswith("core.py")
    label = _labels(result)
    targets = {e["target"] for e in result["edges"]
               if e["relation"] == "references" and label.get(e["source"]) == "f()"}
    assert targets == {field["id"]}

@pytest.mark.parametrize("statement", [
    "JsonValue = dict[str, object]\n",          # an alias by convention only
    "limit: int = 3\n",                          # an annotated variable
    "def f():\n    type Local = int\n",          # not module level
    "class C:\n    Inner: TypeAlias = int\n",    # not module level
])
def test_only_explicit_module_level_aliases_are_declarations(tmp_path: Path, statement: str):
    result = _extract(tmp_path, {"m.py": "from typing import TypeAlias\n\n" + statement})
    names = {"JsonValue", "limit", "Local", "Inner"}
    assert [n["label"] for n in result["nodes"] if n["label"] in names] == []
