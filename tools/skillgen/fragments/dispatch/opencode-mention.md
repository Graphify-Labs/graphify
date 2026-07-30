**Step B2 - Dispatch ALL subagents in a single message (OpenCode)**

> **OpenCode platform:** Uses `@mention` dispatch instead of the Agent tool. All mentions in a single message run in parallel.

Before dispatch, assign every chunk a distinct absolute
`CHUNK_PATH=graphify-out/.graphify_chunk_NN.json`. Dispatch one `@mention` per
chunk — ALL in the same response:

```
@agent Chunk CHUNK_NUM of TOTAL_CHUNKS: [extraction prompt with FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE, and CHUNK_PATH substituted]. You must write the JSON object to CHUNK_PATH before returning.

@agent Chunk 2 of TOTAL_CHUNKS: [next chunk with its distinct CHUNK_PATH; write it before returning]
```

Wait for all agents to return. Treat every inline response as status only, never
as semantic evidence. Verify that every named `CHUNK_PATH` exists; a missing or
invalid chunk aborts the batch. Run the package-owned `graphify merge-chunks`
command from Step B3 to validate and construct
`graphify-out/.graphify_semantic_new.json`. If the `@agent` path cannot write
chunk files, use the serial path that writes each
`graphify-out/.graphify_chunk_NN.json` before that same package merge.

Subagent prompt template:

See `references/extraction-spec.md` for the exact subagent prompt (JSON schema, node-ID rules, confidence rubric, hyperedge, and vision rules). Load it only here, only when at least one chunk holds a doc, paper, or image; a pure-code corpus has skipped Part B and never reads it. Pass each agent that prompt verbatim with FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE, and CHUNK_PATH substituted.
