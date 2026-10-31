---
inclusion: always
---

graphify: A knowledge graph of this project lives in `graphify-out/`. For codebase, architecture, or dependency questions, when `graphify-out/graph.json` exists: for an exact node name or ID, run `graphify query "<name>"` directly; for a natural-language question, load the graphify skill's `references/query.md` first and follow it in order (vocabulary, lessons, query, source check, feedback). Use `graphify path "<A>" "<B>"` / `graphify explain "<concept>"` for relationships and focused concepts. These return a scoped subgraph, usually much smaller than `GRAPH_REPORT.md` or raw grep output. Read `GRAPH_REPORT.md` only for broad architecture review or when those commands do not surface enough context.
