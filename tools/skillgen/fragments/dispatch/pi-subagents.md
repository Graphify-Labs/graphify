**Step B2 - Dispatch ALL subagents in a single message (Pi)**

> **Pi platform:** Dispatch through the `subagent` tool of the pi-subagents extension (`pi install npm:pi-subagents`), not a Claude Code Agent tool.

Dispatch one `delegate` subagent per chunk, all of them in parallel in a single run. If you start one chunk, wait for it, then start the next, you are doing it sequentially and defeating the purpose.

**IMPORTANT - agent:** Always use the builtin `delegate` agent. It has `read`, `bash`, `edit` and `write`, which the subagent needs to write its chunk file.

Each subagent receives this exact prompt (substitute FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE, and CHUNK_PATH).

CHUNK_PATH must be an **absolute** path — derive it before dispatching:
```bash
PROJECT_ROOT=$(pwd)  # cwd — where Part C globs graphify-out/ (NOT .graphify_root/scan dir, #1392)
# Then for chunk N: CHUNK_PATH="${PROJECT_ROOT}/graphify-out/.graphify_chunk_0N.json"
```

Subagent prompt template:

See `references/extraction-spec.md` for the exact subagent prompt (JSON schema, node-ID rules, confidence rubric, frontmatter, hyperedge, and vision rules). Load it only here, only when at least one chunk holds a doc, paper, or image; a pure-code corpus has skipped Part B and never reads it. Pass each subagent that prompt verbatim with FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE, and CHUNK_PATH substituted, and have it write the result to CHUNK_PATH.
