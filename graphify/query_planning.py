"""Deterministic query planning for bounded, relation-aware graph retrieval.

The planner deliberately stays independent of MCP and model providers. It maps
question wording to a small traversal profile, while the caller remains
responsible for symbol scoring, rendering, and any optional LLM synthesis.
"""
from __future__ import annotations

from collections.abc import Hashable, Iterator
from dataclasses import dataclass
import heapq
from itertools import chain
import re

import networkx as nx

from graphify.ontology import normalize_relation


def _canonical_relation(data: dict) -> str:
    """Normalize known aliases while preserving unknown names for diagnostics."""

    raw = str(data.get("relation", "")).strip().lower()
    return normalize_relation(raw) or raw


@dataclass(frozen=True)
class TraversalProfile:
    """Relations that are admissible for one query intent.

    ``relations=None`` is the compatibility/exploration profile and leaves the
    graph unchanged. Other profiles act as an ontology projection: structural
    relations cannot consume a runtime or data-flow evidence budget.
    """

    name: str
    relations: frozenset[str] | None
    llm_mode: str


@dataclass(frozen=True)
class LlmAdmission:
    """Advisory model-use decision derived only from retrieved evidence."""

    mode: str
    reason: str


def recommend_llm(
    profile: TraversalProfile,
    *,
    edge_count: int,
    uncertain_edges: int,
    unresolved_nodes: int,
    direct_lookup: bool,
    truncated: bool = False,
    unsupported_relations: int = 0,
) -> LlmAdmission:
    """Return ``none``, ``synthesize``, or ``reason`` without invoking a model."""

    # A bounded packet can be correct about every edge it contains while still
    # being incomplete. Never authorize a final answer when reachable evidence
    # was omitted; the caller should issue a narrower query instead.
    if truncated:
        return LlmAdmission("reason", "evidence budget reached; run a focused follow-up query")
    if unsupported_relations:
        return LlmAdmission(
            "reason",
            "ontology projection omitted an unsupported relation; run a focused follow-up query",
        )
    if edge_count == 0:
        return LlmAdmission("reason", "no connected evidence")
    if uncertain_edges or unresolved_nodes:
        return LlmAdmission("reason", "evidence contains unresolved or uncertain relationships")
    if direct_lookup:
        return LlmAdmission("none", "deterministic lookup is fully source-backed")
    if profile.llm_mode == "synthesize":
        return LlmAdmission("synthesize", "verified multi-step evidence needs prose synthesis")
    return LlmAdmission("reason", "open-ended exploration requires interpretation")


_RUNTIME_RELATIONS = frozenset({
    "calls",
    "indirect_call",
    "dispatches",
    "emits",
    "publishes",
    "enqueues",
    "dequeues",
    "handles",
    "subscribes",
    "consumes",
    "reads",
    "writes",
    "loads",
    "persists",
    "caches",
    "invalidates",
    "serializes",
    "deserializes",
    # Dynamic dispatch and weakly typed languages often retain a conservative
    # reference when a sound CALLS edge cannot be proven. Keep it as a costly
    # fallback so verified calls/data edges consume the budget first.
    "references",
    "uses",
    # These are bounded structural bridges from a queried type to executable
    # members. Broad file containment and imports remain intentionally absent.
    "defines",
    "method",
    "implements",
    "overrides",
})

RUNTIME_FLOW = TraversalProfile("runtime_flow", _RUNTIME_RELATIONS, "synthesize")
DOCUMENT = TraversalProfile(
    "document",
    frozenset({
        "contains",
        "references",
        "cites",
        "mentions",
        "documents",
        "explains",
        "rationale_for",
    }),
    "synthesize",
)
EXPLORE = TraversalProfile("explore", None, "reason")


_SAFE_STRUCTURAL_OMISSIONS = frozenset({
    "contains",
    "imports",
    "exports",
    "includes",
    "depends_on",
    "requires",
    "requires_env",
    "belongs_to",
    "declares",
    "extends",
    "inherits",
    "mixes_in",
})


def _incident_edge_data(
    graph: nx.Graph | nx.DiGraph | nx.MultiGraph | nx.MultiDiGraph,
    node: Hashable,
) -> Iterator[dict]:
    """Yield incident data without merging opposite arcs in a directed graph."""

    if isinstance(graph, nx.MultiDiGraph):
        for edge in chain(
            graph.out_edges(node, keys=True, data=True),
            graph.in_edges(node, keys=True, data=True),
        ):
            yield edge[-1]
        return
    if isinstance(graph, nx.DiGraph):
        for edge in chain(
            graph.out_edges(node, data=True),
            graph.in_edges(node, data=True),
        ):
            yield edge[-1]
        return
    edges = (
        graph.edges(node, keys=True, data=True)
        if isinstance(graph, nx.MultiGraph)
        else graph.edges(node, data=True)
    )
    for edge in edges:
        yield edge[-1]


