"""Shared edge typing, confidence, and filtering helpers."""
from __future__ import annotations

from math import isfinite
from typing import Mapping


_CONFIDENCE_DEFAULTS = {
    "EXTRACTED": 1.0,
    "INFERRED": 0.5,
    "AMBIGUOUS": 0.2,
}


def confidence_score(edge: Mapping[str, object]) -> float:
    """Return a bounded confidence score, with schema-safe defaults."""
    raw = edge.get("confidence_score")
    if raw is None:
        raw = _CONFIDENCE_DEFAULTS.get(str(edge.get("confidence", "EXTRACTED")), 1.0)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 1.0
    return min(1.0, max(0.0, value)) if isfinite(value) else 0.0


def effective_weight(edge: Mapping[str, object]) -> float:
    """Return relation strength adjusted by provenance confidence."""
    try:
        relation_weight = float(edge.get("weight", 1.0))
    except (TypeError, ValueError):
        relation_weight = 1.0
    if not isfinite(relation_weight) or relation_weight < 0:
        relation_weight = 1.0
    return relation_weight * confidence_score(edge)


def passes_edge_filter(
    edge: Mapping[str, object],
    *,
    min_effective_weight: float = 0.0,
    relations: set[str] | None = None,
) -> bool:
    """Whether an edge is eligible for a consumer's filtered view."""
    relation = edge.get("relation")
    if relations is not None and relation not in relations:
        return False
    return effective_weight(edge) >= min_effective_weight
