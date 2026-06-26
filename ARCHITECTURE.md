# Architecture

graphify is a Claude Code skill backed by a Python library. The skill orchestrates the library; the library can be used standalone.

## Pipeline

```
detect()  →  extract()  →  build_graph()  →  cluster()  →  analyze()  →  report()  →  export()
```

Each stage is a single function in its own module. They communicate through plain Python dicts and NetworkX graphs - no shared state, no side effects outside `graphify-out/`.

## Module responsibilities

### Core pipeline

| Module | Function | Input → Output |
|--------|----------|----------------|
| `detect.py` | `collect_files(root)` | directory → `[Path]` filtered list |
| `extract.py` | `extract(path)` | file path → `{nodes, edges}` dict (dispatches to per-language extractors) |
| `extractors/` | per-language `extract_<lang>` | file path → `{nodes, edges}` dict (blade, elixir, razor, zig, and shared base) |
| `build.py` | `build_graph(extractions)` | list of extraction dicts → `nx.Graph` |
| `dedup.py` | `deduplicate_by_label(G)` | graph → graph with duplicate nodes collapsed |
| `cluster.py` | `cluster(G)` | graph → graph with `community` attr on each node |
| `analyze.py` | `analyze(G)` | graph → analysis dict (god nodes, surprises, import cycles, questions) |
| `report.py` | `render_report(G, analysis)` | graph + analysis → GRAPH_REPORT.md string |
| `export.py` | `export(G, out_dir, ...)` | graph → Obsidian vault, graph.json, graph.html, graph.svg, wiki, canvas |
| `wiki.py` | `to_wiki(G, out_dir)` | graph → agent-crawlable Markdown wiki |

### Query and serving

| Module | Function | Input → Output |
|--------|----------|----------------|
| `serve.py` | `start_server(graph_path)` | graph file path → MCP stdio/HTTP server |
| `prs.py` | `run_prs(...)` | graph + GitHub API → PR dashboard with graph blast radius |
| `querylog.py` | logging helpers | query calls → `~/.cache/graphify-queries.log` JSON Lines |

### Incremental updates and work memory

| Module | Function | Input → Output |
|--------|----------|----------------|
| `manifest.py` | `save_manifest / load_manifest` | file list → `manifest.json` with content hashes |
| `manifest_ingest.py` | `ingest_from_manifest(...)` | manifest + root → merged graph dict |
| `reflect.py` | `reflect(memory_dir, ...)` | `graphify-out/memory/` docs → `reflections/LESSONS.md` |
| `watch.py` | `watch(root, flag_path)` | directory → writes flag file on change |

### Utilities and infrastructure

| Module | Function | Input → Output |
|--------|----------|----------------|
| `ids.py` | `make_id(label, ...)` | label string → canonical NFKC/casefolded node ID |
| `paths.py` | `get_output_dir()` | env / cwd → resolved `graphify-out/` path (honours `GRAPHIFY_OUT`) |
| `cache.py` | `check_semantic_cache / save_semantic_cache` | files → (cached, uncached) split |
| `callflow_html.py` | `write_callflow_html(...)` | graphify-out files → Mermaid architecture/call-flow HTML |
| `ingest.py` | `ingest(url, ...)` | URL → file saved to corpus dir |
| `mcp_ingest.py` | `ingest_mcp_config(path)` | MCP config file → `{nodes, edges}` dict |
| `file_slice.py` | `FileSlice` | oversized text document → list of bounded slices |
| `diagnostics.py` | `diagnose_extraction(G)` | graph → dangling/self-loop/collapsed-edge warnings |
| `global_graph.py` | `add_to_global / remove_from_global` | project graph → `~/.graphify/global.json` cross-project graph |
| `security.py` | validation helpers | URL / path / label → validated or raises |
| `validate.py` | `validate_extraction(data)` | extraction dict → raises on schema errors |
| `benchmark.py` | `run_benchmark(graph_path)` | graph file → corpus vs subgraph token comparison |
| `transcribe.py` | `transcribe(path)` | audio/video file → transcript text (faster-whisper) |
| `llm.py` | `extract_corpus_parallel(...)` | files + backend → semantic `{nodes, edges}` dict |

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

New extractors go into `graphify/extractors/` as a standalone module. The `extract.py` dispatch table and `collect_files()` in `detect.py` are the only files that need updating alongside the extractor itself.

1. Add `graphify/extractors/<lang>.py` with a `extract_<lang>(path: Path) -> dict` function following the existing pattern (tree-sitter parse → walk nodes → collect `nodes` and `edges` → call-graph second pass for INFERRED `calls` edges). Import shared helpers from `graphify/extractors/base.py`.
2. Register the file suffix in the `extract()` dispatch table in `extract.py` and in `collect_files()` in `detect.py`.
3. Add the suffix to `CODE_EXTENSIONS` in `detect.py` and `_WATCHED_EXTENSIONS` in `watch.py`.
4. Add the tree-sitter package to `pyproject.toml` dependencies.
5. Add a fixture file to `tests/fixtures/` and tests to `tests/test_languages.py`.

See `graphify/extractors/MIGRATION.md` for the ongoing migration of existing extractors from the monolithic `extract.py`.

## Security

All external input passes through `graphify/security.py` before use:

- URLs → `validate_url()` (http/https only) + `_NoFileRedirectHandler` (blocks file:// redirects)
- Fetched content → `safe_fetch()` / `safe_fetch_text()` (size cap, timeout)
- Graph file paths → `validate_graph_path()` (must resolve inside `graphify-out/`)
- Node labels → `sanitize_label()` (strips control chars, caps 256 chars, HTML-escapes)

See `SECURITY.md` for the full threat model.

## Testing

One test file per module under `tests/`. Run with:

```bash
pytest tests/ -q
```

All tests are pure unit tests - no network calls, no file system side effects outside `tmp_path`.
