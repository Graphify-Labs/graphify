"""Retained build regressions adapted to transient DTOs and native snapshots."""
from __future__ import annotations

import json
from pathlib import Path

from graphify.build import (
    _semantic_id_remap,
    build,
    build_from_extraction,
    build_merge,
    dedupe_edges,
    dedupe_nodes,
    edge_data,
    edge_datas,
    graph_has_legacy_ids,
)
from graphify.cluster import cluster
from tests.native_helpers import graph_from_build, graph_from_payload

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _attrs(data, node_id):
    return next(node.attributes for node in data.nodes if node.id == node_id)


def _edge(data, source, target, relation=None):
    return next(
        edge for edge in data.edges
        if edge.source == source and edge.target == target
        and (relation is None or edge.attributes.get("relation") == relation)
    )


def _has_edge(data, source, target):
    return any(edge.source == source and edge.target == target for edge in data.edges)


def _ids(data):
    return {node.id for node in data.nodes}


def load_extraction():
    return json.loads((FIXTURES / "extraction.json").read_text())


def test_dedupe_edges_collapses_exact_parallels():
    edges = [
        {"source": "a", "target": "b", "relation": "calls", "source_location": "L1"},
        {"source": "a", "target": "b", "relation": "calls", "source_location": "L9"},
        {"source": "a", "target": "b", "relation": "imports"},
        {"source": "b", "target": "c", "relation": "calls"},
    ]
    out = dedupe_edges(edges)
    assert [(e["source"], e["target"], e["relation"]) for e in out] == [
        ("a", "b", "calls"), ("a", "b", "imports"), ("b", "c", "calls")
    ]
    assert out[0]["source_location"] == "L1"


def test_dedupe_edges_is_idempotent():
    edges = [{"source": "a", "target": "b", "relation": "calls"}] * 2
    once = dedupe_edges(edges)
    assert len(once) == len(dedupe_edges(once + edges)) == 1


def test_dedupe_nodes_collapses_by_id_last_wins():
    nodes = [
        {"id": "foundation", "source_file": "A.swift"},
        {"id": "akit"},
        {"id": "foundation", "source_file": "B.swift"},
    ]
    out = dedupe_nodes(nodes)
    assert [node["id"] for node in out] == ["foundation", "akit"]
    assert out[0]["source_file"] == "B.swift"


def test_build_from_json_node_count():
    assert build_from_extraction(load_extraction()).node_count == 4


def test_build_from_json_edge_count():
    assert build_from_extraction(load_extraction()).edge_count == 4


def test_null_weight_edge_builds_and_clusters(tmp_path):
    data = build_from_extraction({
        "nodes": [{"id": item, "label": item, "source_file": f"{item}.py"} for item in "abc"],
        "edges": [
            {"source": "a", "target": "b", "relation": "references", "weight": None, "confidence_score": None},
            {"source": "b", "target": "c", "relation": "references", "weight": 2.5},
        ],
    })
    assert _edge(data, "a", "b").attributes["weight"] == 1.0
    assert _edge(data, "a", "b").attributes["confidence_score"] == 1.0
    assert _edge(data, "b", "c").attributes["weight"] == 2.5
    cluster(graph_from_build(data))


def test_malformed_weights_normalize():
    data = build_from_extraction({
        "nodes": [{"id": f"n{i}", "source_file": f"{i}.py"} for i in range(4)],
        "edges": [
            {"source": "n0", "target": "n1", "weight": "3.5"},
            {"source": "n1", "target": "n2", "weight": float("nan")},
            {"source": "n2", "target": "n3", "weight": -4},
        ],
    })
    assert [_edge(data, f"n{i}", f"n{i+1}").attributes["weight"] for i in range(3)] == [3.5, 1.0, 1.0]


def test_nodes_have_label():
    assert _attrs(build_from_extraction(load_extraction()), "n_transformer")["label"] == "Transformer"


def test_edges_have_confidence():
    data = build_from_extraction(load_extraction())
    assert _edge(data, "n_attention", "n_concept_attn").attributes["confidence"] == "INFERRED"


def test_ambiguous_edge_preserved():
    data = build_from_extraction(load_extraction())
    assert _edge(data, "n_layernorm", "n_concept_attn").attributes["confidence"] == "AMBIGUOUS"


def test_legacy_node_source_canonicalized():
    data = build_from_extraction({"nodes": [{"id": "n1", "source": "a.py"}], "edges": []})
    assert _attrs(data, "n1")["source_file"] == "a.py"
    assert "source" not in _attrs(data, "n1")


