# Design: Incremental Updates + Entity Deduplication

**Date:** 2026-05-04
**Issues:** #698 (incremental updates), entity deduplication (no issue, proactive)
**Branch:** v7

---

## Problem

1. `graphify extract` rebuilds the full graph from scratch every run — re-sends all files to the LLM regardless of what changed. For a 1000-file Markdown corpus updated daily this is expensive.

2. LLM extraction is chunk-by-chunk — the same real-world concept can get different labels across chunks (`AuthManager`, `AuthenticationManager`, `auth_mgr`). No semantic dedup exists beyond exact string normalization.

---

## Pipeline (every `graphify extract` run)

```
detect (full or incremental, auto-detected)
    ↓
AST extract (code files, AST cache-aware)
    ↓
Semantic LLM extract (doc/paper/image files, semantic cache-aware)
    ↓
build_merge (merge into existing graph, prune deleted nodes)
    ↓
deduplicate_entities (normalize → entropy gate → MinHash/LSH → Jaro-Winkler → community boost → optional LLM)
    ↓
cluster (full graph, always re-run)
    ↓
score_all + god_nodes + surprising_connections
    ↓
write graph.json + .graphify_analysis.json + manifest.json
```

---

## Feature 1: Incremental Updates

### Auto-detection
If `graphify-out/manifest.json` + `graphify-out/graph.json` both exist → incremental mode. No flag needed. First run is always full.

### Incremental mode changes
- `detect_incremental(target)` instead of `detect(target)` — returns `new_files`, `unchanged_files`, `deleted_files`
- Only `new_files` go through AST + LLM extraction
- `build_merge(new_chunks, prune_sources=deleted_files)` instead of `build_from_json` — merges into existing graph, prunes nodes from deleted files
- `manifest.json` written only on successful completion (crash mid-run does not corrupt next run's diff)

### Semantic cache (both full and incremental mode)
- Before LLM call: `check_semantic_cache(files)` splits into `(cached_results, uncached_files)`
- Only `uncached_files` sent to `extract_corpus_parallel`
- After LLM call: `save_semantic_cache(fresh_results)` — keyed by content hash
- On file rename: `source_file` updated to new path in cached result (same pattern as existing AST cache)

### Output summary
```
[graphify extract] incremental: 20 changed, 980 cached, 2 deleted
[graphify extract] graph: 4,821 nodes, 12,304 edges, 43 communities
[graphify extract] tokens: 18,432 in / 6,201 out, est. cost: $0.08
```

### Files changed
- `graphify/__main__.py` — `elif cmd == "extract":` block only (~5 targeted changes)

---

## Feature 2: Entity Deduplication

### New module: `graphify/dedup.py`
Single responsibility. Called from `build.py` after graph construction. Returns deduplicated `(nodes, edges)`.

### Pipeline

**Step 1 — Exact normalization**
Wire up the dormant `deduplicate_by_label` in `build.py`. Catches case/punctuation variants across files. Free win, already written.

**Step 2 — Entropy gate**
Skip fuzzy matching on labels with < 2.5 bits/char entropy. Short ambiguous names (`"AI"`, `"DB"`, `"x"`) are too risky to auto-merge. Only high-entropy labels proceed to steps 3-4.

**Step 3 — MinHash + LSH blocking** (`datasketch`)
3-gram shingles, 128 permutations, threshold 0.7. Generates candidate pairs in O(n) instead of O(n²). Sub-second at 10k nodes.

**Step 4 — Jaro-Winkler verification** (`rapidfuzz`)
Each candidate pair verified at ≥ 0.92. Catches typos, plurals, spacing variants. Pairs below threshold discarded.

**Step 5 — Same-community boost**
Pairs where both nodes share a Leiden community ID get +0.05 score bonus. Graphify-specific advantage — community structure is a strong signal that GraphRAG/LightRAG don't exploit.

**Step 6 — Union-find merge**
Confirmed pairs fed into union-find → connected components → each component merged into one node. Edges rewired to survivor. Self-loops dropped. Prefer shorter non-chunk-suffixed IDs as survivor.

**Step 7 — Optional LLM tiebreaker** (`--dedup-llm` flag)
Ambiguous pairs (score 0.75–0.85) batched in groups of 30, one LLM call per batch. ~$0.01 total for 10k nodes. Off by default.

### Integration point
Dedup runs after `build_merge` / `build_from_json`, before `cluster`. Order matters: cleaner graph → better community detection.

```python
# in build.py
G = build_merge(...)          # or build_from_json
G = deduplicate_entities(G)   # new step
communities = cluster(G)      # unchanged
```

### New dependencies
- `datasketch` — always required (added to `[project.dependencies]`)
- `rapidfuzz` — always required (added to `[project.dependencies]`)
- No `sentence-transformers` / PyTorch dependency

### Files changed
- `graphify/dedup.py` — new module, full pipeline
- `graphify/build.py` — call `deduplicate_entities` after graph construction; wire dormant `deduplicate_by_label`
- `graphify/__main__.py` — add `--dedup-llm` flag parsing in extract block
- `pyproject.toml` — add `datasketch`, `rapidfuzz` to base dependencies

---

## Testing

- Unit tests for each dedup step in isolation (`tests/test_dedup.py`)
- Integration test: two chunks with overlapping entity labels → single merged node in output graph
- Incremental test: run extract twice, assert second run makes zero LLM calls for unchanged files
- Rename test: rename a file, assert cache hit and `source_file` updated correctly
- Delete test: delete a file, assert its nodes are pruned from graph

---

## Non-goals

- `--dedup embed` (MiniLM cosine) — explicitly excluded, no PyTorch dependency
- Incremental support for `graphify update` (AST-only) — already handled by existing AST cache
- Dedup across different graph.json files (merge two graphs) — separate feature
