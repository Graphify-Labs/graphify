"""Tests for analyze.py."""
import json
import pytest
from pathlib import Path
from graphify.build import build_from_extraction
from graphify.cluster import cluster
from graphify.analyze import god_nodes, surprising_connections, _is_concept_node, graph_diff, _surprise_score, _file_category, _is_json_key_node, find_import_cycles, suggest_questions
from graphify.extract import _make_id
from graphify.helix.access import first_edge_attributes
from tests.native_helpers import graph_from_build, graph_from_payload

FIXTURES = Path(__file__).parents[1] / "fixtures"


def make_graph():
    return graph_from_build(build_from_extraction(json.loads((FIXTURES / "extraction.json").read_text())))


def _edge(graph, source, target):
    return first_edge_attributes(graph, source, target)


def _degrees(graph):
    return {row.node_id: int(row.degree) for row in graph.degrees()}


def test_god_nodes_returns_list():
    G = make_graph()
    result = god_nodes(G, top_n=3)
    assert isinstance(result, list)
    assert len(result) <= 3


def test_god_nodes_sorted_by_degree():
    G = make_graph()
    result = god_nodes(G, top_n=30)
    degrees = [r["degree"] for r in result]
    assert degrees == sorted(degrees, reverse=True)


def test_god_nodes_have_required_keys():
    G = make_graph()
    result = god_nodes(G, top_n=1)
    assert "id" in result[0]
    assert "label" in result[0]
    assert "degree" in result[0]


def test_surprising_connections_cross_source_multi_file():
    """Multi-file graph: should find cross-file edges between real entities."""
    G = make_graph()
    communities = cluster(G)
    surprises = surprising_connections(G, communities)
    assert len(surprises) > 0
    for s in surprises:
        assert s["source_files"][0] != s["source_files"][1]


def test_surprising_connections_excludes_concept_nodes():
    """Concept nodes (empty source_file) must not appear in surprises."""
    extraction = json.loads((FIXTURES / "extraction.json").read_text())
    extraction["nodes"].append({"id": "concept_x", "label": "Abstract Concept", "file_type": "document", "source_file": ""})
    extraction["edges"].append({"source": "n_transformer", "target": "concept_x", "relation": "relates_to", "confidence": "INFERRED", "source_file": "", "weight": 0.5})
    G = graph_from_build(build_from_extraction(extraction))
    communities = cluster(G)
    surprises = surprising_connections(G, communities)
    labels = [s["source"] for s in surprises] + [s["target"] for s in surprises]
    assert "Abstract Concept" not in labels


def test_surprising_connections_single_file_uses_community_bridges():
    """Single-file graph: should return cross-community edges, not empty list."""
    nodes = [
        {"id": f"a{i}", "label": f"A{i}", "file_type": "code", "source_file": "single.py", "source_location": f"L{i}"}
        for i in range(5)
    ] + [
        {"id": f"b{i}", "label": f"B{i}", "file_type": "code", "source_file": "single.py", "source_location": f"L{i+10}"}
        for i in range(5)
    ]
    edges = [
        {"source": f"a{i}", "target": f"a{i+1}", "relation": "calls", "confidence": "EXTRACTED", "source_file": "single.py", "weight": 1.0}
        for i in range(4)
    ] + [
        {"source": f"b{i}", "target": f"b{i+1}", "relation": "calls", "confidence": "EXTRACTED", "source_file": "single.py", "weight": 1.0}
        for i in range(4)
    ] + [{"source": "a4", "target": "b0", "relation": "references", "confidence": "INFERRED", "source_file": "single.py", "weight": 0.5}]
    G = graph_from_payload(nodes, edges)

    communities = cluster(G)
    surprises = surprising_connections(G, communities)
    # Should find at least the bridge edge
    assert len(surprises) > 0


