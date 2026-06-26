from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import heapq
from pathlib import Path
from typing import Iterable, Mapping
import unicodedata

import networkx as nx


DEFAULT_AFFECTED_RELATIONS = (
    "calls",
    "references",
    "imports",
    "imports_from",
    "re_exports",
    "inherits",
    "extends",
    "implements",
    "uses",
    "mixes_in",
    "embeds",
)

DEFAULT_RELATION_WEIGHTS: Mapping[str, float] = {
    "calls": 1.0,
    "references": 0.9,
    "imports": 0.85,
    "imports_from": 0.85,
    "re_exports": 0.8,
    "inherits": 0.75,
    "extends": 0.75,
    "implements": 0.75,
    "uses": 1.0,
    "mixes_in": 0.9,
    "embeds": 0.7,
}


@dataclass(frozen=True)
class AffectedHit:
    node_id: str
    depth: int
    via_relation: str


@dataclass(frozen=True)
class WeightedAffectedHit:
    node_id: str
    cost: float
    via_relation: str
    path: tuple[str, ...]


@dataclass(frozen=True)
class WeightedAffectedResult:
    hits: tuple[WeightedAffectedHit, ...]
    proof_paths: dict[str, tuple[str, ...]]
    metrics: dict[str, int | float]


@dataclass(frozen=True)
class PreparedAffectedGraph:
    graph: nx.Graph
    incoming: dict[str, tuple[tuple[str, str, str], ...]]
    degree: dict[str, int]


def _node_label(graph: nx.Graph, node_id: str) -> str:
    data = graph.nodes[node_id]
    return str(data.get("label") or node_id)


def _format_location(data: dict) -> str:
    source_file = data.get("source_file") or "-"
    source_location = data.get("source_location")
    if source_location:
        return f"{source_file}:{source_location}"
    return str(source_file)


def _bare_name(label: str) -> str:
    """Lowercased label with the callable decoration (trailing "()") removed."""
    label = _normalize_label(label)
    return label[:-2] if label.endswith("()") else label


def _normalize_label(label: str) -> str:
    return unicodedata.normalize("NFC", label).casefold()


def resolve_seed(graph: nx.Graph, query: str) -> str | None:
    if query in graph:
        return query
    query_lower = _normalize_label(query)
    exact_label_matches = [
        str(node_id)
        for node_id, data in graph.nodes(data=True)
        if _normalize_label(str(data.get("label", ""))) == query_lower
    ]
    if len(exact_label_matches) == 1:
        return exact_label_matches[0]
    # Callable labels are decorated ("name()"), so a bare "name" query falls
    # through exact matching and then ties with any "name*" sibling in the
    # contains pass. Match on the undecorated name before giving up.
    query_bare = _bare_name(query_lower)
    bare_name_matches = [
        str(node_id)
        for node_id, data in graph.nodes(data=True)
        if _bare_name(str(data.get("label", ""))) == query_bare
    ]
    if len(bare_name_matches) == 1:
        return bare_name_matches[0]
    exact_source_matches = [
        str(node_id)
        for node_id, data in graph.nodes(data=True)
        if _normalize_label(str(data.get("source_file", ""))) == query_lower
    ]
    if len(exact_source_matches) == 1:
        return exact_source_matches[0]
    contains_matches = [
        str(node_id)
        for node_id, data in graph.nodes(data=True)
        if query_lower in _normalize_label(str(data.get("label", "")))
    ]
    if len(contains_matches) == 1:
        return contains_matches[0]
    return None


def prepare_affected_graph(graph: nx.Graph) -> PreparedAffectedGraph:
    incoming: dict[str, list[tuple[str, str, str]]] = {}
    for source, target, data in graph.edges(data=True):
        source_id = str(source)
        target_id = str(target)
        relation = str(data.get("relation", ""))
        incoming.setdefault(target_id, []).append((source_id, target_id, relation))
    ordered = {
        node_id: tuple(sorted(edges, key=lambda edge: (edge[0], edge[2])))
        for node_id, edges in incoming.items()
    }
    degree = {str(node_id): int(deg) for node_id, deg in graph.degree()}
    return PreparedAffectedGraph(graph=graph, incoming=ordered, degree=degree)


