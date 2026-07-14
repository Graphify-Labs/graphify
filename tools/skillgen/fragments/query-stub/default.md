When `graphify-out/graph.json` already exists and the user asks a question about the corpus, answer from the graph rather than rebuilding it:

```bash
graphify query "Where is authentication validated?"
```

@@QUERY_CONTRACT@@

The example is a fixed literal, not an interpolation template. If a plain query finds no useful vocabulary match, retry with relevant labels that actually exist in the graph; do not invent nodes or edges. For CLI examples, the constrained inline NetworkX fallback, `save-result` feedback, and the `/graphify path` and `/graphify explain` flows, see `references/query.md`.
