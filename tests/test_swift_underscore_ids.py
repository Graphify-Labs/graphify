"""Swift methods whose names differ only by a leading `_` or by case keep their own ids.

``make_id`` drops a leading ``_`` and folds case, so ``_bar()`` / ``bar()`` (and
``run()`` / ``Run()``) of one type minted one node id: the second declaration
vanished and its calls were credited to its twin. A type's class body and its
same-file extensions share one id space, so they are grouped together. The
Python/C#/Solidity/Java rule applies (#3302, #4415, #5058, #5151): the one
public name keeps its id, the others are salted.
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
    func bar() { helper() }
    func _bar() { other() }
    func helper() {}
    func other() {}
    func Run() {}
    func caller() { _bar(); bar(); run(); Run() }
}

extension Foo {
    func run() { helper() }
}

class User {
    let foo: Foo = Foo()
    func use() { foo._bar(); foo.bar() }
}
"""


def test_underscore_twin_keeps_its_own_node_and_calls(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"Sources/Foo.swift": FOO})
    ids = _ids_by_label(result, "Foo.swift")
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


def test_typed_receiver_calls_reach_each_twin(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"Sources/Foo.swift": FOO})
    ids = _ids_by_label(result, "Foo.swift")
    bar, ubar, use = _one(ids, ".bar()"), _one(ids, "._bar()"), _one(ids, ".use()")
    calls = _calls(result)
    assert (use, bar) in calls and (use, ubar) in calls


def test_case_only_twin_in_an_extension_is_kept(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"Sources/Foo.swift": FOO})
    ids = _ids_by_label(result, "Foo.swift")
    run, Run, helper, caller = (_one(ids, ".run()"), _one(ids, ".Run()"),
                                _one(ids, ".helper()"), _one(ids, ".caller()"))
    assert run != Run
    calls = _calls(result)
    assert (run, helper) in calls and (Run, helper) not in calls
    assert (caller, run) in calls and (caller, Run) in calls


USER = """class Client {
    let foo: Foo = Foo()
    func useBar() { foo.bar() }
    func useUnderscoreBar() { foo._bar() }
}
"""


def test_cross_file_typed_receiver_binds_the_exact_twin(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"Sources/Foo.swift": FOO, "Sources/Client.swift": USER})
    ids = _ids_by_label(result, "Foo.swift")
    bar, ubar = _one(ids, ".bar()"), _one(ids, "._bar()")
    client = _ids_by_label(result, "Client.swift")
    use_bar, use_ubar = _one(client, ".useBar()"), _one(client, ".useUnderscoreBar()")
    calls = _calls(result)
    assert (use_bar, bar) in calls and (use_ubar, ubar) in calls
    assert (use_bar, ubar) not in calls and (use_ubar, bar) not in calls
