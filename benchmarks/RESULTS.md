# Helix vs NetworkX benchmark

Run on Python 3.12.13 and macOS arm64 with the matching public
`helix-db==0.2.0b3` / `helix-db-embedded==0.2.0b3` pair and NetworkX 3.6.1.
NetworkX was installed only in the isolated benchmark environment. Both
backends use the same deterministic topology and sampled betweenness uses 100
sources with seed 42. Peak RSS is reported but is not a release gate.

Lower is better. Exact samples and every acceptance check are retained in
[`helix-vs-networkx.json`](helix-vs-networkx.json).

| Graph | Backend | Ingest | 1% update | Cold reopen | Hot open | 20 neighbors | BFS d=4 | 5 paths |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 5k / 15k | NetworkX | 0.076s | 0.058s | 0.027s | n/a | 0.005ms | 1.97ms | 0.14ms |
| 5k / 15k | Helix | 10.135s | 13.607s | 1.457s | 7.83ms | 1.62ms | 27.40ms | 1.45ms |
| 20k / 60k | NetworkX | 0.378s | 0.254s | 0.152s | n/a | 0.005ms | 1.11ms | 0.14ms |
| 20k / 60k | Helix | 40.671s | 63.572s | 6.454s | 10.02ms | 1.60ms | 12.17ms | 4.27ms |

| Graph | Backend | Community | Node BTW | Edge BTW | GraphML export | Peak ingest RSS |
|---|---|---:|---:|---:|---:|---:|
| 5k / 15k | NetworkX | 1.300s Louvain | 0.854s | 1.100s | 0.226s | 24.3 MiB |
| 5k / 15k | Helix | 0.121s Leiden | 0.121s | 0.394s | 0.747s | 343.3 MiB |
| 20k / 60k | NetworkX | 13.141s Louvain | 4.988s | 6.920s | 0.683s | 97.5 MiB |
| 20k / 60k | Helix | 1.414s Leiden | 0.612s | 1.853s | 3.246s | 993.5 MiB |

| Graph | NetworkX JSON | Active Helix store | Helix after default-retention update | Eight concurrent cold reopens |
|---|---:|---:|---:|---:|
| 5k / 15k | 1.37 MiB | 35.35 MiB | 73.69 MiB | 7.14s |
| 20k / 60k | 5.58 MiB | 143.71 MiB | 299.32 MiB | 31.24s |

## Gate result

This candidate **does not pass the release gates** and the PR must remain
draft. Absolute hot-operation limits pass, and at 20k/60k native weighted
Leiden, sampled node centrality, and sampled edge centrality are respectively
9.30x, 8.15x, and 3.73x faster than the NetworkX comparator. Build, 1% update,
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

The behavioral parity result in [`parity-networkx.json`](parity-networkx.json)
passes directed path, BFS, DFS, exact node and edge betweenness, Louvain on a
golden graph, layout, relabeling, subgraph, and conversion checks.

Reproduce without Homebrew:

```bash
python3.12 -m venv /tmp/graphify-networkx-benchmark
/tmp/graphify-networkx-benchmark/bin/python -m pip install -e . \
  -r benchmarks/requirements-networkx.txt
PYTHONPATH=. /tmp/graphify-networkx-benchmark/bin/python benchmarks/parity_networkx.py
PYTHONPATH=. /tmp/graphify-networkx-benchmark/bin/python \
  benchmarks/helix_vs_networkx.py --check-gates
```
