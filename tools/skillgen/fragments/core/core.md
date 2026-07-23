@@FRONTMATTER@@

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

@@INSTALL@@

The embedded runtime supports macOS, Linux, and native Windows x86_64. Use the matching public package wheel; do not suggest Homebrew, WSL, source builds, or downloaded DLLs as requirements.

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

@@DISPATCH@@

**Step B3 - Collect and validate results**

Pass only validated transient DTOs back to the production CLI; never persist an intermediate graph.

#### Part C - Merge AST + semantic into final extraction

The production CLI performs merge, identity validation, dangling-edge pruning, and native generation activation. Do not invoke removed chunk-merge or graph-merge commands.

### Step 4 - Build graph, cluster, analyze, generate outputs

Use the production entry point:

```bash
graphify extract INPUT_PATH
```

This writes and activates `graphify-out/graph.helix`, then generates the report and requested presentation exports directly from the native snapshot. Activation is atomic and deletes inactive generations by default; pass `--retain-rollback` to retain exactly one previous generation. A failed or partial build leaves the active generation unchanged.

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

@@QUERY_STUB@@

---

## For /graphify add and --watch

See `references/add-watch.md`.

---

## For the commit hook and native @@HOOKS_TARGET@@ integration

See `references/hooks.md` to wire graphify into a project's @@HOOKS_TARGET@@.

---

@@EXTRA@@## Honesty Rules

- Never invent an edge. If unsure, use AMBIGUOUS.
- Never read an obsolete JSON graph as runtime state.
- Always expose raw cohesion and benchmark measurements.
- Warn before rendering HTML for very large graphs.
