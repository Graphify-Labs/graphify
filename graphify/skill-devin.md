---
name: graphify
description: "Use for any question about a codebase, its architecture, file relationships, or project content — especially when graphify-out/ exists, where the question should be treated as a graphify query first. Turns any input (code, docs, papers, images, videos) into a persistent knowledge graph with god nodes, community detection, and query/path/explain tools."
argument-hint: "[path|query|subcommand]"
model: sonnet
allowed-tools: [read, grep, glob, exec]
triggers: [user, model]
---

# /graphify

Graphify uses `graphify-out/graph.helix` as its only runtime store.

## Usage

```bash
graphify extract [path]
graphify update [path]
graphify query "question"
graphify path "A" "B"
graphify explain "node"
```

## What graphify is for

Use native topology, analysis, confidence, and source locations to understand a corpus without re-reading it.

## What You Must Do When Invoked

If the native store exists, query it. If only an obsolete-format file exists, ignore it and rebuild from source. Windows is temporarily unsupported.

### Step 1 - Ensure graphify is installed

Use `uv tool install graphifyy` or `python3 -m pip install graphifyy`. Homebrew is not required.

### Step 2 - Detect files

Run `graphify extract INPUT_PATH`. The production CLI performs corpus detection
and sensitive-file exclusion. Present its result as a clean summary:

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
- If `total_words` > 2,000,000 OR `total_files` > 200: show the warning and the top 5 subdirectories by file count, then ask which subfolder to run on. Wait for the user's answer before proceeding.
- Otherwise: proceed directly to Step 2.5 if video files were detected, or Step 3 if not.

### Step 2.5 - Transcribe video / audio files (only if video files detected)

Transcribe media to source text only when requested.

### Step 3 - Extract entities and relationships

graphify needs no API key for structural extraction. Never ask the user for one, and never block on one. If this host cannot dispatch subagents, run the deterministic CLI path and skip optional semantic enrichment.

#### Part A - Structural extraction for code files

Code extraction is deterministic and keyless.

#### Part B - Semantic extraction (parallel subagents)

Use bounded semantic chunks only for non-code content.

#### Part C - Merge AST + semantic into final extraction

Transient DTOs are validated by the parent and committed with native state.

### Step 4 - Build graph, cluster, analyze, generate outputs

Run `graphify extract INPUT_PATH`. Atomic activation retains the previous generation for rollback.

### Step 5 - Label communities

Run `graphify label . --missing-only`; labels remain inside Helix state.

### Step 6 - Generate Obsidian vault (opt-in) + HTML

Run native `graphify export` commands.

### Step 6b - Wiki (only if --wiki flag)

Run `graphify export wiki graphify-out/graph.helix`.

### Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag)

Run `graphify export neo4j graphify-out/graph.helix`.

### Step 7b - SVG export (only if --svg flag)

Run `graphify export svg graphify-out/graph.helix`.

### Step 7c - GraphML export (only if --graphml flag)

Run `graphify export graphml graphify-out/graph.helix`.

### Step 7d - MCP server (only if --mcp flag)

Run `python3 -m graphify.serve graphify-out/graph.helix`.

### Step 8 - Token reduction benchmark (only if total_words > 5000)

Run `graphify benchmark --graph graphify-out/graph.helix`.

### Step 9 - Save manifest, update cost tracker, clean up, and report

Build metadata, hashes, caches, and learning state are durable native state.

## Interpreter guard for subcommands

Prefer `graphify`; otherwise use `python3 -m graphify`.

## For --update (incremental re-extraction)

Run `graphify update INPUT_PATH`.

## For --cluster-only

Run `graphify cluster-only INPUT_PATH`.

## For /graphify query

Run `graphify query "QUESTION" [--dfs] [--budget N]`.

## For /graphify path

Run `graphify path "A" "B" --graph graphify-out/graph.helix`.

## For /graphify explain

Run `graphify explain "NODE" --graph graphify-out/graph.helix`.

## For /graphify add

Run `graphify add URL`, then `graphify update .`.

## For --watch

Run `graphify watch INPUT_PATH`.

## For git commit hook

Run `graphify hook install`.

## For always-on context in Devin sessions

Tell Devin to query `graphify-out/graph.helix` before broad source search.

## Honesty Rules

- Never invent an edge.
- Never reconstruct or migrate obsolete runtime data.
- Preserve confidence tags and source citations.
