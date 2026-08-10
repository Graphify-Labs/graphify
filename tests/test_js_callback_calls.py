"""Calls inside a callback passed to a module-level call must not be dropped (#2552).

`export const handler = wrapper(async (req) => { helperA(); })` has a
`call_expression` initializer, so `_js_extra_walk` took the const-literal branch
and never tracked the callback's body — `walk_calls` never descended into it and
the `helperA()` call was lost. The fix tracks each TOPMOST closure in such an
initializer under the const's nid, so its calls flow through the normal
machinery (import-evidence gate included).

The composition test guards the #2552/#2553 coupling: the newly-walked callback
body feeds member calls into `_resolve_typescript_member_calls`, whose origin
gate (#2553) must keep a third-party-typed receiver from fabricating an edge to
an unrelated local class.

#2568 (regression of the #2552 fix): the const-literal branch unioned ALL
sibling closures' params/locals under the one const nid, so a name that is a
LOCAL in sibling closure A wrongly suppressed a real `indirect_call` to that
same name in sibling closure B. The fix scopes each closure's bindings to its
own body (fed to walk_calls as extra_locals), so shadowing stays per-closure.
"""
from __future__ import annotations

from graphify.extract import extract

_HELPERS = "export function helperA(): number { return 1; }\n"


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    r = extract([tmp_path / n for n in files],
                cache_root=tmp_path / "graphify-out", parallel=False)
    lbl = {n["id"]: n["label"] for n in r["nodes"]}
    calls = {(lbl.get(e["source"]), lbl.get(e["target"])) for e in r["edges"]
             if e["relation"] == "calls"}
    return calls, lbl, r


_HANDLER = ("import { helperA } from './helpers';\n"
            "function wrapper(fn: (req: unknown) => Promise<number>) { return fn; }\n"
            "export const handler = wrapper(async (req) => { return helperA(); });\n"
            "export function control(): number { return helperA(); }\n")


def test_callback_body_calls_are_captured(tmp_path):
    calls, _, _ = _extract(tmp_path, {
        "helpers.ts": _HELPERS,
        "handler.ts": _HANDLER,
    })
    assert ("handler", "helperA()") in calls, \
        f"callback body call dropped; calls={sorted(calls)}"
    # control: a plain named-function caller in the same file is unaffected
    assert ("control()", "helperA()") in calls


def test_callback_body_call_is_not_double_counted(tmp_path):
    _, lbl, r = _extract(tmp_path, {
        "helpers.ts": _HELPERS,
        "handler.ts": _HANDLER,
    })
    n = sum(1 for e in r["edges"]
            if e["relation"] == "calls"
            and lbl.get(e["source"]) == "handler"
            and lbl.get(e["target"]) == "helperA()")
    assert n == 1, f"expected exactly one handler -> helperA calls edge, got {n}"


def test_callback_member_call_is_origin_gated(tmp_path):
    # Coupling guard: #2552 makes the callback body visible to the member-call
    # resolver; #2553's origin gate must then block the name-only `Repo` match
    # (third-party type) while the import-evidenced helperA() call resolves.
    calls, lbl, r = _extract(tmp_path, {
        "helpers.ts": _HELPERS,
        "fileb.ts": "export class Repo {\n  save(): void {}\n}\n",
        "h.ts": ("import { helperA } from './helpers';\n"
                 "import type { Repo } from 'external-pkg';\n"
                 "function wrapper(fn: (repo: Repo) => void) { return fn; }\n"
                 "export const h = wrapper((repo: Repo) => "
                 "{ repo.save(); helperA(); });\n"),
    })
    assert ("h", "helperA()") in calls, \
        f"import-evidenced callback call must resolve; calls={sorted(calls)}"
    sf = {n["id"]: str(n.get("source_file", "")) for n in r["nodes"]}
    fabricated = [e for e in r["edges"]
                  if e["relation"] in ("calls", "references", "indirect_call")
                  and sf.get(e["source"], "").endswith("h.ts")
                  and sf.get(e["target"], "").endswith("fileb.ts")]
    assert not fabricated, \
        f"third-party-typed receiver fabricated edge(s) to local Repo: {fabricated}"


