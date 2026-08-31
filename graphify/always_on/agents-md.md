## graphify

This project has a knowledge graph at `graphify-out/` with project structure, symbol relationships, community analysis, and cross-file dependencies.

When the user types `/graphify`, use the installed Graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when `graphify-out/graph.json` exists. Only fall back to source search if Graphify cannot answer or the requested information is outside the indexed graph.
- Prefer Graphify over full-project searches whenever possible. Use source code browsing only to inspect implementation details after Graphify has identified the relevant files or symbols.
- Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than `GRAPH_REPORT.md` or raw grep output.
- Dirty `graphify-out/` files are expected after hooks or incremental updates; dirty graph files are not a reason to skip Graphify. Only skip Graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- Read `graphify-out/GRAPH_REPORT.md` for broad architecture review or when `graphify query`, `graphify path`, or `graphify explain` do not surface enough context.
- Use `graphify-out/graph.html` only when an interactive visualization is explicitly needed; do not rely on it for automated reasoning.
- If `graphify-out/graph.json` does not exist, assume the knowledge graph has not been generated yet. Inspect the source normally or ask the user to run `graphify update .`.
- After modifying code that changes project structure, symbols, modules, or relationships, run `graphify update .` to keep the graph current (AST-only, no API cost). Minor changes such as comments, formatting, or documentation generally do not require updating the graph.