def _path_to_seed(parent: Mapping[str, tuple[str, str]], seed: str, node_id: str) -> tuple[str, ...]:
    path = [node_id]
    current = node_id
    for _ in range(500):
        if current == seed:
            return tuple(path)
        nxt = parent.get(current)
        if not nxt:
            return tuple()
        current = nxt[0]
        path.append(current)
    return tuple()


def weighted_affected_details(
    graph: nx.Graph,
    seed: str,
    *,
    relations: Iterable[str] = DEFAULT_AFFECTED_RELATIONS,
    relation_weights: Mapping[str, float] | None = None,
    max_cost: float | None = None,
    max_nodes: int = 200,
    hub_degree: int | None = None,
    hub_penalty: float = 2.0,
    expand_hubs: bool = False,
    proof_targets: Iterable[str] = (),
) -> WeightedAffectedResult:
    relation_set = set(relations)
    weights = dict(DEFAULT_RELATION_WEIGHTS)
    if relation_weights:
        weights.update({str(k): float(v) for k, v in relation_weights.items()})
    prepared = prepare_affected_graph(graph)
    limit = max(1, int(max_nodes))
    max_allowed_cost = float("inf") if max_cost is None else max(0.0, float(max_cost))
    hub_threshold = None if hub_degree is None else max(1, int(hub_degree))
    penalty = max(0.0, float(hub_penalty))

    dist: dict[str, float] = {seed: 0.0}
    parent: dict[str, tuple[str, str]] = {}
    via: dict[str, str] = {}
    queue: list[tuple[float, int, str]] = [(0.0, 0, seed)]
    counter = 1
    visited: set[str] = set()
    hits: list[WeightedAffectedHit] = []
    traversed_edges = 0
    hub_skips = 0
    max_seen_cost = 0.0

    while queue and len(hits) < limit:
        cost, _order, current = heapq.heappop(queue)
        if current in visited:
            continue
        if cost != dist.get(current):
            continue
        visited.add(current)
        max_seen_cost = max(max_seen_cost, cost)
        if current != seed:
            path = _path_to_seed(parent, seed, current)
            hits.append(
                WeightedAffectedHit(
                    node_id=current,
                    cost=round(cost, 6),
                    via_relation=via.get(current, ""),
                    path=path,
                )
            )

        is_hub = hub_threshold is not None and prepared.degree.get(current, 0) >= hub_threshold
        if current != seed and is_hub and not expand_hubs:
            hub_skips += 1
            continue

        for source, _target, relation in prepared.incoming.get(current, ()):
            if relation not in relation_set:
                continue
            traversed_edges += 1
            if source in visited:
                continue
            relation_cost = max(0.01, float(weights.get(relation, 1.0)))
            source_is_hub = hub_threshold is not None and prepared.degree.get(source, 0) >= hub_threshold
            next_cost = cost + relation_cost + (penalty if source_is_hub and source != seed else 0.0)
            if next_cost > max_allowed_cost:
                continue
            if next_cost < dist.get(source, float("inf")):
                dist[source] = next_cost
                parent[source] = (current, relation)
                via[source] = relation
                heapq.heappush(queue, (next_cost, counter, source))
                counter += 1

    proof_paths = {
        target: _path_to_seed(parent, seed, target)
        for target in proof_targets
        if target == seed or target in visited
    }
    return WeightedAffectedResult(
        hits=tuple(hits),
        proof_paths=proof_paths,
        metrics={
            "visited_nodes": len(visited),
            "traversed_edges": traversed_edges,
            "hub_skips": hub_skips,
            "max_cost": round(max_seen_cost, 6),
        },
    )


