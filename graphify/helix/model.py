"""Graphify's narrow construction and loaded-generation boundaries.

``GraphBuildData`` is a disposable batch payload.  It intentionally has no
adjacency structure or graph algorithms.  ``LoadedGraph`` owns the native
immutable Helix snapshot and the durable state selected from the same
generation; it intentionally does not copy topology into Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Literal, Mapping


GraphKind = Literal["graph", "digraph", "multigraph", "multidigraph"]


def _identity_key(value: Any) -> str:
    import json
    from helixdb.graph import external_id_to_json

    return json.dumps(external_id_to_json(value), sort_keys=True, separators=(",", ":"))


def import_identity(value: Any) -> Any:
    """Decode an explicit JSON-export identity, leaving ordinary IDs unchanged."""
    if isinstance(value, dict) and set(value) == {"__helix_external_id_v1"}:
        from helixdb.graph import external_id_from_json

        return external_id_from_json(value)
    return value


def _export_identity(value: Any) -> Any:
    if isinstance(value, (bytes, tuple, frozenset)):
        from helixdb.graph import external_id_to_json

        return external_id_to_json(value)
    return value


@dataclass(frozen=True)
class NodeData:
    id: Any
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EdgeData:
    source: Any
    target: Any
    attributes: Mapping[str, Any] = field(default_factory=dict)
    key: Any | None = None


@dataclass
class GraphBuildData:
    """Transient records awaiting one staged Helix generation write."""

    kind: GraphKind = "graph"
    nodes: list[NodeData] = field(default_factory=list)
    edges: list[EdgeData] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def directed(self) -> bool:
        return self.kind in {"digraph", "multidigraph"}

    @property
    def multigraph(self) -> bool:
        return self.kind in {"multigraph", "multidigraph"}

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    @classmethod
    def from_node_link(cls, payload: Mapping[str, Any]) -> "GraphBuildData":
        if not isinstance(payload, Mapping):
            raise TypeError("node-link graph payload must be a mapping")
        directed = bool(payload.get("directed", False))
        multigraph = bool(payload.get("multigraph", False))
        kind: GraphKind = (
            "multidigraph" if directed and multigraph else
            "digraph" if directed else
            "multigraph" if multigraph else
            "graph"
        )
        raw_nodes = payload.get("nodes", [])
        raw_edges = payload.get("links", payload.get("edges", []))
        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            raise TypeError("node-link nodes and links must be lists")
        nodes: list[NodeData] = []
        seen: set[str] = set()
        for index, raw in enumerate(raw_nodes):
            if not isinstance(raw, Mapping) or "id" not in raw:
                raise TypeError(f"nodes[{index}] must contain an id")
            node_id = import_identity(raw["id"])
            identity_key = _identity_key(node_id)
            if identity_key in seen:
                raise ValueError(f"duplicate node identifier at nodes[{index}]")
            seen.add(identity_key)
            nodes.append(NodeData(node_id, {k: v for k, v in raw.items() if k != "id"}))
        edges: list[EdgeData] = []
        for index, raw in enumerate(raw_edges):
            if not isinstance(raw, Mapping) or "source" not in raw or "target" not in raw:
                raise TypeError(f"links[{index}] must contain source and target")
            source, target = import_identity(raw["source"]), import_identity(raw["target"])
            if _identity_key(source) not in seen or _identity_key(target) not in seen:
                raise ValueError(f"links[{index}] references a missing node")
            edges.append(EdgeData(
                source,
                target,
                {k: v for k, v in raw.items() if k not in {"source", "target", "key"}},
                import_identity(raw.get("key")) if multigraph else None,
            ))
        reserved = {"directed", "multigraph", "graph", "nodes", "links", "edges", "graphify_state"}
        return cls(
            kind=kind,
            nodes=nodes,
            edges=edges,
            attributes=dict(payload.get("graph", {})),
            extras={k: v for k, v in payload.items() if k not in reserved},
        )

    def to_node_link(
        self,
        *,
        state: Mapping[str, Any] | None = None,
        tagged_identities: bool = False,
    ) -> dict[str, Any]:
        identity = _export_identity if tagged_identities else lambda value: value
        payload: dict[str, Any] = {
            "directed": self.directed,
            "multigraph": self.multigraph,
            "graph": dict(self.attributes),
            "nodes": [{"id": identity(node.id), **dict(node.attributes)} for node in self.nodes],
            "links": [],
            **self.extras,
        }
        for edge in self.edges:
            record = {
                "source": identity(edge.source),
                "target": identity(edge.target),
                **dict(edge.attributes),
            }
            if self.multigraph:
                record["key"] = identity(edge.key)
            payload["links"].append(record)
        if state is not None:
            payload["graphify_state"] = dict(state)
        return payload


@dataclass(frozen=True)
class LoadedGraph:
    """One native graph snapshot and durable state from the same generation."""

    graph: Any
    generation: str
    state: Mapping[str, Any]
    metadata: Mapping[str, Any]
    store_path: Path
    query: Any | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", MappingProxyType(dict(self.state)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


def graphify_attributes(attributes: Mapping[str, Any]) -> dict[str, Any]:
    """Return selected Graphify attributes from a native record."""
    nested = attributes.get("attrs")
    return dict(nested) if isinstance(nested, Mapping) else dict(attributes)


def node_attributes(graph: Any, node_id: Any) -> dict[str, Any]:
    node = graph.node(node_id)
    if node is None:
        raise KeyError(node_id)
    return graphify_attributes(node.attributes)


def edge_attributes(edge: Any) -> dict[str, Any]:
    """Project a native semantic label into a transient/output attribute DTO."""
    attributes = graphify_attributes(edge.attributes)
    attributes.setdefault("relation", edge.label)
    return attributes


def edge_records(graph: Any, edge_ids: Iterable[Any] | None = None) -> tuple[Any, ...]:
    if edge_ids is None:
        return graph.edges()
    records = []
    for edge_id in edge_ids:
        edge = graph.edge(edge_id)
        if edge is not None:
            records.append(edge)
    return tuple(records)


__all__ = [
    "EdgeData", "GraphBuildData", "GraphKind", "LoadedGraph", "NodeData",
    "edge_attributes", "edge_records", "graphify_attributes", "import_identity",
    "node_attributes",
]
