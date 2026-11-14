---
name: graphify-code-graph
description: Use when the user asks about an indexed repository's architecture, symbols, callers, dependencies, imports, change impact, linked tests, team memory, or pull request review status. Selects and verifies results from hosted Graphify MCP tools such as query_graph, graphify_find, graphify_callers, graphify_impact, graphify_trace, recall, and review_status.
---

# Graphify code graph

Use the hosted Graphify MCP connection to answer from repositories indexed in the user's Graphify workspace. The available tools and their schemas come from the live MCP connection; inspect that list instead of assuming every documented tool is present.

## When to use

- Explain how a feature, module, symbol, or repository works.
- Find definitions, relevant files, callers, callees, imports, dependents, or call paths.
- Assess the direct impact of a proposed code change and identify linked tests.
- Read repository memory or the status and findings of an existing pull request review.
- List accessible workspaces and repositories or check graph status.

Do not claim that hosted Graphify sees uncommitted or unindexed changes. For exact-string searches or code absent from the indexed graph, use the available source tools and say which evidence path you used.

## Query workflow

1. If the workspace or repository is not explicit, call `list_workspaces` and `list_repositories`. Report an empty or unindexed result instead of guessing.
2. Choose the narrowest tool that answers the question:
   - `graphify_find` for symbol-name fragments; `graphify_rank_files` for relevant files.
   - `query_graph` for a scoped explanation; `graphify_node` for one symbol and its neighbors.
   - `graphify_callers` for callers; `graphify_impact` for direct callers and callees.
   - `graphify_trace` for paths between two symbols.
   - `graphify_imports_exports` and `graphify_file_neighbors` for file-level dependencies.
   - `graphify_impact` with risk information and `graphify_tests_for` before a code change, when available.
   - `graph_stats` for index and graph status; `recall` for team memory; `review_status` for an existing review.
   - `search` followed by `fetch` when that connector pair is the available interface.
3. Preserve ambiguity. If a symbol has multiple candidates, let the user choose or use the returned identifier; do not silently pick one.
4. Ground the answer in tool results and include returned file paths or source locations. An empty result is not proof that code or a dependency does not exist.
5. Distinguish direct graph evidence, inferred edges, and your own recommendations.

## Safety and state

- Ask the user before `remember`; it saves a fact to repository memory. Do not save secrets or sensitive personal data.
- Ask the user before `set_workspace`; it changes which repositories the session can query.
- `review_status` only reads review state. Do not describe it as starting or rerunning a review.
- Graphify tools do not edit code or run tests. Use the appropriate available tools for those actions and report actual results only.
- Do not fabricate repositories, symbols, paths, line numbers, review findings, or tool output.
