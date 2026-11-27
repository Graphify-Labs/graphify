"""#4200 — GRAPH_REPORT.md collision banner at the top of the report."""
from __future__ import annotations
import networkx as nx
from graphify.report import generate, _label_collision_percent


def _detect_stub(total_files=5, total_words=100):
    return {"total_files": total_files, "total_words": total_words}


def test_collision_percent_zero_on_unique_labels():
    G = nx.Graph()
    for i in range(5):
        G.add_node(f"n{i}", label=f"Node{i}", source_file=f"src/n{i}.py")
    assert _label_collision_percent(G) == 0.0


def test_collision_percent_fires_on_same_label_different_source():
    G = nx.Graph()
    # Two `.getById` methods on different files: classic collision.
    G.add_node("a_getbyid", label=".getById()", source_file="src/a.py")
    G.add_node("b_getbyid", label=".getById()", source_file="src/b.py")
    G.add_node("other", label="Unique", source_file="src/c.py")
    assert _label_collision_percent(G) > 50.0


def test_collision_percent_ignores_concept_nodes():
    """Concept nodes (empty ``source_file``) must NOT drive the banner —
    repeated H1 titles in docs are not code collisions."""
    G = nx.Graph()
    G.add_node("concept1", label="Shared", source_file="")
    G.add_node("concept2", label="Shared", source_file="")
    G.add_node("code1", label="Code", source_file="src/a.py")
    assert _label_collision_percent(G) == 0.0


def test_collision_percent_ignores_missing_label_or_source():
    G = nx.Graph()
    G.add_node("n1", source_file="src/a.py")  # no label
    G.add_node("n2", label="Only")  # no source_file
    assert _label_collision_percent(G) == 0.0


def test_banner_present_when_collision_above_threshold():
    G = nx.Graph()
    for i in range(5):
        G.add_node(f"a{i}", label=".getById()", source_file=f"src/a{i}.py")
    for i in range(5):
        G.add_node(f"b{i}", label=f"Unique{i}", source_file=f"src/b{i}.py")
    for i in range(5):
        G.add_edge(f"a{i}", f"b{i}", confidence="EXTRACTED", weight=1.0)
    report = generate(
        G=G,
        communities={0: list(G.nodes)},
        cohesion_scores={0: 1.0},
        community_labels={0: "Test"},
        god_node_list=[],
        surprise_list=[],
        detection_result=_detect_stub(),
        token_cost={"input": 0, "output": 0},
        root="/tmp/testproj",
    )
    assert "Node-ID collisions detected" in report
    assert "graphify rebuild" in report


def test_banner_absent_when_no_collision():
    G = nx.Graph()
    for i in range(10):
        G.add_node(f"n{i}", label=f"Node{i}", source_file=f"src/n{i}.py")
    for i in range(9):
        G.add_edge(f"n{i}", f"n{i+1}", confidence="EXTRACTED", weight=1.0)
    report = generate(
        G=G,
        communities={0: list(G.nodes)},
        cohesion_scores={0: 1.0},
        community_labels={0: "Test"},
        god_node_list=[],
        surprise_list=[],
        detection_result=_detect_stub(),
        token_cost={"input": 0, "output": 0},
        root="/tmp/testproj",
    )
    assert "collisions detected" not in report
