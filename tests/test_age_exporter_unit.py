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


def test_age_edge_rows_honors_src_tgt_over_undirected_tuple_order():
    """build.py stamps _src/_tgt on every edge because an undirected
    nx.Graph's own (u, v) tuple order reflects node insertion order, not
    which side was the extracted "source" (confirmed live: adding node
    "b" before node "a" then G.add_edge("a", "b") makes G.edges() yield
    ("b", "a", ...)). _age_edge_rows must read _src/_tgt, not u/v
    directly, or every edge can silently push backwards."""
    import networkx as nx

    G = nx.Graph()
    # Insert target before source -- this is exactly the case that
    # reverses G.edges()'s tuple order for an undirected graph.
    G.add_node("callee")
    G.add_node("caller")
    G.add_edge("caller", "callee", relation="calls", confidence="EXTRACTED",
               _src="caller", _tgt="callee")
    assert list(G.edges(data=False)) == [("callee", "caller")]  # the trap

    groups = graphdb._age_edge_rows(G, graphdb._AGE_LEAN_EDGE_FIELDS)
    row = groups["CALLS"][0]
    assert row["src"] == "caller"
    assert row["tgt"] == "callee"


def test_age_edge_rows_falls_back_to_tuple_order_without_src_tgt():
    """Directed graphs (or any edge lacking _src/_tgt) fall back to the
    tuple order, which is correct there."""
    G = _graph([("a", {}), ("b", {})], [("a", "b", {"relation": "calls"})])
    groups = graphdb._age_edge_rows(G, graphdb._AGE_LEAN_EDGE_FIELDS)
    row = groups["CALLS"][0]
    assert row["src"] == "a" and row["tgt"] == "b"


def test_age_index_names_short_label():
    assert graphdb._age_gin_index_name("Code") == "Code_props_gin"
    assert graphdb._age_index_name("Code", "id_idx") == "Code_id_idx"
    assert graphdb._age_index_name("Code", "source_file_idx") == "Code_source_file_idx"


@pytest.mark.parametrize("suffix", ["props_gin", "id_idx", "source_file_idx"])
def test_age_index_name_long_label_stays_within_63_bytes(suffix):
    long = "A" * 80
    name = graphdb._age_index_name(long, suffix)
    assert len(name) <= 63
    assert name.endswith(suffix)
    assert name == graphdb._age_index_name(long, suffix)  # deterministic


def test_age_indexed_node_props_covers_agent_filter_fields():
    # docs/AGE_SCHEMA.md's agent contract: agents filter/join on id + source_file.
    assert graphdb._AGE_INDEXED_NODE_PROPS == ("id", "source_file")


def test_age_batches_chunks_correctly():
    rows = [{"id": i} for i in range(1201)]
    batches = list(graphdb._age_batches(rows, size=500))
    assert len(batches) == 3
    assert [len(b) for b in batches] == [500, 500, 201]
    assert sum(len(b) for b in batches) == len(rows)


# ---------------------------------------------------------------------------
# Phase 3: incremental sync -- narrowing full-graph row groups down to a
# graph_diff()-shaped diff, and computing deletions from the diff alone.
# ---------------------------------------------------------------------------

def test_age_diff_filter_keeps_only_new_and_changed_nodes():
    node_groups = {
        "Code": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
    }
    diff = {
        "new_nodes": [{"id": "c", "label": "C"}],
        "changed_nodes": [{"id": "a", "old": {}, "new": {}}],
        "removed_nodes": [],
        "new_edges": [], "removed_edges": [], "changed_edges": [],
    }
    filtered_nodes, filtered_edges, stale_by_label, stale_edges = (
        graphdb._age_diff_filter(node_groups, {}, diff)
    )
    assert {r["id"] for r in filtered_nodes["Code"]} == {"a", "c"}
    assert filtered_edges == {}
    assert stale_by_label == {}
    assert stale_edges == {}


