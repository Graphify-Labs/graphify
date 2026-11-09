**Step B2 - Dispatch ALL subagents in a single message (Codex)**

> **Codex platform:** Uses `spawn_agent` + `wait_agent` + `close_agent` instead of the Agent tool.
> Requires `multi_agent = true` under `[features]` in `~/.codex/config.toml`.
> If `spawn_agent` is unavailable, tell the user to add that config and restart Codex.

Call `spawn_agent` once per chunk — ALL in the same response so they run in parallel. Build the message by wrapping the extraction prompt in task-delegation framing:

```
spawn_agent(agent_type="worker", message="Your task is to perform the following. Follow the instructions below exactly.\n\n<agent-instructions>\n[extraction prompt, with FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE substituted]\n</agent-instructions>\n\nExecute this now. Output ONLY the structured JSON response.")
```

After all agents are dispatched, collect results sequentially in memory:
```
result = wait_agent(handle); close_agent(handle)   # repeat per handle
```

Collect each result in memory and associate it with the chunk number used for dispatch. Validate that every result is a JSON object with list-valued `nodes` and `edges`; `hyperedges` may be omitted or a list. Empty lists are valid extraction results.

If any subagent fails, returns no result or invalid JSON, or a result cannot be persisted and read back from its expected chunk file, print the affected chunk numbers and stop before Step B3. Do not merge partial results, save cache, or continue to Part C; leave the existing graph and semantic cache untouched.

Only after every result validates, write each result to its matching `graphify-out/.graphify_chunk_NN.json` file, using JSON serialization and the trusted chunk number. Preserve its `nodes`, `edges`, `hyperedges`, `input_tokens`, and `output_tokens` values. Verify that every expected chunk file exists and parses as JSON before continuing. Do not aggregate results or write `graphify-out/.graphify_semantic_new.json` in B2 — shared Step B3 performs the merge and cache update.

Subagent prompt template:

See `references/extraction-spec.md` for the compact subagent prompt (rules, node-ID format, confidence rubric, hyperedge and vision rules, JSON schema). Load it only here, only when at least one chunk holds a doc, paper, or image; a pure-code corpus has skipped Part B and never reads it. Pass each agent that prompt verbatim with FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, and DEEP_MODE substituted, and have it return the JSON inline.
