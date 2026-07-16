# Bug Report: neug Weighted Leiden Produces Degenerate Community Splits

## Summary

When the `weight` parameter is passed to `CALL leiden(...)`, the algorithm produces severely degenerate results on real-world graphs:

- **312 communities** (weighted) vs **91 communities** (unweighted) on the same graph
- **0/20** highest-weight edges end up in the same community (weighted) vs **13/20** (unweighted)
- Lowering `resolution` to 0.001 does **not** help — still 313 communities
- Internal edge ratio drops from **60.6%** (unweighted) to **5.8%** (weighted)

The weighted Leiden appears to **split high-weight edges across communities** — the opposite of expected behavior.

## Environment

- neug version: 0.1.3 (installed from `.venv-arm64`)
- Python: 3.10
- OS: macOS 26.3.1 (arm64)

## Test Data

Real-world code knowledge graph from the neug codebase itself:

- **1332 file nodes**, **2982 edges**
- Edge weights range from 1 to 132 (mean ~2.9)
- 49.2% of edges have weight=1
- Edges are stored as directed (from_file → to_file) in a TEMP_FILE_EDGE rel table
- Weights are stored as **DOUBLE** (critical: see Related Issue #1)

Data files: `file_cluster_nodes.csv` and `file_cluster_edges.csv`
(obtained via `GRAPHIFY_KEEP_TEMP=./tmp_csvs`).

## Reproduction

```bash
# Option 1: Use real data (requires graphify temp CSVs)
python repro_weighted_leiden.py --csv-dir /path/to/tmp_csvs

# Option 2: Use synthetic data (no external files needed)
python repro_weighted_leiden.py
```

### Expected vs Actual

| Metric | Unweighted (res=1.0) | Weighted (res=1.0) | Weighted (res=0.001) |
|--------|---------------------|--------------------|--------------------|
| Communities | 91 | 312 | 313 |
| Internal edges | 60.6% | 5.8% | 6.8% |
| Top-20 high-weight edges in same community | 13/20 | **0/20** | **0/20** |
| Zero-cohesion communities | 35 | 123 | 126 |

### Key Observations

1. **Weight splits strong connections**: The highest-weight edge `schema.cc → schema.h` (weight=132) is split into different communities in weighted mode, but kept together in unweighted mode.

2. **Resolution has no effect**: `res=1.0` → 312 communities, `res=0.001` → 313 communities. The resolution parameter should control community granularity, but it has almost no impact when weights are enabled.

3. **Small synthetic graphs work fine**: On a 10-node graph with 2 clear communities, both weighted and unweighted produce identical correct results. The bug only manifests on larger, sparser graphs.

4. **Internal edge ratio collapses**: Only 5.8% of edges are internal to communities (weighted) vs 60.6% (unweighted). This means the weighted Leiden is actively avoiding placing connected nodes together.

## Hypothesis

The weight parameter may be used inversely in the modularity calculation — higher weight could be **penalizing** community merges rather than encouraging them. Alternatively, the weighted modularity formula may have a scaling issue where large total weight `m` suppresses the modularity gain `ΔQ` to near-zero, preventing any merges.

## Steps in the Algorithm

```cypher
-- 1. Create temp tables
COPY TEMP TempFile FROM 'nodes.csv' (header=true, delim=',')
COPY TEMP TEMP_FILE_EDGE FROM 'edges.csv' (header=true, delim=',', from='TempFile', to='TempFile')

-- 2. Project graph
CALL project_graph('g', ['TempFile'], {'[TempFile, TEMP_FILE_EDGE, TempFile]': ''})

-- 3. Run leiden (weighted — BUGGY)
CALL leiden('g', {concurrency: 1, resolution: 1.0, weight: 'weight'})
YIELD node, community RETURN node.id, community

-- 3b. Run leiden (unweighted — works correctly)
CALL leiden('g', {concurrency: 1, resolution: 1.0})
YIELD node, community RETURN node.id, community
```

## Related Issues

### Issue #1: Weight type must be DOUBLE (not INT64)

If edge weights are stored as INT64 (e.g., CSV values `1`, `2`, `3` without decimal point), `COPY TEMP` infers INT64 type, and the weighted Leiden produces **fully degenerate** results — every node gets its own community (1332 communities for 1332 nodes), regardless of resolution.

Workaround: write weights as float (`1.0`, `2.0`, `3.0`) in the CSV to ensure DOUBLE type inference.

This may be related to the main bug — if the weight type handling has issues, the weighted modularity calculation could be broken for both INT64 and DOUBLE (just differently).

## Impact

This bug prevents the use of weighted Leiden for file-level code clustering in graphify. We have disabled weights as a workaround, but weighted clustering would provide better results if the bug is fixed — file pairs that share many symbols (high weight) should be prioritized for community membership.