def test_legacy_edge_from_to_canonicalized():
    data = build_from_extraction({
        "nodes": [{"id": "n1"}, {"id": "n2"}],
        "edges": [{"from": "n1", "to": "n2", "relation": "calls"}],
    })
    assert data.edge_count == 1


def test_source_file_backslash_normalized():
    data = build_from_extraction({
        "nodes": [
            {"id": "n1", "source_file": r"src\middleware\auth.py"},
            {"id": "n2", "source_file": "src/middleware/auth.py"},
        ],
        "edges": [],
    })
    assert {_attrs(data, node)["source_file"] for node in _ids(data)} == {"src/middleware/auth.py"}


def test_edge_missing_source_file_backfilled_from_node():
    data = build_from_extraction({
        "nodes": [{"id": "n1", "source_file": "docs/a.md"}, {"id": "n2", "source_file": "docs/b.md"}],
        "edges": [{"source": "n1", "target": "n2", "relation": "relates_to"}],
    })
    assert _edge(data, "n1", "n2").attributes["source_file"] == "docs/a.md"


def test_build_merges_multiple_extractions():
    data = build([
        {"nodes": [{"id": "n1", "source_file": "a.py"}], "edges": []},
        {"nodes": [{"id": "n2", "source_file": "b.md"}], "edges": [{"source": "n1", "target": "n2"}]},
    ])
    assert data.node_count == 2 and data.edge_count == 1


def test_none_file_type_defaults_to_concept(capsys):
    data = build_from_extraction({"nodes": [{"id": "n1", "file_type": None}], "edges": []})
    assert _attrs(data, "n1")["file_type"] == "concept"
    assert "invalid file_type" not in capsys.readouterr().err


def test_missing_file_type_defaults_to_concept(capsys):
    data = build_from_extraction({"nodes": [{"id": "n1"}], "edges": []})
    assert _attrs(data, "n1")["file_type"] == "concept"
    assert "invalid file_type" not in capsys.readouterr().err


def test_real_invalid_file_type_coerced_to_concept():
    data = build_from_extraction({"nodes": [{"id": "n1", "file_type": "weird_type"}], "edges": []})
    assert _attrs(data, "n1")["file_type"] == "concept"


def test_file_type_synonym_mapping():
    data = build_from_extraction({
        "nodes": [
            {"id": "n1", "file_type": "markdown"},
            {"id": "n2", "file_type": "tool"},
            {"id": "n3", "file_type": "pattern"},
        ],
        "edges": [],
    })
    assert [_attrs(data, node)["file_type"] for node in ("n1", "n2", "n3")] == ["document", "code", "concept"]


def _ghost_nodes(two_ast=False, same_file=False):
    nodes = [
        {"id": "ast_render", "label": "render", "source_file": "src/a/index.ts", "source_location": "L10", "_origin": "ast"},
        {"id": "ghost_render", "label": "render", "source_file": "src/a/index.ts", "source_location": "L11"},
        {"id": "caller", "label": "main", "source_file": "src/main.ts", "source_location": "L1", "_origin": "ast"},
    ]
    if two_ast:
        nodes.append({"id": "other_render", "label": "render", "source_file": "src/b/index.ts", "source_location": "L20", "_origin": "ast"})
    if same_file:
        nodes = [
            {"id": "a_foo", "label": "Foo", "source_file": "x/doc.md", "source_location": "L1"},
            {"id": "b_foo", "label": "Foo", "source_file": "x/doc.md", "source_location": "L2"},
        ]
    return nodes


def test_ghost_merge_unique_located_node_still_merges():
    data = build_from_extraction({
        "nodes": _ghost_nodes(),
        "edges": [{"source": "caller", "target": "ghost_render", "relation": "calls"}],
    })
    assert "ghost_render" not in _ids(data)
    assert _has_edge(data, "caller", "ast_render")


def test_ghost_merge_uses_full_path_despite_basename_collision():
    data = build_from_extraction({
        "nodes": _ghost_nodes(two_ast=True),
        "edges": [{"source": "caller", "target": "ghost_render", "relation": "calls"}],
    })
    assert "ghost_render" not in _ids(data)
    assert "other_render" in _ids(data)
    assert _has_edge(data, "caller", "ast_render")
    assert not _has_edge(data, "caller", "other_render")


