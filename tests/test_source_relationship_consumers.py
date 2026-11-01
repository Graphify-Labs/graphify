"""INC-QML-89: consumer views retain distinct source relationships on one pair."""
from __future__ import annotations

import json
import sys

import networkx as nx
import pytest

from graphify.cli import dispatch_command
from graphify.export import to_canvas
from graphify.wiki import _god_node_article
from tests.source_relationship_helpers import source_graph, write_graph


def test_req_qml022_ac06_explain_lists_local_ownership_and_call(tmp_path, monkeypatch, capsys):
    """An actual persisted local callable has two connections, both visible to explain."""
    graph, caller, _local = source_graph(tmp_path)
    path = write_graph(graph, tmp_path / "graph.json")
    monkeypatch.setattr(sys, "argv", ["graphify", "explain", caller, "--all", "--graph", str(path)])
    dispatch_command("explain")
    text = capsys.readouterr().out
    assert "[contains]" in text and "[calls]" in text


def test_req_qml022_ac06_wiki_lists_both_local_relationship_groups(tmp_path):
    """Wiki degree and relationship groups describe the same accepted edge facts."""
    graph, caller, _local = source_graph(tmp_path)
    article = _god_node_article(graph, caller, {})
    assert "### contains" in article and "### calls" in article


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml022_ac06_canvas_ids_distinguish_relations_and_directions(tmp_path, directed):
    """Canvas uses unique stable IDs for parallel and opposite source relationships."""
    graph, caller, local = source_graph(tmp_path, directed=directed)
    graph.add_edge(local, caller, relation="calls", confidence="EXTRACTED", _src=local, _tgt=caller)
    path = tmp_path / "graph.canvas"
    to_canvas(graph, {}, str(path))
    first = json.loads(path.read_text())
    assert len(first["edges"]) == len({edge["id"] for edge in first["edges"]})
    pair = [edge for edge in first["edges"]
            if {edge["fromNode"], edge["toNode"]} == {f"n_{caller}", f"n_{local}"}]
    assert len(pair) == 3
    to_canvas(graph, {}, str(path))
    assert json.loads(path.read_text()) == first


def test_req_qml022_ac06_canvas_legacy_simple_graph_retains_pair_id(tmp_path):
    """Ordinary legacy graphs retain their existing IDs and simple topology."""
    graph = nx.Graph()
    graph.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    path = tmp_path / "legacy.canvas"
    to_canvas(graph, {}, str(path))
    assert json.loads(path.read_text())["edges"][0]["id"] == "e_a_b"
