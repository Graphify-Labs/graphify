#!/usr/bin/env python3
"""Non-CI microbenchmark: single-pass scoring vs legacy per-term rescoring.

Verifies the single-pass refactor eliminates the T+1 graph-scoring passes a
T-term query used to run, without changing the result. Reports median/min
latency for:

  * legacy  — one combined `_score_nodes(G, terms)` call PLUS one
              `_score_nodes(G, [token])` call per distinct query token
              (the old `_pick_seeds(terms=...)` per-term guarantee loop).
  * optimized — one `_score_query(G, terms, collect_per_term_seeds=True)`
                 call, with the per-token best computed inline in the same
                 traversal. `_pick_seeds` then consumes `best_seed_by_term`
                 directly — no rescoring.

Equality is asserted (ranked, best_seed_by_term, seeds) before timing. The
optimized path's traversal count is invariant in the number of query terms.

Run it manually; do NOT wire this into CI (wall-clock assertions are flaky):

    uv run python tests/bench_query_scoring.py \\
        --nodes 100000 --term-counts 3,10 --repeats 5

    uv run python tests/bench_query_scoring.py \\
        --graph graphify-out/graph.json \\
        --query "what calls extract" --query "symbol resolution" \\
        --repeats 10
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

import networkx as nx

from graphify.serve import (
    _get_trigram_index,
    _pick_seeds,
    _query_terms,
    _score_nodes,
    _score_query,
    _search_tokens,
)


SYLLABLES = [
    "foo", "bar", "baz", "get", "set", "run", "user", "name", "path",
    "build", "report", "extract", "router", "config", "service",
    "handler", "token", "auth", "rate", "limit", "widget", "model",
]

QUERIES_BY_TERM_COUNT: dict[int, list[str]] = {
    1: ["foo"],
    2: ["foo", "bar"],
    3: ["router", "service", "handler"],
    5: ["get", "user", "run", "name", "path"],
    10: ["extract", "build", "report", "router", "config",
         "service", "token", "rate", "limit", "widget"],
}


def _build_random_graph(n: int, *, seed: int) -> nx.DiGraph:
    """Reproducible broad-match DiGraph: short constructed labels + edge noise.

    Labels draw from a small syllable pool so tokens collide across nodes,
    forcing the trigram prefilter to be selective and exercising score ties
    on common tokens. Edge noise provides degree variance so the legacy
    tie-break (`max(tied, key=degree)`) is actually exercised against the
    new `(-singleton, -degree, label_len, nid)` key tuple."""
    rng = random.Random(seed)
    G: nx.DiGraph = nx.DiGraph()
    for i in range(n):
        label = "_".join(rng.sample(SYLLABLES, rng.randint(1, 3)))
        G.add_node(f"n{i}", label=label, source_file=f"src/{label[:8]}.py")
    for _ in range(n * 2):
        a, b = rng.randrange(n), rng.randrange(n)
        if a != b:
            G.add_edge(f"n{a}", f"n{b}", relation="calls", confidence="EXTRACTED")
    return G


def _load_real_graph(path: str) -> nx.Graph:
    """Light wrapper that just builds a NetworkX graph from a real
    `graphify-out/graph.json`, skipping the size cap and work-memory overlay
    that `serve._load_graph` enforces (the bench is read-only)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "links" not in data and "edges" in data:
        data = dict(data, links=data["edges"])
    data = {**data, "directed": True}
    try:
        return nx.readwrite.json_graph.node_link_graph(data, edges="links")
    except TypeError:
        return nx.readwrite.json_graph.node_link_graph(data)


def _legacy_score_and_pick(G, terms):
    """Recreates the pre-refactor flow: combined scoring plus one
    `_score_nodes([token])` call per distinct query token, with the legacy
    tie-break (`max(tied, key=degree)` over a (-score, label_len, nid)-sorted
    list) to derive `best_seed_by_term`. Returns the same triple as the
    optimized path so they can be compared for equality."""
    ranked = _score_nodes(G, terms)
    norm_terms = sorted({tok for t in terms for tok in _search_tokens(t)})
    best_seed_by_term: dict[str, str] = {}
    for term in norm_terms:
        term_scored = _score_nodes(G, [term])
        if not term_scored:
            continue
        best_score = term_scored[0][0]
        tied = [nid for s, nid in term_scored if s == best_score]
        best_nid = max(tied, key=lambda n: G.degree(n)) if len(tied) > 1 else term_scored[0][1]
        best_seed_by_term[term] = best_nid
    seeds = _pick_seeds(ranked, G=G, best_seed_by_term=best_seed_by_term)
    return ranked, best_seed_by_term, seeds


def _optimized_score_and_pick(G, terms):
    qs = _score_query(G, terms, collect_per_term_seeds=True)
    seeds = _pick_seeds(qs.ranked, G=G, best_seed_by_term=qs.best_seed_by_term)
    return qs.ranked, qs.best_seed_by_term, seeds


def _warm_caches(G, terms):
    """Pre-populate the trigram index and IDF cache so the first timed
    iteration doesn't pay the amortized build cost on either path. Both
    legacy and optimized share these caches via the graph object, so warming
    once is fair to both."""
    _get_trigram_index(G)
    # Touch the idf cache for the combined terms and every per-token singleton,
    # matching exactly the calls the legacy path will make.
    _score_nodes(G, terms)
    for term in {tok for t in terms for tok in _search_tokens(t)}:
        _score_nodes(G, [term])


