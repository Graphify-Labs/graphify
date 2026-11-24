"""Lua table-field functions whose names differ only by a leading `_` keep their own ids.

``make_id`` drops ``_`` and folds case, so ``function M._load()`` /
``function M.load()`` (or ``Runner:_start()`` / ``Runner:start()``) in one
file minted one node id: the second declaration vanished and its calls were
credited to its twin. The Python/C#/Java rule applies (#3302, #4415, #5151),
judged by the field name: the one public field keeps its id, the others are
salted.
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


FOO = """local M = {}
local Runner = {}

function M.bar() M.helper() end
function M._bar() M.other() end
function M.helper() end
function M.other() end

function Runner:start() self:helper() end
function Runner:_start() self:other() end
function Runner:helper() end
function Runner:other() end
function Runner:go() self:_start() self:start() end

function M.caller() M._bar() M.bar() end

return M
"""


def test_underscore_field_twin_keeps_its_own_node_and_calls(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"lua/foo.lua": FOO})
    ids = _ids_by_label(result, "foo.lua")
    bar, ubar = _one(ids, "M.bar()"), _one(ids, "M._bar()")
    helper, other, caller = _one(ids, "M.helper()"), _one(ids, "M.other()"), _one(ids, "M.caller()")
    assert bar != ubar
    # The one public field keeps the plain id; fields that collide with
    # nothing are untouched.
    assert bar.endswith("_foo_m_bar") and helper.endswith("_foo_m_helper")
    calls = _calls(result)
    assert (bar, helper) in calls and (ubar, other) in calls
    assert (bar, other) not in calls and (ubar, helper) not in calls
    assert (caller, bar) in calls and (caller, ubar) in calls


def test_colon_method_twins_are_both_kept(tmp_path: Path) -> None:
    result = _extract(tmp_path, {"lua/foo.lua": FOO})
    ids = _ids_by_label(result, "foo.lua")
    start, ustart, go = _one(ids, "Runner:start()"), _one(ids, "Runner:_start()"), _one(ids, "Runner:go()")
    assert start != ustart and start.endswith("_foo_runner_start")
    calls = _calls(result)
    assert (start, _one(ids, "Runner:helper()")) in calls
    assert (ustart, _one(ids, "Runner:other()")) in calls
    assert (go, start) in calls and (go, ustart) in calls


def test_dot_and_colon_spellings_of_one_field_stay_one_node(tmp_path: Path) -> None:
    src = "local M = {}\nfunction M.run() end\nfunction M:run() end\nfunction M:_run() end\nreturn M\n"
    ids = _ids_by_label(_extract(tmp_path, {"lua/foo.lua": src}), "foo.lua")
    run = ids.get("M.run()", []) + ids.get("M:run()", [])
    assert len(set(run)) == 1 and run[0].endswith("_foo_m_run")
    assert _one(ids, "M:_run()") != run[0]


def test_module_level_underscore_pair_keeps_its_ids(tmp_path: Path) -> None:
    # A bare `_x` / `x` pair is the module-level rule's (#2810): unchanged.
    src = "local function _x() end\nfunction x() end\nlocal M = {}\nfunction M.y() end\nreturn M\n"
    ids = _ids_by_label(_extract(tmp_path, {"lua/foo.lua": src}), "foo.lua")
    assert _one(ids, "_x()").endswith("_foo_x")
    assert _one(ids, "M.y()").endswith("_foo_m_y")
