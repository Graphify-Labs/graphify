# graphify reference: incremental update and cluster-only

Load this only when the user passed `--update` or `--cluster-only`. A first-time full build never reads this file.

## For --update (incremental re-extraction)

Use when you've added or modified files since the last run. Only re-extracts changed files - saves tokens and time.

```bash
$(cat graphify-out/.graphify_python) -c "
import sys, json
from graphify.detect import detect_incremental, save_manifest
from pathlib import Path

from graphify.paths import out_path
from graphify.watch import _read_build_excludes, _read_build_gitignore
# Step B3.5 lists the files this run reads only partway, and the manifest write (and Step 9,
# if it runs) keeps them unstamped. Only B3.5 rewrites the list, so drop one an earlier run
# left: it would keep a file this run serves from the cache unstamped on every run (#4807).
Path('graphify-out/.graphify_partial.txt').unlink(missing_ok=True)
INPUT_PATH = Path('graphify-out/.graphify_root').read_text(encoding=\"utf-8-sig\").strip()
result = detect_incremental(Path(INPUT_PATH), extra_excludes=_read_build_excludes(out_path()), gitignore=_read_build_gitignore(out_path()))
new_total = result.get('new_total', 0)
nf = result.get('new_files', {})
print(json.dumps({
    'new_total': new_total,
    'deleted': len(result.get('deleted_files', [])),
    'new_by_type': {t: len(v) for t, v in nf.items()},
    'total_files': result.get('total_files'),
    'total_words': result.get('total_words'),
    'skipped_sensitive': result.get('skipped_sensitive', []),
}, indent=2, ensure_ascii=False))
print('Full result: graphify-out/.graphify_incremental.json')
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

If `code_only` is True: print `[graphify update] Code-only changes detected - skipping semantic extraction (no LLM needed)`, run Step 3A (AST) on the changed files, then follow only Part B's **Fast path** to overwrite `.graphify_semantic.json` with an empty result and run Part C to create `.graphify_extract.json` from the fresh AST result. Skip semantic cache checks/writes and subagents (Steps B0–B3); do not reuse semantic sidecars from a prior run. Continue to the incremental merge and Steps 4–8 only after Part C has completed.

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

# Load new extraction and incremental state
new_extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text(encoding=\"utf-8\"))
incremental = json.loads(Path('graphify-out/.graphify_incremental.json').read_text(encoding=\"utf-8\"))
INPUT_PATH = Path('graphify-out/.graphify_root').read_text(encoding=\"utf-8-sig\").strip()
deleted = list(incremental.get('deleted_files', []))
# prune_sources is ONLY for genuinely DELETED files. Changed/re-extracted files are
# handled by build_merge's replace-on-re-extract (#1344): every source_file in
# new_chunks is dropped from the base before merge, so old/stale nodes don't survive.
# Do NOT add changed here: with root= passed, prune_set relativizes to the same base
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
    root=INPUT_PATH,
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

# Keep this run's own extraction for the manifest stamp that runs after Step 4
# (.graphify_extract.json now holds the full merged graph; stamping from that would
# mark a changed doc whose chunk failed as done, losing its content forever, #2015),
# and record graph.json's state so the stamp can prove Step 4 rewrote it (#5097).
_graph = Path('graphify-out/graph.json')
_graph_stat = _graph.stat() if _graph.exists() else None
Path('graphify-out/.graphify_update_extract.json').write_text(json.dumps({
    'extraction': new_extraction,
    'graph_mtime_ns': _graph_stat.st_mtime_ns if _graph_stat else None,
    'graph_size': _graph_stat.st_size if _graph_stat else None,
}, ensure_ascii=False), encoding=\"utf-8\")
"
```

Then run Steps 4–8 on the merged graph as normal.

Run this stamp immediately after Step 4 has written `graph.json`, before Steps 5–8:

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from pathlib import Path
from graphify.detect import save_manifest