def weighted_affected_nodes(
    graph: nx.Graph,
    seed: str,
    *,
    relations: Iterable[str] = DEFAULT_AFFECTED_RELATIONS,
    relation_weights: Mapping[str, float] | None = None,
    max_cost: float | None = None,
    max_nodes: int = 200,
    hub_degree: int | None = None,
    hub_penalty: float = 2.0,
    expand_hubs: bool = False,
) -> list[WeightedAffectedHit]:
    return list(
        weighted_affected_details(
            graph,
            seed,
            relations=relations,
            relation_weights=relation_weights,
            max_cost=max_cost,
            max_nodes=max_nodes,
            hub_degree=hub_degree,
            hub_penalty=hub_penalty,
            expand_hubs=expand_hubs,
        ).hits
    )


def affected_proof_path(
    graph: nx.Graph,
    seed: str,
    target: str,
    *,
    relations: Iterable[str] = DEFAULT_AFFECTED_RELATIONS,
    relation_weights: Mapping[str, float] | None = None,
    max_cost: float | None = None,
    max_nodes: int = 200,
    hub_degree: int | None = None,
    hub_penalty: float = 2.0,
    expand_hubs: bool = False,
) -> tuple[str, ...]:
    if target == seed:
        return (seed,)
    details = weighted_affected_details(
        graph,
        seed,
        relations=relations,
        relation_weights=relation_weights,
        max_cost=max_cost,
        max_nodes=max_nodes,
        hub_degree=hub_degree,
        hub_penalty=hub_penalty,
        expand_hubs=expand_hubs,
        proof_targets=(target,),
    )
    return details.proof_paths.get(target, tuple())


def affected_nodes(
    graph: nx.Graph,
    seed: str,
    *,
    relations: Iterable[str] = DEFAULT_AFFECTED_RELATIONS,
    depth: int = 2,
) -> list[AffectedHit]:
    relation_set = set(relations)
    seen = {seed}
    queue: deque[tuple[str, int]] = deque([(seed, 0)])
    hits: list[AffectedHit] = []

    while queue:
        current, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        if hasattr(graph, "in_edges"):
            incoming = graph.in_edges(current, data=True)
        else:
            incoming = (
                (source, target, data)
                for source, target, data in graph.edges(data=True)
                if target == current
            )
        for source, _target, data in incoming:
            relation = str(data.get("relation", ""))
            if relation not in relation_set:
                continue
            source = str(source)
            if source in seen:
                continue
            seen.add(source)
            hit = AffectedHit(source, current_depth + 1, relation)
            hits.append(hit)
            queue.append((source, current_depth + 1))

    return hits


def format_affected(
    graph: nx.Graph,
    query: str,
    *,
    relations: Iterable[str] = DEFAULT_AFFECTED_RELATIONS,
    depth: int = 2,
) -> str:
    relation_list = tuple(relations)
    seed = resolve_seed(graph, query)
    if seed is None:
        return f"No unique node match for {query}"

    hits = affected_nodes(graph, seed, relations=relation_list, depth=depth)
    lines = [
        f"Affected nodes for {_node_label(graph, seed)}",
        f"Relations: {', '.join(relation_list)}",
        f"Depth: {depth}",
    ]
    if not hits:
        lines.append("No affected nodes found.")
        return "\n".join(lines)

    for hit in hits:
        data = graph.nodes[hit.node_id]
        lines.append(
            f"- {_node_label(graph, hit.node_id)} [{hit.via_relation}] {_format_location(data)}"
        )
    return "\n".join(lines)


def load_graph(path: Path) -> nx.Graph:
    import json
    from networkx.readwrite import json_graph

    raw = json.loads(path.read_text(encoding="utf-8"))
    # Force directed so stored caller→callee direction survives the round-trip;
    # mirrors serve.py and __main__.py (#1174).
    raw = {**raw, "directed": True}
    # Normalize the edge key: graphify's `extract` output uses "edges" while
    # networkx's node_link_data default is "links". Without this, an edges-keyed
    # graph.json raises an uncaught KeyError: 'links' here — every other loader
    # (__main__.py) already normalizes this (#738; same class as #1198).
    if "links" not in raw and "edges" in raw:
        raw = dict(raw, links=raw["edges"])
    try:
        return json_graph.node_link_graph(raw, edges="links")
    except TypeError:
        return json_graph.node_link_graph(raw)
