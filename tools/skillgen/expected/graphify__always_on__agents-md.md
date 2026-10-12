## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, follow this order:
  1. First check whether `graphify-out/graph.json` exists. If it does not, skip graph queries and continue with the other codebase workflow.
  2. For a natural-language graph question, follow **Step 0 — Constrained query expansion** in the installed Graphify query workflow (the `references/query.md` sidecar when available). When the user's wording differs from node labels, map the intent only to matching tokens found in the graph's actual node-label vocabulary; do not invent synonyms or terms. If no vocab tokens match the question, say the graph has no relevant vocabulary and stop instead of running a broad or guessed query.
  3. Run `graphify query "<expanded tokens>"` using only the selected vocabulary tokens. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
  4. Keep the user's original question for the answer and any `save-result` operation; use the expanded tokens only for the graph query.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After code-only changes, run `graphify update .` only when `graphify-out/graph.json` already exists. This CLI update locally refreshes the code graph with AST extraction and does not call an LLM or API. It can create a new graph when code files exist, so do not run `graphify update` automatically when that graph is missing.
- For changes to documentation, papers, images, videos, or a mix of code and semantic files, do not automatically run `/graphify --update`. Its semantic extraction can call the configured LLM/API backend and may incur usage or cost; run it only when the user explicitly requests a graph refresh, following the installed Graphify update reference.
- No changes to relevant content means no graph update. If an update fails, report the failure and preserve the existing graph and cache; do not delete or reset them as recovery.
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. Do not flag it as churn or suggest skipping the graph rebuild or its hooks.
