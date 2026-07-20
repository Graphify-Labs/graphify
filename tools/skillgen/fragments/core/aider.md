---
name: graphify
description: "Use for any question about a codebase, its architecture, file relationships, or project content — especially when graphify-out/ exists, where the question should be treated as a graphify query first. Turns any input (code, docs, papers, images, videos) into a persistent knowledge graph with god nodes, community detection, and query/path/explain tools."
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

If the native store exists, query it. If only an obsolete-format file exists, ignore it and rebuild from source. Native Windows x86_64 is supported through the matching public package wheel.

### Step 1 - Ensure graphify is installed

Use `uv tool install graphifyy` or `python3 -m pip install graphifyy`. Homebrew is not required.

### Step 2 - Detect files

The production CLI performs corpus detection and sensitive-file exclusion.

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

Run `graphify extract INPUT_PATH`. Atomic activation deletes inactive generations by default; pass `--retain-rollback` to retain exactly one previous generation.

### Step 5 - Label communities

Run `graphify label . --missing-only`; labels remain inside Helix state.

### Step 6 - Generate Obsidian vault (opt-in) + HTML

Run native `graphify export` commands.

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

## For native CLAUDE.md integration

Run `graphify claude install`.

## Honesty Rules

- Never invent an edge.
- Never reconstruct or migrate obsolete runtime data.
- Preserve confidence tags and source citations.
