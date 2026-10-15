"""#4475: JS/TS class members that differ only by `_`, `$` or `#` stay separate nodes."""
from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from graphify.extract import extract


def _extract(tmp_path: Path, files: dict[str, str]) -> dict:
    for name, src in files.items():
        (tmp_path / name).write_text(src, encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return extract([tmp_path / n for n in files], cache_root=tmp_path, parallel=False)


def _members(r: dict) -> dict[str, str]:
    return {n["label"]: n["id"] for n in r["nodes"] if n["label"].startswith(".")}


def _calls(r: dict) -> set[tuple[str, str]]:
    label = {n["id"]: n["label"] for n in r["nodes"]}
    return {(label.get(e["source"]), label.get(e["target"])) for e in r["edges"] if e["relation"] == "calls"}


@pytest.mark.parametrize("fname,src,expected", [
    ("a.js", "export class R { _onBegin(a) { return a; } onBegin(b) { return b; } }\n", {"._onBegin()", ".onBegin()"}),
    ("a.js", "export class W { #close(a) { return a; } close(b) { return this.#close(b); } }\n", {".#close()", ".close()"}),
    ("a.ts", "export declare class Q { $set(a: number): void; set(b: number): void; }\n", {".$set()", ".set()"}),
    ("a.js", "export class A {\n  updateHash() { return 1; }\n  _updateHash() { return 2; }\n}\n", {".updateHash()", "._updateHash()"}),
    ("a.ts", "export abstract class B { abstract _run(): void; abstract run(): void; }\n", {"._run()", ".run()"}),
    ("a.js", "export class F { _go = () => 1; go = () => 2; }\n", {"._go()", ".go()"}),
])
def test_issue_cases_get_two_nodes(tmp_path, fname, src, expected):
    assert expected <= set(_members(_extract(tmp_path, {fname: src})))


def test_public_member_keeps_the_plain_id_and_private_one_is_salted(tmp_path):
    m = _members(_extract(tmp_path, {"a.js": "export class W { #close(a) { return a; } close(b) { return b; } }\n"}))
    assert m[".close()"] == "a_w_close"
    assert m[".#close()"].startswith("a_w_close_") and m[".#close()"] != "a_w_close"


def test_order_does_not_matter(tmp_path):
    (tmp_path / "1").mkdir()
    (tmp_path / "2").mkdir()
    a = _members(_extract(tmp_path / "1", {"a.js": "export class A { _x() {} x() {} }\n"}))
    b = _members(_extract(tmp_path / "2", {"a.js": "export class A { x() {} _x() {} }\n"}))
    assert a == b


def test_no_public_member_salts_both(tmp_path):
    m = _members(_extract(tmp_path, {"a.js": "export class P { _x() { return 1; } $x() { return 2; } }\n"}))
    assert set(m) == {"._x()", ".$x()"}
    assert "a_p_x" not in m.values() and len(set(m.values())) == 2


def test_non_colliding_member_ids_unchanged(tmp_path):
    m = _members(_extract(tmp_path, {"a.ts": (
        "export class C {\n  run() {}\n  _helper() {}\n  #secret() {}\n  $id() {}\n"
        "  get size() { return 1; }\n  set size(v) {}\n  static make() {}\n"
        "  over(a: number): void;\n  over(a: string): void;\n  over(a: any) {}\n}\n")}))
    assert m == {".run()": "a_c_run", "._helper()": "a_c_helper", ".#secret()": "a_c_secret",
                 ".$id()": "a_c_id", ".size()": "a_c_size", ".make()": "a_c_make", ".over()": "a_c_over"}


def test_call_edges_go_to_the_right_member(tmp_path):
    r = _extract(tmp_path, {"w.js": (
        "export class W {\n  #close(a) { return helper(a); }\n  close(b) { return this.#close(b); }\n"
        "  shut() { return this.close(1); }\n}\nfunction helper(x) { return x; }\n")})
    calls = _calls(r)
    assert (".close()", ".#close()") in calls
    assert (".shut()", ".close()") in calls
    assert (".#close()", "helper()") in calls  # the private body's own call is credited to it
    assert (".close()", "helper()") not in calls


@pytest.mark.parametrize("call,target", [("a.updateHash()", ".updateHash()"), ("a._updateHash()", "._updateHash()")])
@pytest.mark.parametrize("cross_file", [False, True])
def test_callers_reach_the_right_member(tmp_path, call, target, cross_file):
    cls = "export class A {\n  updateHash() { return 1; }\n  _updateHash() { return 2; }\n}\n"
    fn = f"export function f() {{ const a = new A(); return {call}; }}\n"
    files = ({"a.js": cls, "u.js": "import { A } from './a.js';\n" + fn} if cross_file else {"a.js": cls + fn})
    members = {t for s, t in _calls(_extract(tmp_path, files)) if s == "f()" and t and t.startswith(".")}
    assert members == {target}


def test_cross_file_ts_typed_receiver_hits_each_member(tmp_path):
    r = _extract(tmp_path, {
        "ctx.ts": "export class Ctx {\n  set(v: number): void {}\n  $set(v: number): void {}\n}\n",
        "use.ts": ('import { Ctx } from "./ctx";\n'
                   "export function a(c: Ctx) { c.set(1); }\nexport function b(c: Ctx) { c.$set(1); }\n"),
    })
    calls = _calls(r)
    assert ("a()", ".set()") in calls and ("a()", ".$set()") not in calls
    assert ("b()", ".$set()") in calls and ("b()", ".set()") not in calls


def test_dedup_build_and_merge_keep_both(tmp_path):
    from graphify.build import build, build_merge
    from graphify.cluster import cluster
    from graphify.export import to_json
    src = {"a.js": "export class A {\n  close() { return this.#close(); }\n  #close() { return 1; }\n}\n"}
    r = _extract(tmp_path, src)
    G = build([r], dedup=True, root=str(tmp_path))
    labels = {G.nodes[n]["label"] for n in G.nodes}
    assert {".close()", ".#close()"} <= labels
    to_json(G, cluster(G), str(tmp_path / "graph.json"))
    G2 = build_merge([_extract(tmp_path, src)], graph_path=str(tmp_path / "graph.json"), root=str(tmp_path))
    assert set(G2.nodes) == set(G.nodes)



def test_pre_fix_ast_cache_entry_is_never_served_for_js(tmp_path):
    """JS/TS bypass the AST cache, so a collapsed entry left by an older run can't resurface (#4475)."""
    from graphify.cache import save_cached
    from graphify.extract import cache_salt, extract_js
    src = tmp_path / "a.js"
    src.write_text("export class A {\n  updateHash() { return 1; }\n  _updateHash() { return 2; }\n}\n", encoding="utf-8")
    stale = extract_js(src)
    stale["nodes"] = [n for n in stale["nodes"] if n.get("label") != "._updateHash()"]
    save_cached(src, stale, root=tmp_path, cache_root=tmp_path, kind="ast", salt=cache_salt(src))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = extract([src], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert {".updateHash()", "._updateHash()"} <= {n["label"] for n in r["nodes"]}
