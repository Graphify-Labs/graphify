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
    r = extract([tmp_path / n for n in files],
                cache_root=tmp_path / "graphify-out", parallel=False)
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


# ── Origin gate (#2553) ──────────────────────────────────────────────────────
# A receiver typed as a THIRD-PARTY `Repo` must never bind, by name alone, to an
# unrelated local `class Repo` the caller's file neither defines nor imports.

_LOCAL_REPO = "export class Repo {\n  save(): void {}\n  static staticSave(): void {}\n}\n"


def _cross_file_edges(r, src_file: str, tgt_file: str):
    """Edges (any relation) whose source node lives in src_file and target in tgt_file."""
    sf = {n["id"]: str(n.get("source_file", "")) for n in r["nodes"]}
    # method nodes carry their own source_file; fall back to it for both ends
    return [e for e in r["edges"]
            if sf.get(e["source"], "").endswith(src_file)
            and sf.get(e["target"], "").endswith(tgt_file)]


def test_third_party_type_does_not_fabricate_edge_to_local_class(tmp_path):
    _, r = _calls(tmp_path, {
        "fileb.ts": _LOCAL_REPO,
        "filea.ts": ("import type { Repo } from 'external-pkg';\n"
                     "export class ReportService {\n"
                     "  constructor(private repo: Repo) {}\n"
                     "  run(): void { this.repo.save(); }\n"
                     "}\n"),
    })
    bad = [e for e in _cross_file_edges(r, "filea.ts", "fileb.ts")
           if e["relation"] in ("calls", "references", "indirect_call")]
    assert not bad, f"fabricated cross-file edge(s) to un-imported local Repo: {bad}"


def test_genuinely_imported_type_still_resolves_inferred(tmp_path):
    _, r = _calls(tmp_path, {
        "fileb.ts": _LOCAL_REPO,
        "filea.ts": ('import { Repo } from "./fileb";\n'
                     "export class ReportService {\n"
                     "  constructor(private repo: Repo) {}\n"
                     "  run(): void { this.repo.save(); }\n"
                     "}\n"),
    })
    lbl = {n["id"]: n["label"] for n in r["nodes"]}
    hits = [e for e in r["edges"]
            if e["relation"] == "calls"
            and "run" in lbl.get(e["source"], "") and "save" in lbl.get(e["target"], "")]
    assert hits, "imported receiver type must still resolve"
    # table-inferred receiver -> INFERRED (Swift/C#/Java tiering parity)
    assert all(e["confidence"] == "INFERRED" for e in hits)


def test_source_qualified_static_call_is_extracted(tmp_path):
    _, r = _calls(tmp_path, {
        "fileb.ts": _LOCAL_REPO,
        "filea.ts": ('import { Repo } from "./fileb";\n'
                     "export class ReportService {\n"
                     "  constructor(private repo: Repo) {}\n"
                     "  run(): void { Repo.staticSave(); }\n"
                     "}\n"),
    })
    lbl = {n["id"]: n["label"] for n in r["nodes"]}
    hits = [e for e in r["edges"]
            if e["relation"] == "calls"
            and "run" in lbl.get(e["source"], "")
            and "staticSave" in lbl.get(e["target"], "")]
    assert hits, "source-qualified Repo.staticSave() must resolve"
    assert all(e["confidence"] == "EXTRACTED" for e in hits)


def test_same_file_type_still_resolves(tmp_path):
    calls, _ = _calls(tmp_path, {
        "one.ts": (_LOCAL_REPO
                   + "const r = new Repo();\n"
                     "export function runLocal(): void { r.save(); }\n"),
    })
    assert any("runLocal" in s and "save" in t for s, t in calls)
