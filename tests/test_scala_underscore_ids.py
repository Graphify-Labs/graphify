"""Scala methods whose names differ only by `_`, by case or by a setter's `_=` keep their own ids.

``make_id`` drops a leading ``_`` and a trailing ``_=`` and folds case, so
``_bar()`` / ``bar()``, ``forEach`` / ``foreach`` or a getter ``size`` and
its setter ``size_=`` in one type (or its companion object) minted one node
id: the second declaration vanished and its calls were credited to its twin.
The Python/C#/Java rule applies (#3302, #4415, #5151): the one public name
keeps its id, the others are salted.
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


def _calls(result: dict) -> set[tuple[str, str]]:
    return {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}


FOO = """class Foo {
  private var _size = 0
  def bar(): Unit = helper()
  def _bar(): Unit = other()
  def size: Int = count()
  def size_=(v: Int): Unit = other()
  def forEach(): Unit = helper()
  def foreach(): Unit = other()
  def helper(): Unit = {}
  def other(): Unit = {}
  def count(): Int = 1
  def caller(): Unit = { _bar(); bar(); this.foreach() }
}

object Foo {
  def make(): Foo = new Foo
  def Bar(): Foo = make()
}
"""


def test_underscore_twin_keeps_its_own_node_and_calls(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"src/Foo.scala": FOO})
    ids = _ids_by_label(result, "Foo.scala")
    bar, ubar = _one(ids, ".bar()"), _one(ids, "._bar()")
    helper, other, caller = _one(ids, ".helper()"), _one(ids, ".other()"), _one(ids, ".caller()")
    assert bar != ubar
    # `Bar` in the companion object shares the class's id space.
    assert _one(ids, ".Bar()") not in (bar, ubar)
    calls = _calls(result)
    assert (ubar, other) in calls and (ubar, helper) not in calls
    assert (caller, bar) in calls and (caller, ubar) in calls


def test_getter_keeps_its_id_and_setter_is_its_own_node(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"src/Foo.scala": FOO})
    ids = _ids_by_label(result, "Foo.scala")
    size, setter = _one(ids, ".size()"), _one(ids, ".size_=()")
    assert size != setter and size.endswith("_foo_size")
    calls = _calls(result)
    assert (size, _one(ids, ".count()")) in calls and (setter, _one(ids, ".other()")) in calls
    assert (size, _one(ids, ".other()")) not in calls


def test_case_only_twins_are_both_kept(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"src/Foo.scala": FOO})
    ids = _ids_by_label(result, "Foo.scala")
    upper, lower = _one(ids, ".forEach()"), _one(ids, ".foreach()")
    assert upper != lower
    calls = _calls(result)
    assert (upper, _one(ids, ".helper()")) in calls and (lower, _one(ids, ".other()")) in calls
    assert (_one(ids, ".caller()"), lower) in calls


def test_members_without_a_twin_keep_their_ids(tmp_path: Path) -> None:
    ids = _ids_by_label(_extract(tmp_path, {"src/Foo.scala": FOO}), "Foo.scala")
    assert _one(ids, ".helper()").endswith("_foo_helper")
    assert _one(ids, ".make()").endswith("_foo_make")
