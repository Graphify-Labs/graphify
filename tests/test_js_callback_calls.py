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
