# graphify — Codebase Overview

*A developer's guide to what this codebase is, how it's organized, and how it runs. Companion doc: `TECHNICAL_REFERENCE.md` (module-by-module deep reference). Visual: `graph.html` (open in a browser — interactive module dependency graph).*

*Grounded in commit `e32c9f4` (branch `v8`, v0.9.24). Every claim below cites a file, and file:line where practical. Anything not directly verifiable in this pass is marked **[UNVERIFIED]**.*

---

## 1. What this project is

**graphify** turns a folder of code, docs, papers, images, or videos into a **queryable knowledge graph** — nodes are entities (functions, classes, files, concepts...), edges are typed relationships (`calls`, `imports`, `inherits`, `documents`, ...). Its purpose (`pyproject.toml:6`, `README.md:97-113`) is to give AI coding assistants a token-efficient substitute for reading a whole repo: instead of grepping and reading dozens of files, an agent queries a prebuilt graph (`graphify-out/graph.json`) via CLI (`graphify query "..."`) or an MCP server (`graphify-mcp`). `BENCHMARKS.md` claims up to 71.5x token reduction vs. naive full-corpus reading.

It ships two ways:
- **As a Python library/CLI** — `uv tool install graphifyy` or `pip install graphifyy` (distributed name has a double-y; import name and CLI command are `graphify` — see Troubleshooting note below).
- **As an "agent skill"** — `graphify install` writes platform-specific instruction files and hooks into 20+ AI coding tools (Claude Code, Codex, Cursor, Aider, Copilot, Kiro, Devin, ...) so the graph is consulted automatically before those tools read raw files (`graphify/install.py`).

This is a **meta/self-referential codebase**: it is itself a code-comprehension tool, and the project runs it on itself (`.github/workflows/release-graph.yml`, `worked/` example outputs, `AGENTS.md` instructing contributing agents to consult `graphify-out/GRAPH_REPORT.md`).

## 2. Tech stack

| Aspect | Detail | Evidence |
|---|---|---|
| Language | Python ≥3.10, ~52,000 LOC across `graphify/` (65 files) + `graphify/exporters/` (4) + `graphify/extractors/` (29) | `pyproject.toml:11`; `wc -l` |
| Build backend | `setuptools>=68` | `pyproject.toml [build-system]` |
| Package manager | `uv` (primary/recommended), `pip` also works; `uv.lock` committed | `README.md:153-163`, `.github/workflows/ci.yml` |
| Core deps | `networkx` (graph data structure), `numpy`, `rapidfuzz` (fuzzy matching), ~28 `tree-sitter-<language>` grammar packages | `pyproject.toml:14-42` |
| Optional extras | `mcp`, `neo4j`, `falkordb`, `pdf`, `watch`, `svg`, `leiden`, `office`, `google`, `postgres`, `video`, per-LLM-backend extras (`kimi`,`ollama`,`bedrock`,`anthropic`,`gemini`,`openai`), `chinese`, `sql`, `pascal`, `dm`, `terraform`, `all` | `pyproject.toml:52-77` |
| Non-Python files elsewhere in the repo | **Test fixtures only** — `tests/fixtures/sample.<ext>` for ~30 languages (`.go`, `.rs`, `.cs`, `.swift`, `.pas`, `.sql`, `.xaml`...) exercise the language extractors; they are not application code | `tests/fixtures/` listing |

## 3. Architecture at a glance

A **staged pipeline library**, not a long-running service by default:

```
detect()  →  extract()  →  build()/build_from_json()  →  cluster()  →  analyze fns  →  generate() (report)  →  to_json()/to_html()/... (export)
```

Each stage is (mostly) a pure function passing plain dicts / `networkx.Graph` objects — `ARCHITECTURE.md`'s framing of "no shared state" is accurate at the data-flow level, though in practice `analyze.py` has no single `analyze()` function (it's several independent functions) and `export.py` has no single `export()` (one `to_*` function per output format), correcting `ARCHITECTURE.md`'s simplified module table. See §5 for verified signatures.