def test_surprising_connections_ambiguous_scores_higher_than_extracted():
    """AMBIGUOUS edge should score higher than an otherwise identical EXTRACTED edge."""
    nodes = [
        ("a", "Alpha", "repo1/model.py"),
        ("b", "Beta", "repo2/train.py"),
        ("c", "Gamma", "repo1/data.py"),
        ("d", "Delta", "repo2/eval.py"),
    ]
    G = graph_from_payload(
        [{"id": nid, "label": label, "source_file": src, "file_type": "code"} for nid, label, src in nodes],
        [{"source": "a", "target": "b", "relation": "calls", "confidence": "AMBIGUOUS", "weight": 1.0, "source_file": "repo1/model.py"}, {"source": "c", "target": "d", "relation": "calls", "confidence": "EXTRACTED", "weight": 1.0, "source_file": "repo1/data.py"}],
    )
    communities = {0: ["a", "c"], 1: ["b", "d"]}
    nc = {"a": 0, "c": 0, "b": 1, "d": 1}
    score_amb, _ = _surprise_score(G, "a", "b", _edge(G, "a", "b"), nc, "repo1/model.py", "repo2/train.py")
    score_ext, _ = _surprise_score(G, "c", "d", _edge(G, "c", "d"), nc, "repo1/data.py", "repo2/eval.py")
    assert score_amb > score_ext


def test_surprise_score_accepts_precomputed_degrees():
    nodes = [
        ("hub", "Hub", "repo1/hub.py"),
        ("leaf", "Leaf", "repo2/leaf.py"),
        ("n1", "N1", "repo1/n1.py"),
        ("n2", "N2", "repo1/n2.py"),
        ("n3", "N3", "repo1/n3.py"),
        ("n4", "N4", "repo1/n4.py"),
    ]
    G = graph_from_payload(
        [{"id": nid, "label": label, "source_file": src, "file_type": "code"} for nid, label, src in nodes],
        [{"source": "hub", "target": node, "relation": "calls", "confidence": "EXTRACTED", "weight": 1.0} for node in ("leaf", "n1", "n2", "n3", "n4")],
    )

    nc = {"hub": 0, "leaf": 1}
    edge = _edge(G, "hub", "leaf")
    args = (G, "hub", "leaf", edge, nc, "repo1/hub.py", "repo2/leaf.py")

    assert _surprise_score(*args) == _surprise_score(*args, _degrees(G))


def test_surprising_connections_cross_type_scores_higher():
    """Code↔paper edge should score higher than code↔code edge."""
    nodes = [
        ("a", "Transformer", "code/model.py"),
        ("b", "FlashAttn", "papers/flash.pdf"),
        ("c", "Trainer", "code/train.py"),
        ("d", "Dataset", "code/data.py"),
    ]
    G = graph_from_payload(
        [{"id": nid, "label": label, "source_file": src, "file_type": "code"} for nid, label, src in nodes],
        [{"source": "a", "target": "b", "relation": "references", "confidence": "EXTRACTED", "weight": 1.0, "source_file": "code/model.py"}, {"source": "c", "target": "d", "relation": "calls", "confidence": "EXTRACTED", "weight": 1.0, "source_file": "code/train.py"}],
    )
    nc = {"a": 0, "b": 1, "c": 0, "d": 0}
    score_cross, reasons_cross = _surprise_score(G, "a", "b", _edge(G, "a", "b"), nc, "code/model.py", "papers/flash.pdf")
    score_same, _ = _surprise_score(G, "c", "d", _edge(G, "c", "d"), nc, "code/train.py", "code/data.py")
    assert score_cross > score_same
    assert any("code" in r and "paper" in r for r in reasons_cross)


def _make_cross_lang_graph(relation="calls", confidence="INFERRED"):
    """Helper: Python node in backend/, TypeScript node in frontend/, different communities."""
    return graph_from_payload(
        [
            {"id": "py_auth", "label": "AuthError", "source_file": "backend/auth.py", "file_type": "code"},
            {"id": "ts_member", "label": "Member", "source_file": "frontend/types.ts", "file_type": "code"},
            {"id": "py_a", "label": "ServiceA", "source_file": "backend/service.py", "file_type": "code"},
            {"id": "py_b", "label": "ServiceB", "source_file": "backend/utils.py", "file_type": "code"},
        ],
        [
            {"source": "py_auth", "target": "ts_member", "relation": relation, "confidence": confidence, "weight": 0.85, "source_file": "backend/auth.py"},
            {"source": "py_a", "target": "py_b", "relation": "calls", "confidence": "EXTRACTED", "weight": 1.0, "source_file": "backend/service.py"},
        ],
    )