def _indirect(r, lbl):
    return [(lbl.get(e["source"]), lbl.get(e["target"])) for e in r["edges"]
            if e["relation"] == "indirect_call"]


def test_sibling_closure_param_does_not_suppress_indirect_call(tmp_path):
    # #2568: closure 1's param `alpha` must not shadow closure 2's reference
    # to the module-level function `alpha` — each sibling closure tracked
    # under the const nid gets only its OWN bindings as scope.
    _, lbl, r = _extract(tmp_path, {
        "handler.ts": (
            "function alpha(x: unknown) { return x; }\n"
            "function wrapper(a: unknown, b: unknown) { return a || b; }\n"
            "export const handler = wrapper(\n"
            "  (alpha) => { return alpha; },\n"
            "  (pool) => { pool.submit(alpha); });\n"),
    })
    indirect = _indirect(r, lbl)
    assert ("handler", "alpha()") in indirect, \
        f"sibling closure's param suppressed a real indirect_call; indirect={indirect}"


def test_own_closure_local_still_suppresses_indirect_call(tmp_path):
    # A binding in the SAME closure still shadows the module function — the
    # per-body scoping must not drop genuine suppression.
    _, lbl, r = _extract(tmp_path, {
        "handler.ts": (
            "function alpha(x: unknown) { return x; }\n"
            "function wrapper(a: unknown, b: unknown) { return a || b; }\n"
            "export const handler = wrapper(\n"
            "  (beta) => beta,\n"
            "  (pool) => { const alpha = pool.get(); pool.submit(alpha); });\n"),
    })
    to_alpha = [p for p in _indirect(r, lbl) if p[1] == "alpha()"]
    assert not to_alpha, \
        f"closure's own local `alpha` must shadow the module fn; got {to_alpha}"


def test_shadow_and_reference_split_across_siblings(tmp_path):
    # Closure 1 passes its OWN param `alpha` (no edge); closure 2 references
    # the module `alpha` (one edge). Exactly one indirect_call to alpha.
    _, lbl, r = _extract(tmp_path, {
        "handler.ts": (
            "function alpha(x: unknown) { return x; }\n"
            "function wrapper(a: unknown, b: unknown) { return a || b; }\n"
            "const q: unknown[] = [];\n"
            "export const handler = wrapper(\n"
            "  (alpha) => { q.push(alpha); },\n"
            "  (pool) => { pool.submit(alpha); });\n"),
    })
    to_alpha = [p for p in _indirect(r, lbl) if p[1] == "alpha()"]
    assert to_alpha == [("handler", "alpha()")], \
        f"expected exactly one handler -> alpha indirect_call, got {to_alpha}"


def test_multi_closure_direct_calls_still_captured(tmp_path):
    # #2552 guard for the multi-closure shape: a direct call inside the first
    # of two sibling closures still yields a `calls` edge from the const.
    calls, _, _ = _extract(tmp_path, {
        "helpers.ts": _HELPERS,
        "handler.ts": (
            "import { helperA } from './helpers';\n"
            "function wrapper(a: unknown, b: unknown) { return a || b; }\n"
            "export const handler = wrapper(\n"
            "  (a) => { helperA(); },\n"
            "  (b) => b);\n"),
    })
    assert ("handler", "helperA()") in calls, \
        f"direct call in first sibling closure dropped; calls={sorted(calls)}"


def test_unreferenced_module_name_fabricates_nothing(tmp_path):
    # No fabrication: a sibling param named after a module callable, with the
    # module name never referenced in an emission position, yields no
    # indirect_call to it.
    _, lbl, r = _extract(tmp_path, {
        "handler.ts": (
            "function alpha(x: unknown) { return x; }\n"
            "function wrapper(a: unknown, b: unknown) { return a || b; }\n"
            "export const handler = wrapper(\n"
            "  (alpha) => alpha + 1,\n"
            "  (pool) => pool.drain());\n"),
    })
    to_alpha = [p for p in _indirect(r, lbl) if p[1] == "alpha()"]
    assert not to_alpha, f"fabricated indirect_call(s) to alpha: {to_alpha}"
