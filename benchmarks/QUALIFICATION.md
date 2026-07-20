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

- Complete local suite: **2,925 passed, 3 skipped**. The Python 3.12 clean
  environment accounted for the same behavior surface after installing the
  declared development group, including wheel-packaging tests.
- Complete Python 3.10 suite: **2,912 passed, 16 skipped**. The additional
  skips are the expected Python-version-gated optional video coverage; no
  Helix or retained core behavior was skipped.
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
[`helix-vs-networkx-2026-07-19.json`](helix-vs-networkx-2026-07-19.json); reproduction commands and
interpreted results are in [`RESULTS.md`](RESULTS.md).

The public b3 candidate **does not pass the release gates**:

| Graph | Helix ingest | Helix cold open | Peak RSS (informational) | Active store | Slowest absolute hot op |
|---|---:|---:|---:|---:|---:|
| 5k / 15k | 8.17s | 1.07s | 232.3 MiB | 35.12 MiB | 20.57ms |
| 20k / 60k | 32.55s | 4.88s | 647.1 MiB | 143.45 MiB | 8.93ms |

At 20k/60k, weighted Leiden, sampled node centrality, and sampled edge
centrality are respectively **9.76x**, **9.93x**, and **4.13x** faster than the
current v8 NetworkX/JSON comparator, so the three native analytics gates pass.
Absolute hot-operation limits also pass. Build, 1% update, cold-open, active
and post-update storage, and relative warm-operation gates fail.

Default retention deletes the inactive generation through public Helix
operations, but b3 does not physically reclaim enough embedded-store space;
the 20k/60k store grows from 143.45 MiB to 298.80 MiB after the 1% update.
Graphify deliberately does not manipulate SST/WAL files or call private
maintenance APIs. Peak RSS is reported but is non-blocking, as required.

The public ERPNext corpus was independently reproduced at commit
`ea5c648ab04a2b30c5c238f6cb299c4237ff1c1e`. Helix now matches the loaded v8
topology exactly at 25,443 nodes and 59,142 edges, but fresh build is 99.15s
versus 41.30s, cold open is 7.95s versus 0.33s, active storage is 10.34x v8,
and a representative steady query is 3.52s versus 0.05s. Raw measurements are
in [`report-erpnext-2026-07-19.json`](report-erpnext-2026-07-19.json).

The report's other four corpora, exact gold queries, harness scripts, and raw
results were not distributed or attached. The five-corpus gold-recall table
therefore remains outstanding; the public ERPNext and synthetic results are
not a substitute for those missing inputs.

## Conclusion

The integration is correct enough for a draft PR, but is not production-ready.
It must remain draft until the exact public package pair provides a passing
Windows wheel, all CI platforms pass without core skips, the engineers' real
corpora and gold queries pass, and the failed public-package performance and
disk-reclamation gates are resolved without hidden workarounds.
