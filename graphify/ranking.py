"""Relevance ranking of query subgraphs via Reciprocal Rank Fusion (RRF).

`graphify query` seeds a BFS/DFS from the best lexical matches and expands the
neighbourhood. The raw traversal result was then rendered in *degree* order, so
a broad question could surface hundreds of high-degree hubs ahead of the handful
of nodes that actually answer it. This module re-orders the traversal result by
a fused relevance score so the token budget spends itself on the nodes that
matter.

Several independent rankings vote on each node:

  * ``lexical``    - query-term match strength (from ``serve._score_nodes``)
  * ``proximity``  - graph distance from the seed nodes (closer answers first)
  * ``centrality`` - degree / hub-ness (a mild prior toward important nodes)
  * ``community``  - membership in a seed's community (topical cohesion)
  * ``semantic``   - optional local-embedding cosine similarity (opt-in feature)

Rankings are combined with Reciprocal Rank Fusion: a node at rank ``r`` in a
backend contributes ``1 / (k + r)``. RRF needs no per-backend weight tuning and
is robust to backends that score on wildly different scales (BM25 vs. cosine
vs. hop count). The structural backends (proximity / centrality / community) are
graphify's edge — a pure-retrieval tool can't compute them because it has no
typed graph.

Everything here is pure and deterministic: ties break on node id, so the same
graph + query always yields the same order.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

# Standard RRF damping constant (Cormack, Clarke & Buettcher, SIGIR 2009). Large
# k flattens the contribution curve so no single backend dominates on rank alone.
RRF_K = 60

# Backends are listed most-informative-first purely so --explain reads naturally.
_BACKEND_ORDER = ("lexical", "semantic", "proximity", "community", "centrality")

_FAR = 1_000_000  # proximity sentinel for nodes with no path back to a seed


@dataclass
class RankedNode:
    """A node's fused relevance and its per-backend breakdown (for --explain)."""

    node_id: str
    score: float = 0.0
    ranks: dict[str, int] = field(default_factory=dict)
    contributions: dict[str, float] = field(default_factory=dict)

    def explain(self) -> str:
        """One-line breakdown, backends sorted by their contribution."""
        parts = [
            f"{b}#{self.ranks[b]}(+{self.contributions[b]:.4f})"
            for b in sorted(self.contributions, key=lambda b: -self.contributions[b])
        ]
        return f"rank score={self.score:.4f} :: " + " ".join(parts)


def rrf_fuse(
    rankings: Mapping[str, Sequence[str]], k: int = RRF_K
) -> dict[str, RankedNode]:
    """Fuse named rankings into per-node RRF scores.

    ``rankings`` maps a backend name to an ordered list of node ids (best first).
    A node absent from a backend simply receives no contribution from it. The
    first (best) occurrence of a node within a backend wins, so a caller may pass
    a ranking with duplicates without double-counting.
    """
    out: dict[str, RankedNode] = {}
    for backend, ordered in rankings.items():
        for rank, nid in enumerate(ordered, start=1):
            rn = out.get(nid)
            if rn is None:
                rn = RankedNode(nid)
                out[nid] = rn
            if backend in rn.ranks:
                continue
            contrib = 1.0 / (k + rank)
            rn.ranks[backend] = rank
            rn.contributions[backend] = contrib
            rn.score += contrib
    return out


def _lexical_ranking(lexical_scores: Mapping[str, float], nodes: set[str]) -> list[str]:
    scored = [(s, n) for n, s in lexical_scores.items() if n in nodes and s > 0]
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [n for _, n in scored]


def _proximity_ranking(nodes: set[str], distances: Mapping[str, int]) -> list[str]:
    # Nodes with no known distance (never reached from a seed) sink to the back.
    return sorted(nodes, key=lambda n: (distances.get(n, _FAR), n))


def _centrality_ranking(nodes: set[str], degrees: Mapping[str, int]) -> list[str]:
    return sorted(nodes, key=lambda n: (-degrees.get(n, 0), n))


def _community_ranking(
    nodes: set[str],
    node_community: Mapping[str, object],
    seed_communities: set[object],
    degrees: Mapping[str, int],
) -> list[str]:
    in_comm = [n for n in nodes if node_community.get(n) in seed_communities]
    out_comm = [n for n in nodes if node_community.get(n) not in seed_communities]
    in_comm.sort(key=lambda n: (-degrees.get(n, 0), n))
    out_comm.sort(key=lambda n: (-degrees.get(n, 0), n))
    return in_comm + out_comm


def _semantic_ranking(semantic_scores: Mapping[str, float], nodes: set[str]) -> list[str]:
    scored = [(s, n) for n, s in semantic_scores.items() if n in nodes]
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [n for _, n in scored]


def rank_nodes(
    nodes: Iterable[str],
    seeds: Sequence[str],
    *,
    lexical_scores: Mapping[str, float] | None = None,
    distances: Mapping[str, int] | None = None,
    degrees: Mapping[str, int] | None = None,
    node_community: Mapping[str, object] | None = None,
    semantic_scores: Mapping[str, float] | None = None,
    k: int = RRF_K,
) -> list[RankedNode]:
    """Rank ``nodes`` by fused relevance, returning them best-first.

    ``seeds`` (the exact query matches the traversal started from) are always
    pinned to the top in seed order — they are the answer's anchor and must never
    be pushed below expanded neighbours. Every other node is ordered by its RRF
    score. Each returned ``RankedNode`` carries its per-backend breakdown so the
    caller can render ``--explain``.
    """
    node_set = set(nodes)
    degrees = degrees or {}
    lexical_scores = lexical_scores or {}
    distances = distances or {}
    node_community = node_community or {}

    seed_communities = {
        node_community.get(s)
        for s in seeds
        if node_community.get(s) is not None
    }

    rankings: dict[str, list[str]] = {
        "lexical": _lexical_ranking(lexical_scores, node_set),
        "proximity": _proximity_ranking(node_set, distances),
        "centrality": _centrality_ranking(node_set, degrees),
    }
    if seed_communities:
        rankings["community"] = _community_ranking(
            node_set, node_community, seed_communities, degrees
        )
    if semantic_scores:
        rankings["semantic"] = _semantic_ranking(semantic_scores, node_set)

    fused = rrf_fuse(rankings, k=k)

    seed_order = [s for s in seeds if s in node_set]
    seed_set = set(seed_order)
    rest = [n for n in node_set if n not in seed_set]
    rest.sort(key=lambda n: (-(fused[n].score if n in fused else 0.0), n))

    ordered_ids = seed_order + rest
    return [fused.get(n) or RankedNode(n) for n in ordered_ids]
