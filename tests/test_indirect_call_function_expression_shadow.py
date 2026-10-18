"""An untracked `function (…) {…}` expression's bindings must shadow indirect_call args.

`walk_calls` gates its untracked-closure handling on
`config.function_boundary_types`, and that handler already names the type it
should receive:

    _JS_CLOSURE_TYPES = ("arrow_function", "function_expression")

But `function_expression` was absent from the JS and TS `function_boundary_types`
sets, so the gate never opened for one. An INLINE or NESTED expression's body was
walked with the ENCLOSING function's `extra_locals`, and its own parameters and
locals folded into nothing: a bare reference to one of them, passed on as a call
argument, read as an unresolved by-name reference and fabricated an
`indirect_call` edge (INFERRED, 0.8) to an unrelated same-named callable
elsewhere in the corpus.

Scope: a top-level `const f = function (…) {}` is tracked through its declarator
and already had its own shadow-set entry, so it was never affected — see
`test_top_level_const_function_expression_was_already_tracked`. The gap is the
untracked inline/nested forms.

That made the two callback forms disagree, which is what hid it:

    xs.some(k => sink(k))                  # arrow — shadowed, correct
    xs.some(function (k) { return sink(k) })  # function expression — fabricated

Minified bundles name nearly every private function with a single letter, and
`function (err, res) {…}` callbacks are pervasive in older JS, so the two collide
constantly. Same family as `catch_clause.parameter` and the single unparenthesised
arrow parameter: a binding form that never reached the shadow set.
"""
import os
from pathlib import Path

from graphify.extract import extract

VENDOR = "var Lib=function(){function k(a){return a}return{k:k}}();\n"


def _extract_js_dir(tmp_path, files: dict[str, str]):
    base = tmp_path / "src"
    base.mkdir()
    for name, body in files.items():
        (base / name).write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract(
            [Path("src") / name for name in files],
            cache_root=Path(".cache"), parallel=False,
        )
    finally:
        os.chdir(old)
    nid = {n["label"].rstrip("()"): n["id"] for n in r["nodes"]}
    return r, nid


def _indirect(r):
    return {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "indirect_call"}


def test_inline_function_expression_param_emits_no_indirect_call(tmp_path):
    """The reported shape: a minified bundle's private `k` must not become a
    fabricated target because an inline callback names its parameter `k`."""
    r, nid = _extract_js_dir(tmp_path, {
        "vendor.min.js": VENDOR,
        "a.js": "export function run(xs, m){ return xs.some(function (k) { return m.indexOf(k); }); }\n",
    })
    assert all(t != nid["k"] for _s, t in _indirect(r))


def test_named_function_expression_param_shadows(tmp_path):
    """A named function expression is the same node type and must behave alike."""
    r, nid = _extract_js_dir(tmp_path, {
        "vendor.min.js": VENDOR,
        "a.js": "export function run(xs, m){ return xs.some(function nm(k) { return m.indexOf(k); }); }\n",
    })
    assert all(t != nid["k"] for _s, t in _indirect(r))


def test_nested_const_function_expression_shadows(tmp_path):
    """Not only the inline-argument position: a `const` inside a function body
    binds no tracked symbol, so the expression stays untracked."""
    r, nid = _extract_js_dir(tmp_path, {
        "vendor.min.js": VENDOR,
        "a.js": "export function run(m){ const f = function (k) { return m.indexOf(k); }; return f(1); }\n",
    })
    assert all(t != nid["k"] for _s, t in _indirect(r))


def test_top_level_const_function_expression_was_already_tracked(tmp_path):
    """Boundary control: a MODULE-level `const f = function (…) {}` gets its own
    node and shadow-set entry through the declarator, so it never went through
    this gate and passes with and without the fix. Documents what is NOT the
    bug, so the scope of the change stays legible."""
    r, nid = _extract_js_dir(tmp_path, {
        "vendor.min.js": VENDOR,
        "a.js": "export const f = function (k) { return [].indexOf(k); };\n",
    })
    assert "f" in nid
    assert all(t != nid["k"] for _s, t in _indirect(r))


def test_function_expression_local_shadows(tmp_path):
    """Locals, not just parameters, are scoped to the expression's body."""
    r, nid = _extract_js_dir(tmp_path, {
        "vendor.min.js": VENDOR,
        "a.js": "export function run(m){ return [].map(function () { const k = 1; return m.get(k); }); }\n",
    })
    assert all(t != nid["k"] for _s, t in _indirect(r))


