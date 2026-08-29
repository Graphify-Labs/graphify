"""TS/JS/TSX `new Foo(...)` constructor calls emit `calls` edges (#3116).

In tree-sitter JS/TS, `new_expression` exposes its callee under the `constructor`
field rather than `function`. The generic path in `walk_calls` previously queried
only `call_function_field="function"`, dropping constructor calls.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract, extract_js


def _calls(tmp_path: Path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    r = extract([tmp_path / n for n in files],
                cache_root=tmp_path / "graphify-out", parallel=False)
    lbl = {n["id"]: n["label"] for n in r["nodes"]}
    calls = {(lbl.get(e["source"]), lbl.get(e["target"])) for e in r["edges"]
             if e["relation"] == "calls"}
    return calls, r


def test_ts_new_expression_emits_calls_edge_in_file(tmp_path: Path):
    calls, _ = _calls(tmp_path, {
        "main.ts": (
            "class Foo {\n"
            "  constructor(x: number) {}\n"
            "}\n"
            "function caller() {\n"
            "  const x = new Foo(1);\n"
            "}\n"
        )
    })
    assert any(s == "caller()" and t == "Foo" for s, t in calls)


def test_ts_new_expression_resolves_cross_file(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        "foo.ts": "export class Foo {}\n",
        "caller.ts": (
            'import { Foo } from "./foo";\n'
            "export function caller() {\n"
            "  const x = new Foo();\n"
            "}\n"
        ),
    })
    assert any(s == "caller()" and t == "Foo" for s, t in calls)
    cross_edges = [
        e for e in r["edges"]
        if e["relation"] == "calls"
        and "caller" in e["source"]
        and "foo" in e["target"].lower()
    ]
    assert len(cross_edges) == 1


def test_js_new_expression_emits_calls_edge(tmp_path: Path):
    calls, _ = _calls(tmp_path, {
        "app.js": (
            "class Service {}\n"
            "function init() {\n"
            "  const s = new Service();\n"
            "}\n"
        )
    })
    assert any(s == "init()" and t == "Service" for s, t in calls)


def test_tsx_new_expression_emits_calls_edge(tmp_path: Path):
    calls, _ = _calls(tmp_path, {
        "comp.tsx": (
            "class Widget {}\n"
            "function App() {\n"
            "  const w = new Widget();\n"
            "  return <div>{w}</div>;\n"
            "}\n"
        )
    })
    assert any(s == "App()" and t == "Widget" for s, t in calls)


def test_ts_member_new_expression_raw_calls(tmp_path: Path):
    file_path = tmp_path / "member.ts"
    file_path.write_text(
        "function caller() {\n"
        "  const s = new pkg.Foo();\n"
        "}\n",
        encoding="utf-8",
    )
    r = extract_js(file_path)
    assert any(
        rc["callee"] == "Foo"
        and rc.get("is_member_call") is True
        and rc.get("receiver") == "pkg"
        for rc in r.get("raw_calls", [])
    )
