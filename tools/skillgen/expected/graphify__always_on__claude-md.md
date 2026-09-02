## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first use the graph when graphify-out/graph.json exists. Prefer the MCP `query_graph` tool. CLI fallback: `"$(cat graphify-out/.graphify_python)" -m graphify query "<question>"` (PowerShell: `& (Get-Content graphify-out\.graphify_python) -m graphify query "<question>"`); use the same recorded interpreter with `path` or `explain` for relationships and focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
