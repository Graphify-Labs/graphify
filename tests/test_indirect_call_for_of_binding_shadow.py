"""A `for...of` / `for...in` loop binding must shadow indirect_call references.

`_js_local_bound_names` collected parameters and `variable_declarator` targets,
but the loop variable of `for (const entry of xs)` is the statement's `left`
pattern, NOT wrapped in a `variable_declarator`. So `entry` contributed nothing
to the shadow set: used in an object-shorthand argument (`push({ entry })`) it
read as an unresolved by-name reference, resolved against the corpus-wide label
index, and fabricated an INFERRED `indirect_call` edge to an unrelated same-named
module callable (#2606). A generic fixture/helper name then became a false
high-betweenness hub, distorting god-node and community analysis.

C-style `for (let i = 0; ...)` uses a `lexical_declaration` with real
declarators, which was always handled — the same declared/undeclared trap as the
single-arrow-parameter and catch-binding cases.
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


def test_for_of_binding_does_not_fabricate_indirect_call(tmp_path):
    """The reported shape: a `for...of` binding `entry` used in an
    object-shorthand argument must not resolve to an unrelated `entry()`."""
    r, nid = _extract_js_dir(tmp_path, {
        "declaration.mjs": (
            "export function entry(signature) {\n"
            "  return { signature };\n"
            "}\n"
            "export const fixture = entry(\"public.entry()\");\n"
        ),
        "consumer.mjs": (
            "export function findNamed(entries, lookup) {\n"
            "  const resolved = [];\n"
            "  for (const entry of entries) {\n"
            "    if (lookup(entry.name)) resolved.push({ entry });\n"
            "  }\n"
            "  return resolved;\n"
            "}\n"
        ),
    })
    assert (nid["findNamed"], nid["entry"]) not in _indirect(r)


def test_for_of_destructuring_binding_shadows(tmp_path):
    """A destructured loop binding (`for (const { entry } of xs)`) must shadow
    the same way — `_js_collect_pattern_idents` walks the pattern."""
    r, nid = _extract_js_dir(tmp_path, {
        "declaration.mjs": "export function entry(x) { return x; }\n",
        "consumer.mjs": (
            "export function findNamed(rows) {\n"
            "  const out = [];\n"
            "  for (const { entry } of rows) {\n"
            "    out.push({ entry });\n"
            "  }\n"
            "  return out;\n"
            "}\n"
        ),
    })
    assert (nid["findNamed"], nid["entry"]) not in _indirect(r)


def test_genuine_reference_outside_the_loop_still_emits(tmp_path):
    """Widening the shadow set must not blanket-suppress: a same-named callable
    referenced from a function that does NOT bind it in a loop still resolves."""
    r, nid = _extract_js_dir(tmp_path, {"a.js": (
        "function entry(x){ return x; }\n"
        "export function findNamed(rows) {\n"
        "  const out = [];\n"
        "  for (const entry of rows) { out.push({ entry }); }\n"
        "  return out;\n"
        "}\n"
        "export function elsewhere(pool) { pool.submit(entry); }\n"
    )})
    assert (nid["elsewhere"], nid["entry"]) in _indirect(r)
