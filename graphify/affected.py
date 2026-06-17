from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


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


@dataclass(frozen=True)
class AffectedHit:
    node_id: str
    depth: int
    via_relation: str


def _node_label(graph: nx.Graph, node_id: str) -> str:
    data = graph.nodes[node_id]
    return str(data.get("label") or node_id)


def _format_location(data: dict) -> str:
    source_file = data.get("source_file") or "-"
    source_location = data.get("source_location")
    if source_location:
        return f"{source_file}:{source_location}"
    return str(source_file)


def resolve_seed(graph, query: str) -> str | None:
    # FalkorDB-native: resolve via scoped queries (no full-graph load).
    if hasattr(graph, "find_node_ids"):
        if graph.has_node(query):
            return query
        for kwargs in ({"label": query}, {"source_file": query}, {"label_contains": query}):
            matches = graph.find_node_ids(limit=2, **kwargs)
            if len(matches) == 1:
                return str(matches[0])
        return None
    # In-memory fallback (nx / MemGraph)
    if query in graph:
        return query
    query_lower = query.lower()
    for field in ("label", "source_file"):
        exact = [str(n) for n, d in graph.nodes(data=True) if str(d.get(field, "")).lower() == query_lower]
        if len(exact) == 1:
            return exact[0]
    contains = [str(n) for n, d in graph.nodes(data=True) if query_lower in str(d.get("label", "")).lower()]
    return contains[0] if len(contains) == 1 else None


def affected_nodes(
    graph: nx.Graph,
    seed: str,
    *,
    relations: Iterable[str] = DEFAULT_AFFECTED_RELATIONS,
    depth: int = 2,
) -> list[AffectedHit]:
    relation_set = set(relations)

    # FalkorDB-native: one batched reverse-edge query per BFS level (depth queries
    # total) instead of a per-node loop over an in-memory copy of the graph.
    if hasattr(graph, "incoming_edges"):
        seen = {seed}
        hits: list[AffectedHit] = []
        frontier = [seed]
        for d in range(depth):
            if not frontier:
                break
            rows = graph.incoming_edges(frontier, relation_set)
            nxt: list[str] = []
            for _fid, src, relation in sorted(rows, key=lambda r: (str(r[0]), str(r[1]), str(r[2]))):
                src = str(src)
                if src in seen:
                    continue
                seen.add(src)
                hits.append(AffectedHit(src, d + 1, str(relation)))
                nxt.append(src)
            frontier = nxt
        return hits

    # In-memory fallback (nx / MemGraph)
    seen = {seed}
    queue: deque[tuple[str, int]] = deque([(seed, 0)])
    hits = []
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
            hits.append(AffectedHit(source, current_depth + 1, relation))
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

    # Fetch attrs for seed + all hits in one batched query (native) or per-node (fallback).
    ids = [seed] + [h.node_id for h in hits]
    if hasattr(graph, "node_attrs_batch"):
        attrs = graph.node_attrs_batch(ids)
    else:
        attrs = {nid: dict(graph.nodes[nid]) for nid in ids if nid in graph}

    def _label(nid):
        return str(attrs.get(nid, {}).get("label") or nid)

    lines = [
        f"Affected nodes for {_label(seed)}",
        f"Relations: {', '.join(relation_list)}",
        f"Depth: {depth}",
    ]
    if not hits:
        lines.append("No affected nodes found.")
        return "\n".join(lines)

    for hit in hits:
        data = attrs.get(hit.node_id, {})
        lines.append(
            f"- {_label(hit.node_id)} [{hit.via_relation}] {_format_location(data)}"
        )
    return "\n".join(lines)


def connect_graph(path: Path):
    """Open a connection to the FalkorDB-backed graph for the output dir containing
    `path`. Cache-free: returns a store handle (a connection), it does NOT load the
    graph into memory.

    `path` is the legacy graph.json location (e.g. graphify-out/graph.json); we
    use its parent directory to locate the FalkorDB pointer and open the store.
    """
    from .store import open_store

    out_dir = Path(path).parent if Path(path).suffix else Path(path)
    return open_store(out_dir, create=False)
