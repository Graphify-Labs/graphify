"""Elixir defs whose names differ only by `_`, by case or by `!`/`?` keep their own ids.

``make_id`` drops ``_``, ``!`` and ``?`` and folds case, so ``_bar`` / ``bar``,
``__schema__`` / ``schema`` or ``get`` / ``get!`` in one module minted one
node id: the second def vanished and its calls were credited to its twin.
The Python/C#/Java rule applies (#3302, #4415, #5151): the one plain name
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


FOO = """defmodule Foo do
  def bar, do: helper()
  def _bar, do: other()
  def get(x), do: helper()
  def get!(x), do: other()
  def __schema__(:fields), do: other()
  def __schema__(:source), do: other()
  def schema, do: helper()
  def valid?(x), do: other()
  def helper, do: :ok
  def other, do: :ok

  def caller do
    _bar()
    bar()
    get!(1)
  end
end
"""

BAZ = """defmodule Baz do
  def run do
    Foo.get!(1)
    Foo.get(1)
    Foo.__schema__(:fields)
    Foo.schema()
  end
end
"""


def test_underscore_twin_keeps_its_own_node_and_calls(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"lib/foo.ex": FOO})
    ids = _ids_by_label(result, "foo.ex")
    bar, ubar = _one(ids, "bar()"), _one(ids, "_bar()")
    helper, other, caller = _one(ids, "helper()"), _one(ids, "other()"), _one(ids, "caller()")
    assert bar != ubar
    # The one plain name keeps the plain id; defs that collide with nothing
    # (`valid?` alone) are untouched.
    assert bar.endswith("_foo_bar") and helper.endswith("_foo_helper")
    assert _one(ids, "valid?()").endswith("_foo_valid")
    calls = _calls(result)
    assert (bar, helper) in calls and (ubar, other) in calls
    assert (bar, other) not in calls and (ubar, helper) not in calls
    assert (caller, bar) in calls and (caller, ubar) in calls


def test_bang_and_dunder_twins_are_both_kept(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"lib/foo.ex": FOO})
    ids = _ids_by_label(result, "foo.ex")
    get, bang = _one(ids, "get()"), _one(ids, "get!()")
    schema, dunder = _one(ids, "schema()"), _one(ids, "__schema__()")
    assert get != bang and schema != dunder
    assert get.endswith("_foo_get") and schema.endswith("_foo_schema")
    calls = _calls(result)
    assert (get, _one(ids, "helper()")) in calls and (bang, _one(ids, "other()")) in calls
    assert (_one(ids, "caller()"), bang) in calls


def test_cross_module_calls_land_on_the_named_twin(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"lib/foo.ex": FOO, "lib/baz.ex": BAZ})
    ids = _ids_by_label(result, "foo.ex")
    run = _one(_ids_by_label(result, "baz.ex"), "run()")
    calls = _calls(result)
    for label in ("get()", "get!()", "schema()", "__schema__()"):
        assert (run, _one(ids, label)) in calls, label
