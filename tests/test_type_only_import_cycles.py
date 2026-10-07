"""Type-only imports must not manufacture Import Cycles (#3123).

`import type` / `export type ... from` are erased by the TypeScript compiler
— no runtime emit, no module-graph edge — yet the extractor emitted an
ordinary `imports_from` edge for them, and every one of the reporter's
reported cycles (3 of 3 on a ~7,900-node repo) closed only through such
edges. The report even flagged code whose comment said the `export type`
form was chosen for "zero runtime emit"; the mitigation was reported as the
defect.

The edge is kept — the type dependency is real for "what references this
type" — stamped `type_only`, and `find_import_cycles` excludes it the way
it already excludes deferred `import(...)` (#1241).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from graphify.analyze import find_import_cycles
from graphify.build import build_from_json
from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return extract([tmp_path / n for n in files], cache_root=Path(tempfile.mkdtemp()),
                   root=tmp_path, parallel=False)


def _module_edges(result, rel="imports_from"):
    return [e for e in result["edges"] if e["relation"] == rel]


# ---------------------------------------------------------------------------
# The stamp
# ---------------------------------------------------------------------------

def test_import_type_statement_is_stamped(tmp_path):
    r = _extract(tmp_path, {
        "types.ts": "export type Variables = { requestId: string };\n",
        "v1.ts": 'import type { Variables } from "./types.js";\n'
                 "export function makeRouter() { return {} as unknown; }\n",
    })
    edges = [e for e in _module_edges(r) if e["source_file"].endswith("v1.ts")]
    assert edges and all(e.get("type_only") for e in edges)


def test_export_type_reexport_is_stamped(tmp_path):
    r = _extract(tmp_path, {
        "v1.ts": "export type RouterType = { v: number };\n",
        "types.ts": 'export type { RouterType } from "./v1.js";\n',
    })
    stamped = [e for e in r["edges"]
               if e["source_file"].endswith("types.ts")
               and e["relation"] in ("imports_from", "re_exports")]
    assert stamped and all(e.get("type_only") for e in stamped)


def test_a_default_binding_named_type_is_a_runtime_import(tmp_path):
    """`import type from './x.js'` imports a value whose name is `type` —
    erased by nothing."""
    r = _extract(tmp_path, {
        "x.ts": "const type = 1;\nexport default type;\n",
        "user.ts": 'import type from "./x.js";\nexport const y = type;\n',
    })
    edges = [e for e in _module_edges(r) if e["source_file"].endswith("user.ts")]
    assert edges and not any(e.get("type_only") for e in edges)


def test_a_mixed_specifier_list_stays_a_runtime_edge(tmp_path):
    """`import { type B, C }` still imports C at runtime."""
    r = _extract(tmp_path, {
        "b.ts": "export type B = number;\nexport const C = 1;\n",
        "user.ts": 'import { type B, C } from "./b.js";\nexport const y = C;\n',
    })
    edges = [e for e in _module_edges(r) if e["source_file"].endswith("user.ts")]
    assert edges and not any(e.get("type_only") for e in edges)


def test_plain_imports_are_untouched(tmp_path):
    r = _extract(tmp_path, {
        "b.ts": "export const C = 1;\n",
        "user.ts": 'import { C } from "./b.js";\nexport const y = C;\n',
    })
    edges = [e for e in _module_edges(r) if e["source_file"].endswith("user.ts")]
    assert edges and not any("type_only" in e for e in edges)


# ---------------------------------------------------------------------------
# The cycles — the reporter's minimal repro
# ---------------------------------------------------------------------------

def _cycles(tmp_path, files):
    r = _extract(tmp_path, files)
    # directed=True mirrors a --directed build; in the default undirected
    # graph two module edges between one file pair collapse to a single
    # stored edge, so a synthetic 2-cycle needs distinct endpoints anyway.
    G = build_from_json({"nodes": r["nodes"], "edges": r["edges"], "hyperedges": []},
                        root=str(tmp_path), directed=True)
    return find_import_cycles(G)


def test_the_reporters_two_file_cycle_is_gone(tmp_path):
    cycles = _cycles(tmp_path, {
        "types.ts": ("export type Variables = { requestId: string };\n"
                     'export type { RouterType } from "./v1.js";\n'),
        "v1.ts": ('import type { Variables } from "./types.js";\n'
                  "export type RouterType = { v: Variables };\n"
                  "export function makeRouter() { return {} as RouterType; }\n"),
    })
    assert cycles == [], cycles


def test_a_real_runtime_cycle_is_still_reported(tmp_path):
    cycles = _cycles(tmp_path, {
        "a.ts": 'import { b } from "./b.js";\nexport const a = 1;\n',
        "b.ts": 'import { a } from "./a.js";\nexport const b = 2;\n',
    })
    assert len(cycles) == 1
    assert sorted(Path(f).name for f in cycles[0]["cycle"]) == ["a.ts", "b.ts"]


def test_a_cycle_with_one_type_only_leg_is_not_a_cycle(tmp_path):
    """One runtime leg + one type-only leg: no runtime cycle exists."""
    cycles = _cycles(tmp_path, {
        "a.ts": 'import { b } from "./b.js";\nexport type AT = number;\nexport const a = 1;\n',
        "b.ts": 'import type { AT } from "./a.js";\nexport const b = 2;\n',
    })
    assert cycles == [], cycles
