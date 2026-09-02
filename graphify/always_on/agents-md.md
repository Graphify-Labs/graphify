## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first use the graph when graphify-out/graph.json exists. Prefer the MCP `query_graph` tool. CLI fallback: `"$(cat graphify-out/.graphify_python)" -m graphify query "<question>"` (PowerShell: `& (Get-Content graphify-out\.graphify_python) -m graphify query "<question>"`); use the same recorded interpreter with `path` or `explain` for relationships and focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `"$(cat graphify-out/.graphify_python)" -m graphify update .` (PowerShell: `& (Get-Content graphify-out\.graphify_python) -m graphify update .`) to keep the graph current (AST-only, no API cost).
