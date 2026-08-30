#!/usr/bin/env python3
"""Benchmark: before vs after changes.

Imports before.py and after.py, generates a shared dataset, runs both, and
prints a side-by-side comparison.  Run before.py / after.py standalone to
attach a profiler to each scenario individually.

Usage:
    uv run python tests/bench_dedup.py
    uv run python tests/bench_dedup.py --n-ast 200000 --n-semantic 10000 --runs 3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_tests_dir = Path(__file__).resolve().parent
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))

_project_root = _tests_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import before as _before
import after as _after
from graphify.dedup import _ENTROPY_THRESHOLD, _entropy, _norm


def _count_candidates(nodes: list[dict]) -> int:
    seen: set[str] = set()
    count = 0
    for n in nodes:
        key = _norm(n.get("label", n.get("id", "")))
        if key and key not in seen:
            seen.add(key)
            if _entropy(n.get("label", "")) >= _ENTROPY_THRESHOLD and not n.get("source_location"):
                count += 1
    return count


def _stats(times: list[float]) -> dict[str, float]:
    s = sorted(times)
    return {"min": s[0], "median": s[len(s) // 2], "mean": sum(s) / len(s)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n-ast",        type=int,   default=100_000)
    ap.add_argument("--n-semantic",   type=int,   default=5_000)
    ap.add_argument("--runs",         type=int,   default=2)
    ap.add_argument("--near-dup-pct", type=float, default=0.08)
    args = ap.parse_args()

    print("=== bench_dedup: MinHash/LSH skip optimization ===\n")
    print(
        f"Generating dataset: {args.n_ast:,} AST nodes "
        f"+ {args.n_semantic:,} semantic nodes "
        f"(~{int(args.n_semantic * args.near_dup_pct)} near-dups)...",
        flush=True,
    )

    # Both scripts use the same seed so the datasets are identical.
    nodes, edges = _before.make_dataset(args.n_ast, args.n_semantic, args.near_dup_pct)

    cands_before = _count_candidates(_before._strip_source_location(nodes))
    cands_after  = _count_candidates(nodes)

    print(f"  Total: {len(nodes):,} nodes, {len(edges):,} edges")
    print(f"  MinHash candidates before : {cands_before:,}  (all high-entropy nodes)")
    print(f"  MinHash candidates after  : {cands_after:,}  (semantic-only)")
    print()

    # Warm the _norm lru_cache with all labels before timing so neither scenario
    # pays a cold-cache penalty.
    for n in nodes:
        _norm(n.get("label", ""))

    print(f"Running 1 dry run + {args.runs} timed iterations per scenario...\n")

    before_times = _before.run_bench(nodes, edges, args.runs)
    print()
    after_times  = _after.run_bench(nodes, edges, args.runs)
    print()

    bs  = _stats(before_times)
    as_ = _stats(after_times)
    speedup  = bs["median"] / as_["median"] if as_["median"] > 0 else float("inf")
    saved_ms = (bs["median"] - as_["median"]) * 1000
    reduction = 100 * (1 - cands_after / cands_before) if cands_before else 0.0

    print("=== Results ===")
    print(f"  Before  --  min: {bs['min']:.3f}s   median: {bs['median']:.3f}s   mean: {bs['mean']:.3f}s")
    print(f"  After   --  min: {as_['min']:.3f}s   median: {as_['median']:.3f}s   mean: {as_['mean']:.3f}s")
    print()
    print(f"  Candidate reduction : {cands_before:,} -> {cands_after:,}  ({reduction:.1f}% fewer)")
    print(f"  Speedup             : {speedup:.2f}x")
    print(f"  Saved               : {saved_ms:.0f}ms per run (median)")


if __name__ == "__main__":
    main()
