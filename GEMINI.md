# Graphify (local code graph)

This extension exposes your local Graphify knowledge graph to Gemini CLI over MCP. Graphify turns a codebase, with its docs, configs, and SQL schemas, into a queryable graph of callers, dependencies, change impact, and tests, built with deterministic tree-sitter AST parsing. Every edge is explained, there is no vector store, and nothing leaves your machine.

## Setup (one time)

1. Install the CLI with the MCP extra: `uv tool install "graphifyy[mcp]"` (or `pipx install "graphifyy[mcp]"`). The `[mcp]` extra is required, or `graphify-mcp` will not start.
2. Build the graph in your project: `graphify extract .` (writes `graphify-out/graph.json`).

The extension runs `graphify-mcp`, which serves `graphify-out/graph.json` from the current project. Re-run `graphify extract .` (or `graphify update .`) after code changes to keep the graph current.

## How to use it

- Prefer querying the graph over grepping files: ask what calls a symbol, trace the path between two things, or explain one area of the codebase.
- Treat the graph as the map of the codebase. Fall back to reading raw files only when the graph does not cover something.
- Every edge is tagged `EXTRACTED` (explicit in the source) or `INFERRED` (resolved by graphify), so you can tell what was read directly from what was inferred.

## Hosted option

For an always-on graph that stays current without a local build, with cross-repo search and code review across your whole SDLC, see Graphify Cloud at https://graphify.com. It connects over MCP too, so you keep working in this same CLI.
