# graphify reference: query, path, explain

Use this reference only when an active `graphify-out/graph.helix` store exists. Graphify resolves labels, scores vocabulary, traverses, and renders evidence directly from the immutable native snapshot.

### Step 0 — Constrained query expansion (REQUIRED before traversal)

Pass the user's wording to the native CLI. It expands terms against labels and identifiers stored in the active generation; do not reproduce that scoring in the skill.

### Step 1 — Traversal

Two traversal modes are available:

| Mode | Flag | Best for |
|------|------|----------|
| BFS | _(none)_ | Broad nearby context |
| DFS | `--dfs` | A focused dependency or call trace |

Run:

```bash
graphify query "QUESTION"
graphify query "QUESTION" --dfs --budget 3000
```

Answer only from returned nodes and edges. Preserve confidence tags and cite `source_file`/`source_location` when present. If no match exists, say that the native graph lacks evidence rather than inventing a relationship.

Record useful, dead-end, or corrected outcomes with `graphify save-result`; the learning state is committed inside Helix and can be summarized with `graphify reflect --if-stale`.

## For /graphify path

```bash
graphify path "NODE_A" "NODE_B" --graph graphify-out/graph.helix
```

Explain each directed relation and confidence tag in the returned native shortest path. If there is no path, report that directly.

## For /graphify explain

```bash
graphify explain "NODE_NAME" --graph graphify-out/graph.helix
```

Summarize the node, its source, degree, learning annotation, and native connections. Do not fall back to reading or reconstructing an obsolete graph file.
