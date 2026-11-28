"""C++ member functions whose names differ only by a `_`, a `~` or by case keep their own ids.

``make_id`` drops a leading or trailing ``_`` (and ``~``) and folds case, so in
one class body ``_bar()`` / ``bar()``, ``find()`` / ``find_()``, ``Run()`` /
``run()`` and a constructor ``Foo()`` / destructor ``~Foo()`` minted one node
id: the second declaration vanished and its calls were credited to its twin.
The Python/C#/Solidity/Java rule applies (#3302, #4415, #5058, #5151): the one
public name keeps its id, the others are salted. Overloads share one name on
purpose and stay one node.
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
public:
    Foo() { helper(); }
    ~Foo() { other(); }
    void bar() { helper(); }
    void _bar() { other(); }
    void find(int x) { helper(); }
    void find(double x) { helper(); }
    void find_(int x) { other(); }
    void Run() {}
    void run() {}
    void helper() {}
    void other() {}
    void caller() { _bar(); bar(); find(1); find_(1); run(); Run(); }
};

void use(Foo& foo) { foo._bar(); foo.find_(2); }
"""


def test_underscore_twin_keeps_its_own_node_and_calls(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"src/foo.cpp": FOO})
    ids = _ids_by_label(result, "foo.cpp")
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


def test_trailing_underscore_twin_and_overloads(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"src/foo.cpp": FOO})
    ids = _ids_by_label(result, "foo.cpp")
    # Both `find` overloads stay one node; `find_` is its own.
    find, find_ = _one(ids, ".find()"), _one(ids, ".find_()")
    other, caller, use = _one(ids, ".other()"), _one(ids, ".caller()"), _one(ids, "use()")
    assert find != find_ and find.endswith("_foo_find")
    calls = _calls(result)
    assert (find_, other) in calls and (find, other) not in calls
    assert (caller, find) in calls and (caller, find_) in calls
    assert (use, find_) in calls and (use, _one(ids, "._bar()")) in calls


def test_case_only_and_destructor_twins_are_kept(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"src/foo.cpp": FOO})
    ids = _ids_by_label(result, "foo.cpp")
    run, Run, caller = _one(ids, ".run()"), _one(ids, ".Run()"), _one(ids, ".caller()")
    ctor, dtor = _one(ids, ".Foo()"), _one(ids, ".~Foo()")
    assert run != Run and ctor != dtor
    calls = _calls(result)
    assert (caller, run) in calls and (caller, Run) in calls
    assert (dtor, _one(ids, ".other()")) in calls and (ctor, _one(ids, ".other()")) not in calls


HEADER = """class Foo {
public:
    void bar();
    void bar_();
    void helper();
    void other();
    void caller();
};
"""

SOURCE = """#include "foo.h"
void Foo::bar() { helper(); }
void Foo::bar_() { other(); }
void Foo::caller() { bar(); bar_(); }
"""


def test_split_header_calls_reach_each_twin(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"src/foo.h": HEADER, "src/foo.cpp": SOURCE})
    ids = _ids_by_label(result, "foo.h")
    bar, bar_, caller = _one(ids, ".bar()"), _one(ids, ".bar_()"), _one(ids, ".caller()")
    assert bar != bar_
    calls = _calls(result)
    assert (caller, bar) in calls and (caller, bar_) in calls
    assert (bar_, _one(ids, ".other()")) in calls and (bar, _one(ids, ".other()")) not in calls
