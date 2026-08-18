"""A single unparenthesised arrow parameter must shadow indirect_call args.

`_js_local_bound_names` read only the `parameters` field. tree-sitter gives an
arrow with ONE unparenthesised parameter a `parameter` field (singular) and no
`parameters` list node at all, so `x => sink(x)` contributed nothing to the shadow
set: `x` read as an unresolved by-name reference, resolved against the corpus-wide
label index, and fabricated an `indirect_call` edge (INFERRED, 0.8) to an
unrelated same-named callable. Minified bundles name nearly every private
function with a single letter and use this arrow form heavily, so the two collide
constantly.

This is the same singular/plural trap as `catch_clause.parameter`. The
parenthesised form was always handled, which is what makes the bug easy to miss:
`(x) => …` and `x => …` behaved differently.
"""
import os
from pathlib import Path

from graphify.extract import extract


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


def test_single_unparenthesised_arrow_param_emits_no_indirect_call(tmp_path):
    """The reported shape: a minified bundle's private `k` must not become a
    fabricated target because an arrow names its only parameter `k`."""
    r, nid = _extract_js_dir(tmp_path, {
        "vendor.min.js": "var Lib=function(){function k(a){return a}return{k:k}}();\n",
        "a.js": "function sink(f){ return f; }\nexport const run = k => sink(k);\n",
    })
    assert all(t != nid["k"] for _s, t in _indirect(r))


def test_parenthesised_arrow_param_still_shadows(tmp_path):
    """Control: the `parameters` path was already correct and must stay correct."""
    r, nid = _extract_js_dir(tmp_path, {
        "vendor.min.js": "var Lib=function(){function k(a){return a}return{k:k}}();\n",
        "a.js": "function sink(f){ return f; }\nexport const run = (k) => sink(k);\n",
    })
    assert all(t != nid["k"] for _s, t in _indirect(r))


def test_async_single_param_arrow_shadows(tmp_path):
    """`async x => …` is the same node with the same singular field."""
    r, nid = _extract_js_dir(tmp_path, {
        "vendor.min.js": "var Lib=function(){function k(a){return a}return{k:k}}();\n",
        "a.js": "function sink(f){ return f; }\nexport const run = async k => sink(k);\n",
    })
    assert all(t != nid["k"] for _s, t in _indirect(r))


def test_arrow_param_does_not_shadow_a_genuine_reference(tmp_path):
    """The parameter is scoped to its arrow: a same-named module callable
    referenced from a DIFFERENT function must still resolve."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function k(x){ return x; }\n"
        "function sink(f){ return f; }\n"
        "export const shadowed = k => sink(k);\n"
        "export function elsewhere(pool) { pool.submit(k); }\n"
    )})
    assert (nid["elsewhere"], nid["k"]) in _indirect(r)


def test_genuine_reference_inside_the_arrow_still_emits(tmp_path):
    """Widening the shadow set must not blanket-suppress inside arrows: an
    unshadowed callable referenced in the body still emits."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function handler(x){ return x; }\n"
        "export const run = pool => pool.submit(handler);\n"
    )})
    assert (nid["run"], nid["handler"]) in _indirect(r)
