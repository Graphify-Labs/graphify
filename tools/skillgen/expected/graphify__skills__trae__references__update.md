# graphify reference: incremental update and cluster-only

Load this only when the user passed `--update` or `--cluster-only`. A first-time full build never reads this file.

## For --update (incremental re-extraction)

Use when you've added or modified files since the last run. Only re-extracts changed files - saves tokens and time.

```bash
graphify pipeline detect-incremental INPUT_PATH
```

Replace INPUT_PATH with the actual path. This diffs the corpus against the manifest
and writes `.graphify_incremental.json` (the raw result) plus `.graphify_detect.json`,
so Steps 3A–6 (which read it unconditionally) see the right state for an incremental
run: `files` carries the changed subset (drives Step 3A AST + Step 3B0 cache check on
only what changed) and `all_files` the full corpus. It prints the changed/deleted
counts; if nothing changed it says so.

If new files exist, check whether all changed files are code files:

```bash
graphify pipeline code-only-check
```

If `code_only` is True: print `[graphify update] Code-only changes detected - skipping semantic extraction (no LLM needed)`, run only Step 3A (AST) on the changed files, skip Step 3B entirely (no subagents), then go straight to merge and Steps 4–8.

If `code_only` is False (any changed file is a doc/paper/image/video): **first, if any changed file is in `new_files['video']`, run `references/transcribe.md` (Step 2.5) on those files, then rewrite `.graphify_detect.json` to move the resulting transcript paths into `files['document']` and drop `files['video']`** — otherwise raw `.mp4/.mp3` paths are fed to semantic subagents as unreadable media (#1392). Then run the full Steps 3A–3C pipeline as normal.


If no new files exist (only deletions), create an empty extraction so the merge step can prune:

```bash
graphify pipeline empty-extract
```

Then merge this run's extraction into the existing graph and re-stamp the manifest:

```bash
graphify pipeline update-merge INPUT_PATH
```

Replace INPUT_PATH with the actual path (same value used above). Add `--directed` if
`--directed` was given. This uses `build_merge` (reads graph.json directly, preserving
edge direction, #801), prunes only the genuinely deleted files (changed files are
reconciled by replace-on-re-extract, #1344), and relativizes to the scan root so
pruning matches the graph's relative `source_file` values (#1361). It writes the merged
result back to `.graphify_extract.json` for Step 4, and re-stamps the manifest so the
next `--update` diffs against today's state — stamping only semantic files that
actually produced output, and clearing stale hashes for dispatched-but-unstamped ones
(#2015, #1948, #1908).

Then run Steps 4–8 on the merged graph as normal.

After Step 4, show the graph diff:

```bash
graphify pipeline graph-diff
```

Add `--directed` if `--directed` was given. It reads the pre-merge backup
`.graphify_old.json` and prints the summary plus any new nodes/edges.

Before the merge step, save the old graph: `cp graphify-out/graph.json graphify-out/.graphify_old.json`
Clean up after: `rm -f graphify-out/.graphify_old.json`

---

## For --cluster-only

Skip Steps 1–3. Re-run clustering on the existing graph:

```bash
graphify cluster-only .
```

`graphify cluster-only .` is **self-contained**: it re-clusters, names communities, and regenerates `GRAPH_REPORT.md`, `graph.json`, and `graph.html` from the existing graph. **Do not re-run Steps 5–9** — they read intermediate files (`.graphify_extract.json`, `.graphify_detect.json`, `.graphify_analysis.json`) that a prior build's cleanup (Step 9) already deleted, so they raise `FileNotFoundError` (#1392). When it finishes, present the refreshed `GRAPH_REPORT.md` summary as usual.
