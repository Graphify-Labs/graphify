"""Shared classification for actionable and benign graph gaps."""

from __future__ import annotations

from collections import Counter
from enum import Enum
from typing import Iterable

import networkx as nx


class GapCategory(str, Enum):
    """Mutually exclusive reasons a weak graph node is or is not actionable."""

    ACTIONABLE_LOCAL = "actionable_local"
    EXTERNAL = "external"
    RATIONALE = "rationale"
    METADATA = "metadata"
    STRUCTURAL = "structural"


def _is_external(attrs: dict) -> bool:
    """Return True only for affirmative extractor-originated evidence."""

    metadata = (
        attrs.get("metadata")
        if isinstance(attrs.get("metadata"), dict)
        else {}
    )
    return bool(
        attrs.get("external") is True
        or attrs.get("node_kind") == "external_symbol"
        or metadata.get("scip_kind") == "external"
        or str(attrs.get("id", "")).startswith("ref_")
    )


def classify_gap_node(graph: nx.Graph, node_id: str) -> GapCategory:
    """Classify one graph node without deleting or hiding it from queries."""

    from graphify.analyze import (
        _is_concept_node,
        _is_file_node,
        _is_json_key_node,
    )

    attrs = dict(graph.nodes[node_id])
    attrs.setdefault("id", node_id)
    if _is_external(attrs):
        return GapCategory.EXTERNAL
    if attrs.get("file_type") == "rationale":
        return GapCategory.RATIONALE
    if _is_json_key_node(graph, node_id):
        return GapCategory.METADATA
    if (
        _is_file_node(graph, node_id)
        or _is_concept_node(graph, node_id)
        or attrs.get("node_kind") in {"page", "heading"}
    ):
        return GapCategory.STRUCTURAL
    if attrs.get("source_file"):
        return GapCategory.ACTIONABLE_LOCAL
    return GapCategory.STRUCTURAL


def gap_breakdown(
    graph: nx.Graph,
    node_ids: Iterable[str],
) -> dict[str, int]:
    """Count every supplied node in the shared classification vocabulary."""

    counts = Counter(
        classify_gap_node(graph, node_id).value for node_id in node_ids
    )
    return {
        category.value: counts.get(category.value, 0)
        for category in GapCategory
    }
