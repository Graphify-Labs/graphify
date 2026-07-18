# Helix vs NetworkX benchmark

Run on Python 3.12.13 and macOS arm64 with pinned Helix `0.2.0b1` and
NetworkX 3.6.1. NetworkX was installed only in the isolated benchmark
environment. Both backends use the same deterministic topology. Betweenness
uses 100 sampled sources and seed 42 for both node and edge scores.

Lower is better. Query, traversal, shortest-path, and community figures are
medians (5 runs for hot operations, 3 for community detection); centrality,
incremental update, export, and durable ingest are one expensive run. Exact
samples, run counts, RSS, disk, and acceptance checks are retained in
[`helix-vs-networkx.json`](helix-vs-networkx.json).

| Graph | Backend | Ingest | 1% update | Cold reopen | Hot open | 20 neighbors | BFS d=4 | 5 paths |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 5k / 15k | NetworkX | 0.033s | 0.005s | 0.004s | n/a | 0.004ms | 1.53ms | 0.11ms |
| 5k / 15k | Helix | 10.235s | 12.396s | 7.903s | 6.73ms | 1.14ms | 21.47ms | 1.11ms |
| 20k / 60k | NetworkX | 0.221s | 0.023s | 0.020s | n/a | 0.003ms | 0.72ms | 0.10ms |
| 20k / 60k | Helix | 67.224s | 82.233s | 33.462s | 8.12ms | 1.10ms | 9.18ms | 3.64ms |

| Graph | Backend | Community | Node BTW | Edge BTW | GraphML export | Peak ingest RSS |
|---|---|---:|---:|---:|---:|---:|
| 5k / 15k | NetworkX | 1.160s Louvain | 0.807s | 1.014s | 0.121s | 10.5 MiB |
| 5k / 15k | Helix | 0.096s Leiden | 0.098s | 0.304s | 0.594s | 384.4 MiB |
| 20k / 60k | NetworkX | 11.867s Louvain | 4.834s | 6.679s | 0.533s | 39.8 MiB |
| 20k / 60k | Helix | 1.130s Leiden | 0.474s | 1.406s | 2.621s | 1,158.4 MiB |

| Graph | Active Helix generation | Active + rollback | Eight concurrent cold reopens |
|---|---:|---:|---:|
| 5k / 15k | 35.90 MiB | 72.31 MiB | 104.48s |
| 20k / 60k | 148.00 MiB | 296.85 MiB | 416.96s |

All published acceptance gates passed. At 20k/60k, Helix weighted Leiden was
10.5x faster than NetworkX Louvain, sampled node betweenness was 10.2x faster,
and sampled edge betweenness was 4.8x faster. The 200 MB storage gate applies
to the active generation immediately after ingest. The raw results separately
retain the expected footprint after the 1% update creates a rollback generation.

NetworkX remained much faster and smaller for construction, persistence, cold
load, and small hot adjacency operations. Graphify avoids repeated cold opens
by retaining a native immutable snapshot for a long-running reader's lifetime;
no compatibility graph, intermediate JSON graph, or alternate query path is
used.

The behavioral parity result in [`parity-networkx.json`](parity-networkx.json)
passes directed path, BFS, DFS, exact node and edge betweenness, Louvain on a
golden graph, layout, subgraph, relabel, and conversion checks. Graphify's main
suite separately covers all four graph kinds, typed IDs, keyed multiedges,
self-loops, weighted Leiden, cycles, composition, exports, and persistence.

Reproduce in an isolated environment:

```bash
python -m venv /tmp/graphify-networkx-benchmark
/tmp/graphify-networkx-benchmark/bin/pip install -e . \
  -r benchmarks/requirements-networkx.txt
PYTHONPATH=. /tmp/graphify-networkx-benchmark/bin/python benchmarks/parity_networkx.py
PYTHONPATH=. /tmp/graphify-networkx-benchmark/bin/python benchmarks/helix_vs_networkx.py --check-gates
```
