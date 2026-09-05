"""Tier-1 (pure, DB-free) unit tests for the Apache AGE exporter.

These run in the default CI suite -- no live AGE instance, no psycopg
required to be installed. push_to_age() itself lazy-imports psycopg only
inside the function body, so importing graphify.exporters.graphdb here
never touches the optional `age` dependency.

See docs/AGE_PLAN.md "Testing strategy": schema selection (label/relation
sanitization) and the AGE-specific fixed-field-list logic are pure
functions precisely so they can be pinned here, in default CI, rather than
only in the live suite (tests/test_age_integration.py).
"""
from __future__ import annotations

import networkx as nx
import pytest

from graphify.exporters import graphdb


def _graph(nodes, edges):
    G = nx.DiGraph()
    for node_id, attrs in nodes:
        G.add_node(node_id, **attrs)
    for src, tgt, attrs in edges:
        G.add_edge(src, tgt, **attrs)
    return G


# ---------------------------------------------------------------------------
# Schema pin: label/relation sanitization shared across neo4j/falkordb/age.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("code", "code"),
        ("Code", "Code"),
        ("my-file", "myfile"),
        ("my file!!", "myfile"),
        ("", "Entity"),
        ("###", "Entity"),
    ],
)
def test_safe_label_pinned(raw, expected):
    assert graphdb._safe_label(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("calls", "CALLS"),
        ("imports-from", "IMPORTS_FROM"),
        ("re exports", "RE_EXPORTS"),
        ("", "RELATED_TO"),
        # Non-alphanumeric characters are replaced 1:1 with "_", not
        # collapsed -- "!!!" becomes "___", which is non-empty and so does
        # NOT fall back to RELATED_TO. Only a truly empty result does.
        ("!!!", "___"),
    ],
)
def test_safe_rel_pinned(raw, expected):
    assert graphdb._safe_rel(raw) == expected


# ---------------------------------------------------------------------------
# Lean vs. full-props field selection (AGE-specific: SET must enumerate
# fields by name, so the field list itself is a pinned, tested contract).
# ---------------------------------------------------------------------------

def test_lean_node_field_names_are_fixed_schema():
    G = _graph([("a", {"file_type": "code", "label": "A", "custom": 1})], [])
    fields = graphdb._age_node_field_names(G, full_props=False)
    assert fields == graphdb._AGE_LEAN_NODE_FIELDS
    assert "custom" not in fields


def test_full_node_field_names_include_lean_fields_plus_extras():
    G = _graph(
        [
            ("a", {"file_type": "code", "label": "A", "custom_score": 0.5}),
            ("b", {"file_type": "code", "label": "B", "other_field": "x"}),
        ],
        [],
    )
    fields = graphdb._age_node_field_names(G, full_props=True)
    assert set(graphdb._AGE_LEAN_NODE_FIELDS) <= set(fields)
    assert "custom_score" in fields
    assert "other_field" in fields
    # Lean fields keep their fixed relative order at the front.
    assert fields[: len(graphdb._AGE_LEAN_NODE_FIELDS)] == graphdb._AGE_LEAN_NODE_FIELDS


def test_full_node_field_names_exclude_private_and_non_scalar_keys():
    G = _graph(
        [("a", {"file_type": "code", "_private": "x", "nested": {"a": 1}, "listy": [1, 2]})],
        [],
    )
    fields = graphdb._age_node_field_names(G, full_props=True)
    assert "_private" not in fields
    assert "nested" not in fields
    assert "listy" not in fields


def test_lean_edge_field_names_are_fixed_schema():
    G = _graph(
        [("a", {}), ("b", {})],
        [("a", "b", {"relation": "calls", "confidence": "EXTRACTED", "weight": 1.0})],
    )
    fields = graphdb._age_edge_field_names(G, full_props=False)
    assert fields == graphdb._AGE_LEAN_EDGE_FIELDS
    assert "weight" not in fields


def test_full_edge_field_names_include_extras():
    G = _graph(
        [("a", {}), ("b", {})],
        [("a", "b", {"relation": "calls", "confidence": "EXTRACTED", "weight": 1.0})],
    )
    fields = graphdb._age_edge_field_names(G, full_props=True)
    assert "weight" in fields
    assert set(graphdb._AGE_LEAN_EDGE_FIELDS) <= set(fields)


# ---------------------------------------------------------------------------
# Row grouping: labels/relations sanitized, structural metrics stamped.
# ---------------------------------------------------------------------------

def test_age_node_rows_groups_by_sanitized_label_and_stamps_metrics():
    G = _graph(
        [
            ("a", {"file_type": "code", "label": "A", "source_file": "a.py"}),
            ("b", {"file_type": "code", "label": "B", "source_file": "b.py"}),
            ("c", {"file_type": "document", "label": "C"}),
        ],
        [("a", "b", {"relation": "calls"})],
    )
    fields = graphdb._AGE_LEAN_NODE_FIELDS
    groups = graphdb._age_node_rows(
        G, fields, node_community={"a": 0}, god_ids={"a"}, cycle_files={"a.py"}
    )
    assert set(groups.keys()) == {"Code", "Document"}
    assert len(groups["Code"]) == 2
    assert len(groups["Document"]) == 1

    row_a = next(r for r in groups["Code"] if r["id"] == "a")
    assert row_a["community"] == 0
    assert row_a["is_god_node"] is True
    assert row_a["in_cycle"] is True
    assert row_a["degree"] == G.degree("a")

    row_b = next(r for r in groups["Code"] if r["id"] == "b")
    assert row_b["is_god_node"] is False
    assert row_b["in_cycle"] is False
    assert row_b["community"] is None

    # Every row carries exactly the requested field set, no more/less.
    assert set(row_a.keys()) == set(fields)


def test_age_edge_rows_groups_by_sanitized_relation():
    G = _graph(
        [("a", {}), ("b", {}), ("c", {})],
        [
            ("a", "b", {"relation": "calls", "confidence": "EXTRACTED"}),
            ("b", "c", {"relation": "imports-from", "confidence": "INFERRED"}),
        ],
    )
    groups = graphdb._age_edge_rows(G, graphdb._AGE_LEAN_EDGE_FIELDS)
    assert set(groups.keys()) == {"CALLS", "IMPORTS_FROM"}
    row = groups["CALLS"][0]
    assert row["src"] == "a" and row["tgt"] == "b"
    assert row["confidence"] == "EXTRACTED"


def test_age_batches_chunks_correctly():
    rows = [{"id": i} for i in range(1201)]
    batches = list(graphdb._age_batches(rows, size=500))
    assert len(batches) == 3
    assert [len(b) for b in batches] == [500, 500, 201]
    assert sum(len(b) for b in batches) == len(rows)


def test_push_to_age_requires_psycopg(monkeypatch):
    """Import-guard: without psycopg installed, push_to_age() raises a
    clear, actionable ImportError rather than a bare ModuleNotFoundError."""
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "psycopg":
            raise ImportError("no module named psycopg")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    G = _graph([("a", {"file_type": "code"})], [])
    with pytest.raises(ImportError, match="graphifyy\\[age\\]"):
        graphdb.push_to_age(G, conninfo="host=localhost")