def projection_gaps(
    G: nx.Graph,
    nodes: set[str],
    profile: TraversalProfile,
) -> list[str]:
    """Return omitted relation kinds that are not known structural noise.

    Profiles are intentionally small and language-agnostic. A newly added
    extractor may introduce a meaningful runtime relation before the ontology
    knows its name; surfacing it as a gap prevents the optimized projection
    from silently declaring a partial flow complete.
    """

    if profile.relations is None:
        return []
    unsupported: set[str] = set()
    for node in nodes:
        if node not in G:
            continue
        # Incoming arcs matter for completeness, but an undirected conversion
        # would merge reciprocal arcs and hide one of their relation kinds.
        for data in _incident_edge_data(G, node):
            relation = _canonical_relation(data)
            if (
                relation
                and relation not in profile.relations
                and relation not in _SAFE_STRUCTURAL_OMISSIONS
            ):
                unsupported.add(relation)
    return sorted(unsupported)


def plan_query(question: str) -> TraversalProfile:
    """Choose a conservative deterministic traversal profile.

    Only strong runtime wording selects the restricted projection. Ambiguous
    questions retain the historical exploration behavior rather than silently
    dropping potentially relevant relation kinds.
    """

    normalized = " ".join(re.findall(r"[a-z0-9]+", question.lower()))
    if any(term in normalized.split() for term in ("document", "docs", "manual", "page", "section")):
        return DOCUMENT
    runtime_phrase = any(
        phrase in normalized
        for phrase in ("end to end", "runtime flow", "execution flow", "call flow")
    )
    how_it_works = normalized.startswith("how ") and any(
        word in normalized.split()
        for word in ("work", "works", "working", "process", "processing", "generated")
    )
    return RUNTIME_FLOW if runtime_phrase or how_it_works else EXPLORE


def project_graph(G: nx.Graph, profile: TraversalProfile) -> nx.Graph:
    """Return a read-only unrestricted view or an isolated relation projection."""

    if profile.relations is None:
        # Explore queries need the full topology. A frozen O(1) view prevents
        # accidental structural writes without copying a potentially large graph.
        return nx.graphviews.generic_graph_view(G)
    projected = G.__class__()
    projected.graph.update(G.graph)
    projected.add_nodes_from(G.nodes(data=True))
    if isinstance(G, (nx.MultiGraph, nx.MultiDiGraph)):
        for source, target, key, data in G.edges(keys=True, data=True):
            relation = _canonical_relation(data)
            if relation in profile.relations:
                projected.add_edge(source, target, key=key, **{**data, "relation": relation})
    else:
        for source, target, data in G.edges(data=True):
            relation = _canonical_relation(data)
            if relation in profile.relations:
                projected.add_edge(source, target, **{**data, "relation": relation})
    return projected


_RELATION_COSTS = {
    "calls": 1.0,
    "dispatches": 1.0,
    "emits": 1.1,
    "publishes": 1.1,
    "enqueues": 1.1,
    "handles": 1.1,
    "consumes": 1.1,
    "reads": 1.2,
    "writes": 1.2,
    "loads": 1.2,
    "persists": 1.2,
    "caches": 1.2,
    "invalidates": 1.2,
    "indirect_call": 1.4,
    "defines": 2.5,
    "method": 2.5,
    "implements": 3.0,
    "overrides": 3.0,
    "references": 3.5,
    "uses": 3.5,
}

_STRUCTURAL_BRIDGES = frozenset({
    "defines", "method", "implements", "overrides", "references", "uses",
})


def _adjacency_relations(G: nx.Graph, source: str, target: str) -> frozenset[str]:
    """Return every normalized relation carried by one graph adjacency."""

    raw = G.get_edge_data(source, target, default={})
    edge_values = raw.values() if G.is_multigraph() else (raw,)
    return frozenset(
        _canonical_relation(data)
        for data in edge_values
        if data.get("relation")
    )


def _edge_priority(G: nx.Graph, source: str, target: str) -> float:
    """Return the cheapest semantic relation carried by an adjacency."""

    raw = G.get_edge_data(source, target, default={})
    edge_values = raw.values() if G.is_multigraph() else (raw,)

    def _cost(data: dict) -> float:
        relation = _canonical_relation(data)
        cost = _RELATION_COSTS.get(relation, 4.0)
        context = str(data.get("context", "")).lower()
        # A class can expose hundreds of fields and only a handful of methods.
        # For execution-flow questions, unmatched field membership is useful
        # context but not a bridge to the next runtime step. Query relevance can
        # still lower this cost for a specifically named state field.
        if context == "field" and relation in {"defines", "references", "uses"}:
            return max(cost, 3.8)
        return cost

    return min(
        (_cost(data) for data in edge_values),
        default=4.0,
    )


