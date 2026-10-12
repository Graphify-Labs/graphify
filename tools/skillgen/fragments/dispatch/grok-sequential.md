**Step B2 - Extract each chunk sequentially (Grok Build)**

> **Grok Build:** extract the chunks yourself, one after another, in this session. Finish one chunk's file before starting the next, and process every chunk before moving on to Step B3.

For each chunk of uncached files (20-25 per chunk), read the files in that chunk, apply the extraction prompt below, and write the resulting JSON to that chunk's file so Step B3 can collect it. CHUNK_PATH must be an **absolute** path:

```bash
PROJECT_ROOT=$(pwd)  # cwd — where Part C globs graphify-out/ (NOT .graphify_root/scan dir, #1392)
# Then for chunk N: CHUNK_PATH="${PROJECT_ROOT}/graphify-out/.graphify_chunk_0N.json"
```

Repeat for every chunk. Each chunk's JSON must land in its own `graphify-out/.graphify_chunk_NN.json` before Step B3 runs.

Extraction prompt template:

See `references/extraction-spec.md` for the compact extraction prompt (rules, node-ID format, confidence rubric, hyperedge and vision rules, JSON schema). Load it only here, only when at least one chunk holds a doc, paper, or image; a pure-code corpus has skipped Part B and never reads it. Apply that prompt verbatim to each chunk with FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE, and CHUNK_PATH substituted, and write the result to CHUNK_PATH.
