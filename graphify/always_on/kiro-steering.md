---
inclusion: always
---

graphify: A knowledge graph of this project lives in `graphify-out/`. For codebase, architecture, or dependency questions, when `graphify-out/graph.json` exists, prefer the MCP `query_graph` tool. CLI fallback: `"$(cat graphify-out/.graphify_python)" -m graphify query "<question>"` (PowerShell: `& (Get-Content graphify-out\.graphify_python) -m graphify query "<question>"`); use the same recorded interpreter with `path` or `explain`. These return a scoped subgraph, usually much smaller than `GRAPH_REPORT.md` or raw grep output. Read `GRAPH_REPORT.md` only for broad architecture review or when those commands do not surface enough context.