def test_cross_language_inferred_calls_suppressed():
    """Cross-language INFERRED calls edge should score lower than same-language EXTRACTED."""
    G = _make_cross_lang_graph("calls", "INFERRED")
    nc = {"py_auth": 0, "ts_member": 1, "py_a": 0, "py_b": 0}
    score_cross, _ = _surprise_score(G, "py_auth", "ts_member",
                                      _edge(G, "py_auth", "ts_member"), nc,
                                      "backend/auth.py", "frontend/types.ts")
    score_same, _ = _surprise_score(G, "py_a", "py_b",
                                     _edge(G, "py_a", "py_b"), nc,
                                     "backend/service.py", "backend/utils.py")
    assert score_cross <= score_same


def test_cross_language_inferred_uses_suppressed():
    """Cross-language INFERRED uses edge (the exact rsl-siege-manager false positive) should be suppressed."""
    G = _make_cross_lang_graph("uses", "INFERRED")
    nc = {"py_auth": 0, "ts_member": 1, "py_a": 0, "py_b": 0}
    score_cross, _ = _surprise_score(G, "py_auth", "ts_member",
                                      _edge(G, "py_auth", "ts_member"), nc,
                                      "backend/auth.py", "frontend/types.ts")
    score_same, _ = _surprise_score(G, "py_a", "py_b",
                                     _edge(G, "py_a", "py_b"), nc,
                                     "backend/service.py", "backend/utils.py")
    assert score_cross <= score_same


def test_cross_language_semantically_similar_not_suppressed():
    """`semantically_similar_to` across languages is a genuine insight — must not be suppressed."""
    G = _make_cross_lang_graph("semantically_similar_to", "INFERRED")
    nc = {"py_auth": 0, "ts_member": 1, "py_a": 0, "py_b": 0}
    score_sem, _ = _surprise_score(G, "py_auth", "ts_member",
                                    _edge(G, "py_auth", "ts_member"), nc,
                                    "backend/auth.py", "frontend/types.ts")
    score_same, _ = _surprise_score(G, "py_a", "py_b",
                                     _edge(G, "py_a", "py_b"), nc,
                                     "backend/service.py", "backend/utils.py")
    assert score_sem > score_same


def test_same_language_inferred_calls_not_suppressed():
    """INFERRED calls within the same language family must not be affected."""
    G = graph_from_payload(
        [{"id": f"py_{name}", "label": f"Module{name.upper()}", "source_file": f"src/{name}.py", "file_type": "code"} for name in "abcd"],
        [{"source": "py_a", "target": "py_b", "relation": "calls", "confidence": "INFERRED", "weight": 0.8, "source_file": "src/a.py"}, {"source": "py_c", "target": "py_d", "relation": "calls", "confidence": "EXTRACTED", "weight": 1.0, "source_file": "src/c.py"}],
    )
    nc = {"py_a": 0, "py_b": 1, "py_c": 0, "py_d": 1}
    score_inf, _ = _surprise_score(G, "py_a", "py_b", _edge(G, "py_a", "py_b"), nc,
                                    "src/a.py", "src/b.py")
    score_ext, _ = _surprise_score(G, "py_c", "py_d", _edge(G, "py_c", "py_d"), nc,
                                    "src/c.py", "src/d.py")
    assert score_inf > score_ext


def test_cross_language_extracted_calls_not_suppressed():
    """EXTRACTED cross-language edges are real structural facts — must not be penalised."""
    G = _make_cross_lang_graph("calls", "EXTRACTED")
    nc = {"py_auth": 0, "ts_member": 1}
    score, _ = _surprise_score(G, "py_auth", "ts_member",
                                _edge(G, "py_auth", "ts_member"), nc,
                                "backend/auth.py", "frontend/types.ts")
    assert score >= 1


def test_surprising_connections_have_why_field():
    G = make_graph()
    communities = cluster(G)
    for s in surprising_connections(G, communities):
        assert "why" in s
        assert isinstance(s["why"], str)
        assert len(s["why"]) > 0


