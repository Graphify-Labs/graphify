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
| 5k / 15k | NetworkX | 0.043s | 0.005s | 0.004s | n/a | 0.003ms | 1.48ms | 0.10ms |
| 5k / 15k | Helix | 9.280s | 12.329s | 8.156s | 6.08ms | 1.16ms | 20.24ms | 1.13ms |
| 20k / 60k | NetworkX | 0.160s | 0.029s | 0.019s | n/a | 0.004ms | 0.80ms | 0.11ms |
| 20k / 60k | Helix | 62.556s | 78.470s | 34.546s | 7.15ms | 1.10ms | 9.01ms | 3.22ms |

| Graph | Backend | Community | Node BTW | Edge BTW | GraphML export | Peak ingest RSS |
|---|---|---:|---:|---:|---:|---:|
| 5k / 15k | NetworkX | 1.011s Louvain | 0.752s | 0.985s | 0.124s | 10.6 MiB |
| 5k / 15k | Helix | 0.098s Leiden | 0.094s | 0.310s | 0.605s | 360.0 MiB |
| 20k / 60k | NetworkX | 11.129s Louvain | 4.775s | 7.557s | 0.587s | 39.2 MiB |
| 20k / 60k | Helix | 1.149s Leiden | 0.483s | 1.487s | 2.700s | 1,293.8 MiB |

| Graph | Active Helix generation | Active + rollback | Eight concurrent cold reopens |
|---|---:|---:|---:|
| 5k / 15k | 35.75 MiB | 72.25 MiB | 109.59s |
| 20k / 60k | 142.48 MiB | 285.45 MiB | 431.70s |

All published acceptance gates passed. At 20k/60k, Helix weighted Leiden was
9.7x faster than NetworkX Louvain, sampled node betweenness was 9.9x faster,
and sampled edge betweenness was 5.1x faster. The 200 MB storage gate applies
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
