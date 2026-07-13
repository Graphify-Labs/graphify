# graphify reference: query, path, explain

Load this for questions against an existing graph and for `query`, `path`, or `explain`.

**Search contract**

- **Shell safety:** User-controlled question text is data, never shell syntax. Use an MCP/structured argument API or a process API with an argument list. If a shell is unavoidable, correctly escape or encode the question as one argv value. Never interpolate raw user text into a quoted command or code template.
- **Reserved directives:** `include:memory`, `community:...`, and `god:...` are control syntax, not semantic search text. Append them only when intentionally activating that behavior. If the user asks about the literal syntax, answer from documentation or paraphrase the search without the reserved token; forwarding it would activate the parser.
- **Default retrieval:** Query retrieval is staged across code, documentation, tests, and likely communities. Saved `graphify-out/memory` Q&A nodes are fallback-only unless `include:memory` is intentionally active.

| Need | Action |
|------|--------|
| Use prior saved Q&A as candidates | Add `include:memory`. |
| Limit retrieval to a community or god node | Add `community:<id|label>` or `god:<label|id>`; quote labels containing spaces. Named communities come from `.graphify_labels.json` beside `graph.json`. Prefer names in durable instructions because numeric community IDs can change after rebuilds. |
| Control work and output size | Pass `--budget N`; it bounds deterministic traversal as well as final text. |
| Resolve an ambiguous `path` or `explain` label | The CLI exits 2 and prints ranked candidates. MCP/HTTP return the ambiguity diagnostic as successful text. In both cases, never guess; rerun with `<source-file>::<label>` or the exact node ID. |
| Cite a result | Preserve Graphify's truthful source display: a known span, `(file only)`, external/reference provenance from `origin_file`, or `(no source)`. Fallback code must call `graphify.serve._source_display` rather than inventing locations or a separate provenance contract. |

Advanced directives require the Graphify CLI or MCP implementation. The inline NetworkX fallback cannot emulate them: never pass `include:memory`, `community:...`, or `god:...` into fallback label matching.

### Query

Choose traversal mode from the question:

| Mode | Flag | Best for |
|------|------|----------|
| BFS (default) | _(none)_ | Broad context and nearest related concepts. |
| DFS | `--dfs` | A specific chain, dependency, or data flow. |

Use the CLI or MCP through a structured argument API whenever possible. If launching a process, put the complete semantic question in one argv element and add reserved directives only as an intentional part of that same argument. The commands below contain fixed literals; they are not templates for raw string interpolation.

```bash
graphify query "Where is authentication validated?"
graphify query "How does capture reach inference?" --dfs --budget 3000
graphify query 'controller latency community:"Main Runtime"'
graphify query 'request flow god:"Auth Gateway"'
graphify query "why was polling retained? include:memory"
```

Keep semantic text separate from reserved control syntax. For example, if the user asks what `include:memory` means, answer from these instructions or query for `memory inclusion behavior`; do not forward the literal reserved token unless the user intends to include saved Q&A.

Answer only from the returned subgraph. Preserve source display exactly; never turn file-only, external/reference, or missing provenance into an invented line number.

If a plain query returns no useful match because the user's wording differs from graph labels, inspect labels already present in `graph.json` and retry with the closest relevant graph vocabulary. Do not invent labels, synonyms, nodes, or edges.

### Inline NetworkX fallback

Use fallback only when the CLI and MCP implementation are unavailable and the request is a plain, unscoped query. It cannot emulate staged scope selection, advanced directives, label-sidecar resolution, or CLI budget semantics.

- Pass the question into fallback code as structured data, never by inserting it into shell or Python source.
- If intentional behavior requires `include:memory`, `community:...`, or `god:...`, stop and report that CLI/MCP is required. Do not pass directive text into fallback matching.
- If the user is discussing a directive literally, paraphrase the semantic terms before matching so the reserved token is not activated.
- Keep fallback traversal deterministic and bounded, and label its display cap as different from CLI `--budget` semantics.
- Delegate source rendering to the implementation helper so fallback and CLI stay aligned:

```python
from graphify.serve import _source_display

display = _source_display(node_data)
```

`_source_display` preserves known spans and file-only locations, recognizes `origin_file` as external/reference provenance, and marks unowned nodes honestly. Do not create a separate `source_url`-only provenance rule; if runtime URL handling evolves, the shared helper remains the source of truth.

### Save useful results

After answering, save the original question and cited node labels through structured arguments. This fixed-literal example records a useful result:

```bash
graphify save-result --question "Where is authentication validated?" --answer "AuthGuard validates authentication." --type query --nodes AuthGuard --outcome useful
```

Use `--outcome dead_end` when traversal did not answer the question. Use `--outcome corrected` with a correction argument when replacing a wrong result. Before graph work, run `graphify reflect --if-stale` and read `graphify-out/reflections/LESSONS.md` when it exists.

## For /graphify path

Prefer the CLI/MCP resolver. Plain labels are allowed only when unique:

```bash
graphify path "AuthModule" "Database"
graphify path "src/auth.py::AuthModule" "src/db.py::Database"
```

Transport behavior differs only in how ambiguity is returned:

- CLI: exits with status 2 and prints ranked candidates.
- MCP/HTTP: returns the same ambiguity diagnostic as successful tool-result text; it does not turn ambiguity into a transport error.

Both require the same response: never choose a candidate by position or score. Rerun with the printed `<source-file>::<label>` selector or exact node ID.

If CLI/MCP is unavailable, use NetworkX only after obtaining exact node IDs from `graph.json`; do not fuzzy-match labels in fallback code. Explain every hop using only returned relations and confidence, preserve truthful source markers, and save useful explanations with `--type path_query`.

## For /graphify explain

Prefer the CLI/MCP resolver:

```bash
graphify explain "SwinTransformer"
graphify explain "src/model.py::SwinTransformer"
graphify explain "EXACT_NODE_ID"
```

The same transport rule applies: CLI ambiguity exits 2; MCP/HTTP ambiguity is successful diagnostic text. In both cases, rerun with a ranked source-qualified label or exact ID and never guess. If CLI/MCP is unavailable, inspect only an exact node ID in NetworkX and stop if it does not exist.

Write a concise explanation of what the node is, what it connects to, and why those connections matter. Render provenance through `graphify.serve._source_display` so the explanation matches CLI semantics.
