# Release qualification: public Helix `0.2.0b3` (draft)

Graphify is pinned to the matching public PyPI releases
`helix-db==0.2.0b3` and `helix-db-embedded==0.2.0b3`. It uses ordinary public
`helixdb` imports and rejects incompatible SDK versions, missing embedded
payloads, malformed store paths, and unavailable required public APIs. No
Helix source checkout, Git dependency, private wheel, locally compiled
runtime, direct UniFFI import, dynamic native loader, or SDK monkeypatch is
used.

Native Windows x86_64 is a supported Graphify target. Qualification still
requires a normal public `win_amd64` embedded wheel for the exact pinned
version. Public b3 currently publishes macOS universal2 and Linux
x86_64/aarch64 artifacts, but no Windows artifact, so the PR remains draft.

## Graphify acceptance

- Complete local suite: **2,921 passed, 3 skipped**. The Python 3.12 clean
  environment accounted for the same behavior surface after installing the
  declared development group, including wheel-packaging tests.
- CI matrix: Linux x86_64 on Python 3.10 and 3.12, Linux aarch64 on Python
  3.12, macOS universal2 on Python 3.12, and native Windows x86_64 on Python
  3.10 and 3.12.
- All four graph kinds, typed IDs, keyed multiedges, self-loops, hyperedges,
  atomic activation, retained rollback, corruption, writer exclusion,
  concurrent readers, generation hot reload, and read-only enforcement: passed.
- Incremental update and deletion, extraction cache, analysis, learning state,
  clustering, affected/PR analysis, global aggregation, hooks, watch, exports,
  MCP stdio, and MCP Streamable HTTP: passed.
- Generated skill check (134 artifacts), host coverage audit, schema singleton,
  monolith contract, and always-on contract: passed.
- Ruff, scoped Pyright for the native integration surface, Bandit medium/high,
  locked-runtime pip-audit, source compilation, package build, and
  `git diff --check`: passed locally.
- Wheel installation in a clean Python 3.12 environment: passed. The installed
  production dependency set contains neither NetworkX nor graspologic.
- Installed-wheel CLI flow: build native store, query, and shortest path: passed.

Production source contains no NetworkX/graspologic imports or compatibility
graph. Legacy JSON graph files are never migrated, read, modified, or deleted;
the watch path emits one obsolete-format warning and requires a source rebuild.
Obsidian's `.obsidian/graph.json` remains solely because that filename belongs
to Obsidian's presentation configuration, not Graphify storage.

## Benchmark qualification

The isolated benchmark comparator is the only environment that installs
NetworkX. The deterministic parity corpus and full raw measurements are in
[`parity-networkx.json`](parity-networkx.json) and
[`helix-vs-networkx.json`](helix-vs-networkx.json); reproduction commands and
interpreted results are in [`RESULTS.md`](RESULTS.md).

The public b3 candidate **does not pass the release gates**:

| Graph | Helix ingest | Helix cold open | Peak RSS (informational) | Active store | Slowest absolute hot op |
|---|---:|---:|---:|---:|---:|
| 5k / 15k | 10.14s | 1.46s | 343.3 MiB | 35.35 MiB | 27.40ms |
| 20k / 60k | 40.67s | 6.45s | 993.5 MiB | 143.71 MiB | 12.17ms |

At 20k/60k, weighted Leiden, sampled node centrality, and sampled edge
centrality are respectively **9.30x**, **8.15x**, and **3.73x** faster than the
current v8 NetworkX/JSON comparator, so the three native analytics gates pass.
Absolute hot-operation limits also pass. Build, 1% update, cold-open, active
and post-update storage, and relative warm-operation gates fail.

Default retention deletes the inactive generation through public Helix
operations, but b3 does not physically reclaim enough embedded-store space;
the 20k/60k store grows from 143.71 MiB to 299.32 MiB after the 1% update.
Graphify deliberately does not manipulate SST/WAL files or call private
maintenance APIs. Peak RSS is reported but is non-blocking, as required.

The Graphify engineers' `comfywerk`, `agent`, `backend`, `passport`, and
`erpnext` corpora were not available in this checkout, so real-corpus and gold
query qualification remains outstanding. Synthetic results are not a
substitute for that gate.

## Conclusion

The integration is correct enough for a draft PR, but is not production-ready.
It must remain draft until the exact public package pair provides a passing
Windows wheel, all CI platforms pass without core skips, the engineers' real
corpora and gold queries pass, and the failed public-package performance and
disk-reclamation gates are resolved without hidden workarounds.
