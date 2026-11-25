**Step B2 - Dispatch ALL subagents in a single message**

> Uses the host's parallel subagent tool: Claude's `Task`, an `Agent` tool, or
> Freebuff's `spawn_agents` (an array of `{agent_type, prompt}` entries).
> Make one call per chunk — ALL in the same response so they run in parallel.

Pass the extraction prompt as the subagent's prompt/task description:

```
Task(description="Your task is to perform the following. Follow the instructions below exactly.\n\n<agent-instructions>\n[extraction prompt, with FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE substituted]\n</agent-instructions>\n\nExecute this now. Output ONLY the structured JSON response.")
# Agent tool: pass the same text as the call's prompt.
# spawn_agents: one {agent_type: <a writer-capable agent>, prompt: <the same text>} entry per chunk.
```

**Important - subagent type:** use an agent that can **write files to disk** (Claude's `general-purpose`, or the host's equivalent coding agent with Write/Bash access). Do NOT use a read-only explore/research agent — it cannot write chunk files and silently drops extraction results.

Each subagent writes its result to its own `graphify-out/.graphify_chunk_NN.json`. Collect results as each subagent completes and parse each as JSON.

**Serial fallback:** if the host exposes no spawnable agent that can write files, extract the chunks sequentially in the main context instead, writing each `graphify-out/.graphify_chunk_NN.json` to disk before merging. Slower, but the same chunk files and the same result.

CHUNK_PATH must be an **absolute** path — derive it before dispatching:
```bash
PROJECT_ROOT=$(pwd)  # cwd — where Part C globs graphify-out/ (NOT .graphify_root/scan dir, #1392)
# Then for chunk N: CHUNK_PATH="${PROJECT_ROOT}/graphify-out/.graphify_chunk_0N.json"
```

Subagent prompt template:

See `references/extraction-spec.md` for the exact subagent prompt (JSON schema, node-ID rules, confidence rubric, hyperedge, and vision rules). Load it only here, only when at least one chunk holds a doc, paper, or image; a pure-code corpus has skipped Part B and never reads it. Pass each subagent that prompt verbatim with FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE, and CHUNK_PATH substituted, and have it write the result to CHUNK_PATH.
