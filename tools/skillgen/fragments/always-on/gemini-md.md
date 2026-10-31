## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- When graphify-out/graph.json exists, use the graph before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. An exact node name or ID can be passed straight to `graphify query "<name>"`; any natural-language question goes through the ordered workflow in the next rule. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- For a natural-language question, load the graphify skill's `references/query.md` first and follow it in order: vocabulary, lessons, query, source check, feedback. `graphify query` matches case-insensitively (lowercase) against node labels and some other node fields, using exact, prefix and substring tiers combined with field weights and term coverage/IDF (so not a strict global order), with no stemming or synonyms, so wording that differs from the graph's labels can miss the right nodes. The vocabulary, `reflect` and `save-result` steps are CLI-only; the MCP tools (`query_graph` etc.) do not cover them.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. Do not flag it as churn or suggest skipping the graph rebuild or its hooks.
