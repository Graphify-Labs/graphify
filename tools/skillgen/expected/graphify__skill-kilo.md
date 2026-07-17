---
name: graphify
description: "Use for any question about a codebase, its architecture, file relationships, or project content — especially when graphify-out/ exists, where the question should be treated as a graphify query first. Turns any input (code, docs, papers, images, videos) into a persistent knowledge graph with god nodes, community detection, and query/path/explain tools."
---

# /graphify

Turn a folder of code and documents into an embedded Helix knowledge graph, interactive exports, and a plain-language `GRAPH_REPORT.md`.

## Usage

```text
/graphify [path]                                      # build or rebuild the native graph
/graphify <path> --update                             # incrementally update changed files
/graphify <path> --cluster-only                       # rerun clustering and analysis
/graphify <path> --no-viz                             # omit HTML visualization
/graphify <path> --svg | --graphml | --wiki           # presentation exports
/graphify <path> --neo4j | --falkordb                 # database exports
/graphify <path> --mcp                                # start the MCP server
/graphify <path> --watch                              # rebuild on changes
/graphify add <url>                                   # add a source and update
/graphify query "<question>"                          # query the active Helix generation
/graphify path "AuthModule" "Database"                # native shortest path
/graphify explain "SwinTransformer"                   # explain one native node
```

## What graphify is for

Graphify stores topology, communities, analysis, extraction cache, hashes, learning state, and generation metadata together in `graphify-out/graph.helix`. Every production command reads an immutable native snapshot. Presentation formats are exports, never runtime storage.

## What You Must Do When Invoked

For `--help` or `-h`, print the Usage block and stop. Otherwise default the source path to `.`.

**Fast path — existing graph:** if `graphify-out/graph.helix` exists and the user asks a codebase question, run `graphify query "<question>"` immediately. Do not rebuild unless requested.

If only an obsolete-format graph file exists, do not read, migrate, overwrite, or delete it. Tell the user that the format is obsolete and run a source rebuild to create `graphify-out/graph.helix`.

### Step 0 - GitHub repos and multi-path merge (only if a URL or several paths)

For a GitHub URL, clone it with `graphify clone <url> [--branch <branch>]`, then build the clone. For several projects, build each separately and register the native stores with `graphify global add`; there is no graph-file merge command. See `references/github-and-merge.md`.

### Step 1 - Ensure graphify is installed

```bash
# Detect the correct Python interpreter (handles uv tool, pipx, venv, system installs)
PYTHON=""
GRAPHIFY_BIN=$(which graphify 2>/dev/null)
# 1. uv tool installs — most reliable on modern Mac/Linux
if [ -z "$PYTHON" ] && command -v uv >/dev/null 2>&1; then
    _UV_PY=$(uv tool run --from graphifyy python -c "import sys; print(sys.executable)" 2>/dev/null)
    if [ -n "$_UV_PY" ]; then PYTHON="$_UV_PY"; fi
fi
# 2. Read shebang from graphify binary (pipx and direct pip installs)
if [ -z "$PYTHON" ] && [ -n "$GRAPHIFY_BIN" ]; then
    _SHEBANG=$(head -1 "$GRAPHIFY_BIN" | tr -d '#!')
    case "$_SHEBANG" in
        *[!a-zA-Z0-9/_.@-]*) ;;
        *) "$_SHEBANG" -c "import graphify" 2>/dev/null && PYTHON="$_SHEBANG" ;;
    esac
fi
# 3. Fall back to python3
if [ -z "$PYTHON" ]; then PYTHON="python3"; fi
if ! "$PYTHON" -c "import graphify" 2>/dev/null; then
    if command -v uv >/dev/null 2>&1; then
        uv tool install --upgrade graphifyy -q 2>&1 | tail -3
        _UV_PY=$(uv tool run --from graphifyy python -c "import sys; print(sys.executable)" 2>/dev/null)
        if [ -n "$_UV_PY" ]; then PYTHON="$_UV_PY"; fi
    else
        "$PYTHON" -m pip install graphifyy -q 2>/dev/null \
          || "$PYTHON" -m pip install graphifyy -q --break-system-packages 2>&1 | tail -3
    fi
fi
# Write interpreter path for all subsequent steps (persists across invocations)
mkdir -p graphify-out
"$PYTHON" -c "import sys; open('graphify-out/.graphify_python', 'w', encoding='utf-8').write(sys.executable)"
# Save scan root so `graphify update` (no args) knows where to look next time
echo "$(cd INPUT_PATH && pwd)" > graphify-out/.graphify_root
```

