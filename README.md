<p align="center">
  <a href="https://graphifylabs.ai"><img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/logo.png" width="300" height="140" alt="Graphify"/></a>
</p>

<p align="center">
  <a href="https://trendshift.io/repositories/25296?utm_source=repository-badge&amp;utm_medium=badge&amp;utm_campaign=badge-repository-25296" target="_blank" rel="noopener noreferrer"><img src="https://trendshift.io/api/badge/repositories/25296" alt="Graphify-Labs%2Fgraphify | Trendshift" width="250" height="55"/></a>
</p>

<div align="center">
<details><summary><b>Read this in other languages</b></summary>

🇺🇸 <a href="README.md">English</a> | 🇨🇳 <a href="docs/translations/README.zh-CN.md">简体中文</a> | 🇯🇵 <a href="docs/translations/README.ja-JP.md">日本語</a> | 🇰🇷 <a href="docs/translations/README.ko-KR.md">한국어</a> | 🇩🇪 <a href="docs/translations/README.de-DE.md">Deutsch</a> | 🇫🇷 <a href="docs/translations/README.fr-FR.md">Français</a> | 🇪🇸 <a href="docs/translations/README.es-ES.md">Español</a> | 🇮🇳 <a href="docs/translations/README.hi-IN.md">हिन्दी</a> | 🇧🇷 <a href="docs/translations/README.pt-BR.md">Português</a> | 🇷🇺 <a href="docs/translations/README.ru-RU.md">Русский</a> | 🇸🇦 <a href="docs/translations/README.ar-SA.md">العربية</a> | 🇮🇷 <a href="docs/translations/README.fa-IR.md">فارسی</a> | 🇮🇹 <a href="docs/translations/README.it-IT.md">Italiano</a> | 🇵🇱 <a href="docs/translations/README.pl-PL.md">Polski</a> | 🇳🇱 <a href="docs/translations/README.nl-NL.md">Nederlands</a> | 🇹🇷 <a href="docs/translations/README.tr-TR.md">Türkçe</a> | 🇺🇦 <a href="docs/translations/README.uk-UA.md">Українська</a> | 🇻🇳 <a href="docs/translations/README.vi-VN.md">Tiếng Việt</a> | 🇮🇩 <a href="docs/translations/README.id-ID.md">Bahasa Indonesia</a> | 🇸🇪 <a href="docs/translations/README.sv-SE.md">Svenska</a> | 🇬🇷 <a href="docs/translations/README.el-GR.md">Ελληνικά</a> | 🇷🇴 <a href="docs/translations/README.ro-RO.md">Română</a> | 🇨🇿 <a href="docs/translations/README.cs-CZ.md">Čeština</a> | 🇫🇮 <a href="docs/translations/README.fi-FI.md">Suomi</a> | 🇩🇰 <a href="docs/translations/README.da-DK.md">Dansk</a> | 🇳🇴 <a href="docs/translations/README.no-NO.md">Norsk</a> | 🇭🇺 <a href="docs/translations/README.hu-HU.md">Magyar</a> | 🇹🇭 <a href="docs/translations/README.th-TH.md">ภาษาไทย</a> | 🇺🇿 <a href="docs/translations/README.uz-UZ.md">Oʻzbekcha</a> | 🇹🇼 <a href="docs/translations/README.zh-TW.md">繁體中文</a> | 🇵🇭 <a href="docs/translations/README.fil-PH.md">Filipino</a> | 🇮🇱 <a href="docs/translations/README.he-IL.md">עברית</a>

</details>
</div>

<p align="center">
  <a href="https://pypi.org/project/graphifyy/"><img src="https://img.shields.io/pypi/v/graphifyy" alt="PyPI"/></a>
  <a href="https://pepy.tech/project/graphifyy"><img src="https://img.shields.io/pepy/dt/graphifyy?color=blue&label=downloads" alt="Downloads"/></a>
  <a href="https://discord.gg/598Ad9zQZ"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://www.linkedin.com/company/graphify-labs"><img src="https://img.shields.io/badge/LinkedIn-Graphify%20Labs-0077B5?logo=linkedin" alt="LinkedIn"/></a>
  <a href="https://www.ycombinator.com/companies/graphify"><img src="https://img.shields.io/badge/Y%20Combinator-S26-F0652F?style=flat&logo=ycombinator&logoColor=white" alt="YC S26"/></a>
</p>

Type `/graphify` in your AI coding assistant and it maps your entire project (code, docs, PDFs, images, videos) into a **knowledge graph** you can **query instead of grepping** through files.

