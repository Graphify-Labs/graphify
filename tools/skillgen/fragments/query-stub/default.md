When `graphify-out/graph.helix` exists, expand the question against the graph's own vocabulary and answer from its active native generation:

```bash
graphify query "<question>"
```

Use `--dfs` for a trace and `--budget N` to cap output. There is no JSON or in-process compatibility fallback. If the CLI cannot open the Helix store, ask for a source rebuild. See `references/query.md` for query, path, explain, and feedback flows.
