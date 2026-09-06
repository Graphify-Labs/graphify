"""Tier-1 (pure, DB-free) unit tests for graphify.age_backend
(docs/AGE_PLAN.md Phase 6): parsing AGE's agtype vertex/edge/path text
representation. No psycopg import needed -- fetch_graph_from_age()
lazy-imports psycopg only inside the function body.
"""
from __future__ import annotations

from graphify import age_backend as ab


def test_parse_agtype_objects_single_vertex():
    raw = '{"id": 1, "label": "Code", "properties": {"id": "n1", "label": "N1"}}::vertex'
    results = ab.parse_agtype_objects(raw)
    assert len(results) == 1
    obj, kind = results[0]
    assert kind == "vertex"
    assert obj["properties"]["id"] == "n1"


def test_parse_agtype_objects_single_edge():
    raw = '{"id": 5, "label": "CALLS", "properties": {"relation": "calls"}}::edge'
    (obj, kind), = ab.parse_agtype_objects(raw)
    assert kind == "edge"
    assert obj["properties"]["relation"] == "calls"


def test_parse_agtype_objects_path_multiple_elements():
    raw = (
        '[{"id": 1, "label": "Code", "properties": {"id": "a"}}::vertex, '
        '{"id": 2, "label": "CALLS", "properties": {"relation": "calls"}}::edge, '
        '{"id": 3, "label": "Code", "properties": {"id": "b"}}::vertex]::path'
    )
    results = ab.parse_agtype_objects(raw)
    kinds = [k for _, k in results]
    assert kinds == ["vertex", "edge", "vertex"]
    assert [o["properties"].get("id") for o, k in results if k == "vertex"] == ["a", "b"]


def test_parse_agtype_objects_handles_nested_properties_object():
    """The whole point of depth-aware splitting: a naive non-greedy regex
    (\\{.*?\\}::) would stop at the inner "properties" object's closing
    brace, not the outer vertex object's."""
    raw = (
        '{"id": 1, "label": "Code", '
        '"properties": {"id": "n1", "community": 2, "is_god_node": true}}::vertex'
    )
    (obj, kind), = ab.parse_agtype_objects(raw)
    assert kind == "vertex"
    assert obj["properties"] == {"id": "n1", "community": 2, "is_god_node": True}


def test_parse_agtype_objects_no_type_suffix():
    raw = '{"id": "n1", "label": "N1"}'
    (obj, kind), = ab.parse_agtype_objects(raw)
    assert kind is None
    assert obj == {"id": "n1", "label": "N1"}


def test_fetch_graph_from_age_requires_psycopg(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "psycopg":
            raise ImportError("no module named psycopg")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    import pytest
    with pytest.raises(ImportError, match="graphifyy\\[age\\]"):
        ab.fetch_graph_from_age("host=localhost", "graphify")
