# Migrating an exporter out of export.py

`graphify/export.py` holds several output-format exporters in one ~1,100-line
file. They are being split into this package one format at a time, the same way
`graphify/extractors/` is being split out of `extract.py`. This is the playbook
for porting ONE exporter. It is written so an AI agent can execute it in a
single session. (Motivation: the runaway-file-size guardrail discussed in
issue #1213.)

## Status

| exporter | module | migrated |
|---|---|---|
| HTML viz (`to_html`) | `exporters/html.py` | yes |
| GraphDB push (`push_to_falkordb`, `push_to_neo4j`) | `exporters/graphdb.py` | yes |
| shared palette (`COMMUNITY_COLORS`) | `exporters/base.py` | yes |
| `graph.json` (`to_json`) | — | no |
| Cypher (`to_cypher`) | — | no |
| Obsidian vault (`to_obsidian`) | — | no |
| Canvas (`to_canvas`) | — | no |
| GraphML (`to_graphml`) | — | no |
| SVG (`to_svg`) | — | no |

`callflow_html.py` is a separate concern (Mermaid architecture / call-flow
HTML built from `graphify-out/` files, not from a graph object) and is out of
scope for this split.

## Invariants (non-negotiable)

1. **Verbatim moves only.** No renames, no docstring edits, no reformatting,
   no added annotations, no "improvements". Verify: save the block before
   cutting and confirm the pasted block is byte-identical.
2. **One exporter per PR.** Small diffs keep review trivial and avoid conflicts
   with other in-flight ports.
3. **Facade re-export is mandatory.** `export.py` must keep exporting every
   moved name so existing imports (`from graphify.export import to_html`) keep
   working — `from graphify.exporters.<mod> import <fn>  # noqa: E402,F401`.
4. **No exporter imports another exporter.** Symbols shared by more than one
   exporter go in `exporters/base.py`; each module imports from `base`, never
   from a sibling, so the split cannot introduce a circular import. `export.py`
   and the per-format modules both import from `base`.

## Steps

1. Pick one exporter function in `export.py` (e.g. `to_json`). Note its tests
   (e.g. `tests/test_cli_export.py`, `tests/test_export.py`).
2. Create `graphify/exporters/<format>.py` and move the function verbatim, plus
   any helper used *only* by it. If a helper is shared, move it to
   `exporters/base.py` first (its own small step).
3. Re-export from `export.py`:
   `from graphify.exporters.<format> import <fn>  # noqa: E402,F401`, and delete
   the original definition.
4. Run the exporter's existing tests. They must pass unchanged — the facade
   keeps every call site working. Update the status table above.