On top of this pipeline sit three additional runtime modes:
1. **CLI query mode** — one-shot commands (`query`, `path`, `explain`, `affected`, `god-nodes`) read `graphify-out/graph.json` and print results.
2. **MCP server** (`graphify/serve.py`) — stdio or Streamable-HTTP server exposing the graph as tools to any MCP-capable AI client; also deployable as a Docker container (`Dockerfile`).
3. **Watch mode** (`graphify/watch.py`) — a `watchdog`-based filesystem watcher that debounces changes and re-triggers an AST-only rebuild, or flags a "needs semantic update" state for doc/paper/image changes.

### 3.1 The two plugin systems

This codebase has two orthogonal, unusually broad plugin architectures worth understanding up front:

**A. Language extraction plugins** (`graphify/extractors/` + dispatch in `graphify/extract.py`) — ~30 languages. Two coexisting extractor shapes:
- **Bespoke extractors**: self-contained AST walkers, one file each (`extractors/go.py`, `extractors/rust.py`, `extractors/blade.py`, `extractors/zig.py`, `extractors/elixir.py`, `extractors/dart.py`, `extractors/powershell.py`, `extractors/fortran.py`, `extractors/sql.py`, `extractors/dm.py`, `extractors/bash.py`, `extractors/apex.py`, `extractors/terraform.py`, `extractors/sln.py`, `extractors/pascal_forms.py`, `extractors/json_config.py`).
- **Config-driven extractors**: python, js/ts, java, c/cpp, ruby, csharp, kotlin, scala, php, lua, swift, groovy, vue, svelte, astro, xaml — these still live inside `extract.py` as `extract_<lang>` wrapper functions that call one shared generic tree-sitter walker, `_extract_generic()` in `graphify/extractors/engine.py:2157`, parameterized by a `LanguageConfig` dataclass (`extractors/models.py:14`).

  An in-flight refactor (`graphify/extractors/MIGRATION.md`) is migrating bespoke extractors out of `extract.py` one language per PR; config-driven languages are pinned as a future batch move once the shared engine core itself relocates. **Import direction is enforced one-way** (`extractors/base.py:1`: *"DO NOT import from graphify.extract here — direction is extract.py → extractors/ only"*), and `extract.py` re-exports every relocated name (`extract.py:27-142`, all `# noqa: F401`) so external callers see no breakage — a facade pattern.

  Real runtime dispatch is the `_DISPATCH` table (`extract.py:3926`, ~90 extensions → `extract_<lang>` functions), consumed by `_get_extractor()` (`extract.py:4135`). A second registry, `LANGUAGE_EXTRACTORS` in `extractors/__init__.py:36-64`, exists only to keep a test (`tests/test_extractors_registry.py`) honest that the facade re-exports match — **it is not the runtime dispatch path**.

  Cross-file/cross-language call resolution runs as a deferred second pass: every extractor emits unresolved `raw_calls`; `extract()` aggregates them across the whole corpus and resolves globally after all files are parsed (`extract.py:4994-5118`), assigning `EXTRACTED` confidence when import evidence backs the match, `INFERRED` otherwise. Additional **per-language resolver plugins** register into `graphify/resolver_registry.py` (`LanguageResolver` dataclass, `register()`/`run_language_resolvers()`) — e.g. Ruby (`ruby_resolution.py`) and Pascal (`pascal_resolution.py`) member-call resolution.

**B. AI-tool "install as skill" plugins** (`graphify/install.py`, 2204 lines) — one entry per AI coding tool, table-driven for the common case (`_PLATFORM_CONFIG` dict, `install.py:324-465`, ~19 platforms) plus hand-written functions for platforms needing non-generic mechanics: Claude Code gets a `CLAUDE.md` section + a PreToolUse hook in `.claude/settings.json` (`install.py:1640-1688`); Cursor gets `.cursor/rules/graphify.mdc` (`install.py:1042-1056`); OpenCode/Kilo get injected JS plugins intercepting `tool.execute.before` (`install.py:1290-1313`, `1205-1228`); Codex/Aider/others get an `AGENTS.md` section (`install.py:1406-1441`); Kiro gets a steering file (`install.py:877-902`); Antigravity gets `.agents/rules/` + `.agents/workflows/` (`install.py:919-981`). All told, 21+ platforms are supported (`README.md` command list confirms: claude, windows, codebuddy, codex, opencode, aider, amp, agents, claw, droid, trae, trae-cn, gemini, cursor, antigravity, hermes, kiro, pi, devin).

  The actual instruction *text* installed for each platform is itself **generated at build time** by `tools/skillgen/` (fragments under `tools/skillgen/fragments/*.md` + `tools/skillgen/platforms.toml` → committed output at `graphify/skill*.md` and `graphify/skills/<platform>/references/*.md`). CI's `skillgen-check` job (`.github/workflows/ci.yml`) runs 5 drift-guards (`--check`, `--audit-coverage`, `--schema-singleton`, `--monolith-roundtrip`, `--always-on-roundtrip`) so hand-edits to generated files, or missed regenerations, fail the build.

