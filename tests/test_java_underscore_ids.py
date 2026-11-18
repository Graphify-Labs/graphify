"""Java members whose names differ only by a leading `_` or by case keep their own ids.

``make_id`` drops a leading ``_`` and folds case, so ``_bar()`` / ``bar()`` (and
``run()`` / ``Run()``, or a constructor ``Widget()`` and a method ``widget()``)
in one class body minted one node id: the second declaration vanished and its
calls were credited to its twin. The Python/C#/Solidity rule applies (#3302,
#4415, #5058): the one public name keeps its id, the others are salted.
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


FOO = """package demo;

public class Foo {
    public void bar() { helper(); }
    private void _bar() { other(); }
    void helper() {}
    void other() {}
    void Run() {}
    void run() {}
    public void caller() { _bar(); bar(); run(); Run(); }
}
"""


def test_underscore_twin_keeps_its_own_node_and_calls(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"demo/Foo.java": FOO})
    ids = _ids_by_label(result, "Foo.java")
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


def test_case_only_twins_are_both_kept(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"demo/Foo.java": FOO})
    ids = _ids_by_label(result, "Foo.java")
    run, Run, caller = _one(ids, ".run()"), _one(ids, ".Run()"), _one(ids, ".caller()")
    assert run != Run
    calls = _calls(result)
    assert (caller, run) in calls and (caller, Run) in calls


def test_constructor_enum_and_interface_bodies(tmp_path: Path) -> None:
    src = """package demo;
public class Widget {
    Widget() { init(); }
    void widget() { tidy(); }
    void init() {}
    void tidy() {}
    enum Mode { A; void _go() {} void go() { _go(); } }
    interface Cb { void _x(); void X(); }
}
"""
    result = _extract(tmp_path, {"demo/Widget.java": src})
    ids = _ids_by_label(result, "Widget.java")
    ctor, method = _one(ids, ".Widget()"), _one(ids, ".widget()")
    go, ugo = _one(ids, ".go()"), _one(ids, "._go()")
    assert ctor != method and go != ugo
    assert _one(ids, "._x()") != _one(ids, ".X()")
    calls = _calls(result)
    assert (ctor, _one(ids, ".init()")) in calls
    assert (method, _one(ids, ".tidy()")) in calls
    # `go()` calls `_go()`, not itself.
    assert (go, ugo) in calls and (go, go) not in calls


def test_cross_file_receiver_calls_pick_the_right_twin(tmp_path: Path) -> None:
    user = """package demo;
public class User {
    void lower(Foo f) { f.run(); }
    void upper(Foo f) { f.Run(); }
}
"""
    result = _extract(tmp_path, {"demo/Foo.java": FOO, "demo/User.java": user})
    foo = _ids_by_label(result, "Foo.java")
    usr = _ids_by_label(result, "User.java")
    calls = _calls(result)
    assert (_one(usr, ".lower()"), _one(foo, ".run()")) in calls
    assert (_one(usr, ".upper()"), _one(foo, ".Run()")) in calls
    assert (_one(usr, ".lower()"), _one(foo, ".Run()")) not in calls
