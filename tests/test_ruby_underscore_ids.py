"""Ruby methods whose names differ only by a leading `_` or by case keep their own ids.

``make_id`` drops a leading ``_`` and folds case, so ``_bar`` / ``bar`` (and
``_where!`` / ``where!``) in one class or module body minted one node id: the
second declaration vanished and its calls were credited to its twin. The
Python/C#/Java rule applies (#3302, #4415, #5151): the one public name keeps
its id, the others are salted.
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


FOO = """class Foo
  def bar
    helper
  end

  def _bar
    other
  end

  def helper; end
  def other; end

  def where!; helper; end
  def _where!; other; end

  class << self
    def make; end
    def _make; end
  end

  def caller
    _bar
    bar
    self._bar
  end
end
"""

BAZ = """require_relative "foo"

class Baz
  def run
    f = Foo.new
    f._bar
    f.bar
    Foo._make
    Foo.make
  end
end
"""


def test_underscore_twin_keeps_its_own_node_and_calls(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"lib/foo.rb": FOO})
    ids = _ids_by_label(result, "foo.rb")
    bar, ubar = _one(ids, ".bar()"), _one(ids, "._bar()")
    helper, other, caller = _one(ids, ".helper()"), _one(ids, ".other()"), _one(ids, ".caller()")
    assert bar != ubar
    # The one public name keeps the plain id; members that collide with
    # nothing are untouched.
    assert bar.endswith("_foo_bar") and helper.endswith("_foo_helper")
    calls = _calls(result)
    assert (bar, helper) in calls and (ubar, other) in calls
    assert (bar, other) not in calls and (ubar, helper) not in calls
    assert (caller, bar) in calls and (caller, ubar) in calls


def test_bang_and_singleton_twins_are_both_kept(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"lib/foo.rb": FOO})
    ids = _ids_by_label(result, "foo.rb")
    where, uwhere = _one(ids, ".where!()"), _one(ids, "._where!()")
    make, umake = _one(ids, ".make()"), _one(ids, "._make()")
    assert where != uwhere and make != umake
    assert where.endswith("_foo_where_bang") and make.endswith("_foo_make")
    calls = _calls(result)
    assert (where, _one(ids, ".helper()")) in calls
    assert (uwhere, _one(ids, ".other()")) in calls


def test_cross_file_calls_land_on_the_named_twin(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"lib/foo.rb": FOO, "lib/baz.rb": BAZ})
    ids = _ids_by_label(result, "foo.rb")
    run = _one(_ids_by_label(result, "baz.rb"), ".run()")
    calls = _calls(result)
    assert (run, _one(ids, "._bar()")) in calls and (run, _one(ids, ".bar()")) in calls
    assert (run, _one(ids, "._make()")) in calls and (run, _one(ids, ".make()")) in calls


def test_members_without_a_twin_keep_their_ids(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"lib/foo.rb": "class Foo\n  def bar; end\n  def baz; end\nend\n"})
    ids = _ids_by_label(result, "foo.rb")
    assert _one(ids, ".bar()").endswith("_foo_bar")
    assert _one(ids, ".baz()").endswith("_foo_baz")