def test_age_diff_filter_drops_label_with_no_changed_rows():
    node_groups = {"Code": [{"id": "a"}], "Doc": [{"id": "b"}]}
    diff = {
        "new_nodes": [{"id": "a", "label": "A"}],
        "changed_nodes": [], "removed_nodes": [],
        "new_edges": [], "removed_edges": [], "changed_edges": [],
    }
    filtered_nodes, _, _, _ = graphdb._age_diff_filter(node_groups, {}, diff)
    assert "Doc" not in filtered_nodes
    assert list(filtered_nodes.keys()) == ["Code"]


def test_age_diff_filter_computes_stale_nodes_from_removed_nodes():
    diff = {
        "new_nodes": [], "changed_nodes": [],
        "removed_nodes": [{"id": "x", "label": "X", "properties": {"file_type": "code"}}],
        "new_edges": [], "removed_edges": [], "changed_edges": [],
    }
    _, _, stale_by_label, _ = graphdb._age_diff_filter({}, {}, diff)
    assert stale_by_label == {"Code": ["x"]}


def test_age_diff_filter_deletes_old_label_on_relabel():
    """A node whose file_type changed must be deleted under its *old* AGE
    label -- the new-label row is created via the normal upsert path since
    it's already in changed_nodes."""
    diff = {
        "new_nodes": [], "removed_nodes": [],
        "changed_nodes": [{
            "id": "x",
            "old": {"file_type": "code"},
            "new": {"file_type": "document"},
        }],
        "new_edges": [], "removed_edges": [], "changed_edges": [],
    }
    _, _, stale_by_label, _ = graphdb._age_diff_filter({}, {}, diff)
    assert stale_by_label == {"Code": ["x"]}


def test_age_diff_filter_no_relabel_produces_no_stale_entry():
    diff = {
        "new_nodes": [], "removed_nodes": [],
        "changed_nodes": [{
            "id": "x",
            "old": {"file_type": "code"},
            "new": {"file_type": "code"},
        }],
        "new_edges": [], "removed_edges": [], "changed_edges": [],
    }
    _, _, stale_by_label, _ = graphdb._age_diff_filter({}, {}, diff)
    assert stale_by_label == {}


def test_age_diff_filter_keeps_only_new_and_changed_edges():
    edge_groups = {"CALLS": [{"src": "a", "tgt": "b"}, {"src": "b", "tgt": "c"}]}
    diff = {
        "new_nodes": [], "removed_nodes": [], "changed_nodes": [],
        "new_edges": [{"source": "a", "target": "b", "relation": "CALLS"}],
        "removed_edges": [], "changed_edges": [],
    }
    _, filtered_edges, _, _ = graphdb._age_diff_filter({}, edge_groups, diff)
    assert filtered_edges == {"CALLS": [{"src": "a", "tgt": "b"}]}


def test_age_diff_filter_keeps_new_edges_with_raw_lowercase_relation():
    """Regression: edge_groups is keyed by _safe_rel()'s sanitized relation
    (e.g. "calls" -> "CALLS"), but graph_diff()'s "relation" field is the
    raw string -- comparing them unnormalized silently dropped every
    changed/new edge for a normal lowercase relation (found via review)."""
    edge_groups = {"CALLS": [{"src": "a", "tgt": "b"}]}
    diff = {
        "new_nodes": [], "removed_nodes": [], "changed_nodes": [],
        "new_edges": [{"source": "a", "target": "b", "relation": "calls"}],
        "removed_edges": [], "changed_edges": [],
    }
    _, filtered_edges, _, _ = graphdb._age_diff_filter({}, edge_groups, diff)
    assert filtered_edges == {"CALLS": [{"src": "a", "tgt": "b"}]}


