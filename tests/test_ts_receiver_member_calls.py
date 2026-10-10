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


# ── Class fields (`this.field.m()` where the field is declared on the class, not
# injected through the constructor). NestJS / Angular / TypeORM services hold their
# collaborators this way; only constructor parameter properties were typed before.

def _caller_hits(calls, caller: str, callee: str = "doThing") -> bool:
    return any(s == f".{caller}()" and callee in t for s, t in calls)


def test_typed_class_fields_type_this_field_calls(tmp_path):
    calls, _ = _calls(tmp_path, {
        "svc.ts": _SVC,
        "k.ts": ('import { Svc } from "./svc";\n'
                 "export class K {\n"
                 "  protected plain: Svc;\n"
                 "  private maybe?: Svc | undefined;\n"
                 "  #hidden: Svc = new Svc();\n"
                 "  private made = new Svc();\n"
                 "  declare readonly declared: Svc;\n"
                 "  a(): number { return this.plain.doThing(); }\n"
                 "  b(): number { return this.maybe?.doThing() ?? 0; }\n"
                 "  c(): number { return this.#hidden.doThing(); }\n"
                 "  d(): number { return this.made.doThing(); }\n"
                 "  e(): number { return this.declared.doThing(); }\n"
                 "}\n"),
    })
    for caller in ("a", "b", "c", "d", "e"):
        assert _caller_hits(calls, caller), caller


def test_class_fields_the_table_cannot_type_emit_no_edge(tmp_path):
    calls, _ = _calls(tmp_path, {
        "svc.ts": _SVC,
        "other.ts": "export class Other {\n  doThing(): number { return 2; }\n}\n",
        "k.ts": ('import { Svc } from "./svc";\nimport { Other } from "./other";\n'
                 "export class K {\n"
                 "  static shared: Svc;\n"
                 "  many: Svc[];\n"
                 "  either: Svc | Other;\n"
                 "  boxed: Map<string, Svc>;\n"
                 "  a(): number { return this.shared.doThing(); }\n"
                 "  b(): number { return this.many.doThing(); }\n"
                 "  c(): number { return this.either.doThing(); }\n"
                 "  d(): number { return this.boxed.doThing(); }\n"
                 "}\n"),
    })
    for caller in ("a", "b", "c", "d"):
        assert not _caller_hits(calls, caller), caller


def test_class_field_of_an_unimported_type_emits_no_edge(tmp_path):
    # The #2553 origin gate still applies: `Svc` here is not the local class.
    calls, _ = _calls(tmp_path, {
        "svc.ts": _SVC,
        "k.ts": ('import type { Svc } from "external-pkg";\n'
                 "export class K {\n  repo: Svc;\n  a(): number { return this.repo.doThing(); }\n}\n"),
    })
    assert not _caller_hits(calls, "a")
# ── Same-named types: `Context` can be a class in one file and an interface or
# type in others. The caller's own import says which one `c: Context` means.

_CTX_CLASS = "export class Context {\n  header(): number { return 1; }\n}\n"
_CTX_IFACE = "export interface Context {\n  header(): number;\n}\n"


def _hits(calls, caller: str, callee: str = "header") -> bool:
    return any(caller in s and callee in t for s, t in calls)


def test_same_named_type_is_picked_by_the_callers_import(tmp_path):
    calls, r = _calls(tmp_path, {
        "context.ts": _CTX_CLASS,
        "jsx/context.ts": _CTX_IFACE,
        "router/node.ts": "export type Context = { header(): number };\n",
        "cookie.ts": ('import type { Context } from "./context";\n'
                      "export const setCookie = (c: Context): number => c.header();\n"),
    })
    nodes = {n["id"]: n for n in r["nodes"]}
    targets = [e["target"] for e in r["edges"]
               if e["relation"] == "calls" and "setCookie" in nodes[e["source"]]["label"]]
    # the class in ./context.ts, not the jsx interface or the router type alias
    assert len(targets) == 1, targets
    assert targets[0].endswith("context_context_header"), targets
    assert "jsx" not in targets[0] and "router" not in targets[0], targets


def test_same_named_type_the_import_cannot_decide_emits_no_edge(tmp_path):
    calls, _ = _calls(tmp_path, {
        "a/context.ts": _CTX_CLASS,
        "b/context.ts": _CTX_CLASS,
        "both.ts": ('import * as a from "./a/context";\nimport * as b from "./b/context";\n'
                    "type Context = a.Context;\n"
                    "export function both(c: Context): number { return c.header(); }\n"),
        "neither.ts": "export function neither(c: Context): number { return c.header(); }\n",
    })
    assert not _hits(calls, "both")
    assert not _hits(calls, "neither")


def test_a_public_call_never_binds_to_a_private_hash_method(tmp_path):
    # `_key()` folds `#newResponse` and `newResponse` together; a `#name` is only
    # reachable as `#name`, so `c.newResponse()` must not land on it.
    calls, _ = _calls(tmp_path, {
        "ctx.ts": ("export class Ctx {\n"
                   "  #newResponse(): number { return 1; }\n"
                   "  build(): number { return this.#newResponse(); }\n"
                   "}\n"),
        "use.ts": ('import { Ctx } from "./ctx";\n'
                   "export function make(c: Ctx): number { return c.newResponse(); }\n"),
    })
    assert not _hits(calls, "make", "newResponse")
