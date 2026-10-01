#!/usr/bin/env python3
"""Dedup benchmark: BEFORE changes

Simulates pre-optimization behavior by stripping source_location from all nodes
so every high-entropy node enters the MinHash/LSH pipeline regardless of origin.

Run standalone for profiling:
    uv run python tests/before.py
    uv run pyinstrument tests/before.py
    uv run pyinstrument tests/before.py --n-ast 200000 --n-semantic 10000
"""
from __future__ import annotations

import argparse
import contextlib
import io
import random
import string
import sys
import time
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from graphify.dedup import deduplicate_entities

_SEED = 42


def make_dataset(
    n_ast: int,
    n_semantic: int,
    near_dup_pct: float = 0.08,
) -> tuple[list[dict], list[dict]]:
    """Return (nodes, edges) with a mix of AST nodes (source_location) and semantic nodes."""
    rng = random.Random(_SEED)
    nodes: list[dict] = []
    files = [f"src/module_{i}.ts" for i in range(100)]

    for i in range(n_ast):
        label = _rand_label(rng)
        file = rng.choice(files)
        nodes.append({
            "id": f"ast_{i}",
            "label": label,
            "kind": rng.choice(["function", "class", "variable", "type"]),
            "source_file": file,
            "source_location": f"{file}:{rng.randint(1, 800)}:{rng.randint(0, 80)}",
        })

    sem_labels = [_rand_label(rng) for _ in range(n_semantic)]
    for i, label in enumerate(sem_labels):
        nodes.append({"id": f"sem_{i}", "label": label, "kind": "concept"})

    n_near_dups = max(1, int(n_semantic * near_dup_pct))
    alpha = string.ascii_lowercase
    for i in range(n_near_dups):
        base = sem_labels[i % len(sem_labels)]
        if len(base) < 2:
            continue
        pos = rng.randint(0, len(base) - 1)
        replacement = rng.choice(alpha.replace(base[pos], "") or alpha)
        mutated = base[:pos] + replacement + base[pos + 1:]
        nodes.append({"id": f"nd_{i}", "label": mutated, "kind": "concept"})

    ids = [n["id"] for n in nodes]
    edges: list[dict] = []
    for _ in range(len(nodes) * 2):
        src, tgt = rng.sample(ids, 2)
        edges.append({"source": src, "target": tgt, "relation": "depends_on"})

    return nodes, edges


def _rand_label(rng: random.Random) -> str:
    n_parts = rng.randint(1, 3)
    parts = ["".join(rng.choices(string.ascii_lowercase, k=rng.randint(4, 10))) for _ in range(n_parts)]
    return rng.choice(["", "_"]).join(parts)


def _strip_source_location(nodes: list[dict]) -> list[dict]:
    return [{k: v for k, v in n.items() if k != "source_location"} if "source_location" in n else n for n in nodes]


def _run_once(nodes: list[dict], edges: list[dict]) -> float:
    t0 = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        deduplicate_entities(list(nodes), list(edges), communities={})
    return time.perf_counter() - t0


def run_bench(nodes: list[dict], edges: list[dict], runs: int = 2) -> list[float]:
    """Strip source_location and time deduplicate_entities. Returns per-run elapsed times."""
    stripped = _strip_source_location(nodes)
    elapsed = _run_once(stripped, edges)
    print(f"  before  dry : {elapsed:.3f}s  (discarded)", flush=True)
    times = []
    for i in range(runs):
        elapsed = _run_once(stripped, edges)
        times.append(elapsed)
        print(f"  before  run {i + 1}/{runs}: {elapsed:.3f}s", flush=True)
    return times


def _print_stats(times: list[float]) -> None:
    s = sorted(times)
    median = s[len(s) // 2]
    print(f"  min: {s[0]:.3f}s   median: {median:.3f}s   mean: {sum(s)/len(s):.3f}s")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n-ast",        type=int,   default=100_000)
    ap.add_argument("--n-semantic",   type=int,   default=5_000)
    ap.add_argument("--runs",         type=int,   default=2)
    ap.add_argument("--near-dup-pct", type=float, default=0.08)
    args = ap.parse_args()

    nodes, edges = make_dataset(args.n_ast, args.n_semantic, args.near_dup_pct)
    print(f"BEFORE  ({args.n_ast:,} AST + {args.n_semantic:,} semantic, {args.runs} runs)")
    times = run_bench(nodes, edges, args.runs)
    _print_stats(times)


if __name__ == "__main__":
    main()
