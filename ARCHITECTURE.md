# Architecture

graphify is a Claude Code skill backed by a Python library. The skill orchestrates the library; the library can be used standalone.

## Pipeline

```
detect()  →  extract()  →  build_graph()  →  cluster()  →  analyze()  →  report()  →  export()
```

Extraction produces a transient, record-only `GraphBuildData`; every durable
consumer receives a generation-safe `LoadedGraph` around Helix's native immutable
graph. Embedded, on-disk Helix is the only durable graph/index store;
NetworkX is neither imported nor installed in production.

A build writes topology to an inactive generation, loads an immutable native
snapshot for clustering and analysis, then stages topology and all durable state
together. Counts and a SHA-256 checksum are verified before the active-generation
pointer changes. A failed or interrupted build leaves the previous generation and
its incremental hashes active.

## Module responsibilities

| Module | Function | Input → Output |
|--------|----------|----------------|
| `detect.py` | `detect(root)` | directory → typed file lists and Helix-backed incremental state |
| `extract.py` | `extract(path)` | file path → `{nodes, edges}` dict |
| `build.py` | `build_from_json(extraction)` | extraction dict → transient record-only `GraphBuildData` |
| `cluster.py` | `cluster(G)` | native snapshot → weighted Leiden membership |
| `analyze.py` | `analyze(G)` | graph → analysis dict (god nodes, surprises, questions) |
| `report.py` | `render_report(G, analysis)` | graph + analysis → GRAPH_REPORT.md string |
| `export.py` | `export(G, out_dir, ...)` | native snapshot → Obsidian vault, GraphML, Cypher, HTML, SVG |
| `callflow_html.py` | `write_callflow_html(...)` | graphify-out files → Mermaid architecture/call-flow HTML |
| `ingest.py` | `ingest(url, ...)` | URL → file saved to corpus dir |
| `cache.py` | `check_semantic_cache / save_semantic_cache` | files → (cached, uncached) split |
| `security.py` | validation helpers | URL / path / label → validated or raises |
| `validate.py` | `validate_extraction(data)` | extraction dict → raises on schema errors |
| `serve.py` | `serve(store_path)` | active Helix generation → reloadable MCP stdio server |
| `watch.py` | `watch(root)` | changes → atomic embedded Helix rebuild |
| `benchmark.py` | `run_benchmark(store_path)` | active Helix graph → corpus vs subgraph token comparison |

## Durable generation schema

Every active generation contains graph metadata, ordered typed nodes and edges,
communities and names, analysis/report inputs, content and semantic hashes,
extraction cache, extractor state, learning/provenance, and semantic-build
metadata. There are no production topology, cache, label, analysis, or learning
sidecars.

Helix maintains unique equality indexes on `GraphifyNode(storage_key)` and
`GraphifyControl(control_key)`. `storage_key` is the generation plus Helix's
canonical typed external ID, so values such as `1`, `"1"`, and `true` cannot
collide. Semantic relations are native edge labels; they are not duplicated in
the edge attribute blob.

Human-facing reports and explicit exports remain files. Existing Obsidian
application configuration remains untouched.

## Extraction output schema

Every extractor returns:

```json
{
  "nodes": [
    {"id": "unique_string", "label": "human name", "source_file": "path", "source_location": "L42"}
  ],
  "edges": [
    {"source": "id_a", "target": "id_b", "relation": "calls|imports|uses|...", "confidence": "EXTRACTED|INFERRED|AMBIGUOUS"}
  ]
}
```

`validate.py` enforces this schema before `build_graph()` consumes it.

## Confidence labels

| Label | Meaning |
|-------|---------|
| `EXTRACTED` | Relationship is explicitly stated in the source (e.g., an import statement, a direct call) |
| `INFERRED` | Relationship is a reasonable deduction (e.g., call-graph second pass, co-occurrence in context) |
| `AMBIGUOUS` | Relationship is uncertain; flagged for human review in GRAPH_REPORT.md |

## Adding a new language extractor

1. Add a `extract_<lang>(path: Path) -> dict` function in `extract.py` following the existing pattern (tree-sitter parse → walk nodes → collect `nodes` and `edges` → call-graph second pass for INFERRED `calls` edges).
2. Register the file suffix in `extract()` dispatch and `collect_files()`.
3. Add the suffix to `CODE_EXTENSIONS` in `detect.py` and `_WATCHED_EXTENSIONS` in `watch.py`.
4. Add the tree-sitter package to `pyproject.toml` dependencies.
5. Add a fixture file to `tests/fixtures/` and tests to `tests/test_languages.py`.

## Security

All external input passes through `graphify/security.py` before use:

- URLs → `validate_url()` (http/https only) + `_NoFileRedirectHandler` (blocks file:// redirects)
- Fetched content → `safe_fetch()` / `safe_fetch_text()` (size cap, timeout)
- Helix store paths → `validate_store_path()` (must be an existing store directory)
- Node labels → `sanitize_label()` (strips control chars, caps 256 chars, HTML-escapes)

See `SECURITY.md` for the full threat model.

## Testing

One test file per module under `tests/`. Run with:

```bash
pytest tests/ -q
```

The default suite includes unit, migration, corruption, atomicity, concurrency,
native algorithm, and embedded close/reopen tests. The native tests require the
pinned `helix-db-embedded` wheel. They are skipped in minimal source-only
environments and mandatory in CI. NetworkX parity/performance is isolated under
`benchmarks/` and is never a production dependency.
