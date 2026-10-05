**Step B2 - Dispatch subagents and paste their responses**

> **No automated subagent tool:** this host has no parallel Agent/Task API, so
> extraction is driven by hand. Dispatch a subagent per chunk however the host
> allows (a fresh conversation, a parallel pane), then paste each response back.

For each chunk of uncached files (20-25 per chunk), give a subagent the extraction prompt below. When it returns, paste its JSON response and write it to that chunk's file so Step B3 can collect it:

Use the host's file-writing tool to save each parsed JSON response as data to its assigned absolute CHUNK_PATH from B1. Copy the matching FILE_LIST into the extraction prompt. Do not paste model output into an executable shell/Python command or construct a numbered filename. Every current-run response must pass the shared B3 ownership check before caching or merge.

Subagent prompt template:

See `references/extraction-spec.md` for the exact subagent prompt (JSON schema, node-ID rules, confidence rubric, hyperedge, and vision rules). Load it only here, only when at least one chunk holds a doc, paper, or image; a pure-code corpus has skipped Part B and never reads it. Pass each subagent that prompt verbatim with FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, and DEEP_MODE substituted, and write its response to that chunk's file.
