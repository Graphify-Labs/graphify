import networkx as nx
import pytest

from graphify.export import to_obsidian


@pytest.mark.parametrize("graph_type", [nx.DiGraph, nx.MultiDiGraph])
def test_incoming_connection_counts_toward_community_reach(tmp_path, graph_type):
    graph = graph_type()
    graph.add_node("caller", label="Caller")
    graph.add_node("target", label="Target")
    graph.add_edge("caller", "target", relation="calls", confidence="INFERRED")

    to_obsidian(graph, {0: ["caller"], 1: ["target"]}, str(tmp_path))

    community_note = (tmp_path / "_COMMUNITY_Community 1.md").read_text(encoding="utf-8")
    assert "[[Target]] - degree 1, connects to 1 community" in community_note
    target_note = (tmp_path / "Target.md").read_text(encoding="utf-8")
    assert "  - graphify/INFERRED\n" in target_note


def test_self_loop_counts_once_for_dominant_confidence(tmp_path):
    graph = nx.MultiDiGraph()
    graph.add_node("caller", label="Caller")
    graph.add_node("target", label="Target")
    graph.add_edge("caller", "target", relation="calls", confidence="INFERRED")
    graph.add_edge("caller", "target", relation="references", confidence="INFERRED")
    graph.add_edge("target", "target", relation="calls", confidence="EXTRACTED")

    to_obsidian(graph, {0: ["caller"], 1: ["target"]}, str(tmp_path))

    target_note = (tmp_path / "Target.md").read_text(encoding="utf-8")
    assert "  - graphify/INFERRED\n" in target_note
