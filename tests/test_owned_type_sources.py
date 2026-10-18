from pathlib import Path
from graphify.extract import extract


def run(tmp_path, sources):
    paths = []
    for name, text in sources.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        paths.append(p)
    return extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)


def triples(g):
    return {(e["source"], e["target"], e["relation"]) for e in g["edges"]}


def test_callback_local_method_preserved_named_function_local_omitted(tmp_path):
    g = run(
        tmp_path,
        {
            "base.ts": "export class Base {}\nexport interface Result {}\n",
            "local.ts": 'import {Base,Result} from "./base.js";\nexport function make() { class Hidden extends Base { method(): Result { return {}; } } return Hidden; }\nit("x", () => { class Visible extends Base { method(): Result { return {}; } } });\n',
        },
    )
    ids = {n["id"] for n in g["nodes"]}
    edges = triples(g)
    assert ("local_visible_method", "base_result", "references") in edges
    assert ("local_visible", "base_base", "inherits") in edges
    assert not any(e["source"] not in ids for e in g["edges"])
    assert not any("hidden" in e["source"] for e in g["edges"])


def test_same_basename_sources_do_not_suppress_other_callers(tmp_path):
    g = run(
        tmp_path,
        {
            "base.ts": "export class Base {}\nexport interface Result {}\n",
            "a/local.ts": 'import {Base,Result} from "../base.js";\nexport function make() { class Shared extends Base { method(): Result { return {}; } } return Shared; }\n',
            "b/local.ts": 'import {Base,Result} from "../base.js";\nit("x", () => { class Shared extends Base { method(): Result { return {}; } } });\n',
        },
    )
    ids = {n["id"] for n in g["nodes"]}
    edges = triples(g)
    assert ("b_local_shared_method", "base_result", "references") in edges
    assert ("b_local_shared", "base_base", "inherits") in edges
    assert not any(e["source"] not in ids for e in g["edges"])


def test_abstract_method_omissions_do_not_drop_concrete_method(tmp_path):
    g = run(
        tmp_path,
        {
            "base.ts": "export interface Result {}\n",
            "local.ts": 'import {Result} from "./base.js";\nexport abstract class Abstract { abstract method(): Result; concrete(): Result { return {}; } }\n',
        },
    )
    ids = {n["id"] for n in g["nodes"]}
    assert ("local_abstract_concrete", "base_result", "references") in triples(g)
    assert not any(e["source"] not in ids for e in g["edges"])
