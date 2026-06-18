"""Regression tests for GraphStore edge-direction and seed-resolution semantics
surfaced by the PR #1379 review."""
from __future__ import annotations

import json

from graphify import affected as aff
from graphify.serve import _import_graph_json_into_store


def test_edge_attr_lookup_prefers_forward_direction(store):
    """With reciprocal directed edges, ``G[u][v]`` must report the u->v edge's
    attributes, not an arbitrary direction (regression: undirected ``-[r]-``
    returned the reverse edge's relation)."""
    store.add_nodes_from([("a", {"label": "A"}), ("b", {"label": "B"})])
    store.add_edges_from([("a", "b", {"relation": "ab"}), ("b", "a", {"relation": "ba"})])
    assert store["a"]["b"]["relation"] == "ab"
    assert store["b"]["a"]["relation"] == "ba"


def test_edge_attr_lookup_falls_back_to_reverse(store):
    """A single v->u edge is still found when queried as (u, v): the undirected
    graph model must not lose connectivity just because direction is preferred."""
    store.add_nodes_from([("a", {"label": "A"}), ("b", {"label": "B"})])
    store.add_edges_from([("b", "a", {"relation": "ba"})])
    assert store["a"]["b"]["relation"] == "ba"


def test_remove_edges_is_directed(store):
    """Removing (u, v) must delete only the u->v edge, not a reciprocal v->u
    edge (regression: undirected delete nuked both directions, over-pruning
    edges whose own source_file was not deleted)."""
    store.add_nodes_from([("a", {"label": "A"}), ("b", {"label": "B"})])
    store.add_edges_from([("a", "b", {"relation": "ab"}), ("b", "a", {"relation": "ba"})])
    store.remove_edges([("a", "b")])
    remaining = sorted((u, v, d.get("relation")) for u, v, d in store.edges(data=True))
    assert remaining == [("b", "a", "ba")]


def test_traverse_keeps_all_same_level_parent_edges(store):
    """A node reached from multiple parents in the same BFS level must keep an
    edge from EVERY parent (regression: marking visited mid-level dropped all but
    the first, thinning ~⅓ of edges in the subgraph `query` shows the user).

    Diamond: A->B, A->C, B->D, C->D ; from A at depth 2 both B->D and C->D survive.
    """
    store.add_nodes_from([(x, {"label": x}) for x in "ABCD"])
    store.add_edges_from([("A", "B", {}), ("A", "C", {}), ("B", "D", {}), ("C", "D", {})])
    visited, edges = store._traverse(["A"], depth=2, hub_threshold=10 ** 9)
    assert set(visited) == set("ABCD")
    und = {frozenset((u, v)) for u, v in edges}
    assert frozenset(("B", "D")) in und
    assert frozenset(("C", "D")) in und
    assert len(edges) == 4


def test_traverse_dedups_parallel_edges(store):
    """Parallel edges between the same pair must not double-count in the walk."""
    store.add_nodes_from([("A", {"label": "A"}), ("B", {"label": "B"})])
    store.add_edges_from([("A", "B", {"relation": "r1"}), ("A", "B", {"relation": "r2"})])
    _visited, edges = store._traverse(["A"], depth=1, hub_threshold=10 ** 9)
    assert edges == [("A", "B")]


def test_resolve_seed_native_bare_name(store):
    """`affected foo` must resolve to a uniquely-matching callable node ``foo()``
    on the native store path, matching the in-memory _bare_name tier."""
    store.add_nodes_from([("n1", {"label": "foo()"}), ("n2", {"label": "fooExtra()"})])
    assert aff.resolve_seed(store, "foo") == "n1"


def test_legacy_graph_json_imports_into_empty_store(store, tmp_path):
    """A node-link graph.json (pre-FalkorDB project / --no-cluster output) must
    import into an empty store so it stays queryable without a rebuild."""
    gj = tmp_path / "graph.json"
    gj.write_text(json.dumps({
        "nodes": [{"id": "a", "label": "A", "source_file": "a.py"},
                  {"id": "b", "label": "B", "source_file": "b.py"}],
        "links": [{"source": "a", "target": "b", "relation": "calls"}],
    }))
    assert store.number_of_nodes() == 0
    assert _import_graph_json_into_store(gj, store) is True
    assert store.number_of_nodes() == 2
    assert store.number_of_edges() == 1
    # Missing / empty JSON is a no-op, not an error.
    assert _import_graph_json_into_store(tmp_path / "missing.json", store) is False
