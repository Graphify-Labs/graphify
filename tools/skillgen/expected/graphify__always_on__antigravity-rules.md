---
trigger: always_on
description: Consult the graphify knowledge graph at graphify-out/ for codebase and architecture questions.
---

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- For codebase or architecture questions, when `graphify-out/graph.json` exists, first use the graph. Prefer the MCP `query_graph` tool. CLI fallback: `"$(cat graphify-out/.graphify_python)" -m graphify query "<question>"` (PowerShell: `& (Get-Content graphify-out\.graphify_python) -m graphify query "<question>"`); use the same recorded interpreter with `path` or `explain` for relationships and focused concepts. These return a scoped subgraph, usually much smaller than `GRAPH_REPORT.md` or raw grep output.
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