If the import succeeds, print nothing and move straight to Step 2.

**In every subsequent bash block, replace `python3` with `$(cat graphify-out/.graphify_python)` to use the correct interpreter.**

The embedded runtime supports macOS and Linux. Windows is temporarily unsupported. Do not suggest Homebrew as a requirement.

### Step 2 - Detect files

Run the production CLI and let it perform the supported-file and sensitive-file checks:

```bash
graphify extract INPUT_PATH
```

Replace INPUT_PATH with the actual path the user provided. Use `--out
OUTPUT_PATH` when output must live outside the source tree. A successful build
activates `OUTPUT_PATH/graphify-out/graph.helix` atomically.

The production CLI performs corpus detection and sensitive-file exclusion.
Present its result as a clean summary:

```
Corpus: X files · ~Y words
  code:     N files (.py .ts .go ...)
  docs:     N files (.md .txt ...)
  papers:   N files (.pdf ...)
  images:   N files
  video:    N files (.mp4 .mp3 ...)
```

Omit any category with 0 files from the summary.

Then act on it:
- If `total_files` is 0: stop with "No supported files found in [path]."
- If `skipped_sensitive` is non-empty: report the count and list the skipped file names, so a wrongly-flagged source or doc is visible and can be renamed or moved (#2106).
- If `total_words` > 2,000,000 OR `total_files` > 500: show the warning. Then compute the top 5 first-level subdirectories by file count:
  - Use the resolved INPUT_PATH as `scan_root`.
  - Concatenate all file lists across all types (`code`, `document`, `paper`, `image`, `video`).
  - Filter out any path that starts with `scan_root + "/graphify-out/"` to exclude converted sidecars.
  - For each file, strip the `scan_root` prefix and take the first path component. Files directly in `scan_root` with no subdirectory count as `(root)`.
  - If all files are in `(root)` with no subdirectories, do not ask to narrow — no subfolders exist. Instead suggest `--no-cluster` to skip the expensive clustering step and proceed.
  - Otherwise rank by count, show the top 5 with file counts, then ask which subfolder to run on. Wait for the user's answer before proceeding.
- Otherwise: proceed directly to Step 2.5 if video files were detected, or Step 3 if not.

### Step 2.5 - Video and audio (only if video files detected)

When media transcription is requested, see `references/transcribe.md`. Transcripts are source inputs; they are not graph-state sidecars.

### Step 3 - Extract entities and relationships

The CLI performs deterministic structural extraction for code and optional semantic extraction for documents, papers, and images. It owns the native extraction cache and only commits cache changes when the new Helix generation activates successfully.

graphify needs no API key for structural extraction. Never ask the user for one, and never block on one. If the host cannot dispatch subagents, run the deterministic CLI path and report that optional semantic enrichment was skipped.

#### Part A - Structural extraction for code files

Structural extraction is deterministic and requires no model key. Do not create intermediate graph files.

#### Part B - Semantic extraction (parallel subagents)

When the host supports subagents and semantic extraction is needed, dispatch bounded file chunks using the shipped extraction specification. Results are transient build DTOs only; the parent process validates them and commits the final state to Helix.

**Step B2 - Dispatch ALL subagents in a single message**

Call the Agent tool multiple times IN THE SAME RESPONSE - one call per chunk. This is the only way they run in parallel. If you make one Agent call, wait, then make another, you are doing it sequentially and defeating the purpose.

**IMPORTANT - subagent type:** Always use `subagent_type="general-purpose"`. Do NOT use `Explore` - it is read-only and cannot write chunk files to disk, which silently drops extraction results. General-purpose has Write and Bash access which the subagent needs.

Concrete example for 3 chunks:
```
[Agent tool call 1: files 1-15, subagent_type="general-purpose"]
[Agent tool call 2: files 16-30, subagent_type="general-purpose"]
[Agent tool call 3: files 31-45, subagent_type="general-purpose"]
```
All three in one message. Not three separate messages.

Each subagent receives this exact prompt (substitute FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE, and CHUNK_PATH).

CHUNK_PATH must be an **absolute** path — derive it before dispatching:
```bash
PROJECT_ROOT=$(pwd)  # cwd — where Part C globs graphify-out/ (NOT .graphify_root/scan dir, #1392)
# Then for chunk N: CHUNK_PATH="${PROJECT_ROOT}/graphify-out/.graphify_chunk_0N.json"
```

Subagent prompt template:

See `references/extraction-spec.md` for the exact subagent prompt (JSON schema, node-ID rules, confidence rubric, frontmatter, hyperedge, and vision rules). Load it only here, only when at least one chunk holds a doc, paper, or image; a pure-code corpus has skipped Part B and never reads it. Pass each subagent that prompt verbatim with FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE, and CHUNK_PATH substituted, and have it write the result to CHUNK_PATH.

**Step B3 - Collect and validate results**

Pass only validated transient DTOs back to the production CLI; never persist an intermediate graph.

#### Part C - Merge AST + semantic into final extraction

The production CLI performs merge, identity validation, dangling-edge pruning, and native generation activation. Do not invoke removed chunk-merge or graph-merge commands.

### Step 4 - Build graph, cluster, analyze, generate outputs

Use the production entry point:

```bash
graphify extract INPUT_PATH
```

This writes and activates `graphify-out/graph.helix`, then generates the report and requested presentation exports directly from the native snapshot. Activation is atomic and retains one rollback generation. A failed or partial build leaves the active generation unchanged.

### Step 4.5 - Graph health check (read-only integrity gate)

Run a native query and benchmark smoke check:

```bash
graphify query "architecture"
graphify benchmark --graph graphify-out/graph.helix
```

If opening the store fails, rebuild from source. Never attempt JSON repair or migration.

### Step 5 - Label communities

```bash
graphify label . --missing-only
```

Labels are committed in the same native generation state. There is no label sidecar.

### Step 6 - Generate Obsidian vault (opt-in) + HTML

```bash
graphify export html graphify-out/graph.helix
graphify export obsidian graphify-out/graph.helix --out graphify-out/obsidian
```

### Steps 6b-8 - Wiki, Neo4j, FalkorDB, SVG, GraphML, MCP, benchmark (only on their flags)

See `references/exports.md`. Every exporter reads a native Helix generation directly.

### Step 9 - Save manifest, update cost tracker, clean up, and report

Generation metadata, hashes, build inputs, and learning state are durable Helix state. Report the store path, generation ID, node/edge counts, retained warnings, and requested export paths. Do not report removed sidecars.

## Interpreter guard for subcommands

Prefer the installed `graphify` executable. If it is missing, use `python3 -m graphify`; do not assume `brew` exists.

## For --update and --cluster-only

Use `graphify update INPUT_PATH` and `graphify cluster-only INPUT_PATH`. See `references/update.md` for generation and rollback behavior.

---

## For /graphify query

When `graphify-out/graph.helix` exists, expand the question against the graph's own vocabulary and answer from its active native generation:

```bash
graphify query "<question>"
```

Use `--dfs` for a trace and `--budget N` to cap output. There is no JSON or in-process compatibility fallback. If the CLI cannot open the Helix store, ask for a source rebuild. See `references/query.md` for query, path, explain, and feedback flows.

---

## For /graphify add and --watch

See `references/add-watch.md`.

---

## For the commit hook and native CLAUDE.md integration

See `references/hooks.md` to wire graphify into a project's CLAUDE.md.

---

## Kilo-specific rules

- Use the native `Task` tool for semantic extraction fan-out.
- Launch all chunk tasks in the same response so they run in parallel.
- Always use `subagent_type="general"` for extraction chunks.
- After modifying code files during the session, run `graphify update .`.

---

## Honesty Rules

- Never invent an edge. If unsure, use AMBIGUOUS.
- Never read an obsolete JSON graph as runtime state.
- Always expose raw cohesion and benchmark measurements.
- Warn before rendering HTML for very large graphs.
