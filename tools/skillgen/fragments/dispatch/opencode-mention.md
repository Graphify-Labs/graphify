**Step B2 - Dispatch ALL subagents in a single message (OpenCode)**

> **OpenCode platform:** Uses `@mention` dispatch instead of the Agent tool. All mentions in a single message run in parallel.

Dispatch one `@mention` per chunk — ALL in the same response:

```
@agent Chunk CHUNK_NUM of TOTAL_CHUNKS: [extraction prompt with FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE substituted]

@agent Chunk 2 of TOTAL_CHUNKS: [next chunk]
```

Wait for all agents to return. Parse each response as JSON. Accumulate nodes/edges/hyperedges across all results and write to `graphify-out/.graphify_semantic_new.json`. If the `@agent` path cannot write chunk files, fall back to the serial path that writes each `graphify-out/.graphify_chunk_NN.json` before merge.

Subagent prompt template:

See `references/extraction-spec.md` for the exact subagent prompt (JSON schema, node-ID rules, confidence rubric, hyperedge, and vision rules). Load it only here, only when at least one chunk holds a doc, paper, or image; a pure-code corpus has skipped Part B and never reads it. Pass each agent that prompt verbatim with FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, and DEEP_MODE substituted.