def test_file_category():
    assert _file_category("model.py") == "code"
    assert _file_category("flash.pdf") == "paper"
    assert _file_category("diagram.png") == "image"
    assert _file_category("notes.md") == "doc"
    # Languages added in later releases — would misclassify as "doc" without detect.py import
    assert _file_category("app.swift") == "code"
    assert _file_category("plugin.lua") == "code"
    assert _file_category("build.zig") == "code"
    assert _file_category("deploy.ps1") == "code"
    assert _file_category("server.ex") == "code"
    assert _file_category("component.jsx") == "code"
    assert _file_category("analysis.jl") == "code"
    assert _file_category("view.m") == "code"


def test_is_concept_node_empty_source():
    G = graph_from_payload([{"id": "c1", "source_file": ""}])
    assert _is_concept_node(G, "c1") is True


def test_is_concept_node_real_file():
    G = graph_from_payload([{"id": "n1", "source_file": "model.py"}])
    assert _is_concept_node(G, "n1") is False


def test_surprising_connections_have_required_keys():
    G = make_graph()
    communities = cluster(G)
    for s in surprising_connections(G, communities):
        assert "source" in s
        assert "target" in s
        assert "source_files" in s
        assert "confidence" in s


# --- graph_diff tests ---

def _make_simple_graph(nodes, edges):
    """Build a small immutable native graph from node/edge specs."""
    return graph_from_payload(
        [{"id": node_id, "label": label, "source_file": "test.py"} for node_id, label in nodes],
        [{"source": src, "target": tgt, "relation": rel, "confidence": conf} for src, tgt, rel, conf in edges],
    )


def test_graph_diff_new_nodes():
    G_old = _make_simple_graph([("n1", "Alpha"), ("n2", "Beta")], [])
    G_new = _make_simple_graph([("n1", "Alpha"), ("n2", "Beta"), ("n3", "Gamma")], [])
    diff = graph_diff(G_old, G_new)
    assert len(diff["new_nodes"]) == 1
    assert diff["new_nodes"][0]["id"] == "n3"
    assert diff["new_nodes"][0]["label"] == "Gamma"
    assert diff["removed_nodes"] == []
    assert "1 new node" in diff["summary"]


def test_graph_diff_removed_nodes():
    G_old = _make_simple_graph([("n1", "Alpha"), ("n2", "Beta"), ("n3", "Gamma")], [])
    G_new = _make_simple_graph([("n1", "Alpha"), ("n2", "Beta")], [])
    diff = graph_diff(G_old, G_new)
    assert diff["new_nodes"] == []
    assert len(diff["removed_nodes"]) == 1
    assert diff["removed_nodes"][0]["id"] == "n3"
    assert "removed" in diff["summary"]


def test_graph_diff_new_edges():
    nodes = [("n1", "Alpha"), ("n2", "Beta"), ("n3", "Gamma")]
    G_old = _make_simple_graph(nodes, [("n1", "n2", "calls", "EXTRACTED")])
    G_new = _make_simple_graph(
        nodes,
        [("n1", "n2", "calls", "EXTRACTED"), ("n2", "n3", "uses", "INFERRED")],
    )
    diff = graph_diff(G_old, G_new)
    assert len(diff["new_edges"]) == 1
    new_edge = diff["new_edges"][0]
    assert new_edge["relation"] == "uses"
    assert new_edge["confidence"] == "INFERRED"
    assert diff["removed_edges"] == []
    assert "new edge" in diff["summary"]


def test_graph_diff_empty_diff():
    nodes = [("n1", "Alpha"), ("n2", "Beta")]
    edges = [("n1", "n2", "calls", "EXTRACTED")]
    G_old = _make_simple_graph(nodes, edges)
    G_new = _make_simple_graph(nodes, edges)
    diff = graph_diff(G_old, G_new)
    assert diff["new_nodes"] == []
    assert diff["removed_nodes"] == []
    assert diff["new_edges"] == []
    assert diff["removed_edges"] == []
    assert diff["summary"] == "no changes"


# --- code↔doc INFERRED suppression tests ---

