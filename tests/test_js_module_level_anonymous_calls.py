"""Calls made directly inside a module-level anonymous closure, with no
enclosing NAMED function anywhere, must not be dropped (#3124, residual of
#1740).

#1740 fixed calls inside an anonymous callback by attributing them to the
enclosing NAMED function. That still leaves the case where the nearest
enclosing scope is itself anonymous -- `it("...", async () => { ... })` is
exactly this shape, and it hits test files hardest since that is the
idiomatic way to write one. #1740's own report text named the intended
fallback ("not attributed to the enclosing function, not to the module
node") but the module-node half was never implemented; this closes it by
attributing such calls to the file node, mirroring the #3408 fix that
already does this for `this.X = fn` member assignments found in the same
kind of statement.

Known remaining gap, not fixed here: a callee that is BOTH the target of a
direct import from the same file AND called only from a module-level
anonymous closure still does not resolve. The cross-file resolution pass
in `extract.py` dedupes strictly by (source, target) pair regardless of
relation, so the file node's own `imports`/`imports_from` edge to that
target pre-empts the `calls` edge from ever being added -- a NAMED
function's calls never collide this way because imports are always
attributed to the file node, never to a function node, so this collision
is specific to a caller that IS the file node. See
`test_direct_import_collision_is_a_known_remaining_gap` below.
"""
from __future__ import annotations

from graphify.extract import extract


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


def test_same_file_call_inside_anonymous_top_level_closure_is_captured(tmp_path):
    calls, _, _ = _extract(tmp_path, {
        "spec.ts": (
            "function helper(x: number) { return x; }\n"
            "declare function it(n: string, f: () => unknown): void;\n"
            "it(\"does the thing\", async () => {\n"
            "  helper(1);\n"
            "});\n"
        ),
    })
    assert ("spec.ts", "helper()") in calls, \
        f"call inside a module-level anonymous closure dropped; calls={sorted(calls)}"


def test_nested_anonymous_closures_both_attribute_to_the_file_node(tmp_path):
    # The exact repro shape from #3124: an anonymous callback (`it(...)`)
    # containing ANOTHER anonymous callback (`register(...)`) whose body
    # makes the real call. Neither has a named enclosing function anywhere.
    calls, _, _ = _extract(tmp_path, {
        "spec.ts": (
            "function helper(x: number) { return x; }\n"
            "declare function it(n: string, f: () => unknown): void;\n"
            "declare function register(p: string, h: (c: number) => unknown): void;\n"
            "it(\"does the thing\", async () => {\n"
            "  register(\"/a\", async (c) => { return helper(c); });\n"
            "});\n"
        ),
    })
    assert ("spec.ts", "helper()") in calls, \
        f"call inside doubly-nested anonymous closures dropped; calls={sorted(calls)}"


def test_named_enclosing_function_case_is_unaffected(tmp_path):
    # #1740's own fix must keep working unchanged: a call inside an anonymous
    # callback that DOES have a named enclosing function attributes to that
    # function, not to the file node.
    calls, _, _ = _extract(tmp_path, {
        "spec.ts": (
            "function helper(x: number) { return x; }\n"
            "declare function register(p: string, h: (c: number) => unknown): void;\n"
            "export function makeApp() {\n"
            "  register(\"/a\", async (c) => { return helper(c); });\n"
            "}\n"
        ),
    })
    assert ("makeApp()", "helper()") in calls
    assert ("spec.ts", "helper()") not in calls


def test_direct_import_collision_is_a_known_remaining_gap(tmp_path):
    """Documents the limitation described in this module's docstring: when
    the callee is BOTH directly imported by the same file AND only called
    from a module-level anonymous closure, the file node already has an
    `imports` edge to it, and the cross-file resolution pass's (source,
    target) dedup (relation-blind) silently drops the `calls` edge. This is
    a pre-existing limitation of that dedup, exposed here because the file
    node is now a valid `calls` source for the first time -- a NAMED
    function caller never collides this way, since imports are always
    attributed to the file node, never to a function node."""
    calls, _, _ = _extract(tmp_path, {
        "helper.ts": "export function helper(x: number) { return x; }\n",
        "spec.ts": (
            "import { helper } from './helper';\n"
            "declare function it(n: string, f: () => unknown): void;\n"
            "it(\"does the thing\", async () => {\n"
            "  helper(1);\n"
            "});\n"
        ),
    })
    # Documents current behavior (the gap), not the desired end state.
    assert ("spec.ts", "helper()") not in calls
