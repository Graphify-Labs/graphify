"""LLM field aliases: node file/path/filepath -> source_file, edge relationship -> relation."""
from __future__ import annotations

import io
from contextlib import redirect_stderr

from graphify.build import (
    _fold_confidence,
    _fold_edge_aliases,
    _fold_node_aliases,
    build_from_json,
)


def test_edge_relationship_folds_to_relation():
    edge = {"source": "a", "target": "b", "relationship": "calls"}
    _fold_edge_aliases(edge)
    assert edge["relation"] == "calls"
    assert "relationship" not in edge


def test_edge_relation_wins_over_relationship():
    edge = {"source": "a", "target": "b", "relation": "imports", "relationship": "calls"}
    _fold_edge_aliases(edge)
    assert edge["relation"] == "imports"


def test_node_file_folds_to_source_file():
    node = {"id": "a", "label": "A", "file": "foo.ts"}
    _fold_node_aliases(node)
    assert node["source_file"] == "foo.ts"
    assert "file" not in node


def test_node_path_folds_to_source_file():
    node = {"id": "a", "label": "A", "path": "bar.py"}
    _fold_node_aliases(node)
    assert node["source_file"] == "bar.py"
    assert "path" not in node


def test_node_filepath_folds_to_source_file():
    node = {"id": "a", "label": "A", "filepath": "baz.go"}
    _fold_node_aliases(node)
    assert node["source_file"] == "baz.go"


def test_node_source_file_wins_over_alias():
    node = {"id": "a", "label": "A", "source_file": "real.py", "file": "other.py"}
    _fold_node_aliases(node)
    assert node["source_file"] == "real.py"


def test_numeric_confidence_folds_to_inferred_and_backfills_score():
    edge = {"source": "a", "target": "b", "confidence": 0.85}
    _fold_edge_aliases(edge)
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.85


def test_numeric_confidence_does_not_override_an_existing_score():
    edge = {"source": "a", "target": "b", "confidence": 0.85, "confidence_score": 0.5}
    _fold_edge_aliases(edge)
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.5


def test_model_drifted_string_confidence_folds_to_inferred():
    # "high"/"confirmed"/"medium-high"/"medium-low" are model drift from the
    # LLM semantic pass, not the documented EXTRACTED/INFERRED/AMBIGUOUS enum
    # (#4495): none of them parse as a float, so confidence_score is left
    # alone and only the enum field itself is repaired.
    for drifted in ("high", "confirmed", "medium-high", "medium-low"):
        edge = {"source": "a", "target": "b", "confidence": drifted}
        _fold_edge_aliases(edge)
        assert edge["confidence"] == "INFERRED", drifted
        assert "confidence_score" not in edge, drifted


def test_numeric_looking_string_confidence_backfills_score():
    """A string that DOES parse as a float still backfills confidence_score,
    the same as a genuinely numeric confidence (#4495)."""
    edge = {"source": "a", "target": "b", "confidence": "0.85"}
    _fold_edge_aliases(edge)
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.85


def test_lowercase_confidence_is_case_corrected_not_treated_as_drift():
    """A case variant of a real enum value (#4495) IS the enum value, just
    mis-cased -- it must be corrected to its exact spelling, not treated as
    an unknown word that backfills confidence_score from a failed float
    parse of a string that was never meant to be a number."""
    edge = {"source": "a", "target": "b", "confidence": "inferred"}
    _fold_edge_aliases(edge)
    assert edge["confidence"] == "INFERRED"
    assert "confidence_score" not in edge


def test_valid_enum_confidences_are_left_untouched():
    for valid in ("EXTRACTED", "INFERRED", "AMBIGUOUS"):
        edge = {"source": "a", "target": "b", "confidence": valid}
        _fold_edge_aliases(edge)
        assert edge["confidence"] == valid
        assert "confidence_score" not in edge


def test_hyperedge_confidence_folds_the_same_way():
    """#4495: a hyperedge carries the same confidence/confidence_score pair
    an edge does, and had no fold of its own."""
    he = {"id": "h1", "nodes": ["a", "b"], "confidence": "high"}
    _fold_confidence(he)
    assert he["confidence"] == "INFERRED"

    he_numeric = {"id": "h2", "nodes": ["a", "b"], "confidence": 0.75}
    _fold_confidence(he_numeric)
    assert he_numeric["confidence"] == "INFERRED"
    assert he_numeric["confidence_score"] == 0.75


def test_build_from_json_normalizes_drifted_confidence_without_warning():
    """#4495 end to end: a graph carrying the exact warning text from the
    issue must build silently, with the edge and hyperedge confidence both
    repaired to the enum."""
    extraction = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "document", "source_file": "a.md"},
            {"id": "b", "label": "B", "file_type": "document", "source_file": "b.md"},
        ],
        "edges": [
            {
                "source": "a", "target": "b", "relation": "references",
                "confidence": "confirmed", "source_file": "a.md",
            }
        ],
        "hyperedges": [
            {"id": "h1", "nodes": ["a", "b"], "relation": "form", "confidence": "high"}
        ],
    }
    err = io.StringIO()
    with redirect_stderr(err):
        G = build_from_json(extraction)
    assert "invalid confidence" not in err.getvalue()
    _, _, data = next(iter(G.edges(data=True)))
    assert data["confidence"] == "INFERRED"
    assert G.graph["hyperedges"][0]["confidence"] == "INFERRED"


def test_build_from_json_normalizes_without_validation_warnings():
    extraction = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "file": "foo.ts"},
            {"id": "b", "label": "B", "file_type": "code", "path": "bar.py"},
        ],
        "edges": [
            {
                "source": "a",
                "target": "b",
                "relationship": "calls",
                "confidence": "EXTRACTED",
                "source_file": "foo.ts",
            }
        ],
    }
    err = io.StringIO()
    with redirect_stderr(err):
        G = build_from_json(extraction)
    out = err.getvalue()
    assert "missing required field" not in out
    assert G.nodes["a"]["source_file"] == "foo.ts"
    assert G.nodes["b"]["source_file"] == "bar.py"
    assert G.number_of_edges() == 1
    _, _, data = next(iter(G.edges(data=True)))
    assert data["relation"] == "calls"