def test_ghost_merge_non_ast_different_files_both_survive():
    data = build_from_extraction({
        "nodes": [
            {"id": "a", "label": "build_merge() function", "source_file": "dir_a/update.md", "source_location": "L10"},
            {"id": "b", "label": "build_merge() function", "source_file": "dir_b/update.md", "source_location": "L12"},
        ],
        "edges": [],
    })
    assert _ids(data) == {"a", "b"}


def test_ghost_merge_non_ast_same_file_still_merges():
    assert build_from_extraction({"nodes": _ghost_nodes(same_file=True), "edges": []}).node_count == 1


def test_build_merge_preserves_call_edge_direction(tmp_path):
    from graphify.extract import extract_js

    source = tmp_path / "x.js"
    source.write_text("function b() {}\nfunction a() { b(); }\n")
    extraction = extract_js(source)
    initial = build([extraction], dedup=False)
    call = next(edge for edge in initial.edges if edge.attributes.get("relation") == "calls")
    merged = build_merge([], tmp_path / "graph.helix", base_graph=initial, dedup=False)
    retained = next(edge for edge in merged.edges if edge.attributes.get("relation") == "calls")
    assert (retained.source, retained.target) == (call.source, call.target)


def test_build_from_json_preserves_first_direction_on_bidirectional_pair(tmp_path):
    data = build_from_extraction({
        "nodes": [{"id": "a_handler"}, {"id": "z_emitter"}],
        "edges": [
            {"source": "a_handler", "target": "z_emitter", "relation": "calls"},
            {"source": "z_emitter", "target": "a_handler", "relation": "calls"},
        ],
    })
    assert data.edge_count == 1
    assert (data.edges[0].source, data.edges[0].target) == ("a_handler", "z_emitter")


def test_edge_data_simple_graph():
    graph = graph_from_payload([{"id": "a"}, {"id": "b"}], [{"source": "a", "target": "b", "relation": "calls"}])
    assert edge_data(graph, "a", "b")["relation"] == "calls"


def test_edge_datas_simple_graph_returns_singleton_list():
    graph = graph_from_payload([{"id": "a"}, {"id": "b"}], [{"source": "a", "target": "b", "relation": "calls"}])
    assert len(edge_datas(graph, "a", "b")) == 1


def test_edge_data_multigraph_with_parallel_edges():
    graph = graph_from_payload(
        [{"id": "a"}, {"id": "b"}],
        [{"source": "a", "target": "b", "key": "one", "relation": "calls"}, {"source": "a", "target": "b", "key": "two", "relation": "uses"}],
        kind="multigraph",
    )
    assert edge_data(graph, "a", "b")["relation"] in {"calls", "uses"}


def test_edge_datas_multigraph_returns_all_parallel_edges():
    graph = graph_from_payload(
        [{"id": "a"}, {"id": "b"}],
        [{"source": "a", "target": "b", "key": "one", "relation": "calls"}, {"source": "a", "target": "b", "key": "two", "relation": "uses"}],
        kind="multigraph",
    )
    assert {row["relation"] for row in edge_datas(graph, "a", "b")} == {"calls", "uses"}


def test_edge_data_multidigraph():
    graph = graph_from_payload([{"id": "a"}, {"id": "b"}], [{"source": "a", "target": "b", "key": 0, "relation": "calls"}], kind="multidigraph")
    assert edge_data(graph, "a", "b")["relation"] == "calls"


def test_edge_data_node_link_multigraph_roundtrip():
    data = build_from_extraction({
        "directed": True,
        "multigraph": True,
        "nodes": [{"id": "a"}, {"id": "b"}],
        "links": [{"source": "a", "target": "b", "key": 4, "relation": "calls"}],
    })
    graph = graph_from_build(data)
    assert edge_datas(graph, "a", "b")[0]["relation"] == "calls"


def test_build_from_json_relativizes_absolute_source_file(tmp_path):
    root = tmp_path / "repo"
    path = root / "src" / "a.py"
    data = build_from_extraction({"nodes": [{"id": "a", "source_file": str(path)}], "edges": []}, root=root)
    assert _attrs(data, "src_a")["source_file"] == "src/a.py"


def test_build_relativizes_absolute_source_file(tmp_path):
    root = tmp_path / "repo"
    data = build([{"nodes": [{"id": "a", "source_file": str(root / "src/a.py")}], "edges": []}], root=root)
    assert next(iter(data.nodes)).attributes["source_file"] == "src/a.py"


