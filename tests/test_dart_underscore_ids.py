"""Dart functions whose names differ only by a leading `_` keep their own ids.

The Dart extractor scopes a function's id to its file (``stem_name``) and
``make_id`` drops a leading ``_``, so the library-private ``_bar()`` and
``bar()`` of one file minted one node id: the second declaration vanished and
the references it makes were credited to its twin. The Python/C#/Solidity/Java
rule applies (#3302, #4415, #5058, #5151): the one public name keeps its id,
the others are salted.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path: Path, files: dict[str, str]) -> dict:
    paths = []
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        paths.append(p)
    return extract(paths, cache_root=tmp_path, root=tmp_path)


def _ids_by_label(result: dict, source_file: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for n in result["nodes"]:
        if str(n.get("source_file", "")).endswith(source_file):
            out.setdefault(n["label"], []).append(n["id"])
    return out


def _one(ids: dict[str, list[str]], label: str) -> str:
    assert len(ids.get(label, [])) == 1, (label, ids.get(label))
    return ids[label][0]


def _edges(result: dict, relation: str) -> set[tuple[str, str]]:
    return {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == relation}


FOO = """class Foo {
  void bar() { ref.watch(helperProvider); }
  void _bar() { ref.watch(otherProvider); }
  void helper() {}
}

class Other {
  void _helper() { context.push('/home'); }
}
"""


def test_underscore_twin_keeps_its_own_node_and_edges(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"lib/foo.dart": FOO})
    ids = _ids_by_label(result, "foo.dart")
    bar, ubar = _one(ids, "bar"), _one(ids, "_bar")
    assert bar != ubar
    # The one public name keeps the plain id.
    assert bar == "lib_foo_bar"
    refs = _edges(result, "references")
    helper_p = next(n["id"] for n in result["nodes"] if n["label"] == "helperProvider")
    other_p = next(n["id"] for n in result["nodes"] if n["label"] == "otherProvider")
    assert (bar, helper_p) in refs and (ubar, other_p) in refs
    assert (bar, other_p) not in refs and (ubar, helper_p) not in refs


def test_twins_in_different_classes_of_one_file_are_kept(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"lib/foo.dart": FOO})
    ids = _ids_by_label(result, "foo.dart")
    helper, uhelper = _one(ids, "helper"), _one(ids, "_helper")
    assert helper != uhelper
    route = next(n["id"] for n in result["nodes"] if n["label"] == "Route /home")
    nav = _edges(result, "navigates")
    assert (uhelper, route) in nav and (helper, route) not in nav


def test_name_with_no_twin_keeps_its_id(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"lib/foo.dart": "class A {\n  void _solo() {}\n}\n"})
    ids = _ids_by_label(result, "foo.dart")
    assert _one(ids, "_solo") == "lib_foo_solo"
