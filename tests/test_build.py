"""Transient DTO construction and native incremental merge tests."""

from graphify.build import (
    build,
    build_from_extraction,
    build_merge,
    build_unclustered_extraction,
    dedupe_edges,
    dedupe_nodes,
)


def _attrs(graph, node_id):
    return next(node.attributes for node in graph.nodes if node.id == node_id)


def _edge(graph, source, target, relation=None):
    return next(
        edge for edge in graph.edges
        if edge.source == source
        and edge.target == target
        and (relation is None or edge.attributes.get("relation") == relation)
    )


def test_dedupe_records_are_deterministic():
    nodes = [{"id": "a", "label": "old"}, {"id": "b"}, {"id": "a", "label": "new"}]
    assert dedupe_nodes(nodes) == [{"id": "a", "label": "new"}, {"id": "b"}]
    edges = [
        {"source": "a", "target": "b", "relation": "calls", "source_location": "L1"},
        {"source": "a", "target": "b", "relation": "calls", "source_location": "L2"},
        {"source": "a", "target": "b", "relation": "imports"},
    ]
    assert dedupe_edges(edges) == [edges[0], edges[2]]


def test_build_normalizes_attributes_weights_and_direction():
    graph = build_from_extraction({
        "nodes": [
            {"id": "a", "label": "A", "source": "src\\a.py", "file_type": None, "_origin": "ast"},
            {"id": "b", "label": "B", "source_file": "src/b.py", "file_type": "code", "_origin": "ast"},
        ],
        "edges": [
            {"from": "a", "to": "b", "relation": "calls", "weight": None,
             "confidence_score": None},
        ],
    }, directed=True)
    assert graph.kind == "digraph"
    assert graph.node_count == 2 and graph.edge_count == 1
    assert _attrs(graph, "a")["source_file"] == "src/a.py"
    assert _attrs(graph, "a")["file_type"] == "concept"
    assert _edge(graph, "a", "b").attributes["weight"] == 1.0
    assert _edge(graph, "a", "b").attributes["confidence_score"] == 1.0


def test_build_merges_last_node_attributes_and_backfills_edge_source():
    graph = build([
        {"nodes": [{"id": "a", "label": "Old", "source_file": "a.py"}], "edges": []},
        {
            "nodes": [
                {"id": "a", "label": "New", "source_file": "a.py"},
                {"id": "b", "label": "B", "source_file": "b.py"},
            ],
            "edges": [{"source": "a", "target": "b", "relation": "references"}],
        },
    ], dedup=False)
    assert _attrs(graph, "a")["label"] == "New"
    assert _edge(graph, "a", "b").attributes["source_file"] == "a.py"


def test_ghost_merge_uses_source_file_not_basename():
    graph = build_from_extraction({
        "nodes": [
            {
                "id": "a_render",
                "label": "render",
                "file_type": "code",
                "source_file": "src/a/index.ts",
                "source_location": "L10",
                "_origin": "ast",
            },
            {
                "id": "b_render",
                "label": "render",
                "file_type": "code",
                "source_file": "src/b/index.ts",
                "source_location": "L20",
                "_origin": "ast",
            },
            {
                "id": "ghost_render",
                "label": "render",
                "file_type": "code",
                "source_file": "src/a/index.ts",
            },
            {
                "id": "caller",
                "label": "main",
                "file_type": "code",
                "source_file": "src/main.ts",
                "source_location": "L1",
                "_origin": "ast",
            },
        ],
        "edges": [{
            "source": "caller",
            "target": "ghost_render",
            "relation": "calls",
            "confidence": "EXTRACTED",
            "source_file": "src/main.ts",
        }],
    })

    node_ids = {node.id for node in graph.nodes}
    assert "ghost_render" not in node_ids
    assert "b_render" in node_ids
    assert _edge(graph, "caller", "a_render")
    assert not any(
        edge.source == "caller" and edge.target == "b_render"
        for edge in graph.edges
    )


