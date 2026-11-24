**Step B2 - Dispatch ALL subagents in a single message (DeepSeek Harness)**

> **DeepSeek Harness platform:** Dispatch through the built-in `subagent` tool, one delegation per chunk. Call it once per chunk - ALL in the same response so they run in parallel. If you make one call, wait for it, then make another, you are doing it sequentially and defeating the purpose.

**IMPORTANT - the child must write files:** every delegation needs the file tools, because its result is collected from `graphify-out/.graphify_chunk_NN.json` on disk. A read-only child returns prose and silently drops its extraction.

Each subagent receives this exact prompt (substitute FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE, and CHUNK_PATH).

CHUNK_PATH must be an **absolute** path — derive it before dispatching:
```bash
PROJECT_ROOT=$(pwd)  # cwd — where Part C globs graphify-out/ (NOT .graphify_root/scan dir, #1392)
# Then for chunk N: CHUNK_PATH="${PROJECT_ROOT}/graphify-out/.graphify_chunk_0N.json"
```

Subagent prompt template:

See `references/extraction-spec.md` for the exact subagent prompt (JSON schema, node-ID rules, confidence rubric, frontmatter, hyperedge, and vision rules). Load it only here, only when at least one chunk holds a doc, paper, or image; a pure-code corpus has skipped Part B and never reads it. Pass each subagent that prompt verbatim with FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE, and CHUNK_PATH substituted, and have it write the result to CHUNK_PATH.