def test_build_from_json_ambiguous_old_stem_alias_stays_dangling(tmp_path):
    data = build_from_extraction({
        "nodes": [
            {"id": "a_utility", "label": "utility.h", "source_file": "A/utility.h"},
            {"id": "b_utility", "label": "utility.h", "source_file": "B/utility.h"},
            {"id": "server", "label": "server", "source_file": "server.cpp"},
        ],
        "edges": [{"source": "server", "target": "utility", "relation": "imports"}],
    }, root=tmp_path)
    assert data.edge_count == 0


def test_build_from_json_ambiguous_alias_detected_despite_header_impl_salting(tmp_path):
    data = build_from_extraction({
        "nodes": [
            {"id": "a_utility_h", "label": "utility.h", "source_file": "A/utility.h"},
            {"id": "b_utility_h", "label": "utility.h", "source_file": "B/utility.h"},
            {"id": "server", "source_file": "server.cpp"},
        ],
        "edges": [{"source": "server", "target": "utility", "relation": "imports"}],
    }, root=tmp_path)
    assert data.edge_count == 0


def test_build_from_json_unambiguous_old_stem_alias_still_resolves(tmp_path):
    data = build_from_extraction({
        "nodes": [
            {"id": "monitoring_utility", "label": "utility.h", "source_file": "Dev/monitoring/utility.h"},
            {"id": "server", "source_file": "Dev/poker/server.cpp"},
        ],
        "edges": [{"source": "server", "target": "utility", "relation": "imports"}],
    }, root=tmp_path)
    assert data.edge_count == 1


def test_build_from_json_relative_source_file_unchanged(tmp_path):
    data = build_from_extraction({"nodes": [{"id": "foo_bar", "label": "bar", "source_file": "src/foo.py"}], "edges": []}, root=tmp_path)
    assert next(iter(data.nodes)).attributes["source_file"] == "src/foo.py"


def _merge_base():
    return build([{
        "nodes": [
            {"id": "n1", "label": "login", "source_file": "module_a/auth.py", "_origin": "ast"},
            {"id": "n2", "label": "format_date", "source_file": "module_b/utils.py", "_origin": "ast"},
        ],
        "edges": [{"source": "n1", "target": "n2", "source_file": "module_b/utils.py", "_origin": "ast"}],
    }], dedup=False)


def test_build_merge_prune_absolute_paths_match_relative_nodes(tmp_path):
    root = tmp_path / "corpus"
    data = build_merge([], tmp_path / "graph.helix", base_graph=_merge_base(), prune_sources=[str(root / "module_b/utils.py")], root=root, dedup=False)
    assert {node.attributes.get("label") for node in data.nodes} == {"login"}
    assert data.edge_count == 0


def test_build_merge_prune_windows_backslash_paths(tmp_path):
    root = tmp_path / "corpus"
    data = build_merge([], tmp_path / "graph.helix", base_graph=_merge_base(), prune_sources=[str(root / "module_b/utils.py").replace("/", "\\")], root=root, dedup=False)
    assert "format_date" not in {node.attributes.get("label") for node in data.nodes}


def test_build_merge_replaces_changed_file_stale_edges(tmp_path):
    base = build([{
        "nodes": [{"id": "A", "source_file": "changed.md", "_origin": "ast"}, {"id": "B", "source_file": "changed.md", "_origin": "ast"}, {"id": "K", "source_file": "keep.md", "_origin": "ast"}],
        "edges": [{"source": "A", "target": "B", "source_file": "changed.md", "_origin": "ast"}, {"source": "K", "target": "A", "source_file": "keep.md", "_origin": "ast"}],
    }], dedup=False)
    fresh = {"nodes": [{"id": "A", "source_file": "changed.md", "_origin": "ast"}, {"id": "C", "source_file": "changed.md", "_origin": "ast"}], "edges": [{"source": "A", "target": "C", "source_file": "changed.md", "_origin": "ast"}]}
    data = build_merge([fresh], tmp_path / "graph.helix", base_graph=base, dedup=False, root=tmp_path)
    assert _ids(data) == {"A", "C", "K"}
    assert _has_edge(data, "A", "C") and _has_edge(data, "K", "A")


