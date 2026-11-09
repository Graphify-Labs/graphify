"""A JS/TS function nested inside another (#2653) went into the file-wide name
map, so a call to that name from anywhere in the file could bind to it: two
functions with their own `run` both called the last one, and a top-level or
imported `helper` lost its callers to an unrelated inner `helper`.
"""
from __future__ import annotations

from graphify.extract import extract


def _calls(tmp_path, files):
    paths = []
    for name, code in files.items():
        f = tmp_path / name
        f.write_text(code, encoding="utf-8")
        paths.append(f)
    result = extract(sorted(paths), root=tmp_path)
    return {(e["source"], e["target"], e["relation"]) for e in result["edges"]
            if e["relation"] in ("calls", "indirect_call")}


def test_same_inner_name_in_two_functions_binds_to_its_own(tmp_path):
    edges = _calls(tmp_path, {"x.ts": (
        "export function first() { function run() { return 1; } register(run); return run(); }\n"
        "export function second() { function run() { return 2; } register(run); return run(); }\n"
        "function register(f: any) { return f; }\n"
    )})
    assert ("x_first", "x_first_run", "calls") in edges
    assert ("x_second", "x_second_run", "calls") in edges
    assert ("x_first", "x_first_run", "indirect_call") in edges
    assert ("x_second", "x_second_run", "indirect_call") in edges
    assert not {e for e in edges if e[0] == "x_first" and e[1] == "x_second_run"}
    assert not {e for e in edges if e[0] == "x_second" and e[1] == "x_first_run"}


def test_inner_function_does_not_take_a_top_level_functions_callers(tmp_path):
    edges = _calls(tmp_path, {"x.ts": (
        "export function helper() { return 0; }\n"
        "export function a() { function helper() { return 1; } return helper(); }\n"
        "export function b() { return helper(); }\n"
    )})
    assert ("x_a", "x_a_helper", "calls") in edges
    assert ("x_b", "x_helper", "calls") in edges
    assert ("x_b", "x_a_helper", "calls") not in edges


def test_inner_function_does_not_take_an_imported_functions_callers(tmp_path):
    edges = _calls(tmp_path, {
        "lib.ts": "export function helper() { return 0; }\n",
        "x.ts": (
            'import { helper } from "./lib";\n'
            "export function a() { function helper() { return 1; } return helper(); }\n"
            "export function b() { return helper(); }\n"
        ),
    })
    assert ("x_b", "lib_helper", "calls") in edges
    assert ("x_b", "x_a_helper", "calls") not in edges


def test_siblings_and_deeper_inner_functions_still_resolve(tmp_path):
    edges = _calls(tmp_path, {"x.js": (
        "function outer() {\n"
        "  function load() { return parse(); }\n"
        "  function parse() {\n"
        "    function step() { return load(); }\n"
        "    return step();\n"
        "  }\n"
        "  return load();\n"
        "}\n"
    )})
    assert ("x_outer", "x_outer_load", "calls") in edges
    assert ("x_outer_load", "x_outer_parse", "calls") in edges
    assert ("x_outer_parse", "x_outer_parse_step", "calls") in edges
    assert ("x_outer_parse_step", "x_outer_load", "calls") in edges


def test_arrow_components_keep_their_own_inner_functions(tmp_path):
    edges = _calls(tmp_path, {"Panels.tsx": (
        "export const Left = () => { function onClick() { return 1; } return onClick(); };\n"
        "export const Right = () => { function onClick() { return 2; } return onClick(); };\n"
    )})
    assert ("panels_left", "panels_left_onclick", "calls") in edges
    assert ("panels_right", "panels_right_onclick", "calls") in edges
    assert ("panels_left", "panels_right_onclick", "calls") not in edges
