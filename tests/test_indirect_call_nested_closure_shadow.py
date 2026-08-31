"""Indirect-call argument shadowing across untracked JS/TS closures (#2241).

An inline arrow / function-expression argument that is not separately tracked
(`_tracked_body_ids`) has its calls attributed to the ENCLOSING named
function's `caller_nid` (#1630). But the closure's own parameters and locals
were never folded into that enclosing function's shadow set, so a call
argument inside the closure that happened to share a name with an unrelated
callable elsewhere in the corpus produced a fabricated `indirect_call` edge —
even though the identifier was, in fact, a local binding just one lexical
scope down (e.g. `rows.map((r) => c.get(r))`, where `r` is the arrow's own
parameter).

These tests pin the fix: the closure's own bindings now widen the shadow set
for calls made inside it, and only for that subtree. They also pin what must
NOT regress: a genuine by-name reference to a real, unshadowed callable still
emits `indirect_call` from inside the same kind of nested closure.

Out of scope here: a `for (const x of xs)` loop variable not wrapped in a
`variable_declarator` is a separate, pre-existing gap in the same shadow-set
computation, already addressed by #1985 — not retested here to avoid
overlapping that diff.
"""
import os
from pathlib import Path

import networkx as nx

from graphify.affected import affected_nodes
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


def test_untracked_arrow_param_shadow_emits_no_indirect_call(tmp_path):
    """Reported shape (#2241): a one-letter test helper `r` must not become a
    fabricated indirect_call target when an unrelated function's inline `.map`
    callback has its own parameter named `r`, later passed on as a plain call
    argument deeper in the arrow body."""
    r, nid = _extract_js_dir(tmp_path, {
        "round.test.ts": "const r = (v) => Math.round(v);\n",
        "report.ts": (
            "export function buildSheet(rows, cols) {\n"
            "  return rows.map((r) => {\n"
            "    const o = {};\n"
            "    for (const c of cols) o[c.label] = c.get(r);\n"
            "    return o;\n"
            "  });\n"
            "}\n"
        ),
    })
    indirect = _rels(r, "indirect_call")
    assert all(t != nid["r"] for _s, t in indirect)


def test_untracked_arrow_genuine_reference_still_emits_indirect_call(tmp_path):
    """The same nested-arrow shape must still capture a REAL by-name reference
    that is not shadowed by any enclosing local — widening the shadow set for
    untracked closures must not blanket-suppress indirect_call inside them."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function handler(x){ return x; }\n"
        "function via(rows, pool){\n"
        "  return rows.map((row) => {\n"
        "    pool.submit(handler);\n"
        "    return row;\n"
        "  });\n"
        "}\n"
    )})
    indirect = _rels(r, "indirect_call")
    assert (nid["via"], nid["handler"]) in indirect


def test_double_nested_untracked_closures_shadow_compounds(tmp_path):
    """Shadowing must compound through two levels of untracked inline
    closures: an outer arrow's own param and an independently-named inner
    arrow's own param must BOTH be recognized as local, however deep the
    call that references them sits."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function outer(){}\n"
        "function inner(){}\n"
        "function via(rows){\n"
        "  return rows.map((outer) => {\n"
        "    return [1].map((inner) => {\n"
        "      pool.submit(outer);\n"
        "      pool.submit(inner);\n"
        "      return 0;\n"
        "    });\n"
        "  });\n"
        "}\n"
    )})
    indirect = _rels(r, "indirect_call")
    assert all(t != nid["outer"] for _s, t in indirect)
    assert all(t != nid["inner"] for _s, t in indirect)


def test_tracked_const_arrow_param_shadow_still_emits_no_indirect_call(tmp_path):
    """A const-assigned arrow IS separately tracked (its own caller_nid, own
    local_bound_names) — this pre-existing path must be unaffected by the new
    extra_locals threading: a same-named param inside it still shadows."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function handler(){}\n"
        "const via = (pool, handler) => { pool.submit(handler); };\n"
    )})
    indirect = _rels(r, "indirect_call")
    assert all(t != nid["handler"] for _s, t in indirect)


def test_affected_excludes_shadowed_untracked_closure_caller(tmp_path):
    """Blast-radius traversal must not include a caller that only reached the
    target through the fabricated edge this fix removes."""
    r, nid = _extract_js_dir(tmp_path, {
        "round.test.ts": "const r = (v) => Math.round(v);\n",
        "report.ts": (
            "export function buildSheet(rows, cols) {\n"
            "  return rows.map((r) => {\n"
            "    const o = {};\n"
            "    for (const c of cols) o[c.label] = c.get(r);\n"
            "    return o;\n"
            "  });\n"
            "}\n"
        ),
    })
    g = nx.DiGraph()
    for n in r["nodes"]:
        g.add_node(n["id"], **n)
    for e in r["edges"]:
        g.add_edge(e["source"], e["target"], **e)
    affected = {h.node_id for h in affected_nodes(g, nid["r"])}
    assert nid["buildSheet"] not in affected


def test_untracked_arrow_param_shadow_stable_on_warm_cache(tmp_path):
    """The fix must hold on a warm-cache re-extraction, not just a cold run —
    the shadow set is recomputed from the AST each time, never itself cached,
    but the extracted edge set it feeds into is."""
    files = {
        "round.test.ts": "const r = (v) => Math.round(v);\n",
        "report.ts": (
            "export function buildSheet(rows, cols) {\n"
            "  return rows.map((r) => {\n"
            "    const o = {};\n"
            "    for (const c of cols) o[c.label] = c.get(r);\n"
            "    return o;\n"
            "  });\n"
            "}\n"
        ),
    }
    r_cold, nid_cold = _extract_js_dir(tmp_path, files)
    assert all(t != nid_cold["r"] for _s, t in _rels(r_cold, "indirect_call"))

    # Re-extract against the same tmp_path / cache_root: the second run reads
    # the warm AST cache for both unchanged files.
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r_warm = extract(
            [Path("src") / name for name in files],
            cache_root=Path(".cache"), parallel=False,
        )
    finally:
        os.chdir(old)
    nid_warm = {n["label"].rstrip("()"): n["id"] for n in r_warm["nodes"]}
    assert all(t != nid_warm["r"] for _s, t in _rels(r_warm, "indirect_call"))
