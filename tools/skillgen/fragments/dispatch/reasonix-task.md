**Step B2 - Dispatch ALL subagents in a single message**

Use Reasonix's `task` tool for each chunk. Put the complete extraction instructions in `prompt`; `description` is only a short label. Each task must write its JSON result to a distinct absolute `CHUNK_PATH` under the current workspace's `graphify-out/` directory.

```text
task(prompt="[extraction prompt with FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE, and absolute CHUNK_PATH substituted]", description="Extract graph chunk", write_paths=["[absolute CHUNK_PATH]"])
```

Use disjoint `write_paths` when dispatching multiple chunks. Do not use `read_only_task`, since it cannot write the result files. Collect all task results and verify their files before proceeding to Step B3. If the `task` tool is unavailable, process chunks in the current session and write the same JSON files; do not invent a successful child run.

Subagent prompt template:

See `references/extraction-spec.md` for the exact extraction prompt, JSON schema, node-ID rules, confidence rubric, hyperedge, and vision rules. Load it only when at least one chunk contains a document, paper, or image; a pure-code corpus skips Part B. Substitute every placeholder and include the complete prompt in each task.