def _make_code_doc_graph(relation="calls", confidence="INFERRED"):
    return graph_from_payload(
        [
            {"id": "py_fn", "label": "ProcessData", "source_file": "src/processor.py", "file_type": "code"},
            {"id": "md_doc", "label": "README Section", "source_file": "docs/readme.md", "file_type": "document"},
            {"id": "py_a", "label": "ServiceA", "source_file": "src/service.py", "file_type": "code"},
            {"id": "py_b", "label": "ServiceB", "source_file": "src/utils.py", "file_type": "code"},
        ],
        [
            {"source": "py_fn", "target": "md_doc", "relation": relation, "confidence": confidence, "weight": 0.85, "source_file": "src/processor.py"},
            {"source": "py_a", "target": "py_b", "relation": "calls", "confidence": "EXTRACTED", "weight": 1.0, "source_file": "src/service.py"},
        ],
    )


def test_code_doc_inferred_calls_suppressed():
    """Code→doc INFERRED calls edge should score lower than same-language EXTRACTED."""
    G = _make_code_doc_graph("calls", "INFERRED")
    nc = {"py_fn": 0, "md_doc": 1, "py_a": 0, "py_b": 0}
    score_noise, _ = _surprise_score(G, "py_fn", "md_doc",
                                     _edge(G, "py_fn", "md_doc"), nc,
                                     "src/processor.py", "docs/readme.md")
    score_real, _ = _surprise_score(G, "py_a", "py_b",
                                    _edge(G, "py_a", "py_b"), nc,
                                    "src/service.py", "src/utils.py")
    assert score_noise <= score_real


def test_code_doc_inferred_uses_suppressed():
    """Code→doc INFERRED uses edge should score lower than same-language EXTRACTED."""
    G = _make_code_doc_graph("uses", "INFERRED")
    nc = {"py_fn": 0, "md_doc": 1, "py_a": 0, "py_b": 0}
    score_noise, _ = _surprise_score(G, "py_fn", "md_doc",
                                     _edge(G, "py_fn", "md_doc"), nc,
                                     "src/processor.py", "docs/readme.md")
    score_real, _ = _surprise_score(G, "py_a", "py_b",
                                    _edge(G, "py_a", "py_b"), nc,
                                    "src/service.py", "src/utils.py")
    assert score_noise <= score_real


def test_code_doc_extracted_calls_not_suppressed():
    """EXTRACTED code↔doc edges are real facts — must not be penalised."""
    G = _make_code_doc_graph("calls", "EXTRACTED")
    nc = {"py_fn": 0, "md_doc": 1}
    score, _ = _surprise_score(G, "py_fn", "md_doc",
                               _edge(G, "py_fn", "md_doc"), nc,
                               "src/processor.py", "docs/readme.md")
    assert score >= 1


def test_code_doc_inferred_semantically_similar_not_suppressed():
    """`semantically_similar_to` across code↔doc is explicit LLM insight — must not be suppressed."""
    G = _make_code_doc_graph("semantically_similar_to", "INFERRED")
    nc = {"py_fn": 0, "md_doc": 1, "py_a": 0, "py_b": 0}
    score_sem, _ = _surprise_score(G, "py_fn", "md_doc",
                                   _edge(G, "py_fn", "md_doc"), nc,
                                   "src/processor.py", "docs/readme.md")
    score_same, _ = _surprise_score(G, "py_a", "py_b",
                                    _edge(G, "py_a", "py_b"), nc,
                                    "src/service.py", "src/utils.py")
    assert score_sem > score_same


def test_code_unknown_extension_inferred_calls_suppressed():
    """_file_category falls back to 'doc' for unknown extensions, so INFERRED
    calls/uses to unknown-extension files are suppressed the same as code↔doc."""
    assert _file_category("vendor/random.xyz") == "doc"
    G = graph_from_payload(
        [{"id": "py_fn", "label": "Handler", "source_file": "src/handler.py", "file_type": "code"}, {"id": "unk", "label": "Handler", "source_file": "vendor/unknown.xyz", "file_type": "document"}, {"id": "py_a", "label": "A", "source_file": "src/a.py", "file_type": "code"}, {"id": "py_b", "label": "B", "source_file": "src/b.py", "file_type": "code"}],
        [{"source": "py_fn", "target": "unk", "relation": "calls", "confidence": "INFERRED", "weight": 0.8, "source_file": "src/handler.py"}, {"source": "py_a", "target": "py_b", "relation": "calls", "confidence": "EXTRACTED", "weight": 1.0, "source_file": "src/a.py"}],
    )
    nc = {"py_fn": 0, "unk": 1, "py_a": 0, "py_b": 0}
    score_unk, _ = _surprise_score(G, "py_fn", "unk",
                                   _edge(G, "py_fn", "unk"), nc,
                                   "src/handler.py", "vendor/unknown.xyz")
    score_same, _ = _surprise_score(G, "py_a", "py_b",
                                    _edge(G, "py_a", "py_b"), nc,
                                    "src/a.py", "src/b.py")
    assert score_unk <= score_same


