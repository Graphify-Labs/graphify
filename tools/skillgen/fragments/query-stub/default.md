When `graphify-out/graph.json` already exists and the user asks a natural-language question about the corpus, answer from the graph rather than rebuilding it. Load `references/query.md` first and follow its order: vocabulary, lessons, query, source check, feedback. An exact node name or ID can be passed straight to `graphify query`.

```bash
graphify query "<question>"
```

`graphify query` matches case-insensitively (lowercase) against node labels and some other node fields, using exact, prefix and substring tiers combined with field weights and term coverage/IDF (so not a strict global order), with no stemming or synonyms, so first expand the question against the graph's own vocabulary, as the reference describes (cached in `graphify-out/.vocab.txt`, rebuilt only when `graph.json` is newer). The vocabulary, `reflect` and `save-result` steps are CLI-only; the MCP tools do not cover them. If the `graphify query` CLI is unavailable, fall back to an inline NetworkX traversal of `graphify-out/graph.json`. Answer using only what the graph output contains, and quote `source_location` when citing a specific fact. For the vocabulary step, lessons, the BFS/DFS traversal modes, the `--budget` cap, the NetworkX fallback, `save-result` feedback, and the `/graphify path` and `/graphify explain` flows, see `references/query.md`.
