# Release qualification: Helix `0.2.0b1`

Graphify is pinned to `helix-db==0.2.0b1` and
`helix-db-embedded==0.2.0b1`. It rejects incompatible SDK versions, missing
native payloads, malformed store paths, and unavailable required native APIs.

## Graphify acceptance

- Complete macOS arm64 / Python 3.12 suite: **2,757 passed, 30 skipped**.
- CI matrix: Linux Python 3.10, Linux Python 3.12, and macOS Python 3.12.
- All four graph kinds, typed IDs, keyed multiedges, self-loops, hyperedges,
  atomic activation, retained rollback, corruption, writer exclusion,
  concurrent readers, generation hot reload, and read-only enforcement: passed.
- Incremental update and deletion, extraction cache, analysis, learning state,
  clustering, affected/PR analysis, global aggregation, hooks, watch, exports,
  MCP stdio, and MCP Streamable HTTP: passed.
- Generated skill check (134 artifacts), host coverage audit, schema singleton,
  monolith contract, and always-on contract: passed.
- Ruff, scoped Pyright for the native integration surface, Bandit medium/high,
  pip-audit strict, source compilation, package build, and `git diff --check`:
  passed.
- Wheel installation in a clean Python 3.12 environment: passed. The installed
  production dependency set contains neither NetworkX nor graspologic.
- Installed-wheel CLI flow: build native store, query, and shortest path: passed.

Production source contains no NetworkX/graspologic imports or compatibility
graph. Legacy JSON graph files are never migrated, read, modified, or deleted;
the watch path emits one obsolete-format warning and requires a source rebuild.
Obsidian's `.obsidian/graph.json` remains solely because that filename belongs
to Obsidian's presentation configuration, not Graphify storage.

## Benchmarks

The isolated benchmark comparator is the only environment that installs
NetworkX. The deterministic parity corpus and full raw measurements are in
[`parity-networkx.json`](parity-networkx.json) and
[`helix-vs-networkx.json`](helix-vs-networkx.json); reproduction commands and
interpreted results are in [`RESULTS.md`](RESULTS.md).

Every published gate passed:

| Graph | Ingest | Cold open | Peak RSS | Active store | Slowest gated hot op |
|---|---:|---:|---:|---:|---:|
| 5k / 15k | 9.28s | 8.16s | 360.0 MiB | 35.75 MiB | 20.24ms |
| 20k / 60k | 62.56s | 34.55s | 1,293.8 MiB | 142.48 MiB | 9.01ms |

At 20k/60k, weighted Leiden, sampled node centrality, and sampled edge
centrality were respectively **9.7x**, **9.9x**, and **5.1x** faster than the
NetworkX baseline. The raw results also report incremental update, GraphML
export, concurrent cold readers, and the 285.45 MiB active-plus-rollback
footprint; the published 200 MB store gate applies to the active generation
immediately after ingest.

Windows is temporarily unsupported by the pinned embedded runtime. Supported
production targets are macOS universal and Linux x86_64/aarch64.