def test_code_paper_inferred_calls_not_suppressed():
    """Code↔paper INFERRED calls should still surface — it is a meaningful link."""
    G = graph_from_payload(
        [{"id": "py_model", "label": "Transformer", "source_file": "src/model.py", "file_type": "code"}, {"id": "pdf_paper", "label": "Attention Is All You Need", "source_file": "papers/vaswani.pdf", "file_type": "paper"}, {"id": "py_a", "label": "ServiceA", "source_file": "src/service.py", "file_type": "code"}, {"id": "py_b", "label": "ServiceB", "source_file": "src/utils.py", "file_type": "code"}],
        [{"source": "py_model", "target": "pdf_paper", "relation": "calls", "confidence": "INFERRED", "weight": 0.8, "source_file": "src/model.py"}, {"source": "py_a", "target": "py_b", "relation": "calls", "confidence": "EXTRACTED", "weight": 1.0, "source_file": "src/service.py"}],
    )
    nc = {"py_model": 0, "pdf_paper": 1, "py_a": 0, "py_b": 1}
    score_cross, _ = _surprise_score(G, "py_model", "pdf_paper",
                                     _edge(G, "py_model", "pdf_paper"), nc,
                                     "src/model.py", "papers/vaswani.pdf")
    score_same, _ = _surprise_score(G, "py_a", "py_b",
                                    _edge(G, "py_a", "py_b"), nc,
                                    "src/service.py", "src/utils.py")
    assert score_cross > score_same


# --- JSON key node filtering tests ---

def test_is_json_key_node_noise_label():
    G = graph_from_payload([{"id": "j1", "label": "name", "source_file": "schema.json"}])
    assert _is_json_key_node(G, "j1") is True


def test_is_json_key_node_non_json_file():
    G = graph_from_payload([{"id": "n1", "label": "name", "source_file": "model.py"}])
    assert _is_json_key_node(G, "n1") is False


# --- npm dep-block key god-node filtering tests ---

@pytest.mark.parametrize("dep_key", [
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
    "bundledDependencies",
])
def test_god_nodes_excludes_npm_dep_block_keys(dep_key: str) -> None:
    """npm package.json dep-block keys must be filtered from god_nodes output.

    Constructs a small graph with one node labelled with an npm dep-block key
    (sourced from a .json file) and one real-domain node that has high degree.
    Asserts that god_nodes() excludes the dep-block node even when it has the
    highest degree, while the real-domain node is included.

    Args:
        dep_key: The npm dependency-block key label to test (parametrized).
    """
    G = graph_from_payload(
        [{"id": "real_node", "label": "AuthService", "source_file": "src/auth.py", "file_type": "code", "source_location": "L1"}, {"id": "dep_node", "label": dep_key, "source_file": "frontend/package.json", "file_type": "code", "source_location": "L1"}]
        + [{"id": f"pkg_{i}", "label": f"package-{i}", "source_file": "frontend/package.json", "file_type": "code", "source_location": f"L{i + 2}"} for i in range(20)],
        [{"source": "dep_node", "target": f"pkg_{i}", "relation": "contains", "confidence": "EXTRACTED", "source_file": "frontend/package.json", "weight": 1.0} for i in range(20)]
        + [{"source": "real_node", "target": "dep_node", "relation": "imports", "confidence": "EXTRACTED", "source_file": "src/auth.py", "weight": 1.0}],
    )

    result = god_nodes(G, top_n=30)
    result_ids = [r["id"] for r in result]

    assert "dep_node" not in result_ids, (
        f"god_nodes() should filter npm dep-block key '{dep_key}' "
        f"but it appeared in the result: {result}"
    )
    assert "real_node" in result_ids, (
        f"god_nodes() should include real-domain node 'AuthService' "
        f"but it was absent: {result}"
    )