def test_build_merge_root_collapses_convention_drift(tmp_path):
    base = build([{"nodes": [{"id": "old", "source_file": "docs/wiki/overview.md", "_origin": "ast"}, {"id": "stale", "source_file": "docs/wiki/overview.md", "_origin": "ast"}], "edges": []}], dedup=False)
    fresh = {"nodes": [{"id": "new", "source_file": str(tmp_path / "docs/wiki/overview.md"), "_origin": "ast"}], "edges": []}
    data = build_merge([fresh], tmp_path / "graph.helix", base_graph=base, dedup=False, root=tmp_path)
    assert data.node_count == 1
    assert next(iter(data.nodes)).attributes["source_file"] == "docs/wiki/overview.md"


def test_build_from_json_skips_non_hashable_node_id():
    data = build_from_extraction({"nodes": [{"id": "a"}, {"id": ["x"]}, {"label": "missing"}], "edges": []})
    assert _ids(data) == {"a"}


def test_build_from_json_skips_edge_with_non_hashable_endpoint():
    data = build_from_extraction({
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [{"source": "a", "target": ["b"], "relation": "calls"}, {"source": "a", "target": "b", "relation": "imports"}],
    })
    assert data.node_count == 2 and data.edge_count == 1


def test_graph_has_legacy_ids_detects_old_scheme():
    old = [{"id": "api_readme", "source_file": "docs/v1/api/README.md", "type": "document", "source_location": "L1"}]
    new = [{"id": "docs_v1_api_readme", "source_file": "docs/v1/api/README.md", "type": "document", "source_location": "L1"}]
    assert graph_has_legacy_ids(old, root=".")
    assert not graph_has_legacy_ids(new, root=".")


def test_semantic_rekey_relative_vs_absolute_source_file():
    assert _semantic_id_remap([{"id": "api_readme", "source_file": "docs/v1/api/README.md", "type": "document"}], ".") == {"api_readme": "docs_v1_api_readme"}
    assert _semantic_id_remap([{"id": "api_readme", "source_file": "/abs/docs/v1/api/README.md", "type": "document"}], None) == {}


def test_cross_language_imports_references_are_dropped():
    data = build_from_extraction({
        "nodes": [
            {"id": "py", "source_file": "backend/worker.py", "_origin": "ast"},
            {"id": "ts", "source_file": "src/time.ts", "_origin": "ast"},
            {"id": "util", "source_file": "src/util.ts", "_origin": "ast"},
        ],
        "edges": [{"source": "py", "target": "ts", "relation": "imports"}, {"source": "ts", "target": "util", "relation": "imports"}],
    })
    assert not _has_edge(data, "py", "ts")
    assert _has_edge(data, "ts", "util")


def test_cross_family_reference_to_unknown_ext_is_kept():
    data = build_from_extraction({
        "nodes": [{"id": "pkg", "source_file": "package.json", "_origin": "ast"}, {"id": "app", "source_file": "src/app.ts", "_origin": "ast"}],
        "edges": [{"source": "pkg", "target": "app", "relation": "references"}],
    })
    assert _has_edge(data, "pkg", "app")


def test_markdown_doc_twin_merges_into_semantic_doc_node():
    data = build_from_extraction({
        "nodes": [
            {"id": "docs_readme_doc", "file_type": "document", "source_file": "docs/readme.md"},
            {"id": "docs_readme", "file_type": "document", "source_file": "docs/readme.md"},
            {"id": "auth", "source_file": "auth.py"},
        ],
        "edges": [{"source": "docs_readme", "target": "auth", "relation": "references"}],
    })
    assert "docs_readme" not in _ids(data)
    assert _has_edge(data, "docs_readme_doc", "auth")


def test_doc_twin_merge_does_not_touch_code_symbols():
    data = build_from_extraction({
        "nodes": [{"id": "m_foo", "file_type": "code", "source_file": "m.py"}, {"id": "m_foo_doc", "file_type": "rationale", "source_file": "m.py"}],
        "edges": [],
    })
    assert _ids(data) == {"m_foo", "m_foo_doc"}


def test_build_from_json_prunes_dangling_hyperedge_members(capsys):
    data = build_from_extraction({
        "nodes": [{"id": "alpha"}, {"id": "beta"}],
        "edges": [],
        "hyperedges": [{"id": "partial", "nodes": ["alpha", "beta", "ghost"]}, {"id": "gone", "nodes": ["ghost"]}],
    })
    assert data.attributes["hyperedges"] == [{"id": "partial", "nodes": ["alpha", "beta"]}]
    assert "gone" in capsys.readouterr().err