def test_arrow_callback_still_shadows(tmp_path):
    """Control: the arrow path was already correct and must stay correct."""
    r, nid = _extract_js_dir(tmp_path, {
        "vendor.min.js": VENDOR,
        "a.js": "export function run(xs, m){ return xs.some(k => m.indexOf(k)); }\n",
    })
    assert all(t != nid["k"] for _s, t in _indirect(r))


def test_same_named_reference_after_the_expression_still_resolves(tmp_path):
    """The bindings are scoped to the expression: a same-named module callable
    referenced AFTER it, in the enclosing function, must still resolve."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function k(x){ return x; }\n"
        "export function run(m){ [].map(function (z) { return z; }); return m.get(k); }\n"
    )})
    assert (nid["run"], nid["k"]) in _indirect(r)


def test_sibling_function_expression_param_does_not_leak(tmp_path):
    """Two function expressions in one initializer are SEPARATE scopes: the
    first one's parameter must not shadow the second one's body. This is the
    #2568 shape — several closures registered under one id — reached through
    the function-expression form rather than the arrow form."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function k(x){ return x; }\n"
        "function wrap(a, b){ return a || b; }\n"
        "export const handler = wrap(\n"
        "  function (k) { return k; },\n"
        "  function (pool) { return pool.submit(k); }\n"
        ");\n"
    )})
    assert (nid["handler"], nid["k"]) in _indirect(r)


def test_genuine_reference_inside_the_function_expression_still_emits(tmp_path):
    """Widening the shadow set must not blanket-suppress inside the body: an
    unshadowed callable referenced there still emits."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function handler(x){ return x; }\n"
        "export function run(xs){ return xs.map(function (pool) { return pool.submit(handler); }); }\n"
    )})
    assert (nid["run"], nid["handler"]) in _indirect(r)


def test_call_attribution_inside_the_expression_is_unchanged(tmp_path):
    """Adding a type to `function_boundary_types` must not change WHERE calls are
    attributed. Before, a function expression was not a boundary at all, so
    walk_calls recursed in normally; now it takes the boundary branch, which
    descends explicitly with the enclosing `caller_nid` (#1630/#1740). Both
    routes must land the call on the enclosing function, not drop it or
    re-parent it."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function helper(x){ return x; }\n"
        "export function run(xs){ return xs.map(function (row) { return helper(row); }); }\n"
    )})
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    assert (nid["run"], nid["helper"]) in calls


def test_typescript_function_expression_shadows(tmp_path):
    """The TS config carries its own copy of the set; both were missing the type."""
    base = tmp_path / "src"
    base.mkdir()
    (base / "vendor.min.ts").write_text(VENDOR)
    (base / "a.ts").write_text(
        "export function run(xs: number[], m: number[]): boolean {\n"
        "  return xs.some(function (k: number) { return m.indexOf(k) >= 0; });\n"
        "}\n"
    )
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path("src") / "vendor.min.ts", Path("src") / "a.ts"],
                    cache_root=Path(".cache"), parallel=False)
    finally:
        os.chdir(old)
    nid = {n["label"].rstrip("()"): n["id"] for n in r["nodes"]}
    assert all(t != nid["k"] for _s, t in _indirect(r))


def test_generator_function_expression_param_shadows(tmp_path):
    """A GENERATOR function expression (`function*(k){}`) must shadow its param
    the same way a plain function expression does — the type was in
    generator_function_declaration form only, so the expression form still
    fabricated the edge until generator_function joined the boundary set."""
    r, nid = _extract_js_dir(tmp_path, {
        "vendor.min.js": VENDOR,
        "a.js": "export function run(xs, m){ const g = function*(k){ yield m.indexOf(k); }; return g; }\n",
    })
    assert all(t != nid["k"] for _s, t in _indirect(r))


def test_tsx_function_expression_shadows(tmp_path):
    """`.tsx` derives its boundary set from the TS config by reference; assert the
    coupling so a future refactor that gives TSX its own literal can't silently
    regress the shadow."""
    base = tmp_path / "src"
    base.mkdir()
    (base / "vendor.min.tsx").write_text(VENDOR)
    (base / "a.tsx").write_text(
        "export function run(xs: number[], m: number[]) {\n"
        "  return xs.some(function (k: number) { return m.indexOf(k) >= 0; });\n"
        "}\n"
    )
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path("src") / "vendor.min.tsx", Path("src") / "a.tsx"],
                    cache_root=Path(".cache"), parallel=False)
    finally:
        os.chdir(old)
    nid = {n["label"].rstrip("()"): n["id"] for n in r["nodes"]}
    assert all(t != nid["k"] for _s, t in _indirect(r))
