# graphify reference: incremental update and cluster-only

Load this only when the user passed `--update` or `--cluster-only`. A first-time full build never reads this file.

## For --update (incremental re-extraction)

Use when you've added or modified files since the last run. Only re-extracts changed files - saves tokens and time.

```bash
$(cat graphify-out/.graphify_python) -c "
import sys, json
from graphify.detect import detect_incremental, save_manifest
from pathlib import Path

result = detect_incremental(Path('INPUT_PATH'))
new_total = result.get('new_total', 0)
print(json.dumps(result, indent=2, ensure_ascii=False))
Path('graphify-out/.graphify_incremental.json').write_text(json.dumps(result, ensure_ascii=False), encoding=\"utf-8\")
deleted = list(result.get('deleted_files', []))
if new_total == 0 and not deleted:
    print('No files changed since last run. Nothing to update.')
    raise SystemExit(0)
if deleted:
    print(f'{len(deleted)} deleted file(s) to prune.')
if new_total > 0:
    print(f'{new_total} new/changed file(s) to re-extract.')
"
```

Then populate `.graphify_detect.json` so Steps 3A–6 (which read it unconditionally) see the right state for an incremental run. `files` carries the changed subset (drives Step 3A AST + Step 3B0 cache check on only what changed); `all_files` carries the full corpus for any step that needs corpus-wide context:

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from pathlib import Path
r = json.loads(Path('graphify-out/.graphify_incremental.json').read_text(encoding=\"utf-8\"))
Path('graphify-out/.graphify_detect.json').write_text(json.dumps({
    'files': r.get('new_files', {}),
    'all_files': r.get('files', {}),
    'total_files': r.get('new_total', 0),
    'total_words': r.get('total_words', 0),
    'skipped_sensitive': r.get('skipped_sensitive', []),
    'needs_graph': True,
}, ensure_ascii=False), encoding=\"utf-8\")
"
```

If new files exist, first check whether all changed files are code files:

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from pathlib import Path

result = json.loads(open('graphify-out/.graphify_incremental.json', encoding='utf-8').read()) if Path('graphify-out/.graphify_incremental.json').exists() else {}
code_exts = {'.py','.ts','.js','.go','.rs','.java','.cpp','.c','.rb','.swift','.kt','.cs','.scala','.php','.cc','.cxx','.hpp','.h','.kts','.lua','.toc','.f','.F','.f90','.F90','.f95','.F95','.f03','.F03','.f08','.F08'}
new_files = result.get('new_files', {})
all_changed = [f for files in new_files.values() for f in files]
code_only = all(Path(f).suffix.lower() in code_exts for f in all_changed)
print('code_only:', code_only)
"
```

If `code_only` is True: print `[graphify update] Code-only changes detected - skipping semantic extraction (no LLM needed)`, run only Step 3A (AST) on the changed files, skip Step 3B entirely (no subagents), then go straight to merge and Steps 4–8.

If `code_only` is False (any changed file is a doc/paper/image/video): **first, if any changed file is in `new_files['video']`, run `references/transcribe.md` (Step 2.5) on those files, then rewrite `.graphify_detect.json` to move the resulting transcript paths into `files['document']` and drop `files['video']`** — otherwise raw `.mp4/.mp3` paths are fed to semantic subagents as unreadable media (#1392). Then run the full Steps 3A–3C pipeline as normal.


If no new files exist (only deletions), create an empty extraction so the merge step can prune:

```bash
if [ ! -f graphify-out/.graphify_extract.json ]; then
    echo '[graphify update] Only deletions -- creating empty extraction for merge.'
    $(cat graphify-out/.graphify_python) -c "
import json
from pathlib import Path
Path('graphify-out/.graphify_extract.json').write_text(json.dumps({'nodes':[],'edges':[],'hyperedges':[],'input_tokens':0,'output_tokens':0}), encoding='utf-8')
"
fi
```


Then:

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from pathlib import Path
from graphify.build import build_merge
from graphify.detect import save_manifest

# Load new extraction and incremental state
new_extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text(encoding=\"utf-8\"))
incremental = json.loads(Path('graphify-out/.graphify_incremental.json').read_text(encoding=\"utf-8\"))
deleted = list(incremental.get('deleted_files', []))
# prune_sources is ONLY for genuinely DELETED files. Changed/re-extracted files are
# handled by build_merge's replace-on-re-extract (#1344): every source_file in
# new_chunks is dropped from the base before merge, so old/stale nodes don't survive.
# Do NOT add `changed` here: with root= passed, prune_set relativizes to the same base
# as the freshly merged nodes and would DELETE the re-extracted content (#1178 is moot
# now that replace — not the dedup pass — reconciles changed files).
prune = list(deleted) or None

# Use build_merge() — reads graph.json directly without NetworkX round-trip
# so edge direction (calls, implements, imports) is always preserved (#801).
# Pass root= so prune_sources (absolute paths from detect_incremental) are
# relativized to match the graph's relative source_file values; without it
# nothing is pruned and stale nodes accumulate on every update (#1361).
# directed=IS_DIRECTED: replace IS_DIRECTED with True if --directed was given, else
# False. Without it a --directed --update silently rebuilds undirected and collapses
# reciprocal A<->B edges (#1392).
G = build_merge(
    [new_extraction],
    graph_path='graphify-out/graph.json',
    prune_sources=prune,
    root='INPUT_PATH',
    directed=IS_DIRECTED,
)
print(f'[graphify update] Merged: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges')

# Write merged result back to .graphify_extract.json so Step 4 sees the full graph
merged_out = {
    'nodes': [{'id': n, **d} for n, d in G.nodes(data=True)],
    'edges': [
        # Explicit source/target last so they win over any stale attrs in d.
        {**{k: val for k, val in d.items() if k not in ('_src', '_tgt', 'source', 'target')},
         'source': d.get('_src', u), 'target': d.get('_tgt', v)}
        for u, v, d in G.edges(data=True)
    ],
    # G.graph["hyperedges"] holds hyperedges from both existing graph.json
    # and new_extraction (build_merge combines them). Falling back to
    # new_extraction only would silently drop prior-run hyperedges (#801).
    'hyperedges': list(G.graph.get('hyperedges', [])),
    'input_tokens': new_extraction.get('input_tokens', 0),
    'output_tokens': new_extraction.get('output_tokens', 0),
}
Path('graphify-out/.graphify_extract.json').write_text(json.dumps(merged_out, ensure_ascii=False), encoding=\"utf-8\")
print(f'[graphify update] Merged extraction written ({len(merged_out[\"nodes\"])} nodes, {len(merged_out[\"edges\"])} edges)')

# Save manifest so next --update diffs against today's state, not the
# prior run's baseline (prevents ghost-node reports on subsequent updates).
# root= matches the build_merge call above so the manifest keys stay relative to
# the scan root — portable across clones/machines, so --update keeps matching
# cached files instead of missing every one after a move (#1417).
#
# Only stamp semantic files (docs/papers/images) that ACTUALLY produced output
# THIS run (new_extraction is this run's fresh extraction, read above before the
# merge overwrote the file): a changed doc whose chunk failed must stay unstamped
# so the next --update re-queues it, otherwise it is marked done and its content
# is lost forever (#2015). Mirrors the library extract path
# (cli._stamped_manifest_files + clear_semantic + scan_corpus).
from graphify.cli import _stamped_manifest_files
_manifest_files = _stamped_manifest_files(incremental['files'], new_extraction, Path('INPUT_PATH'))
# Changed semantic files dispatched this run but NOT stamped had their chunk fail
# or be omitted; clear any stale semantic_hash so they are re-queued (#1948).
_sem_types = ('document', 'paper', 'image')
_dispatched = {f for t, fl in incremental.get('new_files', {}).items() if t in _sem_types for f in fl}
_stamped = {f for fl in _manifest_files.values() for f in fl}
_cleared = _dispatched - _stamped
# scan_corpus = the RAW full corpus so in-root files newly excluded since last run
# are dropped rather than masquerading as deletions; untouched rows preserved (#1908).
_scan = {f for fl in incremental['files'].values() for f in fl}
save_manifest(_manifest_files, root='INPUT_PATH', scan_corpus=_scan, clear_semantic=_cleared or None)
print('[graphify update] Manifest saved.')
"
```

Then run Steps 4–8 on the merged graph as normal.

After Step 4, show the graph diff:

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from graphify.analyze import graph_diff
from graphify.build import build_from_json
from networkx.readwrite import json_graph
import networkx as nx
from pathlib import Path

# Load old graph (before update) from backup written before merge
old_data = json.loads(Path('graphify-out/.graphify_old.json').read_text(encoding=\"utf-8\")) if Path('graphify-out/.graphify_old.json').exists() else None
new_extract = json.loads(Path('graphify-out/.graphify_extract.json').read_text(encoding=\"utf-8\"))
G_new = build_from_json(new_extract, directed=IS_DIRECTED)

if old_data:
    G_old = json_graph.node_link_graph(old_data, edges='links')
    diff = graph_diff(G_old, G_new)
    print(diff['summary'])
    if diff['new_nodes']:
        print('New nodes:', ', '.join(n['label'] for n in diff['new_nodes'][:5]))
    if diff['new_edges']:
        print('New edges:', len(diff['new_edges']))
"
```

Before the merge step, save the old graph: `cp graphify-out/graph.json graphify-out/.graphify_old.json`
Clean up after: `rm -f graphify-out/.graphify_old.json`

---

## For --cluster-only

Skip Steps 1–3. Re-run clustering on the existing graph:

```bash
graphify cluster-only .
```

`graphify cluster-only .` is **self-contained**: it re-clusters, names communities, and regenerates `GRAPH_REPORT.md`, `graph.json`, and `graph.html` from the existing graph. **Do not re-run Steps 5–9** — they read intermediate files (`.graphify_extract.json`, `.graphify_detect.json`, `.graphify_analysis.json`) that a prior build's cleanup (Step 9) already deleted, so they raise `FileNotFoundError` (#1392). When it finishes, present the refreshed `GRAPH_REPORT.md` summary as usual.

---

## ⚠️ Failure modes seen in the field (read before merging)

Each of these cost a real debugging round on a large repo (~4000 nodes, ~106
files). They are not hypothetical, and none of them errors — every one fails
silently and leaves a plausible-looking graph.

### 1. `prune_sources` does not do what it reads like

Two separate traps, and they compound:

- It matches paths **exactly as the graph stores them**, which is *relative*.
  Passing an absolute path prunes nothing, silently, and you end up with the old
  and new nodes for that file side by side.
- `build_merge` prunes **after** inserting. So naming a source you are
  simultaneously re-adding deletes the **new** nodes too, and you are left with
  neither.

**What works:** strip that source's nodes and edges from `graph.json` by hand
first, then merge with **no** `prune_sources` at all.

```python
drop = {n['id'] for n in g['nodes'] if str(n.get('source_file')) in FULL_REEXTRACT}
g['nodes'] = [n for n in g['nodes'] if n['id'] not in drop]
g['links'] = [l for l in g['links']
              if l['source'] not in drop and l['target'] not in drop]
```

⚠️ Only prune a source you re-extracted in **FULL**. A partially re-extracted
file (say you only re-read the changed section of a large doc) must **not** be
pruned, or everything you did not re-read disappears.

### 2. Hyperedges live in TWO places and the merge overwrites them

`graph.json` carries `hyperedges` at top level **and** under `graph`. Filter only
one copy and `build_merge` keeps just the incoming batch — 36 vanished this way
in one run, with no error and no warning.

**Reconstruct them explicitly after every merge**, combining the previous graph's
with the new batch (new wins on id clash), then assert every member id exists.

### 3. Keep that assertion — it finds pre-existing damage

The first time it ran it surfaced four hyperedges that had been dangling in the
graph *already*: extraction agents can name a member id they never emit as a
node, and nothing validates that at write time.

⚠️ The instinct is to blame the change you just made. Check the previous
`graph.json` before concluding that — in that case they had been broken for a
whole wave.

**Repair rather than discard:** drop the phantom member when **3 or more real
members remain** (the grouping is still true); only drop the hyperedge when too
few survive.

### 4. AST output paths do not match the graph's

`extract()` returns `source_file` as an **absolute path with the platform
separator** (`C:\repo\tests\foo.spec.js`), while the graph stores **relative,
forward-slash** paths. Merging raw creates a duplicate source for every file —
the ghost-node shape.

Normalise `source_file` on **nodes, edges and hyperedges** before merging, then
assert the final graph contains zero absolute or backslash paths.

### 5. Prefer a targeted update to a full one

Check how much actually changed before planning chunks. In one run `detect_incremental`
reported 14 changed files (~970 KB), but `git diff` showed **326 lines across 5
files** — and two of the flagged files had *zero* diff, changed only in metadata.
Three agents on the changed material beat ten re-deriving untouched prose.

**State the trade-off when you do this:** a partially re-extracted file is not
pruned, so nodes for *edited* lines keep their earlier phrasing. Additions land;
rewrites may lag. That is usually the right trade, but it should be a decision,
not an accident.
