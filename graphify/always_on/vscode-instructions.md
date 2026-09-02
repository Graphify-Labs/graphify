## graphify

For any question about this repo's architecture, structure, components, or how to add/modify/find
code, first use the graph when `graphify-out/graph.json` exists. Prefer the MCP `query_graph` tool.
CLI fallback: `"$(cat graphify-out/.graphify_python)" -m graphify query "<question>"` (PowerShell:
`& (Get-Content graphify-out\.graphify_python) -m graphify query "<question>"`); use the same recorded
interpreter with `path` or `explain`. These return a scoped subgraph, usually much smaller than the
full report or raw grep output.

Triggers: "how do I…", "where is…", "what does … do", "add/modify a <component>",
"explain the architecture", or anything that depends on how files or classes relate.

If `graphify-out/wiki/index.md` exists, use it for broad navigation. Read `graphify-out/GRAPH_REPORT.md`
only for broad architecture review or when query/path/explain do not surface enough context. Only read
source files when (a) modifying/debugging specific code, (b) the graph lacks the needed detail, or
(c) the graph is missing or stale.

Type `/graphify` in Copilot Chat to build or update the graph.
