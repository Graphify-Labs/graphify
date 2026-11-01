"""Invocation-owned canonical C++ lookup data shared by native unit mappings.

The snapshot freezes container membership, not borrowed node dictionaries. It
adds no declaration proof and performs only the indexing previously repeated by
each mapping. A bound lazy mapper cannot combine a stale index with new inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from graphify.qml_resolution_types import source_path


@dataclass(frozen=True)
class AcceptedCppIndex:
    nodes: tuple
    edges: tuple
    paths: MappingProxyType
    definition_paths: MappingProxyType
    accepted: MappingProxyType
    parents: MappingProxyType
    class_parents: MappingProxyType


def accepted_cpp_index(nodes, edges, *, root):
    """Preserve ordered membership, duplicate-ID selection and exact parent provenance."""
    nodes, edges = tuple(nodes), tuple(edges)
    paths = {id(node): source_path(node, root) for node in nodes}
    definition_paths = {id(node): source_path({"source_file": node.get("definition_file")}, root)
                        for node in nodes}
    accepted = {node["id"]: node for node in nodes}
    parents, class_parents = {}, {}
    for edge in edges:
        if edge.get("relation") in {"method", "contains"}:
            parents.setdefault(edge["target"], set()).add(edge["source"])
            parent = accepted.get(edge["source"], {})
            if (edge.get("confidence") == "EXTRACTED" and parent.get("_callable_class") is True
                    and source_path(edge, root) == source_path(parent, root)):
                class_parents.setdefault(edge["target"], set()).add(edge["source"])
    return AcceptedCppIndex(nodes, edges, MappingProxyType(paths), MappingProxyType(definition_paths),
                            MappingProxyType(accepted),
                            MappingProxyType({key: frozenset(value) for key, value in parents.items()}),
                            MappingProxyType({key: frozenset(value) for key, value in class_parents.items()}))


def _accepted_cpp_mapper(nodes, edges, *, root):
    """Bind one entry cohort; do not index until an admitted source actually needs mapping."""
    nodes, edges = tuple(nodes), tuple(edges)
    index = None

    def mapping(unit):
        nonlocal index
        from graphify.extractors.qt_cpp_mapping import CppMapping

        if index is None:
            index = accepted_cpp_index(nodes, edges, root=root)
        return CppMapping._from_index(unit, index)

    return mapping
