from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import unicodedata

import networkx as nx


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


def _bare_name(label: str) -> str:
    """Lowercased label with the callable decoration (trailing "()") removed."""
    label = _normalize_label(label)
    return label[:-2] if label.endswith("()") else label


def _normalize_label(label: str) -> str:
    return unicodedata.normalize("NFC", label).casefold()


def _prefer_file_node(
    graph: nx.Graph,
    node_ids: list[str],
    query: str,
) -> str | None:
    """Return the file-level node when a source_file query matches many nodes."""
    query_basename = _normalize_label(Path(query).name)
    exact_file_nodes = [
        node_id
        for node_id in node_ids
        if str(graph.nodes[node_id].get("source_location", "")) == "L1"
        and _normalize_label(str(graph.nodes[node_id].get("label", ""))) == query_basename
    ]
    if len(exact_file_nodes) == 1:
        return exact_file_nodes[0]

    l1_nodes = [
        node_id
        for node_id in node_ids
        if str(graph.nodes[node_id].get("source_location", "")) == "L1"
    ]
    if len(l1_nodes) == 1:
        return l1_nodes[0]

    basename_nodes = [
        node_id
        for node_id in node_ids
        if _normalize_label(str(graph.nodes[node_id].get("label", ""))) == query_basename
    ]
    if len(basename_nodes) == 1:
        return basename_nodes[0]

    return None


def resolve_seed(graph: nx.Graph, query: str) -> str | None:
    # A trailing path separator must not change a source-file match — serve's
    # _find_node tokenizes the path (which drops it), so strip it here for parity
    # (otherwise `affected "src/x.ts/"` returned None while `explain` resolved it).
    query = query.rstrip("/\\") or query
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
    if exact_source_matches:
        preferred_file_node = _prefer_file_node(graph, exact_source_matches, query)
        if preferred_file_node is not None:
            return preferred_file_node
    contains_matches = [
        str(node_id)
        for node_id, data in graph.nodes(data=True)
        if query_lower in _normalize_label(str(data.get("label", "")))
    ]
    if len(contains_matches) == 1:
        return contains_matches[0]
    return None


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

    # #1669: seed the reverse walk with the root's own member nodes (one outward
    # `method`/`contains` hop). A caller can bind to a class's method node rather
    # than the class node itself (e.g. `Service.call` resolves to the `def
    # self.call` node, #1634), so those callers are unreachable from the class
    # otherwise. The member nodes are seeds only (not reported as hits), and
    # `method`/`contains` stay out of the general relation-filtered walk, so this
    # adds no forward noise anywhere else.
    if hasattr(graph, "out_edges"):
        member_edges = graph.out_edges(seed, data=True)
    else:
        member_edges = (
            (s, t, d) for s, t, d in graph.edges(data=True) if s == seed
        )
    for _s, member, data in member_edges:
        if str(data.get("relation", "")) not in ("method", "contains"):
            continue
        member = str(member)
        if member not in seen:
            seen.add(member)
            queue.append((member, 0))

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

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(
            f"Cannot read graph file {path}: {exc}. "
            "Re-run 'graphify extract' to regenerate it."
        ) from exc
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
