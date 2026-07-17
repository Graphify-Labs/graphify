from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import unicodedata

from .helix.model import edge_attributes, graphify_attributes, node_attributes
from .helix.persistence import load_graph as load_helix_graph


DEFAULT_AFFECTED_RELATIONS = (
    "calls",
    "indirect_call",
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
    node_id: Any
    depth: int
    via_relation: str


def _node_label(graph: Any, node_id: Any) -> str:
    data = node_attributes(graph, node_id)
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


def _prefer_file_node(
    graph: Any,
    node_ids: list[Any],
    query: str,
) -> str | None:
    """Return the file-level node when a source_file query matches many nodes."""
    query_basename = _normalize_label(Path(query).name)
    exact_file_nodes = [
        node_id
        for node_id in node_ids
        if str(node_attributes(graph, node_id).get("source_location", "")) == "L1"
        and _normalize_label(str(node_attributes(graph, node_id).get("label", ""))) == query_basename
    ]
    if len(exact_file_nodes) == 1:
        return exact_file_nodes[0]

    l1_nodes = [
        node_id
        for node_id in node_ids
        if str(node_attributes(graph, node_id).get("source_location", "")) == "L1"
    ]
    if len(l1_nodes) == 1:
        return l1_nodes[0]

    basename_nodes = [
        node_id
        for node_id in node_ids
        if _normalize_label(str(node_attributes(graph, node_id).get("label", ""))) == query_basename
    ]
    if len(basename_nodes) == 1:
        return basename_nodes[0]

    return None


def resolve_seed(graph: Any, query: str) -> Any | None:
    # A trailing path separator must not change a source-file match — serve's
    # _find_node tokenizes the path (which drops it), so strip it here for parity
    # (otherwise `affected "src/x.ts/"` returned None while `explain` resolved it).
    query = query.rstrip("/\\") or query
    if graph.contains_node(query):
        return query
    query_lower = _normalize_label(query)
    exact_label_matches = [
        node.id
        for node in graph.nodes()
        if (data := graphify_attributes(node.attributes)) is not None
        if _normalize_label(str(data.get("label", ""))) == query_lower
    ]
    if len(exact_label_matches) == 1:
        return exact_label_matches[0]
    # Callable labels are decorated ("name()"), so a bare "name" query falls
    # through exact matching and then ties with any "name*" sibling in the
    # contains pass. Match on the undecorated name before giving up.
    query_bare = _bare_name(query_lower)
    bare_name_matches = [
        node.id
        for node in graph.nodes()
        if (data := graphify_attributes(node.attributes)) is not None
        if _bare_name(str(data.get("label", ""))) == query_bare
    ]
    if len(bare_name_matches) == 1:
        return bare_name_matches[0]
    exact_source_matches = [
        node.id
        for node in graph.nodes()
        if (data := graphify_attributes(node.attributes)) is not None
        if _normalize_label(str(data.get("source_file", ""))) == query_lower
    ]
    if len(exact_source_matches) == 1:
        return exact_source_matches[0]
    if exact_source_matches:
        preferred_file_node = _prefer_file_node(graph, exact_source_matches, query)
        if preferred_file_node is not None:
            return preferred_file_node
    contains_matches = [
        node.id
        for node in graph.nodes()
        if (data := graphify_attributes(node.attributes)) is not None
        if query_lower in _normalize_label(str(data.get("label", "")))
    ]
    if len(contains_matches) == 1:
        return contains_matches[0]
    return None


def affected_nodes(
    graph: Any,
    seed: Any,
    *,
    relations: Iterable[str] = DEFAULT_AFFECTED_RELATIONS,
    depth: int = 2,
) -> list[AffectedHit]:
    relation_set = set(relations)
    seen = {seed}
    queue: deque[tuple[Any, int]] = deque([(seed, 0)])
    hits: list[AffectedHit] = []

    # #1669: seed the reverse walk with the root's own member nodes (one outward
    # `method`/`contains` hop). A caller can bind to a class's method node rather
    # than the class node itself (e.g. `Service.call` resolves to the `def
    # self.call` node, #1634), so those callers are unreachable from the class
    # otherwise. The member nodes are seeds only (not reported as hits), and
    # `method`/`contains` stay out of the general relation-filtered walk, so this
    # adds no forward noise anywhere else.
    member_edges = (
        graph.edge(edge_id) for edge_id in graph.out_edge_ids(seed)
    )
    for edge in member_edges:
        if edge is None:
            continue
        member, data = edge.target, edge_attributes(edge)
        if str(data.get("relation", "")) not in ("method", "contains"):
            continue
        if member not in seen:
            seen.add(member)
            queue.append((member, 0))

    while queue:
        current, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        incoming = (graph.edge(edge_id) for edge_id in graph.in_edge_ids(current))
        for edge in incoming:
            if edge is None:
                continue
            source, data = edge.source, edge_attributes(edge)
            relation = str(data.get("relation", ""))
            if relation not in relation_set:
                continue
            if source in seen:
                continue
            seen.add(source)
            hit = AffectedHit(source, current_depth + 1, relation)
            hits.append(hit)
            queue.append((source, current_depth + 1))

    return hits


def format_affected(
    graph: Any,
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
        data = node_attributes(graph, hit.node_id)
        lines.append(
            f"- {_node_label(graph, hit.node_id)} [{hit.via_relation}] {_format_location(data)}"
        )
    return "\n".join(lines)


def load_graph(path: Path):
    """Open the active immutable graph from a Helix store directory."""
    try:
        return load_helix_graph(path).graph
    except (OSError, RuntimeError, ValueError) as exc:
        raise RuntimeError(
            f"Cannot open Helix store {path}: {exc}. "
            "Re-run 'graphify extract' to regenerate it."
        ) from exc
