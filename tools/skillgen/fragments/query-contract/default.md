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
