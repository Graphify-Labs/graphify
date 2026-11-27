When `graphify-out/graph.json` already exists and the user asks a question about the corpus, answer from the graph rather than rebuilding it. Write the user's question verbatim to `graphify-out/.graphify_question` (your file-writing tool or a quoted heredoc — never paste it into a quoted command-line argument), then run:

```bash
graphify query "$(cat graphify-out/.graphify_question)"
```

Before traversal, expand the question against the graph's own vocabulary so a wording mismatch does not collapse the answer to noise. If the `graphify query` CLI is unavailable, fall back to an inline NetworkX traversal of `graphify-out/graph.json`. Answer using only what the graph output contains, and quote `source_location` when citing a specific fact. For that vocab-expansion step, the BFS/DFS traversal modes, the `--budget` cap, the NetworkX fallback, `save-result` feedback, and the `/graphify path` and `/graphify explain` flows, see `references/query.md`.
