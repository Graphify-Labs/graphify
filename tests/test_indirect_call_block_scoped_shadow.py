"""A block-scoped `let`/`const` binding must not shadow indirect_call
references outside the block it is actually scoped to.

`_js_local_bound_names` collected `let`/`const` declarator targets (and a
`for`/`for-of` loop's own binding) into one FUNCTION-WIDE shadow set, but
both are block-scoped in JS, unlike `var` (function-scoped, hoisted). A
reference to a same-named module callable made OUTSIDE the block that binds
the name had its genuine indirect_call edge suppressed (#2822):

- a `const`/`let` declared inside any nested block (`if`, `try`, a bare `{}`)
- a `for...of`/`for...in` loop binding, referenced after the loop ends
- a closure that outlives the loop and still references the loop binding

`var` is exempt from all of this — it is genuinely function-scoped
regardless of how deeply it is nested, so a `var` with the same shapes must
still correctly shadow a same-named module callable everywhere in the
function, including outside the block/loop that declares it. And the #2606
fix (a loop binding shadows references INSIDE its own loop) must not
regress.
"""
import os
from pathlib import Path

from graphify.extract import extract, extract_js


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


def test_block_scoped_const_does_not_shadow_a_reference_outside_the_block(tmp_path):
    """Case 1 from the issue: a `const` declared inside an `if` block must not
    suppress a reference to a same-named module callable outside that block."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function k(x){ return x; }\n"
        "export function run(flag, p){\n"
        "  if (flag) { const k = 1; void k; }\n"
        "  return p.submit(k);\n"
        "}\n"
    )})
    assert (nid["run"], nid["k"]) in _indirect(r)


def test_for_of_binding_does_not_shadow_a_reference_after_the_loop(tmp_path):
    """Case 2 from the issue: referenced after the loop ends, not inside it."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function k(x){ return x; }\n"
        "export function run(p){ for (const k of [1]) void k; p.submit(k); }\n"
    )})
    assert (nid["run"], nid["k"]) in _indirect(r)


def test_for_of_binding_does_not_shadow_a_closure_that_outlives_the_loop(tmp_path):
    """Case 3 from the issue: a closure returned after the loop still refers
    to the module callable, not the loop's own binding."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function k(x){ return x; }\n"
        "export function run(p){ for (const k of [1]) void k; return () => p.submit(k); }\n"
    )})
    assert (nid["run"], nid["k"]) in _indirect(r)


def test_for_of_binding_still_shadows_a_reference_inside_its_own_loop(tmp_path):
    """Control from the issue (#2606 must not regress): a reference INSIDE the
    loop still refers to the loop's own binding, not the module callable."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function k(x){ return x; }\n"
        "export function run(p){ for (const k of [1]) p.submit(k); }\n"
    )})
    assert (nid["run"], nid["k"]) not in _indirect(r)


def test_c_style_for_let_still_shadows_a_reference_inside_its_own_loop(tmp_path):
    """A C-style `for (let i = ...)` binding shadows a reference inside the
    loop, exactly like for-of, while a reference to the same name outside the
    loop still correctly resolves. Both calls read identically as source
    text (`p.submit(k)`), so this asserts on `source_location` (the outside
    call, L4) rather than just edge presence -- a pair-membership check
    alone cannot distinguish "only the outside call resolved" from "both
    wrongly resolved"."""
    f = tmp_path / "a.js"
    f.write_text(
        "function k(x){ return x; }\n"
        "export function run(p){\n"
        "  for (let k = 0; k < 3; k++) { p.submit(k); }\n"
        "  return p.submit(k);\n"
        "}\n"
    )
    r = extract_js(f)
    indirect = [e for e in r["edges"] if e["relation"] == "indirect_call"]
    assert len(indirect) == 1, (
        f"expected exactly one indirect_call edge (the outside call only), got {indirect}"
    )
    assert indirect[0]["source_location"] == "L4", (
        "the resolved edge must be the outside-the-loop call, not the inside one"
    )


def test_var_inside_a_block_still_shadows_a_reference_outside_the_block(tmp_path):
    """var is genuinely function-scoped (hoisted): unlike the let/const case
    above, a var declared inside an if-block must still shadow a reference
    outside that block, everywhere in the function."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function k(x){ return x; }\n"
        "export function run(flag, p){\n"
        "  if (flag) { var k = 1; void k; }\n"
        "  return p.submit(k);\n"
        "}\n"
    )})
    assert (nid["run"], nid["k"]) not in _indirect(r)


def test_var_for_of_binding_still_shadows_a_reference_after_the_loop(tmp_path):
    """Same as above for a var-form for-of loop binding: hoisted, so it must
    still shadow a reference made after the loop ends."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function k(x){ return x; }\n"
        "export function run(p){ for (var k of [1]) void k; return p.submit(k); }\n"
    )})
    assert (nid["run"], nid["k"]) not in _indirect(r)


def test_genuine_reference_elsewhere_still_emits(tmp_path):
    """Widening the shadow scope must not blanket-suppress: a same-named
    callable referenced from a function that does not bind it at all still
    resolves."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function k(x){ return x; }\n"
        "export function run(flag, p){\n"
        "  if (flag) { const k = 1; void k; }\n"
        "  return p.submit(k);\n"
        "}\n"
        "export function elsewhere(pool) { pool.submit(k); }\n"
    )})
    assert (nid["elsewhere"], nid["k"]) in _indirect(r)
