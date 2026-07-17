"""Analysis behavior on real embedded-Helix snapshots."""

from graphify.analyze import (
    _file_category,
    _is_concept_node,
    _is_json_key_node,
    _surprise_score,
    find_import_cycles,
    god_nodes,
    graph_diff,
    suggest_questions,
    surprising_connections,
)
from graphify.helix.access import first_edge_attributes
from tests.native_helpers import graph_from_payload, triangle


def _graph():
    return graph_from_payload(
        [
            {"id": "hub", "label": "Hub", "file_type": "code", "source_file": "src/hub.py"},
            {"id": "left", "label": "Left", "file_type": "code", "source_file": "src/left.py"},
            {"id": "right", "label": "Right", "file_type": "code", "source_file": "web/right.ts"},
            {"id": "doc", "label": "Design", "file_type": "document", "source_file": "docs/design.md"},
        ],
        [
            {"source": "hub", "target": "left", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "hub", "target": "right", "relation": "references", "confidence": "INFERRED"},
            {"source": "hub", "target": "doc", "relation": "documents", "confidence": "INFERRED"},
        ],
        kind="digraph",
    )


def test_analysis_runs_on_native_snapshot(tmp_path):
    graph = triangle(tmp_path).graph
    communities = {0: ["a", "b"], 1: ["c"]}
    assert god_nodes(graph)
    assert surprising_connections(graph, communities)
    assert suggest_questions(graph, communities, {0: "Core", 1: "Leaf"})


def test_god_nodes_are_ranked_and_structured():
    result = god_nodes(_graph(), top_n=3)
    assert result[0]["id"] == "hub"
    assert result[0]["degree"] == 3
    assert {"id", "label", "degree"} <= set(result[0])


def test_surprises_exclude_concepts_and_keep_cross_file_edges():
    graph = graph_from_payload(
        [
            {"id": "a", "label": "A", "file_type": "code", "source_file": "a.py"},
            {"id": "b", "label": "B", "file_type": "code", "source_file": "b.py"},
            {"id": "concept", "label": "Concept", "file_type": "document", "source_file": ""},
        ],
        [
            {"source": "a", "target": "b", "relation": "references", "confidence": "INFERRED"},
            {"source": "a", "target": "concept", "relation": "references", "confidence": "INFERRED"},
        ],
    )
    result = surprising_connections(graph, {0: ["a", "concept"], 1: ["b"]})
    labels = {item["source"] for item in result} | {item["target"] for item in result}
    assert result and "Concept" not in labels
    assert result[0]["source_files"][0] != result[0]["source_files"][1]
    assert result[0]["why"]


def test_surprise_scoring_retains_confidence_and_language_rules():
    graph = graph_from_payload(
        [
            {"id": "py", "label": "Auth", "source_file": "api/auth.py", "file_type": "code"},
            {"id": "ts", "label": "Member", "source_file": "web/types.ts", "file_type": "code"},
            {"id": "doc", "label": "Auth", "source_file": "docs/auth.md", "file_type": "document"},
        ],
        [
            {"source": "py", "target": "ts", "relation": "calls", "confidence": "INFERRED"},
            {"source": "py", "target": "doc", "relation": "semantically_similar_to", "confidence": "INFERRED"},
        ],
    )
    communities = {"py": 0, "ts": 1, "doc": 1}
    cross, _ = _surprise_score(
        graph, "py", "ts", first_edge_attributes(graph, "py", "ts"), communities,
        "api/auth.py", "web/types.ts",
    )
    semantic, _ = _surprise_score(
        graph, "py", "doc", first_edge_attributes(graph, "py", "doc"), communities,
        "api/auth.py", "docs/auth.md",
    )
    assert semantic > cross


def test_node_noise_helpers_use_native_attributes():
    graph = graph_from_payload([
        {"id": "concept", "source_file": ""},
        {"id": "json", "label": "dependencies", "source_file": "package.json"},
        {"id": "real", "label": "Auth", "source_file": "auth.py"},
    ])
    assert _is_concept_node(graph, "concept")
    assert _is_json_key_node(graph, "json")
    assert not _is_json_key_node(graph, "real")
    assert _file_category("paper.pdf") == "paper"


def test_graph_diff_native_nodes_and_edges():
    old = graph_from_payload([
        {"id": "a", "label": "A"}, {"id": "b", "label": "B"},
    ], [{"source": "a", "target": "b", "relation": "calls"}])
    new = graph_from_payload([
        {"id": "a", "label": "A"}, {"id": "c", "label": "C"},
    ], [{"source": "a", "target": "c", "relation": "uses"}])
    result = graph_diff(old, new)
    assert [row["id"] for row in result["new_nodes"]] == ["c"]
    assert [row["id"] for row in result["removed_nodes"]] == ["b"]
    assert result["new_edges"][0]["relation"] == "uses"
    assert result["removed_edges"][0]["relation"] == "calls"


def test_import_cycles_support_self_loops_and_length_limit():
    graph = graph_from_payload(
        [
            {"id": "a", "label": "A", "source_file": "a.py"},
            {"id": "b", "label": "B", "source_file": "b.py"},
            {"id": "c", "label": "C", "source_file": "c.py"},
        ],
        [
            {"source": "a", "target": "b", "relation": "imports_from", "source_file": "a.py"},
            {"source": "b", "target": "a", "relation": "imports_from", "source_file": "b.py"},
            {"source": "c", "target": "c", "relation": "imports_from", "source_file": "c.py"},
        ],
        kind="digraph",
    )
    cycles = find_import_cycles(graph, max_cycle_length=2)
    assert {tuple(item["cycle"]) for item in cycles}
    assert any(len(item["cycle"]) == 1 for item in cycles)
