"""Versioned, language-neutral relation ontology used at graph boundaries."""
from __future__ import annotations

from dataclasses import dataclass


ONTOLOGY_VERSION = "1.0"


@dataclass(frozen=True)
class RelationSpec:
    """Meaning and direction shared by every language-specific extractor."""

    name: str
    category: str
    direction: str = "source_to_target"


@dataclass(frozen=True)
class EdgeValidation:
    """Non-throwing validation result suitable for partial graph diagnostics."""

    valid: bool
    normalized_relation: str | None
    reason: str = ""
    reverse_endpoints: bool = False


@dataclass(frozen=True)
class RelationNormalization:
    """Canonical relation plus the endpoint transform required by an alias."""

    name: str
    reverse_endpoints: bool = False


_RELATIONS = {
    spec.name: spec
    for spec in (
        RelationSpec("contains", "structure"),
        RelationSpec("defines", "structure"),
        RelationSpec("method", "structure"),
        RelationSpec("imports", "dependency"),
        RelationSpec("imports_from", "dependency"),
        RelationSpec("exports", "dependency"),
        RelationSpec("includes", "dependency"),
        RelationSpec("depends_on", "dependency"),
        RelationSpec("requires", "dependency"),
        RelationSpec("calls", "runtime"),
        RelationSpec("indirect_call", "runtime"),
        RelationSpec("dispatches", "runtime"),
        RelationSpec("instantiates", "runtime"),
        RelationSpec("handles", "runtime"),
        RelationSpec("emits", "runtime"),
        RelationSpec("publishes", "runtime"),
        RelationSpec("subscribes", "runtime"),
        RelationSpec("enqueues", "runtime"),
        RelationSpec("dequeues", "runtime"),
        RelationSpec("consumes", "runtime"),
        RelationSpec("reads", "data"),
        RelationSpec("writes", "data"),
        RelationSpec("loads", "data"),
        RelationSpec("persists", "data"),
        RelationSpec("caches", "data"),
        RelationSpec("invalidates", "data"),
        RelationSpec("serializes", "data"),
        RelationSpec("deserializes", "data"),
        RelationSpec("references", "reference"),
        RelationSpec("uses", "reference"),
        RelationSpec("implements", "type"),
        RelationSpec("overrides", "type"),
        RelationSpec("extends", "type"),
        RelationSpec("documents", "documentation"),
        RelationSpec("mentions", "documentation"),
        RelationSpec("explains", "documentation"),
        RelationSpec("cites", "documentation"),
        RelationSpec("rationale_for", "documentation"),
    )
}

_ALIASES = {
    "call": "calls",
    "invokes": "calls",
    "invoked_by": "calls",
    "read": "reads",
    "reads_from": "reads",
    "write": "writes",
    "writes_to": "writes",
    "inherits": "extends",
    "implemented_by": "implements",
    "described_in": "documents",
    "related_to": "references",
    # SCIP producers use transport-specific relationship names. Normalize at
    # the ingestion boundary so query planning remains language-neutral.
    "scip_impl": "implements",
    "scip_typed": "references",
    "scip_def": "defines",
    "scip_ref": "references",
}

_INVERSE_ALIASES = frozenset({"invoked_by", "implemented_by", "described_in"})


def normalize_relation_with_direction(relation: str) -> RelationNormalization | None:
    """Return canonical identity and whether an inverse alias swaps endpoints."""

    normalized = str(relation or "").strip().lower().replace("-", "_").replace(" ", "_")
    canonical = _ALIASES.get(normalized, normalized)
    if canonical not in _RELATIONS:
        return None
    return RelationNormalization(canonical, normalized in _INVERSE_ALIASES)


def normalize_relation(relation: str) -> str | None:
    """Return a canonical relation, preserving unknowns as explicit gaps."""

    normalized = normalize_relation_with_direction(relation)
    return normalized.name if normalized is not None else None


def relation_spec(relation: str) -> RelationSpec | None:
    canonical = normalize_relation(relation)
    return _RELATIONS.get(canonical) if canonical else None


def relations_for_category(*categories: str) -> frozenset[str]:
    wanted = set(categories)
    return frozenset(name for name, spec in _RELATIONS.items() if spec.category in wanted)


def validate_edge(edge: dict) -> EdgeValidation:
    """Validate ontology identity and endpoints without mutating source facts."""

    normalization = normalize_relation_with_direction(str(edge.get("relation", "")))
    if normalization is None:
        return EdgeValidation(False, None, f"unknown relation: {edge.get('relation', '')}")
    source = edge.get("source")
    target = edge.get("target")
    if source is None or source == "" or target is None or target == "":
        return EdgeValidation(
            False,
            normalization.name,
            "edge requires source and target",
            normalization.reverse_endpoints,
        )
    return EdgeValidation(
        True,
        normalization.name,
        reverse_endpoints=normalization.reverse_endpoints,
    )
