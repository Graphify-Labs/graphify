**Step B2 - Dispatch ALL subagents in a single message (Codex)**

> **Codex platform:** Uses `spawn_agent` + `wait_agent` + `close_agent` instead of the Agent tool.
> Requires `multi_agent = true` under `[features]` in `~/.codex/config.toml`.
> If `spawn_agent` is unavailable, tell the user to add that config and restart Codex.

Call `spawn_agent` once per chunk — ALL in the same response so they run in parallel. Build the message by wrapping the extraction prompt in task-delegation framing:

```
spawn_agent(agent_type="worker", message="Your task is to perform the following. Follow the instructions below exactly.\n\n<agent-instructions>\n[extraction prompt, with FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE, and CHUNK_PATH substituted]\n</agent-instructions>\n\nExecute this now. Write the structured JSON to CHUNK_PATH and return only a completion status.")
```

Give every agent a distinct absolute `CHUNK_PATH` under `graphify-out/`, as
required by the extraction prompt. After all agents are dispatched, collect
completion statuses sequentially:
```
result = wait_agent(handle); close_agent(handle)   # repeat per handle
```

Each worker must write its JSON to its assigned `CHUNK_PATH`; its inline return
is not a substitute for the file. Do not accumulate or merge results in memory.
After every worker completes, continue with the common Step B3 package validator,
which checks all chunk files before any merge or persistence.

Subagent prompt template:

See `references/extraction-spec.md` for the compact subagent prompt (rules, node-ID format, confidence rubric, hyperedge and vision rules, JSON schema). Load it only here, only when at least one chunk holds a doc, paper, or image; a pure-code corpus has skipped Part B and never reads it. Pass each agent that prompt verbatim with FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE, and CHUNK_PATH substituted. Its inline return is only a completion status; the distinct CHUNK_PATH file is the sole accepted semantic result.
