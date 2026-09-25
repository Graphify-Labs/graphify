"""Cross-language ontology normalization and validation contracts."""

from graphify.ontology import ONTOLOGY_VERSION, normalize_relation, relation_spec, validate_edge


def test_relation_aliases_normalize_to_one_cross_language_vocabulary():
    assert normalize_relation("reads_from") == "reads"
    assert normalize_relation("invokes") == "calls"
    assert normalize_relation("inherits") == "implements"


def test_relation_spec_preserves_direction_and_runtime_category():
    spec = relation_spec("calls")

    assert spec is not None
    assert spec.category == "runtime"
    assert spec.direction == "source_to_target"
    assert ONTOLOGY_VERSION


def test_unknown_relation_is_reported_not_silently_coerced():
    finding = validate_edge({"source": "a", "target": "b", "relation": "teleports"})

    assert finding.valid is False
    assert finding.normalized_relation is None
    assert "unknown relation" in finding.reason


def test_edge_validation_accepts_zero_as_a_node_identifier():
    """NetworkX permits integer node IDs, including zero at either endpoint."""
    assert validate_edge({"source": 0, "target": 1, "relation": "calls"}).valid
    assert validate_edge({"source": 1, "target": 0, "relation": "calls"}).valid