- **Code maps for free, fully local.** Code is parsed with tree-sitter AST: deterministic, no LLM, nothing leaves your machine. (Docs, PDFs, images and video use your assistant's model, or a configured API key, for a semantic pass.)
- **Every edge is explained.** Each connection is tagged `EXTRACTED` (explicit in the source) or `INFERRED` (resolved by graphify), so you can tell what was read directly from what was inferred.
- **Not a vector index.** No embeddings, no vector store: a real graph you traverse. Ask a question, trace the path between two things, or explain one concept.

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/graph-hero.png" alt="graphify's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>The FastAPI codebase mapped by graphify. Every node is a concept, colors are detected communities, and the whole thing is clickable in graph.html.</em>
</p>

**Get started** (30 seconds):

```bash
uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # register the skill with your AI assistant
```

Then, in your AI assistant:

```
/graphify .
```

That's it. You get **three files**:

This is the MaluDb fork of [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify). Upstream graphify maps a project — code, docs, PDFs — into a queryable knowledge graph (`graphify-out/graph.json`) using tree-sitter AST extraction, with zero LLM cost for code. This fork adds a MaluDb export path on top of that: the graph is persisted into MaluDb as subjects and statements, and application code is linked to your database data model, so agents using MaluDb memory can answer questions like *"which files write to `orders`?"* directly from memory.

**Works in** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot, and 15+ more — [pick your platform](#install).

---

## See it in action

<p align="center">
  <img src="https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/demo-path.svg" alt="graphify path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

Once the graph is built you query it instead of reading files. Real output, graphify run on the FastAPI codebase shown above:

```text
$ graphify explain "APIRouter"
Node: APIRouter
  Source:    routing.py L2210
  Community: 2
  Degree:    47

Connections (47):
  --> RequestValidationError [uses] [INFERRED]
  --> Dependant [uses] [INFERRED]
  --> .get() [method] [EXTRACTED]
  <-- __init__.py [imports] [EXTRACTED]
  ...

$ graphify path "FastAPI" "ModelField"
Shortest path (3 hops):
  FastAPI --uses--> DefaultPlaceholder <--references-- get_request_handler() --references--> ModelField
```

Every edge carries a **confidence tag** (`EXTRACTED` = explicit in the source, `INFERRED` = derived by resolution), so you can tell what was read directly from what was inferred. `graphify query "<question>"` returns a scoped subgraph for a plain-language question, and `graphify path A B` traces how any two things connect.

---

## What it does

What you get out of the box:

| Capability | What you get |
|---|---|
| **God nodes** | The most-connected concepts, so you see what everything flows through |
| **Communities** | The graph split into subsystems (Leiden), with LLM-free labels |
| **Cross-file links** | `calls` / `imports` / `inherits` / `mixes_in` resolved across ~40 languages via tree-sitter AST |
| **Query, path, explain** | Ask a question, trace the path between two things, or explain one concept, all against `graph.json` |
| **Rationale + doc refs** | `# NOTE:` / `# WHY:` comments and ADR/RFC citations become first-class nodes linked to the code |
| **Beyond code** | Docs, PDFs, images, and video/audio all map into the same graph |
| **Local-first** | Code is parsed locally with tree-sitter (no LLM, nothing leaves your machine); only the semantic pass over docs/media calls a backend, and only if you configure one |

---

## How the graph maps to MaluDb

| Benchmark | Metric | graphify | Field |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | QA accuracy | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | QA accuracy | **76%** | tied with dense RAG |
| Graph build | LLM credits | **0** | per-token for most systems |

| graphify | MaluDb |
|---|---|
| Node | Subject with canonical name `<namespace>/<node id>`; the node label becomes an alias |
| Edge | Statement (subject–verb–object); the edge relation is the verb |
| Confidence `EXTRACTED` / `INFERRED` / `AMBIGUOUS` | Statement confidence `1.0` / `0.7` / `0.4` |
| Community assignment | Carried on the node payload |

The server upserts idempotently — re-pushing the same graph updates rather than duplicates, so it is safe to re-export after every rebuild.

## Prerequisites

- **Python 3.10+** and [uv](https://docs.astral.sh/uv/) (recommended) or pipx/pip
- **A running MaluDb API server** and a bearer token (mint one via the server's `/v1/tokens` endpoint)
- For `--postgres` introspection: network access to the target PostgreSQL database

## Installation

If `uv` is not installed yet (`uv --version` fails), install it first and open a new shell:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install from this fork (the PyPI package `graphifyy` is upstream and does not include the MaluDb exporter):

```bash
# From a clone (recommended for development):
git clone https://github.com/maludb/graphify.git
cd graphify
uv tool install .

# With the PostgreSQL introspection and SQL-parsing extras:
uv tool install ".[postgres,sql]"

# Or directly from GitHub without cloning:
uv tool install "graphifyy[postgres,sql] @ git+https://github.com/maludb/graphify.git"
```

The CLI command is `graphify`. If the command is not found after install, run `uv tool update-shell` and open a new terminal.

The base install needs **no API keys and no extras** for code-only extraction — AST parsing runs fully offline. The two extras used by this fork:

| Extra | What it adds |
|---|---|
| `postgres` | `graphify extract --postgres <DSN>` live schema introspection (`psycopg`) |
| `sql` | tree-sitter-sql parsing for `.sql` files and SQL-statement analysis |

## Configuration

The MaluDb exporter reads two environment variables so credentials stay off the command line (and out of `ps` output / shell history):

| Platform | Install command |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (auto-detected) or `graphify install --platform windows` |
| CodeBuddy | `graphify install --platform codebuddy` |
| Codex | `graphify install --platform codex` |
| OpenCode | `graphify install --platform opencode` |
| Kilo Code | `graphify install --platform kilo` |
| GitHub Copilot CLI | `graphify install --platform copilot` |
| VS Code Copilot Chat | `graphify vscode install` |
| Aider | `graphify install --platform aider` |
| OpenClaw | `graphify install --platform claw` |
| Factory Droid | `graphify install --platform droid` |
| Trae | `graphify install --platform trae` |
| Trae CN | `graphify install --platform trae-cn` |
| Gemini CLI | `graphify install --platform gemini` |
| Hermes | `graphify install --platform hermes` |
| Kimi Code | `graphify install --platform kimi` |
| Amp | `graphify amp install` |
| Agent Skills (cross-framework) | `graphify install --platform agents` (alias `--platform skills`) |
| Kiro IDE/CLI | `graphify kiro install` |
| Pi coding agent | `graphify install --platform pi` |
| Cursor | `graphify cursor install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

Codex users also need `multi_agent = true` under `[features]` in `~/.codex/config.toml` for parallel extraction. CodeBuddy uses the same Agent tool and PreToolUse hook mechanism as Claude Code. Factory Droid uses the `Task` tool for parallel subagent dispatch. OpenClaw and Aider use sequential extraction (parallel agent support is still early on those platforms). Trae uses the Agent tool for parallel subagent dispatch and does **not** support `PreToolUse` hooks, so AGENTS.md is the always-on mechanism.

`--platform agents` (alias `--platform skills`) targets the generic cross-framework [Agent-Skills](https://github.com/anthropics/skills) locations: the spec's user-global `~/.agents/skills/` (read by `npx skills` and spec-compliant frameworks) for a global install, and `./.agents/skills/` for a project (`--project`) install. The bare `graphify install` stays single-platform (Claude Code) by design — use the named `agents` platform when you want the skill discoverable by any framework that reads `.agents/skills`.

> Codex uses `$graphify` instead of `/graphify`.

</details>

<details>
<summary><b>Optional extras</b> (install only what you need)</summary>

| Extra | What it adds | Install |
|---|---|---|
| `pdf` | PDF extraction | `uv tool install "graphifyy[pdf]"` |
| `office` | `.docx` and `.xlsx` support | `uv tool install "graphifyy[office]"` |
| `google` | Google Sheets rendering | `uv tool install "graphifyy[google]"` |
| `video` | Video/audio transcription (faster-whisper + yt-dlp) | `uv tool install "graphifyy[video]"` |
| `mcp` | MCP stdio server | `uv tool install "graphifyy[mcp]"` |
| `neo4j` | Neo4j push support | `uv tool install "graphifyy[neo4j]"` |
| `falkordb` | FalkorDB push support | `uv tool install "graphifyy[falkordb]"` |
| `svg` | SVG graph export | `uv tool install "graphifyy[svg]"` |
| `leiden` | Leiden community detection (Python < 3.13 only) | `uv tool install "graphifyy[leiden]"` |
| `ollama` | Ollama local inference | `uv tool install "graphifyy[ollama]"` |
| `openai` | OpenAI / OpenAI-compatible APIs | `uv tool install "graphifyy[openai]"` |
| `gemini` | Google Gemini API | `uv tool install "graphifyy[gemini]"` |
| `anthropic` | Anthropic Claude API (`--backend claude`, uses `ANTHROPIC_API_KEY`) | `uv tool install "graphifyy[anthropic]"` |
| `bedrock` | AWS Bedrock (uses IAM, no API key) | `uv tool install "graphifyy[bedrock]"` |
| `azure` | Azure OpenAI Service (`--backend azure`, uses `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT`) | `uv tool install "graphifyy[openai]"` |
| `sql` | SQL schema extraction | `uv tool install "graphifyy[sql]"` |
| `postgres` | Live PostgreSQL introspection (`--postgres DSN`) | `uv tool install "graphifyy[postgres]"` |
| `dm` | BYOND DreamMaker `.dm`/`.dme` AST extraction (may need a C compiler + `python3-dev` if no wheel matches your platform) | `uv tool install "graphifyy[dm]"` |
| `terraform` | Terraform / HCL `.tf`/`.tfvars`/`.hcl` AST extraction | `uv tool install "graphifyy[terraform]"` |
| `pascal` | Pascal / Delphi `.pas`/`.dpr`/`.dpk`/`.inc` AST extraction (more accurate `calls`/`inherits` edges; falls back to a regex extractor when absent) | `uv tool install "graphifyy[pascal]"` |
| `chinese` | Chinese query segmentation (jieba) | `uv tool install "graphifyy[chinese]"` |
| `all` | Everything above | `uv tool install "graphifyy[all]"` |

</details>

---

## Make your assistant always use the graph

Run this once in your project after building a graph:

| Platform | Command |
|----------|---------|
| Claude Code | `graphify claude install` |
| CodeBuddy | `graphify codebuddy install` |
| Codex | `graphify codex install` |
| OpenCode | `graphify opencode install` |
| Kilo Code | `graphify kilo install` |
| GitHub Copilot CLI | `graphify copilot install` |
| VS Code Copilot Chat | `graphify vscode install` |
| Aider | `graphify aider install` |
| OpenClaw | `graphify claw install` |
| Factory Droid | `graphify droid install` |
| Trae | `graphify trae install` |
| Trae CN | `graphify trae-cn install` |
| Cursor | `graphify cursor install` |
| Gemini CLI | `graphify gemini install` |
| Hermes | `graphify hermes install` |
| Kimi Code | `graphify install --platform kimi` |
| Amp | `graphify amp install` |
| Agent Skills (cross-framework) | `graphify agents install` (alias `graphify skills install`) |
| Kiro IDE/CLI | `graphify kiro install` |
| Pi coding agent | `graphify pi install` |
| Devin CLI | `graphify devin install` |
| Google Antigravity | `graphify antigravity install` |

This writes a small config file that tells your assistant to consult the knowledge graph for codebase questions, preferring scoped queries like `graphify query "<question>"` over reading the full report or grepping raw files.

- **Hook platforms** (Claude Code, Gemini CLI): a hook fires automatically before search-style tool calls (and, on Claude Code, before reading source files one by one via the Read/Glob tools) and nudges your assistant toward the graph path.
- **Instruction-file platforms** (Codex, OpenCode, Cursor, etc.): persistent instruction files (`AGENTS.md`, `.cursor/rules/`, etc.) provide the same query-first guidance.

`GRAPH_REPORT.md` is still available for broad architecture review.

**CodeBuddy** does the same two things as Claude Code: writes a `CODEBUDDY.md` section telling CodeBuddy to read `graphify-out/GRAPH_REPORT.md` before answering architecture questions, and installs `PreToolUse` hooks (`.codebuddy/settings.json`) that fire before Bash search commands and file reads, nudging toward `graphify query` instead.

**Codex** writes to `AGENTS.md` and also installs a `PreToolUse` hook in `.codex/hooks.json` that fires before every Bash tool call, same always-on mechanism as Claude Code.

**Kilo Code** installs the Graphify skill to `~/.config/kilo/skills/graphify/SKILL.md` and a native `/graphify` command to `~/.config/kilo/command/graphify.md`. `graphify kilo install` also writes `AGENTS.md` plus a native `tool.execute.before` plugin (`.kilo/plugins/graphify.js` + `.kilo/kilo.json` or `.kilo/kilo.jsonc` registration) so Kilo gets the same always-on graph reminder behavior through native `.kilo` config.

**Cursor** writes `.cursor/rules/graphify.mdc` with `alwaysApply: true`, so Cursor includes it in every conversation automatically, no hook needed.

To remove graphify from all platforms at once: `graphify uninstall` (add `--purge` to also delete `graphify-out/`). Or use the per-platform command (e.g. `graphify claude uninstall`).

---

## What's in the report

- **God nodes** — the most-connected concepts in your project. Everything flows through these.
- **Surprising connections** — links between things that live in different files or modules. Ranked by how unexpected they are.
- **The "why"** — inline comments (`# NOTE:`, `# WHY:`, `# HACK:`), docstrings, and design rationale from docs are extracted as separate nodes linked to the code they explain.
- **Suggested questions** — 4–5 questions the graph is uniquely positioned to answer.
- **Confidence tags** — every inferred relationship is marked `EXTRACTED`, `INFERRED`, or `AMBIGUOUS`. You always know what was found vs guessed.

---

## What files it handles

| Type | Extensions |
|------|-----------|
| Code (36 tree-sitter grammars) | `.py .ts .mts .cts .js .jsx .tsx .mjs .go .rs .java .c .cpp .cc .cxx .h .hpp .cu .cuh .metal .rb .cs .kt .kts .scala .php .swift .lua .luau .toc .zig .ps1 .psm1 .psd1 .ex .exs .m .mm .jl .vue .svelte .astro .groovy .gradle .dart .v .sv .svh .sql .f .f90 .f95 .f03 .f08 .pas .pp .dpr .dpk .lpr .inc .dfm .lfm .lpk .sh .bash .json .dm .dme .dmi .dmm .dmf .sln .slnx .csproj .fsproj .vbproj .xaml .razor .cshtml` (`.dm`/`.dme` requires `uv tool install graphifyy[dm]`; `.mts`/`.cts` reuse the TypeScript grammar, `.cc`/`.cxx` and CUDA `.cu`/`.cuh` and Metal `.metal` reuse the C++ grammar) |
| Salesforce Apex | `.cls .trigger` (regex-based; classes, interfaces, enums, methods, triggers, SOQL/DML edges) |
| Terraform / HCL | `.tf .tfvars .hcl` (requires `uv tool install graphifyy[terraform]`) |
| MCP configs | `.mcp.json` `mcp.json` `mcp_servers.json` `claude_desktop_config.json` — extracts server nodes, package refs, env var requirements |
| Package manifests | `apm.yml` `pyproject.toml` `go.mod` `pom.xml` — one canonical package node per package (by name) plus `depends_on` edges, so a package referenced from many manifests is a single hub |
| Docs | `.md .mdx .qmd .html .txt .rst .yaml .yml` (markdown `[text](./other.md)` links and `[[wikilinks]]` become `references` edges between docs) |
| Office | `.docx .xlsx` (requires `uv tool install graphifyy[office]`) |
| Google Workspace | `.gdoc .gsheet .gslides` (opt-in; requires `gws` auth and `--google-workspace`; Sheets need `uv tool install graphifyy[google]`) |
| PDFs | `.pdf` |
| Images | `.png .jpg .webp .gif` |
| Video / Audio | `.mp4 .mov .mp3 .wav` and more (requires `uv tool install graphifyy[video]`) |
| YouTube / URLs | any video URL (requires `uv tool install graphifyy[video]`) |

Code is extracted **locally with no API calls** (AST via tree-sitter). Everything else goes through your AI assistant's model API.

Google Drive for desktop `.gdoc`, `.gsheet`, and `.gslides` files are shortcut
pointers, not document content. To include native Google Docs, Sheets, and Slides
in a headless extraction, install and authenticate the
[`gws` CLI](https://github.com/googleworkspace/cli), then run:

```bash
uv tool install "graphifyy[google]"  # needed for Google Sheets table rendering
gws auth login -s drive
graphify extract ./docs --google-workspace
```

You can also set `GRAPHIFY_GOOGLE_WORKSPACE=1`. Graphify exports shortcuts into
`graphify-out/converted/` as Markdown sidecars, then extracts those files.

---

## Common commands

```bash
export MALUDB_URL="http://localhost:8000"
export MALUDB_TOKEN="<your-token>"
```

### `graphify export maludb` flags

| Flag | Default | Purpose |
|---|---|---|
| `--push URL` | `$MALUDB_URL` | MaluDb API server base URL (http/https) |
| `--token T` | `$MALUDB_TOKEN` | Bearer token |
| `--namespace NS` | project directory name | Namespace prefix for all subjects created by this import |
| `--graph PATH` | `graphify-out/graph.json` | Graph file to push |
| `--sql-usage` | off | Mine SQL table references from source files and push them as extra cross-namespace links |
| `--source-root DIR` | the graph's project directory | Root the graph's `source_file` paths are resolved against for SQL scanning |
| `--db-schema S` | `public` | Schema assumed for unqualified table names found in SQL |
| `--datamodel-ns NS` | `datamodel` | Namespace of the data-model graph the mined links point at |

## Quick start

### 1. Build a code graph

```bash
cd ~/my-app
graphify extract .        # AST-only, offline, no API key needed
```

This writes `graphify-out/graph.json` (plus `graph.html` and `GRAPH_REPORT.md`). Inside Claude Code you can run `/graphify .` instead — same output.

### 2. Push it to MaluDb

```bash
graphify export maludb
# Pushed to MaluDb (http://localhost:8000, namespace 'my-app'):
#   1842 nodes (1842 new, 0 updated), 5210 edges (5210 new)
```

The namespace defaults to the project directory name; pass `--namespace` to control it.

### 3. Push your data model

Build a graph of the live database schema and push it under the `datamodel` namespace:

```bash
graphify extract --postgres "postgresql://user:pass@host/db"
graphify export maludb --namespace datamodel
```

Every table becomes a typed `table` node carrying real catalog metadata — columns with types and nullability, primary-key columns, and unique constraints (including unique indexes not declared as constraints). Foreign keys become edges between tables. If you keep DDL in the repo instead, plain `graphify extract` on a directory containing `.sql` files produces the same typed nodes from the `CREATE TABLE` statements.

| Variable | Used for | When required |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude (Anthropic) backend | `--backend claude` |
| `ANTHROPIC_BASE_URL` | Anthropic-compatible endpoint URL (LiteLLM proxy, gateways, ...) | `--backend claude` (default: `https://api.anthropic.com`) |
| `ANTHROPIC_MODEL` | Model name for the Claude backend — for custom endpoints, use the model name/alias your server exposes | `--backend claude` (default: `claude-sonnet-4-6`) |
| `GEMINI_API_KEY` or `GOOGLE_API_KEY` | Google Gemini backend | `--backend gemini` |
| `OPENAI_API_KEY` | OpenAI or OpenAI-compatible APIs | `--backend openai` (local servers accept any non-empty value) |
| `OPENAI_BASE_URL` | OpenAI-compatible server URL (llama.cpp, vLLM, LM Studio, ...) | `--backend openai` (default: `https://api.openai.com/v1`) |
| `OPENAI_MODEL` | Model name for the OpenAI backend — for self-hosted servers, use the model name/alias your server exposes (check its `/v1/models` endpoint), e.g. `LFM2.5-8B-A1B-UD-Q4_K_XL` for llama.cpp | `--backend openai` (default: `gpt-4.1-mini`) |
| `DEEPSEEK_API_KEY` | DeepSeek backend | `--backend deepseek` |
| `MOONSHOT_API_KEY` | Kimi Code backend | `--backend kimi` |
| `OLLAMA_BASE_URL` | Ollama local inference URL | `--backend ollama` (default: `http://localhost:11434`) |
| `OLLAMA_MODEL` | Ollama model name | `--backend ollama` (default: auto-detect) |
| `GRAPHIFY_OLLAMA_NUM_CTX` | Override Ollama KV-cache window size | optional — auto-sized by default |
| `GRAPHIFY_OLLAMA_KEEP_ALIVE` | Minutes to keep Ollama model loaded | optional — set `0` to unload after each chunk |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI Service backend | `--backend azure` |
| `AZURE_OPENAI_ENDPOINT` | Azure resource endpoint URL | `--backend azure` (required alongside API key) |
| `AZURE_OPENAI_API_VERSION` | Azure API version override | optional — default `2024-12-01-preview` |
| `AZURE_OPENAI_DEPLOYMENT` or `GRAPHIFY_AZURE_MODEL` | Azure deployment name | optional — default `gpt-4o` |
| `AWS_*` / `~/.aws/credentials` | AWS Bedrock — standard credential chain | `--backend bedrock` (no API key, uses IAM) |
| `GRAPHIFY_MAX_WORKERS` | AST parallelism thread count | optional — also `--max-workers` flag |
| `GRAPHIFY_MAX_OUTPUT_TOKENS` | Raise output cap for dense corpora | optional — e.g. `32768` for large files |
| `GRAPHIFY_API_TIMEOUT` | Per-call timeout in seconds for HTTP, claude-cli, and Anthropic SDK backends (default: 600) | optional — also `--api-timeout` flag |
| `GRAPHIFY_MAX_RETRIES` | How many times to retry a rate-limited (429) request before giving up (default: 6; honors `Retry-After`) | optional — raise for strict per-org limits (e.g. kimi); `0` disables |
| `GRAPHIFY_FORCE` | Force graph rebuild even with fewer nodes | optional — also `--force` flag |
| `GRAPHIFY_GOOGLE_WORKSPACE` | Auto-enable Google Workspace export | optional — set to `1` |
| `GRAPHIFY_TRIAGE_BACKEND` | Backend for `graphify prs --triage` | optional — auto-detected from available keys |
| `GRAPHIFY_TRIAGE_MODEL` | Model override for triage | optional — e.g. `claude-opus-4-7` |
| `GRAPHIFY_QUERY_LOG` | Override query log path (default: `~/.cache/graphify-queries.log`) | optional — set to empty or `/dev/null` to silence |
| `GRAPHIFY_QUERY_LOG_DISABLE` | Set to `1` to disable query logging entirely | optional |
| `GRAPHIFY_QUERY_LOG_RESPONSES` | Set to `1` to also log full subgraph responses (off by default) | optional |
| `GRAPHIFY_MAX_GRAPH_BYTES` | Override the 512 MiB graph.json size cap — e.g. `700MB`, `2GB`, or plain bytes | optional — useful for very large corpora |
| `GRAPHIFY_LLM_TEMPERATURE` | Override LLM temperature for semantic extraction — e.g. `0.7`, or `none` to omit | optional — auto-omitted for o1/o3/o4/gpt-5 reasoning models |

---

## Privacy

- **Code files** — processed locally via tree-sitter. Nothing leaves your machine. A code-only corpus requires no API key — `graphify extract` runs fully offline.
- **Video / audio** — transcribed locally with faster-whisper. Nothing leaves your machine.
- **Docs, PDFs, images** — sent to your AI assistant for semantic extraction (via the `/graphify` skill, using whatever model your IDE session runs). Headless `graphify extract` requires `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), a running Ollama instance (`OLLAMA_BASE_URL`), AWS credentials via the standard provider chain (Bedrock - no API key needed, uses IAM), or the `claude` CLI binary (Claude Code - no API key needed, uses your Claude subscription). The `--dedup-llm` flag uses the same key.
- **Data residency** — `graphify extract` auto-detects which provider to use based on which API key is set (priority: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). For code with data-residency requirements, use `--backend ollama` (fully local) or pass an explicit `--backend` flag. Kimi (`MOONSHOT_API_KEY`) routes to Moonshot AI servers in China.
- **No telemetry**, no usage tracking, no analytics.
- **Query logging** — every `graphify query`, `graphify path`, `graphify explain`, and MCP `query_graph` call is logged to `~/.cache/graphify-queries.log` in JSON Lines format (timestamp, question, corpus, nodes returned, duration). Full subgraph responses are **not** stored by default. Set `GRAPHIFY_QUERY_LOG_DISABLE=1` to opt out, or `GRAPHIFY_QUERY_LOG=/dev/null` to silence without disabling the code path.

---

## Troubleshooting

**`graphify: command not found` after installing**
The CLI is installed but its bin directory isn't on your shell's `PATH`. Pick the fix for how you installed:
- **uv** (`uv tool install graphifyy`): the command lands in uv's tool bin dir (`~/.local/bin`), which a fresh macOS/zsh setup often doesn't have on `PATH`. Run `uv tool update-shell`, then open a new terminal. (Find the dir with `uv tool dir --bin`.)
- **pipx** (`pipx install graphifyy`): run `pipx ensurepath`, then open a new terminal.
- **pip** (`pip install graphifyy`): pip installs scripts to a user bin dir that may not be on `PATH` — add `~/Library/Python/3.x/bin` (macOS) or `~/.local/bin` (Linux) to your `PATH` in `~/.zshrc`/`~/.bashrc`, or just run `python -m graphify`.

**`uvx graphify …` or `uv tool run graphify …` fails to resolve `graphify`**
The PyPI package is `graphifyy`; `graphify` is only the command it provides. `uv tool run` treats the first word as a *package name*, so it looks for a package called `graphify` and reports `No solution found … no versions of graphify`. Name the package explicitly: `uvx --from graphifyy graphify install` (same as `uv tool run --from graphifyy graphify install`). Or `uv tool install graphifyy` once and then call `graphify` directly.

**`python -m graphify` works but `graphify` command doesn't**
Your shell's `PATH` doesn't include the bin directory the command was installed to. Prefer `uv tool install` / `pipx install` over plain `pip`, then run `uv tool update-shell` / `pipx ensurepath` and open a new terminal (see the install notes above).

Re-push the code graph with SQL-usage mining enabled:

```bash
cd ~/my-app
graphify export maludb --sql-usage
# sql-usage: 317 table-reference links mined from /home/me/my-app
# Pushed to MaluDb (...): 1842 nodes (0 new, 1842 updated), 5527 edges (317 new)
```

The miner scans each source file that appears in the graph (Python, PHP, TypeScript/JavaScript, Rust, Go, Ruby, Java, Kotlin, C#, C/C++, Perl, and `.sql`) for `INSERT INTO` / `UPDATE … SET` / `DELETE FROM` (→ `writes` links) and `FROM` / `JOIN` (→ `reads` links). Each hit becomes a link from the file's node to `datamodel/<schema>.<table>`, pushed with the server's `resolve_external` option: targets that exist in the tenant's data-model graph resolve into real edges; unknown targets land in the import report's `skipped` list rather than failing the import.

The mining is deliberately regex-based — the goal is `INFERRED`-confidence "this file touches that table" edges, not full query understanding. System catalogs (`pg_catalog`, `information_schema`, `pg_*`), SQL set-returning functions, and interpolated/placeholder names are filtered out.

## Typical workflow

```bash
# one-time
export MALUDB_URL=... MALUDB_TOKEN=...
graphify extract --postgres "$DATABASE_URL"      # data-model graph
graphify export maludb --namespace datamodel

# per repository, repeat after significant changes
cd ~/repos/my-app
graphify extract .
graphify export maludb --sql-usage

# then query the graph locally...
graphify query "what writes to the orders table?"
# ...or let any MaluDb-connected agent answer from memory
```

`graphify hook install` (upstream feature) rebuilds the graph on every git commit; re-run the export afterwards to keep MaluDb in sync.

- [How it works](docs/how-it-works.md) — the extraction pipeline, community detection, confidence scoring, benchmarks
- [ARCHITECTURE.md](ARCHITECTURE.md) — module breakdown, how to add a language
- [Optional integrations](docs/docker-mcp-sqlite.md) — Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo) — the book on the ideas behind graphify, the architecture end to end

---

## Built on graphify: Penpax

**`error: --push URL (or MALUDB_URL) required`** — set `MALUDB_URL` or pass `--push http://host:port`. Only `http`/`https` schemes are accepted.

**`error: --token (or MALUDB_TOKEN) required`** — mint a bearer token on the MaluDb server (`/v1/tokens`) and export it as `MALUDB_TOKEN`.

**`MaluDb import failed: HTTP 401/403`** — the token is invalid or lacks write access for the tenant.

**`--sql-usage` mined 0 links** — the scanner resolves the graph's `source_file` paths against `--source-root` (default: the graph's project directory, i.e. the parent of `graphify-out/`). If you moved `graph.json` or run from elsewhere, pass `--source-root` explicitly.

**Mined links all land in `skipped`** — the targets are `<datamodel-ns>/<schema>.<table>`; make sure the data-model graph was pushed under the same namespace (`--datamodel-ns`, default `datamodel`) and that unqualified names match your schema (`--db-schema`, default `public`).

**`--postgres` fails to import psycopg** — install the extra: `uv tool install ".[postgres]"`.

## Development

```bash
git clone https://github.com/maludb/graphify.git
cd graphify
uv sync --all-extras          # venv + all extras + dev group (pytest, ruff, pyright)

uv run pytest tests/ -q                       # full suite
uv run pytest tests/test_export.py -q         # MaluDb exporter tests
uv run pytest tests/test_pg_introspect.py -q  # PostgreSQL introspection tests
```

Fork-specific code lives in:

- `graphify/export.py` — `push_to_maludb()` (stdlib `urllib`, no extra dependency)
- `graphify/sql_usage.py` — SQL-usage mining (code file → table links)
- `graphify/pg_introspect.py` — live PostgreSQL schema introspection with catalog metadata
- `graphify/__main__.py` — the `graphify export maludb` CLI wiring

To pull upstream improvements:

```bash
git remote add upstream https://github.com/Graphify-Labs/graphify
git fetch upstream && git merge upstream/v8
```

## Related MaluDb repositories

- [maludb-core](https://github.com/maludb/maludb-core) — the memory database (PostgreSQL 17 extension)
- API servers: [maludb-lamp-api-server](https://github.com/maludb/maludb-lamp-api-server) (reference), [maludb-python-api-server](https://github.com/maludb/maludb-python-api-server), [maludb-fastify-api-server](https://github.com/maludb/maludb-fastify-api-server) — any of them accepts `graphify export maludb`
- [maludb-terminal](https://github.com/maludb/maludb-terminal) — Rust CLI + MCP server for querying the memory the graph lands in

MaluDb is an open-source memory database supported by [Kinetic Seas Incorporated](https://kineticseas.com).

## License

<p align="center">
  <a href="https://star-history.com/#safishamsi/graphify&Date">
    <img src="https://api.star-history.com/svg?repos=safishamsi/graphify&type=Date" alt="Star History Chart" width="370"/>
  </a>
</p>

---

## Community and links

<p align="center">
  <a href="https://discord.gg/598Ad9zQZ"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/graphifyy"><img src="https://img.shields.io/badge/X-graphifyy-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
