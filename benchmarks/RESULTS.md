# Helix vs NetworkX benchmark

Run on Python 3.12.13 and macOS arm64 with the matching public
`helix-db==0.2.0b3` / `helix-db-embedded==0.2.0b3` pair and NetworkX 3.6.1.
NetworkX was installed only in the isolated benchmark environment. Both
backends use the same deterministic topology and sampled betweenness uses 100
sources with seed 42. Peak RSS is reported but is not a release gate.

Lower is better. Exact samples and every acceptance check are retained in
[`helix-vs-networkx-2026-07-19.json`](helix-vs-networkx-2026-07-19.json).

| Graph | Backend | Ingest | 1% update | Cold reopen | Hot open | 20 neighbors | BFS d=4 | 5 paths |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 5k / 15k | NetworkX | 0.076s | 0.045s | 0.026s | n/a | 0.004ms | 1.39ms | 0.11ms |
| 5k / 15k | Helix | 8.167s | 10.730s | 1.073s | 5.48ms | 1.15ms | 20.57ms | 1.11ms |
| 20k / 60k | NetworkX | 0.304s | 0.192s | 0.124s | n/a | 0.003ms | 0.93ms | 0.11ms |
| 20k / 60k | Helix | 32.554s | 49.525s | 4.875s | 7.15ms | 1.10ms | 8.93ms | 3.25ms |

| Graph | Backend | Community | Node BTW | Edge BTW | GraphML export | Peak ingest RSS |
|---|---|---:|---:|---:|---:|---:|
| 5k / 15k | NetworkX | 0.996s Louvain | 0.665s | 0.826s | 0.512s | 24.3 MiB |
| 5k / 15k | Helix | 0.095s Leiden | 0.093s | 0.301s | 0.582s | 232.3 MiB |
| 20k / 60k | NetworkX | 9.915s Louvain | 4.096s | 5.731s | 0.539s | 97.4 MiB |
| 20k / 60k | Helix | 1.015s Leiden | 0.412s | 1.386s | 2.553s | 647.1 MiB |

| Graph | NetworkX JSON | Active Helix store | Helix after default-retention update | Eight concurrent cold reopens |
|---|---:|---:|---:|---:|
| 5k / 15k | 1.37 MiB | 35.12 MiB | 73.24 MiB | 4.03s |
| 20k / 60k | 5.58 MiB | 143.45 MiB | 298.80 MiB | 16.80s |

## Gate result

This candidate **does not pass the release gates** and the PR must remain
draft. Absolute hot-operation limits pass, and at 20k/60k native weighted
Leiden, sampled node centrality, and sampled edge centrality are respectively
9.76x, 9.93x, and 4.13x faster than the NetworkX comparator. Build, 1% update,
cold-open, storage, and relative warm-operation gates fail.

Public b3 substantially improves the earlier public b1 engine result, but it
still does not reach the required 2x build/update or 3s cold-open limits.
Increasing Graphify's public write-batch size from 1,000 to 5,000 records did
not improve the remaining ingest time.

Default retention logically deletes the inactive generation through public
Helix operations, but the embedded store does not reclaim its physical space;
the post-update store more than doubles. Graphify does not compact SST/WAL
files or call private maintenance APIs, so disk reclamation remains a public
package limitation.

The behavioral parity result from the current candidate
passes directed path, BFS, DFS, exact node and edge betweenness, Louvain on a
golden graph, layout, relabeling, subgraph, and conversion checks.

## Public ERPNext report reproduction

The report-style public ERPNext run now has exact loaded-topology parity at
25,443 nodes and 59,142 edges. It still fails release qualification: fresh
build is 99.15s versus 41.30s, median cold open is 7.95s versus 0.33s, active
storage is 10.34x v8, and a representative steady query is 3.52s versus 0.05s.
The immediate unchanged-topology update passes at 46.65s versus 40.13s. See
[`report-erpnext-2026-07-19.json`](report-erpnext-2026-07-19.json) for commands,
versions, samples, and unavailable report inputs.

Reproduce without Homebrew:

```bash
python3.12 -m venv /tmp/graphify-networkx-benchmark
/tmp/graphify-networkx-benchmark/bin/python -m pip install -e . \
  -r benchmarks/requirements-networkx.txt
PYTHONPATH=. /tmp/graphify-networkx-benchmark/bin/python benchmarks/parity_networkx.py
PYTHONPATH=. /tmp/graphify-networkx-benchmark/bin/python \
  benchmarks/helix_vs_networkx.py \
  --out benchmarks/helix-vs-networkx-2026-07-19.json --check-gates
```
