When `graphify-out/graph.json` already exists and the user asks a question about the corpus, run the query directly:

```bash
graphify query "<question>"
```

Answer using only what the graph output contains, and quote `source_location` when citing a specific fact. Before traversal, expand the question against the graph's own vocabulary so a wording mismatch does not collapse the answer to noise. For that vocab-expansion step, the `--dfs` / `--budget` modes, `save-result` feedback, and the `/graphify path` and `/graphify explain` flows, see `references/query.md`.
