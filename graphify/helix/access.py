"""Small projections over the native immutable Helix graph surface.

These helpers keep Graphify's attribute conventions in one place. Callers use
native Helix records and algorithms directly.
"""

from __future__ import annotations

from typing import Any, Iterable

from .model import edge_attributes, graphify_attributes, node_attributes


def node_ids(graph: Any) -> tuple[Any, ...]:
    return tuple(node.id for node in graph.nodes())


def node_rows(graph: Any) -> tuple[tuple[Any, dict[str, Any]], ...]:
    return tuple((node.id, graphify_attributes(node.attributes)) for node in graph.nodes())


def edge_rows(
    graph: Any, node_id: Any | None = None
) -> tuple[tuple[Any, Any, dict[str, Any], Any], ...]:
    records: Iterable[Any]
    if node_id is None:
        records = graph.edges()
    else:
        records = (
            edge
            for edge_id in graph.incident_edge_ids(node_id)
            if (edge := graph.edge(edge_id)) is not None
        )
    return tuple(
        (edge.source, edge.target, edge_attributes(edge), edge)
        for edge in records
    )


def degree_map(graph: Any) -> dict[Any, int]:
    return {row.node_id: int(row.degree) for row in graph.degrees()}


def degree(graph: Any, node_id: Any) -> int:
    return int(graph.degree(node_id).degree)


def first_edge_attributes(graph: Any, source: Any, target: Any) -> dict[str, Any]:
    edge_ids = graph.edges_between(source, target)
    if not edge_ids and not graph.directed:
        edge_ids = graph.edges_between(target, source)
    edge = graph.edge(edge_ids[0]) if edge_ids else None
    return edge_attributes(edge) if edge is not None else {}


def all_edge_attributes(graph: Any, source: Any, target: Any) -> list[dict[str, Any]]:
    edge_ids = list(graph.edges_between(source, target))
    if not edge_ids and not graph.directed:
        edge_ids = list(graph.edges_between(target, source))
    return [
        edge_attributes(edge)
        for edge_id in edge_ids
        if (edge := graph.edge(edge_id)) is not None
    ]


__all__ = [
    "all_edge_attributes",
    "degree",
    "degree_map",
    "edge_rows",
    "first_edge_attributes",
    "node_attributes",
    "node_ids",
    "node_rows",
]
