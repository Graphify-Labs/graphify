When `graphify-out/graph.json` already exists and the user asks a question about the corpus, answer from the graph rather than rebuilding it:

```bash
graphify query "<question>" --format evidence-json --max-nodes 80 --budget 1000
```

Read the packet's `llm.mode`: `none` means answer directly without another graph call, `synthesize` means produce one grounded answer from this packet, and `reason` permits focused recovery. Only on `reason` should you expand against the graph vocabulary or run another traversal. If the CLI is unavailable, fall back to an inline NetworkX traversal of `graphify-out/graph.json`. Answer using only graph evidence and cite `source_location`. For lazy document sections, recovery, path/explain, and feedback details, see `references/query.md`.