def test_is_json_key_node_real_label():
    G = graph_from_payload([{"id": "j2", "label": "UserProfile", "source_file": "schema.json"}])
    assert _is_json_key_node(G, "j2") is False


def test_god_nodes_excludes_json_noise():
    """god_nodes must not return generic JSON key nodes like 'name' or 'id'."""
    G = graph_from_payload(
        [{"id": "real", "label": "AuthService", "source_file": "src/auth.py"}, {"id": "json_name", "label": "name", "source_file": "schema.json"}]
        + [{"id": f"peer{i}", "label": f"Peer{i}", "source_file": f"src/peer{i}.py"} for i in range(8)],
        [{"source": hub, "target": f"peer{i}"} for i in range(8) for hub in ("json_name", "real")],
    )
    result = god_nodes(G, top_n=10)
    labels = [r["label"] for r in result]
    assert "name" not in labels
    assert "AuthService" in labels


def test_god_nodes_filter_is_case_insensitive():
    """JSON-key filter must match regardless of label casing."""
    variants = ("Start", "START", "Name", "ID")
    G = graph_from_payload(
        [{"id": "real", "label": "RealAbstraction", "source_file": "libs/real.py"}]
        + [{"id": f"peer{i}", "label": f"P{i}", "source_file": f"src/p{i}.py"} for i in range(3)]
        + [{"id": f"json_{index}_{variant.lower()}", "label": variant, "source_file": "testhelpers/data.json"} for index, variant in enumerate(variants)]
        + [{"id": f"json_{index}_{variant.lower()}_t{i}", "label": f"X{i}", "source_file": "testhelpers/data.json"} for index, variant in enumerate(variants) for i in range(15)],
        [{"source": "real", "target": f"peer{i}"} for i in range(3)]
        + [{"source": f"json_{index}_{variant.lower()}_t{i}", "target": f"json_{index}_{variant.lower()}"} for index, variant in enumerate(variants) for i in range(15)],
    )
    result = god_nodes(G, top_n=10)
    labels = [r["label"] for r in result]
    for variant in ("Start", "START", "Name", "ID"):
        assert variant not in labels, f"`{variant}` should be filtered as JSON-key noise"


def test_suggest_questions_excludes_rationale_nodes_from_isolated_count():
    G = graph_from_payload([{"id": "service", "label": "Service", "file_type": "code", "source_file": "service.py"}, {"id": "reason", "label": "Explains service", "file_type": "rationale", "source_file": "service.py"}])

    questions = suggest_questions(G, communities={}, community_labels={}, top_n=10)
    isolated = next(question for question in questions if question["type"] == "isolated_nodes")

    assert isolated["why"].startswith("1 weakly-connected node")
    assert "`Service`" in isolated["question"]
    assert "Explains service" not in isolated["question"]


# ── find_import_cycles tests ──────────────────────────────────────────────────


def _make_file_node(path: str) -> tuple[str, dict]:
    """Create a graph node resembling real graphify schema."""
    nid = _make_id(path)
    return nid, {"label": Path(path).name, "source_file": path, "file_type": "code"}


