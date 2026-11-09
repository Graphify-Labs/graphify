"""#3942: TypeScript 5.0's `export type * from "..."` has no equivalent in
tree-sitter-typescript 0.23 (the latest release) — the grammar raises an
ERROR on the `type` keyword in this position, and the whole file is dropped,
losing every symbol, not just the one statement.

The construct is erased at compile time, the same as `import type` /
`export type { X }`, so the graph only needs the re-export edge. Blanking
out `type` (same byte length, same offsets) before parsing lets the grammar
read the ordinary, already-supported `export * from "..."` form instead.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.extract import _normalize_ts_export_type_star, extract


def _extract(tmp_path: Path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files],
                    cache_root=tmp_path / ".cache", parallel=False)
    finally:
        os.chdir(old)
    return r


def test_export_type_star_no_longer_a_syntax_error(tmp_path, capsys):
    r = _extract(tmp_path, {
        "index.ts": 'export type * from "./types.js";\n',
        "types.ts": "export type FetchFn = typeof globalThis.fetch;\n",
    })
    err = capsys.readouterr().err
    assert "syntax error" not in err, err


def test_export_type_star_still_produces_the_re_export_edge(tmp_path):
    r = _extract(tmp_path, {
        "index.ts": 'export type * from "./types.js";\n',
        "types.ts": "export type FetchFn = typeof globalThis.fetch;\n",
    })
    rels = {e["relation"] for e in r["edges"]
            if e["source"].endswith("index_ts") or e["source"] == "index"}
    assert "imports_from" in rels or "re_exports" in rels, r["edges"]
    # types.ts's own symbol must survive too — the whole point is that
    # neither file is dropped.
    assert "FetchFn" in {n["label"] for n in r["nodes"]}


def test_export_type_named_form_is_unaffected(tmp_path):
    """Control: the already-working named type re-export must not be touched
    by a regex that is specifically anchored on the `*` star form."""
    r = _extract(tmp_path, {
        "named.ts": 'export type { FetchFn } from "./types.js";\n',
        "types.ts": "export type FetchFn = typeof globalThis.fetch;\n",
    })
    type_only_edges = [e for e in r["edges"] if e.get("type_only")]
    assert type_only_edges, "the named form must keep its type_only stamp (#3123)"


def test_normalize_function_only_blanks_the_type_keyword():
    source = b'export type * from "./types.js";\n'
    normalized = _normalize_ts_export_type_star(source)
    assert normalized is not None
    assert len(normalized) == len(source)
    assert normalized == b'export      * from "./types.js";\n'


def test_normalize_function_returns_none_when_no_match():
    assert _normalize_ts_export_type_star(b'export * from "./x";\n') is None
    assert _normalize_ts_export_type_star(b'export type { X } from "./x";\n') is None
