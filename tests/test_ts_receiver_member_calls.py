"""TS/JS receiver-typed member calls beyond `this.field` (#1630).

The #1316 resolver handled `this.injectedField.method()`. This adds two receiver
tiers whose type is statically known but was previously dropped, so
`affected <method>` silently under-reported:

  A. a local `const x = new Foo()` binding, then `x.method()`;
  B. a closure over a type-annotated parameter, `f(x: Foo) => () => x.method()`.

Resolution is by receiver type with the single-definition guard; an untyped or
non-bare-typed receiver produces no edge.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract

_SVC = "export class Svc {\n  doThing(): number { return 1; }\n}\n"


def _calls(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    # Real-CLI shape: absolute input paths + a graphify-out cache subdir.
    r = extract([tmp_path / n for n in files], cache_root=tmp_path / "graphify-out")
    lbl = {n["id"]: n["label"] for n in r["nodes"]}
    return {(lbl.get(e["source"]), lbl.get(e["target"])) for e in r["edges"]
            if e["relation"] == "calls"}, r


def test_local_new_binding_receiver(tmp_path):
    calls, _ = _calls(tmp_path, {
        "svc.ts": _SVC,
        "direct.ts": ('import { Svc } from "./svc";\nconst s = new Svc();\n'
                      "export function usesDirect(): number { return s.doThing(); }\n"),
    })
    assert any("usesDirect" in s and "doThing" in t for s, t in calls)


def test_closure_over_typed_param_receiver(tmp_path):
    calls, _ = _calls(tmp_path, {
        "svc.ts": _SVC,
        "closure.ts": ('import { Svc } from "./svc";\n'
                       "export function register(svc: Svc): () => number "
                       "{ return () => svc.doThing(); }\n"),
    })
    assert any("register" in s and "doThing" in t for s, t in calls)


def test_new_binding_resolves_to_correct_class_under_ambiguity(tmp_path):
    calls, r = _calls(tmp_path, {
        "svc.ts": _SVC,
        "cache.ts": "export class Cache {\n  doThing(): number { return 2; }\n}\n",
        "d.ts": ('import { Svc } from "./svc";\nconst s = new Svc();\n'
                 "export function f(): number { return s.doThing(); }\n"),
    })
    # must resolve to Svc.doThing (id contains svc), never Cache.doThing
    tgts = [t for _s, t in [(e["source"], e["target"]) for e in r["edges"]
                            if e["relation"] == "calls" and "_f" in e["source"]]]
    assert tgts and all("svc" in t.lower() for t in tgts)
    assert not any("cache" in t.lower() for t in tgts)


def test_untyped_param_receiver_emits_no_edge(tmp_path):
    calls, _ = _calls(tmp_path, {
        "svc.ts": _SVC,
        "n.ts": "export function g(x): number { return x.doThing(); }\n",
    })
    assert not any("doThing" in t for _s, t in calls)


def test_array_typed_receiver_emits_no_edge(tmp_path):
    calls, _ = _calls(tmp_path, {
        "svc.ts": _SVC,
        "a.ts": ('import { Svc } from "./svc";\n'
                 "export function h(xs: Svc[]): number { return xs[0].doThing(); }\n"),
    })
    assert not any("h(" in s and "doThing" in t for s, t in calls)
