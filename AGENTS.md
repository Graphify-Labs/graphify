## graphify

This project has a graphify knowledge graph at `graphify-out/`.

### AST-first graph policy

Default graph generation is **code-only** (no LLM). `.graphifyignore` excludes documentation and generated skill markdown so extraction stays offline and deterministic. Or pass **`--code-only`** on `graphify extract` to skip semantic work even when docs are detected.

| Task | Command |
|------|---------|
| Full AST rebuild | `graphify extract . --code-only --no-label` |
| Full AST rebuild (docs already ignored) | `graphify extract . --no-label` |
| Incremental code update | `graphify update .` (AST-only, no API cost) |
| Auto-rebuild on commit | `graphify hook install` |
| Agent retrieval | `graphify query "<question>"` or MCP (`python -m graphify.serve graphify-out/graph.json`) |

Do **not** run `/graphify .` for routine rebuilds — it may dispatch semantic extraction if docs are not excluded. Prefer `graphify extract` or `graphify update`.

**Optional semantic overlay** (docs, community labels, inferred links) — run only on demand:

```bash
graphify extract ./docs --backend gemini --out ./doc-overlay
graphify merge-graphs graphify-out/graph.json \
  doc-overlay/graphify-out/graph.json --out graphify-out/graph.json
graphify label .   # human-readable community names (one batched LLM call)
```

### Agent rules

- Before answering architecture or codebase questions, read `graphify-out/GRAPH_REPORT.md` for god nodes and community structure
- If `graphify-out/wiki/index.md` exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
- Prefer `graphify query` over grepping or reading many source files when `graphify-out/graph.json` exists