def _node_relevance_bonus(
    G: nx.Graph,
    node: str,
    relevance_terms: frozenset[str],
) -> float:
    """Reward query-matching destinations without overriding graph semantics.

    The capped bonus can reorder peers and bring a matching structural member
    ahead of a large class fan-out. It cannot make an edge free or outweigh an
    entire additional hop, so causal relationships remain the primary signal.
    """

    if not relevance_terms:
        return 0.0
    data = G.nodes[node]
    label = str(data.get("label", node))
    words = {
        part.lower()
        for part in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|[0-9]+", label)
    }
    compact = re.sub(r"[^a-z0-9]", "", label.lower())
    bonus = 0.0
    for term in relevance_terms:
        normalized = re.sub(r"[^a-z0-9]", "", term.lower())
        if len(normalized) < 2:
            continue
        if normalized in words:
            bonus += 0.6
        elif normalized in compact:
            bonus += 0.35
    return min(bonus, 1.5)


def bounded_best_first(
    G: nx.Graph,
    start_nodes: list[str],
    *,
    depth: int,
    max_nodes: int,
    max_edges: int | None = None,
    relevance_terms: set[str] | frozenset[str] | None = None,
    structural_branch_limit: int | None = None,
) -> tuple[set[str], list[tuple[str, str]]]:
    """Traverse the lowest-cost semantic paths within explicit evidence budgets.

    The queue is deterministic, relation-aware, and bounded before rendering.
    This prevents a high-fan-out call site from producing hundreds of nodes that
    are later discarded only by the text-token truncation layer.
    """

    node_limit = max(1, max_nodes)
    # Zero is a valid explicit evidence budget, and negative caller input must
    # not accidentally admit the first direct-seed edge either.
    edge_limit = max(0, max_edges) if max_edges is not None else node_limit * 2
    normalized_terms = frozenset(term.lower() for term in (relevance_terms or ()))
    # Structural fan-out grows with the caller's evidence budget, but one class
    # cannot consume it all. This is intentionally dynamic rather than a fixed
    # top-k: small packets remain focused and larger investigations retain more
    # members. Omitted neighbors are detected by the caller's coverage check.
    structural_limit = (
        max(1, structural_branch_limit)
        if structural_branch_limit is not None
        else max(4, min(12, node_limit // 8))
    )
    seeds = [node for node in start_nodes if node in G][:node_limit]
    frontier: list[tuple[float, int, str, str, tuple[str, str] | None]] = []
    best_cost: dict[str, float] = {}
    for node in seeds:
        best_cost[node] = 0.0
        heapq.heappush(frontier, (0.0, 0, str(node), node, None))

    visited: set[str] = set()
    # Multiple high-confidence seeds can be directly connected. Because every
    # seed enters the frontier with zero cost, normal parent-edge discovery
    # would skip that relationship as an already-cheaper destination. Preserve
    # direct seed evidence once, in deterministic order.
    seed_set = set(seeds)
    edges: list[tuple[str, str]] = []
    for source in sorted(seeds, key=str):
        if len(edges) >= edge_limit:
            break
        for target in sorted(G.neighbors(source), key=str):
            edge = (source, target)
            reverse = (target, source)
            if target in seed_set and edge not in edges and reverse not in edges:
                edges.append(edge)
                if len(edges) >= edge_limit:
                    break
        if len(edges) >= edge_limit:
            break
    while frontier and len(visited) < node_limit:
        cost, hops, _stable_id, node, parent_edge = heapq.heappop(frontier)
        if node in visited or cost > best_cost.get(node, float("inf")):
            continue
        visited.add(node)
        if parent_edge is not None and len(edges) < edge_limit:
            edges.append(parent_edge)
        if hops >= depth:
            continue
        candidates = []
        for neighbor in G.neighbors(node):
            if neighbor in visited:
                continue
            edge_cost = _edge_priority(G, node, neighbor)
            relevance_bonus = _node_relevance_bonus(G, neighbor, normalized_terms)
            candidate_cost = cost + max(0.05, edge_cost - relevance_bonus)
            relations = _adjacency_relations(G, node, neighbor)
            structural = bool(relations) and relations <= _STRUCTURAL_BRIDGES
            candidates.append((candidate_cost, str(neighbor), neighbor, structural))

        structural_added = 0
        for candidate_cost, _neighbor_id, neighbor, structural in sorted(candidates):
            if structural and structural_added >= structural_limit:
                continue
            if candidate_cost >= best_cost.get(neighbor, float("inf")):
                continue
            if structural:
                structural_added += 1
            best_cost[neighbor] = candidate_cost
            heapq.heappush(
                frontier,
                (candidate_cost, hops + 1, str(neighbor), neighbor, (node, neighbor)),
            )
    return visited, edges
