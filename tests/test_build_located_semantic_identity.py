import json

import pytest

from graphify.build import build, build_from_json, build_merge


def _located_nodes():
    return [
        {"id": "pkg_name", "label": "name", "file_type": "code",
         "source_file": "pkg/plugin.json", "source_location": "L2"},
        {"id": "pkg_author_name", "label": "name", "file_type": "code",
         "source_file": "pkg/plugin.json", "source_location": "L5"},
        {"id": "doc_s1_notes", "label": "Notas", "file_type": "document",
         "source_file": "docs/plan.md", "source_location": "L10"},
        {"id": "doc_s2_notes", "label": "Notas", "file_type": "document",
         "source_file": "docs/plan.md", "source_location": "L80"},
        {"id": "other_name", "label": "name", "file_type": "code",
         "source_file": "pkg/other.json", "source_location": "L2"},
    ]


@pytest.mark.parametrize("reverse", [False, True])
def test_distinct_same_file_locations_preserve_ids_and_edges(reverse):
    nodes = _located_nodes()
    if reverse:
        nodes.reverse()
    graph = build_from_json({
        "nodes": nodes,
        "edges": [
            {"source": "pkg_name", "target": "doc_s1_notes", "relation": "references"},
            {"source": "pkg_author_name", "target": "doc_s2_notes", "relation": "references"},
        ],
        "hyperedges": [],
    }, dedup=False)
    assert set(graph.nodes) == {node["id"] for node in nodes}
    assert graph.has_edge("pkg_name", "doc_s1_notes")
    assert graph.has_edge("pkg_author_name", "doc_s2_notes")


def test_empty_no_dedup_merge_keeps_located_graph(tmp_path):
    nodes = _located_nodes()
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps({"nodes": nodes, "edges": [], "hyperedges": []}), encoding="utf-8")
    graph = build_merge([{"nodes": [], "edges": [], "hyperedges": []}], graph_path, dedup=False)
    assert set(graph.nodes) == {node["id"] for node in nodes}


def test_disabled_dedup_keeps_distinct_semantic_ids_at_identical_locations():
    nodes = [
        {"id": name, "label": "Notes", "file_type": "document", "_origin": "semantic",
         "source_file": "plan.md", "source_location": location}
        for name, location in [("a_first", "L2"), ("b_second", "L5"), ("z_first", "L2"), ("z_second", "L5")]
    ]
    graph = build_from_json({
        "nodes": nodes,
        "edges": [{"source": "z_first", "target": "z_second", "relation": "references"}],
        "hyperedges": [],
    }, dedup=False)
    assert set(graph.nodes) == {node["id"] for node in nodes}
    assert graph.has_edge("z_first", "z_second")


def test_ast_twin_remains_canonical_despite_semantic_location_drift():
    graph = build_from_json({
        "nodes": [
            {"id": "src_render", "label": "render", "file_type": "code", "_origin": "ast",
             "source_file": "src/view.py", "source_location": "L2"},
            {"id": "view_render", "label": "render", "file_type": "code", "_origin": "semantic",
             "source_file": "src/view.py", "source_location": "L5"},
        ],
        "edges": [], "hyperedges": [],
    }, dedup=False)
    assert set(graph.nodes) == {"src_render"}


def test_full_build_honors_disabled_semantic_dedup():
    nodes = _located_nodes()
    graph = build([{"nodes": nodes, "edges": [], "hyperedges": []}], dedup=False)
    assert set(graph.nodes) == {node["id"] for node in nodes}


def test_fresh_merge_honors_disabled_semantic_dedup(tmp_path):
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps({"nodes": [], "edges": [], "hyperedges": []}), encoding="utf-8")
    nodes = _located_nodes()
    graph = build_merge([{"nodes": nodes, "edges": [], "hyperedges": []}], graph_path, dedup=False)
    assert set(graph.nodes) == {node["id"] for node in nodes}