def test_ghost_merge_not_across_directories_same_basename():
    graph = build_from_extraction({
        "nodes": [
            {
                "id": "docs_a_index",
                "label": "Quickstart",
                "file_type": "document",
                "source_file": "docs/product_a/index.md",
                "source_location": "L1",
            },
            {
                "id": "docs_b_index",
                "label": "Quickstart",
                "file_type": "document",
                "source_file": "docs/product_b/index.md",
            },
            {
                "id": "docs_hub",
                "label": "Docs",
                "file_type": "concept",
                "source_file": "docs/hub.md",
                "source_location": "L1",
            },
        ],
        "edges": [{
            "source": "docs_hub",
            "target": "docs_b_index",
            "relation": "links_to",
            "confidence": "INFERRED",
            "source_file": "docs/hub.md",
        }],
    })

    assert {node.id for node in graph.nodes} >= {
        "docs_a_index",
        "docs_b_index",
    }
    assert _edge(graph, "docs_hub", "docs_b_index")
    assert not any(
        edge.source == "docs_hub" and edge.target == "docs_a_index"
        for edge in graph.edges
    )


def test_parallel_relations_and_self_loop_survive():
    graph = build_from_extraction({
        "directed": True,
        "multigraph": True,
        "nodes": [{"id": "a"}, {"id": "b"}],
        "links": [
            {"source": "a", "target": "b", "key": "call", "relation": "calls"},
            {"source": "a", "target": "b", "key": "use", "relation": "uses"},
            {"source": "a", "target": "a", "key": "self", "relation": "recursive"},
        ],
    })
    assert graph.kind == "multidigraph"
    assert graph.edge_count == 3
    assert {edge.key for edge in graph.edges} == {"call", "use", "self"}


def test_unclustered_build_preserves_parallel_and_external_edges():
    graph = build_unclustered_extraction({
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [
            {"source": "a", "target": "b", "relation": "calls"},
            {"source": "a", "target": "b", "relation": "imports"},
            {"source": "b", "target": "a", "relation": "calls"},
            {"source": "a", "target": "external", "relation": "imports"},
            {"source": "a", "target": "b", "relation": "calls"},
        ],
    })

    assert graph.kind == "multigraph"
    assert {node.id for node in graph.nodes} == {"a", "b", "external"}
    assert graph.edge_count == 4
    assert [edge.key for edge in graph.edges[:3]] == [0, 1, 2]
    assert {
        (edge.source, edge.target, edge.attributes["relation"])
        for edge in graph.edges
    } == {
        ("a", "b", "calls"),
        ("a", "b", "imports"),
        ("b", "a", "calls"),
        ("a", "external", "imports"),
    }


def test_hyperedges_prune_dangling_members():
    graph = build_from_extraction({
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [],
        "hyperedges": [
            {"id": "flow", "nodes": ["a", "missing", "b"], "source_file": "flow.md"},
            {"id": "gone", "nodes": ["missing"]},
        ],
    })
    assert graph.attributes["hyperedges"] == [
        {"id": "flow", "nodes": ["a", "b"], "source_file": "flow.md"}
    ]


def test_incremental_merge_replaces_changed_and_prunes_deleted(tmp_path):
    store_path = tmp_path / "graph.helix"
    initial = build_from_extraction({
        "nodes": [
            {"id": "a", "label": "Old", "source_file": "a.py", "_origin": "ast"},
            {"id": "stale", "label": "Stale", "source_file": "a.py", "_origin": "ast"},
            {"id": "b", "label": "B", "source_file": "b.py", "_origin": "ast"},
        ],
        "edges": [
            {"source": "a", "target": "b", "relation": "calls", "source_file": "a.py", "_origin": "ast"},
            {"source": "stale", "target": "b", "relation": "calls", "source_file": "a.py", "_origin": "ast"},
        ],
        "hyperedges": [{"id": "b-flow", "nodes": ["b"], "source_file": "b.py"}],
    }, directed=True)
    merged = build_merge([
        {"nodes": [{"id": "a", "label": "New", "source_file": "a.py", "_origin": "ast"}], "edges": []}
    ], graph_path=store_path, base_graph=initial, prune_sources=["b.py"], directed=True, dedup=False)
    assert {node.id for node in merged.nodes} == {"a"}
    assert _attrs(merged, "a")["label"] == "New"
    assert merged.edge_count == 0
    assert merged.attributes.get("hyperedges", []) == []


def test_typed_identifiers_remain_distinct():
    graph = build_from_extraction({
        "nodes": [{"id": 1, "label": "integer"}, {"id": "1", "label": "string"}],
        "edges": [{"source": 1, "target": "1", "relation": "links"}],
    })
    assert {node.id for node in graph.nodes} == {1, "1"}