def _bench(fn, *, repeats: int) -> list[float]:
    # One uncounted warm-up — `_warm_caches` already populated caches, but
    # this also amortizes any per-call code-path setup unique to `fn`.
    fn()
    times: list[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return times


def _verify_equality(G, terms) -> tuple[int, int]:
    leg_rank, leg_best, leg_seeds = _legacy_score_and_pick(G, terms)
    opt_rank, opt_best, opt_seeds = _optimized_score_and_pick(G, terms)
    assert leg_rank == opt_rank, (
        f"ranked diverged for terms={terms}: legacy[:5]={leg_rank[:5]} opt[:5]={opt_rank[:5]}"
    )
    assert leg_best == opt_best, (
        f"best_seed_by_term diverged for terms={terms}: legacy={leg_best} opt={opt_best}"
    )
    assert leg_seeds == opt_seeds, (
        f"seeds diverged for terms={terms}: legacy={leg_seeds} opt={opt_seeds}"
    )
    return len(leg_rank), len(leg_seeds)


def _row(label: str, n_nodes: int, n_terms: int, times: list[float],
         traversal_count: int, n_ranked: int, n_seeds: int) -> str:
    med = statistics.median(times) * 1000
    mn = min(times) * 1000
    return (f"{label:<10} | n={n_nodes:<7} | terms={n_terms:<3} | "
            f"median={med:7.2f}ms | min={mn:7.2f}ms | "
            f"passes={traversal_count:<3} | ranked={n_ranked:<6} seeds={n_seeds}")


def _legacy_traversal_count(terms) -> int:
    # 1 combined pass + one per-token singleton pass.
    return 1 + len({tok for t in terms for tok in _search_tokens(t)})


def _run_scenario(G, terms, *, repeats: int) -> tuple[float, float]:
    _warm_caches(G, terms)
    n_ranked, n_seeds = _verify_equality(G, terms)

    legacy_times = _bench(lambda: _legacy_score_and_pick(G, terms), repeats=repeats)
    opt_times = _bench(lambda: _optimized_score_and_pick(G, terms), repeats=repeats)

    n_nodes = G.number_of_nodes()
    n_terms = len(set(tok for t in terms for tok in _search_tokens(t)))
    print(_row("legacy", n_nodes, n_terms, legacy_times,
               _legacy_traversal_count(terms), n_ranked, n_seeds))
    print(_row("optimized", n_nodes, n_terms, opt_times,
               1, n_ranked, n_seeds))

    med_legacy = statistics.median(legacy_times)
    med_opt = statistics.median(opt_times)
    speedup = med_legacy / med_opt if med_opt > 0 else float("inf")
    print(f"speedup   | median: {speedup:.2f}x | "
          f"min: {min(legacy_times) / min(opt_times):.2f}x")
    return med_legacy, med_opt


def _resolve_scenarios(args) -> list[list[str]]:
    if args.graph:
        # Real-graph mode: each --query is a natural-language sentence, tokenized
        # using the same helper the production path uses.
        sentences = args.query or ["what calls extract"]
        scenarios = [_query_terms(s) for s in sentences]
        # Dedupe identical token sets (multiple --query args may tokenize the same).
        seen: list[list[str]] = []
        for q in scenarios:
            if q not in seen:
                seen.append(q)
        return seen
    term_counts = [int(s.strip()) for s in args.term_counts.split(",") if s.strip()]
    scenarios: list[list[str]] = []
    for tc in term_counts:
        if tc in QUERIES_BY_TERM_COUNT:
            scenarios.append(QUERIES_BY_TERM_COUNT[tc])
        elif tc > 0:
            scenarios.append([SYLLABLES[i % len(SYLLABLES)] for i in range(tc)])
    return scenarios


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Microbenchmark single-pass query scoring vs legacy per-term rescoring.",
    )
    p.add_argument("--nodes", type=int, default=100_000,
                   help="node count for the synthetic benchmark graph (default: 100000)")
    p.add_argument("--seed", type=int, default=20260714, help="RNG seed for the synthetic graph")
    p.add_argument("--term-counts", default="3,10",
                   help="comma-separated list of term counts to benchmark (synthetic mode)")
    p.add_argument("--repeats", type=int, default=5,
                   help="timed iterations per scenario (after one warm-up)")
    p.add_argument("--graph", default=None,
                   help="optional path to a real graphify-out/graph.json; overrides --nodes")
    p.add_argument("--query", action="append", default=None,
                   help="natural-language query sentence (real-graph mode; repeat for multiple)")
    args = p.parse_args(argv)

    if args.graph:
        print(f"loading real graph: {args.graph} ...", file=sys.stderr)
        t0 = time.perf_counter()
        G = _load_real_graph(args.graph)
        print(f"  loaded in {time.perf_counter() - t0:.2f}s", file=sys.stderr)
    else:
        print(f"building synthetic graph: n={args.nodes} seed={args.seed} ...",
              file=sys.stderr)
        t0 = time.perf_counter()
        G = _build_random_graph(args.nodes, seed=args.seed)
        print(f"  built in {time.perf_counter() - t0:.2f}s", file=sys.stderr)

    print()
    print(f"graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    scenarios = _resolve_scenarios(args)
    print(f"scenarios: {len(scenarios)} | repeats per scenario: {args.repeats}")
    print("-" * 110)

    summaries = []
    for terms in scenarios:
        print()
        med_legacy, med_opt = _run_scenario(G, terms, repeats=args.repeats)
        summaries.append((terms, med_legacy, med_opt))

    print()
    print("-" * 110)
    print("summary:")
    for terms, med_legacy, med_opt in summaries:
        speedup = med_legacy / med_opt if med_opt > 0 else float("inf")
        print(f"  terms={len(set(tok for t in terms for tok in _search_tokens(t))):>3} | "
              f"median legacy={med_legacy*1000:>8.2f}ms | "
              f"median optimized={med_opt*1000:>8.2f}ms | "
              f"speedup={speedup:>5.2f}x")
    return 0


if __name__ == "__main__":
    sys.exit(main())