## 4. Domain model

- **Node**: `{id, label, file_type, source_file, source_location}`. `file_type ∈ {code, document, paper, image, rationale, concept}`.
- **Edge**: `{source, target, relation, confidence, source_file}`. `confidence ∈ {EXTRACTED, INFERRED, AMBIGUOUS}` — `EXTRACTED` is explicit in source (an import statement, a direct call), `INFERRED` is a reasonable deduction (call-graph second pass), `AMBIGUOUS` is uncertain and flagged in `GRAPH_REPORT.md` for human review.
- Schema enforced (warn, not hard-fail) by `validate_extraction()` in `graphify/validate.py:10`, called from `build_from_json()` (`build.py:539`).
- Stored as `graphify-out/graph.json` (NetworkX node-link JSON). Derived artifacts on demand: `GRAPH_REPORT.md`, an Obsidian-compatible wiki vault, `graph.html`, `graph.svg`, `graph.canvas`, `graph.graphml`, a Cypher script, a D3 collapsible tree view, a Mermaid call-flow HTML doc.

## 5. The core pipeline — verified function signatures

*Corrects `ARCHITECTURE.md`'s simplified module table where the real code differs.*

| Stage | Function | File:line | I/O |
|---|---|---|---|
| File discovery (used by `extract` CLI command) | `detect(root, *, follow_symlinks=None, google_workspace=None, extra_excludes=None, cache_root=None, gitignore=True) -> dict` | `graphify/detect.py:1238` | root path → classified file lists (code/doc/paper/image), gitignore-filtered |
| File discovery (standalone/watch/update) | `collect_files(target, *, follow_symlinks=False, root=None) -> list[Path]` | `graphify/extract.py:5248` | dir/file path → flat sorted list of extractable files |
| AST extraction | `extract(paths, cache_root=None, *, root=None, parallel=True, max_workers=None) -> dict` | `graphify/extract.py:4381` | file paths → `{"nodes":[...], "edges":[...], "input_tokens":0, "output_tokens":0}` |
| Semantic (LLM) extraction | `extract_corpus_parallel(...)` | `graphify/llm.py` | doc/paper/image paths → `{"nodes":[...], "edges":[...], "hyperedges":[...], tokens}` |
| Build (merge extractions) | `build(extractions, *, directed=False, dedup=True, root=None) -> nx.Graph` | `graphify/build.py:938` | list of extraction dicts → graph |
| Build (single dict) | `build_from_json(extraction, *, directed=False, root=None) -> nx.Graph` | `graphify/build.py:490` | one extraction dict → graph; runs schema validation internally |
| Build (incremental) | `build_merge(...)` | `graphify/build.py:1038` | new extractions + existing `graph.json` → merged graph |
| Cluster | `cluster(G, resolution=1.0, exclude_hubs_percentile=None) -> dict[int, list[str]]` | `graphify/cluster.py:134` | graph → `{community_id: [node_ids]}` (Leiden-based) |
| Cluster scoring | `score_all(G, communities) -> dict[int, float]` | `graphify/cluster.py:268` | → per-community cohesion score |
| Analyze — hubs | `god_nodes(G, top_n=10) -> list[dict]` | `graphify/analyze.py:101` | most-connected non-trivial nodes |
| Analyze — anomalies | `surprising_connections(G, communities, ...) -> list[dict]` | `graphify/analyze.py:125` | cross-community/cross-file "surprising" edges |
| Analyze — questions | `suggest_questions(...)` | `graphify/analyze.py:420` | suggested exploration questions for the report |
| Analyze — diff / cycles | `graph_diff(...)` / `find_import_cycles(...)` | `analyze.py:548` / `analyze.py:632` | graph comparison / import-cycle detection |
| Report | `generate(G, communities, cohesion_scores, community_labels, god_node_list, surprise_list, detection_result, token_cost, root, ...) -> str` | `graphify/report.py:71` | all analysis artifacts → Markdown text (written as `GRAPH_REPORT.md`) |
| Export — JSON | `to_json(G, communities, output_path, *, force=False, ...) -> bool` | `graphify/export.py:232` | writes `graph.json`; **refuses to shrink** the graph unexpectedly (issue #479 anti-data-loss guard) unless `force=True` |
| Export — HTML/Obsidian/Canvas/GraphML/SVG/Cypher | `to_html`, `to_obsidian`, `to_canvas`, `to_graphml`, `to_svg`, `to_cypher` | `graphify/export.py` (various) + `graphify/exporters/html.py` | one function per format, dispatched by `graphify export <format>` |
| Export — live graph DB push | `push_to_neo4j`, `push_to_falkordb` | `graphify/exporters/graphdb.py:9,80` | parameterized Cypher via the `neo4j`/`falkordb` SDKs |

## 6. CLI execution flow

**Startup**: `graphify <args>` (console script) or `python -m graphify` → `graphify/__main__.py:main()` (line 460) → `_run_cli()` (line 483). This reconfigures stdout/stderr to UTF-8, checks installed-skill version staleness, handles `-v`/`--help`/bare invocation, then:
1. Tries `dispatch_install_cli(cmd)` from `graphify/install.py:1929` — handles `install`/`uninstall`/all per-platform install commands. If matched, done.
2. Otherwise calls `dispatch_command(cmd)` in `graphify/cli.py:626` — a single large `if/elif` chain (not a registry) over ~30 subcommands, each with function-local lazy imports to keep bare CLI startup fast.

**Bare `graphify <path>` invocation** (no subcommand): `cli.py:3675` rewrites `sys.argv` to insert `"extract"` and re-enters `main()`. This is the "just run `graphify .`" convenience form.

**Three materially different "run the pipeline" commands** — a subtlety worth knowing before assuming they're interchangeable:

| Command | What it runs | Produces |
|---|---|---|
| `graphify extract <path>` (= bare `graphify <path>`) | detect → AST extract → semantic (LLM) extract for docs/papers/images not cache-hit → build → cluster → analyze → `to_json` | `graph.json` + `.graphify_analysis.json` **only** — deliberately stops before labeling/report so the agent-orchestrated skill.md flow can do LLM community-naming as its own step |
| `graphify cluster-only <path>` / `graphify label <path>` | loads existing `graph.json` → re-cluster → label communities (hub-based or LLM) → analyze → `generate()` report → `to_json`+`to_html` | `GRAPH_REPORT.md` + refreshed `graph.json`/`graph.html` — the "missing back half" of `extract` |
| `graphify update <path>` | delegates entirely to `graphify.watch._rebuild_code()`, which runs detect → AST extract (**no LLM step**) → build → cluster → analyze → report → export in one call | `graph.json` + `GRAPH_REPORT.md` + `graph.html` in one shot, code-only (no semantic re-extraction) |

**Full CLI command table** (branch locations in `graphify/cli.py` unless noted):

| Command | Purpose |
|---|---|
| `install` / `uninstall` / `<platform> install\|uninstall` | Install/remove the skill for one or all of 21+ AI tool platforms (`install.py`) |
| `provider list\|show\|add\|remove` | Manage custom LLM providers in `~/.graphify/providers.json` |
| `prs` | PR-related subcommands (`graphify/prs.py`) |
| `hook install\|uninstall\|status` | Git post-commit/post-checkout hook management (`graphify/hooks.py`) |
| `query "<question>"` | BFS/DFS scoped-subgraph text answer to a question |
| `affected "<node>"` | Reverse traversal — what depends on this node |
| `god-nodes` | List most-connected hub nodes |
| `save-result` / `reflect` | Feedback-loop: save a Q&A result / summarize `memory/` into `LESSONS.md` |
| `path "A" "B"` | Shortest path between two named nodes |
| `explain "X"` | Plain-language explanation of a node + neighbors |
| `diagnose multigraph` | Reports same-endpoint edge collapse risk |
| `add <url>` | Fetch a URL into the corpus (`graphify/ingest.py`) |
| `watch <path>` | Watch a folder, rebuild on change (`graphify/watch.py`) |
| `cluster-only` / `label` | Re-cluster + (re)label + regenerate report on an existing graph |
| `update <path>` | Full AST-only rebuild (no LLM) |
| `hook-check` / `hook-guard` / `check-update` | Editor/agent integration guards |
| `tree` | D3 collapsible-tree HTML view (`graphify/tree_html.py`) |
| `merge-driver` | Git merge driver for `graph.json` conflicts |
| `merge-graphs` | Merge two+ standalone `graph.json` files |
| `clone <url>` | Clone a GitHub repo, print its path |
| `export <format>` | html / callflow-html / obsidian / wiki / svg / graphml / neo4j / falkordb |
| `benchmark` | Token-reduction measurement vs. naive full-corpus reading |
| `global add\|remove\|list\|path` | Cross-project merged graph at `~/.graphify/global-graph.json` |
| `extract <path>` | Headless full pipeline (see table above) |
| `cache-check` / `merge-chunks` / `merge-semantic` | Internal commands supporting agent-orchestrated (skill.md) semantic extraction |

## 7. Serving mode (MCP)

`graphify-mcp` → `graphify/serve.py:_main` (line 1929). Builds one shared `mcp.server.Server("graphify")` (`_build_server`, `serve.py:1103`) reused by both transports:
- **stdio** (default): `serve()` at `serve.py:1713`.
- **Streamable HTTP** (MCP spec 2025-03-26): `serve_http()` at `serve.py:1871`, Starlette app (`_build_http_app`, `serve.py:1789`), optional API-key middleware (`_ApiKeyMiddleware`, `serve.py:1748`, pure-ASGI to avoid buffering SSE), DNS-rebinding protection. This is what the `Dockerfile` runs as a shared team service (`ENTRYPOINT ["python", "-m", "graphify.serve"]`, `EXPOSE 8080`).

**Tools exposed** (`list_tools()`, `serve.py:1192`): `query_graph`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `shortest_path`, `list_prs`, `get_pr_impact`, `triage_prs` — each accepts an optional `project_path` to multiplex several graphs from one server process, with an mtime/size-keyed graph cache (`_load_ctx`, `serve.py:1131`). `get_neighbors`/`get_community`/`query_graph` honor a `token_budget` (default 2000) with truncation announced at the **top** of the response, not just the bottom (`_cut_lines_to_budget`, `serve.py:925`).

**Resources**: `graphify://report`, `graphify://stats`, `graphify://god-nodes`, `graphify://surprises`, `graphify://audit`, `graphify://questions` — always read the server's default graph, not a per-call `project_path`.

Query scoring lives in `serve.py`, not `cli.py`: TF-IDF-like term scoring with a trigram inverted index (`_score_nodes`, `serve.py:351`), hub-degree throttling during BFS/DFS (p99 degree threshold) so traversal doesn't blow out through god-nodes, and edge-`context` filtering (call/import/field/parameter_type/...). `graphify query` (the CLI command) calls this same code (`_query_graph_text`).

## 8. Watch mode & git hooks

**`graphify watch <path>`** (`graphify/watch.py:watch`, line ~1396): uses `watchdog`, polling observer on macOS (FSEvents can miss rapid saves), native observer elsewhere. Debounces (default 3s), classifies the batch as code-only (→ AST-only `_rebuild_code()`) or containing docs/papers/images (→ writes a `graphify-out/needs_update` flag, no auto LLM call). Concurrency-safe via an advisory `fcntl.flock` per-repo rebuild lock, with a pending-changes queue so a concurrent hook's changes aren't dropped.

**`graphify hook install`** (`graphify/hooks.py`): installs a **post-commit** hook that spawns a detached background incremental rebuild (changed files only, `SIGALRM` timeout, resource limits) and a **post-checkout** hook that does a full rebuild on branch switches; also registers a git **merge driver** for `graph.json` so concurrent branch edits to the graph union-merge instead of conflicting. Both skip during rebase/merge/cherry-pick and inside linked worktrees.

## 9. Security model (`graphify/security.py`)

| Function | Guards against |
|---|---|
| `validate_url()` (`security.py:103`) | Non-http(s) schemes, cloud-metadata hostnames, private/loopback/CGN/link-local IP ranges (post-DNS-resolution) |
| `_SSRFGuardedHTTPConnection` (`security.py:180`) | DNS-rebind TOCTOU — resolves+validates once, connects to that literal IP |
| `_NoFileRedirectHandler` (`security.py:231`) | Open-redirect SSRF — re-validates every redirect target |
| `safe_fetch()` / `safe_fetch_text()` (`security.py:258,302`) | Unbounded downloads (50MB/10MB caps), non-2xx handling |
| `validate_graph_path()` (`security.py:315`) | Path traversal outside `graphify-out/` |
| `check_graph_file_size_cap()` (`security.py:357`) | Memory-exhaustion from a huge/crafted `graph.json` (default 512MiB cap) |
| `sanitize_label()` / `sanitize_metadata()` (`security.py:394,416`) | Control chars, oversized strings, unescaped HTML in exported labels |
| `_cypher_escape()`/`_cypher_label()` (`export.py:339`) | Cypher injection in the Neo4j/FalkorDB text export |
| `_yaml_str()` (`export.py:116`) | YAML-frontmatter injection in Obsidian export |

Full threat model and disclosure process: `SECURITY.md`.

## 10. Folder structure

```
graphify/                  Application package (~52,000 LOC, 65 files)
├── exporters/              4 files — output-format plugins (html.py, graphdb.py=neo4j+falkordb, base.py)
├── extractors/              29 files — per-language extraction plugins + shared engine.py/resolution.py
├── skills/                  GENERATED per-platform skill markdown (tracked; produced by tools/skillgen)
└── always_on/                GENERATED always-on instruction snippets
tests/                      159 test files (per-module / per-language / per-platform / per-regression)
└── fixtures/                 ~70 sample source files + multi-file cross-reference fixtures
tools/skillgen/              Build-time generator: fragments/*.md → graphify/skill*.md + skills/*/references/*.md
docs/                        Hand-written docs (how-it-works.md, RFCs) + docs/translations/ (33+ README translations)
scripts/                     One dev script (gen_demo_path.py)
worked/                      Example graphify outputs run against OTHER repos (httpx, karpathy-repos, ...) — demo artifacts
.github/workflows/           ci.yml, publish.yml, release-graph.yml
```

Package data note: `[tool.setuptools] packages = ["graphify", "graphify.extractors", "graphify.exporters"]` (`pyproject.toml`) — `graphify.skills`/`graphify.always_on` are **not** importable packages, they ship as static markdown via `[tool.setuptools.package-data]`.

## 11. Environment variables

Only needed for headless/CI extraction (`README.md:490-528` has the authoritative full table — summarized here):

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` / `ANTHROPIC_MODEL` | Claude backend config |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Gemini backend |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` | OpenAI-compatible backend (also local servers) |
| `DEEPSEEK_API_KEY`, `MOONSHOT_API_KEY` | DeepSeek / Kimi backends |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` / `GRAPHIFY_OLLAMA_*` | Local Ollama inference |
| `AZURE_OPENAI_*` | Azure OpenAI backend |
| `AWS_*` | Bedrock (standard credential chain, no API key) |
| `GRAPHIFY_MAX_WORKERS` | AST extraction parallelism |
| `GRAPHIFY_MAX_OUTPUT_TOKENS`, `GRAPHIFY_API_TIMEOUT`, `GRAPHIFY_MAX_RETRIES` | LLM call tuning |
| `GRAPHIFY_FORCE` | Force rebuild even if the graph would shrink |
| `GRAPHIFY_QUERY_LOG_ENABLE` / `GRAPHIFY_QUERY_LOG` / `GRAPHIFY_QUERY_LOG_DISABLE` / `GRAPHIFY_QUERY_LOG_RESPONSES` | Opt-in local query logging (off by default, `~/.cache/graphify-queries.log`) |
| `GRAPHIFY_MAX_GRAPH_BYTES` | Override the 512MiB graph.json size cap |
| `GRAPHIFY_TRIAGE_BACKEND` / `GRAPHIFY_TRIAGE_MODEL` | `graphify prs --triage` backend override |

**Nothing is required for local code-only use** — `graphify extract --code-only` runs fully offline via tree-sitter.

## 12. Testing, CI/CD, and deployment

- **Tests**: 159 files under `tests/`, organized per-module, per-language-extractor, per-platform-installer, and per-regression (`test_cross_extension_reexport_self_cycle.py`-style descriptive names, not issue numbers). Fixtures under `tests/fixtures/` (one sample file per language, plus multi-file cross-reference dirs like `crate_a/`+`crate_b/` for cross-crate Rust resolution). Run: `pytest tests/ -q`. `tests/conftest.py` mainly filters known third-party warnings.
- **CI** (`.github/workflows/ci.yml`, triggers on push/PR to `v1`-`v8`/`main`):
  - `skillgen-check` — validates generated skill files match `tools/skillgen/` fragments (5 sub-checks, full git history checkout required).
  - `test` — Python 3.10 and 3.12 matrix, `uv sync --all-extras --frozen`, `pytest`, then an end-to-end smoke test (`graphify --help`, `graphify install`).
  - `security-scan` — `bandit -r graphify -ll` + `pip-audit --strict`, currently `continue-on-error: true` (informational, not a merge gate).
- **Pre-commit** (`.pre-commit-config.yaml`): `skillgen-check` (local) + `ruff`.
- **Publish** (`.github/workflows/publish.yml`): on GitHub release published (or manual dispatch) — builds sdist+wheel via `uv build`, asserts `pyproject.toml` version matches the release tag, `twine check`, publishes to PyPI via OIDC trusted publishing (package name `graphifyy`).
- **release-graph** (`.github/workflows/release-graph.yml`): builds graphify's **own** self-graph (AST-only), runs `cluster-only --no-label`, exports HTML, bundles `graph.json`+`graph.html`+`GRAPH_REPORT.md` into `graphify-self-graph.tar.gz`, attaches it to the GitHub release.
- **Deployment**: `Dockerfile` packages the **MCP server as a shared HTTP service** (`python:3.12-slim`, `pip install ".[mcp]"`, non-root user, `ENTRYPOINT ["python", "-m", "graphify.serve"]`, `graph.json` mounted at runtime via `-v`, never baked into the image — issue #1143). `docs/docker-mcp-sqlite.md` is an unrelated third-party runbook (SQLite MCP server in Docker Desktop's MCP Toolkit), not documentation of graphify's own image.
- **Lint/typecheck**: ruff (`pyproject.toml [tool.ruff]`, deliberately conservative rule set `["E9","F63","F7","F82"]` — syntax/undefined-name only, noted as provisional), pyright (`basic` mode).

## 13. Recent project activity (from `CHANGELOG.md`, v0.9.17→0.9.24, 2026-07-16 to 2026-07-22)

Very high release velocity (near-daily point releases), almost entirely community-reported bug-fix regressions. Recurring themes: graph correctness/determinism (edge direction, path ordering, ID collisions), incremental-update/cache correctness (manifest stamping, atomic writes, shrink guards), cross-language import/re-export resolution edge cases, MCP/CLI output truncation and token budgets, and install/hook robustness across platforms. One notable feature in this window: opt-in strict PreToolUse hook mode (v0.9.19).

## 14. Known rough edges (flagged during this research pass — not fixed, just documented)

- **`graphify/cli.py` is a high-fan-in hub** (imports ~27 of the ~48 top-level `graphify` modules; `dispatch_command` is a single ~3,000-line `if/elif` chain rather than a command registry). See `graph.html` — it's visibly the most-connected node. Not necessarily a problem (lazy per-branch imports keep startup light), but it is the natural "start here" and "biggest blast radius" file.
- **`graphify/symbol_resolution.py`** (top-level, 554 lines — distinct from `graphify/extractors/resolution.py`, which *is* wired in) appears to be **dead code in production** — imported only by its own test (`tests/test_symbol_resolution.py`); `extract.py` never imports it. Likely a parked/in-progress replacement for logic still embedded ad hoc in `extract.py`, or orphaned. **[UNVERIFIED — could not confirm intent from changelog/issues.]**
- `ARCHITECTURE.md`'s module table describes a tidier, more aspirational shape (`analyze()`, `render_report()`, `export()`) than the actual code (`analyze.py` has no unary `analyze()`; the report function is `generate()`; `export.py` has one `to_*` function per format). This overview and `TECHNICAL_REFERENCE.md` use the verified real names.
- `graphify/extractors/csharp.py` is **not** the C# extractor (that's `extract_csharp()` in `extract.py` via the shared engine) — it currently only holds C#-specific cross-file *resolution* passes, a preview of where the extractor itself will land once config-driven languages migrate per `MIGRATION.md`.