INPUT_PATH = Path('graphify-out/.graphify_root').read_text(encoding=\"utf-8-sig\").strip()
# The merge block saved this run's fresh extraction before it overwrote
# .graphify_extract.json with the full merged graph; stamp from this copy so a
# changed doc whose chunk failed stays unstamped and is re-queued (#2015).
_update_state = json.loads(Path('graphify-out/.graphify_update_extract.json').read_text(encoding=\"utf-8\"))
new_extraction = _update_state['extraction']
incremental = json.loads(Path('graphify-out/.graphify_incremental.json').read_text(encoding=\"utf-8\"))

# Step 4 must have rewritten graph.json this run. It exits non-zero instead of
# overwriting a graph it refuses, but an agent that reached this block anyway would
# mark the changed files done while graph.json still held the old content (#5097).
# The merge block recorded graph.json's stat before Step 4; an unchanged stat means
# Step 4 never wrote it, so refuse to stamp and leave the files queued.
_graph = Path('graphify-out/graph.json')
if not _graph.exists():
    raise SystemExit('[graphify update] Refusing to stamp the manifest: graphify-out/graph.json is missing.')
_graph_stat = _graph.stat()
if (_graph_stat.st_mtime_ns == _update_state.get('graph_mtime_ns')
        and _graph_stat.st_size == _update_state.get('graph_size')):
    raise SystemExit(
        '[graphify update] Refusing to stamp the manifest: Step 4 did not rewrite '
        'graphify-out/graph.json. Run Step 4 again (with --force if the shrink is '
        'intentional), then re-run this block. The changed files stay queued.'
    )

# Save manifest so next --update diffs against today's state, not the
# prior run's baseline (prevents ghost-node reports on subsequent updates).
# root= matches the merge block's build_merge call so the manifest keys stay
# relative to the scan root — portable across clones/machines, so --update keeps
# matching cached files instead of missing every one after a move (#1417).
#
# Only stamp semantic files (docs/papers/images) that ACTUALLY produced output
# THIS run: a changed doc whose chunk failed must stay unstamped so the next
# --update re-queues it, otherwise it is marked done and its content is lost
# forever (#2015). Mirrors the library extract path
# (cli._stamped_manifest_files + clear_semantic + scan_corpus).
from graphify.cli import _stamped_manifest_files
# A file a subagent only partly read (Step B3.5 lists it) DID produce output, so the
# filter alone would stamp it and the next --update would never re-queue it. Pass the
# list as Step 9 does after a full build, so it stays unstamped and is retried (#2225, #4807).
# Leave the list on disk: Step 9 reads it too if it runs after the update.
_pf = Path('graphify-out/.graphify_partial.txt')
_partial = {l.strip() for l in _pf.read_text(encoding='utf-8').splitlines() if l.strip()} if _pf.exists() else set()
_manifest_files = _stamped_manifest_files(incremental['files'], new_extraction, Path(INPUT_PATH), partial_source_files=_partial)
# Changed semantic files dispatched this run but NOT stamped had their chunk fail
# or be omitted; clear any stale semantic_hash so they are re-queued (#1948).
_sem_types = ('document', 'paper', 'image')
_dispatched = {f for t, fl in incremental.get('new_files', {}).items() if t in _sem_types for f in fl}
_stamped = {f for fl in _manifest_files.values() for f in fl}
_cleared = _dispatched - _stamped
# scan_corpus = the RAW full corpus so in-root files newly excluded since last run
# are dropped rather than masquerading as deletions; untouched rows preserved (#1908).
_scan = {f for fl in incremental['files'].values() for f in fl}
save_manifest(_manifest_files, root=INPUT_PATH, scan_corpus=_scan, clear_semantic=_cleared or None)
print('[graphify update] Manifest saved.')
"
```

This stamp must stay after Step 4. Step 4 refuses to overwrite a larger graph
(#479), and a stamp written before it ran would mark the changed files done while
`graph.json` still held the old content, so the next `--update` would report nothing
to do (#5097). The block also checks that `graph.json` changed since the merge block
and exits non-zero without stamping if it did not, so even a misordered run leaves
the changed files queued. The library path does the same: `graphify/watch.py` checks
the shrink before it writes the manifest.

After Step 4, show the graph diff:

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from graphify.analyze import graph_diff
from graphify.build import build_from_json
from graphify.paths import load_node_link_graph
import networkx as nx
from pathlib import Path

# Load old graph (before update) from backup written before merge
old_data = json.loads(Path('graphify-out/.graphify_old.json').read_text(encoding=\"utf-8\")) if Path('graphify-out/.graphify_old.json').exists() else None
new_extract = json.loads(Path('graphify-out/.graphify_extract.json').read_text(encoding=\"utf-8\"))
G_new = build_from_json(new_extract, directed=IS_DIRECTED)

if old_data:
    G_old = load_node_link_graph(old_data)
    diff = graph_diff(G_old, G_new)
    print(diff['summary'])
    if diff['new_nodes']:
        print('New nodes:', ', '.join(n['label'] for n in diff['new_nodes'][:5]))
    if diff['new_edges']:
        print('New edges:', len(diff['new_edges']))
"
```

Before the merge step, save the old graph: `cp graphify-out/graph.json graphify-out/.graphify_old.json`
Clean up after: `rm -f graphify-out/.graphify_old.json graphify-out/.graphify_update_extract.json`

---

## For --cluster-only

Skip Steps 1–3. Re-run clustering on the existing graph:

```bash
graphify cluster-only .
```

`graphify cluster-only .` is **self-contained**: it re-clusters, names communities, and regenerates `GRAPH_REPORT.md`, `graph.json`, and `graph.html` from the existing graph. **Do not re-run Steps 5–9** — they read intermediate files (`.graphify_extract.json`, `.graphify_detect.json`, `.graphify_analysis.json`) that a prior build's cleanup (Step 9) already deleted, so they raise `FileNotFoundError` (#1392). When it finishes, present the refreshed `GRAPH_REPORT.md` summary as usual.
