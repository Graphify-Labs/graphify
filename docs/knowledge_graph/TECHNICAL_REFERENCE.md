# graphify — Technical Reference

*Deep module-by-module reference for contributors. Companion doc: `CODEBASE_OVERVIEW.md` (architecture, pipeline, execution flow — read that first). Visual: `graph.html`.*

*Grounded in commit `e32c9f4` (branch `v8`, v0.9.24), file:line cited throughout. Marked **[UNVERIFIED]** where a research pass could not confirm intent from code alone.*

---

## 1. Module-by-module map (`graphify/*.py`, 48 top-level modules)

Grouped by subsystem. "Imports →" lists internal `graphify.*` dependencies (from static `from graphify.X import` grep — not exhaustive of function-local/lazy imports, notably `cli.py`'s, which are far broader — see §3).

### Pipeline core
| Module | Responsibility | Key symbols |
|---|---|---|
| `detect.py` (1871 lines) | Corpus file discovery/classification for the `extract` command; gitignore/`.graphifyignore` handling; `CODE_EXTENSIONS` set | `detect(root, ...)` L1238 |
| `extract.py` (5320 lines) | AST extraction orchestrator: dispatch table, ~20 `extract_<lang>` wrapper functions for config-driven languages, cross-file call resolution, facade re-exports for migrated extractors | `extract()` L4381, `_DISPATCH` L3926, `_get_extractor()` L4135, `collect_files()` L5248 |
| `build.py` (1293 lines) | Merges extraction dicts into a `networkx.Graph`; ID disambiguation, dedup, incremental merge, legacy-ID migration | `build()` L938, `build_from_json()` L490, `build_merge()` L1038, `dedupe_nodes/edges()` L295/314 |
| `cluster.py` (320 lines) | Leiden community detection, cohesion scoring, community-ID stability across rebuilds | `cluster()` L134, `score_all()` L268, `label_communities_by_hub()` L86, `remap_communities_to_previous()` L272 |
| `analyze.py` (741 lines) | Independent analysis functions — no single `analyze()` entry point | `god_nodes()` L101, `surprising_connections()` L125, `suggest_questions()` L420, `graph_diff()` L548, `find_import_cycles()` L632 |
| `report.py` (short) | Renders `GRAPH_REPORT.md` text | `generate()` L71 |
| `export.py` (1093 lines) | One `to_*`/`push_to_*` function per output format (see §4) — no unary `export()` | `to_json()` L232, `to_obsidian()` L454, `to_canvas()` L785, `to_graphml()` L963, `to_svg()` L1026, `to_cypher()` L384, `backup_if_protected()` L35 |
| `validate.py` | Extraction-dict schema enforcement (warn, not hard-fail) | `validate_extraction()` L10, `assert_valid()` L90, `VALID_CONFIDENCES`/`VALID_FILE_TYPES`/`REQUIRED_*_FIELDS` L4-7 |

### CLI / orchestration
| Module | Responsibility | Key symbols |
|---|---|---|
| `__main__.py` (716 lines) | Process entry point, argv parsing, help text, version-staleness check, hands off to `install.py` then `cli.py` | `main()` L460, `_run_cli()` L483 |
| `cli.py` (3685 lines) | The command dispatcher — one `if/elif` branch per subcommand (see `CODEBASE_OVERVIEW.md` §6 for the full table) | `dispatch_command()` L626, `_reenter_main()` L621 |

### Serving / live modes
| Module | Responsibility | Key symbols |
|---|---|---|
| `serve.py` (1999 lines) | MCP server (stdio + Streamable HTTP), query scoring/traversal engine, resources | `_build_server()` L1103, `serve()` L1713, `serve_http()` L1871, `_score_nodes()` L351, `_bfs()`/`_dfs()` L740/770ish, `_subgraph_to_text()` L796 |
| `watch.py` (1496 lines) | Filesystem watcher (watchdog), debounce, incremental rebuild, per-repo lock | `watch()` ~L1396, `_rebuild_code()` L839, `_rebuild_lock()` L157 |
| `hooks.py` (690 lines) | Git post-commit/post-checkout hook install, merge driver registration | `install()` L633, `_hooks_dir()` L399, `_register_merge_driver()` L525 |
| `affected.py` | Reverse-dependency traversal ("what depends on X") | `resolve_seed()` L98, `affected_nodes()` L145 |
| `querylog.py` | Opt-in JSONL query logging, never raises | `log_query()` L43 |

### Ingestion
| Module | Responsibility | Key symbols |
|---|---|---|
| `ingest.py` (353 lines) | URL → corpus markdown file (tweets, arxiv, webpages, PDFs, images); routes all network I/O through `security.safe_fetch*` | `ingest()` L218, `save_query_result()` L274 |
| `mcp_ingest.py` (386 lines) | Extractor (not a fetcher) for `.mcp.json`/`claude_desktop_config.json` style files → graph nodes; explicitly never reads env-var **values**, only keys (secret avoidance) | `extract_mcp_config()` L86 |
| `scip_ingest.py` (363 lines) | SCIP index ingestion | — |
| `manifest_ingest.py` | Manifest-based ingestion helper | — |
| `transcribe.py` (353 lines) | Local audio/video transcription (faster-whisper) | `download_audio()` referenced |
| `google_workspace.py` | `.gdoc`/`.gsheet`/`.gslides` shortcut export via `gws` | — |

### Install / distribution
| Module | Responsibility | Key symbols |
|---|---|---|
| `install.py` (2204 lines) | The 20+-platform "install as skill" system — see `CODEBASE_OVERVIEW.md` §3.1 for the architecture; per-platform functions listed there | `install()` L589, `dispatch_install_cli()` L1929, `_PLATFORM_CONFIG` L324, `uninstall_all()` L1714 |

### Utilities / infrastructure
| Module | Responsibility | Key symbols |
|---|---|---|
| `paths.py` (304 lines) | `graphify-out/` path resolution, atomic writes, test-path classification, call-site disambiguation | `write_json_atomic()` L88, `_atomic_replace()` L29, `disambiguate_ambiguous_candidates()` L223 |
| `ids.py` (50 lines) | **Single canonical** node-ID normalization (explicitly fixes recurring "ID drift" bugs across 3 producers: AST extractor, LLM extractor, graph builder — cites issues #811/#550/#1033/#1104) | `normalize_id()` L32, `make_id()` L43 |
| `security.py` (460 lines) | SSRF/path-traversal/size-cap/sanitization — see `CODEBASE_OVERVIEW.md` §9 | (table there) |
| `cache.py` (1040 lines) | Two-tier extraction cache: versioned AST cache (`cache/ast/v{n}/`), unversioned semantic/LLM cache with prompt-fingerprint invalidation | `file_hash()` ~L256, `check_semantic_cache()` L719, `save_semantic_cache()` L808, `prompt_fingerprint()` L89 |
| `resolver_registry.py` (85 lines) | Plugin registry for per-language cross-file resolution passes | `LanguageResolver` L28, `register()` L48, `run_language_resolvers()` L59 |
| `symbol_resolution.py` (554 lines) | Deterministic Python/Bash import-alias-guided call resolution — **[UNVERIFIED: appears unused in production]**, only referenced by `tests/test_symbol_resolution.py`, not imported by `extract.py` or any `extractors/*.py` | `build_python_symbol_index()`, `resolve_python_import_guided_calls()` L218, `resolve_cross_file_raw_calls()` L307, `resolve_bash_source_edges()` L404 |
| `ruby_resolution.py` / `pascal_resolution.py` | Language-specific resolver-registry plugins (Ruby member calls, Pascal inherited-ancestor calls) | `resolve_ruby_member_calls()` L52, `resolve_pascal_inherited_calls()` L42 |
| `global_graph.py` (184 lines) | Cross-repo merged graph at `~/.graphify/global-graph.json`; repo-tag ID prefixing, dedup of shared external-library nodes | `global_add()` L79, `global_remove()` L161, `global_list()` L178 |
| `dedup.py` (669 lines) + `_minhash.py` | Near-duplicate node detection via MinHash | — |
| `diagnostics.py` (406 lines) | `diagnose multigraph` — same-endpoint edge collapse risk reporting | — |
| `reflect.py` (882 lines) | Aggregates `graphify-out/memory/*.md` outcomes into `LESSONS.md` | — |
| `prs.py` (761 lines) | PR-related subcommands (list/impact/triage) | — |
| `benchmark.py` | Token-reduction measurement — note: uses its **own simplified** BFS reimplementation, not `serve._bfs`/`_score_nodes`, so its numbers may not perfectly represent live query cost | `run_benchmark()` |
| `llm.py` (2994 lines) | LLM backend abstraction (Claude/OpenAI/Gemini/Ollama/Azure/Bedrock/Kimi/DeepSeek), semantic extraction orchestration, community labeling | `extract_corpus_parallel()`, `generate_community_labels()` |
| `cache_check` support: `manifest.py`, `file_slice.py`, `semantic_cleanup.py`, `multigraph_compat.py`, `cargo_introspect.py`, `pg_introspect.py` | Supporting utilities for manifest tracking, LLM context slicing, semantic-result cleanup, multigraph→simple-graph compatibility shims, Cargo/Postgres schema introspection | — |
| `callflow_html.py` (2022 lines) | Mermaid-based architecture/call-flow HTML doc generator | `write_callflow_html()` L1579, `generate_overview_graph()` L1075 |
| `tree_html.py` (585 lines) | D3 v7 collapsible filesystem-tree HTML view | `write_tree_html()` L565, `build_tree()` L68 |
| `wiki.py` (337 lines) | Obsidian-independent Wikipedia-style markdown wiki (one article per community + per god-node) | `to_wiki()` L211 |

## 2. Extractors subsystem (`graphify/extractors/`, 29 files)

| File | Role |
|---|---|
| `engine.py` (4581 lines) | Shared generic tree-sitter walker `_extract_generic()` (L2157) used by all config-driven languages; two-visitor-pass design (definitions pass, then a deferred calls pass) |
| `base.py` | Shared helpers: `_make_id`, `_file_stem`, `_read_text`, `_LANGUAGE_BUILTIN_GLOBALS` (builtin-noise blocklist to prevent god-nodes, #726); enforces the one-way import boundary from `extract.py` |
| `models.py` | `LanguageConfig` dataclass (L14) — the "strategy" object injected into `_extract_generic`; `_SymbolResolutionFacts` and fact dataclasses (L57-119) |
| `resolution.py` (2617 lines) | **The wired-in** symbol resolution subsystem: JS/TS module-path resolution (tsconfig aliases, workspace packages), Python relative-import resolution, Java/PHP/Pascal/C# type-reference arbitration. Entry point `_augment_symbol_resolution_edges()` L1757, called once from `extract.py:4572` |
| `__init__.py` | `LANGUAGE_EXTRACTORS` registry (L36-64) — test-only, confirms facade re-export identity; **not the runtime dispatch path** |
| `go.py`, `rust.py`, `blade.py`, `zig.py`, `elixir.py`, `dart.py`, `powershell.py`, `fortran.py`, `sql.py`, `dm.py`, `bash.py`, `apex.py`, `terraform.py`, `sln.py`, `pascal_forms.py`, `json_config.py`, `pascal.py`, `objc.py`, `razor.py`, `julia.py`, `verilog.py`, `markdown.py` | Bespoke, self-contained per-language extractors (own `walk()`/`walk_calls()` AST traversal) |
| `csharp.py` | **Not** the C# extractor — only cross-file C# resolution passes (`_build_csharp_type_def_index` L19, `_resolve_cross_file_csharp_imports` L77, `_resolve_csharp_type_references` L152); C# extraction itself is `extract_csharp()` in `extract.py` via the shared engine |

**Extractor pattern example (bespoke, `go.py`)**: `extract_go(path)` (L53) walks the file once collecting declarations (`walk()`, L177-326: functions, receiver-typed methods, struct/interface embedding, imports), then a second pass (`walk_calls()`, L339-384) resolves call expressions against the file's own `label_to_nid` map, falling back to a `raw_calls` list for cross-file/global resolution. `rust.py` mirrors this exactly (walk L163-335, walk_calls L348-398).

**Config-driven pattern example**: `extract_python()` (`extract.py:1136`) is a thin wrapper: `_extract_generic(path, _PYTHON_CONFIG)`. Same shape for Java (`extract.py:1592`→`_JAVA_CONFIG`), C# (`extract.py:1728`→`_CSHARP_CONFIG`), etc. — one `LanguageConfig` instance per language (e.g. `_PYTHON_CONFIG` L686, `_JS_CONFIG` L700, `_JAVA_CONFIG` L754, `_CSHARP_CONFIG` L832).

**Adding a new language** — verified playbook (supersedes `ARCHITECTURE.md`'s simplified 5-step version; see `graphify/extractors/MIGRATION.md` for the authoritative in-flight refactor status):
1. Write a bespoke `extract_<lang>(path) -> dict` in a new `graphify/extractors/<lang>.py` (self-contained walker), OR add a `LanguageConfig` + thin wrapper in `extract.py` if the language fits the generic engine.
2. Register the suffix in `_DISPATCH` (`extract.py:3926`).
3. Add the suffix to `CODE_EXTENSIONS` (`detect.py:31`) and `_WATCHED_EXTENSIONS` (`watch.py:264`, derived from `CODE_EXTENSIONS | DOC_EXTENSIONS | ...`).
4. Add the `tree-sitter-<lang>` dependency to `pyproject.toml` (core or an optional extra, per `_EXTRA_FOR_EXTENSION` in `extract.py`).
5. Add a fixture under `tests/fixtures/sample.<ext>` and tests in the relevant `tests/test_<lang>*.py`.
6. If cross-file resolution is needed, register a `LanguageResolver` via `resolver_registry.register()` (see `ruby_resolution.py`/`pascal_resolution.py` for the pattern).

## 3. Exporters subsystem (`graphify/exporters/`, 4 files)

| File | Role |
|---|---|
| `base.py` | `COMMUNITY_COLORS` palette only — split out to avoid a circular import between `export.py` and format modules |
| `html.py` (560 lines) | `to_html()` (L325) — interactive vis.js graph; auto-falls back to a community-aggregated meta-graph above a node-count limit |
| `graphdb.py` (173 lines) | Both Neo4j **and** FalkorDB: `push_to_neo4j()` (L9, `neo4j` driver, parameterized Cypher) and `push_to_falkordb()` (L80, `falkordb` SDK, near-identical MERGE queries, differs only in connection setup) |

**Full export format inventory** (each is an independent `to_*`/`push_to_*` function in `export.py`, dispatched by `graphify export <subcmd>` in `cli.py:2054`, not a single `export()` call):

| Format | Function | Notable behavior |
|---|---|---|
| `graph.json` | `to_json()` | Shrink-guard refuses to overwrite with fewer nodes unless forced (#479); atomic write |
| `graph.html` | `to_html()` | vis.js; community-aggregated fallback above a size threshold |
| Obsidian vault | `to_obsidian()` | One `.md`/node + YAML frontmatter + `[[wikilinks]]`, one file per community, tracks graphify-owned files via a manifest so user notes are never clobbered |
| `graph.canvas` | `to_canvas()` | Obsidian Canvas JSON, communities as grid-laid-out groups, top-200 edges by weight |
| `graph.graphml` | `to_graphml()` | Gephi/yEd compatible |
| `graph.svg` | `to_svg()` | matplotlib spring-layout static image, community-colored |
| `cypher.txt` | `to_cypher()` | OpenCypher `MERGE` script with dedicated injection-safe escaping |
| Live Neo4j/FalkorDB | `push_to_neo4j()`/`push_to_falkordb()` | Direct DB push via SDK, parameterized queries |
| Mermaid call-flow HTML | `write_callflow_html()` (`callflow_html.py`) | Section-based Mermaid flowcharts + prose, bilingual EN/中文 |
| D3 tree view | `write_tree_html()` (`tree_html.py`) | Collapsible filesystem-rooted tree, `graphify tree` command (not under `export`) |
| Wiki | `to_wiki()` (`wiki.py`) | Wikipedia-style markdown, community + god-node articles |

## 4. Design patterns catalog (with evidence)

| Pattern | Where | Evidence |
|---|---|---|
| **Pipeline/stage pattern with instrumentation** | `cli.py`'s `extract`/`cluster-only` paths thread a `_StageTimer` through each phase | `cli.py:2645`, `.mark("detect")` etc. |
| **Strategy pattern** | `LanguageConfig` injected into the single `_extract_generic()` algorithm; per-language hooks are callables in the config | `extractors/models.py:14-54` |
| **Visitor / two-pass AST walker** | Every extractor: pass 1 collects definitions, pass 2 (deferred) resolves calls against the file's own symbol map, falling back to `raw_calls` for cross-file resolution | `go.py:177-384`, `rust.py:163-398` |
| **Registry pattern** | `resolver_registry.py` (`_REGISTRY` list + `register()`/`run_language_resolvers()`); also the test-only `LANGUAGE_EXTRACTORS` in `extractors/__init__.py` | `resolver_registry.py:45-59` |
| **Facade pattern** | `extract.py` re-exports every symbol relocated into `extractors/*` so external callers (`__main__.py`, `watch.py`, tests) are unaffected by the in-flight migration | `extract.py:27-142`, all `# noqa: F401` |
| **Deferred/two-pass resolution at corpus scope** | Every file emits unresolved `raw_calls`; `extract()` aggregates and resolves them globally once all files are parsed | `extract.py:4561-5118` |
| **Table-driven plugin dispatch** | `install.py`'s `_PLATFORM_CONFIG` covers ~19 of 21+ AI-tool platforms through one generic path; only platforms needing non-generic mechanics (native hooks, JS plugins) get bespoke functions | `install.py:324-465` + per-platform functions |
| **Single source of truth for a cross-cutting concern** | `graphify/ids.py` centralizes ID normalization specifically because it drifted across 3 independent producers in the past | `ids.py:1-23` docstring |
| **Split pipeline halves for two different callers** | `extract` (CLI/headless) stops before labeling; `cluster-only`/`label` is the shared "back half" also reachable standalone, so the LLM-orchestrated skill.md flow and the plain CLI flow share code without duplicating it | `cli.py:3482-3489` vs `cli.py:1438-1761` |
| **Confidence-scored edges as first-class schema** | `EXTRACTED`/`INFERRED`/`AMBIGUOUS` let deterministic AST edges and LLM-inferred edges coexist safely; surfaced as a percentage breakdown in the report | `validate.py:5`, `report.py:93-97` |
| **Build-time codegen with drift guards** | `tools/skillgen/` renders 20+ generated skill files from shared fragments; CI fails the build on any hand-edit or missed regeneration | `tools/skillgen/gen.py`, `.github/workflows/ci.yml` skillgen-check job |
| **Anti-data-loss shrink guards** | Both `to_json()` and the incremental `build_merge()` refuse to silently produce a smaller graph than the last good one (issue #479) | `export.py:233-287` |

## 5. Glossary

| Term | Meaning |
|---|---|
| **Node** | A graph entity: function, class, file, concept, community, etc. Schema: `{id, label, file_type, source_file, source_location}`. |
| **Edge** | A typed relationship between two nodes. Schema: `{source, target, relation, confidence, source_file}`. |
| **EXTRACTED / INFERRED / AMBIGUOUS** | Confidence tiers for an edge — explicit-in-source, deduced, or uncertain-flag-for-review, respectively. |
| **God node** | A node with unusually high degree (connectivity) — surfaced by `graphify god-nodes` / `analyze.god_nodes()` as an architectural hub, not necessarily a code smell. |
| **Community** | A cluster of related nodes from Leiden community detection (`cluster.py`); roughly maps to a subsystem/module. |
| **Cohesion score** | Per-community metric (`score_all()`) of how internally connected vs. externally connected a community's nodes are. |
| **`graphify-out/`** | The default output directory for `graph.json`, `GRAPH_REPORT.md`, caches, wiki, and other generated artifacts. |
| **Raw call** | An unresolved call-site reference emitted by a single-file extraction pass, resolved globally in a later corpus-wide pass. |
| **Skill** | The bundle of instructions (`SKILL.md` + optional `references/`) that teaches an AI coding tool to use graphify's graph instead of raw file reads. |
| **Always-on block** | A short instruction snippet injected into a tool's always-loaded context file (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, ...) rather than a lazily-loaded skill file. |
| **Bespoke extractor** | A hand-written, self-contained per-language AST walker (as opposed to a config-driven one riding the shared engine). |
| **Config-driven extractor** | A language handled by the shared `_extract_generic()` engine, parameterized by a `LanguageConfig`. |
| **Shrink guard** | A write-time check that refuses to persist a graph with unexpectedly fewer nodes than the previous version, to prevent silent data loss from a bad partial rebuild. |
| **Hyperedge** | A relationship spanning more than two nodes, emitted by semantic (LLM) extraction; normalized during `build()` (`build.py:85`, `_normalize_hyperedge_members`). |
| **Global graph** | A separate, cross-repo merged graph at `~/.graphify/global-graph.json`, built by tagging each project's node IDs with a repo prefix. |

## 6. Uncertainties flagged during this research pass

These are explicitly **not fixed** — they're documented so a developer doesn't waste time rediscovering them:

1. `graphify/symbol_resolution.py` (top-level module) appears unused by the production pipeline — only its own test imports it. Whether it's a planned replacement for logic still ad hoc in `extract.py`, or dead/orphaned code, could not be determined from the code alone. **[UNVERIFIED]**
2. `graphify/benchmark.py`'s token-reduction measurement reimplements a simplified BFS independent of the real `serve._bfs`/`_score_nodes` query path (no hub throttling, no IDF/trigram scoring, no stopword filtering) — so `BENCHMARKS.md`/README numbers sourced from it may not represent live query cost exactly. **[UNVERIFIED — not confirmed whether this divergence is intentional/acceptable to maintainers.]**
3. The precise `cli.py` subcommand wiring to `ingest.ingest()` (likely `add`) and to `mcp_ingest.extract_mcp_config()` (likely inside `detect()`/`extract()`'s corpus-type routing) was not traced to an exact line in this pass.
4. `ARCHITECTURE.md` (root-level doc) describes a slightly idealized/older module shape in places (unary `analyze()`/`export()`, `render_report()` instead of `generate()`) — this reference document reflects the verified current code; treat `ARCHITECTURE.md` as directional, not literal, until it's updated.
