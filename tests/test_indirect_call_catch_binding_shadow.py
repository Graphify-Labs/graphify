"""`catch (e)` bindings must shadow indirect_call args — inside the clause only.

`_js_local_bound_names` collects a function's locals from parameters and
`variable_declarator` nodes. A `catch` clause binds its name through the clause's
own `parameter` field and is never wrapped in a `variable_declarator`, so the
handler's binding was absent from the shadow set guarding indirect_call argument
resolution: passing it on as a plain call argument (`handlers.get(e)`) read as an
unresolved by-name reference, resolved against the corpus-wide label index, and
fabricated an `indirect_call` edge (INFERRED, 0.8) to an unrelated same-named
callable. One-letter catch bindings make this land constantly against minified
bundles, which define a private function for nearly every letter.

The binding is scoped to the clause, so the fix folds it into `extra_locals` for
that subtree only (the channel #2241 added for untracked closures) rather than
into the function-wide set — a same-named module callable referenced *outside* the
catch block still resolves. These tests pin both halves of that, plus the ES2019
optional binding (`catch { }`), which is a real `catch_clause` with no `parameter`.
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


def _rels(r, relation):
    return {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == relation}


def test_catch_binding_emits_no_indirect_call(tmp_path):
    """Reported shape: a minified bundle's private `k` must not become a fabricated
    indirect_call target because an unrelated function names its catch binding `k`
    and passes it on."""
    r, nid = _extract_js_dir(tmp_path, {
        "vendor.min.js": "var Lib=function(){function k(a){return a}return{k:k}}();\n",
        "a.js": (
            "export function run(handlers) {\n"
            "  try { boom(); } catch (k) { handlers.get(k); }\n"
            "}\n"
        ),
    })
    indirect = _rels(r, "indirect_call")
    assert all(t != nid["k"] for _s, t in indirect)


def test_catch_binding_destructured_emits_no_indirect_call(tmp_path):
    """`catch ({ cause })` binds through the same field via a pattern — the
    destructured name must shadow too."""
    r, nid = _extract_js_dir(tmp_path, {
        "lib.js": "export function cause(){ return 1; }\n",
        "a.js": (
            "export function run(sink) {\n"
            "  try { boom(); } catch ({ cause }) { sink.push(cause); }\n"
            "}\n"
        ),
    })
    indirect = _rels(r, "indirect_call")
    assert all(t != nid["cause"] for _s, t in indirect)


def test_catch_binding_does_not_shadow_outside_its_block(tmp_path):
    """The binding is scoped to the clause: a same-named module callable referenced
    AFTER the try/catch must still resolve. Folding the name into the function-wide
    set instead of this subtree would suppress it."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function k(x){ return x; }\n"
        "export function run(pool) {\n"
        "  try { boom(); } catch (k) { log(k); }\n"
        "  pool.submit(k);\n"
        "}\n"
    )})
    indirect = _rels(r, "indirect_call")
    assert (nid["run"], nid["k"]) in indirect


def test_catch_genuine_reference_still_emits_indirect_call(tmp_path):
    """Widening the shadow set must not blanket-suppress indirect_call inside a catch
    block: a real by-name reference to an unshadowed callable still emits."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function handler(x){ return x; }\n"
        "export function run(pool) {\n"
        "  try { boom(); } catch (e) { pool.submit(handler); }\n"
        "}\n"
    )})
    indirect = _rels(r, "indirect_call")
    assert (nid["run"], nid["handler"]) in indirect


def test_optional_catch_binding_unaffected(tmp_path):
    """ES2019 `catch { }` is a real catch_clause with no `parameter` field — the
    `param is not None` guard keeps it from raising, and nothing is shadowed."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function handler(x){ return x; }\n"
        "export function run(pool) {\n"
        "  try { boom(); } catch { pool.submit(handler); }\n"
        "}\n"
    )})
    indirect = _rels(r, "indirect_call")
    assert (nid["run"], nid["handler"]) in indirect
