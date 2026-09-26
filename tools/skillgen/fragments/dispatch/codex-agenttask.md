**Step B2 - Dispatch ALL subagents in a single message (Codex)**

Create `graphify-out/` under the current working directory. For each chunk, assign a unique absolute `CHUNK_PATH` there, named `.graphify_chunk_NN.json` (for example, resolve `graphify-out/.graphify_chunk_01.json` against the current working directory). The parent supplies this path; the subagent must write the JSON directly to it.

See `references/extraction-spec.md` for the shared extraction prompt (rules, node-ID format, confidence rubric, hyperedge and vision rules, JSON schema). Load it only here, only when at least one chunk holds a doc, paper, or image; a pure-code corpus has skipped Part B and never reads it. Pass each agent that prompt verbatim with FILE_LIST, CHUNK_NUM, TOTAL_CHUNKS, DEEP_MODE, and CHUNK_PATH substituted. FILE_LIST contains absolute source paths.

Use the actual Codex subagent tools exposed in this session, following their declared argument schemas. Call `spawn_agent` once per chunk with the substituted prompt and file-write access. Dispatch all chunks before waiting, within the session's concurrency limit; if needed, wait for a running chunk to finish before dispatching the next. Do not select a read-only agent.

Wait until every dispatched subagent has completed using the available wait tool (for example, `collaboration.wait_agent` for collaboration tools, or `wait` for Codex tools exposing it). Track completion messages and agent status: a wait notification or timeout does not by itself mean every agent has finished. Do not parse wait results or completion messages as extraction JSON. Each subagent saves its result at CHUNK_PATH; after all agents have completed, proceed to the shared Step B3 to check the chunk files, collect results, cache, and merge.

If subagent tools are unavailable, report that limitation and ask the user to enable Codex multi-agent support and restart the session.