def _cycle_payload():
    a_id, a = _make_file_node("src/a.ts")
    b_id, b = _make_file_node("src/b.ts")
    c_id, c = _make_file_node("src/c.ts")
    d_id, d = _make_file_node("src/d.ts")
    ext_id = _make_id("react")

    nodes = [{"id": a_id, **a}, {"id": b_id, **b}, {"id": c_id, **c}, {"id": d_id, **d}, {"id": ext_id, "label": "react", "file_type": "code"}]
    edges = [
        {"source": a_id, "target": b_id, "relation": "imports_from", "source_file": "src/a.ts", "confidence": "EXTRACTED"},
        {"source": b_id, "target": a_id, "relation": "imports_from", "source_file": "src/b.ts", "confidence": "EXTRACTED"},
        {"source": b_id, "target": c_id, "relation": "imports_from", "source_file": "src/b.ts", "confidence": "EXTRACTED"},
        {"source": c_id, "target": d_id, "relation": "imports_from", "source_file": "src/c.ts", "confidence": "EXTRACTED"},
        {"source": d_id, "target": b_id, "relation": "imports_from", "source_file": "src/d.ts", "confidence": "EXTRACTED"},
        {"source": c_id, "target": c_id, "relation": "imports_from", "source_file": "src/c.ts", "confidence": "EXTRACTED"},
        {"source": a_id, "target": ext_id, "relation": "calls", "source_file": "src/a.ts", "confidence": "INFERRED"},
        {"source": a_id, "target": ext_id, "relation": "contains", "source_file": "src/a.ts", "confidence": "EXTRACTED"},
        {"source": a_id, "target": ext_id, "relation": "imports_from", "source_file": "src/a.ts", "confidence": "EXTRACTED"},
    ]
    return nodes, edges


def _make_cycle_graph_directed():
    nodes, edges = _cycle_payload()
    return graph_from_payload(nodes, edges, kind="multidigraph")


def test_find_import_cycles_returns_structured_records():
    G = _make_cycle_graph_directed()
    cycles = find_import_cycles(G)
    assert isinstance(cycles, list)
    assert cycles
    assert isinstance(cycles[0], dict)
    assert "cycle" in cycles[0]
    assert "length" in cycles[0]
    assert "why" in cycles[0]


def test_find_import_cycles_detects_2_and_3_cycles():
    G = _make_cycle_graph_directed()
    cycles = find_import_cycles(G)
    cycle_sets = [set(c["cycle"]) for c in cycles]
    assert any({"src/a.ts", "src/b.ts"}.issubset(s) for s in cycle_sets)
    assert any({"src/b.ts", "src/c.ts", "src/d.ts"}.issubset(s) for s in cycle_sets)


def test_find_import_cycles_includes_self_loop_cycle():
    G = _make_cycle_graph_directed()
    cycles = find_import_cycles(G)
    assert any(c["cycle"] == ["src/c.ts"] and c["length"] == 1 for c in cycles)


def test_find_import_cycles_respects_max_cycle_length():
    G = _make_cycle_graph_directed()
    cycles = find_import_cycles(G, max_cycle_length=2)
    assert all(c["length"] <= 2 for c in cycles)


def test_find_import_cycles_skips_nodes_without_source_file():
    G = _make_cycle_graph_directed()
    cycles = find_import_cycles(G)
    flat = " ".join(" ".join(c["cycle"]) for c in cycles)
    assert "react" not in flat


def test_find_import_cycles_handles_undirected_graph_input():
    nodes, edges = _cycle_payload()
    Gu = graph_from_payload(nodes, edges, kind="multigraph")
    cycles = find_import_cycles(Gu)
    assert cycles  # should still resolve orientation via edge.source_file


def test_find_import_cycles_ignores_non_import_relations():
    a_id, a = _make_file_node("src/a.ts")
    b_id, b = _make_file_node("src/b.ts")
    G = graph_from_payload(
        [{"id": a_id, **a}, {"id": b_id, **b}],
        [{"source": a_id, "target": b_id, "relation": "calls", "source_file": "src/a.ts", "confidence": "INFERRED"}, {"source": b_id, "target": a_id, "relation": "contains", "source_file": "src/b.ts", "confidence": "EXTRACTED"}],
        kind="digraph",
    )
    assert find_import_cycles(G) == []


def test_find_import_cycles_empty_graph():
    assert find_import_cycles(graph_from_payload([], kind="digraph")) == []


def test_find_import_cycles_no_cycles():
    x_id, x = _make_file_node("x.ts")
    y_id, y = _make_file_node("y.ts")
    G = graph_from_payload(
        [{"id": x_id, **x}, {"id": y_id, **y}],
        [{"source": x_id, "target": y_id, "relation": "imports_from", "source_file": "x.ts", "confidence": "EXTRACTED"}],
        kind="digraph",
    )
    assert find_import_cycles(G) == []