def test_age_diff_filter_restores_edges_incident_to_a_relabeled_node():
    """Regression: a changed node whose file_type changed is deleted (under
    its old label) via DETACH DELETE, which also removes every edge
    incident to it -- but graph_diff() doesn't mark those edges "changed"
    just because an endpoint relabeled, so they'd never come back without
    explicit handling (found via review)."""
    edge_groups = {
        "CALLS": [{"src": "a", "tgt": "b"}, {"src": "c", "tgt": "d"}],
    }
    diff = {
        "new_nodes": [], "removed_nodes": [],
        "changed_nodes": [{"id": "a", "old": {"file_type": "code"}, "new": {"file_type": "doc"}}],
        "new_edges": [], "removed_edges": [], "changed_edges": [],
    }
    _, filtered_edges, stale_by_label, _ = graphdb._age_diff_filter({}, edge_groups, diff)
    # The edge touching the relabeled node "a" must be re-included for
    # upsert even though it's otherwise unchanged; the unrelated c->d edge
    # must not be.
    assert filtered_edges == {"CALLS": [{"src": "a", "tgt": "b"}]}
    assert stale_by_label == {"Code": ["a"]}


def test_age_diff_filter_computes_stale_edges_from_removed_edges():
    diff = {
        "new_nodes": [], "removed_nodes": [], "changed_nodes": [],
        "new_edges": [], "changed_edges": [],
        "removed_edges": [{"source": "a", "target": "b", "relation": "calls"}],
    }
    _, _, _, stale_edges = graphdb._age_diff_filter({}, {}, diff)
    assert stale_edges == {"CALLS": [("a", "b")]}


def test_push_to_age_diff_mode_skips_live_state_read(monkeypatch):
    """With a diff supplied, push_to_age() must never issue the
    read-existing-AGE-state queries (MATCH (n) / MATCH (a)-[r]->(b)) --
    that's the whole point of incremental sync."""
    executed: list[str] = []

    class _FakeCursor:
        def execute(self, query, params=None):
            text = query if isinstance(query, str) else str(getattr(query, "as_string", lambda c: query)(None))
            executed.append(text)

        def fetchone(self):
            return (1,)  # graph already exists

        def fetchall(self):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    import sys
    import types

    fake_psycopg = types.ModuleType("psycopg")
    fake_psycopg.connect = lambda *a, **k: _FakeConn()
    fake_sql_mod = types.ModuleType("psycopg.sql")

    class _Literal:
        def __init__(self, v):
            self.v = v

        def as_string(self, ctx):
            return repr(self.v)

    class _Identifier:
        def __init__(self, *parts):
            self.v = ".".join(parts)

        def as_string(self, ctx):
            return '"' + '"."'.join(self.v.split(".")) + '"'

    class _SQL:
        def __init__(self, s):
            self.s = s.s if isinstance(s, _SQL) else s

        def format(self, **kwargs):
            rendered = {}
            for k, v in kwargs.items():
                if isinstance(v, _SQL):
                    rendered[k] = v.s
                elif isinstance(v, _Literal):
                    rendered[k] = repr(v.v)
                else:
                    rendered[k] = str(v)
            return _SQL(self.s.format(**rendered))

        def as_string(self, ctx):
            return self.s

    fake_sql_mod.Literal = _Literal
    fake_sql_mod.Identifier = _Identifier
    fake_sql_mod.SQL = _SQL
    fake_sql_mod.Composed = _SQL
    fake_psycopg.sql = fake_sql_mod
    fake_psycopg.errors = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
    monkeypatch.setitem(sys.modules, "psycopg.sql", fake_sql_mod)

    G = _graph(
        [("a", {"file_type": "code", "label": "A"}), ("b", {"file_type": "code", "label": "B"})],
        [("a", "b", {"relation": "calls", "confidence": "EXTRACTED"})],
    )
    diff = {
        "new_nodes": [{"id": "a", "label": "A", "properties": {"file_type": "code"}}],
        "changed_nodes": [], "removed_nodes": [],
        "new_edges": [], "removed_edges": [], "changed_edges": [],
    }
    graphdb.push_to_age(G, conninfo="host=localhost", diff=diff)
    assert not any("MATCH (n)" in q or "MATCH (a)-[r]->(b)" in q for q in executed)


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
